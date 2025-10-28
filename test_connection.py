#!/usr/bin/env python3
"""
Test script to validate connection to the deployed MCP server

This script tests:
1. Basic server connectivity
2. API key authentication
3. MCP protocol initialization
4. Available tools and capabilities
"""

import os
import sys
import requests
import json
from typing import Dict, Any


class Colors:
    """ANSI color codes for terminal output"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


def print_success(message: str):
    print(f"{Colors.GREEN}✓{Colors.RESET} {message}")


def print_error(message: str):
    print(f"{Colors.RED}✗{Colors.RESET} {message}")


def print_info(message: str):
    print(f"{Colors.BLUE}ℹ{Colors.RESET} {message}")


def print_warning(message: str):
    print(f"{Colors.YELLOW}⚠{Colors.RESET} {message}")


def test_health_check(base_url: str) -> bool:
    """Test basic server connectivity"""
    print(f"\n{Colors.BOLD}1. Testing server health...{Colors.RESET}")
    try:
        response = requests.get(f"{base_url}/health", timeout=10)
        if response.status_code == 200:
            data = response.json()
            print_success(f"Server is healthy: {data}")
            return True
        else:
            print_error(f"Health check failed: HTTP {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print_error(f"Connection failed: {e}")
        return False


def test_api_key_validation(base_url: str, api_key: str) -> bool:
    """Test API key authentication"""
    print(f"\n{Colors.BOLD}2. Testing API key authentication...{Colors.RESET}")

    # Test without API key (should fail)
    try:
        response = requests.get(f"{base_url}/mcp-info", timeout=10)
        if response.status_code == 403:
            print_success("Server correctly rejects requests without API key")
        else:
            print_warning(f"Expected 403, got {response.status_code}")
    except Exception as e:
        print_error(f"Request failed: {e}")

    # Test with API key
    try:
        headers = {'X-API-Key': api_key}
        response = requests.get(f"{base_url}/validate", headers=headers, timeout=10)
        if response.status_code == 200:
            print_success("API key is valid")
            return True
        else:
            print_error(f"API key validation failed: HTTP {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print_error(f"Connection failed: {e}")
        return False


def test_mcp_initialization(base_url: str, api_key: str) -> Dict[str, Any]:
    """Test MCP protocol initialization"""
    print(f"\n{Colors.BOLD}3. Testing MCP protocol initialization...{Colors.RESET}")

    headers = {
        'Content-Type': 'application/json',
        'X-API-Key': api_key
    }

    # Send initialize request
    initialize_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {
                "name": "test-client",
                "version": "1.0.0"
            }
        }
    }

    try:
        response = requests.post(
            f"{base_url}/mcp-rpc",
            json=initialize_request,
            headers=headers,
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            if 'result' in data:
                print_success("MCP initialization successful")
                print_info(f"Protocol version: {data['result'].get('protocolVersion')}")
                print_info(f"Server: {data['result'].get('serverInfo', {}).get('name')}")
                return data['result']
            else:
                print_error(f"Initialization failed: {data.get('error', {}).get('message')}")
                return {}
        else:
            print_error(f"Initialization failed: HTTP {response.status_code}")
            return {}
    except requests.exceptions.RequestException as e:
        print_error(f"Connection failed: {e}")
        return {}


def test_list_tools(base_url: str, api_key: str) -> bool:
    """Test listing available tools"""
    print(f"\n{Colors.BOLD}4. Testing available tools...{Colors.RESET}")

    headers = {
        'Content-Type': 'application/json',
        'X-API-Key': api_key
    }

    list_tools_request = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {}
    }

    try:
        response = requests.post(
            f"{base_url}/mcp-rpc",
            json=list_tools_request,
            headers=headers,
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            if 'result' in data:
                tools = data['result'].get('tools', [])
                print_success(f"Found {len(tools)} available tools:")
                for tool in tools:
                    print(f"  • {Colors.BOLD}{tool['name']}{Colors.RESET}: {tool.get('description', 'No description')}")
                return True
            else:
                print_error(f"Failed to list tools: {data.get('error', {}).get('message')}")
                return False
        else:
            print_error(f"Failed to list tools: HTTP {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print_error(f"Connection failed: {e}")
        return False


def test_mcp_info(base_url: str, api_key: str) -> bool:
    """Test MCP info endpoint"""
    print(f"\n{Colors.BOLD}5. Testing MCP info endpoint...{Colors.RESET}")

    headers = {'X-API-Key': api_key}

    try:
        response = requests.get(
            f"{base_url}/mcp-info",
            headers=headers,
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            print_success("MCP info retrieved successfully:")
            print(json.dumps(data, indent=2))
            return True
        else:
            print_error(f"Failed to get MCP info: HTTP {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print_error(f"Connection failed: {e}")
        return False


def main():
    print(f"{Colors.BOLD}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}MCP Server Connection Test{Colors.RESET}")
    print(f"{Colors.BOLD}{'='*60}{Colors.RESET}")

    # Get configuration from environment or use defaults
    base_url = os.environ.get('MCP_SERVER_URL', 'https://api.c4dhi.org')
    api_key = os.environ.get('MCP_API_KEY', '')

    if not api_key:
        print_error("MCP_API_KEY environment variable is not set")
        print_info("Usage: MCP_API_KEY=your-key python3 test_connection.py")
        sys.exit(1)

    print_info(f"Testing server at: {base_url}")
    print()

    # Run tests
    results = []
    results.append(("Health Check", test_health_check(base_url)))
    results.append(("API Key Authentication", test_api_key_validation(base_url, api_key)))
    results.append(("MCP Initialization", bool(test_mcp_initialization(base_url, api_key))))
    results.append(("List Tools", test_list_tools(base_url, api_key)))
    results.append(("MCP Info", test_mcp_info(base_url, api_key)))

    # Summary
    print(f"\n{Colors.BOLD}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}Test Summary{Colors.RESET}")
    print(f"{Colors.BOLD}{'='*60}{Colors.RESET}")

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = f"{Colors.GREEN}PASS{Colors.RESET}" if result else f"{Colors.RED}FAIL{Colors.RESET}"
        print(f"{test_name}: {status}")

    print(f"\n{Colors.BOLD}Result: {passed}/{total} tests passed{Colors.RESET}")

    if passed == total:
        print_success("All tests passed! Your server is ready to use with Claude Desktop.")
        sys.exit(0)
    else:
        print_error(f"{total - passed} test(s) failed. Please check your configuration.")
        sys.exit(1)


if __name__ == '__main__':
    main()
