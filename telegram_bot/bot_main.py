#!/usr/bin/env python3
"""
Telegram Bot Main
=================

Главный файл для запуска Telegram бота
"""

import logging
import fcntl
import os
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv

"""Main entrypoint with strict singleton, stable logging and webhook off."""

# Добавляем корневую папку проекта в путь
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

# Загружаем переменные окружения
load_dotenv()

from telegram.ext import Application

# Настройка логирования (до импорта хендлеров, чтобы перехватить basicConfig из подмодулей)
logs_dir = project_root / "logs"
logs_dir.mkdir(parents=True, exist_ok=True)

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
# Чистим дублирующиеся хендлеры при повторных запусках в одном процессе
if root_logger.handlers:
    for h in list(root_logger.handlers):
        root_logger.removeHandler(h)

fmt = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
fileh = RotatingFileHandler(str(logs_dir / 'telegram_bot.out'), maxBytes=2_000_000, backupCount=3, encoding='utf-8')
fileh.setFormatter(fmt)
root_logger.addHandler(fileh)

logger = logging.getLogger(__name__)

# Перенаправляем print (stdout/stderr) в логгер, чтобы всё попадало в файл
class _LoggerWriter:
    def __init__(self, logger: logging.Logger, level):
        self._logger = logger
        self._level = level
    def write(self, message: str):
        if not message:
            return
        for line in str(message).rstrip().splitlines():
            if line:
                self._level(line)
    def flush(self):
        pass

stdout_logger = logging.getLogger("stdout")
stderr_logger = logging.getLogger("stderr")
# Убедимся, что дополнительные хендлеры на специализированных логгерах отсутствуют (используем только root -> file)
stdout_logger.handlers = []
stderr_logger.handlers = []
stdout_logger.propagate = True
stderr_logger.propagate = True
sys.stdout = _LoggerWriter(stdout_logger, stdout_logger.info)
sys.stderr = _LoggerWriter(stderr_logger, stderr_logger.error)

# Скрываем HTTP логи от httpx (слишком много)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram.ext.Application").setLevel(logging.WARNING)


def start_bot():
    """Запуск бота (синхронно), чтобы PTB сам управлял event loop."""
    # Гарантия одного экземпляра: файловая блокировка
    lock_path = project_root / "logs" / "bot_main.lock"
    pid_path = project_root / "logs" / "telegram_bot.pid"
    lock_file = open(lock_path, "w")
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        logger.error("❌ Другой экземпляр бота уже запущен (lock). Выходим.")
        print("❌ Другой экземпляр бота уже запущен.")
        return
    # Страховка: проверка существующего PID
    try:
        if pid_path.exists():
            existing = pid_path.read_text().strip()
            if existing.isdigit() and Path(f"/proc/{existing}").exists():
                logger.error("❌ Бот уже запущен (pidfile)")
                return
    except Exception:
        pass

    # Получаем токен
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not bot_token:
        logger.error("❌ TELEGRAM_BOT_TOKEN не установлен в переменных окружения")
        raise ValueError("TELEGRAM_BOT_TOKEN не установлен")

    # Создаем приложение с настройками таймаутов
    application = (
        Application.builder()
        .token(bot_token)
        .get_updates_read_timeout(15)
        .get_updates_write_timeout(15)
        .get_updates_connect_timeout(15)
        .get_updates_pool_timeout(15)
        .build()
    )

    # Отключаем webhook, чтобы не конфликтовал с polling
    try:
        import requests
        requests.get(f"https://api.telegram.org/bot{bot_token}/setWebhook", params={"url": ""}, timeout=10)
    except Exception:
        pass

    # Настраиваем обработчики (после настройки логирования)
    from telegram_bot.handlers import setup_handlers
    setup_handlers(application)

    logger.info("🤖 Telegram бот запущен")
    print("✅ Бот работает! Отправьте PDF документ для тестирования")
    try:
        pid_path.write_text(str(os.getpid()))
    except Exception:
        pass

    # Запускаем бота (блокирующе)
    application.run_polling(
        drop_pending_updates=True,
        poll_interval=2.0,
        timeout=10,
    )

    # При штатном завершении снимаем блокировку
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        lock_file.close()
    except Exception:
        pass


if __name__ == "__main__":
    try:
        start_bot()
    except KeyboardInterrupt:
        logger.info("🛑 Остановка бота по запросу пользователя")
    except Exception as e:
        logger.exception(f"❌ Ошибка запуска бота: {e}")
