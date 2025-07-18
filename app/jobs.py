# app/jobs.py
import uuid, os, tempfile, subprocess, json, time, requests
from google.cloud import storage
from google import generativeai as genai
from google.auth import default
from google.auth.transport.requests import Request
from google.cloud import aiplatform
from elevenlabs.client import ElevenLabs
from rq import Queue
import redis

# Configure Google Gemini API with separate API key
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Configure Google Cloud Storage with separate credentials
BUCKET = os.getenv("GCS_BUCKET")
# Use explicit credentials for Cloud Storage if provided
gcs_credentials_path = os.getenv("GOOGLE_CLOUD_CREDENTIALS_PATH")
if gcs_credentials_path:
    client = storage.Client.from_service_account_json(gcs_credentials_path)
else:
    # Fall back to default credentials
    client = storage.Client()
bucket = client.bucket(BUCKET)

# Redis connection and queue setup
redis_conn = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
q = Queue(connection=redis_conn)

def make_script(prompt: str) -> str:
    model = genai.GenerativeModel("gemini-2.5-flash")
    return model.generate_content(prompt).text  #  [oai_citation:3‡Google AI for Developers](https://ai.google.dev/gemini-api/docs/text-generation?utm_source=chatgpt.com)

def gen_video(video_request: dict) -> str:
    """
    Video generation using Google's full API structure.
    Supports image inputs, video inputs, and all parameters.
    """
    from rq import get_current_job
    from app.websocket_manager import manager
    
    job = get_current_job()
    job_id = job.get_id()
    total_steps = 3
    
    try:
        # Step 1: Initialize authentication
        job.meta['progress'] = 10
        job.meta['current_step'] = 'Initializing video generation'
        job.meta['step_number'] = 1
        job.meta['total_steps'] = total_steps
        job.save_meta()
        
        # Send WebSocket notification
        manager.notify_progress(job_id, 10, 'Initializing video generation', 1, total_steps)
        
        # Get credentials and access token
        vertex_credentials_path = os.getenv("GOOGLE_CLOUD_CREDENTIALS_PATH")
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "mcp-summer-school")
        
        if vertex_credentials_path:
            # Use service account credentials
            from google.oauth2 import service_account
            credentials = service_account.Credentials.from_service_account_file(
                vertex_credentials_path,
                scopes=['https://www.googleapis.com/auth/cloud-platform']
            )
        else:
            # Fall back to default credentials
            credentials, _ = default()
        
        credentials.refresh(Request())
        access_token = credentials.token
        
        # Vertex AI configuration
        location_id = os.getenv("VERTEX_AI_REGION", "us-central1")
        api_endpoint = f"{location_id}-aiplatform.googleapis.com"
        model_id = os.getenv("VEO_MODEL_ID", "veo-3.0-generate-preview")
        
        # Step 2: Submit video generation request
        job.meta['progress'] = 50
        job.meta['current_step'] = 'Submitting video generation request'
        job.meta['step_number'] = 2
        job.save_meta()
        
        # Send WebSocket notification
        manager.notify_progress(job_id, 50, 'Submitting video generation request', 2, total_steps)
        
        # Build instance from video_request
        instance = {
            "prompt": video_request["prompt"]
        }
        
        # Add optional image input
        if video_request.get("image"):
            instance["image"] = video_request["image"]
        
        # Add optional last frame input
        if video_request.get("lastFrame"):
            instance["lastFrame"] = video_request["lastFrame"]
        
        # Add optional video input
        if video_request.get("video"):
            instance["video"] = video_request["video"]
        
        # Get parameters with defaults
        parameters = video_request.get("parameters", {})
        request_parameters = {
            "aspectRatio": parameters.get("aspectRatio", "16:9"),
            "sampleCount": parameters.get("sampleCount", 1),
            "durationSeconds": parameters.get("durationSeconds", 8),
            "personGeneration": parameters.get("personGeneration", "allow_all"),
            "generateAudio": parameters.get("generateAudio", True),
            "enhancePrompt": parameters.get("enhancePrompt", True)  # Veo 3 requires this to be True
        }
        
        # Add optional parameters if provided
        if parameters.get("negativePrompt"):
            request_parameters["negativePrompt"] = parameters["negativePrompt"]
        if parameters.get("resolution"):
            request_parameters["resolution"] = parameters["resolution"]
        if parameters.get("seed"):
            request_parameters["seed"] = parameters["seed"]
        
        # Always set storageUri to automatically save to our GCS bucket
        # This prevents base64 responses and saves directly to our bucket
        storage_folder = f"gs://{BUCKET}/videos/{job_id}"
        request_parameters["storageUri"] = parameters.get("storageUri", storage_folder)
        
        # Prepare request payload matching Google's exact structure
        request_data = {
            "instances": [instance],
            "parameters": request_parameters
        }
        
        # Submit the long-running operation
        url = f"https://{api_endpoint}/v1/projects/{project_id}/locations/{location_id}/publishers/google/models/{model_id}:predictLongRunning"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}"
        }
        
        import sys
        print(f"DEBUG: Submitting request to: {url}", file=sys.stderr)
        print(f"DEBUG: Request headers: {headers}", file=sys.stderr)
        print(f"DEBUG: Request data: {json.dumps(request_data, indent=2)}", file=sys.stderr)
        
        response = requests.post(url, headers=headers, json=request_data)
        
        print(f"DEBUG: Response status: {response.status_code}", file=sys.stderr)
        print(f"DEBUG: Response content: {response.text}", file=sys.stderr)
        
        response.raise_for_status()
        
        operation = response.json()
        operation_name = operation.get("name")
        
        if not operation_name:
            raise ValueError(f"No operation name returned from API. Response: {operation}")
        
        print(f"DEBUG: Operation name: {operation_name}", file=sys.stderr)
        
        # Initialize video_url variable
        video_url = None
        
        # Immediate status check to catch early failures
        job.meta['progress'] = 55
        job.meta['current_step'] = 'Checking initial operation status'
        job.save_meta()
        manager.notify_progress(job_id, 55, 'Checking initial operation status', 3, total_steps)
        
        print(f"DEBUG: Performing immediate status check for early failure detection", file=sys.stderr)
        try:
            # Wait a brief moment for operation to be registered, then check immediately
            time.sleep(5)
            immediate_status = fetch_operation_status(operation_name)
            print(f"DEBUG: Immediate status check result: {immediate_status}", file=sys.stderr)
            
            # Check if operation failed immediately
            if immediate_status.get("done") and "error" in immediate_status:
                error = immediate_status["error"]
                error_msg = f"Video generation failed immediately - Code: {error.get('code', 'unknown')}, Message: {error.get('message', 'no message')}"
                print(f"DEBUG: {error_msg}", file=sys.stderr)
                raise ValueError(error_msg)
            
            # If operation completed immediately (unlikely but possible)
            if immediate_status.get("done") and "response" in immediate_status:
                print(f"DEBUG: Operation completed immediately!", file=sys.stderr)
                response_data = immediate_status["response"]
                videos = response_data.get("videos", [])
                if videos and "gcsUri" in videos[0]:
                    video_gcs_uri = videos[0]["gcsUri"]
                    blob_path = video_gcs_uri.replace(f"gs://{BUCKET}/", "")
                    blob = bucket.blob(blob_path)
                    blob.make_public()
                    
                    # Operation completed immediately, skip polling
                    print(f"DEBUG: Video ready immediately at: {blob.public_url}", file=sys.stderr)
                    video_url = blob.public_url
                else:
                    print(f"DEBUG: Operation done but no video found, will continue polling", file=sys.stderr)
            
        except Exception as e:
            print(f"DEBUG: Immediate status check failed (operation still initializing): {e}", file=sys.stderr)
        
        # If we got a video URL immediately, we're done
        if video_url:
            # Store operation metadata for immediate completion
            operation_info = {
                "operation_name": operation_name,
                "video_request": video_request,
                "timestamp": time.time(),
                "job_id": job_id,
                "project_id": project_id,
                "location_id": location_id,
                "video_url": video_url,
                "video_filename": video_url.split('/')[-1] if video_url.startswith("https://") else "immediate_completion.mp4",
                "original_video_url": video_url,
                "source_type": "immediate_completion"
            }
            
            metadata_blob = bucket.blob(f"metadata/{operation_info['video_filename'].replace('.mp4', '.json')}")
            metadata_blob.upload_from_string(json.dumps(operation_info, indent=2), content_type="application/json")
            
            # Mark as complete
            job.meta['progress'] = 100
            job.meta['current_step'] = 'Complete - Video ready!'
            job.save_meta()
            
            manager.notify_completion(job_id, video_url)
            return video_url
        
        # Operation is running - store operation info for user to track
        job.meta['progress'] = 60
        job.meta['current_step'] = 'Video generation in progress - check status manually'
        job.meta['operation_name'] = operation_name
        job.meta['status'] = 'running'  # Explicitly mark as running, not failed
        job.save_meta()
        
        # Send WebSocket notification about ongoing operation
        manager.notify_progress(job_id, 60, 'Video generation in progress - use /mcp/{job_id} or /operation/{operation_name} to check status', 3, total_steps)
        
        print(f"DEBUG: Video generation submitted successfully. Operation: {operation_name}", file=sys.stderr)
        print(f"DEBUG: Use status endpoints to check progress", file=sys.stderr)
        
        # Return a success indicator with operation name
        # This ensures RQ treats the job as successful
        return {
            "status": "submitted",
            "operation_name": operation_name,
            "message": "Video generation started successfully"
        }
    
    except Exception as e:
        manager.notify_error(job_id, str(e))
        raise e


def fetch_operation_status(operation_name: str) -> dict:
    """
    Query the status of a video generation operation using Google's fetchPredictOperation endpoint.
    Returns the operation status and result if available.
    """
    try:
        # Get credentials and access token
        vertex_credentials_path = os.getenv("GOOGLE_CLOUD_CREDENTIALS_PATH")
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "mcp-summer-school")
        
        if vertex_credentials_path:
            from google.oauth2 import service_account
            credentials = service_account.Credentials.from_service_account_file(
                vertex_credentials_path,
                scopes=['https://www.googleapis.com/auth/cloud-platform']
            )
        else:
            credentials, _ = default()
        
        credentials.refresh(Request())
        
        # Vertex AI configuration
        location_id = os.getenv("VERTEX_AI_REGION", "us-central1")
        api_endpoint = f"{location_id}-aiplatform.googleapis.com"
        model_id = os.getenv("VEO_MODEL_ID", "veo-3.0-generate-preview")
        
        # Prepare request payload for fetchPredictOperation
        request_data = {
            "operationName": operation_name
        }
        
        # Submit fetchPredictOperation request
        url = f"https://{api_endpoint}/v1/projects/{project_id}/locations/{location_id}/publishers/google/models/{model_id}:fetchPredictOperation"
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"Bearer {credentials.token}"
        }
        
        import sys
        print(f"DEBUG FETCH: Querying operation status at: {url}", file=sys.stderr)
        print(f"DEBUG FETCH: Request data: {json.dumps(request_data, indent=2)}", file=sys.stderr)
        
        response = requests.post(url, headers=headers, json=request_data)
        
        print(f"DEBUG FETCH: Response status: {response.status_code}", file=sys.stderr)
        print(f"DEBUG FETCH: Response content: {response.text}", file=sys.stderr)
        
        response.raise_for_status()
        
        return response.json()
        
    except Exception as e:
        print(f"DEBUG FETCH: Error fetching operation status: {e}", file=sys.stderr)
        raise e

def gen_audio(prompt: str) -> str:
    from rq import get_current_job
    from app.websocket_manager import manager
    import time
    
    job = get_current_job()
    job_id = job.get_id()
    total_steps = 4
    
    try:
        # Step 1: Generate script
        job.meta['progress'] = 10
        job.meta['current_step'] = 'Generating script with AI'
        job.meta['step_number'] = 1
        job.meta['total_steps'] = total_steps
        job.save_meta()
        
        # Send WebSocket notification
        manager.notify_progress(job_id, 10, 'Generating script with AI', 1, total_steps)
        
        script = make_script(prompt)
        
        # Step 2: Initialize ElevenLabs and get voice
        job.meta['progress'] = 30
        job.meta['current_step'] = 'Initializing text-to-speech engine'
        job.meta['step_number'] = 2
        job.save_meta()
        
        # Send WebSocket notification
        manager.notify_progress(job_id, 30, 'Initializing text-to-speech engine', 2, total_steps)
        
        el = ElevenLabs(api_key=os.getenv("XI_KEY"))
        
        # Get available voices and use the first one, or use a known voice ID
        try:
            voices = el.voices.get_all()
            voice_id = voices.voices[0].voice_id if voices.voices else "pNInz6obpgDQGcFmaJgB"  # Default Adam voice ID
        except:
            # Fallback to a known voice ID for Adam
            voice_id = "pNInz6obpgDQGcFmaJgB"
        
        # Step 3: Generate audio
        job.meta['progress'] = 60
        job.meta['current_step'] = 'Converting text to speech'
        job.meta['step_number'] = 3
        job.save_meta()
        
        # Send WebSocket notification
        manager.notify_progress(job_id, 60, 'Converting text to speech', 3, total_steps)
        
        audio_generator = el.generate(text=script, voice=voice_id)
        audio_bytes = b"".join(audio_generator)  # Convert generator to bytes
        
        # Step 4: Upload to storage
        job.meta['progress'] = 90
        job.meta['current_step'] = 'Uploading audio file to cloud storage'
        job.meta['step_number'] = 4
        job.save_meta()
        
        # Send WebSocket notification
        manager.notify_progress(job_id, 90, 'Uploading audio file to cloud storage', 4, total_steps)
        
        blob = bucket.blob(f"audio/{uuid.uuid4()}.mp3")
        blob.upload_from_string(audio_bytes)
        
        # Completion
        job.meta['progress'] = 100
        job.meta['current_step'] = 'Complete'
        job.save_meta()
        
        # Send completion notification
        manager.notify_completion(job_id, blob.public_url)
        
        return blob.public_url
    
    except Exception as e:
        # Send error notification
        manager.notify_error(job_id, str(e))
        raise e