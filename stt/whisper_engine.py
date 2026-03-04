import asyncio
import os
from typing import Optional

import numpy as np
from faster_whisper import WhisperModel

from app.utils.logger import logger

class WhisperEngine:
    """Speech-to-Text engine using Whisper (placeholder implementation)"""
    
    def __init__(self):
        self.model_loaded = False
        self.model_name = os.environ.get("WHISPER_MODEL", "small")
        self.device = os.environ.get("WHISPER_DEVICE", "cpu")
        self.compute_type = os.environ.get("WHISPER_COMPUTE_TYPE", "int8")
        self.language = os.environ.get("WHISPER_LANGUAGE")
        self.model: Optional[WhisperModel] = None
    
    async def initialize(self):
        """Initialize Whisper model"""
        try:
            logger.info("Initializing Whisper engine...")

            def _load_model():
                return WhisperModel(self.model_name, device=self.device, compute_type=self.compute_type)

            self.model = await asyncio.to_thread(_load_model)
            self.model_loaded = True
            logger.info("Whisper engine initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Whisper engine: {e}")
            raise
    
    async def transcribe(self, audio_data: bytes) -> str:
        """Transcribe audio data to text"""
        if not self.model_loaded or not self.model:
            raise RuntimeError("Whisper engine not initialized")
        
        try:
            logger.debug(f"Transcribing {len(audio_data)} bytes of audio")

            # Assumption: raw PCM int16 mono @ 16kHz
            pcm = np.frombuffer(audio_data, dtype=np.int16)
            if pcm.size == 0:
                return ""
            audio = (pcm.astype(np.float32) / 32768.0).copy()

            def _do_transcribe():
                segments, _info = self.model.transcribe(
                    audio,
                    language=self.language,
                    vad_filter=True,
                )
                parts = []
                for seg in segments:
                    if seg.text:
                        parts.append(seg.text)
                return "".join(parts).strip()

            text = await asyncio.to_thread(_do_transcribe)
            return text
            
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            raise
    
    def get_status(self) -> dict:
        """Get engine status"""
        return {
            "model_loaded": self.model_loaded,
            "model_name": self.model_name,
            "engine_type": "whisper_stt"
        }