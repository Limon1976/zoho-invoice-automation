import config  # Загружает .env
import os
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    print("⚠️ Переменная OPENAI_API_KEY отсутствует!")
else:
    masked = API_KEY[:8] + "*" * 10 + API_KEY[-4:]
    print(f"🔑 Используется ключ: {masked}")
import requests

url = "https://api.openai.com/v1/models"
headers = {"Authorization": f"Bearer {API_KEY}"}

response = requests.get(url, headers=headers)

if response.status_code == 200:
    print("✅ API работает! Доступные модели:")
    models = response.json()["data"]
    for model in models[:5]:  # Показываем только 5 моделей
        print("-", model["id"])
else:
    print(f"❌ Ошибка: {response.status_code}, {response.text}")