from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import json
import asyncio
from app.utils.logger import setup_logger
from app.middleware.auth import auth
from app.middleware.rate_limiter import rate_limiter
from app.pipeline.audio_processor import audio_processor
from app.websocket.ws_server import RobotWebSocket

# Setup logging
logger = setup_logger("robot_dog_brain", "INFO", "logs/robot_dog.log")

app = FastAPI(title="Robot Dog AI", version="1.0.0")

# WebSocket handler
robot_ws = RobotWebSocket()

@app.on_event("startup")
async def startup_event():
    """Initialize components on startup"""
    try:
        await audio_processor.initialize()
        logger.info("Robot Dog AI server started successfully")
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        raise

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
 "audio_processor": audio_processor.get_status(),
        "active_connections": len(robot_ws.clients)
    }

@app.get("/auth/token")
async def get_auth_token():
    """Get authentication token for WebSocket connection"""
    token = auth.generate_token()
    auth.add_token(token)
    return {"token": token, "expires_in": 3600}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Enhanced WebSocket endpoint with authentication and rate limiting"""
    
    # Authentication
    if not await auth.authenticate_websocket(websocket):
        return
    
    # Rate limiting check
    if not await rate_limiter.check_websocket_rate(websocket):
        return
    
    # Handle connection using RobotWebSocket class
    await robot_ws.handle(websocket)

@app.websocket("/ws/public")
async def public_websocket_endpoint(websocket: WebSocket):
    """Public WebSocket endpoint for testing (no auth required)"""
    logger.info("Public WebSocket connection requested")
    await robot_ws.handle(websocket)
