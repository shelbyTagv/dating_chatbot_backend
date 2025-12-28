import requests
from config import BASE_URL, API_TOKEN

def send_text(phone: str, text: str):
    url = f"{BASE_URL}/sendMessage/{API_TOKEN}"
    payload = {
        "chatId": f"{phone}@c.us",
        "message": text
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"WhatsApp send error: {e}")
