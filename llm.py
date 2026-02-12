import requests

OLLAMA_URL = "http://localhost:11434/api/generate"

def ask_llama(prompt: str):
    payload = {
        "model": "llama3.1:8b",
        "prompt": prompt,
        "stream": False
    }

    response = requests.post(OLLAMA_URL, json=payload)
    data = response.json()
    return data["response"]
