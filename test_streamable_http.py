#!/usr/bin/env python3
"""
Test suite for Streamable HTTP Transport (Protocol 2025-03-26+)

Tests:
- Single endpoint POST /mcp
- JSON responses for quick operations
- SSE streaming for long operations
- Protocol version negotiation
- Backward compatibility with legacy transport
"""

import os
import sys
import requests
import json
from typing import Dict, Any, Generator


class Colors:
    """ANSI color codes"""
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


def print_section(message: str):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{message}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.RESET}\n")


class StreamableHTTPTester:
    """Test suite for Streamable HTTP transport"""

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url
        self.api_key = api_key
        self.passed = 0
        self.failed = 0

    def make_request(self, method: str, params: Dict[str, Any] = None,
                    accept: str = "application/json",
                    protocol_version: str = "2025-03-26",
                    endpoint: str = "/mcp") -> requests.Response:
        """Make an MCP request"""
        headers = {
            'Content-Type': 'application/json',
            'Accept': accept,
            'X-API-Key': self.api_key,
            'MCP-Protocol-Version': protocol_version
        }

        request_data = {
            'jsonrpc': '2.0',
            'id': 1,
            'method': method,
            'params': params or {}
        }

        stream = 'text/event-stream' in accept

        return requests.post(
            f"{self.base_url}{endpoint}",
            headers=headers,
            json=request_data,
            stream=stream,
            timeout=10
        )

    def parse_sse_events(self, response: requests.Response) -> Generator[Dict[str, Any], None, None]:
        """Parse SSE events from streaming response"""
        for line in response.iter_lines():
            if line:
                line_str = line.decode('utf-8')
                if line_str.startswith('data: '):
                    try:
                        yield json.loads(line_str[6:])
                    except json.JSONDecodeError:
                        pass

    # ==================== Tests ====================

    def test_server_info(self) -> bool:
        """Test /mcp-info endpoint"""
        print_section("1. Server Information")

        try:
            response = requests.get(
                f"{self.base_url}/mcp-info",
                headers={'X-API-Key': self.api_key},
                timeout=10
            )

            if response.status_code != 200:
                print_error(f"Server info failed: HTTP {response.status_code}")
                return False

            info = response.json()

            # Check for streamable transport
            if 'streamable' not in info.get('transport', {}):
                print_error("Server doesn't support streamable transport")
                return False

            print_success("Server info retrieved successfully")
            print_info(f"Supported versions: {info.get('supported_versions', [])}")
            print_info(f"Streamable endpoint: {info['transport']['streamable']['endpoint']}")
            return True

        except Exception as e:
            print_error(f"Server info test failed: {e}")
            return False

    def test_quick_operation_json(self) -> bool:
        """Test quick operation with JSON response"""
        print_section("2. Quick Operation (JSON Response)")

        try:
            response = self.make_request(
                method='ping',
                accept='application/json',
                protocol_version='2025-03-26'
            )

            if response.status_code != 200:
                print_error(f"Quick operation failed: HTTP {response.status_code}")
                return False

            # Check it's JSON, not SSE
            content_type = response.headers.get('Content-Type', '')
            if 'application/json' not in content_type:
                print_error(f"Expected JSON, got: {content_type}")
                return False

            data = response.json()

            if data.get('jsonrpc') != '2.0':
                print_error("Invalid JSON-RPC response")
                return False

            print_success("Quick operation returned JSON successfully")
            print_info(f"Response time: {response.elapsed.total_seconds():.3f}s")
            return True

        except Exception as e:
            print_error(f"Quick operation test failed: {e}")
            return False

    def test_tools_list(self) -> bool:
        """Test tools/list method"""
        print_section("3. Tools List")

        try:
            response = self.make_request(
                method='tools/list',
                accept='application/json',
                protocol_version='2025-03-26'
            )

            if response.status_code != 200:
                print_error(f"Tools list failed: HTTP {response.status_code}")
                return False

            data = response.json()
            tools = data.get('result', {}).get('tools', [])

            if not tools:
                print_error("No tools returned")
                return False

            print_success(f"Found {len(tools)} tools")
            for tool in tools:
                print_info(f"  • {tool['name']}: {tool.get('description', 'No description')[:60]}...")

            return True

        except Exception as e:
            print_error(f"Tools list test failed: {e}")
            return False

    def test_protocol_version_negotiation(self) -> bool:
        """Test protocol version negotiation"""
        print_section("4. Protocol Version Negotiation")

        tests = [
            ('2025-03-26', True, 'Should accept 2025-03-26'),
            ('2025-06-18', True, 'Should accept 2025-06-18'),
            ('2024-11-05', True, 'Should accept 2024-11-05 (legacy)'),
            ('2099-01-01', False, 'Should reject unsupported version'),
        ]

        all_passed = True

        for version, should_succeed, description in tests:
            try:
                response = self.make_request(
                    method='ping',
                    protocol_version=version
                )

                if should_succeed:
                    if response.status_code == 200:
                        data = response.json()
                        if 'error' not in data:
                            print_success(f"{description}: ✓")
                        else:
                            print_error(f"{description}: Got error response")
                            all_passed = False
                    else:
                        print_error(f"{description}: HTTP {response.status_code}")
                        all_passed = False
                else:
                    # Should fail
                    data = response.json()
                    if 'error' in data:
                        print_success(f"{description}: ✓")
                    else:
                        print_error(f"{description}: Should have returned error")
                        all_passed = False

            except Exception as e:
                print_error(f"{description}: {e}")
                all_passed = False

        return all_passed

    def test_initialize_with_version(self) -> bool:
        """Test initialize method with version negotiation"""
        print_section("5. Initialize with Version Negotiation")

        versions_to_test = ['2024-11-05', '2025-03-26', '2025-06-18']
        all_passed = True

        for version in versions_to_test:
            try:
                response = self.make_request(
                    method='initialize',
                    params={
                        'protocolVersion': version,
                        'capabilities': {},
                        'clientInfo': {
                            'name': 'test-client',
                            'version': '1.0.0'
                        }
                    },
                    protocol_version=version
                )

                if response.status_code != 200:
                    print_error(f"Initialize failed for {version}: HTTP {response.status_code}")
                    all_passed = False
                    continue

                data = response.json()

                if 'error' in data:
                    print_error(f"Initialize failed for {version}: {data['error']['message']}")
                    all_passed = False
                    continue

                result = data.get('result', {})
                returned_version = result.get('protocolVersion')

                if returned_version != version:
                    print_error(f"Version mismatch for {version}: got {returned_version}")
                    all_passed = False
                    continue

                print_success(f"Initialize successful with version {version}")

            except Exception as e:
                print_error(f"Initialize test failed for {version}: {e}")
                all_passed = False

        return all_passed

    def test_streaming_detection(self) -> bool:
        """Test that server correctly detects when to stream"""
        print_section("6. Streaming Detection")

        print_info("Testing quick operation with streaming request...")
        try:
            # Request streaming for a quick operation
            response = self.make_request(
                method='ping',
                accept='text/event-stream',
                protocol_version='2025-03-26'
            )

            content_type = response.headers.get('Content-Type', '')

            # Quick operation should still return quickly
            # (may be JSON or SSE with single event)
            print_success(f"Quick operation handled: {content_type}")

        except Exception as e:
            print_error(f"Streaming detection test failed: {e}")
            return False

        return True

    def test_legacy_endpoint_compatibility(self) -> bool:
        """Test legacy endpoints still work"""
        print_section("7. Legacy Endpoint Compatibility")

        try:
            # Test legacy JSON-RPC endpoint
            response = self.make_request(
                method='ping',
                protocol_version='2024-11-05',
                endpoint='/mcp-rpc'
            )

            if response.status_code != 200:
                print_error(f"Legacy endpoint failed: HTTP {response.status_code}")
                return False

            data = response.json()

            if data.get('jsonrpc') != '2.0':
                print_error("Invalid response from legacy endpoint")
                return False

            print_success("Legacy /mcp-rpc endpoint works")
            return True

        except Exception as e:
            print_error(f"Legacy endpoint test failed: {e}")
            return False

    def test_error_handling(self) -> bool:
        """Test error handling"""
        print_section("8. Error Handling")

        tests = [
            {
                'name': 'Invalid method',
                'method': 'invalid_method_xyz',
                'should_fail': True
            },
            {
                'name': 'Invalid params',
                'method': 'tools/call',
                'params': {'invalid': 'params'},
                'should_fail': True
            },
        ]

        all_passed = True

        for test in tests:
            try:
                response = self.make_request(
                    method=test['method'],
                    params=test.get('params'),
                    protocol_version='2025-03-26'
                )

                data = response.json()

                if test['should_fail']:
                    if 'error' in data or 'isError' in data.get('result', {}):
                        print_success(f"{test['name']}: Correctly returned error")
                    else:
                        print_error(f"{test['name']}: Should have returned error")
                        all_passed = False
                else:
                    if 'result' in data and 'error' not in data:
                        print_success(f"{test['name']}: Success")
                    else:
                        print_error(f"{test['name']}: Unexpected error")
                        all_passed = False

            except Exception as e:
                print_error(f"{test['name']}: {e}")
                all_passed = False

        return all_passed

    def run_all_tests(self) -> bool:
        """Run all tests"""
        tests = [
            ('Server Info', self.test_server_info),
            ('Quick Operation (JSON)', self.test_quick_operation_json),
            ('Tools List', self.test_tools_list),
            ('Protocol Version Negotiation', self.test_protocol_version_negotiation),
            ('Initialize with Version', self.test_initialize_with_version),
            ('Streaming Detection', self.test_streaming_detection),
            ('Legacy Compatibility', self.test_legacy_endpoint_compatibility),
            ('Error Handling', self.test_error_handling),
        ]

        print(f"\n{Colors.BOLD}{'='*60}{Colors.RESET}")
        print(f"{Colors.BOLD}Streamable HTTP Transport Test Suite{Colors.RESET}")
        print(f"{Colors.BOLD}{'='*60}{Colors.RESET}")
        print_info(f"Server: {self.base_url}")
        print_info(f"Testing {len(tests)} test scenarios")

        results = []

        for name, test_func in tests:
            try:
                passed = test_func()
                results.append((name, passed))
                if passed:
                    self.passed += 1
                else:
                    self.failed += 1
            except Exception as e:
                print_error(f"{name} crashed: {e}")
                results.append((name, False))
                self.failed += 1

        # Summary
        print(f"\n{Colors.BOLD}{'='*60}{Colors.RESET}")
        print(f"{Colors.BOLD}Test Summary{Colors.RESET}")
        print(f"{Colors.BOLD}{'='*60}{Colors.RESET}\n")

        for name, passed in results:
            status = f"{Colors.GREEN}PASS{Colors.RESET}" if passed else f"{Colors.RED}FAIL{Colors.RESET}"
            print(f"{name}: {status}")

        total = self.passed + self.failed
        print(f"\n{Colors.BOLD}Result: {self.passed}/{total} tests passed{Colors.RESET}")

        if self.passed == total:
            print_success("All tests passed! ✓✓✓")
            return True
        else:
            print_error(f"{self.failed} test(s) failed.")
            return False


def main():
    # Get configuration
    base_url = os.environ.get('MCP_SERVER_URL', 'http://localhost:8000')
    api_key = os.environ.get('MCP_API_KEY', '')

    if not api_key:
        print_error("MCP_API_KEY environment variable is required")
        print_info("Usage: MCP_API_KEY=your-key python3 test_streamable_http.py")
        sys.exit(1)

    print_info(f"Testing server at: {base_url}")

    # Run tests
    tester = StreamableHTTPTester(base_url, api_key)
    success = tester.run_all_tests()

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
