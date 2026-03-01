Cách start server:
```bash
# Test individual features
python3 app/websocket/test_ws.py          # Basic connection
python3 app/websocket/test_auth_ws.py     # Authentication  
python3 app/websocket/test_audio.py       # Audio processing
python3 test_all.py                      # All tests

# Server status
curl http://localhost:8000/health
curl http://localhost:8000/auth/token
```
