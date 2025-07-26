#!/usr/bin/env python3
"""
Local MCP Testing Script - Tests MCP functionality without full service setup.
This script directly tests the MCP protocol components without needing credentials.
"""

import json
import uuid
import asyncio
from app.mcp_protocol import mcp_handler, JsonRpcRequest
from app.mcp_models import (
    McpTool, McpToolInputSchema, McpResource, McpPrompt, McpPromptArgument
)

def test_mcp_protocol_handler():
    """Test the MCP protocol handler directly"""
    print("🧪 Testing MCP Protocol Handler")
    print("=" * 50)
    
    # Test 1: Initialization
    print("1. Testing Protocol Initialization")
    init_data = {
        "jsonrpc": "2.0",
        "id": "1",
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {"sampling": {}},
            "clientInfo": {"name": "Test Client", "version": "1.0.0"}
        }
    }
    
    response_json = mcp_handler.process_message(json.dumps(init_data))
    response = json.loads(response_json)
    print(f"Init Response: {json.dumps(response, indent=2)}")
    
    assert "result" in response, "Initialization should succeed"
    assert response["result"]["protocolVersion"] == "2025-06-18", "Wrong protocol version"
    print("✅ Initialization successful")
    
    # Test 2: Ping
    print("\n2. Testing Ping")
    ping_data = {
        "jsonrpc": "2.0",
        "id": "2",
        "method": "ping"
    }
    
    response_json = mcp_handler.process_message(json.dumps(ping_data))
    response = json.loads(response_json)
    print(f"Ping Response: {json.dumps(response, indent=2)}")
    
    assert "result" in response, "Ping should succeed"
    print("✅ Ping successful")
    
    # Test 3: Error handling
    print("\n3. Testing Error Handling")
    error_data = {
        "jsonrpc": "2.0",
        "id": "3",
        "method": "unknown_method"
    }
    
    response_json = mcp_handler.process_message(json.dumps(error_data))
    response = json.loads(response_json)
    print(f"Error Response: {json.dumps(response, indent=2)}")
    
    assert "error" in response, "Should return error for unknown method"
    print("✅ Error handling works")
    
    print("\n🎉 MCP Protocol Handler Tests Passed!")


def test_mcp_endpoints():
    """Test MCP endpoints directly"""
    print("\n🛠️ Testing MCP Endpoints")
    print("=" * 50)
    
    from app.mcp_endpoints import mcp_endpoints
    
    # Test tools list
    tools_request = JsonRpcRequest(
        id="tools-1",
        method="tools/list"
    )
    
    response = mcp_endpoints.handle_tools_list(tools_request)
    result = json.loads(response.json())
    print(f"Tools List: {json.dumps(result, indent=2)}")
    
    assert "result" in result, "Tools list should succeed"
    assert "tools" in result["result"], "Should have tools array"
    print(f"✅ Found {len(result['result']['tools'])} tools")
    
    # Test resources list
    resources_request = JsonRpcRequest(
        id="resources-1", 
        method="resources/list"
    )
    
    response = mcp_endpoints.handle_resources_list(resources_request)
    result = json.loads(response.json())
    print(f"Resources List: {json.dumps(result, indent=2)}")
    
    assert "result" in result, "Resources list should succeed"
    print("✅ Resources list works")
    
    # Test prompts list
    prompts_request = JsonRpcRequest(
        id="prompts-1",
        method="prompts/list"
    )
    
    response = mcp_endpoints.handle_prompts_list(prompts_request)
    result = json.loads(response.json())
    print(f"Prompts List: {json.dumps(result, indent=2)}")
    
    assert "result" in result, "Prompts list should succeed"
    assert "prompts" in result["result"], "Should have prompts array"
    print(f"✅ Found {len(result['result']['prompts'])} prompts")
    
    # Test prompt get
    prompt_get_request = JsonRpcRequest(
        id="prompt-get-1",
        method="prompts/get",
        params={
            "name": "video_generation",
            "arguments": {
                "topic": "test video",
                "style": "cinematic"
            }
        }
    )
    
    response = mcp_endpoints.handle_prompts_get(prompt_get_request)
    result = json.loads(response.json())
    print(f"Prompt Get: {json.dumps(result, indent=2)}")
    
    assert "result" in result, "Prompt get should succeed"
    assert "messages" in result["result"], "Should have messages"
    print("✅ Prompt get works")
    
    print("\n🎉 MCP Endpoints Tests Passed!")


def test_mcp_models():
    """Test MCP data models"""
    print("\n📋 Testing MCP Data Models")
    print("=" * 50)
    
    # Test tool model
    tool = McpTool(
        name="test_tool",
        description="A test tool",
        inputSchema=McpToolInputSchema(
            type="object",
            properties={
                "param1": {"type": "string", "description": "First parameter"}
            },
            required=["param1"]
        )
    )
    print(f"Tool Model: {tool.dict()}")
    print("✅ Tool model works")
    
    # Test resource model
    resource = McpResource(
        uri="test://resource/123",
        name="Test Resource",
        description="A test resource",
        mimeType="application/json"
    )
    print(f"Resource Model: {resource.dict()}")
    print("✅ Resource model works")
    
    # Test prompt model
    prompt = McpPrompt(
        name="test_prompt",
        description="A test prompt",
        arguments=[
            McpPromptArgument(name="arg1", description="First argument", required=True)
        ]
    )
    print(f"Prompt Model: {prompt.dict()}")
    print("✅ Prompt model works")
    
    print("\n🎉 MCP Data Models Tests Passed!")


async def test_mcp_transport():
    """Test MCP transport layer"""
    print("\n📡 Testing MCP Transport Layer")
    print("=" * 50)
    
    from app.mcp_transport import mcp_transport
    
    # Test message processing
    test_message = json.dumps({
        "jsonrpc": "2.0",
        "id": "transport-1",
        "method": "ping"
    })
    
    response_json = await mcp_transport._process_mcp_message(test_message)
    response = json.loads(response_json)
    print(f"Transport Response: {json.dumps(response, indent=2)}")
    
    assert "result" in response, "Transport should handle ping"
    print("✅ Transport message processing works")
    
    # Test connection count
    count = mcp_transport.get_connection_count()
    print(f"SSE Connection Count: {count}")
    print("✅ Transport connection tracking works")
    
    print("\n🎉 MCP Transport Tests Passed!")


def create_test_requests():
    """Create sample MCP test requests for manual testing"""
    print("\n📝 Sample MCP Requests for Manual Testing")
    print("=" * 50)
    
    # Initialize request
    init_request = {
        "jsonrpc": "2.0",
        "id": "1",
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {"sampling": {}},
            "clientInfo": {"name": "Manual Test Client", "version": "1.0.0"}
        }
    }
    print("Initialization Request:")
    print(json.dumps(init_request, indent=2))
    
    # Tools list request
    tools_request = {
        "jsonrpc": "2.0",
        "id": "2", 
        "method": "tools/list"
    }
    print("\nTools List Request:")
    print(json.dumps(tools_request, indent=2))
    
    # Tool call request (will fail without credentials but shows format)
    tool_call_request = {
        "jsonrpc": "2.0",
        "id": "3",
        "method": "tools/call",
        "params": {
            "name": "analyze_writing_style",
            "arguments": {
                "style_instruction": "Talk like Shakespeare"
            }
        }
    }
    print("\nTool Call Request (no credentials - will show error):")
    print(json.dumps(tool_call_request, indent=2))
    
    # Prompts get request
    prompt_request = {
        "jsonrpc": "2.0",
        "id": "4",
        "method": "prompts/get",
        "params": {
            "name": "video_generation",
            "arguments": {
                "topic": "dancing robot",
                "style": "futuristic",
                "mood": "energetic"
            }
        }
    }
    print("\nPrompt Get Request:")
    print(json.dumps(prompt_request, indent=2))
    
    print("\n💡 Use these with curl or a REST client to test the /mcp-rpc endpoint")


if __name__ == "__main__":
    print("🚀 MCP Local Testing Suite")
    print("Testing MCP components without full service setup")
    print("=" * 60)
    
    try:
        # Test core protocol handler
        test_mcp_protocol_handler()
        
        # Test data models
        test_mcp_models()
        
        # Test endpoints (without actual job execution)
        test_mcp_endpoints()
        
        # Test transport layer
        asyncio.run(test_mcp_transport())
        
        # Show sample requests for manual testing
        create_test_requests()
        
        print("\n" + "=" * 60)
        print("🎉 ALL MCP LOCAL TESTS PASSED!")
        print("The MCP implementation is working correctly!")
        print("\nTo test with real HTTP requests:")
        print("1. Set minimal environment variables:")
        print("   export REDIS_URL='redis://localhost:6379/0'")
        print("   export GCS_BUCKET='test-bucket'")
        print("2. Start Redis: docker run -d -p 6379:6379 redis:7-alpine")
        print("3. Start service: python3 -m uvicorn app.main:app --port 8000")
        print("4. Use the sample requests above with /mcp-rpc endpoint")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        exit(1)