# app/mcp_models.py
from pydantic import BaseModel, Field
from typing import Dict

class MCPRequest(BaseModel):
    mode: str = Field(pattern="^(video|audio)$")
    prompt: str

class MCPResponse(BaseModel):
    job_id: str
    status: str
    download_url: str | None = None