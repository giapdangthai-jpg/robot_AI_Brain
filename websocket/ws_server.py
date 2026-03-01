# app/websocket/ws_server.py

import asyncio
import numpy as np
import json
from fastapi import WebSocket
from app.utils.logger import logger
from app.pipeline.audio_processor import audio_processor
from app.llm.llm_client import LLMClient
from app.tts.piper_engine import PiperEngine


class RobotWebSocket:

    def __init__(self):
        self.clients = []
        self.client_stats = {}  # Track client statistics
        self.llm_client = LLMClient()
        self.tts_engine = PiperEngine()

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
                    await self._handle_text_message(websocket, client_id, message['text'])

                elif message.get("bytes") is not None:
                    await self._handle_binary_message(websocket, client_id, message['bytes'])

        except Exception as e:
            logger.error(f"Unexpected WS error {client_id}: {e}")

        finally:
            if websocket in self.clients:
                self.clients.remove(websocket)

            logger.info(f"Cleanup {client_id}")

    async def _handle_text_message(self, websocket: WebSocket, client_id: str, text_message: str):
        """Handle text messages from ESP32"""
        try:
            logger.info(f"TEXT from {client_id}: {text_message}")
            
            # Try to parse as JSON first
            try:
                message_data = json.loads(text_message)
                message_type = message_data.get("type", "text")
                content = message_data.get("content", text_message)
            except json.JSONDecodeError:
                # Treat as plain text
                message_type = "text"
                content = text_message
            
            if message_type == "device_info":
                # Save device info for observability
                self.client_stats[client_id] = {
                    **self.client_stats.get(client_id, {}),
                    "device_info": message_data,
                }
                await self._safe_send_text(websocket, json.dumps({
                    "type": "device_info_ack",
                    "status": "ok",
                }))
            elif message_type == "text":
                # Process text through LLM -> TTS pipeline
                await self._process_text_to_audio(websocket, client_id, content)
            elif message_type == "command":
                # Handle direct commands
                await self._handle_command(websocket, client_id, content)
            else:
                logger.warning(f"Unknown message type: {message_type}")
                
        except Exception as e:
            logger.error(f"Error handling text message from {client_id}: {e}")
            await self._safe_send_text(websocket, json.dumps({
                "type": "error",
                "message": "Failed to process text message"
            }))
    
    async def _handle_binary_message(self, websocket: WebSocket, client_id: str, binary_data: bytes):
        """Handle binary audio data from ESP32"""
        try:
            logger.debug(f"Binary from {client_id}: {len(binary_data)} bytes")
            
            # Process audio through pipeline (STT -> LLM -> TTS)
            # For now, just echo back to confirm receipt
            await self._safe_send_bytes(websocket, binary_data)
            
        except Exception as e:
            logger.error(f"Error handling binary message from {client_id}: {e}")
    
    async def _process_text_to_audio(self, websocket: WebSocket, client_id: str, text: str):
        """Process text through LLM -> TTS pipeline"""
        try:
            logger.info(f"Processing text from {client_id}: {text}")
            
            # Step 1: Generate response using LLM
            llm_response = await self.llm_client.generate_response(text)
            logger.info(f"LLM response: {llm_response}")
            
            # Step 2: Convert response to speech using TTS
            audio_data = await self.tts_engine.synthesize(llm_response)
            logger.info(f"Generated audio: {len(audio_data)} bytes")
            
            # Step 3: Send response back to ESP32
            response_data = {
                "type": "response",
                "text": llm_response,
                "timestamp": asyncio.get_event_loop().time()
            }
            await self._safe_send_text(websocket, json.dumps(response_data))
            
            # Step 4: Send audio data
            if audio_data:
                await self._safe_send_bytes(websocket, audio_data)
                logger.info(f"Sent text response and audio to {client_id}")
            else:
                logger.warning(f"No audio data generated for {client_id}")
                
        except Exception as e:
            logger.error(f"Error in text-to-audio pipeline for {client_id}: {e}")
            # Send error response
            error_response = {
                "type": "error",
                "message": "Failed to process text",
                "error": str(e)
            }
            await self._safe_send_text(websocket, json.dumps(error_response))
    
    async def _handle_command(self, websocket: WebSocket, client_id: str, command: str):
        """Handle direct commands from ESP32"""
        try:
            logger.info(f"Command from {client_id}: {command}")
            
            # Process command (bark, wag, sit, etc.)
            response_data = {
                "type": "command_response",
                "command": command,
                "status": "executed",
                "timestamp": asyncio.get_event_loop().time()
            }
            await self._safe_send_text(websocket, json.dumps(response_data))
            
        except Exception as e:
            logger.error(f"Error handling command from {client_id}: {e}")

    async def _safe_send_text(self, websocket: WebSocket, text: str) -> bool:
        """Best-effort send that won't crash the WS loop if the peer disconnected."""
        try:
            if getattr(websocket, "application_state", None) and str(websocket.application_state) != "WebSocketState.CONNECTED":
                return False
            await websocket.send_text(text)
            return True
        except Exception as e:
            logger.debug(f"Safe send_text failed: {e}")
            return False

    async def _safe_send_bytes(self, websocket: WebSocket, data: bytes) -> bool:
        """Best-effort send that won't crash the WS loop if the peer disconnected."""
        try:
            if getattr(websocket, "application_state", None) and str(websocket.application_state) != "WebSocketState.CONNECTED":
                return False
            await websocket.send_bytes(data)
            return True
        except Exception as e:
            logger.debug(f"Safe send_bytes failed: {e}")
            return False
    
    async def initialize_pipeline(self):
        """Initialize LLM and TTS components"""
        try:
            await self.llm_client.initialize()
            await self.tts_engine.initialize()
            logger.info("WebSocket pipeline initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize pipeline: {e}")
            raise

    async def close_pipeline(self):
        """Close LLM/TTS resources on shutdown."""
        try:
            close_fn = getattr(self.llm_client, "close", None)
            if callable(close_fn):
                await close_fn()
        except Exception as e:
            logger.warning(f"Failed to close LLM client: {e}")
    
    def get_client_stats(self) -> dict:
        """Get statistics for all connected clients"""
        return {
            "total_clients": len(self.clients),
            "client_details": self.client_stats,
            "llm_status": self.llm_client.get_status(),
            "tts_status": self.tts_engine.get_status()
        }
