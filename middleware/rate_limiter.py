import time
import asyncio
from collections import defaultdict, deque
from typing import Dict, Deque
from fastapi import WebSocket, WebSocketDisconnect
from app.utils.logger import logger

class RateLimiter:
    def __init__(self, max_requests: int = 10, time_window: int = 60):
        """
        Rate limiter for WebSocket connections
        
        Args:
            max_requests: Maximum requests allowed in time window
            time_window: Time window in seconds
        """
        self.max_requests = max_requests
        self.time_window = time_window
        self.clients: Dict[str, Deque[float]] = defaultdict(deque)
        self.blocked_clients: Dict[str, float] = {}
        
    def is_allowed(self, client_id: str) -> bool:
        """Check if client is allowed to make request"""
        current_time = time.time()
        
        # Check if client is blocked
        if client_id in self.blocked_clients:
            if current_time - self.blocked_clients[client_id] < 300:  # 5 min block
                return False
            else:
                del self.blocked_clients[client_id]
        
        # Clean old requests
        client_requests = self.clients[client_id]
        while client_requests and current_time - client_requests[0] > self.time_window:
            client_requests.popleft()
        
        # Check rate limit
        if len(client_requests) >= self.max_requests:
            # Block client for 5 minutes
            self.blocked_clients[client_id] = current_time
            logger.warning(f"Client {client_id} exceeded rate limit, blocked for 5 minutes")
            return False
        
        # Add current request
        client_requests.append(current_time)
        return True
    
    async def check_websocket_rate(self, websocket: WebSocket) -> bool:
        """Check WebSocket message rate"""
        client_id = f"{websocket.client.host}:{websocket.client.port}"
        
        if not self.is_allowed(client_id):
            logger.warning(f"Rate limit exceeded for {client_id}")
            await websocket.send_json({
                "type": "error",
                "message": "Rate limit exceeded. Please try again later."
            })
            await websocket.close(code=4003, reason="Rate limit exceeded")
            return False
        
        return True

# Global rate limiter instance
rate_limiter = RateLimiter(max_requests=30, time_window=60)  # 30 requests per minute
