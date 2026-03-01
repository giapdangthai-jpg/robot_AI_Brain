import time
import hashlib
import secrets
from typing import Optional, Dict
from fastapi import WebSocket, WebSocketDisconnect
from app.utils.logger import logger

class AuthMiddleware:
    def __init__(self, secret_key: str = None):
        self.secret_key = secret_key or secrets.token_urlsafe(32)
        self.active_tokens: Dict[str, float] = {}
        self.token_expiry = 3600  # 1 hour
        
    def generate_token(self) -> str:
        """Generate authentication token"""
        timestamp = str(int(time.time()))
        token_data = f"{timestamp}:{self.secret_key}"
        return hashlib.sha256(token_data.encode()).hexdigest()
    
    def validate_token(self, token: str) -> bool:
        """Validate authentication token"""
        if not token:
            return False
            
        # Check if token exists and not expired
        if token in self.active_tokens:
            if time.time() - self.active_tokens[token] < self.token_expiry:
                return True
            else:
                del self.active_tokens[token]
        
        return False
    
    def add_token(self, token: str):
        """Add token to active tokens"""
        self.active_tokens[token] = time.time()
    
    async def authenticate_websocket(self, websocket: WebSocket) -> bool:
        """Authenticate WebSocket connection"""
        try:
            # Get token from query params or headers
            token = websocket.query_params.get("token")
            if not token:
                token = websocket.headers.get("authorization", "").replace("Bearer ", "")
            
            if not self.validate_token(token):
                logger.warning(f"Unauthorized WebSocket connection attempt from {websocket.client}")
                await websocket.close(code=4001, reason="Unauthorized")
                return False
            
            logger.info(f"WebSocket authenticated successfully from {websocket.client}")
            return True
            
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            await websocket.close(code=4002, reason="Authentication failed")
            return False

# Global auth instance
auth = AuthMiddleware()
