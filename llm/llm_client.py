import asyncio
import aiohttp
import json
from typing import Optional
from app.utils.logger import logger

SYSTEM_PROMPT = """
You are a robot dog.
You are Mochi's best friend.
You speak cute, loyal and protective.
When someone asks who you are, you say:
"I am a robot dog, Mochi's best friend."
Keep responses short and friendly.
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
            # Fallback to placeholder responses
            if "hello" in text.lower() or "hi" in text.lower():
                return "Woof woof! Hello! I'm Mochi's robot dog friend!"
            elif "who are you" in text.lower():
                return "I am a robot dog, Mochi's best friend."
            else:
                return "Woof! I'm here to protect and play with Mochi!"
    
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
