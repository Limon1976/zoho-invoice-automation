# Запускать скрипт командой: python run_all.py
import logging
import os
import config
from multiprocessing import Process
from telegram_bot.bot_main import main as run_bot
from watcher.monitor import start_watching

# 🔇 Отключаем лишние HTTP-запросы от httpx
logging.getLogger("httpx").setLevel(logging.WARNING)

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s:%(processName)s:%(message)s"
    )
    logging.info("🚀 Запускаю Telegram-бота и мониторинг проформ...")

    bot_process = Process(target=run_bot, name="TelegramBot")
    watcher_process = Process(target=start_watching, name="Watcher")

    bot_process.start()
    logging.info(f"👤 PID процесса TelegramBot: {bot_process.pid}")
    watcher_process.start()
    logging.info(f"👁️ PID процесса Watcher: {watcher_process.pid}")

    # Если нужно ждать завершения дочерних процессов (обычно не нужно, но для полноты)
    bot_process.join()
    watcher_process.join()