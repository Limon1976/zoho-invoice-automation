import os
import requests
from dotenv import load_dotenv

# Загружаем переменные окружения из .env
load_dotenv()

ZOHO_CLIENT_ID = os.getenv("ZOHO_CLIENT_ID")
ZOHO_CLIENT_SECRET = os.getenv("ZOHO_CLIENT_SECRET")
ZOHO_REFRESH_TOKEN = os.getenv("ZOHO_REFRESH_TOKEN")
ZOHO_API_DOMAIN = "https://www.zohoapis.eu"

# Внутренний кэш
_access_token_cache = None

def refresh_access_token():
    """Обновляет `access_token` с помощью `refresh_token`"""
    url = "https://accounts.zoho.eu/oauth/v2/token"
    payload = {
        "refresh_token": ZOHO_REFRESH_TOKEN,
        "client_id": ZOHO_CLIENT_ID,
        "client_secret": ZOHO_CLIENT_SECRET,
        "grant_type": "refresh_token"
    }
    
    response = requests.post(url, data=payload)
    data = response.json()
    
    if "access_token" in data:
        new_access_token = data["access_token"]
        print("✅ `access_token` успешно обновлён!")
        return new_access_token
    else:
        print(f"❌ Ошибка обновления токена: {data}")
        return None

def get_access_token(force_refresh=False):
    """Возвращает `access_token`, обновляя при необходимости"""
    global _access_token_cache
    if _access_token_cache and not force_refresh:
        return _access_token_cache
    _access_token_cache = refresh_access_token()
    return _access_token_cache

if __name__ == "__main__":
    print("🔄 Получаем `access_token`...")
    token = get_access_token()
    print("🔑 Токен:", token)