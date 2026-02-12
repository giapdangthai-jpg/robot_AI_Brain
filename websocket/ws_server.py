# app/websocket/ws_server.py

import asyncio
import numpy as np
from fastapi import WebSocket

class RobotWebSocket:

    def __init__(self):
        self.clients = []

    async def handle(self, websocket: WebSocket):
        await websocket.accept()
        self.clients.append(websocket)

        print("ESP32 connected")

        try:
            while True:
                message = await websocket.receive()

                # Binary audio từ ESP32
                if "bytes" in message and message["bytes"] is not None:
                    pcm_data = message["bytes"]

                    print(f"Received audio chunk: {len(pcm_data)} bytes")

                    # TODO: push vào audio pipeline

                    # Test echo lại cho ESP
                    await websocket.send_bytes(pcm_data)

                # JSON text message
                elif "text" in message and message["text"] is not None:
                    print("Received text:", message["text"])
                    await websocket.send_text("ACK")

        except Exception as e:
            print("Connection closed:", e)

        finally:
            self.clients.remove(websocket)
            print("ESP32 disconnected")
