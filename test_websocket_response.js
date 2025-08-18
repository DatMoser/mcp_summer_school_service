#!/usr/bin/env node

const WebSocket = require('ws');

// Test if WebSocket returns the same complete response as the API
async function testWebSocketResponse() {
    console.log('🔌 Testing WebSocket response structure...');
    
    // Submit a job first
    console.log('📤 Submitting audio job...');
    const response = await fetch('http://localhost:8081/mcp', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-API-Key': 'summer-school-2025'
        },
        body: JSON.stringify({
            mode: 'audio',
            prompt: 'WebSocket test audio job',
            audio_format: 'wav',
            max_duration_seconds: 30,
            generate_thumbnail: false
        })
    });
    
    const jobData = await response.json();
    const jobId = jobData.job_id;
    console.log(`✅ Job submitted: ${jobId}`);
    
    // Connect to WebSocket and wait for completion
    const ws = new WebSocket(`ws://localhost:8081/ws/${jobId}`);
    
    let initialStatus = null;
    let finalStatus = null;
    
    ws.on('open', () => {
        console.log('🔗 WebSocket connected');
    });
    
    ws.on('message', (data) => {
        const message = JSON.parse(data.toString());
        console.log(`📨 WebSocket message: ${message.status} - ${message.current_step}`);
        
        if (!initialStatus) {
            initialStatus = message;
            console.log('📥 Initial status received via WebSocket');
        }
        
        if (message.status === 'finished') {
            finalStatus = message;
            console.log('🎉 Job completion received via WebSocket');
            
            // Compare with API response
            setTimeout(async () => {
                console.log('\n🔍 Comparing WebSocket vs API response...');
                
                const apiResponse = await fetch(`http://localhost:8081/mcp/${jobId}`, {
                    headers: {
                        'X-API-Key': 'summer-school-2025'
                    }
                });
                const apiData = await apiResponse.json();
                
                console.log('\n📊 WebSocket Response:');
                console.log(JSON.stringify(finalStatus, null, 2));
                
                console.log('\n📊 API Response:');
                console.log(JSON.stringify(apiData, null, 2));
                
                // Check if key fields match
                const fieldsToCheck = [
                    'job_id', 'status', 'download_url', 'display_audio_url', 
                    'download_audio_url', 'thumbnail_url', 'progress', 
                    'current_step', 'total_steps', 'step_number'
                ];
                
                let allMatch = true;
                for (const field of fieldsToCheck) {
                    if (finalStatus[field] !== apiData[field]) {
                        console.log(`❌ Mismatch in ${field}:`);
                        console.log(`   WebSocket: ${finalStatus[field]}`);
                        console.log(`   API: ${apiData[field]}`);
                        allMatch = false;
                    }
                }
                
                if (allMatch) {
                    console.log('\n✅ SUCCESS: WebSocket and API responses match perfectly!');
                } else {
                    console.log('\n❌ FAILURE: WebSocket and API responses differ');
                }
                
                // Verify audio-specific fields are present
                if (finalStatus.display_audio_url && finalStatus.download_audio_url) {
                    console.log('✅ Audio-specific URL fields are present in WebSocket response');
                    
                    if (finalStatus.display_audio_url.includes('.mp3') && 
                        finalStatus.download_audio_url.includes('.wav')) {
                        console.log('✅ Correct formats: MP3 for display, WAV for download');
                    } else {
                        console.log('❌ Incorrect audio formats');
                    }
                } else {
                    console.log('❌ Missing audio-specific URL fields in WebSocket response');
                }
                
                ws.close();
                process.exit(allMatch ? 0 : 1);
            }, 2000);
        }
    });
    
    ws.on('error', (error) => {
        console.error('❌ WebSocket error:', error);
        process.exit(1);
    });
    
    // Timeout after 2 minutes
    setTimeout(() => {
        console.log('⏰ Test timeout - job may be taking too long');
        ws.close();
        process.exit(1);
    }, 120000);
}

testWebSocketResponse().catch(console.error);