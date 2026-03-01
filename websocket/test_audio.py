#!/usr/bin/env python3
"""
Test audio processing through WebSocket
"""

import asyncio
import websockets
import json
import numpy as np

def generate_test_audio(duration_seconds=1.0, sample_rate=16000):
    """Generate test audio data (sine wave)"""
    t = np.linspace(0, duration_seconds, int(sample_rate * duration_seconds))
    frequency = 440  # A4 note
    audio = np.sin(2 * np.pi * frequency * t) * 0.3
    
    # Convert to 16-bit PCM
    audio_bytes = (audio * 32767).astype(np.int16).tobytes()
    return audio_bytes

async def test_audio_processing():
    """Test audio processing pipeline"""
    
    print("🎵 Testing Audio Processing")
    print("=" * 30)
    
    uri = "ws://127.0.0.1:8000/ws/public"
    
    try:
        async with websockets.connect(uri) as ws:
            print("✅ Connected for audio test")
            
            # Generate test audio
            audio_data = generate_test_audio(2.0)  # 2 seconds
            print(f"🎶 Generated {len(audio_data)} bytes of test audio")
            
            # Send audio data
            await ws.send(audio_data)
            print("📤 Sent audio data")
            
            # Wait for response
            try:
                response = await asyncio.wait_for(ws.recv(), timeout=5.0)
                
                if isinstance(response, bytes):
                    print(f"📥 Received audio response: {len(response)} bytes")
                    print("✅ Audio echo successful")
                else:
                    data = json.loads(response)
                    print(f"📥 Received text response: {data}")
                    
            except asyncio.TimeoutError:
                print("⏰ No response received (timeout)")
            
            # Test status
            await ws.send(json.dumps({"type": "status"}))
            response = await ws.recv()
            data = json.loads(response)
            
            print("📊 Audio Processor Status:")
            audio_status = data["server_status"]["audio_processor"]
            for key, value in audio_status.items():
                print(f"  {key}: {value}")
                
    except Exception as e:
        print(f"❌ Audio test failed: {e}")

async def test_multiple_chunks():
    """Test sending multiple audio chunks"""
    
    print("\n🔄 Testing Multiple Audio Chunks")
    print("=" * 40)
    
    uri = "ws://127.0.0.1:8000/ws/public"
    
    try:
        async with websockets.connect(uri) as ws:
            print("✅ Connected for chunk test")
            
            # Send multiple small chunks
            chunk_size = 1024  # 1KB chunks
            total_audio = generate_test_audio(3.0)  # 3 seconds total
            
            chunks_sent = 0
            for i in range(0, len(total_audio), chunk_size):
                chunk = total_audio[i:i+chunk_size]
                await ws.send(chunk)
                chunks_sent += 1
                print(f"📤 Sent chunk {chunks_sent}: {len(chunk)} bytes")
                
                # Small delay between chunks
                await asyncio.sleep(0.1)
            
            print(f"✅ Sent {chunks_sent} chunks total")
            
            # Wait for final response
            try:
                response = await asyncio.wait_for(ws.recv(), timeout=3.0)
                if isinstance(response, bytes):
                    print(f"📥 Final audio response: {len(response)} bytes")
                else:
                    print(f"📥 Final response: {response}")
            except asyncio.TimeoutError:
                print("⏰ No final response")
                
    except Exception as e:
        print(f"❌ Chunk test failed: {e}")

async def main():
    await test_audio_processing()
    await test_multiple_chunks()
    
    print("\n" + "=" * 30)
    print("🏁 Audio tests complete")

if __name__ == "__main__":
    asyncio.run(main())
