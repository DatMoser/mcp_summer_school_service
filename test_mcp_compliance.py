#!/usr/bin/env python3
"""
MCP Protocol Compliance Test Script.
Tests the MCP implementation for proper JSON-RPC 2.0 and MCP protocol compliance.
"""

import requests
import json
import time
import uuid
from typing import Dict, Any


class McpClient:
    """Simple MCP client for testing protocol compliance"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.mcp_endpoint = f"{base_url}/mcp-rpc"
        self.initialized = False
        self.capabilities = None
    
    def send_request(self, method: str, params: Dict[str, Any] = None, request_id: str = None) -> Dict[str, Any]:
        """Send JSON-RPC request to MCP server"""
        if request_id is None:
            request_id = str(uuid.uuid4())
        
        request_data = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method
        }
        
        if params:
            request_data["params"] = params
        
        print(f"Sending: {json.dumps(request_data, indent=2)}")
        
        response = requests.post(
            self.mcp_endpoint,
            json=request_data,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code != 200:
            raise Exception(f"HTTP {response.status_code}: {response.text}")
        
        result = response.json()
        print(f"Received: {json.dumps(result, indent=2)}")
        print("-" * 50)
        
        return result
    
    def initialize(self) -> Dict[str, Any]:
        """Initialize MCP session"""
        params = {
            "protocolVersion": "2025-06-18",
            "capabilities": {
                "sampling": {}
            },
            "clientInfo": {
                "name": "MCP Test Client",
                "version": "1.0.0"
            }
        }
        
        result = self.send_request("initialize", params)
        
        if "result" in result:
            self.initialized = True
            self.capabilities = result["result"]["capabilities"]
            print("✅ MCP initialization successful")
        else:
            print("❌ MCP initialization failed")
            
        return result
    
    def send_initialized_notification(self):
        """Send initialized notification"""
        request_data = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
        }
        
        print(f"Sending notification: {json.dumps(request_data, indent=2)}")
        
        response = requests.post(
            self.mcp_endpoint,
            json=request_data,
            headers={"Content-Type": "application/json"}
        )
        
        print(f"Notification response status: {response.status_code}")
        if response.content:
            print(f"Notification response: {response.text}")
        print("-" * 50)
    
    def list_tools(self) -> Dict[str, Any]:
        """List available tools"""
        return self.send_request("tools/list")
    
    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a tool"""
        params = {
            "name": tool_name,
            "arguments": arguments
        }
        return self.send_request("tools/call", params)
    
    def list_resources(self) -> Dict[str, Any]:
        """List available resources"""
        return self.send_request("resources/list")
    
    def read_resource(self, uri: str) -> Dict[str, Any]:
        """Read a resource"""
        params = {"uri": uri}
        return self.send_request("resources/read", params)
    
    def list_prompts(self) -> Dict[str, Any]:
        """List available prompts"""
        return self.send_request("prompts/list")
    
    def get_prompt(self, name: str, arguments: Dict[str, Any] = None) -> Dict[str, Any]:
        """Get a prompt"""
        params = {"name": name}
        if arguments:
            params["arguments"] = arguments
        return self.send_request("prompts/get", params)


def test_mcp_compliance():
    """Run MCP protocol compliance tests"""
    print("🧪 Starting MCP Protocol Compliance Tests")
    print("=" * 60)
    
    client = McpClient()
    
    try:
        # Test 1: Server Info
        print("📋 Test 1: Check server info endpoints")
        response = requests.get(f"{client.base_url}/")
        print(f"Root endpoint: {response.status_code}")
        
        response = requests.get(f"{client.base_url}/mcp-info")
        print(f"MCP info endpoint: {response.status_code}")
        print(f"MCP info: {json.dumps(response.json(), indent=2)}")
        print("-" * 50)
        
        # Test 2: Protocol Initialization
        print("🤝 Test 2: MCP Protocol Initialization")
        init_result = client.initialize()
        assert "result" in init_result, "Initialization failed"
        assert init_result["result"]["protocolVersion"] == "2025-06-18", "Wrong protocol version"
        
        # Send initialized notification
        client.send_initialized_notification()
        
        # Test 3: Tools Interface
        print("🛠️ Test 3: Tools Interface")
        tools_result = client.list_tools()
        assert "result" in tools_result, "Tools list failed"
        assert "tools" in tools_result["result"], "No tools in response"
        
        tools = tools_result["result"]["tools"]
        print(f"Available tools: {[tool['name'] for tool in tools]}")
        
        # Test tool call
        if tools:
            tool_name = "analyze_writing_style"
            print(f"Testing tool call: {tool_name}")
            tool_result = client.call_tool(tool_name, {
                "style_instruction": "Talk like a friendly teacher"
            })
            # Note: This will fail without credentials, but should return proper error
            print(f"Tool call result: {tool_result}")
        
        # Test 4: Resources Interface
        print("📚 Test 4: Resources Interface")
        resources_result = client.list_resources()
        assert "result" in resources_result, "Resources list failed"
        assert "resources" in resources_result["result"], "No resources in response"
        
        resources = resources_result["result"]["resources"]
        print(f"Available resources: {len(resources)} resources")
        
        # Test 5: Prompts Interface
        print("📝 Test 5: Prompts Interface")
        prompts_result = client.list_prompts()
        assert "result" in prompts_result, "Prompts list failed"
        assert "prompts" in prompts_result["result"], "No prompts in response"
        
        prompts = prompts_result["result"]["prompts"]
        print(f"Available prompts: {[prompt['name'] for prompt in prompts]}")
        
        # Test prompt get
        if prompts:
            prompt_name = "video_generation"
            print(f"Testing prompt get: {prompt_name}")
            prompt_result = client.get_prompt(prompt_name, {
                "topic": "cats playing",
                "style": "cute"
            })
            assert "result" in prompt_result, "Prompt get failed"
            print(f"Prompt result has messages: {'messages' in prompt_result['result']}")
        
        # Test 6: Error Handling
        print("❌ Test 6: Error Handling")
        
        # Test unknown method
        error_result = client.send_request("unknown/method")
        assert "error" in error_result, "Should return error for unknown method"
        assert error_result["error"]["code"] == -32601, "Wrong error code for unknown method"
        
        # Test invalid parameters
        error_result = client.send_request("tools/call", {"invalid": "params"})
        assert "error" in error_result, "Should return error for invalid params"
        
        print("✅ All MCP compliance tests passed!")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


def test_sse_connection():
    """Test Server-Sent Events connection"""
    print("\n📡 Testing Server-Sent Events Connection")
    print("-" * 50)
    
    client_id = str(uuid.uuid4())
    sse_url = f"http://localhost:8000/mcp-sse/{client_id}"
    
    try:
        # Note: This is a basic test - real SSE testing requires more sophisticated handling
        response = requests.get(sse_url, stream=True, timeout=5)
        print(f"SSE connection status: {response.status_code}")
        
        if response.status_code == 200:
            print("✅ SSE endpoint accessible")
            # Read first few bytes to verify it's streaming
            chunk = next(response.iter_content(chunk_size=100), None)
            if chunk:
                print(f"SSE data sample: {chunk[:50]}...")
        else:
            print(f"❌ SSE connection failed: {response.status_code}")
    
    except requests.exceptions.Timeout:
        print("✅ SSE connection timeout (expected for streaming endpoint)")
    except Exception as e:
        print(f"❌ SSE test error: {e}")


if __name__ == "__main__":
    print("🚀 MCP Summer School Service - Protocol Compliance Test")
    print("Make sure the service is running on http://localhost:8000")
    print("\nTesting in 3 seconds...")
    time.sleep(3)
    
    success = test_mcp_compliance()
    test_sse_connection()
    
    if success:
        print("\n🎉 MCP Protocol Implementation is Compliant!")
    else:
        print("\n💥 MCP Protocol Implementation needs fixes!")
        exit(1)