# MCP Summer School Service - Updated API Interface Documentation

## Overview
A REST API service for video and audio generation with real-time progress tracking via WebSockets. **Now supports user-provided API keys and credentials on a per-request basis.**

## Base URL
Configure your client to point to the service endpoint (deployment-specific).

## Health Check

### System Status
**Endpoint**: `GET /health`

**Response (Healthy)**:
```json
{
  "status": "healthy",
  "timestamp": "2025-01-20T12:00:00Z",
  "uptime": 12345.67,
  "service": "MCP Video/Audio Generator",
  "version": "1.0.0",
  "components": {
    "redis": {
      "status": "healthy",
      "message": "Redis connection successful"
    },
    "queue": {
      "status": "healthy",
      "message": "Queue accessible",
      "jobs_queued": 3,
      "jobs_failed": 0
    },
    "storage": {
      "status": "configured",
      "message": "GCS bucket configured: my-bucket"
    },
    "websocket": {
      "status": "healthy",
      "message": "WebSocket manager operational",
      "active_connections": 5
    }
  }
}
```

**Response (Degraded - HTTP 503)**:
```json
{
  "status": "degraded",
  "components": {
    "redis": {
      "status": "unhealthy",
      "message": "Redis connection failed: Connection refused"
    }
  }
}
```

### Service Info
**Endpoint**: `GET /`

**Response**:
```json
{
  "service": "MCP Video/Audio Generator",
  "status": "running",
  "version": "1.0.0",
  "endpoints": {
    "health": "/health",
    "create_job": "/mcp",
    "check_job": "/mcp/{job_id}",
    "websocket": "/ws/{job_id}",
    "docs": "/docs"
  }
}
```

## Authentication Options
- **Environment Variables**: Service uses pre-configured credentials (original behavior)
- **User Credentials**: Pass your own API keys in each request (new feature)

## Request/Response Flow

### 1. Submit Generation Job
**Endpoint**: `POST /mcp`  
**Content-Type**: `application/json`

**Request Body**:
```json
{
  "mode": "video|audio",           // REQUIRED
  "prompt": "string",              // REQUIRED: Generation prompt
  "generate_thumbnail": false,     // OPTIONAL: Generate podcast thumbnail (audio mode only)
  "thumbnail_prompt": "string",    // OPTIONAL: Custom prompt for thumbnail generation (audio mode only)
  "credentials": {                 // OPTIONAL: Your own API keys
    "gemini_api_key": "AIza...",
    "google_cloud_credentials": {...}, // Service account JSON as object
    "google_cloud_project": "my-project-id",
    "vertex_ai_region": "us-central1",
    "gcs_bucket": "my-bucket-name",
    "elevenlabs_api_key": "sk_..."
  },
  "image": {                       // OPTIONAL: Input image for video
    "bytesBase64Encoded": "string",
    "gcsUri": "string", 
    "mimeType": "string"
  },
  "lastFrame": {                   // OPTIONAL: Last frame for video continuation
    "bytesBase64Encoded": "string",
    "gcsUri": "string",
    "mimeType": "string"
  },
  "video": {                       // OPTIONAL: Input video for transformation
    "bytesBase64Encoded": "string",
    "gcsUri": "string",
    "mimeType": "string"
  },
  "parameters": {                  // OPTIONAL: Video generation settings
    "model": "veo-3.0-generate-preview", // Video generation model
    "aspectRatio": "16:9",         // Default: "16:9" (16:9, 9:16, 1:1, 4:3, 3:4)
    "durationSeconds": 8,          // Default: 8 seconds (1-60)
    "enhancePrompt": true,         // Default: true
    "generateAudio": true,         // Default: true
    "negativePrompt": "string",
    "personGeneration": "allow_all",
    "resolution": "string",
    "sampleCount": 1,              // Default: 1 (1-4)
    "seed": 12345,
    "storageUri": "gs://bucket/path"
  }
}
```

**Response**:
```json
{
  "job_id": "uuid-string",
  "status": "queued",
  "progress": 0,
  "current_step": "Job queued, waiting to start",
  "total_steps": 5,               // 3 for video, 4 for audio, 5 for audio with thumbnail
  "step_number": 0
}
```

**Error Response (400 Bad Request)**:
```json
{
  "detail": "Invalid credentials: [specific error message]"
}
```

**Possible validation errors**:
- Invalid credentials
- Unsupported video model
- Invalid duration (must be 1-60 seconds)
- Invalid aspect ratio
- Invalid sample count (must be 1-4)
```

### 2. Check Job Status
**Endpoint**: `GET /mcp/{job_id}`

**Response**:
```json
{
  "job_id": "uuid-string",
  "status": "queued|started|finished|failed|not_found",
  "download_url": "https://...",   // Available when finished
  "thumbnail_url": "https://...",  // Available for audio with thumbnail generation
  "progress": 85,                  // 0-100
  "current_step": "Processing step description",
  "total_steps": 5,                // Varies by mode and options
  "step_number": 3,
  "operation_name": "projects/..."  // For manual tracking (video only)
}
```

### 3. Long-Polling Status Check
**Endpoint**: `GET /mcp/{job_id}/wait`

Waits up to 5 minutes for completion. Same response format as status check.

### 4. Operation Status (Video Only)
**Endpoint**: `GET /operation/{operation_name}`

**Note**: Currently uses environment credentials only. User credentials not supported yet.

**Response**:
```json
{
  "operation_name": "string",
  "done": true,
  "status": "completed|running|failed",
  "video_url": "https://...",      // Public download URL
  "download_ready": true,
  "error": "error message"         // If failed
}
```

## WebSocket Real-Time Updates

**Endpoint**: `WebSocket /ws/{job_id}`

**Message Format**:
```json
{
  "job_id": "uuid-string",
  "progress": 75,
  "current_step": "Converting text to speech",
  "step_number": 3,
  "total_steps": 4,
  "status": "started"
}
```

## Credentials Configuration

### Required for Video Generation:
- `gemini_api_key`: Google Gemini API key for script generation (if audio mode)
- `google_cloud_credentials`: Service account JSON object with Cloud Storage and Vertex AI permissions
- `google_cloud_project`: Your Google Cloud project ID
- `vertex_ai_region`: Vertex AI region (default: "us-central1")
- `gcs_bucket`: Google Cloud Storage bucket name for file storage

### Required for Audio Generation:
- `gemini_api_key`: Google Gemini API key for script generation
- `google_cloud_credentials`: Service account JSON object with Cloud Storage permissions  
- `gcs_bucket`: Google Cloud Storage bucket name for file storage
- `elevenlabs_api_key`: ElevenLabs API key for text-to-speech

### Service Account Permissions:
Your Google Cloud service account needs these IAM roles:
- `roles/storage.admin` (or `roles/storage.objectCreator` + `roles/storage.objectViewer`)
- `roles/aiplatform.user` (for video generation)

### Fallback Behavior:
If credentials are not provided in the request, the service falls back to environment variables:
- `GEMINI_API_KEY`
- `GOOGLE_CLOUD_CREDENTIALS_PATH` 
- `GOOGLE_CLOUD_PROJECT`
- `VERTEX_AI_REGION`
- `GCS_BUCKET`
- `XI_KEY`

## Status Values

- `queued`: Job submitted, waiting to process
- `started`: Processing in progress  
- `finished`: Complete, download_url available
- `failed`: Error occurred
- `not_found`: Invalid job_id

## Supported Video Models

The following video generation models are supported:
- `veo-3.0-generate-preview` (default) - Latest Veo 3.0 model
- `veo-2.0-generate-preview` - Veo 2.0 model
- `veo-1.0-generate-preview` - Original Veo model
- `imagen-3.0-generate-001` - Imagen 3.0 model
- `imagen-3.0-fast-generate-001` - Fast Imagen 3.0 model

## Video Parameters Validation

- **Duration**: 1-60 seconds
- **Aspect Ratio**: 16:9, 9:16, 1:1, 4:3, 3:4
- **Sample Count**: 1-4 videos per request
- **Model**: Must be from supported models list

## Progress Tracking

### Video Generation Steps (3 total):
1. Initialize authentication (10%)
2. Submit to Google Cloud (50%) 
3. Monitor operation (60%+)

### Audio Generation Steps (4 total):
1. Generate script (10%)
2. Initialize text-to-speech (30%)
3. Convert to audio (60%)
4. Upload to storage (90%)

### Audio with Thumbnail Steps (5 total):
1. Generate script (10%)
2. Initialize text-to-speech (30%)
3. Convert to audio (60%)
4. Generate thumbnail (70%)
5. Upload files to storage (90%)

## Security Features

- **Credential Validation**: API keys are validated before job submission
- **Automatic Cleanup**: Sensitive credentials are automatically cleared from job metadata upon completion or failure
- **No Logging**: Credentials are not logged or persisted beyond job execution
- **Secure Storage**: Generated files are stored in your specified GCS bucket with public URLs

## Error Handling

All endpoints return standard HTTP status codes:
- `200`: Success
- `400`: Bad request (invalid credentials or parameters)
- `404`: Job not found
- `500`: Internal server error

Error responses include descriptive messages in the response body.

## Usage Patterns

### With User Credentials
```
1. POST /mcp with credentials → get job_id  
2. WebSocket /ws/{job_id} for real-time updates
3. GET /mcp/{job_id} for final download_url
```

### With Environment Credentials (Legacy)
```
1. POST /mcp without credentials → get job_id
2. Repeatedly GET /mcp/{job_id} until status == "finished"
3. Use download_url from final response
```

## Download URLs

- **Audio Files**: All `download_url` values are publicly accessible HTTPS URLs for MP3 files
- **Podcast Thumbnails**: When `generate_thumbnail: true`, `thumbnail_url` contains a public PNG image URL
- **Video Files**: `download_url` contains publicly accessible video file URLs
- No additional authentication required for downloading

## Migration Notes

- **Backward Compatibility**: Existing clients continue to work without modification
- **Optional Credentials**: The `credentials` field is completely optional
- **Gradual Migration**: You can migrate to user credentials one request at a time
- **No Breaking Changes**: All existing API endpoints and response formats remain unchanged

## Usage Examples

### Video Generation with Custom Model
```json
{
  "mode": "video",
  "prompt": "A cat playing with a ball of yarn",
  "parameters": {
    "model": "veo-2.0-generate-preview",
    "durationSeconds": 15,
    "aspectRatio": "9:16",
    "generateAudio": true
  }
}
```

### Podcast Generation with Thumbnail
```json
{
  "mode": "audio",
  "prompt": "Create a podcast about artificial intelligence trends in 2024",
  "generate_thumbnail": true,
  "thumbnail_prompt": "Professional AI-themed podcast cover with futuristic design, neural networks, and '2024 AI Trends' text",
  "credentials": {
    "gemini_api_key": "your-key",
    "elevenlabs_api_key": "your-key",
    "gcs_bucket": "your-bucket"
  }
}
```

### Response with Thumbnail
```json
{
  "job_id": "123e4567-e89b-12d3-a456-426614174000",
  "status": "finished",
  "download_url": "https://storage.googleapis.com/bucket/audio/file.mp3",
  "thumbnail_url": "https://storage.googleapis.com/bucket/thumbnails/thumb.png",
  "progress": 100,
  "current_step": "Complete",
  "total_steps": 5,
  "step_number": 5
}
```