# test_ws.py
import asyncio
import websockets
import json

async def test():
    uri = "ws://127.0.0.1:8000/ws"

    async with websockets.connect(uri) as ws:
        print("Connected")

        await ws.send(json.dumps({"type": "ping"}))
        response = await ws.recv()
        print("Server:", response)

asyncio.run(test())
