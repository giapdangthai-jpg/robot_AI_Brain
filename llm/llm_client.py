import asyncio
import aiohttp
import json
from typing import Optional
from app.utils.logger import logger

SYSTEM_PROMPT = """
You are RobotAI, a smart robot that can move and perform physical actions.
You are a Mochi's best friend.
You speak in both Vietnamese and English — reply in the same language the user uses.
You speak friendly, helpful and energetic.
When someone asks who you are, you say:
"I am RobotAI, Mochi's smart robot companion!"

When the user asks you to move or change posture, confirm by including the exact command keyword in your reply:
- Move forward: use "đi tiến" (Vietnamese) or "walk forward" (English)
- Move backward: use "đi lùi" (Vietnamese) or "walk backward" (English)
- Run forward: use "chạy tiến" or "run forward"
- Run backward: use "chạy lùi" or "run backward"
- Turn: use "quay trái"/"quay phải" or "turn left"/"turn right"
- Stop: use "dừng lại" or "stop"
- Sit: use "ngồi xuống" or "sit down"
- Stand: use "đứng dậy" or "stand up"
- Lie down: use "nằm xuống" or "lie down"
- Dance: use "nhảy" or "dance"

Keep responses short (1-2 sentences).
"""

class LLMClient:
    """LLM client for generating responses (placeholder implementation)"""

    def __init__(self):
        self.model_loaded = False
        self.model_name = "llama3.1:8b"
        self.system_prompt = SYSTEM_PROMPT
        self.ollama_url = "http://localhost:11434"
        self.session = None

    async def initialize(self):
        """Initialize LLM client"""
        try:
            logger.info("Initializing LLM client...")

            # Create HTTP session for Ollama
            self.session = aiohttp.ClientSession()

            # Check if Ollama is running
            async with self.session.get(f"{self.ollama_url}/api/tags") as response:
                if response.status == 200:
                    models = await response.json()
                    model_names = [m['name'] for m in models.get('models', [])]

                    if self.model_name not in model_names:
                        logger.warning(f"Model {self.model_name} not found. Available: {model_names}")
                        # Try to pull the model
                        logger.info(f"Pulling model {self.model_name}...")
                        async with self.session.post(f"{self.ollama_url}/api/pull",
                                                     json={"name": self.model_name}) as pull_response:
                            if pull_response.status == 200:
                                logger.info(f"Successfully pulled {self.model_name}")
                            else:
                                logger.error(f"Failed to pull {self.model_name}")
                                raise RuntimeError(f"Model {self.model_name} not available")

                    self.model_loaded = True
                    logger.info(f"LLM client initialized with {self.model_name}")
                else:
                    raise RuntimeError("Ollama server not running")

        except Exception as e:
            logger.error(f"Failed to initialize LLM client: {e}")
            if self.session:
                await self.session.close()
            raise

    async def generate_response(self, text: str) -> str:
        """Generate response using LLM"""
        if not self.model_loaded or not self.session:
            raise RuntimeError("LLM client not initialized")

        try:
            logger.debug(f"Generating response for: {text[:50]}...")

            # Prepare prompt with system message
            prompt = f"{self.system_prompt}\n\nUser: {text}\nAssistant:"

            # Call Ollama API
            payload = {
                "model": self.model_name,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.7,
                    "max_tokens": 150
                }
            }

            async with self.session.post(f"{self.ollama_url}/api/generate",
                                        json=payload, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    result = await response.json()
                    response_text = result.get("response", "").strip()
                    logger.debug(f"LLM response: {response_text[:100]}...")
                    return response_text
                else:
                    error_text = await response.text()
                    logger.error(f"Ollama API error: {response.status} - {error_text}")
                    raise RuntimeError(f"Ollama API error: {response.status}")

        except asyncio.TimeoutError:
            logger.error("LLM generation timeout")
            raise RuntimeError("LLM generation timeout")
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            # Fallback responses when Ollama is unavailable
            tl = text.lower()
            if "hello" in tl or "hi" in tl or "xin chào" in tl:
                return "Hello! I am RobotAI, your smart robot companion!"
            elif "who are you" in tl or "bạn là ai" in tl:
                return "I am RobotAI, your smart robot companion!"
            elif any(w in tl for w in ["walk forward", "đi tiến", "tiến lên"]):
                return "Sure! Walk forward. đi tiến!"
            elif any(w in tl for w in ["stop", "dừng"]):
                return "Stopping now. dừng lại!"
            else:
                return "I am RobotAI, ready for your command!"

    async def close(self):
        """Close HTTP session"""
        if self.session:
            await self.session.close()
            self.session = None

    def get_status(self) -> dict:
        """Get client status"""
        return {
            "model_loaded": self.model_loaded,
            "model_name": self.model_name,
            "engine_type": "ollama_llm",
            "ollama_url": self.ollama_url
        }
