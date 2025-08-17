import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

def test_openai_connection():
    """Тест подключения к OpenAI API"""
    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        # Простой тест API
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": "Привет! Это тест подключения."}],
            max_tokens=50
        )
        
        print("✅ OpenAI API работает!")
        print(f"Ответ: {response.choices[0].message.content}")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка OpenAI API: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Тестирование OpenAI API...")
    test_openai_connection()
