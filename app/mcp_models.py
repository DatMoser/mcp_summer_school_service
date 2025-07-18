# app/mcp_models.py
from pydantic import BaseModel, Field
from typing import Dict, Optional, Literal, Union

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

class MCPRequest(BaseModel):
    mode: str = Field(pattern="^(video|audio)$")
    prompt: str
    # Optional advanced video generation parameters
    image: Optional[ImageInput] = None
    lastFrame: Optional[ImageInput] = None
    video: Optional[VideoInput] = None
    parameters: Optional[VideoGenerationParameters] = None

class MCPResponse(BaseModel):
    job_id: str
    status: str
    download_url: Optional[str] = None
    progress: Optional[int] = None  # Progress percentage (0-100)
    current_step: Optional[str] = None  # Current processing step
    total_steps: Optional[int] = None  # Total number of steps
    step_number: Optional[int] = None  # Current step number
    estimated_completion: Optional[str] = None  # Estimated completion time
    operation_name: Optional[str] = None  # Google Cloud operation name for manual tracking