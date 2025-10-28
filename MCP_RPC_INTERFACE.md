# MCP JSON-RPC 2.0 Interface Documentation

Complete technical reference for the Model Context Protocol (MCP) JSON-RPC 2.0 remote interface.

**Server Base URL**: `https://api.c4dhi.org`

**Protocol Version**: `2025-06-18`

**JSON-RPC Version**: `2.0`

---

## Table of Contents

1. [Protocol Overview](#protocol-overview)
2. [Authentication](#authentication)
3. [Transport Layer](#transport-layer)
4. [Request/Response Format](#requestresponse-format)
5. [MCP Methods](#mcp-methods)
6. [Tools Interface](#tools-interface)
7. [Resources Interface](#resources-interface)
8. [Prompts Interface](#prompts-interface)
9. [Server-Sent Events (SSE)](#server-sent-events-sse)
10. [Error Codes](#error-codes)
11. [Client Implementation Examples](#client-implementation-examples)

---

## Protocol Overview

This server implements the Model Context Protocol (MCP) using JSON-RPC 2.0 as the message format. The protocol enables AI assistants to:

- **Generate videos** using Google Veo models (1-60 seconds)
- **Generate audio/podcasts** using text-to-speech (ElevenLabs)
- **Analyze writing styles** for custom voice generation
- **Monitor job progress** in real-time

### Key Features

- **Asynchronous job processing** with Redis queue
- **Real-time progress updates** via Server-Sent Events
- **Flexible credential management** (server-side or per-request)
- **Google Cloud Storage** for media hosting
- **Multiple video models** (Veo 3.0, 2.0, 1.0)
- **Audio format options** (MP3, WAV, M4A)

---

## Authentication

All endpoints (except `/health` and `/validate`) require API key authentication.

### Header Format

```
X-API-Key: your-api-key-here
```

### Example

```bash
curl -X POST https://api.c4dhi.org/mcp-rpc \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key-here" \
  -d '{"jsonrpc":"2.0","id":1,"method":"ping"}'
```

### Credential Options

You can provide credentials in two ways:

1. **Server-side** (configured via environment variables)
2. **Per-request** (passed in tool call parameters)

Per-request credentials override server defaults:

```json
{
  "credentials": {
    "gemini_api_key": "AIza...",
    "google_cloud_credentials": {...},
    "google_cloud_project": "your-project-id",
    "vertex_ai_region": "us-central1",
    "gcs_bucket": "your-bucket-name",
    "elevenlabs_api_key": "sk_..."
  }
}
```

---

## Transport Layer

### HTTP POST Endpoint

**URL**: `POST /mcp-rpc`

**Content-Type**: `application/json`

**Authentication**: Required (X-API-Key header)

All JSON-RPC requests are sent via HTTP POST to this endpoint.

### Server-Sent Events (SSE) Endpoint

**URL**: `GET /mcp-sse/{client_id}`

**Authentication**: Required (X-API-Key header)

Real-time notifications for job progress, capability changes, and system events.

### Info Endpoint

**URL**: `GET /mcp-info`

**Authentication**: Required (X-API-Key header)

Returns server capabilities and configuration.

---

## Request/Response Format

### JSON-RPC 2.0 Request

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "method_name",
  "params": {
    "param1": "value1",
    "param2": "value2"
  }
}
```

**Fields**:

- `jsonrpc` (string, required): Must be `"2.0"`
- `id` (string|number, required): Unique request identifier
- `method` (string, required): MCP method name
- `params` (object, optional): Method parameters

### JSON-RPC 2.0 Response (Success)

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "data": "response data"
  }
}
```

**Fields**:

- `jsonrpc` (string): Always `"2.0"`
- `id` (string|number): Matches request ID
- `result` (any): Method return value

### JSON-RPC 2.0 Response (Error)

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": {
    "code": -32600,
    "message": "Invalid Request",
    "data": {
      "details": "Additional error information"
    }
  }
}
```

**Fields**:

- `jsonrpc` (string): Always `"2.0"`
- `id` (string|number|null): Request ID or null if not available
- `error` (object): Error details
  - `code` (number): Error code
  - `message` (string): Error message
  - `data` (any, optional): Additional error information

### JSON-RPC 2.0 Notification

Notifications are messages without an `id` field (no response expected):

```json
{
  "jsonrpc": "2.0",
  "method": "notifications/initialized"
}
```

---

## MCP Methods

### 1. initialize

**Description**: Initializes the MCP protocol connection and negotiates capabilities.

**Method**: `initialize`

**Parameters**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `protocolVersion` | string | Yes | MCP protocol version (e.g., "2025-06-18") |
| `capabilities` | object | Yes | Client capabilities (can be empty: {}) |
| `clientInfo` | object | Yes | Client identification |
| `clientInfo.name` | string | Yes | Client name |
| `clientInfo.version` | string | Yes | Client version |

**Request Example**:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {
    "protocolVersion": "2025-06-18",
    "capabilities": {},
    "clientInfo": {
      "name": "my-mcp-client",
      "version": "1.0.0"
    }
  }
}
```

**Response**:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "protocolVersion": "2025-06-18",
    "capabilities": {
      "tools": {},
      "resources": {},
      "prompts": {}
    },
    "serverInfo": {
      "name": "video-audio-mcp-server",
      "version": "1.0.0"
    }
  }
}
```

**Response Fields**:

- `protocolVersion` (string): Server's MCP protocol version
- `capabilities` (object): Server capabilities
- `serverInfo` (object): Server identification
  - `name` (string): Server name
  - `version` (string): Server version

**Notes**:
- This must be the first method called after connection
- After successful initialization, send `notifications/initialized` notification

---

### 2. notifications/initialized

**Description**: Notification sent by client after successful initialization.

**Method**: `notifications/initialized`

**Parameters**: None

**Request Example**:

```json
{
  "jsonrpc": "2.0",
  "method": "notifications/initialized"
}
```

**Response**: None (this is a notification, no response expected)

---

### 3. ping

**Description**: Tests connection health. Returns empty result if successful.

**Method**: `ping`

**Parameters**: None (empty object)

**Request Example**:

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "ping",
  "params": {}
}
```

**Response**:

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {}
}
```

---

### 4. tools/list

**Description**: Lists all available tools with their schemas.

**Method**: `tools/list`

**Parameters**: None (empty object)

**Request Example**:

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/list",
  "params": {}
}
```

**Response**:

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "result": {
    "tools": [
      {
        "name": "generate_video",
        "description": "Generate a video using Google Veo models...",
        "inputSchema": {
          "type": "object",
          "properties": {
            "prompt": {
              "type": "string",
              "description": "Text description of the video to generate"
            },
            "duration": {
              "type": "integer",
              "description": "Video duration in seconds (1-60)",
              "minimum": 1,
              "maximum": 60,
              "default": 10
            },
            "aspect_ratio": {
              "type": "string",
              "enum": ["16:9", "9:16", "1:1"],
              "default": "16:9"
            },
            "model": {
              "type": "string",
              "enum": ["veo-3.0-generate-preview", "veo-2.0-generate-001", "veo-1.0-generate-001"],
              "default": "veo-3.0-generate-preview"
            },
            "generate_audio": {
              "type": "boolean",
              "default": true
            },
            "credentials": {
              "type": "object",
              "description": "Optional credentials to override server defaults"
            }
          },
          "required": ["prompt"]
        }
      },
      {
        "name": "generate_audio",
        "description": "Generate audio/podcast using AI text-to-speech...",
        "inputSchema": {
          "type": "object",
          "properties": {
            "prompt": {
              "type": "string",
              "description": "Prompt for podcast/audio generation"
            },
            "format": {
              "type": "string",
              "enum": ["mp3", "wav", "m4a"],
              "default": "mp3"
            },
            "max_duration": {
              "type": "integer",
              "description": "Maximum duration in seconds",
              "default": 300
            },
            "generate_thumbnail": {
              "type": "boolean",
              "default": true
            },
            "credentials": {
              "type": "object"
            }
          },
          "required": ["prompt"]
        }
      },
      {
        "name": "analyze_writing_style",
        "description": "Analyze writing/speaking style for content generation...",
        "inputSchema": {
          "type": "object",
          "properties": {
            "style_description": {
              "type": "string",
              "description": "Description of style to analyze (e.g., 'Donald Trump')"
            },
            "credentials": {
              "type": "object"
            }
          },
          "required": ["style_description"]
        }
      },
      {
        "name": "check_job_status",
        "description": "Check the status of a video or audio generation job",
        "inputSchema": {
          "type": "object",
          "properties": {
            "job_id": {
              "type": "string",
              "description": "Job ID returned from generate_video or generate_audio"
            }
          },
          "required": ["job_id"]
        }
      }
    ]
  }
}
```

**Response Fields**:

- `tools` (array): List of available tools
  - `name` (string): Tool identifier
  - `description` (string): Human-readable description
  - `inputSchema` (object): JSON Schema for tool parameters

---

### 5. tools/call

**Description**: Invokes a tool with specified parameters.

**Method**: `tools/call`

**Parameters**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Tool name (e.g., "generate_video") |
| `arguments` | object | Yes | Tool-specific parameters |

**Request Example (generate_video)**:

```json
{
  "jsonrpc": "2.0",
  "id": 4,
  "method": "tools/call",
  "params": {
    "name": "generate_video",
    "arguments": {
      "prompt": "A serene mountain landscape at sunrise with mist",
      "duration": 10,
      "aspect_ratio": "16:9",
      "model": "veo-3.0-generate-preview",
      "generate_audio": true
    }
  }
}
```

**Response (Success)**:

```json
{
  "jsonrpc": "2.0",
  "id": 4,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Video generation started successfully!\n\nJob ID: abc123-def456-ghi789\nStatus: queued\n\nUse check_job_status with this job_id to monitor progress."
      }
    ],
    "isError": false
  }
}
```

**Response (Error)**:

```json
{
  "jsonrpc": "2.0",
  "id": 4,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Error: Invalid duration. Must be between 1 and 60 seconds."
      }
    ],
    "isError": true
  }
}
```

**Response Fields**:

- `content` (array): Response content
  - `type` (string): Content type ("text", "image", "resource")
  - `text` (string): Text content
- `isError` (boolean): Whether the operation failed

---

### 6. resources/list

**Description**: Lists all available resources (job status resources).

**Method**: `resources/list`

**Parameters**: None (empty object)

**Request Example**:

```json
{
  "jsonrpc": "2.0",
  "id": 5,
  "method": "resources/list",
  "params": {}
}
```

**Response**:

```json
{
  "jsonrpc": "2.0",
  "id": 5,
  "result": {
    "resources": [
      {
        "uri": "job://abc123-def456-ghi789",
        "name": "Job abc123-def456-ghi789",
        "description": "Status and results for job abc123-def456-ghi789",
        "mimeType": "application/json"
      }
    ]
  }
}
```

**Response Fields**:

- `resources` (array): List of available resources
  - `uri` (string): Resource URI (format: `job://{job_id}`)
  - `name` (string): Human-readable name
  - `description` (string): Resource description
  - `mimeType` (string): Content type

---

### 7. resources/read

**Description**: Reads the content of a specific resource.

**Method**: `resources/read`

**Parameters**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `uri` | string | Yes | Resource URI (e.g., "job://abc123-def456-ghi789") |

**Request Example**:

```json
{
  "jsonrpc": "2.0",
  "id": 6,
  "method": "resources/read",
  "params": {
    "uri": "job://abc123-def456-ghi789"
  }
}
```

**Response**:

```json
{
  "jsonrpc": "2.0",
  "id": 6,
  "result": {
    "contents": [
      {
        "uri": "job://abc123-def456-ghi789",
        "mimeType": "application/json",
        "text": "{\"job_id\":\"abc123-def456-ghi789\",\"status\":\"completed\",\"result\":{\"video_url\":\"https://storage.googleapis.com/...\",\"thumbnail_url\":\"https://storage.googleapis.com/...\"}}"
      }
    ]
  }
}
```

**Response Fields**:

- `contents` (array): Resource contents
  - `uri` (string): Resource URI
  - `mimeType` (string): Content type
  - `text` (string): JSON-encoded job status and results

**Job Status Object**:

```json
{
  "job_id": "abc123-def456-ghi789",
  "status": "completed",
  "progress": 100,
  "result": {
    "video_url": "https://storage.googleapis.com/...",
    "thumbnail_url": "https://storage.googleapis.com/...",
    "duration": 10.5,
    "format": "mp4"
  }
}
```

**Status Values**:

- `queued` - Job is waiting in queue
- `processing` - Job is being processed
- `completed` - Job finished successfully
- `failed` - Job failed (check `error` field)

---

### 8. prompts/list

**Description**: Lists all available prompt templates.

**Method**: `prompts/list`

**Parameters**: None (empty object)

**Request Example**:

```json
{
  "jsonrpc": "2.0",
  "id": 7,
  "method": "prompts/list",
  "params": {}
}
```

**Response**:

```json
{
  "jsonrpc": "2.0",
  "id": 7,
  "result": {
    "prompts": [
      {
        "name": "video_generation",
        "description": "Template for generating video content with Google Veo",
        "arguments": [
          {
            "name": "topic",
            "description": "The topic or subject for the video",
            "required": true
          },
          {
            "name": "style",
            "description": "Visual style (e.g., cinematic, documentary, artistic)",
            "required": false
          }
        ]
      },
      {
        "name": "podcast_generation",
        "description": "Template for generating podcast/audio content",
        "arguments": [
          {
            "name": "topic",
            "description": "The podcast topic",
            "required": true
          },
          {
            "name": "tone",
            "description": "Podcast tone (e.g., casual, professional, humorous)",
            "required": false
          }
        ]
      },
      {
        "name": "style_analysis",
        "description": "Template for analyzing writing/speaking styles",
        "arguments": [
          {
            "name": "person",
            "description": "Person whose style to analyze",
            "required": true
          }
        ]
      }
    ]
  }
}
```

**Response Fields**:

- `prompts` (array): List of available prompts
  - `name` (string): Prompt identifier
  - `description` (string): Human-readable description
  - `arguments` (array): Prompt arguments
    - `name` (string): Argument name
    - `description` (string): Argument description
    - `required` (boolean): Whether argument is required

---

### 9. prompts/get

**Description**: Retrieves a prompt template with specified arguments filled in.

**Method**: `prompts/get`

**Parameters**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Prompt name |
| `arguments` | object | No | Prompt arguments (key-value pairs) |

**Request Example**:

```json
{
  "jsonrpc": "2.0",
  "id": 8,
  "method": "prompts/get",
  "params": {
    "name": "video_generation",
    "arguments": {
      "topic": "ocean waves at sunset",
      "style": "cinematic"
    }
  }
}
```

**Response**:

```json
{
  "jsonrpc": "2.0",
  "id": 8,
  "result": {
    "description": "Video generation prompt for: ocean waves at sunset",
    "messages": [
      {
        "role": "user",
        "content": {
          "type": "text",
          "text": "Generate a cinematic video showing ocean waves at sunset. Duration: 10 seconds. Aspect ratio: 16:9."
        }
      }
    ]
  }
}
```

**Response Fields**:

- `description` (string): Prompt description
- `messages` (array): Formatted prompt messages
  - `role` (string): Message role ("user" or "assistant")
  - `content` (object): Message content
    - `type` (string): Content type ("text")
    - `text` (string): Prompt text

---

## Tools Interface

### Tool: generate_video

**Description**: Generates a video using Google Veo models based on text prompt.

**Parameters**:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `prompt` | string | Yes | - | Text description of video to generate |
| `duration` | integer | No | 10 | Duration in seconds (1-60) |
| `aspect_ratio` | string | No | "16:9" | Aspect ratio: "16:9", "9:16", or "1:1" |
| `model` | string | No | "veo-3.0-generate-preview" | Veo model to use |
| `generate_audio` | boolean | No | true | Whether to generate audio |
| `credentials` | object | No | - | Override server credentials |

**Model Options**:

- `veo-3.0-generate-preview` - Latest Veo 3.0 (best quality)
- `veo-2.0-generate-001` - Veo 2.0
- `veo-1.0-generate-001` - Veo 1.0

**Example Call**:

```json
{
  "jsonrpc": "2.0",
  "id": 10,
  "method": "tools/call",
  "params": {
    "name": "generate_video",
    "arguments": {
      "prompt": "A red panda eating bamboo in a misty forest",
      "duration": 15,
      "aspect_ratio": "16:9",
      "model": "veo-3.0-generate-preview",
      "generate_audio": true
    }
  }
}
```

**Success Response**:

```json
{
  "jsonrpc": "2.0",
  "id": 10,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Video generation started successfully!\n\nJob ID: vid-2024-abc123\nStatus: queued\nModel: veo-3.0-generate-preview\nDuration: 15 seconds\nAspect Ratio: 16:9\n\nUse check_job_status with job_id 'vid-2024-abc123' to monitor progress."
      }
    ],
    "isError": false
  }
}
```

**Constraints**:

- Prompt: 1-1000 characters
- Duration: 1-60 seconds
- Aspect ratio: Must be "16:9", "9:16", or "1:1"
- Processing time: 2-10 minutes depending on duration

---

### Tool: generate_audio

**Description**: Generates audio/podcast content using AI text-to-speech.

**Parameters**:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `prompt` | string | Yes | - | Prompt for audio generation |
| `format` | string | No | "mp3" | Audio format: "mp3", "wav", "m4a" |
| `max_duration` | integer | No | 300 | Maximum duration in seconds |
| `generate_thumbnail` | boolean | No | true | Generate thumbnail image |
| `credentials` | object | No | - | Override server credentials |

**Example Call**:

```json
{
  "jsonrpc": "2.0",
  "id": 11,
  "method": "tools/call",
  "params": {
    "name": "generate_audio",
    "arguments": {
      "prompt": "Create a 60-second podcast intro about artificial intelligence and its impact on society",
      "format": "mp3",
      "max_duration": 60,
      "generate_thumbnail": true
    }
  }
}
```

**Success Response**:

```json
{
  "jsonrpc": "2.0",
  "id": 11,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Audio generation completed!\n\nJob ID: aud-2024-xyz789\nAudio URL: https://storage.googleapis.com/bucket/audio.mp3\nThumbnail URL: https://storage.googleapis.com/bucket/thumb.jpg\nDuration: 58.3 seconds\nFormat: mp3"
      }
    ],
    "isError": false
  }
}
```

**Notes**:

- Uses ElevenLabs text-to-speech
- Supports multiple voices and accents
- Can incorporate analyzed styles (from analyze_writing_style)
- Processing time: 10-60 seconds

---

### Tool: analyze_writing_style

**Description**: Analyzes writing/speaking style for use in audio generation.

**Parameters**:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `style_description` | string | Yes | - | Description of style to analyze (e.g., person's name) |
| `credentials` | object | No | - | Override server credentials |

**Example Call**:

```json
{
  "jsonrpc": "2.0",
  "id": 12,
  "method": "tools/call",
  "params": {
    "name": "analyze_writing_style",
    "arguments": {
      "style_description": "Elon Musk"
    }
  }
}
```

**Success Response**:

```json
{
  "jsonrpc": "2.0",
  "id": 12,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Style Analysis: Elon Musk\n\nKey Characteristics:\n- Direct, informal communication\n- Technical precision with simplified explanations\n- Frequent use of first principles thinking\n- Optimistic about technology\n- Casual humor and meme references\n\nVocabulary:\n- Engineering terms\n- Physics concepts\n- Future-oriented language\n\nSpeaking Patterns:\n- Short, punchy sentences\n- Occasional pauses for thought\n- Technical details mixed with accessibility"
      }
    ],
    "isError": false
  }
}
```

**Use Case**:

The analysis result can be used to inform the `generate_audio` prompt for creating content in a specific style.

---

### Tool: check_job_status

**Description**: Checks the status and retrieves results of a generation job.

**Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `job_id` | string | Yes | Job ID from generate_video or generate_audio |

**Example Call**:

```json
{
  "jsonrpc": "2.0",
  "id": 13,
  "method": "tools/call",
  "params": {
    "name": "check_job_status",
    "arguments": {
      "job_id": "vid-2024-abc123"
    }
  }
}
```

**Response (Queued)**:

```json
{
  "jsonrpc": "2.0",
  "id": 13,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Job Status: vid-2024-abc123\n\nStatus: queued\nProgress: 0%\n\nYour job is waiting in the queue."
      }
    ],
    "isError": false
  }
}
```

**Response (Processing)**:

```json
{
  "jsonrpc": "2.0",
  "id": 13,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Job Status: vid-2024-abc123\n\nStatus: processing\nProgress: 45%\n\nCurrent stage: Generating video frames"
      }
    ],
    "isError": false
  }
}
```

**Response (Completed)**:

```json
{
  "jsonrpc": "2.0",
  "id": 13,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Job Status: vid-2024-abc123\n\nStatus: completed\nProgress: 100%\n\nResults:\nVideo URL: https://storage.googleapis.com/bucket/video.mp4\nThumbnail URL: https://storage.googleapis.com/bucket/thumb.jpg\nDuration: 15.2 seconds\nResolution: 1920x1080\nFormat: mp4"
      }
    ],
    "isError": false
  }
}
```

**Response (Failed)**:

```json
{
  "jsonrpc": "2.0",
  "id": 13,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Job Status: vid-2024-abc123\n\nStatus: failed\n\nError: Insufficient quota for video generation. Please check your Google Cloud quota."
      }
    ],
    "isError": true
  }
}
```

---

## Resources Interface

### Resource URI Format

```
job://{job_id}
```

### Resource Schema

When reading a job resource, the content is a JSON object:

```json
{
  "job_id": "vid-2024-abc123",
  "status": "completed",
  "progress": 100,
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:35:42Z",
  "type": "video",
  "parameters": {
    "prompt": "A red panda eating bamboo",
    "duration": 15,
    "aspect_ratio": "16:9",
    "model": "veo-3.0-generate-preview"
  },
  "result": {
    "video_url": "https://storage.googleapis.com/bucket/video.mp4",
    "thumbnail_url": "https://storage.googleapis.com/bucket/thumb.jpg",
    "duration": 15.2,
    "resolution": "1920x1080",
    "format": "mp4",
    "size_bytes": 24567890
  }
}
```

### Status Lifecycle

```
queued → processing → completed
                   ↓
                 failed
```

### Example: Read Job Resource

```json
{
  "jsonrpc": "2.0",
  "id": 14,
  "method": "resources/read",
  "params": {
    "uri": "job://vid-2024-abc123"
  }
}
```

Response provides full job details as JSON.

---

## Prompts Interface

### Available Prompts

#### 1. video_generation

**Description**: Template for video generation with Google Veo.

**Arguments**:

- `topic` (required): Video topic/subject
- `style` (optional): Visual style (cinematic, documentary, artistic, etc.)
- `duration` (optional): Duration in seconds
- `aspect_ratio` (optional): Aspect ratio

**Example**:

```json
{
  "jsonrpc": "2.0",
  "id": 15,
  "method": "prompts/get",
  "params": {
    "name": "video_generation",
    "arguments": {
      "topic": "Northern lights over snowy mountains",
      "style": "cinematic",
      "duration": "20",
      "aspect_ratio": "16:9"
    }
  }
}
```

#### 2. podcast_generation

**Description**: Template for podcast/audio generation.

**Arguments**:

- `topic` (required): Podcast topic
- `tone` (optional): Tone (casual, professional, humorous, etc.)
- `duration` (optional): Target duration

**Example**:

```json
{
  "jsonrpc": "2.0",
  "id": 16,
  "method": "prompts/get",
  "params": {
    "name": "podcast_generation",
    "arguments": {
      "topic": "The future of renewable energy",
      "tone": "professional",
      "duration": "60"
    }
  }
}
```

#### 3. style_analysis

**Description**: Template for analyzing communication styles.

**Arguments**:

- `person` (required): Person whose style to analyze

**Example**:

```json
{
  "jsonrpc": "2.0",
  "id": 17,
  "method": "prompts/get",
  "params": {
    "name": "style_analysis",
    "arguments": {
      "person": "David Attenborough"
    }
  }
}
```

---

## Server-Sent Events (SSE)

### Connection

**URL**: `GET /mcp-sse/{client_id}`

**Headers**:

```
X-API-Key: your-api-key-here
Accept: text/event-stream
```

**Example**:

```bash
curl -N -H "X-API-Key: your-key" \
  -H "Accept: text/event-stream" \
  https://api.c4dhi.org/mcp-sse/client-12345
```

### Event Format

SSE events follow this format:

```
event: message
data: {"type":"job_progress","job_id":"vid-123","progress":45}

event: message
data: {"type":"job_completed","job_id":"vid-123","result":{...}}
```

### Event Types

#### 1. job_progress

Sent periodically during job processing.

```json
{
  "type": "job_progress",
  "job_id": "vid-2024-abc123",
  "progress": 45,
  "stage": "Generating video frames",
  "timestamp": "2024-01-15T10:32:15Z"
}
```

#### 2. job_completed

Sent when job finishes successfully.

```json
{
  "type": "job_completed",
  "job_id": "vid-2024-abc123",
  "result": {
    "video_url": "https://storage.googleapis.com/...",
    "thumbnail_url": "https://storage.googleapis.com/...",
    "duration": 15.2,
    "format": "mp4"
  },
  "timestamp": "2024-01-15T10:35:42Z"
}
```

#### 3. job_failed

Sent when job fails.

```json
{
  "type": "job_failed",
  "job_id": "vid-2024-abc123",
  "error": "Insufficient quota",
  "details": "Google Cloud quota exceeded",
  "timestamp": "2024-01-15T10:35:42Z"
}
```

#### 4. capability_changed

Sent when server capabilities change.

```json
{
  "type": "capability_changed",
  "capabilities": {
    "tools": {},
    "resources": {},
    "prompts": {}
  },
  "timestamp": "2024-01-15T10:30:00Z"
}
```

#### 5. ping

Keep-alive message sent every 30 seconds.

```
event: ping
data: {"type":"ping","timestamp":"2024-01-15T10:30:00Z"}
```

### Client Implementation

```python
import requests
import json

headers = {'X-API-Key': 'your-key'}
response = requests.get(
    'https://api.c4dhi.org/mcp-sse/client-12345',
    headers=headers,
    stream=True
)

for line in response.iter_lines():
    if line:
        line = line.decode('utf-8')
        if line.startswith('data: '):
            data = json.loads(line[6:])
            print(f"Event: {data.get('type')}")
```

---

## Error Codes

### Standard JSON-RPC 2.0 Errors

| Code | Message | Description |
|------|---------|-------------|
| -32700 | Parse error | Invalid JSON |
| -32600 | Invalid Request | JSON-RPC request is invalid |
| -32601 | Method not found | Method does not exist |
| -32602 | Invalid params | Invalid method parameters |
| -32603 | Internal error | Internal JSON-RPC error |

### MCP-Specific Errors

| Code | Message | Description |
|------|---------|-------------|
| -32000 | Server error | Generic server error |
| -32001 | Tool not found | Requested tool does not exist |
| -32002 | Resource not found | Requested resource does not exist |
| -32003 | Prompt not found | Requested prompt does not exist |

### Application Errors

| Code | Message | Description |
|------|---------|-------------|
| -32100 | Authentication failed | Invalid API key |
| -32101 | Invalid credentials | Invalid Google Cloud or ElevenLabs credentials |
| -32102 | Quota exceeded | API quota exceeded |
| -32103 | Job not found | Job ID does not exist |
| -32104 | Invalid parameter | Parameter validation failed |

### Error Response Example

```json
{
  "jsonrpc": "2.0",
  "id": 10,
  "error": {
    "code": -32104,
    "message": "Invalid parameter",
    "data": {
      "parameter": "duration",
      "value": 120,
      "constraint": "Must be between 1 and 60",
      "details": "Video duration of 120 seconds exceeds maximum allowed duration"
    }
  }
}
```

---

## Client Implementation Examples

### Python Client

```python
import requests
import json
import time

class MCPClient:
    def __init__(self, base_url, api_key):
        self.base_url = base_url
        self.api_key = api_key
        self.request_id = 0
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'X-API-Key': api_key
        })

    def _call(self, method, params=None):
        self.request_id += 1
        request = {
            'jsonrpc': '2.0',
            'id': self.request_id,
            'method': method,
            'params': params or {}
        }

        response = self.session.post(
            f'{self.base_url}/mcp-rpc',
            json=request,
            timeout=300
        )
        response.raise_for_status()

        data = response.json()
        if 'error' in data:
            raise Exception(f"RPC Error: {data['error']}")
        return data.get('result')

    def initialize(self):
        """Initialize MCP connection"""
        return self._call('initialize', {
            'protocolVersion': '2025-06-18',
            'capabilities': {},
            'clientInfo': {
                'name': 'python-mcp-client',
                'version': '1.0.0'
            }
        })

    def list_tools(self):
        """List available tools"""
        return self._call('tools/list')

    def generate_video(self, prompt, duration=10, aspect_ratio='16:9'):
        """Generate a video"""
        return self._call('tools/call', {
            'name': 'generate_video',
            'arguments': {
                'prompt': prompt,
                'duration': duration,
                'aspect_ratio': aspect_ratio
            }
        })

    def generate_audio(self, prompt, format='mp3'):
        """Generate audio/podcast"""
        return self._call('tools/call', {
            'name': 'generate_audio',
            'arguments': {
                'prompt': prompt,
                'format': format
            }
        })

    def check_job_status(self, job_id):
        """Check job status"""
        return self._call('tools/call', {
            'name': 'check_job_status',
            'arguments': {
                'job_id': job_id
            }
        })

    def wait_for_job(self, job_id, poll_interval=5):
        """Wait for job to complete"""
        while True:
            result = self.check_job_status(job_id)
            content = result['content'][0]['text']

            if 'completed' in content.lower():
                return result
            elif 'failed' in content.lower():
                raise Exception(f"Job failed: {content}")

            print(f"Job {job_id} still processing...")
            time.sleep(poll_interval)

# Usage
client = MCPClient('https://api.c4dhi.org', 'your-api-key')

# Initialize
client.initialize()

# Generate video
result = client.generate_video(
    prompt='A sunset over the ocean',
    duration=10
)
print(result)

# Extract job_id and wait
job_id = 'vid-2024-abc123'  # Extract from result
final_result = client.wait_for_job(job_id)
print(final_result)
```

### JavaScript/TypeScript Client

```javascript
class MCPClient {
  constructor(baseUrl, apiKey) {
    this.baseUrl = baseUrl;
    this.apiKey = apiKey;
    this.requestId = 0;
  }

  async call(method, params = {}) {
    this.requestId++;
    const request = {
      jsonrpc: '2.0',
      id: this.requestId,
      method,
      params
    };

    const response = await fetch(`${this.baseUrl}/mcp-rpc`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': this.apiKey
      },
      body: JSON.stringify(request)
    });

    const data = await response.json();

    if (data.error) {
      throw new Error(`RPC Error: ${JSON.stringify(data.error)}`);
    }

    return data.result;
  }

  async initialize() {
    return this.call('initialize', {
      protocolVersion: '2025-06-18',
      capabilities: {},
      clientInfo: {
        name: 'js-mcp-client',
        version: '1.0.0'
      }
    });
  }

  async listTools() {
    return this.call('tools/list');
  }

  async generateVideo(prompt, options = {}) {
    return this.call('tools/call', {
      name: 'generate_video',
      arguments: {
        prompt,
        duration: options.duration || 10,
        aspect_ratio: options.aspectRatio || '16:9',
        model: options.model || 'veo-3.0-generate-preview'
      }
    });
  }

  async generateAudio(prompt, options = {}) {
    return this.call('tools/call', {
      name: 'generate_audio',
      arguments: {
        prompt,
        format: options.format || 'mp3',
        max_duration: options.maxDuration || 300
      }
    });
  }

  async checkJobStatus(jobId) {
    return this.call('tools/call', {
      name: 'check_job_status',
      arguments: { job_id: jobId }
    });
  }

  async waitForJob(jobId, pollInterval = 5000) {
    while (true) {
      const result = await this.checkJobStatus(jobId);
      const content = result.content[0].text;

      if (content.toLowerCase().includes('completed')) {
        return result;
      } else if (content.toLowerCase().includes('failed')) {
        throw new Error(`Job failed: ${content}`);
      }

      console.log(`Job ${jobId} still processing...`);
      await new Promise(resolve => setTimeout(resolve, pollInterval));
    }
  }
}

// Usage
const client = new MCPClient('https://api.c4dhi.org', 'your-api-key');

async function main() {
  // Initialize
  await client.initialize();

  // Generate video
  const result = await client.generateVideo(
    'A sunset over the ocean',
    { duration: 10, aspectRatio: '16:9' }
  );
  console.log(result);

  // Extract job_id and wait
  const jobId = 'vid-2024-abc123'; // Extract from result
  const finalResult = await client.waitForJob(jobId);
  console.log(finalResult);
}

main().catch(console.error);
```

### cURL Examples

#### Initialize Connection

```bash
curl -X POST https://api.c4dhi.org/mcp-rpc \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
      "protocolVersion": "2025-06-18",
      "capabilities": {},
      "clientInfo": {
        "name": "curl-client",
        "version": "1.0.0"
      }
    }
  }'
```

#### List Tools

```bash
curl -X POST https://api.c4dhi.org/mcp-rpc \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/list",
    "params": {}
  }'
```

#### Generate Video

```bash
curl -X POST https://api.c4dhi.org/mcp-rpc \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {
      "name": "generate_video",
      "arguments": {
        "prompt": "A serene mountain landscape at sunrise",
        "duration": 15,
        "aspect_ratio": "16:9",
        "model": "veo-3.0-generate-preview"
      }
    }
  }'
```

#### Check Job Status

```bash
curl -X POST https://api.c4dhi.org/mcp-rpc \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "jsonrpc": "2.0",
    "id": 4,
    "method": "tools/call",
    "params": {
      "name": "check_job_status",
      "arguments": {
        "job_id": "vid-2024-abc123"
      }
    }
  }'
```

#### Read Resource

```bash
curl -X POST https://api.c4dhi.org/mcp-rpc \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "jsonrpc": "2.0",
    "id": 5,
    "method": "resources/read",
    "params": {
      "uri": "job://vid-2024-abc123"
    }
  }'
```

#### SSE Connection

```bash
curl -N -H "X-API-Key: your-api-key" \
  -H "Accept: text/event-stream" \
  https://api.c4dhi.org/mcp-sse/my-client-id
```

---

## Complete Workflow Example

### 1. Initialize Connection

```json
POST /mcp-rpc
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {
    "protocolVersion": "2025-06-18",
    "capabilities": {},
    "clientInfo": {"name": "my-client", "version": "1.0"}
  }
}
```

### 2. List Available Tools

```json
POST /mcp-rpc
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/list",
  "params": {}
}
```

### 3. Generate Video

```json
POST /mcp-rpc
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "generate_video",
    "arguments": {
      "prompt": "Ocean waves crashing on rocky shore at sunset",
      "duration": 20,
      "aspect_ratio": "16:9"
    }
  }
}
```

Response includes `job_id`: `"vid-2024-xyz789"`

### 4. Monitor Progress (Option A: Polling)

```json
POST /mcp-rpc
{
  "jsonrpc": "2.0",
  "id": 4,
  "method": "tools/call",
  "params": {
    "name": "check_job_status",
    "arguments": {"job_id": "vid-2024-xyz789"}
  }
}
```

Repeat every 5-10 seconds until status is "completed"

### 5. Monitor Progress (Option B: SSE)

```bash
GET /mcp-sse/my-client-id
```

Listen for `job_completed` event

### 6. Retrieve Final Results

```json
POST /mcp-rpc
{
  "jsonrpc": "2.0",
  "id": 5,
  "method": "resources/read",
  "params": {
    "uri": "job://vid-2024-xyz789"
  }
}
```

Returns full job details with video URL

---

## Best Practices

### 1. Connection Management

- Call `initialize` once at the start of each session
- Reuse the same HTTP client/session for multiple requests
- Implement exponential backoff for retries

### 2. Job Monitoring

- Use SSE for real-time updates when possible
- If polling, wait at least 5 seconds between checks
- Handle long-running jobs gracefully (video generation can take 2-10 minutes)

### 3. Error Handling

- Always check for `error` field in responses
- Implement retry logic for transient errors (-32603, -32000)
- Log full error objects for debugging

### 4. Credentials

- Use server-side credentials when possible (more secure)
- Only pass per-request credentials when necessary
- Never log or expose credentials in error messages

### 5. Resource Management

- Clean up old job resources periodically
- Cache resource reads when appropriate
- Use pagination for large resource lists

### 6. Rate Limiting

- Respect server rate limits (if implemented)
- Implement client-side throttling for bulk operations
- Monitor quota usage for Google Cloud APIs

---

## Additional Resources

- **MCP_IMPLEMENTATION.md** - Implementation details and architecture
- **CLIENT_API_GUIDE.md** - REST API alternative
- **README.md** - Setup and deployment guide
- **CLAUDE_DESKTOP_SETUP.md** - Claude Desktop integration

---

## Appendix: Complete Type Definitions

### TypeScript Types

```typescript
// JSON-RPC Base Types
interface JSONRPCRequest {
  jsonrpc: '2.0';
  id: string | number;
  method: string;
  params?: object;
}

interface JSONRPCResponse {
  jsonrpc: '2.0';
  id: string | number;
  result?: any;
  error?: JSONRPCError;
}

interface JSONRPCError {
  code: number;
  message: string;
  data?: any;
}

// MCP Types
interface MCPInitializeParams {
  protocolVersion: string;
  capabilities: object;
  clientInfo: {
    name: string;
    version: string;
  };
}

interface MCPInitializeResult {
  protocolVersion: string;
  capabilities: {
    tools?: object;
    resources?: object;
    prompts?: object;
  };
  serverInfo: {
    name: string;
    version: string;
  };
}

interface MCPTool {
  name: string;
  description: string;
  inputSchema: object; // JSON Schema
}

interface MCPResource {
  uri: string;
  name: string;
  description: string;
  mimeType: string;
}

interface MCPPrompt {
  name: string;
  description: string;
  arguments: Array<{
    name: string;
    description: string;
    required: boolean;
  }>;
}

// Tool-Specific Types
interface GenerateVideoArgs {
  prompt: string;
  duration?: number;
  aspect_ratio?: '16:9' | '9:16' | '1:1';
  model?: 'veo-3.0-generate-preview' | 'veo-2.0-generate-001' | 'veo-1.0-generate-001';
  generate_audio?: boolean;
  credentials?: Credentials;
}

interface GenerateAudioArgs {
  prompt: string;
  format?: 'mp3' | 'wav' | 'm4a';
  max_duration?: number;
  generate_thumbnail?: boolean;
  credentials?: Credentials;
}

interface AnalyzeStyleArgs {
  style_description: string;
  credentials?: Credentials;
}

interface CheckJobStatusArgs {
  job_id: string;
}

interface Credentials {
  gemini_api_key?: string;
  google_cloud_credentials?: object;
  google_cloud_project?: string;
  vertex_ai_region?: string;
  gcs_bucket?: string;
  elevenlabs_api_key?: string;
}

// Job Types
interface JobStatus {
  job_id: string;
  status: 'queued' | 'processing' | 'completed' | 'failed';
  progress: number;
  created_at: string;
  updated_at: string;
  type: 'video' | 'audio';
  parameters: object;
  result?: {
    video_url?: string;
    audio_url?: string;
    thumbnail_url?: string;
    duration?: number;
    format?: string;
    resolution?: string;
    size_bytes?: number;
  };
  error?: string;
}
```

---

**Document Version**: 1.0

**Last Updated**: 2024-01-15

**Server Base URL**: https://api.c4dhi.org

**Support**: See main README.md for troubleshooting and support information
