# MCP Testing Guide

This guide shows you how to test the MCP (Model Context Protocol) functionality locally.

## Quick Setup for Testing

### 1. Start Redis (Required)
```bash
# Start Redis for job queue
docker run -d -p 6379:6379 redis:7-alpine
```

### 2. Set Minimal Environment Variables
```bash
export REDIS_URL="redis://localhost:6379/0"
export GCS_BUCKET="test-bucket" 
export GOOGLE_CLOUD_PROJECT="test-project"
```

### 3. Start the Service
```bash
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Testing Methods

### Method 1: Basic Component Testing (No Service Required)

Test MCP components directly without starting the full service:

```bash
python3 test_simple_mcp.py
```

This tests:
- ✅ MCP protocol handler initialization
- ✅ JSON-RPC 2.0 message processing  
- ✅ Data model validation
- ✅ Basic ping functionality

### Method 2: HTTP Endpoint Testing (Service Required)

Once the service is running, test HTTP endpoints:

#### Check Service Status
```bash
# Basic service info
curl http://localhost:8000/

# MCP-specific info
curl http://localhost:8000/mcp-info

# Health check (includes MCP status)
curl http://localhost:8000/health
```

#### Test MCP JSON-RPC Endpoint

**1. Initialize MCP Session**
```bash
curl -X POST http://localhost:8000/mcp-rpc \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "1",
    "method": "initialize",
    "params": {
      "protocolVersion": "2025-06-18",
      "capabilities": {"sampling": {}},
      "clientInfo": {"name": "Test Client", "version": "1.0.0"}
    }
  }'
```

Expected response:
```json
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

**2. Send Initialized Notification**
```bash
curl -X POST http://localhost:8000/mcp-rpc \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "notifications/initialized"
  }'
```

**3. List Available Tools**
```bash
curl -X POST http://localhost:8000/mcp-rpc \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "2",
    "method": "tools/list"
  }'
```

Expected response shows 4 tools:
- `generate_video`
- `generate_audio` 
- `analyze_writing_style`
- `check_job_status`

**4. Test Tool Call (Style Analysis)**
```bash
curl -X POST http://localhost:8000/mcp-rpc \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "3",
    "method": "tools/call",
    "params": {
      "name": "analyze_writing_style",
      "arguments": {
        "style_instruction": "Talk like Shakespeare"
      }
    }
  }'
```

This will return an error about missing credentials, which is expected.

**5. List Resources**
```bash
curl -X POST http://localhost:8000/mcp-rpc \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "4",
    "method": "resources/list"
  }'
```

**6. List Prompts**
```bash
curl -X POST http://localhost:8000/mcp-rpc \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "5",
    "method": "prompts/list"
  }'
```

**7. Get a Prompt**
```bash  
curl -X POST http://localhost:8000/mcp-rpc \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "6",
    "method": "prompts/get",
    "params": {
      "name": "video_generation",
      "arguments": {
        "topic": "dancing robot",
        "style": "futuristic",
        "mood": "energetic"
      }
    }
  }'
```

#### Test Server-Sent Events

Open a new terminal and connect to SSE:

```bash
curl -N http://localhost:8000/mcp-sse/test-client-123
```

This will show real-time events including keep-alive pings.

### Method 3: Full Compliance Testing

Run the complete MCP compliance test (requires service running):

```bash
python3 test_mcp_compliance.py
```

This comprehensive test covers:
- ✅ Protocol initialization
- ✅ All MCP methods (tools, resources, prompts)
- ✅ Error handling 
- ✅ Server-Sent Events
- ✅ JSON-RPC 2.0 compliance

## Expected Results

### ✅ Working Correctly
- Initialize returns server capabilities
- Tools list shows 4 available tools
- Resources list returns empty array (no jobs yet)
- Prompts list shows 3 available prompts
- Prompt get returns structured messages
- SSE connection streams keep-alive events
- Errors return proper JSON-RPC error codes

### ❌ Common Issues & Solutions

**"Connection refused"**
- Make sure service is running on port 8000
- Check `curl http://localhost:8000/health`

**"Redis connection failed"**  
- Start Redis: `docker run -d -p 6379:6379 redis:7-alpine`
- Check REDIS_URL environment variable

**"Google Cloud credentials error"**
- This is expected for basic testing
- Tool calls will fail but list operations work
- For full functionality, provide real credentials

**"Method not found"**
- Make sure you're using POST requests
- Check JSON-RPC format is correct
- Ensure "jsonrpc": "2.0" is included

## Testing with Real Credentials

To test actual video/audio generation:

1. Set up your credentials:
```bash
export GEMINI_API_KEY="your-gemini-key"
export GOOGLE_CLOUD_PROJECT="your-project-id"
export GCS_BUCKET="your-bucket-name"
export ELEVENLABS_API_KEY="your-elevenlabs-key"
```

2. Use tool calls with credentials in the arguments:
```bash
curl -X POST http://localhost:8000/mcp-rpc \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "7",
    "method": "tools/call",
    "params": {
      "name": "analyze_writing_style",
      "arguments": {
        "style_instruction": "Talk like a friendly teacher",
        "credentials": {
          "gemini_api_key": "your-actual-key"
        }
      }
    }
  }'
```

## Verification Checklist

Run through this checklist to verify MCP implementation:

- [ ] Service starts without errors
- [ ] `/mcp-info` returns MCP capabilities
- [ ] `/health` shows MCP component as healthy
- [ ] Initialize method works and returns server info
- [ ] Tools list returns 4 tools with proper schemas
- [ ] Resources list works (empty is fine)  
- [ ] Prompts list returns 3 prompts
- [ ] Prompt get returns structured messages
- [ ] Tool calls return proper errors when missing credentials
- [ ] SSE endpoint accepts connections and streams events
- [ ] Error responses follow JSON-RPC 2.0 format
- [ ] Unknown methods return -32601 error code

## Integration with LLMs

Once verified, LLMs can connect using standard MCP protocol:

1. **Initialize**: Send initialize request with capabilities
2. **Discover**: List available tools, resources, prompts  
3. **Execute**: Call tools with proper arguments
4. **Monitor**: Use SSE for real-time progress updates
5. **Access**: Read resources for job results

The service provides full MCP compatibility while preserving all existing REST API functionality.