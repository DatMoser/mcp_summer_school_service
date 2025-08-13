# app/main.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.websockets import WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from app.auth_middleware import APIKeyMiddleware
from app.mcp_models import MCPRequest, MCPResponse, WritingStyleRequest, WritingStyleResponse
from app.mcp_transport import mcp_transport
from app.jobs import gen_video, gen_audio, fetch_operation_status, q, analyze_writing_style
from app.credential_utils import get_credentials_or_default, validate_credentials, validate_video_parameters
from google.cloud.storage import Blob
from google.cloud import storage
from app.websocket_manager import manager
import uuid
import os
import time
import asyncio
import json
import sys
from dotenv import load_dotenv, find_dotenv

# Docker-only validation - ensure application can only run in Docker
def validate_docker_environment():
    """Ensure the application is running in a Docker container"""
    docker_indicators = [
        os.path.exists('/.dockerenv'),  # Standard Docker indicator file
        os.path.exists('/proc/1/cgroup'),  # Process cgroup info
        os.getenv('DOCKER_ENV') == 'true'  # Our custom environment variable
    ]
    
    if not any(docker_indicators):
        print("ERROR: This application can only be started through Docker!")
        print("Please use 'docker-compose up' or deploy through Coolify")
        print("Direct Python execution is not supported.")
        sys.exit(1)
    
    print("✓ Docker environment validated - application starting")

# Validate Docker environment before any other imports
validate_docker_environment()

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

def make_blob_public_safe(blob: Blob) -> str:
    """
    Make a blob publicly accessible, handling both uniform and legacy bucket access.
    Returns the public URL.
    """
    try:
        # Try legacy ACL method first
        blob.make_public()
        return blob.public_url
    except Exception as e:
        if "uniform bucket-level access" in str(e).lower():
            # For uniform bucket-level access, we need to ensure the bucket allows public access
            # The blob is already publicly accessible if the bucket allows it
            # Return the public URL format
            return f"https://storage.googleapis.com/{blob.bucket.name}/{blob.name}"
        else:
            # Re-raise other exceptions
            raise e

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
            return make_blob_public_safe(blob)
        except Exception as e:
            print(f"Warning: Could not make blob public: {e}")
            return f"https://storage.googleapis.com/{BUCKET}/{blob_path}"
    elif url.startswith(f"https://storage.googleapis.com/{BUCKET}/"):
        # Already a public HTTPS URL, ensure it's accessible
        blob_path = url.replace(f"https://storage.googleapis.com/{BUCKET}/", "")
        blob = bucket.blob(blob_path)
        
        try:
            return make_blob_public_safe(blob)
        except Exception as e:
            print(f"Warning: Could not make blob public: {e}")
            return url
    else:
        # External URL, return as-is
        return url

app = FastAPI(title="MCP PdTx Video and Audio generator")

# Configure CORS origins from environment variable
allowed_origins = os.getenv("CORS_ORIGINS", "*").split(",")
allowed_origins = [origin.strip() for origin in allowed_origins]

# Add CORS middleware to allow client-side requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add API key middleware to protect all endpoints
app.add_middleware(APIKeyMiddleware)

# ================================
# MCP Protocol Endpoints
# ================================

@app.post("/mcp-rpc")
async def mcp_json_rpc_endpoint(request: Request):
    """
    MCP JSON-RPC 2.0 endpoint.
    Handles all MCP protocol communication including initialization, tools, resources, and prompts.
    """
    return await mcp_transport.handle_json_rpc_post(request)

@app.get("/mcp-sse/{client_id}")
async def mcp_sse_endpoint(client_id: str):
    """
    MCP Server-Sent Events endpoint for real-time notifications.
    Provides job progress updates and capability changes to MCP clients.
    """
    return await mcp_transport.handle_sse_connection(client_id)

@app.get("/mcp-info")
def mcp_info():
    """
    MCP server information and capabilities.
    Returns details about available MCP features and connection status.
    """
    return {
        "protocol": "Model Context Protocol (MCP)",
        "version": "2025-06-18", 
        "transport": ["HTTP POST", "Server-Sent Events"],
        "capabilities": {
            "tools": {
                "listChanged": True,
                "available": ["generate_video", "generate_audio", "analyze_writing_style", "check_job_status"]
            },
            "resources": {
                "subscribe": True,
                "listChanged": True,
                "available": ["job://{job_id}"]
            },
            "prompts": {
                "listChanged": True,
                "available": ["video_generation", "podcast_generation", "style_analysis"]
            }
        },
        "endpoints": {
            "json_rpc": "/mcp-rpc",
            "server_sent_events": "/mcp-sse/{client_id}",
            "info": "/mcp-info"
        },
        "sse_connections": mcp_transport.get_connection_count(),
        "connected_clients": len(mcp_transport.get_connected_clients())
    }

@app.get("/")
def root():
    """
    Root endpoint providing basic service information.
    """
    return {
        "service": "MCP Video/Audio Generator",
        "status": "running",
        "version": "1.0.0",
        "protocols": {
            "rest": "Traditional REST API",
            "mcp": "Model Context Protocol (JSON-RPC 2.0)"
        },
        "endpoints": {
            "health": "/health",
            "validate": "/validate",
            "create_job": "/mcp",
            "check_job": "/mcp/{job_id}",
            "analyze_style": "/mcp/analyze-style",
            "websocket": "/ws/{job_id}",
            "docs": "/docs",
            "mcp_info": "/mcp-info",
            "mcp_rpc": "/mcp-rpc",
            "mcp_sse": "/mcp-sse/{client_id}"
        }
    }

@app.get("/validate")
def validate_api_key(request: Request):
    """
    Validate API key endpoint.
    Returns a simple response when API key is detected.
    """
    import os
    
    api_key = os.getenv("API_KEY")
    provided_api_key = request.headers.get("X-API-Key")
    
    if not api_key or not provided_api_key or provided_api_key != api_key:
        return {"valid": False}
    
    return {"valid": True}

@app.get("/health")
def health_check():
    """
    Health check endpoint to verify system status.
    Returns system information including Redis, queue, and service health.
    """
    import time
    from datetime import datetime
    
    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "uptime": time.time(),  # Process uptime placeholder
        "service": "MCP Video/Audio Generator",
        "version": "1.0.0",
        "components": {}
    }
    
    # Check Redis connection
    try:
        from app.jobs import redis_conn
        redis_conn.ping()
        health_status["components"]["redis"] = {
            "status": "healthy",
            "message": "Redis connection successful"
        }
    except Exception as e:
        health_status["status"] = "degraded"
        health_status["components"]["redis"] = {
            "status": "unhealthy",
            "message": f"Redis connection failed: {str(e)}"
        }
    
    # Check RQ Queue
    try:
        from app.jobs import q
        queue_info = {
            "status": "healthy",
            "message": "Queue accessible",
            "jobs_queued": len(q),
            "jobs_failed": len(q.failed_job_registry)
        }
        health_status["components"]["queue"] = queue_info
    except Exception as e:
        health_status["status"] = "degraded"
        health_status["components"]["queue"] = {
            "status": "unhealthy",
            "message": f"Queue check failed: {str(e)}"
        }
    
    # Check Google Cloud Storage (basic check)
    try:
        if os.getenv("GCS_BUCKET"):
            health_status["components"]["storage"] = {
                "status": "configured",
                "message": f"GCS bucket configured: {os.getenv('GCS_BUCKET')}"
            }
        else:
            health_status["components"]["storage"] = {
                "status": "warning",
                "message": "GCS bucket not configured"
            }
    except Exception as e:
        health_status["components"]["storage"] = {
            "status": "warning",
            "message": f"Storage check failed: {str(e)}"
        }
    
    # Check WebSocket manager
    try:
        from app.websocket_manager import manager
        active_connections = sum(len(connections) for connections in manager.active_connections.values())
        health_status["components"]["websocket"] = {
            "status": "healthy",
            "message": "WebSocket manager operational",
            "active_connections": active_connections
        }
    except Exception as e:
        health_status["components"]["websocket"] = {
            "status": "warning",
            "message": f"WebSocket check failed: {str(e)}"
        }
    
    # Check MCP protocol
    try:
        from app.mcp_protocol import mcp_handler
        from app.mcp_transport import mcp_transport
        sse_connections = mcp_transport.get_connection_count()
        health_status["components"]["mcp"] = {
            "status": "healthy",
            "message": "MCP protocol handler operational",
            "protocol_version": "2025-06-18",
            "sse_connections": sse_connections,
            "initialized": mcp_handler.initialized
        }
    except Exception as e:
        health_status["components"]["mcp"] = {
            "status": "warning",
            "message": f"MCP check failed: {str(e)}"
        }
    
    # Set overall status code for HTTP response
    status_code = 200
    if health_status["status"] == "degraded":
        status_code = 503  # Service Unavailable
    elif health_status["status"] == "unhealthy":
        status_code = 503
    
    from fastapi import Response
    return Response(
        content=json.dumps(health_status, indent=2),
        status_code=status_code,
        media_type="application/json"
    )

@app.post("/mcp", response_model=MCPResponse)
def create_task(req: MCPRequest):
    from fastapi import HTTPException
    
    job_id = str(uuid.uuid4())
    
    # Get credentials from request or use environment defaults
    creds_dict = get_credentials_or_default(req.credentials)
    
    # Validate credentials before starting job
    is_valid, error_message = validate_credentials(creds_dict)
    if not is_valid:
        raise HTTPException(status_code=400, detail=f"Invalid credentials: {error_message}")
    
    # Validate video parameters if in video mode
    if req.mode == "video":
        is_valid, error_message = validate_video_parameters(req.parameters)
        if not is_valid:
            raise HTTPException(status_code=400, detail=f"Invalid video parameters: {error_message}")
    
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
        
        job = q.enqueue_call(func=gen_video, args=(video_request, creds_dict), job_id=job_id)
    else:
        job = q.enqueue_call(func=gen_audio, args=(req.prompt, creds_dict, req.generate_thumbnail, req.thumbnail_prompt, req.provider), job_id=job_id)
    
    # Calculate total steps based on mode and options
    if req.mode == "audio":
        total_steps = 5 if req.generate_thumbnail else 4
    else:
        total_steps = 3
    
    return MCPResponse(
        job_id=job.get_id(), 
        status="queued",
        progress=0,
        current_step="Job queued, waiting to start",
        total_steps=total_steps,
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
    thumbnail_url = None
    if job.is_finished and result:
        if isinstance(result, dict):
            # Audio result format: {"audio_url": "...", "thumbnail_url": "..."}
            if result.get("audio_url"):
                url = resolve_gcs_url(result["audio_url"])
                thumbnail_url = resolve_gcs_url(result["thumbnail_url"]) if result.get("thumbnail_url") else None
            # Video format: {"status": "submitted", "operation_name": "...", "message": "..."}
            elif result.get("status") == "submitted" and result.get("operation_name"):
                operation_name = result.get("operation_name")
                # Job submitted successfully, check if operation is complete
                try:
                    # TODO: We need to get credentials from job metadata for this call
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
                    # TODO: We need to get credentials from job metadata for this call
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
        thumbnail_url=thumbnail_url,
        progress=progress,
        current_step=current_step,
        total_steps=total_steps,
        step_number=step_number,
        operation_name=operation_name
    )

@app.post("/mcp/analyze-style", response_model=WritingStyleResponse)
def analyze_writing_style_endpoint(req: WritingStyleRequest):
    """
    Analyze dialogue style for podcast generation based on style instructions.
    Takes instructions like "Talk like Trump" and returns podcast generation settings.
    """
    from fastapi import HTTPException
    
    # Get credentials from request or use environment defaults
    creds_dict = get_credentials_or_default(req.credentials)
    
    # Validate that we have the required API key for the chosen provider (OpenAI is internal)
    if req.provider == "gemini" and not creds_dict.get('gemini_api_key'):
        raise HTTPException(status_code=400, detail="Gemini API key is required when using Gemini provider for writing style analysis")
    elif req.provider not in ["openai", "gemini"]:
        raise HTTPException(status_code=400, detail="Provider must be 'openai' or 'gemini'")
    elif req.provider == "openai" and not creds_dict.get('openai_api_key'):
        raise HTTPException(status_code=500, detail="Internal OpenAI API key not configured on server")
    
    try:
        # Call the analysis function with provider selection
        result = analyze_writing_style(
            req.prompt, 
            provider=req.provider,
            gemini_api_key=creds_dict.get('gemini_api_key')
        )
        
        # Return the structured response
        return WritingStyleResponse(**result)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error analyzing writing style: {str(e)}")

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
        # TODO: Add support for user-provided credentials in this endpoint
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
            # Use timeout to avoid blocking indefinitely
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                await websocket.send_text(json.dumps({"type": "ping", "job_id": job_id}))
    except WebSocketDisconnect:
        print(f"WebSocket disconnected for job {job_id}")
    except Exception as e:
        print(f"WebSocket error for job {job_id}: {e}")
    finally:
        manager.disconnect(websocket, job_id)

# Global variable to store the Redis listener task
redis_listener_task = None

# Background task to listen for Redis messages and broadcast via WebSocket
async def redis_listener():
    """Background task that listens for Redis messages and broadcasts to WebSocket clients"""
    import redis.asyncio as aioredis
    
    redis = None
    pubsub = None
    
    try:
        redis = aioredis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
        pubsub = redis.pubsub()
        
        # Subscribe to all websocket channels
        await pubsub.psubscribe("websocket:*")
        
        # Use proper async iteration with exception handling
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
    
    except asyncio.CancelledError:
        print("Redis listener task cancelled")
        raise
    except Exception as e:
        print(f"Redis listener error: {e}")
    finally:
        # Clean up resources
        try:
            if pubsub:
                await pubsub.aclose()
            if redis:
                await redis.aclose()
        except Exception as e:
            print(f"Error cleaning up Redis connection: {e}")

# Start the Redis listener when the app starts
@app.on_event("startup")
async def startup_event():
    global redis_listener_task
    redis_listener_task = asyncio.create_task(redis_listener())
    print("Redis listener task started")

# Clean up when the app shuts down
@app.on_event("shutdown")
async def shutdown_event():
    global redis_listener_task
    if redis_listener_task:
        print("Cancelling Redis listener task")
        redis_listener_task.cancel()
        try:
            await redis_listener_task
        except asyncio.CancelledError:
            print("Redis listener task cancelled successfully")
        except Exception as e:
            print(f"Error during Redis listener shutdown: {e}")