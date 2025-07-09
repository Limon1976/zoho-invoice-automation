import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from dotenv import load_dotenv
load_dotenv()

from telegram_bot.logging_config import setup_logger
logger = setup_logger(__name__)

from telegram.ext import ApplicationBuilder, MessageHandler, filters
from telegram_bot.handlers import handle_document

BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN") or ""
if not BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен в .env")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(MessageHandler(filters.Document.PDF, handle_document))

    logger.info("🤖 Telegram-бот запущен. Ожидаю проформы...")
    app.run_polling()

if __name__ == "__main__":
    main()
