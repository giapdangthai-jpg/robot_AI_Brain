# app/websocket/ws_server.py

import asyncio
import numpy as np
import json
from fastapi import WebSocket
from app.utils.logger import logger
from app.pipeline.audio_processor import audio_processor
from fastapi import WebSocket, WebSocketDisconnect


class RobotWebSocket:

    def __init__(self):
        self.clients = []
        self.client_stats = {}  # Track client statistics

    async def handle(self, websocket: WebSocket):
        client_id = f"{websocket.client.host}:{websocket.client.port}"

        await websocket.accept()
        self.clients.append(websocket)

        logger.info(f"Client connected: {client_id}")

        try:
            while True:
                message = await websocket.receive()

                # ⭐ QUAN TRỌNG: check disconnect event
                if message["type"] == "websocket.disconnect":
                    logger.info(f"Client disconnected: {client_id}")
                    break

                if message.get("text") is not None:
                    logger.info(f"TEXT from {client_id}: {message['text']}")

                elif message.get("bytes") is not None:
                    logger.debug(f"Binary from {client_id}: {len(message['bytes'])} bytes")

        except WebSocketDisconnect:
            logger.info(f"WebSocketDisconnect exception: {client_id}")

        except Exception as e:
            logger.error(f"Unexpected WS error {client_id}: {e}")

        finally:
            if websocket in self.clients:
                self.clients.remove(websocket)

            logger.info(f"Cleanup {client_id}")

    def get_client_stats(self) -> dict:
        """Get statistics for all connected clients"""
        return {
            "total_clients": len(self.clients),
            "client_details": self.client_stats
        }
    
    async def broadcast_message(self, message: dict, exclude_client=None):
        """Broadcast message to all connected clients"""
        message_str = json.dumps(message)
        disconnected_clients = []
        
        for client in self.clients:
            if client != exclude_client:
                try:
                    await client.send_text(message_str)
                except Exception as e:
                    logger.error(f"Failed to send broadcast message: {e}")
                    disconnected_clients.append(client)
        
        # Remove disconnected clients
        for client in disconnected_clients:
            if client in self.clients:
                self.clients.remove(client)
