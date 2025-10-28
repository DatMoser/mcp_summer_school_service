# Migration Guide: Legacy HTTP+SSE → Streamable HTTP

Quick guide for migrating your MCP client from the legacy dual-endpoint transport to the modern single-endpoint streamable HTTP transport.

## TL;DR

| What | Old (Legacy) | New (Streamable) |
|------|--------------|------------------|
| **Endpoint** | `/mcp-rpc` + `/mcp-sse/{id}` | `/mcp` |
| **Protocol Version** | `2024-11-05` | `2025-03-26` or `2025-06-18` |
| **Connections** | 2 (POST + GET) | 1 (POST) |
| **Streaming** | Manual (separate SSE) | Automatic (based on Accept header) |

---

## Step-by-Step Migration

### Step 1: Update Endpoint URL

**Before**:
```python
requests.post('https://api.c4dhi.org/mcp-rpc', ...)
```

**After**:
```python
requests.post('https://api.c4dhi.org/mcp', ...)
```

### Step 2: Update Protocol Version Header

**Before**:
```python
headers = {
    'MCP-Protocol-Version': '2024-11-05'
}
```

**After**:
```python
headers = {
    'MCP-Protocol-Version': '2025-03-26'  # or '2025-06-18'
}
```

### Step 3: Choose Response Mode

For **quick operations** (tools/list, ping, check_job_status):
```python
headers = {
    'Accept': 'application/json',  # Get JSON response
    'MCP-Protocol-Version': '2025-03-26'
}
```

For **long operations with streaming** (generate_video, generate_audio):
```python
headers = {
    'Accept': 'text/event-stream',  # Get streaming progress
    'MCP-Protocol-Version': '2025-03-26'
}
```

### Step 4: Remove Separate SSE Connection

**Before** (Legacy - two connections):
```python
# Connection 1: Send request
response = requests.post(
    'https://api.c4dhi.org/mcp-rpc',
    headers={'X-API-Key': api_key},
    json=request
)

# Connection 2: Listen for updates
sse_response = requests.get(
    f'https://api.c4dhi.org/mcp-sse/{client_id}',
    headers={'X-API-Key': api_key},
    stream=True
)
```

**After** (Streamable - one connection):
```python
# Single connection with streaming
response = requests.post(
    'https://api.c4dhi.org/mcp',
    headers={
        'X-API-Key': api_key,
        'Accept': 'text/event-stream',
        'MCP-Protocol-Version': '2025-03-26'
    },
    json=request,
    stream=True
)

# Iterate over streaming events
for line in response.iter_lines():
    if line:
        # Process SSE event
        ...
```

---

## Code Examples

### Before: Legacy Client

```python
import requests
import json
import threading

class LegacyMCPClient:
    def __init__(self, base_url, api_key):
        self.base_url = base_url
        self.api_key = api_key
        self.client_id = 'my-client-123'
        self.sse_thread = None

    def generate_video(self, prompt):
        # Step 1: Start SSE listener
        def sse_listener():
            response = requests.get(
                f'{self.base_url}/mcp-sse/{self.client_id}',
                headers={
                    'X-API-Key': self.api_key,
                    'Accept': 'text/event-stream'
                },
                stream=True
            )
            for line in response.iter_lines():
                if line:
                    print(line.decode('utf-8'))

        self.sse_thread = threading.Thread(target=sse_listener, daemon=True)
        self.sse_thread.start()

        # Step 2: Send request
        response = requests.post(
            f'{self.base_url}/mcp-rpc',
            headers={
                'Content-Type': 'application/json',
                'X-API-Key': self.api_key
            },
            json={
                'jsonrpc': '2.0',
                'id': 1,
                'method': 'tools/call',
                'params': {
                    'name': 'generate_video',
                    'arguments': {'prompt': prompt}
                }
            }
        )
        return response.json()

# Usage
client = LegacyMCPClient('https://api.c4dhi.org', 'your-key')
result = client.generate_video('sunset over ocean')
```

### After: Streamable Client

```python
import requests
import json

class StreamableMCPClient:
    def __init__(self, base_url, api_key):
        self.base_url = base_url
        self.api_key = api_key

    def generate_video(self, prompt):
        # Single request with streaming
        response = requests.post(
            f'{self.base_url}/mcp',
            headers={
                'Content-Type': 'application/json',
                'Accept': 'text/event-stream',  # Request streaming
                'X-API-Key': self.api_key,
                'MCP-Protocol-Version': '2025-03-26'
            },
            json={
                'jsonrpc': '2.0',
                'id': 1,
                'method': 'tools/call',
                'params': {
                    'name': 'generate_video',
                    'arguments': {'prompt': prompt}
                }
            },
            stream=True
        )

        # Process streaming events
        for line in response.iter_lines():
            if line:
                line_str = line.decode('utf-8')
                if line_str.startswith('data: '):
                    data = json.loads(line_str[6:])
                    print(f"Event: {data}")

                    # Check for completion
                    if data.get('type') == 'job_complete':
                        return data['result']

# Usage - Much simpler!
client = StreamableMCPClient('https://api.c4dhi.org', 'your-key')
result = client.generate_video('sunset over ocean')
```

**Key Improvements**:
- ✅ No separate SSE connection needed
- ✅ No threading required
- ✅ Simpler connection management
- ✅ Automatic cleanup when stream ends

---

## Common Patterns

### Pattern 1: Quick Operations (No Streaming)

**Before**:
```python
response = requests.post(
    'https://api.c4dhi.org/mcp-rpc',
    headers={'X-API-Key': api_key},
    json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}
)
```

**After** (same, just change endpoint):
```python
response = requests.post(
    'https://api.c4dhi.org/mcp',
    headers={
        'X-API-Key': api_key,
        'Accept': 'application/json',
        'MCP-Protocol-Version': '2025-03-26'
    },
    json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}
)
```

### Pattern 2: Long Operations with Polling

If you don't want streaming and prefer polling:

**Both Work the Same**:
```python
# Start job
response = requests.post(
    'https://api.c4dhi.org/mcp',  # New endpoint
    headers={
        'X-API-Key': api_key,
        'Accept': 'application/json',  # No streaming
        'MCP-Protocol-Version': '2025-03-26'
    },
    json={
        'jsonrpc': '2.0',
        'id': 1,
        'method': 'tools/call',
        'params': {
            'name': 'generate_video',
            'arguments': {'prompt': 'test'}
        }
    }
)

job_id = extract_job_id(response.json())

# Poll for status
while True:
    status_response = requests.post(
        'https://api.c4dhi.org/mcp',
        headers={
            'X-API-Key': api_key,
            'Accept': 'application/json',
            'MCP-Protocol-Version': '2025-03-26'
        },
        json={
            'jsonrpc': '2.0',
            'id': 2,
            'method': 'tools/call',
            'params': {
                'name': 'check_job_status',
                'arguments': {'job_id': job_id}
            }
        }
    )

    if is_complete(status_response):
        break

    time.sleep(5)
```

### Pattern 3: Long Operations with Streaming

**New capability** (not available in legacy):
```python
response = requests.post(
    'https://api.c4dhi.org/mcp',
    headers={
        'X-API-Key': api_key,
        'Accept': 'text/event-stream',  # Enable streaming
        'MCP-Protocol-Version': '2025-03-26'
    },
    json={
        'jsonrpc': '2.0',
        'id': 1,
        'method': 'tools/call',
        'params': {
            'name': 'generate_video',
            'arguments': {'prompt': 'test'}
        }
    },
    stream=True
)

# Automatically receive updates
for line in response.iter_lines():
    if line:
        line_str = line.decode('utf-8')
        if line_str.startswith('data: '):
            event = json.loads(line_str[6:])

            if event.get('type') == 'job_progress':
                print(f"Progress: {event['progress']}%")
            elif event.get('type') == 'job_complete':
                print(f"Done! URL: {event['result']['video_url']}")
                break
```

---

## Backward Compatibility

**Good news**: The server supports both transports simultaneously!

You can:
- ✅ Migrate gradually (some clients use new, some use old)
- ✅ Test new transport without breaking existing clients
- ✅ Roll back if needed (old transport still works)

### Testing Strategy

1. **Deploy server** (already supports both)
2. **Test new transport** in development
3. **Migrate one client** at a time
4. **Monitor** for issues
5. **Complete migration** when confident

---

## Validation Checklist

After migrating, verify:

- [ ] Protocol version header is set to `2025-03-26` or `2025-06-18`
- [ ] Using `POST /mcp` instead of `POST /mcp-rpc`
- [ ] No separate SSE connection to `/mcp-sse/{client_id}`
- [ ] Accept header is set appropriately:
  - [ ] `application/json` for quick ops or polling
  - [ ] `text/event-stream` for streaming
- [ ] Streaming responses are handled correctly
- [ ] Connection cleanup works properly
- [ ] Error handling updated for new response format

---

## Troubleshooting

### Issue: Getting 404 on `/mcp`

**Solution**: Ensure server is updated and deployed. Check `/mcp-info` endpoint to verify server supports streamable transport.

### Issue: Not receiving streaming events

**Check**:
1. Is `Accept: text/event-stream` header set?
2. Is `stream=True` in requests call?
3. Is the operation long-running (generate_video/generate_audio)?
4. Are you iterating over `response.iter_lines()`?

### Issue: Events are coming from wrong connection

**Problem**: You might still have legacy SSE connection open.

**Solution**: Remove all references to `/mcp-sse/{client_id}` endpoint.

### Issue: Can't switch back to legacy

**Solution**: Change headers back:
```python
headers = {
    'MCP-Protocol-Version': '2024-11-05'  # Use legacy version
}
# Use /mcp-rpc and /mcp-sse endpoints
```

---

## Need Help?

1. **Check server info**: `GET /mcp-info`
2. **Review examples**: See TRANSPORT_VERSIONS.md
3. **API reference**: See MCP_RPC_INTERFACE.md
4. **Test connection**: Use `test_connection.py`

---

## Summary

**Minimum changes required**:
1. Change endpoint: `/mcp-rpc` → `/mcp`
2. Add protocol version: `MCP-Protocol-Version: 2025-03-26`
3. Add Accept header: `Accept: text/event-stream` (for streaming)
4. Remove separate SSE connection code

**Benefits**:
- ✅ Simpler code
- ✅ Fewer connections
- ✅ Automatic streaming
- ✅ Future-proof

**Time estimate**: 15-30 minutes for a typical client

---

**Last Updated**: 2024-01-15
**Server Version**: 1.0.0
