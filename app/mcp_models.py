# app/mcp_models.py
from pydantic import BaseModel, Field
from typing import Dict, Optional, Literal, Union, Any

class ImageInput(BaseModel):
    bytesBase64Encoded: Optional[str] = None
    gcsUri: Optional[str] = None
    mimeType: Optional[str] = None

class VideoInput(BaseModel):
    bytesBase64Encoded: Optional[str] = None
    gcsUri: Optional[str] = None
    mimeType: Optional[str] = None

class VideoGenerationParameters(BaseModel):
    aspectRatio: Optional[str] = "16:9"
    durationSeconds: Optional[int] = 8
    enhancePrompt: Optional[bool] = True  # Veo 3 requires this to be True
    generateAudio: Optional[bool] = True
    negativePrompt: Optional[str] = None
    personGeneration: Optional[str] = "allow_all"
    resolution: Optional[str] = None  # Veo 3 models only
    sampleCount: Optional[int] = 1
    seed: Optional[int] = None
    storageUri: Optional[str] = None
    model: Optional[str] = "veo-3.0-generate-preview"  # Video generation model

class UserCredentials(BaseModel):
    gemini_api_key: Optional[str] = None
    google_cloud_credentials: Optional[Dict[str, Any]] = None  # Service account JSON as dict
    google_cloud_project: Optional[str] = None
    vertex_ai_region: Optional[str] = None
    gcs_bucket: Optional[str] = None
    elevenlabs_api_key: Optional[str] = None

class MCPRequest(BaseModel):
    mode: str = Field(pattern="^(video|audio)$")
    prompt: str
    # Optional advanced video generation parameters
    image: Optional[ImageInput] = None
    lastFrame: Optional[ImageInput] = None
    video: Optional[VideoInput] = None
    parameters: Optional[VideoGenerationParameters] = None
    credentials: Optional[UserCredentials] = None
    # Audio/Podcast specific parameters
    generate_thumbnail: Optional[bool] = False  # Generate podcast thumbnail for audio mode
    thumbnail_prompt: Optional[str] = None  # Custom prompt for thumbnail generation (if not provided, uses main prompt)

class WritingStyleRequest(BaseModel):
    prompt: str  # Style instruction like "Talk like Trump" or "Speak like a professor"
    credentials: Optional[UserCredentials] = None

class WritingStyleResponse(BaseModel):
    tone: str
    pace: str
    vocabulary_level: str
    target_audience: str
    content_structure: str
    energy_level: Optional[str] = None
    formality: Optional[str] = None
    humor_style: Optional[str] = None
    empathy_level: Optional[str] = None
    confidence_level: Optional[str] = None
    storytelling: Optional[str] = None
    keyPhrases: list[str]
    additionalInstructions: str

class MCPResponse(BaseModel):
    job_id: str
    status: str
    download_url: Optional[str] = None
    thumbnail_url: Optional[str] = None  # Podcast thumbnail URL (audio mode only)
    progress: Optional[int] = None  # Progress percentage (0-100)
    current_step: Optional[str] = None  # Current processing step
    total_steps: Optional[int] = None  # Total number of steps
    step_number: Optional[int] = None  # Current step number
    estimated_completion: Optional[str] = None  # Estimated completion time
    operation_name: Optional[str] = None  # Google Cloud operation name for manual tracking