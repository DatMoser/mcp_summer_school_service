# MCP Transport Versions Guide

This document explains the two MCP transport mechanisms supported by this server and helps you choose the right one for your use case.

## Quick Reference

| Feature | Streamable HTTP (2025+) | Legacy HTTP+SSE (2024-11-05) |
|---------|------------------------|------------------------------|
| **Endpoint** | Single `/mcp` | Dual `/mcp-rpc` + `/mcp-sse/{id}` |
| **Protocol Versions** | 2025-03-26, 2025-06-18 | 2024-11-05 |
| **Request Method** | POST | POST (requests) + GET (events) |
| **Streaming** | Automatic (based on Accept header) | Manual (separate SSE connection) |
| **Connection Management** | Automatic | Manual (client manages two connections) |
| **Status** | ✅ Recommended | 📦 Legacy (maintained for compatibility) |
| **Best For** | Modern clients, simpler integration | Older clients, explicit control |

---

## Transport #1: Streamable HTTP (Recommended)

### Overview

**Protocol Versions**: `2025-03-26`, `2025-06-18`

The **Streamable HTTP Transport** is the modern MCP standard that uses a single endpoint for all communication. It intelligently decides whether to return a JSON response or upgrade to SSE streaming based on:
1. The operation type (quick vs long-running)
2. The client's `Accept` header preference

### Architecture

```
Client                          Server
  |                               |
  | POST /mcp                     |
  | Accept: text/event-stream     |
  |------------------------------>|
  |                               |
  |    event: message (initial)   |
  |<------------------------------|
  |    event: job_progress (45%)  |
  |<------------------------------|
  |    event: job_progress (90%)  |
  |<------------------------------|
  |    event: job_complete        |
  |<------------------------------|
  |                               |
  | Connection closes             |
```

### Key Features

#### ✅ Single Endpoint
- All communication flows through `POST /mcp`
- No need to manage separate SSE connections
- Simpler client implementation

#### ✅ Automatic Streaming Detection
The server automatically determines if streaming is appropriate:

| Operation | Accept: application/json | Accept: text/event-stream |
|-----------|-------------------------|---------------------------|
| **Quick** (ping, tools/list) | JSON response | JSON in SSE (single event) |
| **Long-running** (generate_video) | JSON with job_id | SSE stream with progress |

#### ✅ Smart Response Mode
- **Quick operations** (< 5 seconds): Always returns JSON immediately
- **Long operations** (2-10 minutes):
  - JSON mode: Returns job_id, client polls with `check_job_status`
  - Streaming mode: Streams progress updates automatically until completion

### When to Use

Use **Streamable HTTP** when:
- ✅ You're building a new MCP client
- ✅ You want simpler integration (one endpoint)
- ✅ You prefer automatic streaming for long operations
- ✅ Your client library supports Accept header negotiation
- ✅ You want the latest MCP features

### Example Usage

#### Quick Operation (JSON Response)

```bash
curl -X POST https://api.c4dhi.org/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -H "X-API-Key: your-key" \
  -H "MCP-Protocol-Version: 2025-03-26" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/list"
  }'
```

**Response** (immediate JSON):
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "tools": [...]
  }
}
```

#### Long Operation (JSON with job_id)

```bash
curl -X POST https://api.c4dhi.org/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -H "X-API-Key: your-key" \
  -H "MCP-Protocol-Version: 2025-03-26" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
      "name": "generate_video",
      "arguments": {"prompt": "sunset over ocean"}
    }
  }'
```

**Response** (immediate JSON with job_id):
```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "content": [{
      "type": "text",
      "text": "Video generation started!\nJob ID: abc123..."
    }]
  }
}
```

Then poll with `check_job_status` tool.

#### Long Operation (Streaming)

```bash
curl -X POST https://api.c4dhi.org/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -H "X-API-Key: your-key" \
  -H "MCP-Protocol-Version: 2025-03-26" \
  -d '{
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {
      "name": "generate_video",
      "arguments": {"prompt": "sunset over ocean"}
    }
  }' \
  --no-buffer
```

**Response** (SSE stream):
```
event: message
data: {"jsonrpc":"2.0","id":3,"result":{"content":[{"type":"text","text":"Job ID: abc123"}]}}

event: job_progress
data: {"type":"job_progress","job_id":"abc123","progress":15,"current_step":"Initializing"}

event: job_progress
data: {"type":"job_progress","job_id":"abc123","progress":45,"current_step":"Generating frames"}

event: job_progress
data: {"type":"job_progress","job_id":"abc123","progress":90,"current_step":"Finalizing"}

event: job_complete
data: {"type":"job_complete","job_id":"abc123","result":{"video_url":"https://..."}}
```

Connection automatically closes after completion.

### Python Client Example

```python
import requests
import json

class StreamableMCPClient:
    def __init__(self, base_url, api_key):
        self.base_url = base_url
        self.api_key = api_key
        self.headers = {
            'Content-Type': 'application/json',
            'X-API-Key': api_key,
            'MCP-Protocol-Version': '2025-03-26'
        }

    def call_quick(self, method, params=None):
        """Call for quick operations - returns JSON"""
        headers = {**self.headers, 'Accept': 'application/json'}
        response = requests.post(
            f'{self.base_url}/mcp',
            headers=headers,
            json={
                'jsonrpc': '2.0',
                'id': 1,
                'method': method,
                'params': params or {}
            }
        )
        return response.json()

    def call_with_streaming(self, method, params=None):
        """Call for long operations - yields progress updates"""
        headers = {**self.headers, 'Accept': 'text/event-stream'}
        response = requests.post(
            f'{self.base_url}/mcp',
            headers=headers,
            json={
                'jsonrpc': '2.0',
                'id': 1,
                'method': method,
                'params': params or {}
            },
            stream=True
        )

        for line in response.iter_lines():
            if line:
                line_str = line.decode('utf-8')
                if line_str.startswith('data: '):
                    yield json.loads(line_str[6:])

# Usage
client = StreamableMCPClient('https://api.c4dhi.org', 'your-key')

# Quick operation
result = client.call_quick('tools/list')
print(result)

# Long operation with streaming
for event in client.call_with_streaming(
    'tools/call',
    {'name': 'generate_video', 'arguments': {'prompt': 'test'}}
):
    print(f"Progress: {event.get('progress', 0)}%")
```

---

## Transport #2: Legacy HTTP+SSE

### Overview

**Protocol Version**: `2024-11-05`

The **Legacy HTTP+SSE Transport** uses a dual-endpoint architecture where:
- Client sends JSON-RPC requests to `POST /mcp-rpc`
- Client maintains a separate SSE connection to `GET /mcp-sse/{client_id}` for notifications

This was the original MCP remote transport design.

### Architecture

```
Client                          Server
  |                               |
  | POST /mcp-rpc (request)       |
  |------------------------------>|
  | {"method":"generate_video"}   |
  |                               |
  |    JSON response (job_id)     |
  |<------------------------------|
  |                               |

  (Separate connection)

  | GET /mcp-sse/client-123       |
  |------------------------------>|
  |    event: job_progress (45%)  |
  |<------------------------------|
  |    event: job_progress (90%)  |
  |<------------------------------|
  |    event: job_complete        |
  |<------------------------------|
```

### Key Features

#### 📦 Dual Endpoints
- `POST /mcp-rpc`: Send JSON-RPC requests
- `GET /mcp-sse/{client_id}`: Receive real-time notifications

#### 📦 Manual Connection Management
- Client must establish and maintain two separate connections
- SSE connection stays open for the duration of the session
- All job progress notifications broadcast to SSE connection

#### 📦 Explicit Control
- Clear separation between requests and notifications
- Client has full control over connection lifecycle
- No automatic streaming decisions

### When to Use

Use **Legacy HTTP+SSE** when:
- ✅ You have an existing MCP client using this pattern
- ✅ You need backward compatibility
- ✅ You want explicit control over connections
- ✅ Your client expects the dual-endpoint pattern
- ✅ You're debugging or troubleshooting

### Example Usage

#### 1. Send Request

```bash
curl -X POST https://api.c4dhi.org/mcp-rpc \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -H "MCP-Protocol-Version: 2024-11-05" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "generate_video",
      "arguments": {"prompt": "sunset"}
    }
  }'
```

**Response**:
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [{
      "type": "text",
      "text": "Job ID: abc123..."
    }]
  }
}
```

#### 2. Listen for Progress (Separate Connection)

```bash
curl -N https://api.c4dhi.org/mcp-sse/my-client-id \
  -H "X-API-Key: your-key" \
  -H "Accept: text/event-stream"
```

**Stream Output**:
```
event: connected
data: {"type":"connection_established","client_id":"my-client-id"}

event: job_progress
data: {"type":"job_progress","job_id":"abc123","progress":45}

event: job_complete
data: {"type":"job_complete","job_id":"abc123","download_url":"https://..."}
```

### Python Client Example

```python
import requests
import json
import threading

class LegacyMCPClient:
    def __init__(self, base_url, api_key, client_id):
        self.base_url = base_url
        self.api_key = api_key
        self.client_id = client_id
        self.sse_thread = None
        self.running = False

    def send_request(self, method, params=None):
        """Send JSON-RPC request"""
        response = requests.post(
            f'{self.base_url}/mcp-rpc',
            headers={
                'Content-Type': 'application/json',
                'X-API-Key': self.api_key,
                'MCP-Protocol-Version': '2024-11-05'
            },
            json={
                'jsonrpc': '2.0',
                'id': 1,
                'method': method,
                'params': params or {}
            }
        )
        return response.json()

    def start_sse_listener(self, callback):
        """Start SSE listener in background thread"""
        def sse_worker():
            response = requests.get(
                f'{self.base_url}/mcp-sse/{self.client_id}',
                headers={
                    'X-API-Key': self.api_key,
                    'Accept': 'text/event-stream'
                },
                stream=True
            )

            for line in response.iter_lines():
                if not self.running:
                    break
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith('data: '):
                        data = json.loads(line_str[6:])
                        callback(data)

        self.running = True
        self.sse_thread = threading.Thread(target=sse_worker, daemon=True)
        self.sse_thread.start()

    def stop(self):
        """Stop SSE listener"""
        self.running = False
        if self.sse_thread:
            self.sse_thread.join(timeout=1)

# Usage
client = LegacyMCPClient('https://api.c4dhi.org', 'your-key', 'my-client')

# Start SSE listener
def on_notification(data):
    print(f"Notification: {data}")

client.start_sse_listener(on_notification)

# Send request
result = client.send_request(
    'tools/call',
    {'name': 'generate_video', 'arguments': {'prompt': 'test'}}
)
print(result)

# Keep running to receive notifications
import time
time.sleep(60)

client.stop()
```

---

## Comparison

### Advantages: Streamable HTTP

✅ **Simpler**: One endpoint instead of two
✅ **Modern**: Latest MCP standard
✅ **Automatic**: Server decides when to stream
✅ **Efficient**: Connection only open when needed
✅ **Cleaner**: No manual connection management

### Advantages: Legacy HTTP+SSE

✅ **Compatible**: Works with older clients
✅ **Explicit**: Clear separation of concerns
✅ **Flexible**: Client controls connections
✅ **Debuggable**: Easy to inspect each connection
✅ **Proven**: Battle-tested pattern

---

## Migration Path

### From Legacy to Streamable HTTP

**Step 1**: Update your protocol version
```python
# Old
headers = {'MCP-Protocol-Version': '2024-11-05'}

# New
headers = {'MCP-Protocol-Version': '2025-03-26'}
```

**Step 2**: Change endpoint
```python
# Old
POST /mcp-rpc

# New
POST /mcp
```

**Step 3**: Add Accept header for streaming
```python
# For streaming responses
headers = {
    'Accept': 'text/event-stream',  # Request streaming
    'MCP-Protocol-Version': '2025-03-26'
}
```

**Step 4**: Remove separate SSE connection
```python
# Old: Two connections
requests.post(f'{base_url}/mcp-rpc', ...)
requests.get(f'{base_url}/mcp-sse/{client_id}', stream=True)

# New: One connection
requests.post(f'{base_url}/mcp', ..., stream=True)
```

---

## Recommendations

### For New Projects
**Use Streamable HTTP** (`POST /mcp` with `2025-03-26`):
- Simpler to implement
- Future-proof
- Better developer experience

### For Existing Projects
**Evaluate migration effort**:
- If easy: Migrate to Streamable HTTP
- If complex: Stay on Legacy (fully supported)
- If uncertain: Use both (server supports both!)

### For Maximum Compatibility
**Support both transports**:
```python
def detect_transport(base_url, api_key):
    """Auto-detect which transport the server supports"""
    response = requests.get(
        f'{base_url}/mcp-info',
        headers={'X-API-Key': api_key}
    )
    info = response.json()

    if 'streamable' in info.get('transport', {}):
        return 'streamable'
    else:
        return 'legacy'
```

---

## Troubleshooting

### Issue: Not receiving streaming responses

**Check**:
1. Are you sending `Accept: text/event-stream`?
2. Are you using `POST /mcp` (not `/mcp-rpc`)?
3. Is your protocol version 2025-03-26 or 2025-06-18?
4. Is the operation long-running (generate_video, generate_audio)?

### Issue: Legacy SSE not connecting

**Check**:
1. Are you using `GET /mcp-sse/{client_id}`?
2. Is your client_id unique and consistent?
3. Are you sending `Accept: text/event-stream`?
4. Is your connection staying open (not closing immediately)?

### Issue: No progress updates

**Check**:
- Streamable: Connection must stay open with streaming
- Legacy: Separate SSE connection must be established
- Both: Job must actually be running (check with `check_job_status`)

---

## Further Reading

- **MCP_RPC_INTERFACE.md**: Complete API reference
- **MIGRATION_GUIDE.md**: Step-by-step migration instructions
- **README.md**: Setup and configuration
- **CLAUDE_DESKTOP_SETUP.md**: Claude Desktop integration

---

**Last Updated**: 2024-01-15
**Server Version**: 1.0.0
**Supported Protocol Versions**: 2024-11-05, 2025-03-26, 2025-06-18
