#!/bin/bash

echo "=== API Key Authentication Test ==="
echo ""

echo "1. Testing without API key (should fail):"
curl -i http://localhost:8081/health
echo ""
echo ""

echo "2. Testing with correct API key (should succeed):"
curl -i -H "X-API-Key: test-secret-key-12345" http://localhost:8081/health
echo ""
echo ""

echo "3. Testing with wrong API key (should fail):"
curl -i -H "X-API-Key: wrong-key" http://localhost:8081/health
echo ""
echo ""

echo "4. Testing case sensitivity (should fail):"
curl -i -H "x-api-key: test-secret-key-12345" http://localhost:8081/health
echo ""
echo ""

echo "5. Testing MCP endpoint with correct API key:"
curl -i -H "X-API-Key: test-secret-key-12345" http://localhost:8081/mcp-info
echo ""
echo ""

echo "6. Testing root endpoint with correct API key:"
curl -i -H "X-API-Key: test-secret-key-12345" http://localhost:8081/
echo ""
echo ""

echo "=== Current API key in container ==="
docker-compose exec app printenv API_KEY