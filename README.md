# MCP Summer School Service

A FastAPI-based REST API service for AI-powered video and audio generation with real-time progress tracking. Generate videos using Google's Veo models and podcasts using ElevenLabs text-to-speech with your own API credentials.

## 🎯 What This Service Does

- **🎬 Video Generation**: Create videos from text prompts using Google's Veo 3.0/2.0 models via Vertex AI
- **🎧 Audio/Podcast Generation**: Generate spoken audio content using ElevenLabs text-to-speech
- **📊 Real-time Progress**: WebSocket support for live progress updates
- **🔐 Secure**: User-provided credentials validated per request
- **☁️ Cloud Storage**: Files automatically stored in Google Cloud Storage
- **🔄 Job Queue**: Redis-based job processing for scalability

## 🚀 Quick Start

### Prerequisites

Before you begin, you'll need:

1. **Python 3.11+** installed on your system
2. **Docker and Docker Compose** (for containerized deployment)
3. **Google Cloud Account** with billing enabled
4. **API Keys** from the following services:
   - Google Cloud (Service Account JSON)
   - Google Gemini API key
   - ElevenLabs API key (for audio generation)

### Required Google Cloud Setup

1. **Create a Google Cloud Project**
2. **Enable APIs**:
   ```bash
   gcloud services enable aiplatform.googleapis.com
   gcloud services enable storage-api.googleapis.com
   ```
3. **Create a Service Account**:
   ```bash
   gcloud iam service-accounts create mcp-video-service
   ```
4. **Grant Required Permissions**:
   ```bash
   gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
     --member="serviceAccount:mcp-video-service@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
     --role="roles/aiplatform.user"
   
   gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
     --member="serviceAccount:mcp-video-service@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
     --role="roles/storage.admin"
   ```
5. **Create and Download Service Account Key**:
   ```bash
   gcloud iam service-accounts keys create service-account-key.json \
     --iam-account=mcp-video-service@YOUR_PROJECT_ID.iam.gserviceaccount.com
   ```
6. **Create a Cloud Storage Bucket**:
   ```bash
   gsutil mb gs://your-unique-bucket-name
   ```

### API Keys Setup

1. **Google Gemini API Key**:
   - Go to [Google AI Studio](https://aistudio.google.com/app/apikey)
   - Create a new API key

2. **ElevenLabs API Key** (for audio generation):
   - Sign up at [ElevenLabs](https://elevenlabs.io/)
   - Get your API key from the profile section

## 📦 Installation & Deployment

### Option 1: Docker Compose (Recommended)

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd mcp_summer_school_service
   ```

2. **Create environment file**:
   ```bash
   cp .env.example .env
   ```

3. **Configure your .env file**:
   ```env
   # Google Cloud Configuration
   GOOGLE_CLOUD_PROJECT=your-project-id
   VERTEX_AI_REGION=us-central1
   GCS_BUCKET=your-unique-bucket-name
   GOOGLE_CLOUD_CREDENTIALS_PATH=/app/service-account-key.json
   
   # API Keys (Optional - can be provided per request)
   GEMINI_API_KEY=your-gemini-api-key
   XI_KEY=your-elevenlabs-api-key
   
   # AI Model Configuration
   VEO_MODEL_ID=veo-3.0-generate-preview
   IMAGEN_MODEL_ID=imagen-3.0-fast-generate-001  # Cheapest thumbnail model at $0.02/image
   
   # Redis Configuration
   REDIS_URL=redis://redis:6379/0
   ```

4. **Place your service account key**:
   ```bash
   # Put your service-account-key.json in the project root
   cp /path/to/your/service-account-key.json ./service-account-key.json
   ```

5. **Start the services**:
   ```bash
   docker-compose up -d
   ```

6. **Verify deployment**:
   ```bash
   curl http://localhost:8000/docs
   ```

### Option 2: Local Development

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Start Redis** (required for job queue):
   ```bash
   docker run -d -p 6379:6379 redis:7-alpine
   ```

3. **Set environment variables**:
   ```bash
   export GOOGLE_CLOUD_PROJECT=your-project-id
   export GCS_BUCKET=your-bucket-name
   export GEMINI_API_KEY=your-gemini-key
   export XI_KEY=your-elevenlabs-key
   export IMAGEN_MODEL_ID=imagen-3.0-fast-generate-001  # Optional: cheapest thumbnail model
   export REDIS_URL=redis://localhost:6379/0
   ```

4. **Start the worker** (in one terminal):
   ```bash
   rq worker --url redis://localhost:6379/0
   ```

5. **Start the API server** (in another terminal):
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

## 🔧 Usage Examples

### Video Generation

```bash
curl -X POST "http://localhost:8000/mcp" \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "video",
    "prompt": "A cat playing with a ball of yarn in slow motion",
    "credentials": {
      "gemini_api_key": "your-gemini-api-key",
      "google_cloud_credentials": {...service-account-json...},
      "google_cloud_project": "your-project-id",
      "vertex_ai_region": "us-central1",
      "gcs_bucket": "your-bucket-name"
    },
    "parameters": {
      "model": "veo-3.0-generate-preview",
      "durationSeconds": 8,
      "aspectRatio": "16:9",
      "generateAudio": true
    }
  }'
```

### Audio/Podcast Generation

```bash
curl -X POST "http://localhost:8000/mcp" \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "audio",
    "prompt": "Create a 2-minute podcast about the future of artificial intelligence",
    "generate_thumbnail": true,
    "thumbnail_prompt": "Futuristic AI podcast thumbnail with robot brain, glowing circuits, and 'AI Future' text",
    "credentials": {
      "gemini_api_key": "your-gemini-api-key",
      "google_cloud_credentials": {...service-account-json...},
      "gcs_bucket": "your-bucket-name",
      "elevenlabs_api_key": "your-elevenlabs-key"
    }
  }'
```

### Check Job Status

```bash
# Get job status
curl "http://localhost:8000/mcp/{job_id}"

# Wait for completion (long-polling)
curl "http://localhost:8000/mcp/{job_id}/wait"
```

### Dialogue Style Analysis

```bash
curl -X POST "http://localhost:8000/mcp/analyze-style" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Talk like Trump",
    "credentials": {
      "gemini_api_key": "your-gemini-api-key"
    }
  }'
```

**Response Structure:**
```json
{
  "tone": "authoritative",
  "pace": "fast", 
  "vocabulary_level": "simple",
  "target_audience": "supporters",
  "content_structure": "repetitive",
  "energy_level": "high",
  "formality": "informal",
  "humor_style": "boastful",
  "empathy_level": "low",
  "confidence_level": "extremely confident",
  "storytelling": "anecdotal",
  "keyPhrases": ["tremendous", "believe me", "many people say"],
  "additionalInstructions": "Use superlatives frequently, repeat key points, speak with absolute certainty"
}
```

**Expected Response Types:**
- **tone**: `authoritative`, `casual`, `dramatic`, `confident`, `passionate`, `professional`, `friendly`
- **pace**: `fast`, `slow`, `moderate`, `rushed`, `deliberate`, `varied`
- **vocabulary_level**: `simple`, `conversational`, `sophisticated`, `technical`, `colloquial`, `academic`
- **target_audience**: `supporters`, `general public`, `experts`, `working class`, `professionals`, `students`
- **content_structure**: `rambling`, `structured`, `repetitive`, `stream-of-consciousness`, `analytical`
- **energy_level**: `high`, `explosive`, `moderate`, `low`, `dynamic`
- **formality**: `informal`, `conversational`, `formal`, `crude`, `folksy`, `semi-formal`
- **humor_style**: `sarcastic`, `self-deprecating`, `boastful`, `witty`, `dry`, `playful`, `none`
- **empathy_level**: `low`, `moderate`, `high`, `performative`, `neutral`
- **confidence_level**: `extremely confident`, `boastful`, `uncertain`, `assertive`, `tentative`
- **storytelling**: `anecdotal`, `repetitive`, `tangential`, `direct`, `exaggerated`, `fact-based`
- **keyPhrases**: Array of signature phrases, expressions, and verbal tics
- **additionalInstructions**: Specific vocal patterns and speech characteristics

### System Health Check

```bash
# Check if system is healthy
curl "http://localhost:8000/health"

# Basic service info
curl "http://localhost:8000/"
```

### Real-time Progress via WebSocket

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/{job_id}');
ws.onmessage = function(event) {
    const progress = JSON.parse(event.data);
    console.log(`Progress: ${progress.progress}% - ${progress.current_step}`);
};
```

### Cost-Optimized Examples

**Generate audio without thumbnail (saves $0.02):**
```bash
curl -X POST "http://localhost:8000/mcp" \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "audio",
    "prompt": "Quick podcast summary",
    "generate_thumbnail": false,
    "credentials": {...}
  }'
```

**Short video for lower cost ($1.50 vs $4.00):**
```bash
curl -X POST "http://localhost:8000/mcp" \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "video",
    "prompt": "Quick product demo",
    "parameters": {
      "durationSeconds": 3,  # $1.50 cost vs 8s at $4.00
      "model": "veo-3.0-generate-preview",
      "aspectRatio": "16:9"
    },
    "credentials": {...}
  }'
```

**Premium quality thumbnail (higher cost):**
```bash
# Set environment variable for higher quality
export IMAGEN_MODEL_ID=imagen-4.0-generate-001  # $0.04/image vs $0.02

# Then make request with thumbnail
curl -X POST "http://localhost:8000/mcp" \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "audio",
    "prompt": "Professional podcast",
    "generate_thumbnail": true,
    "thumbnail_prompt": "Elegant professional podcast cover with microphone, gold accents, premium typography",
    "credentials": {...}
  }'
```

### Custom Thumbnail Prompts

**Use a custom prompt for thumbnail generation (separate from audio content):**
```bash
curl -X POST "http://localhost:8000/mcp" \\
  -H "Content-Type: application/json" \\
  -d '{
    "mode": "audio",
    "prompt": "Discuss the economic impact of renewable energy adoption",
    "generate_thumbnail": true,
    "thumbnail_prompt": "Clean energy podcast cover: solar panels, wind turbines, green economy icons, modern design",
    "credentials": {...}
  }'
```

**Benefits of custom thumbnail prompts:**
- 🎨 **Creative Control**: Design thumbnails that match your brand
- 👁️ **Visual Appeal**: Create eye-catching covers separate from audio content  
- 📊 **Marketing Focus**: Target specific audiences with visual elements
- ✨ **Professional Look**: Use design-specific language for better results

**Thumbnail Prompt Tips:**
- Include visual elements: "microphone, headphones, waveforms"
- Specify design style: "modern, professional, minimalist, vibrant"
- Add branding elements: "logo space, consistent colors"
- Mention text placement: "title area, readable typography"

## 🔐 Authentication Options

### Option 1: Per-Request Credentials (Recommended)

Provide credentials in each API request:

```json
{
  "mode": "video",
  "prompt": "Your prompt here",
  "credentials": {
    "gemini_api_key": "AIza...",
    "google_cloud_credentials": {
      "type": "service_account",
      "project_id": "your-project",
      "private_key_id": "...",
      "private_key": "-----BEGIN PRIVATE KEY-----...",
      "client_email": "service@project.iam.gserviceaccount.com",
      "client_id": "...",
      "auth_uri": "https://accounts.google.com/o/oauth2/auth",
      "token_uri": "https://oauth2.googleapis.com/token"
    },
    "google_cloud_project": "your-project-id",
    "vertex_ai_region": "us-central1",
    "gcs_bucket": "your-bucket",
    "elevenlabs_api_key": "sk_..."
  }
}
```

### Option 2: Environment Variables (Legacy)

Set credentials via environment variables and omit the `credentials` field in requests.

## 📋 API Reference

### Endpoints

**Core Functionality:**
- `POST /mcp` - Submit video/audio generation job
- `GET /mcp/{job_id}` - Check job status
- `GET /mcp/{job_id}/wait` - Long-polling status check
- `POST /mcp/analyze-style` - Analyze dialogue style for podcast generation
- `GET /operation/{operation_name}` - Query video operation status
- `WebSocket /ws/{job_id}` - Real-time progress updates

**System Monitoring:**
- `GET /` - Service information and available endpoints
- `GET /health` - Comprehensive health check with component status
- `GET /docs` - Interactive API documentation (Swagger UI)

### Supported Video Models

- `veo-3.0-generate-preview` (default) - Latest Veo 3.0 model
- `veo-2.0-generate-preview` - Veo 2.0 model
- `veo-1.0-generate-preview` - Original Veo model
- `imagen-3.0-generate-001` - Imagen 3.0 model
- `imagen-3.0-fast-generate-001` - Fast Imagen 3.0 model

### Video Parameters

- **Duration**: 1-60 seconds
- **Aspect Ratio**: 16:9, 9:16, 1:1, 4:3, 3:4
- **Sample Count**: 1-4 videos per request
- **Audio Generation**: Enabled by default
- **Person Generation**: Configurable (allow_all, allow_adult, block_all)

### Audio/Thumbnail Parameters

- **generate_thumbnail**: Boolean to enable thumbnail generation (audio mode only)
- **thumbnail_prompt**: Custom prompt for thumbnail design (optional)
  - If not provided: Auto-generates based on main prompt
  - If provided: Uses custom prompt for more control over thumbnail design
  - Example: `"Professional podcast cover with microphone and modern typography"`

### Response Status Values

- `queued` - Job submitted, waiting to process
- `started` - Processing in progress
- `finished` - Complete, download_url available
- `failed` - Error occurred
- `not_found` - Invalid job_id

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   FastAPI App   │────│   Redis Queue   │────│  RQ Workers     │
│   (Port 8000)   │    │   (Port 6379)   │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   WebSocket     │    │   Job Metadata  │    │  Google Cloud   │
│   Updates       │    │   & Progress    │    │  Services       │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 🔧 Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GOOGLE_CLOUD_PROJECT` | Yes | Your Google Cloud project ID |
| `VERTEX_AI_REGION` | No | Vertex AI region (default: us-central1) |
| `GCS_BUCKET` | Yes | Google Cloud Storage bucket name |
| `GOOGLE_CLOUD_CREDENTIALS_PATH` | No | Path to service account JSON file |
| `GEMINI_API_KEY` | No | Google Gemini API key (can be per-request) |
| `XI_KEY` | No | ElevenLabs API key (can be per-request) |
| `VEO_MODEL_ID` | No | Default video model (default: veo-3.0-generate-preview) |
| `IMAGEN_MODEL_ID` | No | Image generation model for thumbnails (default: imagen-3.0-fast-generate-001) |
| `REDIS_URL` | No | Redis connection URL (default: redis://localhost:6379/0) |

## 🚨 Troubleshooting

### Health Check First!

Before troubleshooting issues, always check the system health:

```bash
# Check overall system health
curl http://localhost:8000/health

# Quick service status
curl http://localhost:8000/
```

The health check will show you:
- ✅ **Redis Connection**: Whether the job queue is accessible
- 📁 **Queue Status**: Number of pending and failed jobs
- 📦 **Storage Config**: GCS bucket configuration status
- 🔌 **WebSocket Status**: Real-time connection manager status

### Common Issues

0. **Service not responding**:
   - Check `curl http://localhost:8000/health` returns HTTP 200
   - If HTTP 503, check which components are "unhealthy"
   - Restart services: `docker-compose restart`

1. **"Invalid credentials" error**:
   - Verify your service account has the required IAM roles
   - Check that your API keys are correct and active
   - Ensure your Google Cloud project has billing enabled

2. **"Job not found" error**:
   - Check that Redis is running and accessible
   - Verify the job_id is correct

3. **Video generation timeout**:
   - Video generation can take 5-15 minutes
   - Use the WebSocket endpoint for real-time updates
   - Check operation status using `/operation/{operation_name}`

4. **Storage permissions error**:
   - Ensure your service account has `roles/storage.admin` permission
   - Verify the GCS bucket exists and is accessible

### Logs

View logs for debugging:

```bash
# Docker Compose logs
docker-compose logs -f app
docker-compose logs -f worker

# Local development
# Check FastAPI logs in terminal
# Check worker logs in worker terminal
```

## 💰 Cost Optimization

### Thumbnail Generation Cost
- **Default Model**: Uses Imagen 3 Fast (`imagen-3.0-fast-generate-001`) at **$0.02 per image**
- **Optimized for Cost**: Automatically selects the cheapest available model
- **Configurable**: Set `IMAGEN_MODEL_ID` environment variable to use different models

**Available Models & Pricing**:
| Model | Cost/Image | Speed | Quality | Best For |
|-------|------------|-------|---------|----------|
| `imagen-3.0-fast-generate-001` ⭐ | $0.02 | Fast | Good | Thumbnails (default) |
| `imagen-4.0-fast-generate-001` | $0.02 | Fast | Better | Higher quality thumbnails |
| `imagen-3.0-generate-001` | $0.04 | Slower | High | Professional images |
| `imagen-4.0-generate-001` | $0.04 | Slower | Highest | Premium quality |

### Video Generation Cost
- **Veo 2.0/3.0 Models**: **$0.50 per second** of generated video
- **8-second video (default)**: **$4.00** per generation
- **1-minute video**: **$30.00** per generation  
- **Duration Impact**: Each second adds $0.50 to the cost
- **Quality Options**: Configure via `VEO_MODEL_ID` for different models

**Video Cost Examples**:
| Duration | Cost | Use Case |
|----------|------|----------|
| 3 seconds | $1.50 | Quick demo/preview |
| 8 seconds | $4.00 | Standard content (default) |
| 15 seconds | $7.50 | Social media posts |
| 30 seconds | $15.00 | Short advertisements |
| 60 seconds | $30.00 | Full promotional videos |

**Supported Models**: veo-3.0-generate-preview, veo-2.0-generate-preview, veo-1.0-generate-preview

### Audio Generation Cost
- **Text-to-Speech**: Uses ElevenLabs API (user-provided key)
- **Script Generation**: Uses Google Gemini API (minimal cost)
- **Storage**: Google Cloud Storage charges apply

### Cost Management Tips

**For Video Generation**:
- **Short Duration**: 3-second videos cost $1.50 vs 8-second at $4.00
- **Development**: Use shorter videos for testing/prototyping
- **Production Planning**: Budget $0.50 per second of final content
- **Model Choice**: Veo 1.0 may be cheaper than newer versions

**For Audio Generation**:
- **Skip Thumbnails**: Use `generate_thumbnail: false` to save $0.02 per job
- **Batch Audio**: Generate multiple podcasts in one session

**General Optimization**:
- **Environment Variables**: Pre-configure cheapest models as defaults
- **Request Validation**: Use credential validation to avoid failed billing
- **Monitor Usage**: Track API costs through Google Cloud Console

## 🔒 Security Considerations

- **Never commit API keys** to version control
- **Use service accounts** instead of personal Google accounts
- **Rotate API keys** regularly
- **Limit service account permissions** to minimum required
- **Use environment variables** or secret management for credentials
- **Enable audit logging** in Google Cloud for production

## 📚 Additional Resources

- [Detailed API Documentation](UPDATED_API_INTERFACE.md)
- [Google Vertex AI Documentation](https://cloud.google.com/vertex-ai/docs)
- [ElevenLabs API Documentation](https://elevenlabs.io/docs)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📄 License

tbd.

## 💡 Support

For issues and questions:
1. Check the [troubleshooting section](#-troubleshooting)
2. Review the [API documentation](UPDATED_API_INTERFACE.md)
3. Open an issue in the repository

---

**Ready to generate amazing content? Start with the Quick Start guide above! 🚀**