#!/usr/bin/env python3
"""
Test authenticated WebSocket connection
"""

import asyncio
import websockets
import json
import requests

async def test_authenticated():
    """Test authenticated WebSocket connection"""
    
    # 1. Get authentication token
    print("🔑 Getting authentication token...")
    try:
        response = requests.get("http://127.0.0.1:8000/auth/token")
        token_data = response.json()
        token = token_data["token"]
        print(f"✅ Got token: {token[:16]}...")
    except Exception as e:
        print(f"❌ Failed to get token: {e}")
        return
    
    # 2. Connect with token
    print("\n🔗 Connecting to authenticated WebSocket...")
    uri = f"ws://127.0.0.1:8000/ws?token={token}"
    
    try:
        async with websockets.connect(uri) as ws:
            print("✅ Authenticated connection established")
            
            # Test ping
            await ws.send(json.dumps({"type": "ping", "timestamp": 1234567890}))
            response = await ws.recv()
            data = json.loads(response)
            print(f"✅ Pong response: {data}")
            
            # Test status
            await ws.send(json.dumps({"type": "status"}))
            response = await ws.recv()
            data = json.loads(response)
            print(f"✅ Status response: {json.dumps(data, indent=2)}")
            
    except Exception as e:
        print(f"❌ Authenticated connection failed: {e}")

async def test_unauthorized():
    """Test unauthorized connection (should fail)"""
    
    print("\n🚫 Testing unauthorized connection...")
    uri = "ws://127.0.0.1:8000/ws"  # No token
    
    try:
        async with websockets.connect(uri) as ws:
            print("❌ Unexpected success - should have failed")
    except Exception as e:
        print(f"✅ Correctly rejected: {e}")

async def main():
    print("🚀 Testing Authenticated WebSocket")
    print("=" * 40)
    
    await test_unauthorized()
    await test_authenticated()
    
    print("\n" + "=" * 40)
    print("🏁 Auth tests complete")

if __name__ == "__main__":
    asyncio.run(main())
