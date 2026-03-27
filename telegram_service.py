import requests
import config

def send_telegram(message: str):
    token = config.TELEGRAM_BOT_TOKEN()
    chat_id = config.TELEGRAM_CHAT_ID()
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = requests.post(url, json={"chat_id": chat_id, "text": message}, timeout=10)
    resp.raise_for_status()
