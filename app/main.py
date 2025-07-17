# app/main.py
from fastapi import FastAPI
from app.mcp_models import MCPRequest, MCPResponse
from app.jobs import gen_video, gen_audio, q
import uuid

app = FastAPI(title="MCP PdTx Video and Audio generator")

@app.post("/mcp", response_model=MCPResponse)
def create_task(req: MCPRequest):
    job_id = str(uuid.uuid4())
    if req.mode == "video":
        job = q.enqueue_call(func=gen_video, args=(req.prompt,), job_id=job_id)
    else:
        job = q.enqueue_call(func=gen_audio, args=(req.prompt,), job_id=job_id)
    return MCPResponse(job_id=job.get_id(), status="queued")

@app.get("/mcp/{job_id}", response_model=MCPResponse)
def check(job_id: str):
    job = q.fetch_job(job_id)
    url = job.result if job.is_finished else None
    return MCPResponse(job_id=job_id, status=job.get_status(), download_url=url)