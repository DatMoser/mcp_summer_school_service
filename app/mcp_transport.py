# app/mcp_transport.py
"""
MCP Transport Layer implementation.
Provides HTTP POST and Server-Sent Events transport for MCP protocol.
"""

import json
import asyncio
from typing import Dict, Any, Optional, AsyncGenerator
from fastapi import Request, HTTPException
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse
from app.mcp_protocol import mcp_handler, JsonRpcRequest
from app.mcp_endpoints import mcp_endpoints
import logging

logger = logging.getLogger(__name__)


class McpTransport:
    """
    MCP Transport layer implementing HTTP POST and Server-Sent Events.
    Handles message routing between JSON-RPC protocol and MCP endpoints.
    """
    
    def __init__(self):
        self.sse_connections: Dict[str, asyncio.Queue] = {}
    
    async def handle_json_rpc_post(self, request: Request) -> Dict[str, Any]:
        """
        Handle JSON-RPC over HTTP POST.
        Main entry point for MCP protocol messages.
        """
        try:
            # Parse request body
            body = await request.body()
            if not body:
                raise HTTPException(status_code=400, detail="Empty request body")
            
            message = body.decode('utf-8')
            logger.debug(f"Received MCP message: {message}")
            
            # Process through protocol handler
            response_json = await self._process_mcp_message(message)
            
            if response_json is None:
                # Notification - no response needed
                return {"jsonrpc": "2.0", "id": None, "result": None}
            
            response_data = json.loads(response_json)
            logger.debug(f"Sending MCP response: {response_data}")
            
            return response_data
            
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON")
        except Exception as e:
            logger.error(f"Error processing MCP request: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    async def _process_mcp_message(self, message: str) -> Optional[str]:
        """Process MCP message through protocol and endpoint handlers"""
        try:
            # Parse JSON-RPC request
            data = json.loads(message)
            request = JsonRpcRequest(**data)
            
            # First try protocol handler (initialize, ping, etc.)
            response = mcp_handler.route_request(request)
            if response:
                return response.json()
            
            # Route to MCP endpoints
            if request.method == "tools/list":
                response = mcp_endpoints.handle_tools_list(request)
            elif request.method == "tools/call":
                response = mcp_endpoints.handle_tools_call(request)
            elif request.method == "resources/list":
                response = mcp_endpoints.handle_resources_list(request)
            elif request.method == "resources/read":
                response = mcp_endpoints.handle_resources_read(request)
            elif request.method == "prompts/list":
                response = mcp_endpoints.handle_prompts_list(request)
            elif request.method == "prompts/get":
                response = mcp_endpoints.handle_prompts_get(request)
            else:
                # Unknown method
                response = mcp_handler.create_error_response(
                    request.id, -32601, f"Method not found: {request.method}"
                )
            
            return response.json()
            
        except Exception as e:
            logger.error(f"Error processing MCP message: {e}")
            error_response = mcp_handler.create_error_response(
                None, -32603, f"Internal error: {str(e)}"
            )
            return error_response.json()
    
    async def handle_sse_connection(self, client_id: str) -> EventSourceResponse:
        """
        Handle Server-Sent Events connection for real-time updates.
        Used for job progress notifications and dynamic capability changes.
        """
        async def event_generator() -> AsyncGenerator[Dict[str, Any], None]:
            # Create queue for this client
            queue = asyncio.Queue()
            self.sse_connections[client_id] = queue
            
            try:
                # Send initial connection event
                yield {
                    "event": "connected", 
                    "data": json.dumps({
                        "type": "connection_established",
                        "client_id": client_id,
                        "timestamp": asyncio.get_event_loop().time()
                    })
                }
                
                # Send periodic keep-alive and listen for messages
                while True:
                    try:
                        # Wait for message with timeout for keep-alive
                        message = await asyncio.wait_for(queue.get(), timeout=30.0)
                        yield {
                            "event": message.get("event", "message"),
                            "data": json.dumps(message.get("data", {}))
                        }
                    except asyncio.TimeoutError:
                        # Send keep-alive
                        yield {
                            "event": "keep-alive",
                            "data": json.dumps({
                                "type": "ping",
                                "timestamp": asyncio.get_event_loop().time()
                            })
                        }
            
            except asyncio.CancelledError:
                logger.info(f"SSE connection cancelled for client {client_id}")
            except Exception as e:
                logger.error(f"SSE error for client {client_id}: {e}")
                yield {
                    "event": "error",
                    "data": json.dumps({
                        "type": "connection_error", 
                        "error": str(e)
                    })
                }
            finally:
                # Clean up
                if client_id in self.sse_connections:
                    del self.sse_connections[client_id]
                logger.info(f"SSE connection closed for client {client_id}")
        
        return EventSourceResponse(event_generator())
    
    async def broadcast_notification(self, event: str, data: Dict[str, Any]):
        """Broadcast notification to all SSE clients"""
        if not self.sse_connections:
            return
        
        message = {
            "event": event,
            "data": data
        }
        
        # Send to all connected clients
        disconnected_clients = []
        for client_id, queue in self.sse_connections.items():
            try:
                await queue.put(message)
            except Exception as e:
                logger.error(f"Failed to send SSE message to client {client_id}: {e}")
                disconnected_clients.append(client_id)
        
        # Clean up disconnected clients
        for client_id in disconnected_clients:
            if client_id in self.sse_connections:
                del self.sse_connections[client_id]
    
    async def send_to_client(self, client_id: str, event: str, data: Dict[str, Any]):
        """Send notification to specific SSE client"""
        if client_id not in self.sse_connections:
            logger.warning(f"Client {client_id} not connected for SSE")
            return
        
        message = {
            "event": event,
            "data": data
        }
        
        try:
            await self.sse_connections[client_id].put(message)
        except Exception as e:
            logger.error(f"Failed to send SSE message to client {client_id}: {e}")
            # Remove disconnected client
            if client_id in self.sse_connections:
                del self.sse_connections[client_id]
    
    def get_connection_count(self) -> int:
        """Get number of active SSE connections"""
        return len(self.sse_connections)
    
    def get_connected_clients(self) -> list:
        """Get list of connected client IDs"""
        return list(self.sse_connections.keys())


# Global transport instance
mcp_transport = McpTransport()


# Integration with existing WebSocket manager for job notifications
class McpWebSocketBridge:
    """
    Bridge between existing WebSocket job notifications and MCP SSE transport.
    Allows MCP clients to receive job progress updates via Server-Sent Events.
    """
    
    def __init__(self, transport: McpTransport):
        self.transport = transport
    
    async def notify_job_progress(self, job_id: str, progress: int, current_step: str, 
                                  step_number: int, total_steps: int, status: str = "started"):
        """Send job progress notification to MCP clients"""
        await self.transport.broadcast_notification("job_progress", {
            "type": "job_progress",
            "job_id": job_id,
            "status": status,
            "progress": progress,
            "current_step": current_step,
            "step_number": step_number,
            "total_steps": total_steps,
            "timestamp": asyncio.get_event_loop().time()
        })
    
    async def notify_job_completion(self, job_id: str, download_url: str):
        """Send job completion notification to MCP clients"""
        await self.transport.broadcast_notification("job_complete", {
            "type": "job_complete",
            "job_id": job_id,
            "status": "finished",
            "progress": 100,
            "current_step": "Complete",
            "download_url": download_url,
            "timestamp": asyncio.get_event_loop().time()
        })
    
    async def notify_job_error(self, job_id: str, error_message: str):
        """Send job error notification to MCP clients"""
        await self.transport.broadcast_notification("job_error", {
            "type": "job_error",
            "job_id": job_id,
            "status": "failed",
            "progress": 0,
            "current_step": "Job failed",
            "error": error_message,
            "timestamp": asyncio.get_event_loop().time()
        })
    
    async def notify_capability_change(self, capability: str, available: bool):
        """Send capability change notification to MCP clients"""
        await self.transport.broadcast_notification("capability_changed", {
            "type": "capability_changed",
            "capability": capability,
            "available": available,
            "timestamp": asyncio.get_event_loop().time()
        })


# Global WebSocket bridge instance
mcp_websocket_bridge = McpWebSocketBridge(mcp_transport)