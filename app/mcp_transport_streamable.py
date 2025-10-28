# app/mcp_transport_streamable.py
"""
MCP Streamable HTTP Transport (Protocol version 2025-03-26+)

Implements single-endpoint MCP transport that can:
- Return JSON responses for quick operations
- Upgrade to SSE streaming for long-running operations
- Handle protocol version negotiation
"""

import json
import asyncio
import uuid
from typing import Dict, Any, Optional, AsyncGenerator
from fastapi import Request, HTTPException
from sse_starlette.sse import EventSourceResponse
from app.mcp_protocol import mcp_handler, JsonRpcRequest
from app.mcp_endpoints import mcp_endpoints
import logging

logger = logging.getLogger(__name__)


class StreamableHttpTransport:
    """
    Streamable HTTP Transport for MCP (2025-03-26+)

    Single endpoint that intelligently decides between:
    - JSON response for quick operations
    - SSE streaming for long-running operations
    """

    # Tools that require streaming (long-running operations)
    STREAMING_TOOLS = {
        "generate_video",  # 2-10 minutes
        "generate_audio",  # 10-60 seconds
    }

    # Quick-response tools
    QUICK_TOOLS = {
        "analyze_writing_style",  # < 5 seconds
        "check_job_status",  # Instant
    }

    def __init__(self):
        self.active_streams: Dict[str, asyncio.Queue] = {}
        self.job_streams: Dict[str, str] = {}  # job_id -> client_id mapping

    async def handle_request(self, request: Request) -> Any:
        """
        Main handler for streamable HTTP transport.
        Decides between JSON response and SSE streaming based on:
        - Accept header preference
        - Operation type (quick vs long-running)
        """
        try:
            # Get protocol version from header
            protocol_version = request.headers.get("MCP-Protocol-Version", "2025-03-26")
            logger.debug(f"Protocol version: {protocol_version}")

            # Validate protocol version
            if protocol_version not in ["2025-03-26", "2025-06-18"]:
                return {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {
                        "code": -32000,
                        "message": f"Unsupported protocol version: {protocol_version}",
                        "data": {
                            "supported": ["2025-03-26", "2025-06-18"],
                            "requested": protocol_version
                        }
                    }
                }

            # Parse request body
            body = await request.body()
            if not body:
                raise HTTPException(status_code=400, detail="Empty request body")

            message = body.decode('utf-8')
            data = json.loads(message)
            json_rpc_request = JsonRpcRequest(**data)

            logger.debug(f"Received {json_rpc_request.method} request (ID: {json_rpc_request.id})")

            # Check Accept header
            accept_header = request.headers.get("Accept", "application/json")
            client_wants_streaming = "text/event-stream" in accept_header

            # Determine if this operation should stream
            should_stream = self._should_stream_operation(
                json_rpc_request,
                client_wants_streaming
            )

            if should_stream:
                logger.info(f"Streaming response for {json_rpc_request.method}")
                return await self._handle_streaming_response(json_rpc_request, protocol_version)
            else:
                logger.info(f"JSON response for {json_rpc_request.method}")
                return await self._handle_json_response(json_rpc_request, protocol_version)

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON: {e}")
            raise HTTPException(status_code=400, detail="Invalid JSON")
        except Exception as e:
            logger.error(f"Error processing request: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    def _should_stream_operation(self, request: JsonRpcRequest, client_wants_streaming: bool) -> bool:
        """
        Determine if an operation should use SSE streaming.

        Streaming is used when:
        1. Client accepts text/event-stream
        2. AND operation is long-running (in STREAMING_TOOLS)
        """
        # Only tools/call can be streamed
        if request.method != "tools/call":
            return False

        # Client must accept streaming
        if not client_wants_streaming:
            return False

        # Check if tool is long-running
        params = request.params or {}
        tool_name = params.get("name", "")

        return tool_name in self.STREAMING_TOOLS

    async def _handle_json_response(self, request: JsonRpcRequest, protocol_version: str) -> Dict[str, Any]:
        """
        Handle request with standard JSON response.
        Used for quick operations or when client doesn't want streaming.
        """
        try:
            # Process through protocol handler first
            response = mcp_handler.route_request(request)
            if response:
                return json.loads(response.json())

            # Route to MCP endpoints
            response = await self._route_to_endpoint(request)
            return json.loads(response.json())

        except Exception as e:
            logger.error(f"Error handling JSON response: {e}")
            error_response = mcp_handler.create_error_response(
                request.id, -32603, f"Internal error: {str(e)}"
            )
            return json.loads(error_response.json())

    async def _handle_streaming_response(self, request: JsonRpcRequest, protocol_version: str) -> EventSourceResponse:
        """
        Handle request with SSE streaming response.
        Used for long-running operations when client wants streaming.
        """
        client_id = str(uuid.uuid4())

        async def event_generator() -> AsyncGenerator[Dict[str, Any], None]:
            queue = asyncio.Queue()
            self.active_streams[client_id] = queue

            try:
                # Send initial response with job initiation
                logger.info(f"Starting streaming response for client {client_id}")

                # Process the request to start the job
                response = await self._route_to_endpoint(request)
                initial_response = json.loads(response.json())

                # Send initial JSON-RPC response
                yield {
                    "event": "message",
                    "data": json.dumps(initial_response)
                }

                # Extract job_id if present
                job_id = self._extract_job_id(initial_response)
                if job_id:
                    self.job_streams[job_id] = client_id
                    logger.info(f"Tracking job {job_id} for client {client_id}")

                # Stream updates until completion
                while True:
                    try:
                        # Wait for progress updates with timeout for keep-alive
                        message = await asyncio.wait_for(queue.get(), timeout=30.0)

                        # Check if this is a completion message
                        is_complete = message.get("data", {}).get("type") in ["job_complete", "job_error"]

                        yield {
                            "event": message.get("event", "message"),
                            "data": json.dumps(message.get("data", {}))
                        }

                        # End stream on completion
                        if is_complete:
                            logger.info(f"Job completed, ending stream for client {client_id}")
                            break

                    except asyncio.TimeoutError:
                        # Send keep-alive ping
                        yield {
                            "event": "ping",
                            "data": json.dumps({
                                "type": "ping",
                                "timestamp": asyncio.get_event_loop().time()
                            })
                        }

            except asyncio.CancelledError:
                logger.info(f"Stream cancelled for client {client_id}")
            except Exception as e:
                logger.error(f"Error in streaming response: {e}")
                yield {
                    "event": "error",
                    "data": json.dumps({
                        "type": "error",
                        "error": str(e)
                    })
                }
            finally:
                # Cleanup
                if client_id in self.active_streams:
                    del self.active_streams[client_id]

                # Remove job mapping
                if job_id and job_id in self.job_streams:
                    del self.job_streams[job_id]

                logger.info(f"Stream closed for client {client_id}")

        return EventSourceResponse(event_generator())

    def _extract_job_id(self, response: Dict[str, Any]) -> Optional[str]:
        """Extract job_id from tool call response"""
        try:
            if "result" not in response:
                return None

            result = response["result"]

            # Check in content array (MCP tool response format)
            if "content" in result and isinstance(result["content"], list):
                for item in result["content"]:
                    if item.get("type") == "text":
                        text = item.get("text", "")
                        # Parse job_id from text (format: "Job ID: xyz123")
                        if "Job ID:" in text:
                            parts = text.split("Job ID:")
                            if len(parts) > 1:
                                job_id = parts[1].strip().split()[0]
                                return job_id

            # Direct job_id in result
            if "job_id" in result:
                return result["job_id"]

            return None

        except Exception as e:
            logger.error(f"Error extracting job_id: {e}")
            return None

    async def _route_to_endpoint(self, request: JsonRpcRequest):
        """Route request to appropriate MCP endpoint"""
        if request.method == "tools/list":
            return mcp_endpoints.handle_tools_list(request)
        elif request.method == "tools/call":
            return mcp_endpoints.handle_tools_call(request)
        elif request.method == "resources/list":
            return mcp_endpoints.handle_resources_list(request)
        elif request.method == "resources/read":
            return mcp_endpoints.handle_resources_read(request)
        elif request.method == "prompts/list":
            return mcp_endpoints.handle_prompts_list(request)
        elif request.method == "prompts/get":
            return mcp_endpoints.handle_prompts_get(request)
        else:
            return mcp_handler.create_error_response(
                request.id, -32601, f"Method not found: {request.method}"
            )

    async def notify_job_progress(self, job_id: str, progress: int, status: str,
                                  current_step: str, step_number: int, total_steps: int):
        """
        Send job progress notification to streaming client.
        Called by job workers during processing.
        """
        if job_id not in self.job_streams:
            logger.debug(f"No active stream for job {job_id}")
            return

        client_id = self.job_streams[job_id]
        if client_id not in self.active_streams:
            logger.warning(f"Client {client_id} stream not found for job {job_id}")
            return

        message = {
            "event": "job_progress",
            "data": {
                "type": "job_progress",
                "job_id": job_id,
                "status": status,
                "progress": progress,
                "current_step": current_step,
                "step_number": step_number,
                "total_steps": total_steps,
                "timestamp": asyncio.get_event_loop().time()
            }
        }

        try:
            await self.active_streams[client_id].put(message)
            logger.debug(f"Sent progress update for job {job_id}: {progress}%")
        except Exception as e:
            logger.error(f"Failed to send progress for job {job_id}: {e}")

    async def notify_job_complete(self, job_id: str, result: Dict[str, Any]):
        """
        Send job completion notification to streaming client.
        Called by job workers on successful completion.
        """
        if job_id not in self.job_streams:
            logger.debug(f"No active stream for job {job_id}")
            return

        client_id = self.job_streams[job_id]
        if client_id not in self.active_streams:
            logger.warning(f"Client {client_id} stream not found for job {job_id}")
            return

        message = {
            "event": "job_complete",
            "data": {
                "type": "job_complete",
                "job_id": job_id,
                "status": "completed",
                "progress": 100,
                "result": result,
                "timestamp": asyncio.get_event_loop().time()
            }
        }

        try:
            await self.active_streams[client_id].put(message)
            logger.info(f"Sent completion notification for job {job_id}")
        except Exception as e:
            logger.error(f"Failed to send completion for job {job_id}: {e}")

    async def notify_job_error(self, job_id: str, error: str):
        """
        Send job error notification to streaming client.
        Called by job workers on failure.
        """
        if job_id not in self.job_streams:
            logger.debug(f"No active stream for job {job_id}")
            return

        client_id = self.job_streams[job_id]
        if client_id not in self.active_streams:
            logger.warning(f"Client {client_id} stream not found for job {job_id}")
            return

        message = {
            "event": "job_error",
            "data": {
                "type": "job_error",
                "job_id": job_id,
                "status": "failed",
                "error": error,
                "timestamp": asyncio.get_event_loop().time()
            }
        }

        try:
            await self.active_streams[client_id].put(message)
            logger.info(f"Sent error notification for job {job_id}")
        except Exception as e:
            logger.error(f"Failed to send error for job {job_id}: {e}")

    def get_active_stream_count(self) -> int:
        """Get number of active streaming connections"""
        return len(self.active_streams)

    def get_tracked_jobs(self) -> list:
        """Get list of job IDs being tracked for streaming"""
        return list(self.job_streams.keys())


# Global streamable transport instance
streamable_transport = StreamableHttpTransport()
