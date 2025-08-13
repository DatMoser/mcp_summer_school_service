# MCP Video/Audio Generator API - Client Integration Guide

## Service Overview
This service provides video and audio generation capabilities through both REST API and Model Context Protocol (MCP). It supports Google Cloud's video generation models and audio synthesis.

## Authentication
All endpoints (except `/health` and `/validate`) require API key authentication via the `X-API-Key` header.

## Base URL
```
http://localhost:8081  # Default Docker setup
```

## Core Endpoints

### 1. Health Check (No Auth Required)
```http
GET /health
```
Returns system status including Redis, queue, storage, and MCP protocol health.

### 2. API Key Validation (With Auth)
```http
GET /validate
X-API-Key: your-api-key
```
Response:
```json
{
  "valid": true,
  "message": "API key is valid"
}
```

### 3. Create Generation Job
```http
POST /mcp
Content-Type: application/json
X-API-Key: your-api-key

{
  "mode": "video",  // or "audio"
  "prompt": "A cat playing piano",
  "credentials": {
    "gemini_api_key": "your-gemini-key",
    "runpod_api_key": "your-runpod-key"  // for audio mode
  }
}
```

Response:
```json
{
  "job_id": "uuid-string",
  "status": "queued",
  "progress": 0,
  "current_step": "Job queued, waiting to start",
  "total_steps": 3,
  "step_number": 0
}
```

### 4. Check Job Status
```http
GET /mcp/{job_id}
X-API-Key: your-api-key
```

Response (completed):
```json
{
  "job_id": "uuid-string",
  "status": "finished",
  "download_url": "https://storage.googleapis.com/...",
  "progress": 100,
  "current_step": "Generation complete",
  "total_steps": 3,
  "step_number": 3
}
```

### 5. Writing Style Analysis
```http
POST /mcp/analyze-style
Content-Type: application/json
X-API-Key: your-api-key

{
  "prompt": "Talk like Trump",
  "credentials": {
    "gemini_api_key": "your-gemini-key"
  }
}
```

## Real-time Updates

### WebSocket Connection
```javascript
const ws = new WebSocket(`ws://localhost:8081/ws/${job_id}`);
ws.onmessage = (event) => {
  const update = JSON.parse(event.data);
  console.log('Progress:', update.progress, update.current_step);
};
```

### Server-Sent Events (MCP)
```http
GET /mcp-sse/{client_id}
X-API-Key: your-api-key
```

## MCP Protocol Integration

### JSON-RPC Endpoint
```http
POST /mcp-rpc
Content-Type: application/json
X-API-Key: your-api-key

{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/list",
  "params": {}
}
```

### Available MCP Tools
- `generate_video`: Create video from prompts/images
- `generate_audio`: Create podcast-style audio
- `analyze_writing_style`: Analyze dialogue patterns
- `check_job_status`: Query generation progress

### MCP Server Info
```http
GET /mcp-info
X-API-Key: your-api-key
```

## Error Handling

### Common HTTP Status Codes
- `200`: Success
- `401`: Missing/invalid API key
- `400`: Invalid request parameters
- `503`: Service unavailable (health issues)

### Error Response Format
```json
{
  "error": "Unauthorized",
  "message": "API key required. Please provide X-API-Key header."
}
```

## Integration Examples

### Python Client
```python
import requests

headers = {"X-API-Key": "your-api-key"}
base_url = "http://localhost:8081"

# Create video generation job
job_data = {
    "mode": "video",
    "prompt": "A sunset over mountains",
    "credentials": {"gemini_api_key": "your-key"}
}

response = requests.post(f"{base_url}/mcp", json=job_data, headers=headers)
job = response.json()

# Poll for completion
while True:
    status = requests.get(f"{base_url}/mcp/{job['job_id']}", headers=headers)
    result = status.json()
    
    if result["status"] == "finished":
        print(f"Video ready: {result['download_url']}")
        break
    elif result["status"] == "failed":
        print("Generation failed")
        break
```

### JavaScript Client
```javascript
const apiKey = 'your-api-key';
const baseUrl = 'http://localhost:8081';

async function generateVideo(prompt) {
  const response = await fetch(`${baseUrl}/mcp`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': apiKey
    },
    body: JSON.stringify({
      mode: 'video',
      prompt: prompt,
      credentials: { gemini_api_key: 'your-key' }
    })
  });
  
  const job = await response.json();
  return job.job_id;
}

async function checkStatus(jobId) {
  const response = await fetch(`${baseUrl}/mcp/${jobId}`, {
    headers: { 'X-API-Key': apiKey }
  });
  return response.json();
}
```

## CORS Configuration
The service supports CORS with configurable origins via `CORS_ORIGINS` environment variable.

## Rate Limiting
No built-in rate limiting. Implement client-side throttling as needed.

## Security Notes
- Always use HTTPS in production
- Store API keys securely (environment variables)
- Monitor `/health` endpoint for service availability
- Use `/validate` endpoint to verify API key before making requests