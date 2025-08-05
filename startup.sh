#!/bin/bash

set -e  # Exit on any error

echo "=== MCP Summer School Service Startup ==="
echo "Docker-only startup script initiated"

# Validate we're running in Docker
if [ ! -f /.dockerenv ] && [ ! -f /proc/1/cgroup ] || [ -z "$DOCKER_ENV" ]; then
    echo "ERROR: This application can only be started through Docker!"
    echo "Please use 'docker-compose up' or deploy through Coolify"
    exit 1
fi

echo "✓ Docker environment validated"

# Check if file injection is required
if [ -n "$INJECTED_FILE_CONTENT" ] && [ -n "$INJECTED_FILE_PATH" ]; then
    echo "File injection requested: $INJECTED_FILE_PATH"
    
    # Create directory if it doesn't exist
    INJECTED_DIR=$(dirname "$INJECTED_FILE_PATH")
    if [ ! -d "$INJECTED_DIR" ]; then
        echo "Creating directory: $INJECTED_DIR"
        mkdir -p "$INJECTED_DIR"
    fi
    
    # Decode and write the file content
    echo "Injecting file content from environment variable..."
    if echo "$INJECTED_FILE_CONTENT" | base64 -d > "$INJECTED_FILE_PATH" 2>/dev/null; then
        echo "✓ File successfully injected to: $INJECTED_FILE_PATH"
        
        # Set appropriate permissions
        chmod 644 "$INJECTED_FILE_PATH"
        
        # Verify file was created
        if [ -f "$INJECTED_FILE_PATH" ]; then
            FILE_SIZE=$(stat -f%z "$INJECTED_FILE_PATH" 2>/dev/null || stat -c%s "$INJECTED_FILE_PATH" 2>/dev/null || echo "unknown")
            echo "✓ File verification passed (size: ${FILE_SIZE} bytes)"
        else
            echo "ERROR: File injection failed - file not found after creation"
            exit 1
        fi
    else
        echo "ERROR: Failed to decode and write file content"
        echo "Make sure INJECTED_FILE_CONTENT is properly base64 encoded"
        exit 1
    fi
elif [ -n "$INJECTED_FILE_CONTENT" ] || [ -n "$INJECTED_FILE_PATH" ]; then
    echo "ERROR: Both INJECTED_FILE_CONTENT and INJECTED_FILE_PATH must be set together"
    echo "INJECTED_FILE_CONTENT set: $([ -n "$INJECTED_FILE_CONTENT" ] && echo "yes" || echo "no")"
    echo "INJECTED_FILE_PATH set: $([ -n "$INJECTED_FILE_PATH" ] && echo "yes" || echo "no")"
    exit 1
else
    echo "No file injection configured (optional)"
fi

# Handle Google Cloud authentication if configured
if [ -n "$GOOGLE_CLOUD_CREDENTIALS_PATH" ]; then
    echo "Activating Google Cloud service account..."
    if gcloud auth activate-service-account --key-file="$GOOGLE_CLOUD_CREDENTIALS_PATH"; then
        echo "✓ Google Cloud authentication successful"
    else
        echo "WARNING: Google Cloud authentication failed"
    fi
fi

# Determine which service to start based on arguments
if [ "$1" = "worker" ]; then
    echo "Starting RQ worker..."
    export PYTHONWARNINGS='ignore::UserWarning'
    exec rq worker --url redis://redis:6379/0
elif [ "$1" = "app" ] || [ -z "$1" ]; then
    echo "Starting FastAPI application..."
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
else
    echo "Starting with custom command: $*"
    exec "$@"
fi