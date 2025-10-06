"""
Тестовый бот для проверки новой архитектуры handlers_v2
Работает параллельно с основным ботом
"""

import os
import sys
import logging
from pathlib import Path

# Добавляем путь к проекту
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from telegram import Update
from telegram.ext import Application, MessageHandler, CallbackQueryHandler, CommandHandler, filters

from telegram_bot.handlers_v2.documents.document_handler import DocumentHandlerV2
from telegram_bot.handlers_v2.callbacks.callback_router import CallbackRouterV2
from telegram_bot.utils_v2.feature_flags import FEATURES, enable_feature

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('logs/bot_v2_test.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


async def start_command(update: Update, context):
    """Команда /start для тестового бота"""
    await update.message.reply_text(
        "🤖 Тестовый бот v2 запущен!\n\n"
        "✨ Новые возможности:\n"
        "• 📄 Поддержка PDF и JPEG\n"
        "• 💳 ExpenseService интеграция\n"
        "• 🌸 Цветочные accounts\n"
        "• 🏢 Branch логика\n\n"
        "📎 Отправьте документ для тестирования!"
    )


async def status_command(update: Update, context):
    """Показывает статус feature flags"""
    enabled_features = [f for f, enabled in FEATURES.items() if enabled]
    disabled_features = [f for f, enabled in FEATURES.items() if not enabled]
    
    message = "🎛️ СТАТУС FEATURE FLAGS:\n\n"
    
    if enabled_features:
        message += "✅ ВКЛЮЧЕНО:\n"
        for feature in enabled_features:
            message += f"  • {feature}\n"
        message += "\n"
    
    if disabled_features:
        message += "❌ ОТКЛЮЧЕНО:\n"
        for feature in disabled_features:
            message += f"  • {feature}\n"
    
    await update.message.reply_text(message)


def setup_v2_handlers(application):
    """Настройка новых handlers v2"""
    
    # Включаем функции для тестирования
    enable_feature('use_new_document_handler')
    enable_feature('use_new_callback_router')
    enable_feature('use_jpeg_processing')
    
    # Создаем handlers
    doc_handler = DocumentHandlerV2()
    callback_router = CallbackRouterV2()
    
    # Регистрируем handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("status", status_command))
    
    # Документы (PDF и изображения)
    application.add_handler(MessageHandler(
        filters.Document.PDF | filters.PHOTO, 
        doc_handler.handle_document
    ))
    
    # Callbacks
    application.add_handler(CallbackQueryHandler(callback_router.route_callback))
    
    logger.info("✅ Handlers v2 настроены")


def main():
    """Запуск тестового бота"""
    
    # Получаем токен (используем тестовый или основной)
    token = os.getenv('TELEGRAM_BOT_TOKEN_TEST') or os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not token:
        logger.error("❌ TELEGRAM_BOT_TOKEN не найден")
        return
    
    # Создаем приложение
    application = Application.builder().token(token).build()
    
    # Настраиваем handlers v2
    setup_v2_handlers(application)
    
    logger.info("🚀 Тестовый бот v2 запускается...")
    
    # Запускаем бота
    try:
        application.run_polling(drop_pending_updates=True)
    except KeyboardInterrupt:
        logger.info("🛑 Тестовый бот остановлен")
    except Exception as e:
        logger.error(f"❌ Ошибка тестового бота: {e}")


if __name__ == '__main__':
    main()
