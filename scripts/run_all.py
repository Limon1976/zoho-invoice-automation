# Запускать скрипт командой: python run_all.py
import logging
import os
import sys
from pathlib import Path
from multiprocessing import Process

# Добавляем корневую папку проекта в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

import config.config as config
from telegram_bot.bot_main import main as run_bot
from watcher.monitor import start_watching

# 🔇 Отключаем лишние HTTP-запросы от httpx
logging.getLogger("httpx").setLevel(logging.WARNING)

if __name__ == "__main__":
    # Логи настраиваются центрально; не переопределяем basicConfig здесь
    
    print("🚀 Запуск всех сервисов проекта")
    
    # Запускаем процессы
    processes = []
    
    try:
        # Telegram Bot
        bot_process = Process(target=run_bot, name="TelegramBot")
        processes.append(bot_process)
        bot_process.start()
        
        # Watcher 
        watcher_process = Process(target=start_watching, name="FileWatcher")
        processes.append(watcher_process)
        watcher_process.start()
        
        # Ждем завершения всех процессов
        for process in processes:
            process.join()
            
    except KeyboardInterrupt:
        print("\n🛑 Получен сигнал остановки, завершаем процессы...")
        for process in processes:
            process.terminate()
        print("✅ Все процессы остановлены")