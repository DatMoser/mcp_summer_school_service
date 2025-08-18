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
            
            # Define resolve_gcs_url locally to avoid circular import
            def resolve_gcs_url(url: str) -> str:
                """Convert GCS URI or ensure HTTPS URL is publicly accessible."""
                if not url:
                    return url
                
                BUCKET = os.getenv("GCS_BUCKET")
                if url.startswith("gs://"):
                    # Convert gs://bucket/path to public HTTPS URL
                    blob_path = url.replace(f"gs://{BUCKET}/", "")
                    return f"https://storage.googleapis.com/{BUCKET}/{blob_path}"
                elif url.startswith(f"https://storage.googleapis.com/{BUCKET}/"):
                    # Already a public HTTPS URL
                    return url
                else:
                    # External URL, return as-is
                    return url
            
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
            custom_status = job.meta.get('status', None)
            operation_name = job.meta.get('operation_name', None)
            
            # Determine actual job status
            job_status = job.get_status()
            
            # If we have a custom status and job is finished with a submission result, override status
            if custom_status == 'running' and job_status == 'finished':
                job_status = 'started'  # Show as started/running instead of finished
            
            # Set status-specific defaults
            if job_status == "queued":
                current_step = "Job queued, waiting to start"
                progress = 0
                step_number = 0
            elif job_status == "started" and progress == 0:
                current_step = "Job started, initializing..."
                progress = 5
                step_number = 1
            elif job_status == "failed":
                current_step = "Job failed"
                progress = 0
            
            result = job.result if job.is_finished else None
            
            # Handle different result formats (same logic as main.py check() function)
            url = None
            display_audio_url = None
            download_audio_url = None
            thumbnail_url = None
            audio_duration_seconds = None
            
            if job.is_finished and result:
                if isinstance(result, dict):
                    # Audio result format: {"audio_url": "...", "display_audio_url": "...", "download_audio_url": "...", "thumbnail_url": "..."}
                    if result.get("audio_url"):
                        url = resolve_gcs_url(result["audio_url"])  # Backward compatibility
                        display_audio_url = resolve_gcs_url(result["display_audio_url"]) if result.get("display_audio_url") else url
                        download_audio_url = resolve_gcs_url(result["download_audio_url"]) if result.get("download_audio_url") else url
                        thumbnail_url = resolve_gcs_url(result["thumbnail_url"]) if result.get("thumbnail_url") else None
                        audio_duration_seconds = result.get("audio_duration_seconds")
                    # Video format: {"status": "submitted", "operation_name": "...", "message": "..."}
                    elif result.get("status") == "submitted" and result.get("operation_name"):
                        operation_name = result.get("operation_name")
                elif isinstance(result, str):
                    if result.startswith('http'):
                        # Direct video URL
                        url = resolve_gcs_url(result)
                    elif result.startswith('projects/'):
                        # Operation name (old format)
                        operation_name = result
                    else:
                        # Other string result
                        url = resolve_gcs_url(result)
            
            message = {
                "job_id": job_id,
                "status": job_status,
                "download_url": url,
                "display_audio_url": display_audio_url,
                "download_audio_url": download_audio_url,
                "thumbnail_url": thumbnail_url,
                "audio_duration_seconds": audio_duration_seconds,
                "progress": progress,
                "current_step": current_step,
                "total_steps": total_steps,
                "step_number": step_number,
                "operation_name": operation_name,
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
        """Notify about job completion with full response structure"""
        import sys
        print(f"DEBUG WEBSOCKET START: notify_completion called for job {job_id}", file=sys.stderr)
        
        # Get the complete job status like the API endpoint does
        try:
            from app.jobs import q
            
            # Define resolve_gcs_url locally to avoid circular import
            def resolve_gcs_url(url: str) -> str:
                """Convert GCS URI or ensure HTTPS URL is publicly accessible."""
                if not url:
                    return url
                
                BUCKET = os.getenv("GCS_BUCKET")
                if url.startswith("gs://"):
                    # Convert gs://bucket/path to public HTTPS URL
                    blob_path = url.replace(f"gs://{BUCKET}/", "")
                    return f"https://storage.googleapis.com/{BUCKET}/{blob_path}"
                elif url.startswith(f"https://storage.googleapis.com/{BUCKET}/"):
                    # Already a public HTTPS URL
                    return url
                else:
                    # External URL, return as-is
                    return url
            
            job = q.fetch_job(job_id)
            if job is None:
                return
                
            # Get progress info from job metadata
            progress = job.meta.get('progress', 100)
            current_step = job.meta.get('current_step', 'Complete')
            total_steps = job.meta.get('total_steps', 1)
            step_number = job.meta.get('step_number', total_steps)
            custom_status = job.meta.get('status', None)
            operation_name = job.meta.get('operation_name', None)
            
            # Determine actual job status
            job_status = job.get_status()
            
            # For completion notifications, we always want "finished" status
            # Override the custom status logic for completion
            if job.is_finished:
                job_status = 'finished'
            
            result = job.result if job.is_finished else None
            
            # Handle different result formats (same logic as main.py check() function)
            url = None
            display_audio_url = None
            download_audio_url = None
            thumbnail_url = None
            audio_duration_seconds = None
            
            if job.is_finished and result:
                if isinstance(result, dict):
                    # Audio result format: {"audio_url": "...", "display_audio_url": "...", "download_audio_url": "...", "thumbnail_url": "..."}
                    if result.get("audio_url"):
                        url = resolve_gcs_url(result["audio_url"])  # Backward compatibility
                        display_audio_url = resolve_gcs_url(result["display_audio_url"]) if result.get("display_audio_url") else url
                        download_audio_url = resolve_gcs_url(result["download_audio_url"]) if result.get("download_audio_url") else url
                        thumbnail_url = resolve_gcs_url(result["thumbnail_url"]) if result.get("thumbnail_url") else None
                        audio_duration_seconds = result.get("audio_duration_seconds")
                    # Video format: {"status": "submitted", "operation_name": "...", "message": "..."}
                    elif result.get("status") == "submitted" and result.get("operation_name"):
                        operation_name = result.get("operation_name")
                        # For video operations that are still running, use the provided download_url
                        url = download_url
                elif isinstance(result, str):
                    # String result (legacy or direct URL)
                    url = resolve_gcs_url(result)
            
            # If we still don't have a URL, use the provided download_url
            if not url:
                url = download_url
            
            message = {
                "job_id": job_id,
                "status": job_status,
                "download_url": url,
                "display_audio_url": display_audio_url,
                "download_audio_url": download_audio_url,
                "thumbnail_url": thumbnail_url,
                "audio_duration_seconds": audio_duration_seconds,
                "progress": progress,
                "current_step": current_step,
                "total_steps": total_steps,
                "step_number": step_number,
                "operation_name": operation_name
            }
            
        except Exception as e:
            # Fallback to simple message if something goes wrong
            print(f"Error creating complete completion message for job {job_id}: {e}")
            import traceback
            traceback.print_exc()
            message = {
                "job_id": job_id,
                "status": "finished",
                "progress": 100,
                "current_step": "Complete",
                "download_url": download_url
            }
        
        # Debug logging
        import sys
        print(f"DEBUG WEBSOCKET: Publishing completion message for job {job_id}", file=sys.stderr)
        print(f"DEBUG WEBSOCKET: Message: {json.dumps(message, indent=2)}", file=sys.stderr)
        
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