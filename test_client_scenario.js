// Test script to simulate your client-side fetch request
// Run with: node test_client_scenario.js

const backendUrl = 'http://localhost:8081';
const apiKey = 'test-secret-key-12345';

async function testHealthEndpoint() {
  console.log('=== Testing Client-Side Fetch Request ===\n');
  
  try {
    console.log('Making fetch request to:', `${backendUrl}/health`);
    console.log('API Key:', apiKey);
    console.log('Method: GET\n');
    
    const response = await fetch(`${backendUrl}/health`, {
      method: 'GET',
      headers: {
        'X-API-Key': apiKey,
      },
    });
    
    console.log('Response Status:', response.status);
    console.log('Response Headers:');
    for (let [key, value] of response.headers.entries()) {
      console.log(`  ${key}: ${value}`);
    }
    console.log();
    
    if (response.ok) {
      const data = await response.json();
      console.log('✅ SUCCESS: Health endpoint responded successfully');
      console.log('Response Data:', JSON.stringify(data, null, 2));
    } else {
      const errorData = await response.text();
      console.log('❌ FAILED: Response not OK');
      console.log('Error Data:', errorData);
    }
    
  } catch (error) {
    console.log('❌ NETWORK ERROR:', error.message);
    console.log('This likely means CORS is blocking the request or the server is not accessible.');
  }
}

// Test with wrong API key
async function testWithWrongKey() {
  console.log('\n=== Testing with Wrong API Key ===\n');
  
  try {
    const response = await fetch(`${backendUrl}/health`, {
      method: 'GET',
      headers: {
        'X-API-Key': 'wrong-key-12345',
      },
    });
    
    console.log('Response Status:', response.status);
    const errorData = await response.text();
    console.log('Error Response:', errorData);
    
  } catch (error) {
    console.log('❌ NETWORK ERROR:', error.message);
  }
}

// Test without API key
async function testWithoutKey() {
  console.log('\n=== Testing without API Key ===\n');
  
  try {
    const response = await fetch(`${backendUrl}/health`, {
      method: 'GET',
      headers: {
        // No X-API-Key header
      },
    });
    
    console.log('Response Status:', response.status);
    const errorData = await response.text();
    console.log('Error Response:', errorData);
    
  } catch (error) {
    console.log('❌ NETWORK ERROR:', error.message);
  }
}

// Run all tests
(async () => {
  await testHealthEndpoint();
  await testWithWrongKey();
  await testWithoutKey();
})();