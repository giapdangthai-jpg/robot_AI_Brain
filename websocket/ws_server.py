# app/websocket/ws_server.py

import asyncio
import numpy as np
import json
import os
from fastapi import WebSocket
from app.utils.logger import logger
from app.pipeline.audio_processor import audio_processor
from app.llm.llm_client import LLMClient
from app.stt.whisper_engine import WhisperEngine
from app.tts.piper_engine import PiperEngine


class RobotWebSocket:

    def __init__(self):
        self.clients = []
        self.client_stats = {}  # Track client statistics
        self.audio_buffers = {}  # client_id -> bytearray
        self._audio_remainders = {}  # client_id -> bytes (0 or 1 byte) for int16 alignment
        self.min_audio_bytes_for_stt = 16000  # ~0.5s @ 16kHz 16-bit mono
        self.force_process_audio_bytes = 160000  # ~5.0s @ 16kHz 16-bit mono
        self.max_audio_bytes_per_utterance = 320000  # cap buffer growth
        self.audio_idle_flush_seconds = 0.4
        self._last_audio_rx_time = {}  # client_id -> loop.time()
        self._idle_flush_tasks = {}  # client_id -> asyncio.Task
        try:
            self.ws_tts_chunk_bytes = int(os.environ.get("WS_TTS_CHUNK_BYTES", "0"))
        except Exception:
            self.ws_tts_chunk_bytes = 0
        self.ws_tts_send_markers = os.environ.get("WS_TTS_SEND_MARKERS", "0") == "1"
        self.ws_tts_pace = os.environ.get("WS_TTS_PACE", "0") == "1"
        try:
            self.ws_tts_pace_factor = float(os.environ.get("WS_TTS_PACE_FACTOR", "1.0"))
        except Exception:
            self.ws_tts_pace_factor = 1.0
        try:
            self.ws_tts_auto_chunk_over_bytes = int(os.environ.get("WS_TTS_AUTO_CHUNK_OVER", "32768"))
        except Exception:
            self.ws_tts_auto_chunk_over_bytes = 32768
        try:
            self.ws_tts_auto_chunk_bytes = int(os.environ.get("WS_TTS_AUTO_CHUNK_BYTES", "4096"))
        except Exception:
            self.ws_tts_auto_chunk_bytes = 4096
        self.ws_tts_auto_pace = os.environ.get("WS_TTS_AUTO_PACE", "1") == "1"
        self.stt_engine = WhisperEngine()
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
                    code = message.get("code")
                    reason = message.get("reason")
                    if code is not None or reason is not None:
                        logger.info(f"Client disconnected: {client_id} (code={code}, reason={reason})")
                    else:
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

            try:
                t = self._idle_flush_tasks.get(client_id)
                if t and not t.done():
                    t.cancel()
            except Exception:
                pass

            try:
                self.audio_buffers.pop(client_id, None)
                self._audio_remainders.pop(client_id, None)
                self._last_audio_rx_time.pop(client_id, None)
                self._idle_flush_tasks.pop(client_id, None)
            except Exception:
                pass

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
            elif message_type == "audio_end":
                await self._flush_audio_buffer(websocket, client_id)
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
            logger.info(f"Binary from {client_id}: {len(binary_data)} bytes")

            if not binary_data:
                return

            # Ensure int16 alignment across frames: if we previously had an odd remainder byte,
            # prepend it so np.frombuffer(..., int16) won't mis-align.
            rem = self._audio_remainders.get(client_id)
            if rem:
                binary_data = rem + binary_data
                self._audio_remainders[client_id] = b""

            if len(binary_data) % 2 == 1:
                # Keep last byte for next message.
                self._audio_remainders[client_id] = binary_data[-1:]
                binary_data = binary_data[:-1]

            if not binary_data:
                return

            buf = self.audio_buffers.get(client_id)
            if buf is None:
                buf = bytearray()
                self.audio_buffers[client_id] = buf

            buf.extend(binary_data)

            logger.info(f"Audio buffer {client_id}: {len(buf)} bytes")

            # Schedule/refresh idle flush (so short utterances get processed even without audio_end)
            now = asyncio.get_event_loop().time()
            self._last_audio_rx_time[client_id] = now
            existing_task = self._idle_flush_tasks.get(client_id)
            if existing_task and not existing_task.done():
                existing_task.cancel()
            self._idle_flush_tasks[client_id] = asyncio.create_task(
                self._idle_flush_after(websocket, client_id, now)
            )

            # Prevent unbounded growth if ESP streams continuously.
            if len(buf) > self.max_audio_bytes_per_utterance:
                logger.warning(
                    f"Audio buffer too large for {client_id} ({len(buf)} bytes). Resetting buffer."
                )
                buf.clear()
                self._audio_remainders[client_id] = b""
                return

            # Don't aggressively chop the utterance into 0.5s chunks.
            # Prefer waiting for audio_end or idle flush to get a contiguous phrase.
            # If the buffer grows too large, force process to keep latency bounded.
            if len(buf) >= self.force_process_audio_bytes:
                audio_chunk = bytes(buf)
                buf.clear()
                await self._process_audio_and_respond(websocket, client_id, audio_chunk, flushed=False)

        except Exception as e:
            logger.error(f"Error handling binary message from {client_id}: {e}")
            await self._safe_send_text(websocket, json.dumps({
                "type": "error",
                "message": "Failed to process audio",
                "error": str(e),
            }))

    async def _idle_flush_after(self, websocket: WebSocket, client_id: str, scheduled_at: float):
        try:
            await asyncio.sleep(self.audio_idle_flush_seconds)
            last = self._last_audio_rx_time.get(client_id)
            if last != scheduled_at:
                return

            buf = self.audio_buffers.get(client_id)
            if not buf or len(buf) == 0:
                return

            logger.info(f"Idle flush triggered for {client_id}")
            await self._flush_audio_buffer(websocket, client_id)
        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.debug(f"Idle flush task failed for {client_id}: {e}")

    async def _flush_audio_buffer(self, websocket: WebSocket, client_id: str):
        """Force process current buffered audio (useful when ESP sends audio in a burst then signals end)."""
        try:
            buf = self.audio_buffers.get(client_id)
            if not buf or len(buf) == 0:
                await self._safe_send_text(websocket, json.dumps({
                    "type": "audio_end_ack",
                    "status": "empty",
                }))
                return

            audio_chunk = bytes(buf)
            buf.clear()

            # Drop any dangling remainder when flushing (it is < 1 sample).
            self._audio_remainders[client_id] = b""

            logger.info(f"Flushing audio buffer for {client_id}: {len(audio_chunk)} bytes")

            await self._process_audio_and_respond(websocket, client_id, audio_chunk, flushed=True)

        except Exception as e:
            logger.error(f"Failed to flush audio buffer for {client_id}: {e}")
            await self._safe_send_text(websocket, json.dumps({
                "type": "error",
                "message": "Failed to flush audio buffer",
                "error": str(e),
            }))

    async def _process_audio_and_respond(self, websocket: WebSocket, client_id: str, audio_chunk: bytes, flushed: bool):
        """Run STT -> LLM -> TTS for an audio chunk and send both text + audio back to the client."""
        # 1) STT (Whisper)
        user_text = await self.stt_engine.transcribe(audio_chunk)
        logger.info(f"STT from {client_id}: {user_text}")

        # 2) LLM
        llm_response = await self.llm_client.generate_response(user_text)
        logger.info(f"LLM response: {llm_response}")

        # 3) TTS
        audio_out = await self.tts_engine.synthesize(llm_response)
        logger.info(f"TTS Generated audio: {len(audio_out)} bytes")

        # 4) Send back both text + audio to ESP32
        response_data = {
            "type": "audio_response",
            "user_text": user_text,
            "text": llm_response,
            "timestamp": asyncio.get_event_loop().time(),
        }
        if flushed:
            response_data["flushed"] = True

        await self._safe_send_text(websocket, json.dumps(response_data))
        if audio_out:
            await self._send_tts_audio(websocket, audio_out, meta={"type": "audio_response_audio"})
    
    async def _process_text_to_audio(self, websocket: WebSocket, client_id: str, text: str):
        """Process text through LLM -> TTS pipeline"""
        try:
            logger.info(f"Processing text from {client_id}: {text}")
            
            # Step 1: Generate response using LLM
            llm_response = await self.llm_client.generate_response(text)
            logger.info(f"LLM response: {llm_response}")
            
            # Step 2: Convert response to speech using TTS
            audio_data = await self.tts_engine.synthesize(llm_response)
            logger.info(f"TTS Generated audio: {len(audio_data)} bytes")
            
            # Step 3: Send response back to ESP32
            # Include user_text so ESP32 can parse commands from original speech
            response_data = {
                "type": "response",
                "user_text": text,
                "text": llm_response,
                "timestamp": asyncio.get_event_loop().time()
            }
            await self._safe_send_text(websocket, json.dumps(response_data))
            
            # Step 4: Send audio data
            if audio_data:
                await self._send_tts_audio(websocket, audio_data, meta={"type": "response_audio"})
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

    async def _send_tts_audio(self, websocket: WebSocket, audio_data: bytes, meta: dict | None = None) -> None:
        chunk_bytes = self.ws_tts_chunk_bytes
        if not audio_data:
            return

        auto_chunked = False
        if not chunk_bytes or chunk_bytes <= 0:
            if len(audio_data) > self.ws_tts_auto_chunk_over_bytes:
                chunk_bytes = self.ws_tts_auto_chunk_bytes
                auto_chunked = True
            else:
                await self._safe_send_bytes(websocket, audio_data)
                return

        # Ensure chunk boundary doesn't split int16 samples.
        if chunk_bytes % 2 != 0:
            chunk_bytes -= 1
        if chunk_bytes <= 0:
            await self._safe_send_bytes(websocket, audio_data)
            return

        if meta is None:
            meta = {}

        audio_id = str(int(asyncio.get_event_loop().time() * 1000))
        if self.ws_tts_send_markers:
            start_msg = {
                **meta,
                "type": "audio_start",
                "audio_id": audio_id,
                "total_bytes": len(audio_data),
                "chunk_bytes": chunk_bytes,
                "format": "pcm_s16le",
                "sample_rate": 16000,
                "channels": 1,
            }
            await self._safe_send_text(websocket, json.dumps(start_msg))

        seq = 0
        remainder = b""
        for i in range(0, len(audio_data), chunk_bytes):
            chunk = audio_data[i : i + chunk_bytes]
            if remainder:
                chunk = remainder + chunk
                remainder = b""
            if len(chunk) % 2 == 1:
                remainder = chunk[-1:]
                chunk = chunk[:-1]
            if not chunk:
                continue
            ok = await self._safe_send_bytes(websocket, chunk)
            if not ok:
                return
            seq += 1
            if seq % 8 == 0:
                await asyncio.sleep(0)

            if self.ws_tts_pace or (auto_chunked and self.ws_tts_auto_pace):
                samples = len(chunk) // 2
                seconds = (samples / 16000.0) * max(self.ws_tts_pace_factor, 0.0)
                if seconds > 0:
                    await asyncio.sleep(seconds)

        if remainder:
            # Drop dangling < 1 sample byte. Should be rare, but keep int16 alignment.
            remainder = b""

        if self.ws_tts_send_markers:
            end_msg = {
                **meta,
                "type": "audio_end",
                "audio_id": audio_id,
                "total_bytes": len(audio_data),
                "chunks": seq,
            }
            await self._safe_send_text(websocket, json.dumps(end_msg))
    
    async def initialize_pipeline(self):
        """Initialize LLM and TTS components"""
        try:
            await self.stt_engine.initialize()
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
