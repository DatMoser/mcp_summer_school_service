#!/usr/bin/env python3
"""
Simple MCP Testing Script - Basic functionality test
"""

import json
import os
import tempfile

# Set minimal environment to avoid import errors
os.environ.setdefault('REDIS_URL', 'redis://localhost:6379/0')
os.environ.setdefault('GCS_BUCKET', 'test-bucket')
os.environ.setdefault('GOOGLE_CLOUD_PROJECT', 'test-project')

# Test the protocol handler directly
from app.mcp_protocol import mcp_handler

def test_basic_mcp():
    print("🧪 Basic MCP Protocol Test")
    print("=" * 40)
    
    # Test 1: Initialization
    print("1. Testing Initialize")
    init_message = json.dumps({
        "jsonrpc": "2.0",
        "id": "1",
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {"sampling": {}},
            "clientInfo": {"name": "Test", "version": "1.0"}
        }
    })
    
    response = mcp_handler.process_message(init_message)
    print(f"Response: {response}")
    
    if response:
        data = json.loads(response)
        if "result" in data:
            print("✅ Initialize works!")
        else:
            print("❌ Initialize failed")
    
    # Test 2: Ping
    print("\n2. Testing Ping")
    ping_message = json.dumps({
        "jsonrpc": "2.0", 
        "id": "2",
        "method": "ping"
    })
    
    response = mcp_handler.process_message(ping_message)
    print(f"Response: {response}")
    
    if response:
        data = json.loads(response)
        if "result" in data:
            print("✅ Ping works!")
        else:
            print("❌ Ping failed")
    
    # Test 3: Test models
    print("\n3. Testing Models")
    from app.mcp_models import McpTool, McpToolInputSchema
    
    tool = McpTool(
        name="test",
        description="Test tool",
        inputSchema=McpToolInputSchema(
            type="object",
            properties={"test": {"type": "string"}}
        )
    )
    print(f"Tool created: {tool.name}")
    print("✅ Models work!")
    
    print("\n🎉 Basic MCP tests completed!")

if __name__ == "__main__":
    test_basic_mcp()