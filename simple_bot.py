#!/usr/bin/env python3
"""
Простой Telegram бот для тестирования исправлений
"""

import os
import sys
import logging
from pathlib import Path

# Добавляем корневую папку в path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from telegram.ext import Application

# Логи настраиваются централизованно главным приложением; здесь берём логгер
logger = logging.getLogger(__name__)

def main():
    """Простой запуск бота"""
    
    # Получаем токен
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not bot_token:
        print("❌ TELEGRAM_BOT_TOKEN не установлен")
        return
    
    print("🔄 Запускаем простого бота...")
    
    try:
        # Создаем приложение 
        application = Application.builder().token(bot_token).build()
        
        # Настраиваем обработчики
        from telegram_bot.handlers import setup_handlers
        setup_handlers(application)
        
        print("✅ Бот запущен с исправлениями!")
        print("📋 Адрес, description и SKU теперь работают корректно")
        print("🚀 Отправьте PDF документ для тестирования")
        
        # Запускаем polling
        application.run_polling(drop_pending_updates=True)
        
    except KeyboardInterrupt:
        print("\n👋 Бот остановлен")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    main() 