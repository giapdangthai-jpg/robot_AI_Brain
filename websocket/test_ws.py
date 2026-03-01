# test_ws.py
import asyncio
import websockets
import json

async def test():
    # Use public endpoint (no auth required) and default port
    uri = "ws://127.0.0.1:8000/ws/public"

    async with websockets.connect(uri) as ws:
        print("Connected")

        await ws.send(json.dumps({"type": "ping", "timestamp": 1234567890}))
        response = await ws.recv()
        print("Server:", response)

asyncio.run(test())
