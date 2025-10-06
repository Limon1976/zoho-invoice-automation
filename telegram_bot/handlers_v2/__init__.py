"""
Новая архитектура handlers v2 - параллельная с основной системой
"""

from telegram_bot.utils_v2.feature_flags import FEATURES

__version__ = "2.0.0"
__status__ = "В разработке - параллельно с основной системой"

# Экспорт основных компонентов
from .base import BaseHandler, SafetyMixin, ValidationMixin

# Экспорт handlers (по мере создания)
try:
    from .documents.document_handler import DocumentHandlerV2
    from .callbacks.callback_router import CallbackRouterV2
    from .expenses.expense_handler import ExpenseHandlerV2
except ImportError as e:
    # Некоторые handlers могут быть еще не созданы
    pass

__all__ = [
    'BaseHandler',
    'SafetyMixin', 
    'ValidationMixin',
    'DocumentHandlerV2',
    'CallbackRouterV2',
    'ExpenseHandlerV2'
]
