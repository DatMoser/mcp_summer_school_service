# app/main.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.websockets import WebSocketDisconnect
from app.mcp_models import MCPRequest, MCPResponse
from app.jobs import gen_video, gen_audio, fetch_operation_status, q
from google.cloud import storage
from app.websocket_manager import manager
import uuid
import os
import time
import asyncio
import json
from dotenv import load_dotenv, find_dotenv

# Load and print recognized .env files
dotenv_path = find_dotenv()

# Configure Google Cloud Storage
BUCKET = os.getenv("GCS_BUCKET")
gcs_credentials_path = os.getenv("GOOGLE_CLOUD_CREDENTIALS_PATH")
if gcs_credentials_path:
    storage_client = storage.Client.from_service_account_json(gcs_credentials_path)
else:
    storage_client = storage.Client()
bucket = storage_client.bucket(BUCKET)

def resolve_gcs_url(url: str) -> str:
    """
    Convert GCS URI (gs://bucket/path) or ensure HTTPS URL is publicly accessible.
    Returns a public HTTPS URL for immediate download.
    """
    if not url:
        return url
    
    if url.startswith("gs://"):
        # Convert gs://bucket/path to public HTTPS URL
        blob_path = url.replace(f"gs://{BUCKET}/", "")
        blob = bucket.blob(blob_path)
        
        # Make sure blob is public
        try:
            blob.make_public()
        except Exception as e:
            print(f"Warning: Could not make blob public: {e}")
        
        return blob.public_url
    elif url.startswith(f"https://storage.googleapis.com/{BUCKET}/"):
        # Already a public HTTPS URL, ensure it's accessible
        blob_path = url.replace(f"https://storage.googleapis.com/{BUCKET}/", "")
        blob = bucket.blob(blob_path)
        
        try:
            blob.make_public()
        except Exception as e:
            print(f"Warning: Could not make blob public: {e}")
        
        return url
    else:
        # External URL, return as-is
        return url

app = FastAPI(title="MCP PdTx Video and Audio generator")

@app.post("/mcp", response_model=MCPResponse)
def create_task(req: MCPRequest):
    job_id = str(uuid.uuid4())
    if req.mode == "video":
        # Build video request object from MCPRequest
        video_request = {
            "prompt": req.prompt,
            "image": req.image.dict() if req.image else None,
            "lastFrame": req.lastFrame.dict() if req.lastFrame else None,
            "video": req.video.dict() if req.video else None,
            "parameters": req.parameters.dict() if req.parameters else {}
        }
        # Remove None values
        video_request = {k: v for k, v in video_request.items() if v is not None}
        
        job = q.enqueue_call(func=gen_video, args=(video_request,), job_id=job_id)
    else:
        job = q.enqueue_call(func=gen_audio, args=(req.prompt,), job_id=job_id)
    
    return MCPResponse(
        job_id=job.get_id(), 
        status="queued",
        progress=0,
        current_step="Job queued, waiting to start",
        total_steps=4 if req.mode == "audio" else 3,
        step_number=0
    )

@app.get("/mcp/{job_id}", response_model=MCPResponse)
def check(job_id: str):
    job = q.fetch_job(job_id)
    
    if job is None:
        return MCPResponse(
            job_id=job_id, 
            status="not_found",
            current_step="Job not found"
        )
    
    # Get progress info from job metadata
    progress = job.meta.get('progress', 0)
    current_step = job.meta.get('current_step', 'Processing...')
    total_steps = job.meta.get('total_steps', 1)
    step_number = job.meta.get('step_number', 0)
    custom_status = job.meta.get('status', None)
    
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
    operation_name = job.meta.get('operation_name', None)
    
    # Handle different result formats
    url = None
    if job.is_finished and result:
        if isinstance(result, dict):
            # New format: {"status": "submitted", "operation_name": "...", "message": "..."}
            if result.get("status") == "submitted" and result.get("operation_name"):
                operation_name = result.get("operation_name")
                # Job submitted successfully, check if operation is complete
                try:
                    operation_result = fetch_operation_status(operation_name)
                    if operation_result.get("done") and "response" in operation_result:
                        response_data = operation_result["response"]
                        videos = response_data.get("videos", [])
                        if videos and "gcsUri" in videos[0]:
                            gcs_uri = videos[0]["gcsUri"]
                            url = resolve_gcs_url(gcs_uri)
                        else:
                            predictions = response_data.get("predictions", [])
                            if predictions and "videoUrl" in predictions[0]:
                                url = resolve_gcs_url(predictions[0]["videoUrl"])
                except Exception as e:
                    print(f"Error querying operation status: {e}")
        elif isinstance(result, str):
            if result.startswith('http'):
                # Direct video URL
                url = resolve_gcs_url(result)
            elif result.startswith('projects/'):
                # Operation name (old format)
                operation_name = result
                try:
                    operation_result = fetch_operation_status(operation_name)
                    if operation_result.get("done") and "response" in operation_result:
                        response_data = operation_result["response"]
                        videos = response_data.get("videos", [])
                        if videos and "gcsUri" in videos[0]:
                            gcs_uri = videos[0]["gcsUri"]
                            url = resolve_gcs_url(gcs_uri)
                        else:
                            predictions = response_data.get("predictions", [])
                            if predictions and "videoUrl" in predictions[0]:
                                url = resolve_gcs_url(predictions[0]["videoUrl"])
                except Exception as e:
                    print(f"Error querying operation status: {e}")
            else:
                # Other string result
                url = resolve_gcs_url(result)
    
    return MCPResponse(
        job_id=job_id, 
        status=job_status, 
        download_url=url,
        progress=progress,
        current_step=current_step,
        total_steps=total_steps,
        step_number=step_number,
        operation_name=operation_name
    )

@app.get("/mcp/{job_id}/wait", response_model=MCPResponse)
def wait_for_completion(job_id: str):
    """
    Long-polling endpoint that waits for job completion.
    Returns immediately when job is finished or failed.
    """
    max_wait_time = 300  # 5 minutes max wait
    poll_interval = 2    # Check every 2 seconds
    start_time = time.time()
    
    while time.time() - start_time < max_wait_time:
        response = check(job_id)
        
        if response.status in ["finished", "failed", "not_found"]:
            return response
        
        time.sleep(poll_interval)
    
    # Timeout - return current status
    return check(job_id)

@app.get("/operation/{operation_name}")
def query_operation_status(operation_name: str):
    """
    Query the status of a Google Cloud video generation operation directly.
    This uses Google's fetchPredictOperation endpoint.
    """
    try:
        operation_result = fetch_operation_status(operation_name)
        
        # Parse the response to extract useful information
        status_info = {
            "operation_name": operation_name,
            "done": operation_result.get("done", False),
            "status": "completed" if operation_result.get("done") else "running"
        }
        
        # Check for errors
        if "error" in operation_result:
            status_info["status"] = "failed"
            status_info["error"] = operation_result["error"]
        
        # Extract video URL if available
        if operation_result.get("done") and "response" in operation_result:
            response_data = operation_result["response"]
            # Veo returns videos array with gcsUri when storageUri is specified
            videos = response_data.get("videos", [])
            if videos and "gcsUri" in videos[0]:
                gcs_uri = videos[0]["gcsUri"]
                # Resolve GCS URI to public HTTPS URL for immediate download
                public_url = resolve_gcs_url(gcs_uri)
                status_info["video_url"] = public_url
                status_info["gcs_uri"] = gcs_uri
                status_info["download_ready"] = True
            else:
                # Fallback to predictions format for compatibility
                predictions = response_data.get("predictions", [])
                if predictions and "videoUrl" in predictions[0]:
                    video_url = predictions[0]["videoUrl"]
                    # Resolve any GCS URLs here too
                    status_info["video_url"] = resolve_gcs_url(video_url)
                    status_info["download_ready"] = True
                else:
                    status_info["download_ready"] = False
        else:
            status_info["download_ready"] = False
        
        # Include full Google response for debugging
        status_info["google_response"] = operation_result
        
        return status_info
        
    except Exception as e:
        return {
            "operation_name": operation_name,
            "status": "error",
            "error": str(e)
        }

@app.websocket("/ws/{job_id}")
async def websocket_endpoint(websocket: WebSocket, job_id: str):
    """
    WebSocket endpoint for real-time job progress updates.
    Clients can connect to /ws/{job_id} to receive live updates.
    """
    await manager.connect(websocket, job_id)
    
    try:
        while True:
            # Keep the connection alive and listen for client messages
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, job_id)
    except Exception as e:
        manager.disconnect(websocket, job_id)

# Background task to listen for Redis messages and broadcast via WebSocket
async def redis_listener():
    """Background task that listens for Redis messages and broadcasts to WebSocket clients"""
    import redis.asyncio as aioredis
    
    redis = aioredis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    pubsub = redis.pubsub()
    
    # Subscribe to all websocket channels
    await pubsub.psubscribe("websocket:*")
    
    async for message in pubsub.listen():
        if message['type'] == 'pmessage':
            try:
                # Extract job_id from channel name
                channel = message['channel'].decode('utf-8')
                job_id = channel.split(':', 1)[1]
                
                # Parse the message
                data = json.loads(message['data'].decode('utf-8'))
                
                # Broadcast to all clients subscribed to this job
                await manager.broadcast_to_job(job_id, data)
                
            except Exception as e:
                print(f"Error processing Redis message: {e}")

# Start the Redis listener when the app starts
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(redis_listener())