#!/usr/bin/env python3
"""
Simple HTTP test of MCP endpoints - use this if the service is running
"""

import requests
import json
import time

def test_mcp_http():
    """Test MCP via HTTP requests"""
    base_url = "http://localhost:8000"
    mcp_url = f"{base_url}/mcp-rpc"
    
    print("🌐 Testing MCP via HTTP")
    print("=" * 40)
    
    # Test 1: Check if service is running
    try:
        response = requests.get(f"{base_url}/")
        print(f"✅ Service is running: {response.status_code}")
        print(f"Service info: {response.json()}")
    except requests.exceptions.ConnectionError:
        print("❌ Service not running. Start with:")
        print("   python3 -m uvicorn app.main:app --port 8000")
        return False
    
    # Test 2: Check MCP info
    try:
        response = requests.get(f"{base_url}/mcp-info")
        print(f"\n📋 MCP Info: {response.status_code}")
        info = response.json()
        print(f"Protocol: {info.get('protocol')}")
        print(f"Version: {info.get('version')}")
        print(f"Capabilities: {list(info.get('capabilities', {}).keys())}")
    except Exception as e:
        print(f"❌ MCP info failed: {e}")
    
    # Test 3: Initialize MCP session
    try:
        init_request = {
            "jsonrpc": "2.0",
            "id": "1",
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {"sampling": {}},
                "clientInfo": {"name": "HTTP Test", "version": "1.0"}
            }
        }
        
        response = requests.post(mcp_url, json=init_request)
        print(f"\n🤝 Initialize: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            if "result" in result:
                print("✅ MCP initialization successful")
                server_info = result["result"].get("serverInfo", {})
                print(f"Server: {server_info.get('name')} v{server_info.get('version')}")
            else:
                print(f"❌ Initialize failed: {result}")
        else:
            print(f"❌ HTTP error: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Initialize failed: {e}")
    
    # Test 4: List tools
    try:
        tools_request = {
            "jsonrpc": "2.0",
            "id": "2",
            "method": "tools/list"
        }
        
        response = requests.post(mcp_url, json=tools_request)
        print(f"\n🛠️ Tools List: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            if "result" in result:
                tools = result["result"].get("tools", [])
                print(f"✅ Found {len(tools)} tools:")
                for tool in tools:
                    print(f"  - {tool['name']}: {tool['description']}")
            else:
                print(f"❌ Tools list failed: {result}")
                
    except Exception as e:
        print(f"❌ Tools list failed: {e}")
    
    # Test 5: List prompts
    try:
        prompts_request = {
            "jsonrpc": "2.0", 
            "id": "3",
            "method": "prompts/list"
        }
        
        response = requests.post(mcp_url, json=prompts_request)
        print(f"\n📝 Prompts List: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            if "result" in result:
                prompts = result["result"].get("prompts", [])
                print(f"✅ Found {len(prompts)} prompts:")
                for prompt in prompts:
                    print(f"  - {prompt['name']}: {prompt.get('description', 'No description')}")
            else:
                print(f"❌ Prompts list failed: {result}")
                
    except Exception as e:
        print(f"❌ Prompts list failed: {e}")
    
    # Test 6: Test error handling
    try:
        error_request = {
            "jsonrpc": "2.0",
            "id": "4", 
            "method": "unknown/method"
        }
        
        response = requests.post(mcp_url, json=error_request)
        print(f"\n❌ Error Test: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            if "error" in result:
                error = result["error"]
                print(f"✅ Proper error handling: {error['code']} - {error['message']}")
            else:
                print(f"❌ Should have returned error: {result}")
                
    except Exception as e:
        print(f"❌ Error test failed: {e}")
    
    print(f"\n🎉 MCP HTTP testing completed!")
    print("\nFor full testing with credentials, use the examples in MCP_TESTING_GUIDE.md")
    return True

if __name__ == "__main__":
    test_mcp_http()