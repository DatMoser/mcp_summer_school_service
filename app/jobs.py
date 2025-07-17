# app/jobs.py
import uuid, os, tempfile, subprocess, json
from google.cloud import aiplatform, storage
from google import generativeai as genai
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

def gen_video(prompt: str) -> str:
    # Configure Vertex AI client with separate credentials if provided
    vertex_credentials_path = os.getenv("GOOGLE_CLOUD_CREDENTIALS_PATH")
    if vertex_credentials_path:
        aiplatform.init(
            project=os.getenv("GOOGLE_CLOUD_PROJECT"),
            location=os.getenv("GOOGLE_CLOUD_REGION", "us-central1"),
            credentials=vertex_credentials_path
        )
    else:
        aiplatform.init(
            project=os.getenv("GOOGLE_CLOUD_PROJECT"),
            location=os.getenv("GOOGLE_CLOUD_REGION", "us-central1")
        )
    
    veo_client = aiplatform.gapic.PredictionServiceClient()
    # details trimmed – follow Veo sample  [oai_citation:4‡Google Cloud](https://cloud.google.com/vertex-ai/generative-ai/docs/video/overview?utm_source=chatgpt.com)
    video_bytes = veo_client.predict(...)
    blob = bucket.blob(f"videos/{uuid.uuid4()}.mp4")
    blob.upload_from_string(video_bytes)
    return blob.public_url

def gen_audio(prompt: str) -> str:
    script = make_script(prompt)
    el = ElevenLabs(api_key=os.getenv("XI_KEY"))
    audio = el.generate(text=script, voice="Adam")
    blob = bucket.blob(f"audio/{uuid.uuid4()}.mp3")
    blob.upload_from_string(audio)
    return blob.public_url