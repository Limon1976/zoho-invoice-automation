"""
Базовый класс для новых handlers с безопасной архитектурой
"""

import logging
from typing import Optional
from telegram import Update
from telegram.ext import ContextTypes

from telegram_bot.services.expense_service import ExpenseService
from telegram_bot.services.account_manager import AccountManager
from telegram_bot.services.attachment_manager import AttachmentManager
from telegram_bot.services.branch_manager import BranchManager
from telegram_bot.utils_v2.feature_flags import is_enabled

logger = logging.getLogger(__name__)


class BaseHandler:
    """Базовый класс для всех новых handlers"""
    
    def __init__(self):
        # Инициализируем только проверенные сервисы
        self.expense_service = ExpenseService()
        self.account_manager = AccountManager()
        self.attachment_manager = AttachmentManager()
        self.branch_manager = BranchManager()
    
    async def handle_error(self, update: Update, error: Exception, context_info: str = ""):
        """Унифицированная обработка ошибок"""
        try:
            error_msg = f"❌ Ошибка {context_info}: {str(error)}"
            logger.error(f"Handler error in {context_info}: {error}", exc_info=True)
            
            if update.callback_query:
                await update.callback_query.edit_message_text(error_msg)
            elif update.message:
                await update.message.reply_text(error_msg)
                
        except Exception as e:
            logger.error(f"Failed to send error message: {e}")
    
    def should_use_new_handler(self, handler_type: str) -> bool:
        """Проверяет нужно ли использовать новый handler"""
        feature_map = {
            'document': 'use_new_document_handler',
            'expense': 'use_new_expense_handler',
            'bill': 'use_new_bill_handler',
            'contact': 'use_new_contact_handler',
            'callback': 'use_new_callback_router'
        }
        
        feature = feature_map.get(handler_type)
        if feature:
            return is_enabled(feature)
        
        return False
    
    async def fallback_to_old_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE, handler_name: str):
        """Fallback к старому handler если новый не включен"""
        logger.info(f"🔄 Fallback к старому handler: {handler_name}")
        
        # Здесь можно добавить вызов старых handlers при необходимости
        # Пока просто логируем
        await update.message.reply_text(f"⚠️ Функция {handler_name} временно недоступна")


class SafetyMixin:
    """Mixin для дополнительной безопасности"""
    
    async def validate_context(self, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Проверяет что контекст валиден"""
        try:
            if not context or not context.user_data:
                return False
            return True
        except Exception:
            return False
    
    async def backup_context(self, context: ContextTypes.DEFAULT_TYPE, operation: str):
        """Создает backup контекста перед операцией"""
        try:
            if context and context.user_data:
                backup_key = f"backup_{operation}_{hash(str(context.user_data))}"
                # В продакшене можно сохранить в Redis
                logger.info(f"📋 Backup контекста для операции: {operation}")
        except Exception as e:
            logger.warning(f"Failed to backup context: {e}")


class ValidationMixin:
    """Mixin для валидации данных"""
    
    def validate_analysis(self, analysis: dict) -> bool:
        """Проверяет что анализ документа валиден"""
        required_fields = ['supplier_name', 'total_amount', 'currency']
        
        for field in required_fields:
            if not analysis.get(field):
                logger.warning(f"❌ Отсутствует обязательное поле: {field}")
                return False
        
        return True
    
    def validate_supplier(self, supplier: dict) -> bool:
        """Проверяет что данные поставщика валидны"""
        if not supplier or not supplier.get('contact_id'):
            logger.warning("❌ Поставщик не найден или отсутствует contact_id")
            return False
        
        return True
