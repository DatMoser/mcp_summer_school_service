# Claude Desktop Setup Guide

This guide explains how to connect your deployed MCP server at **https://api.c4dhi.org** to Claude Desktop.

## Overview

Your MCP server provides AI-powered video and audio generation tools that can be used directly within Claude Desktop conversations. This setup uses a bridge script to translate between Claude Desktop's stdio-based MCP protocol and your HTTP-based MCP server.

## Available Tools

Once connected, you'll have access to these tools in Claude Desktop:

- **generate_video** - Create videos (1-60 seconds) using Google Veo models
- **generate_audio** - Generate podcasts/audio with AI text-to-speech (ElevenLabs)
- **analyze_writing_style** - Analyze dialogue patterns for custom voice generation
- **check_job_status** - Monitor job progress and retrieve results

## Prerequisites

1. **Claude Desktop** installed (macOS/Windows/Linux)
2. **Python 3.7+** installed on your system
3. **API Key** for your deployed server (the value of your `API_KEY` environment variable)
4. **requests** Python library: `pip install requests`

## Step 1: Test Your Server Connection

Before configuring Claude Desktop, verify your server is accessible:

```bash
# Set your API key
export MCP_API_KEY="your-api-key-here"

# Run the connection test
python3 test_connection.py
```

You should see all tests pass. If any tests fail, check your server deployment and API key.

## Step 2: Locate Your Claude Desktop Config File

Find your Claude Desktop configuration file location:

**macOS:**
```
~/Library/Application Support/Claude/claude_desktop_config.json
```

**Windows:**
```
%APPDATA%\Claude\claude_desktop_config.json
```

**Linux:**
```
~/.config/Claude/claude_desktop_config.json
```

If the file doesn't exist, create it with an empty JSON object: `{}`

## Step 3: Add MCP Server Configuration

Edit your `claude_desktop_config.json` file to add the video-audio-generator server:

```json
{
  "mcpServers": {
    "video-audio-generator": {
      "command": "python3",
      "args": [
        "/ABSOLUTE/PATH/TO/mcp-bridge.py"
      ],
      "env": {
        "MCP_SERVER_URL": "https://api.c4dhi.org",
        "MCP_API_KEY": "your-actual-api-key-here"
      }
    }
  }
}
```

**Important:**
- Replace `/ABSOLUTE/PATH/TO/mcp-bridge.py` with the actual absolute path to the bridge script
- Replace `your-actual-api-key-here` with your real API key
- On macOS, the path would be something like: `/Users/felixmoser/Github/mcp_summer_school_service/mcp-bridge.py`

### Example Configuration

For this repository, your config would look like:

```json
{
  "mcpServers": {
    "video-audio-generator": {
      "command": "python3",
      "args": [
        "/Users/felixmoser/Github/mcp_summer_school_service/mcp-bridge.py"
      ],
      "env": {
        "MCP_SERVER_URL": "https://api.c4dhi.org",
        "MCP_API_KEY": "your-actual-api-key-here"
      }
    }
  }
}
```

### Multiple MCP Servers

If you already have other MCP servers configured, add the video-audio-generator as an additional entry:

```json
{
  "mcpServers": {
    "existing-server": {
      "command": "...",
      "args": ["..."]
    },
    "video-audio-generator": {
      "command": "python3",
      "args": [
        "/Users/felixmoser/Github/mcp_summer_school_service/mcp-bridge.py"
      ],
      "env": {
        "MCP_SERVER_URL": "https://api.c4dhi.org",
        "MCP_API_KEY": "your-actual-api-key-here"
      }
    }
  }
}
```

## Step 4: Restart Claude Desktop

After updating the configuration:

1. **Quit Claude Desktop completely** (Cmd+Q on macOS, or use Exit from system tray)
2. **Restart Claude Desktop**
3. The bridge script will automatically connect to your deployed server

## Step 5: Verify the Connection

In Claude Desktop, you should see the MCP server status in the interface. You can also test it by asking Claude to use one of the tools:

### Example Prompts

**Generate a video:**
```
Can you generate a 10-second video of a sunset over the ocean using the video generation tool?
```

**Generate audio:**
```
Create a short podcast introduction about AI technology.
```

**Analyze writing style:**
```
Analyze the writing style of Steve Jobs for podcast generation.
```

## How It Works

The architecture looks like this:

```
Claude Desktop (stdio)
    ↕ JSON-RPC
mcp-bridge.py
    ↕ HTTP + SSE
https://api.c4dhi.org (Your deployed server)
    ↕
Google Cloud (Veo, Vertex AI, GCS)
ElevenLabs (Text-to-Speech)
```

The bridge script (`mcp-bridge.py`):
- Accepts stdio input from Claude Desktop
- Translates JSON-RPC requests to HTTP
- Forwards requests to your deployed server with authentication
- Listens for Server-Sent Events (SSE) for real-time updates
- Streams responses back to Claude Desktop via stdout

## Troubleshooting

### Claude Desktop doesn't show the server

1. Check the configuration file syntax is valid JSON (use a JSON validator)
2. Verify the path to `mcp-bridge.py` is absolute and correct
3. Check Claude Desktop logs for errors
4. Ensure Python 3 and requests library are installed

### Connection errors in bridge script

1. Verify your server is running: `curl https://api.c4dhi.org/health`
2. Test your API key: `python3 test_connection.py`
3. Check the bridge logs in stderr output
4. Ensure no firewall is blocking the connection

### Tools not working

1. Verify your server has valid credentials configured (Google Cloud, ElevenLabs)
2. Check job status using the `check_job_status` tool with the returned job_id
3. Look at server logs for error messages
4. Test the REST API directly to isolate the issue

### Bridge script logs

The bridge script logs to stderr. To see logs:

```bash
# Run the bridge manually to see logs
export MCP_API_KEY="your-key"
python3 mcp-bridge.py
# Then type JSON-RPC requests (one per line)
```

## Advanced Configuration

### Custom server URL

If you need to test against a different deployment:

```json
{
  "mcpServers": {
    "video-audio-generator": {
      "command": "python3",
      "args": ["/path/to/mcp-bridge.py"],
      "env": {
        "MCP_SERVER_URL": "https://staging.c4dhi.org",
        "MCP_API_KEY": "staging-api-key"
      }
    }
  }
}
```

### Multiple environments

You can configure multiple instances for different environments:

```json
{
  "mcpServers": {
    "video-audio-prod": {
      "command": "python3",
      "args": ["/path/to/mcp-bridge.py"],
      "env": {
        "MCP_SERVER_URL": "https://api.c4dhi.org",
        "MCP_API_KEY": "prod-key"
      }
    },
    "video-audio-staging": {
      "command": "python3",
      "args": ["/path/to/mcp-bridge.py"],
      "env": {
        "MCP_SERVER_URL": "https://staging.c4dhi.org",
        "MCP_API_KEY": "staging-key"
      }
    }
  }
}
```

## Usage Tips

### Video Generation

```
Generate a video using the generate_video tool:
- Prompt: "A serene mountain landscape at dawn"
- Duration: 10 seconds
- Aspect ratio: 16:9
- Model: veo-3.0-generate-preview
```

The tool will return a job_id. Use `check_job_status` to monitor progress and get the final video URL.

### Audio Generation

```
Create a podcast using the generate_audio tool:
- Prompt: "Welcome to TechTalk, where we discuss the latest in AI"
- Format: mp3
- Max duration: 30 seconds
```

### Real-time Updates

The bridge script automatically listens for SSE updates, so you'll receive real-time progress notifications as your videos and audio are generated.

## Security Notes

- Your API key is stored in the Claude Desktop config file
- The config file should have restricted permissions (600 on Unix systems)
- The bridge script never logs your API key
- All communication with the server uses HTTPS

## Getting Help

If you encounter issues:

1. Run `python3 test_connection.py` to diagnose connection problems
2. Check the bridge script stderr logs
3. Verify your server deployment status
4. Review the main README.md for server-side troubleshooting

## Additional Resources

- **Main README**: Comprehensive server documentation and API reference
- **MCP_IMPLEMENTATION.md**: Details on the MCP protocol implementation
- **CLIENT_API_GUIDE.md**: REST API usage examples
- **test_connection.py**: Connection validation script
- **mcp-bridge.py**: Bridge script source code

## What's Next?

Once connected, you can:
- Generate videos directly from Claude Desktop conversations
- Create AI podcasts with custom voices
- Analyze writing styles for voice customization
- Monitor job progress in real-time
- Access all generated content via Google Cloud Storage URLs

Enjoy using your AI video and audio generation tools in Claude Desktop!
