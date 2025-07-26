# MCP Protocol Implementation

This document describes the Model Context Protocol (MCP) implementation in the MCP Summer School Service, providing full MCP compliance alongside the existing REST API.

## Overview

The service now supports both:
- **REST API**: Traditional HTTP endpoints (existing functionality preserved)
- **MCP Protocol**: JSON-RPC 2.0 based protocol with tools, resources, and prompts

## MCP Protocol Compliance

### Supported MCP Version
- **Protocol Version**: `2025-06-18`
- **Transport**: HTTP POST + Server-Sent Events
- **Message Format**: JSON-RPC 2.0

### Server Capabilities
```json
{
  "tools": {"listChanged": true},
  "resources": {"subscribe": true, "listChanged": true},
  "prompts": {"listChanged": true},
  "logging": {}
}
```

## MCP Endpoints

### Core Protocol
- `POST /mcp-rpc` - Main JSON-RPC 2.0 endpoint for all MCP communication
- `GET /mcp-sse/{client_id}` - Server-Sent Events for real-time notifications  
- `GET /mcp-info` - MCP server information and capabilities

### Protocol Methods

#### Initialization
```json
// Request
{
  "jsonrpc": "2.0",
  "id": "1",
  "method": "initialize",
  "params": {
    "protocolVersion": "2025-06-18",
    "capabilities": {"sampling": {}},
    "clientInfo": {"name": "Client", "version": "1.0.0"}
  }
}

// Response
{
  "jsonrpc": "2.0",
  "id": "1",
  "result": {
    "protocolVersion": "2025-06-18",
    "capabilities": {
      "tools": {"listChanged": true},
      "resources": {"subscribe": true, "listChanged": true},
      "prompts": {"listChanged": true}
    },
    "serverInfo": {
      "name": "MCP Video/Audio Generator",
      "version": "1.0.0"
    }
  }
}
```

#### Tools Interface

**List Tools**
```json
{
  "jsonrpc": "2.0",
  "id": "2",
  "method": "tools/list"
}
```

**Available Tools:**
- `generate_video` - Generate videos using Google Veo models
- `generate_audio` - Generate audio/podcasts using AI TTS
- `analyze_writing_style` - Analyze dialogue styles for content generation
- `check_job_status` - Monitor job progress and results

**Call Tool Example**
```json
{
  "jsonrpc": "2.0",
  "id": "3",
  "method": "tools/call",
  "params": {
    "name": "generate_video",
    "arguments": {
      "prompt": "A cat playing with a ball of yarn",
      "duration_seconds": 8,
      "aspect_ratio": "16:9",
      "credentials": {
        "gemini_api_key": "your-key",
        "google_cloud_project": "your-project"
      }
    }
  }
}
```

#### Resources Interface

**List Resources**
```json
{
  "jsonrpc": "2.0",
  "id": "4", 
  "method": "resources/list"
}
```

**Resource Types:**
- `job://{job_id}` - Access job status and results in JSON format

**Read Resource Example**
```json
{
  "jsonrpc": "2.0",
  "id": "5",
  "method": "resources/read",
  "params": {
    "uri": "job://abc123"
  }
}
```

#### Prompts Interface

**List Prompts**
```json
{
  "jsonrpc": "2.0",
  "id": "6",
  "method": "prompts/list"
}
```

**Available Prompts:**
- `video_generation` - Template for video creation with customizable parameters
- `podcast_generation` - Template for audio/podcast content
- `style_analysis` - Template for analyzing speaking/writing styles

**Get Prompt Example**
```json
{
  "jsonrpc": "2.0",
  "id": "7",
  "method": "prompts/get",
  "params": {
    "name": "video_generation",
    "arguments": {
      "topic": "space exploration",
      "style": "documentary",
      "mood": "inspiring"
    }
  }
}
```

## Server-Sent Events (SSE)

Real-time notifications are delivered via SSE at `/mcp-sse/{client_id}`:

### Job Progress Updates
```json
{
  "event": "job_progress",
  "data": {
    "type": "job_progress",
    "job_id": "abc123",
    "status": "started",
    "progress": 60,
    "current_step": "Converting text to speech",
    "step_number": 3,
    "total_steps": 4
  }
}
```

### Job Completion
```json
{
  "event": "job_complete",
  "data": {
    "type": "job_complete", 
    "job_id": "abc123",
    "status": "finished",
    "progress": 100,
    "download_url": "https://storage.googleapis.com/bucket/audio/file.mp3"
  }
}
```

### Capability Changes
```json
{
  "event": "capability_changed",
  "data": {
    "type": "capability_changed",
    "capability": "tools",
    "available": true
  }
}
```

## Integration with Existing System

The MCP implementation preserves all existing functionality:

### Preserved Features ✅
- All REST endpoints (`/mcp`, `/mcp/{job_id}`, etc.) work unchanged
- WebSocket real-time updates continue working
- Redis job queue system unchanged  
- Google Cloud integration intact
- Credential handling system preserved
- All business logic for video/audio generation preserved

### New MCP Features 🆕
- JSON-RPC 2.0 protocol compliance
- MCP initialization handshake
- Structured tools, resources, and prompts
- Server-Sent Events for real-time updates
- Protocol version negotiation
- Standardized error handling

## Usage Examples

### Basic MCP Client Session

```python
import requests
import json

# 1. Initialize MCP session
init_request = {
    "jsonrpc": "2.0",
    "id": "1",
    "method": "initialize", 
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {"sampling": {}},
        "clientInfo": {"name": "My Client", "version": "1.0.0"}
    }
}

response = requests.post("http://localhost:8000/mcp-rpc", json=init_request)
print(response.json())

# 2. Send initialized notification
init_notify = {
    "jsonrpc": "2.0",
    "method": "notifications/initialized"
}
requests.post("http://localhost:8000/mcp-rpc", json=init_notify)

# 3. List available tools
tools_request = {
    "jsonrpc": "2.0", 
    "id": "2",
    "method": "tools/list"
}
response = requests.post("http://localhost:8000/mcp-rpc", json=tools_request)
print("Available tools:", response.json())
```

### Video Generation via MCP

```python
video_request = {
    "jsonrpc": "2.0",
    "id": "3", 
    "method": "tools/call",
    "params": {
        "name": "generate_video",
        "arguments": {
            "prompt": "A sunset over mountains with birds flying",
            "duration_seconds": 5,
            "aspect_ratio": "16:9",
            "model": "veo-3.0-generate-preview",
            "credentials": {
                "gemini_api_key": "your-gemini-key",
                "google_cloud_credentials": {...},
                "google_cloud_project": "your-project-id",
                "vertex_ai_region": "us-central1",
                "gcs_bucket": "your-bucket"
            }
        }
    }
}

response = requests.post("http://localhost:8000/mcp-rpc", json=video_request)
result = response.json()
print("Video generation started:", result)
```

### Real-time Progress Monitoring

```python
import sseclient

# Connect to SSE stream
client_id = "my-client-123"
sse_url = f"http://localhost:8000/mcp-sse/{client_id}"

client = sseclient.SSEClient(sse_url)
for event in client.events():
    data = json.loads(event.data)
    print(f"Event: {event.event}, Data: {data}")
    
    if data.get("type") == "job_complete":
        print(f"Job finished! Download: {data.get('download_url')}")
        break
```

## Testing MCP Compliance

Run the compliance test script:

```bash
python test_mcp_compliance.py
```

This tests:
- ✅ Protocol initialization and capability negotiation
- ✅ Tools interface (list/call)  
- ✅ Resources interface (list/read)
- ✅ Prompts interface (list/get)
- ✅ Error handling and edge cases
- ✅ Server-Sent Events connectivity

## Error Handling

MCP protocol uses standard JSON-RPC 2.0 error codes:

| Code | Meaning | Description |
|------|---------|-------------|
| -32700 | Parse Error | Invalid JSON |
| -32600 | Invalid Request | Invalid JSON-RPC request |
| -32601 | Method Not Found | Unknown method |
| -32602 | Invalid Params | Invalid parameters |
| -32603 | Internal Error | Server error |
| -32000 | Invalid Protocol Version | Unsupported MCP version |
| -32001 | Unsupported Capability | Capability not supported |
| -32002 | Tool Execution Error | Tool call failed |
| -32003 | Resource Not Found | Resource doesn't exist |

Example error response:
```json
{
  "jsonrpc": "2.0",
  "id": "1",
  "error": {
    "code": -32602,
    "message": "Invalid credentials: Gemini API key is required",
    "data": {"field": "credentials.gemini_api_key"}
  }
}
```

## Health Monitoring

Check MCP protocol health:

```bash
curl http://localhost:8000/health
```

The health check includes MCP status:
```json
{
  "components": {
    "mcp": {
      "status": "healthy",
      "message": "MCP protocol handler operational", 
      "protocol_version": "2025-06-18",
      "sse_connections": 2,
      "initialized": true
    }
  }
}
```

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   REST Client   │    │   MCP Client    │    │  SSE Client     │
│                 │    │  (JSON-RPC 2.0) │    │ (Real-time)     │  
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   REST Routes   │    │  MCP Transport  │    │   SSE Stream    │
│ (/mcp, /health) │    │   (/mcp-rpc)    │    │ (/mcp-sse/*)    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                                 ▼
                    ┌─────────────────┐
                    │ Business Logic  │
                    │ (Jobs, AI APIs) │
                    └─────────────────┘
```

## Compatibility

- **MCP Protocol Version**: 2025-06-18 ✅
- **JSON-RPC**: 2.0 ✅  
- **Transport**: HTTP POST, Server-Sent Events ✅
- **Capabilities**: Tools, Resources, Prompts ✅
- **Real-time Updates**: SSE notifications ✅
- **Backward Compatibility**: All REST endpoints preserved ✅

The implementation provides full MCP protocol compliance while maintaining 100% backward compatibility with existing REST API clients.