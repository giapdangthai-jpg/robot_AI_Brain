import asyncio
import numpy as np
from typing import Optional, Callable
from app.utils.logger import logger
from app.stt.whisper_engine import WhisperEngine
from app.llm.llm_client import LLMClient
from app.tts.piper_engine import PiperEngine

class AudioProcessor:
    def __init__(self):
        self.whisper_engine: Optional[WhisperEngine] = None
        self.llm_client: Optional[LLMClient] = None
        self.tts_engine: Optional[PiperEngine] = None
        self.is_processing = False
        self.audio_buffer = []
        self.buffer_size = 4096  # bytes
        self.error_count = 0
        self.max_errors = 5
        
    async def initialize(self):
        """Initialize audio processing components"""
        try:
            logger.info("Initializing audio processor...")
            
            # Initialize components (will be implemented later)
            # self.whisper_engine = WhisperEngine()
            # self.llm_client = LLMClient()
            # self.tts_engine = PiperEngine()
            
            # await self.whisper_engine.initialize()
            # await self.llm_client.initialize()
            # await self.tts_engine.initialize()
            
            logger.info("Audio processor initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize audio processor: {e}")
            raise
    
    async def process_audio_chunk(self, audio_data: bytes) -> Optional[bytes]:
        """Process incoming audio chunk and return response audio"""
        if self.is_processing:
            logger.warning("Audio processor busy, dropping chunk")
            return None
        
        try:
            self.is_processing = True
            
            # Add to buffer
            self.audio_buffer.append(audio_data)
            
            # Process when buffer is full
            if len(b''.join(self.audio_buffer)) >= self.buffer_size:
                return await self._process_buffer()
            
            return None
            
        except Exception as e:
            logger.error(f"Error processing audio chunk: {e}")
            self.error_count += 1
            
            # Reset on too many errors
            if self.error_count >= self.max_errors:
                logger.warning("Too many errors, resetting audio processor")
                await self._reset_processor()
            
            return None
        
        finally:
            self.is_processing = False
    
    async def _process_buffer(self) -> Optional[bytes]:
        """Process accumulated audio buffer"""
        try:
            # Combine buffer
            audio_chunk = b''.join(self.audio_buffer)
            self.audio_buffer.clear()
            
            logger.debug(f"Processing audio chunk: {len(audio_chunk)} bytes")
            
            # TODO: Implement full pipeline
            # 1. Speech-to-text
            # text = await self.whisper_engine.transcribe(audio_chunk)
            
            # 2. LLM processing
            # response_text = await self.llm_client.generate_response(text)
            
            # 3. Text-to-speech
            # response_audio = await self.tts_engine.synthesize(response_text)
            
            # For now, just echo back
            return audio_chunk
            
        except Exception as e:
            logger.error(f"Error in audio processing pipeline: {e}")
            return None
    
    async def _reset_processor(self):
        """Reset processor after errors"""
        self.audio_buffer.clear()
        self.error_count = 0
        self.is_processing = False
        
        # Reinitialize if needed
        try:
            await self.initialize()
        except Exception as e:
            logger.error(f"Failed to reset audio processor: {e}")
    
    def get_status(self) -> dict:
        """Get processor status"""
        return {
            "is_processing": self.is_processing,
            "buffer_size": len(b''.join(self.audio_buffer)),
            "error_count": self.error_count,
            "components_initialized": {
                "whisper": self.whisper_engine is not None,
                "llm": self.llm_client is not None,
                "tts": self.tts_engine is not None
            }
        }

# Global audio processor instance
audio_processor = AudioProcessor()
