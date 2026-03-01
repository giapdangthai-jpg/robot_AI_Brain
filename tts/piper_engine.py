import asyncio
import subprocess
import tempfile
import os
import numpy as np
from typing import Optional
from app.utils.logger import logger

class PiperEngine:
    """Text-to-Speech engine using Piper (placeholder implementation)"""
    
    def __init__(self):
        self.model_loaded = False
        self.model_name = "piper-voice"
        self.voice_model = "en_US-lessac-medium"
        self.piper_path = "piper"  # Assumes piper is in PATH
        self.model_dir = "piper_models"
        self.temp_dir = tempfile.mkdtemp()
        self.voice_onnx_path: Optional[str] = None
        self.voice_config_path: Optional[str] = None
    
    async def initialize(self):
        """Initialize Piper TTS engine"""
        try:
            logger.info("Initializing Piper TTS engine...")
            
            # Check if piper is installed
            try:
                result = subprocess.run([self.piper_path, "--help"], 
                                      capture_output=True, text=True, timeout=10)
                if result.returncode != 0:
                    raise RuntimeError("Piper not found in PATH")
            except (subprocess.TimeoutExpired, FileNotFoundError):
                logger.error("Piper TTS not found. Please install Piper: https://github.com/rhasspy/piper")
                raise RuntimeError("Piper TTS not installed")
            
            # Create model directory if it doesn't exist
            os.makedirs(self.model_dir, exist_ok=True)

            env_model_path = os.environ.get("PIPER_MODEL_PATH")
            env_config_path = os.environ.get("PIPER_CONFIG_PATH")
            if env_model_path:
                self.voice_onnx_path = env_model_path
                self.voice_config_path = env_config_path
            else:
                # Check if voice model exists, download if needed
                self.voice_onnx_path = self._find_voice_onnx_path()
                self.voice_config_path = self._find_voice_config_path()
                if not self.voice_onnx_path:
                    logger.info(f"Downloading Piper voice model: {self.voice_model}")
                    await self._download_voice_model()
                    self.voice_onnx_path = self._find_voice_onnx_path()
                    self.voice_config_path = self._find_voice_config_path()
            
            if not self.voice_onnx_path:
                raise RuntimeError(f"Unable to locate Piper voice model after download: {self.voice_model}")
            
            self.model_loaded = True
            logger.info(f"Piper TTS engine initialized with {self.voice_model}")
            
        except Exception as e:
            logger.error(f"Failed to initialize Piper TTS engine: {e}")
            raise
    
    async def synthesize(self, text: str) -> bytes:
        """Synthesize text to audio"""
        if not self.model_loaded:
            raise RuntimeError("Piper TTS engine not initialized")
        
        try:
            logger.debug(f"Synthesizing speech for: {text[:50]}...")
            
            # Create temporary files
            text_file = os.path.join(self.temp_dir, "input.txt")
            wav_file = os.path.join(self.temp_dir, "output.wav")
            
            # Write text to file
            with open(text_file, 'w', encoding='utf-8') as f:
                f.write(text)
            
            # Run Piper TTS
            model_path = self.voice_onnx_path or os.path.join(self.model_dir, f"{self.voice_model}.onnx")
            config_path = self.voice_config_path
            cmd = [
                self.piper_path,
                "--model", model_path,
                "--input_file", text_file,
                "--output_file", wav_file
            ]

            if config_path:
                cmd.extend(["--config", config_path])
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                logger.error(f"Piper TTS error: {result.stderr}")
                # Fallback to simple audio generation
                return await self._generate_fallback_audio(text)
            
            # Read the generated WAV file
            if os.path.exists(wav_file):
                if os.environ.get("PIPER_DEBUG_PLAY") == "1":
                    try:
                        subprocess.Popen(["afplay", wav_file])
                    except Exception as e:
                        logger.warning(f"Failed to play debug audio via afplay: {e}")
                with open(wav_file, 'rb') as f:
                    # Skip WAV header (44 bytes) to get raw audio data
                    audio_data = f.read()
                    if len(audio_data) > 44:
                        return audio_data[44:]  # Return raw PCM data
                    else:
                        return await self._generate_fallback_audio(text)
            else:
                return await self._generate_fallback_audio(text)
            
        except subprocess.TimeoutExpired:
            logger.error("Piper TTS timeout")
            return await self._generate_fallback_audio(text)
        except Exception as e:
            logger.error(f"TTS synthesis failed: {e}")
            return await self._generate_fallback_audio(text)
    
    def _find_voice_onnx_path(self) -> Optional[str]:
        """Locate the .onnx model for the configured voice under model_dir."""
        try:
            if not os.path.isdir(self.model_dir):
                return None

            # Piper download layout may be nested; search by filename.
            target_filename = f"{self.voice_model}.onnx"
            for root, _dirs, files in os.walk(self.model_dir):
                if target_filename in files:
                    return os.path.join(root, target_filename)
            return None
        except Exception as e:
            logger.warning(f"Failed to locate Piper voice model: {e}")
            return None

    def _find_voice_config_path(self) -> Optional[str]:
        """Locate the .json config for the configured voice under model_dir."""
        try:
            if not os.path.isdir(self.model_dir):
                return None

            # Prefer a config file that matches the selected voice model name.
            target_filename = f"{self.voice_model}.json"
            for root, _dirs, files in os.walk(self.model_dir):
                if target_filename in files:
                    return os.path.join(root, target_filename)

            # Fallback: if model exists somewhere, try sibling .json
            onnx_path = self._find_voice_onnx_path()
            if onnx_path:
                candidate = os.path.splitext(onnx_path)[0] + ".json"
                if os.path.exists(candidate):
                    return candidate

            return None
        except Exception as e:
            logger.warning(f"Failed to locate Piper voice config: {e}")
            return None

    async def _download_voice_model(self):
        """Download Piper voice model"""
        try:
            # Use Piper's official downloader. This ensures the expected directory layout.
            cmd = [
                "python3",
                "-m",
                "piper.download_voices",
                "--download-dir",
                self.model_dir,
                self.voice_model,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

            if result.returncode == 0:
                logger.info(f"Successfully downloaded voice {self.voice_model} into {self.model_dir}")
            else:
                logger.warning(
                    f"Failed to download {self.voice_model} via piper.download_voices: {result.stderr}"
                )
                
        except Exception as e:
            logger.warning(f"Could not download voice model: {e}")
    
    async def _generate_fallback_audio(self, text: str) -> bytes:
        """Generate fallback audio when Piper fails"""
        try:
            # Generate simple sine wave audio as fallback
            sample_rate = 16000
            duration = len(text) * 0.1  # Rough estimate
            t = np.linspace(0, duration, int(sample_rate * duration))
            frequency = 440  # A4 note
            audio = np.sin(2 * np.pi * frequency * t) * 0.3
            
            # Convert to 16-bit PCM
            audio_bytes = (audio * 32767).astype(np.int16).tobytes()
            return audio_bytes
        except Exception as e:
            logger.error(f"Fallback audio generation failed: {e}")
            # Return empty bytes as last resort
            return b''
    
    def get_status(self) -> dict:
        """Get engine status"""
        return {
            "model_loaded": self.model_loaded,
            "model_name": self.model_name,
            "voice_model": self.voice_model,
            "engine_type": "piper_tts",
            "piper_path": self.piper_path,
            "model_dir": self.model_dir
        }