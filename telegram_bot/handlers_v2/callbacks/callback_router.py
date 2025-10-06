"""
Новый Callback Router v2 с чистой архитектурой
"""

import logging
import os
from datetime import datetime
from typing import Optional
from telegram import Update
from telegram.ext import ContextTypes

from telegram_bot.handlers_v2.base import BaseHandler
from telegram_bot.utils_v2.feature_flags import is_enabled

logger = logging.getLogger(__name__)


class CallbackRouterV2(BaseHandler):
    """Новый роутер для callback запросов"""
    
    def __init__(self):
        super().__init__()
        
        # Маршруты для новых handlers
        self.v2_routes = {
            'v2_create_expense': self._handle_create_expense,
            'v2_create_bill': self._handle_create_bill,
            'v2_create_contact': self._handle_create_contact,
            'v2_upload_workdrive': self._handle_upload_workdrive,
            'v2_cancel': self._handle_cancel
        }
    
    async def route_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Маршрутизация callback запросов"""
        
        if not update.callback_query:
            return
        
        query = update.callback_query
        action = query.data
        
        logger.info(f"🔘 Callback v2 received: {action}")
        
        # Проверяем это v2 callback
        if action.startswith('v2_'):
            # Используем новую архитектуру
            if not self.should_use_new_handler('callback'):
                await query.answer("⚠️ Новая функция временно недоступна")
                return
            
            handler = self.v2_routes.get(action)
            if handler:
                await handler(update, context)
            else:
                await query.edit_message_text(f"❌ Неизвестное действие v2: {action}")
        else:
            # Fallback к старому роутеру
            logger.info(f"🔄 Fallback к старому callback handler: {action}")
            await query.answer("🔄 Используется старая система...")
            # Здесь можно добавить вызов старого callback handler
    
    async def _handle_create_expense(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка создания Expense"""
        try:
            from telegram_bot.handlers_v2.expenses.expense_handler import ExpenseHandlerV2
            
            expense_handler = ExpenseHandlerV2()
            await expense_handler.create_expense(update, context)
            
        except Exception as e:
            await self.handle_error(update, e, "создания Expense")
    
    async def _handle_create_bill(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка создания Bill"""
        try:
            # TODO: Создать BillHandlerV2
            await update.callback_query.edit_message_text(
                "📋 Bill Handler v2 в разработке\n"
                "🔄 Используйте старую систему"
            )
            
        except Exception as e:
            await self.handle_error(update, e, "создания Bill")
    
    async def _handle_create_contact(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка создания контакта"""
        try:
            # TODO: Создать ContactHandlerV2
            await update.callback_query.edit_message_text(
                "👤 Contact Handler v2 в разработке\n"
                "🔄 Используйте старую систему"
            )
            
        except Exception as e:
            await self.handle_error(update, e, "создания контакта")
    
    async def _handle_upload_workdrive(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка загрузки в WorkDrive"""
        try:
            query = update.callback_query
            await query.edit_message_text("📁 Загружаю файл в WorkDrive...")
            
            # Получаем данные из контекста
            analysis = context.user_data.get('document_analysis_v2') or context.user_data.get('document_analysis', {})
            file_path = context.user_data.get('processed_file_path') or context.user_data.get('file_path')
            
            if not file_path or not os.path.exists(file_path):
                await query.edit_message_text("❌ Файл не найден для загрузки в WorkDrive")
                return
            
            # Загружаем в WorkDrive
            from functions.zoho_workdrive import ZohoWorkDriveAPI
            
            workdrive = ZohoWorkDriveAPI()
            
            # Определяем дату продажи для выбора правильной папки
            sale_date = analysis.get('sale_date') or analysis.get('issue_date') or analysis.get('document_date')
            supplier_name = analysis.get('supplier_name', 'Unknown')
            document_type = analysis.get('document_type', 'document')
            
            # Создаем имя файла: Фирма_ЦенаБрутто
            gross_amount = analysis.get('total_amount', '0')
            # Убираем валюту и форматируем цену
            if isinstance(gross_amount, str):
                gross_amount = gross_amount.replace('PLN', '').replace('€', '').replace('$', '').strip()
            # Заменяем запятую на точку для файловой системы
            gross_amount = str(gross_amount).replace(',', '.')
            file_extension = os.path.splitext(file_path)[1]
            new_filename = f"{supplier_name.replace(' ', '_')}_{gross_amount}{file_extension}"
            
            # Загружаем файл в правильную папку по дате продажи
            upload_result = workdrive.auto_upload_document(
                org_name="PARKENTERTAINMENT",
                document_date=sale_date,
                file_path=file_path,
                filename=new_filename,
                analysis=analysis
            )
            
            if upload_result.get('success'):
                file_id = upload_result.get('file_id')
                
                # Помечаем как Final
                mark_result = workdrive.mark_file_as_final(file_id)
                
                if mark_result:
                    folder_path = upload_result.get('folder_path', 'Unknown')
                    document_year = upload_result.get('document_year', 'Unknown')
                    await query.edit_message_text(
                        f"✅ Файл успешно загружен в WorkDrive!\n"
                        f"📁 Папка: {folder_path}\n"
                        f"📅 Год документа: {document_year}\n"
                        f"📄 Файл: {new_filename}\n"
                        f"🏷️ Статус: Final (обработан)\n"
                        f"🆔 File ID: {file_id}"
                    )
                else:
                    folder_path = upload_result.get('folder_path', 'Unknown')
                    await query.edit_message_text(
                        f"⚠️ Файл загружен, но не помечен как Final\n"
                        f"📁 Папка: {folder_path}\n"
                        f"📄 Файл: {new_filename}\n"
                        f"🆔 File ID: {file_id}"
                    )
            else:
                error_msg = upload_result.get('error', 'Неизвестная ошибка')
                await query.edit_message_text(f"❌ Ошибка загрузки в WorkDrive: {error_msg}")
            
        except Exception as e:
            await self.handle_error(update, e, "загрузки в WorkDrive")
    
    async def _handle_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка отмены"""
        await update.callback_query.edit_message_text("❌ Операция отменена")
        logger.info("✅ Операция отменена пользователем")
