#!/usr/bin/env python3
"""
Enhanced WebSocket test client with authentication and rate limiting
"""

import asyncio
import websockets
import json
import time
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent.parent))

# Default server port (will be updated dynamically)
SERVER_PORT = 8000

async def test_authentication():
    """Test authentication flow"""
    print("=== Testing Authentication ===")
    
    # Import auth module
    from app.middleware.auth import auth
    
    # Generate token
    token = auth.generate_token()
    auth.add_token(token)
    print(f"Generated token: {token[:16]}...")
    
    # Test WebSocket with token
    uri = f"ws://127.0.0.1:{SERVER_PORT}/ws?token={token}"
    
    try:
        async with websockets.connect(uri) as ws:
            print("✅ Authenticated WebSocket connected")
            
            # Send ping
            await ws.send(json.dumps({"type": "ping", "timestamp": time.time()}))
            response = await ws.recv()
            data = json.loads(response)
            print(f"✅ Pong response: {data}")
            
    except Exception as e:
        print(f"❌ Auth test failed: {e}")

async def test_public_websocket():
    """Test public WebSocket endpoint"""
    print("\n=== Testing Public WebSocket ===")
    
    uri = f"ws://127.0.0.1:{SERVER_PORT}/ws/public"
    
    try:
        async with websockets.connect(uri) as ws:
            print("✅ Public WebSocket connected")
            
            # Send status request
            await ws.send(json.dumps({"type": "status"}))
            response = await ws.recv()
            data = json.loads(response)
            print(f"✅ Status response: {json.dumps(data, indent=2)}")
            
    except Exception as e:
        print(f"❌ Public WebSocket test failed: {e}")

async def test_rate_limiting():
    """Test rate limiting"""
    print("\n=== Testing Rate Limiting ===")
    
    uri = f"ws://127.0.0.1:{SERVER_PORT}/ws/public"
    
    try:
        async with websockets.connect(uri) as ws:
            print("✅ Connected for rate limiting test")
            
            # Send rapid messages to test rate limit
            for i in range(35):  # Exceed default limit of 30/min
                await ws.send(json.dumps({"type": "ping", "seq": i}))
                try:
                    response = await ws.recv()
                    print(f"Message {i}: ✅")
                except Exception as e:
                    print(f"Message {i}: ❌ Rate limited - {e}")
                    break
                    
    except Exception as e:
        print(f"❌ Rate limiting test failed: {e}")

async def test_health_endpoint():
    """Test health check endpoint"""
    print("\n=== Testing Health Endpoint ===")
    
    try:
        import aiohttp
        
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://127.0.0.1:{SERVER_PORT}/health") as response:
                if response.status == 200:
                    data = await response.json()
                    print("✅ Health check successful")
                    print(f"Status: {json.dumps(data, indent=2)}")
                else:
                    print(f"❌ Health check failed: {response.status}")
                    
    except ImportError:
        print("⚠️  aiohttp not installed, skipping health check")
    except Exception as e:
        print(f"❌ Health check failed: {e}")

async def test_audio_simulation():
    """Test audio data simulation"""
    print("\n=== Testing Audio Simulation ===")
    
    uri = f"ws://127.0.0.1:{SERVER_PORT}/ws/public"
    
    try:
        async with websockets.connect(uri) as ws:
            print("✅ Connected for audio test")
            
            # Simulate audio data (binary)
            audio_data = b'\x00\x01\x02\x03' * 256  # 1KB of dummy audio
            
            await ws.send(audio_data)
            print("✅ Sent audio data")
            
            # Wait for response (echo)
            response = await ws.recv()
            if isinstance(response, bytes):
                print(f"✅ Received audio response: {len(response)} bytes")
            else:
                print(f"✅ Received text response: {response}")
                
    except Exception as e:
        print(f"❌ Audio test failed: {e}")

async def main():
    """Run all tests"""
    global SERVER_PORT
    SERVER_PORT = 8000
    print("🚀 Starting Enhanced WebSocket Tests")
    print("=" * 50)
    
    # Check if server is running
    try:
        import aiohttp
        
        # Try port 8001 first, then 8000
        for port in [8001, 8000]:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"http://127.0.0.1:{port}/health", timeout=2) as response:
                        pass
                print(f"✅ Server is running on port {port}")
                # Update global port for other functions
                SERVER_PORT = port
                break
            except:
                continue
        else:
            print("❌ Server is not running. Please start with:")
            print("   python3 -m uvicorn app.main:app --reload")
            return
    except ImportError:
        print("⚠️  aiohttp not installed, assuming server is on port 8001")
        SERVER_PORT = 8001
    except Exception as e:
        print(f"❌ Error checking server: {e}")
        return
    
    # Run tests
    await test_health_endpoint()
    await test_public_websocket()
    await test_authentication()
    await test_audio_simulation()
    await test_rate_limiting()
    
    print("\n" + "=" * 50)
    print("🏁 Enhanced WebSocket Tests Complete")

if __name__ == "__main__":
    asyncio.run(main())
