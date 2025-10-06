"""
Новый Expense Handler v2 с использованием ExpenseService
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from telegram_bot.handlers_v2.base import BaseHandler, SafetyMixin, ValidationMixin
from functions.zoho_contact_search import find_supplier_in_zoho

logger = logging.getLogger(__name__)


class ExpenseHandlerV2(BaseHandler, SafetyMixin, ValidationMixin):
    """Новый обработчик создания Expense"""
    
    async def create_expense(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Создает Expense используя ExpenseService"""
        
        if not update.callback_query:
            return
            
        query = update.callback_query
        
        try:
            # Проверяем контекст
            if not await self.validate_context(context):
                await query.edit_message_text("❌ Контекст не найден")
                return
            
            analysis = context.user_data.get('document_analysis_v2', {})
            if not self.validate_analysis(analysis):
                await query.edit_message_text("❌ Анализ документа невалиден")
                return
            
            await query.edit_message_text("💸 Создаю Expense через ExpenseService...")
            
            # Определяем организацию
            org_id, org_name = self._determine_organization(analysis)
            
            # Проверяем поставщика
            supplier_name = analysis.get('supplier_name', 'Unknown Vendor')
            supplier_vat = analysis.get('supplier_vat', '')
            
            supplier_contact = find_supplier_in_zoho(org_id, supplier_name, supplier_vat)
            
            if not supplier_contact or not supplier_contact.get('contact_id'):
                # Поставщик не найден - предлагаем создать
                await self._offer_create_supplier(query, analysis)
                return
            
            # Создаем Expense через ExpenseService
            supplier = {'contact_id': supplier_contact.get('contact_id')}
            file_path = context.user_data.get('processed_file_path') or context.user_data.get('file_path')
            
            result = await self.expense_service.create_expense_from_analysis(
                analysis=analysis,
                supplier=supplier,
                org_id=org_id,
                org_name=org_name,
                file_path=file_path
            )
            
            if 'error' in result:
                await query.edit_message_text(f"❌ Ошибка создания Expense: {result['error']}")
                return
            
            # Expense успешно создан
            expense_data = result.get('expense', {})
            expense_id = expense_data.get('expense_id')
            expense_number = expense_data.get('expense_number')
            total = expense_data.get('total', 0)
            currency = analysis.get('currency', 'PLN')
            
            # Формируем успешное сообщение
            zoho_url = f"https://books.zoho.eu/app/{org_id}#/expenses/{expense_id}"
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 Открыть в Zoho", url=zoho_url)],
                [InlineKeyboardButton("📁 Загрузить в WorkDrive", callback_data="v2_upload_workdrive")]
            ])
            
            await query.edit_message_text(
                f"✅ Expense #{expense_number} создан! (v2)\n\n"
                f"💰 Сумма: {total:.2f} {currency}\n"
                f"🏪 Поставщик: {supplier_name}\n"
                f"📄 Номер: {analysis.get('bill_number', 'N/A')}",
                reply_markup=keyboard
            )
            
            logger.info(f"✅ Expense создан через v2 handler: {expense_id}")
            
        except Exception as e:
            await self.handle_error(update, e, "создания Expense")
    
    def _determine_organization(self, analysis: dict) -> tuple[str, str]:
        """Определяет организацию для Expense"""
        our_company = analysis.get('our_company', '')
        
        if 'parkentertainment' in our_company.lower():
            return '20082562863', 'PARKENTERTAINMENT'
        elif 'tavie' in our_company.lower():
            return '20092948714', 'TaVie Europe OÜ'
        else:
            # По умолчанию PARKENTERTAINMENT
            return '20082562863', 'PARKENTERTAINMENT'
    
    async def _offer_create_supplier(self, query, analysis: dict):
        """Предлагает создать поставщика если не найден"""
        supplier_name = analysis.get('supplier_name', 'Unknown')
        supplier_vat = analysis.get('supplier_vat', '')
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Создать поставщика", callback_data="v2_create_contact")],
            [InlineKeyboardButton("❌ Отмена", callback_data="v2_cancel")]
        ])
        
        await query.edit_message_text(
            f"❌ Поставщик не найден!\n\n"
            f"🏪 Поставщик: {supplier_name}\n"
            f"🏷️ VAT: {supplier_vat or 'Не указан'}\n\n"
            f"Создайте поставщика перед созданием Expense.",
            reply_markup=keyboard
        )
