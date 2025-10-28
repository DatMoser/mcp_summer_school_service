#!/usr/bin/env python3
"""
MCP Bridge Script for Claude Desktop

This script bridges Claude Desktop's stdio-based MCP protocol to the HTTP-based
MCP server deployed at https://api.c4dhi.org

Supports both:
- Streamable HTTP transport (2025-03-26+): Single /mcp endpoint
- Legacy HTTP+SSE transport (2024-11-05): Dual /mcp-rpc + /mcp-sse endpoints

Auto-detects which transport the server supports.
"""

import sys
import json
import os
import requests
import uuid
from typing import Any, Dict, Optional
import threading
import time


class MCPBridge:
    """Bridges stdio MCP protocol to HTTP MCP endpoints"""

    def __init__(self, base_url: str, api_key: str, use_legacy: bool = False):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.client_id = str(uuid.uuid4())
        self.sse_thread: Optional[threading.Thread] = None
        self.running = False
        self.use_legacy = use_legacy
        self.protocol_version = "2024-11-05" if use_legacy else "2025-03-26"

        # Auto-detect transport if not specified
        if not use_legacy:
            detected = self.detect_transport()
            if detected == "legacy":
                self.log("Server doesn't support streamable transport, using legacy")
                self.use_legacy = True
                self.protocol_version = "2024-11-05"

    def log(self, message: str):
        """Log to stderr (stdout is reserved for MCP protocol)"""
        print(f"[MCP Bridge] {message}", file=sys.stderr, flush=True)

    def detect_transport(self) -> str:
        """Detect which transport the server supports"""
        try:
            response = requests.get(
                f'{self.base_url}/mcp-info',
                headers={'X-API-Key': self.api_key},
                timeout=5
            )
            if response.status_code == 200:
                info = response.json()
                if 'streamable' in info.get('transport', {}):
                    return "streamable"
        except Exception as e:
            self.log(f"Transport detection failed: {e}")

        return "legacy"

    def send_response(self, response: Dict[str, Any]):
        """Send JSON-RPC response to stdout for Claude Desktop"""
        json.dump(response, sys.stdout)
        sys.stdout.write('\n')
        sys.stdout.flush()

    def handle_request(self, request: Dict[str, Any]):
        """Forward JSON-RPC request to HTTP server"""
        try:
            # Forward to HTTP endpoint (legacy or streamable)
            endpoint = '/mcp-rpc' if self.use_legacy else '/mcp'

            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'X-API-Key': self.api_key,
                'MCP-Protocol-Version': self.protocol_version
            }

            response = requests.post(
                f'{self.base_url}{endpoint}',
                json=request,
                headers=headers,
                timeout=300  # 5 minute timeout for long operations
            )

            if response.status_code == 200:
                response_data = response.json()
                self.send_response(response_data)
            else:
                # Send error response
                error_response = {
                    "jsonrpc": "2.0",
                    "id": request.get("id"),
                    "error": {
                        "code": response.status_code,
                        "message": f"HTTP {response.status_code}: {response.text}"
                    }
                }
                self.send_response(error_response)

        except requests.exceptions.RequestException as e:
            self.log(f"Request error: {e}")
            error_response = {
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "error": {
                    "code": -32603,
                    "message": f"Connection error: {str(e)}"
                }
            }
            self.send_response(error_response)
        except Exception as e:
            self.log(f"Unexpected error: {e}")
            error_response = {
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "error": {
                    "code": -32603,
                    "message": f"Internal error: {str(e)}"
                }
            }
            self.send_response(error_response)

    def start_sse_listener(self):
        """Listen to SSE endpoint for real-time notifications"""
        def sse_worker():
            self.log(f"Starting SSE listener for client {self.client_id}")
            headers = {'X-API-Key': self.api_key}

            while self.running:
                try:
                    response = requests.get(
                        f'{self.base_url}/mcp-sse/{self.client_id}',
                        headers=headers,
                        stream=True,
                        timeout=300
                    )

                    for line in response.iter_lines():
                        if not self.running:
                            break

                        if line:
                            line = line.decode('utf-8')
                            if line.startswith('data: '):
                                try:
                                    data = json.loads(line[6:])
                                    # Forward SSE notification as JSON-RPC notification
                                    notification = {
                                        "jsonrpc": "2.0",
                                        "method": "notifications/message",
                                        "params": data
                                    }
                                    self.send_response(notification)
                                except json.JSONDecodeError:
                                    pass

                except requests.exceptions.RequestException as e:
                    if self.running:
                        self.log(f"SSE connection error: {e}, retrying in 5s...")
                        time.sleep(5)
                except Exception as e:
                    if self.running:
                        self.log(f"SSE unexpected error: {e}")
                        time.sleep(5)

        self.sse_thread = threading.Thread(target=sse_worker, daemon=True)
        self.sse_thread.start()

    def run(self):
        """Main loop: read from stdin, forward to HTTP server"""
        self.log(f"MCP Bridge starting...")
        self.log(f"Connecting to: {self.base_url}")
        self.log(f"Client ID: {self.client_id}")

        self.running = True

        # Start SSE listener in background
        self.start_sse_listener()

        try:
            # Read JSON-RPC requests from stdin
            for line in sys.stdin:
                line = line.strip()
                if not line:
                    continue

                try:
                    request = json.loads(line)
                    self.log(f"Received request: {request.get('method', 'unknown')}")
                    self.handle_request(request)
                except json.JSONDecodeError as e:
                    self.log(f"Invalid JSON: {e}")
                    error_response = {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {
                            "code": -32700,
                            "message": "Parse error"
                        }
                    }
                    self.send_response(error_response)
        except KeyboardInterrupt:
            self.log("Shutting down...")
        finally:
            self.running = False
            if self.sse_thread:
                self.sse_thread.join(timeout=1)


def main():
    # Configuration from environment variables
    base_url = os.environ.get('MCP_SERVER_URL', 'https://api.c4dhi.org')
    api_key = os.environ.get('MCP_API_KEY', '')
    use_legacy = os.environ.get('MCP_USE_LEGACY', 'false').lower() == 'true'

    if not api_key:
        print("ERROR: MCP_API_KEY environment variable is required", file=sys.stderr)
        sys.exit(1)

    # Create and run bridge
    bridge = MCPBridge(base_url, api_key, use_legacy=use_legacy)
    transport_type = "Legacy (2024-11-05)" if bridge.use_legacy else "Streamable (2025-03-26+)"
    endpoint = "/mcp-rpc + /mcp-sse" if bridge.use_legacy else "/mcp"
    print(f"[MCP Bridge] Using {transport_type} transport: {endpoint}", file=sys.stderr)
    bridge.run()


if __name__ == '__main__':
    main()
