# app/websocket_manager.py
import json
import asyncio
from typing import Dict, Set
from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect
import redis
import os

class WebSocketManager:
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self.redis_client = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
        
    async def connect(self, websocket: WebSocket, job_id: str):
        await websocket.accept()
        if job_id not in self.active_connections:
            self.active_connections[job_id] = set()
        self.active_connections[job_id].add(websocket)
        
        # Send current job status immediately upon connection
        await self.send_current_status(websocket, job_id)
        
    def disconnect(self, websocket: WebSocket, job_id: str):
        if job_id in self.active_connections:
            self.active_connections[job_id].discard(websocket)
            if not self.active_connections[job_id]:
                del self.active_connections[job_id]
    
    async def send_current_status(self, websocket: WebSocket, job_id: str):
        """Send current job status to a newly connected client"""
        try:
            from app.jobs import q
            job = q.fetch_job(job_id)
            
            if job is None:
                await websocket.send_text(json.dumps({
                    "job_id": job_id,
                    "status": "not_found",
                    "error": "Job not found"
                }))
                return
            
            # Get progress info from job metadata
            progress = job.meta.get('progress', 0)
            current_step = job.meta.get('current_step', 'Processing...')
            total_steps = job.meta.get('total_steps', 1)
            step_number = job.meta.get('step_number', 0)
            
            # Set status-specific defaults
            if job.get_status() == "queued":
                current_step = "Job queued, waiting to start"
                progress = 0
                step_number = 0
            elif job.get_status() == "started" and progress == 0:
                current_step = "Job started, initializing..."
                progress = 5
                step_number = 1
            elif job.get_status() == "failed":
                current_step = "Job failed"
                progress = 0
            
            url = job.result if job.is_finished else None
            
            message = {
                "job_id": job_id,
                "status": job.get_status(),
                "download_url": url,
                "progress": progress,
                "current_step": current_step,
                "total_steps": total_steps,
                "step_number": step_number,
                "timestamp": asyncio.get_event_loop().time()
            }
            
            await websocket.send_text(json.dumps(message))
            
        except Exception as e:
            await websocket.send_text(json.dumps({
                "job_id": job_id,
                "status": "error",
                "error": str(e)
            }))
    
    async def broadcast_to_job(self, job_id: str, message: dict):
        """Broadcast a message to all clients subscribed to a specific job"""
        if job_id not in self.active_connections:
            return
        
        message["timestamp"] = asyncio.get_event_loop().time()
        message_text = json.dumps(message)
        
        # Create a copy of the set to avoid modification during iteration
        connections = self.active_connections[job_id].copy()
        broken_connections = []
        
        for websocket in connections:
            try:
                await websocket.send_text(message_text)
            except Exception as e:
                # Collect broken connections for cleanup
                broken_connections.append(websocket)
                print(f"WebSocket send failed for job {job_id}: {e}")
        
        # Clean up broken connections outside the iteration
        for websocket in broken_connections:
            self.disconnect(websocket, job_id)
    
    def notify_progress(self, job_id: str, progress: int, current_step: str, 
                       step_number: int, total_steps: int, status: str = "started"):
        """
        Synchronous method to be called from job functions.
        Publishes progress to Redis for async processing.
        """
        message = {
            "job_id": job_id,
            "status": status,
            "progress": progress,
            "current_step": current_step,
            "step_number": step_number,
            "total_steps": total_steps
        }
        
        # Publish to Redis channel for async processing
        self.redis_client.publish(f"websocket:{job_id}", json.dumps(message))
        
        # Also notify MCP clients via SSE
        try:
            import asyncio
            from app.mcp_transport import mcp_websocket_bridge
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(mcp_websocket_bridge.notify_job_progress(
                    job_id, progress, current_step, step_number, total_steps, status
                ))
        except Exception:
            pass  # Don't fail if MCP notification fails
    
    def notify_completion(self, job_id: str, download_url: str):
        """Notify about job completion"""
        message = {
            "job_id": job_id,
            "status": "finished",
            "progress": 100,
            "current_step": "Complete",
            "download_url": download_url
        }
        
        self.redis_client.publish(f"websocket:{job_id}", json.dumps(message))
        
        # Also notify MCP clients via SSE
        try:
            import asyncio
            from app.mcp_transport import mcp_websocket_bridge
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(mcp_websocket_bridge.notify_job_completion(
                    job_id, download_url
                ))
        except Exception:
            pass  # Don't fail if MCP notification fails
    
    def notify_error(self, job_id: str, error_message: str):
        """Notify about job error"""
        message = {
            "job_id": job_id,
            "status": "failed",
            "progress": 0,
            "current_step": "Job failed",
            "error": error_message
        }
        
        self.redis_client.publish(f"websocket:{job_id}", json.dumps(message))
        
        # Also notify MCP clients via SSE
        try:
            import asyncio
            from app.mcp_transport import mcp_websocket_bridge
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(mcp_websocket_bridge.notify_job_error(
                    job_id, error_message
                ))
        except Exception:
            pass  # Don't fail if MCP notification fails

# Global instance
manager = WebSocketManager()