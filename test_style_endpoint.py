#!/usr/bin/env python3
"""
Quick test script for the writing style analysis endpoint
"""
import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

def test_style_endpoint():
    # Test data - style instructions for podcast generation
    test_instructions = [
        "Talk like Trump",
        "Speak like a university professor",
        "Sound like Joe Rogan",
        "Talk like a southern preacher"
    ]
    
    for instruction in test_instructions:
        print(f"\n🎯 Testing instruction: '{instruction}'")
        
        # Test request
        payload = {
            "prompt": instruction,
            "credentials": {
                "gemini_api_key": os.getenv("GEMINI_API_KEY")
            }
        }
        
        try:
            # Assuming the server runs on localhost:8000
            response = requests.post("http://localhost:8000/mcp/analyze-style", json=payload)
            
            if response.status_code == 200:
                result = response.json()
                print("✅ Endpoint working successfully!")
                print(f"Tone: {result.get('tone')}")
                print(f"Pace: {result.get('pace')}")
                print(f"Key Phrases: {result.get('keyPhrases')}")
                print(f"Additional Instructions: {result.get('additionalInstructions')}")
            else:
                print(f"❌ Error: {response.status_code}")
                print(response.text)
                
        except requests.exceptions.ConnectionError:
            print("❌ Could not connect to server. Make sure the FastAPI server is running.")
            break
        except Exception as e:
            print(f"❌ Unexpected error: {e}")

if __name__ == "__main__":
    test_style_endpoint()