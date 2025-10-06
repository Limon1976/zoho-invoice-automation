"""
ExpenseService - унифицированная логика создания Expense
Выделен из handlers.py для переиспользования в WorkDrive Processor и других модулях
"""

import logging
from typing import Dict, Optional, Tuple
from datetime import datetime
import requests

from telegram_bot.services.account_manager import AccountManager
from functions.zoho_api import get_access_token, find_tax_by_percent
from telegram_bot.services.attachment_manager import AttachmentManager

logger = logging.getLogger(__name__)


class ExpenseService:
    """Сервис для создания Expense в Zoho Books"""
    
    @staticmethod
    def determine_payment_method(analysis: Dict) -> str:
        """
        Определяет способ оплаты из текста документа
        
        Returns:
            'personal' для наличных (Petty Cash)
            'business' для карты (Konto Firmowe)
        """
        text = (analysis.get('extracted_text') or '').lower()
        
        # Проверяем на наличные
        cash_indicators = [
            'gotówka', 'gotowka', 'cash', 
            'zapłacono gotówka', 'zaplacono gotowka',
            'płatność gotówką', 'platnosc gotowka'
        ]
        
        for indicator in cash_indicators:
            if indicator in text:
                logger.info("💰 Определен способ оплаты: наличные (Petty Cash)")
                return 'personal'
        
        # Проверяем на карту
        card_indicators = [
            'karta', 'card', 'zapłacono karta', 'zaplacono karta',
            'płatność kartą', 'platnosc karta'
        ]
        
        for indicator in card_indicators:
            if indicator in text:
                logger.info("💰 Определен способ оплаты: карта (Konto Firmowe)")
                return 'business'
        
        # По умолчанию для парагонов - наличные
        logger.info("💰 Способ оплаты не определен четко → наличные (Petty Cash) по умолчанию")
        return 'personal'
    
    @staticmethod
    def create_expense_payload(
        analysis: Dict, 
        supplier: Dict, 
        org_id: str,
        org_name: str
    ) -> Tuple[Dict, Optional[str]]:
        """
        Создает payload для Expense API
        
        Returns:
            Tuple[expense_payload, error_message]
        """
        try:
            # Определяем способ оплаты
            payment_type = ExpenseService.determine_payment_method(analysis)
            
            # Получаем счета через Account Manager
            paid_through_account_id, _ = AccountManager.get_paid_through_account(org_id, org_name, payment_type)
            
            # Формируем контекст для выбора account (включаем line_items для лучшего определения)
            context_items = []
            line_items = analysis.get('line_items', [])
            for item in line_items:
                context_items.append(item.get('description', ''))
                context_items.append(item.get('description_en', ''))
            
            context_text = f"Supplier: {analysis.get('supplier_name')}, Items: {', '.join(context_items)}, Category: {analysis.get('product_category', 'OTHER')}"
            
            expense_account_id, expense_account_name = AccountManager.get_expense_account(
                org_id, 
                org_name,
                context_text,
                analysis.get('supplier_name', ''),
                analysis.get('product_category', 'OTHER')
            )
            
            if not paid_through_account_id:
                return {}, f"Не удалось определить paid_through_account для {payment_type}"
            
            if not expense_account_id:
                return {}, f"Не удалось определить expense_account"
            
            logger.info(f"💳 Expense account: {expense_account_name} (ID: {expense_account_id})")
            logger.info(f"💳 Paid through: {payment_type} account (ID: {paid_through_account_id})")
            
            # Определяем branch для цветочных расходов (только для PARKENTERTAINMENT)
            branch_id = None
            if org_id == '20082562863' and expense_account_name in ['Flowers', 'Boxes', 'Paper, ribons', 'Vases', 'Balloons', 'Expenses IRIS']:
                # Цветочные расходы идут на branch "Iris flowers atelier"
                branch_id = '281497000000355063'  # Iris flowers atelier branch ID
                logger.info(f"🌸 ЦВЕТОЧНЫЙ расход → branch: Iris flowers atelier (ID: {branch_id})")
            
            # Налоги
            tax_rate = float(analysis.get('tax_rate') or 0)
            vat_amount = float(analysis.get('vat_amount') or 0)
            tax_id = None
            if tax_rate > 0:
                tax_id = find_tax_by_percent(org_id, tax_rate)
                logger.info(f"💰 Налог: {tax_rate}% (ID: {tax_id}), сумма налога: {vat_amount}")
            
            # Сумма для парагонов (VAT уже включен в gross_amount)
            amount = analysis.get('gross_amount') or analysis.get('total_amount', 0)
            logger.info(f"💰 Суммы из анализа: gross={analysis.get('gross_amount')}, net={analysis.get('net_amount')}, vat={analysis.get('vat_amount')}")
            
            # Формируем краткие notes (до 100 символов)
            line_items = analysis.get('line_items', [])
            if line_items and len(line_items) > 1:
                # Многопозиционная покупка - обобщаем
                notes = f"{len(line_items)} items: {amount:.2f} {analysis.get('currency', 'PLN')}"
                if tax_rate > 0:
                    notes += f" (VAT {tax_rate}%)"
            elif line_items:
                # Одна позиция - показываем название
                item_desc = line_items[0].get('description', 'Item')[:30]
                notes = f"{item_desc}: {amount:.2f} {analysis.get('currency', 'PLN')}"
                if tax_rate > 0:
                    notes += f" (VAT {tax_rate}%)"
            else:
                # Фолбэк без line_items
                notes = f"Receipt: {amount:.2f} {analysis.get('currency', 'PLN')}"
                if tax_rate > 0:
                    notes += f" (VAT {tax_rate}%)"
            
            # Проверяем лимит 100 символов
            if len(notes) > 100:
                notes = notes[:97] + "..."
            
            # Детальное описание
            if line_items and len(line_items) > 1:
                description = f"Receipt from {analysis.get('supplier_name')}. Doc #{analysis.get('bill_number')}. {len(line_items)} items purchased"
            elif line_items:
                description = f"Receipt from {analysis.get('supplier_name')}. Doc #{analysis.get('bill_number')}. {line_items[0].get('description', 'Item')[:50]}"
            else:
                description = f"Receipt from {analysis.get('supplier_name')}. Doc #{analysis.get('bill_number')}. Total {amount:.2f} {analysis.get('currency', 'PLN')}"
            
            expense_payload = {
                "account_id": expense_account_id,
                "paid_through_account_id": paid_through_account_id,
                "vendor_id": supplier.get('contact_id'),
                "vendor_name": analysis.get('supplier_name'),
                "date": analysis.get('issue_date') or analysis.get('date') or datetime.now().strftime('%Y-%m-%d'),
                "amount": float(amount),
                "currency_code": analysis.get('currency', 'PLN'),
                "reference_number": analysis.get('bill_number', ''),
                "description": description,
                "notes": notes,
                "is_inclusive_tax": True  # VAT включен в сумму для парагонов
            }
            
            # Добавляем branch_id для цветочных расходов
            if branch_id:
                expense_payload["branch_id"] = branch_id
            
            # Добавляем налог если есть
            if tax_id and vat_amount > 0:
                expense_payload["tax_id"] = tax_id
                expense_payload["tax_amount"] = float(vat_amount)
            
            logger.info(f"💳 Expense payload: сумма={amount} {analysis.get('currency', 'PLN')}, способ оплаты={payment_type}")
            
            return expense_payload, None
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания expense payload: {e}")
            return {}, str(e)
    
    @staticmethod
    def create_expense(org_id: str, expense_payload: Dict) -> Dict:
        """
        Создает Expense в Zoho Books
        
        Returns:
            Dict с результатом создания
        """
        try:
            access_token = get_access_token()
            if not access_token:
                return {"error": "Ошибка получения токена Zoho"}
                
            expense_url = f"https://www.zohoapis.eu/books/v3/expenses?organization_id={org_id}"
            headers = {
                "Authorization": f"Zoho-oauthtoken {access_token}",
                "Content-Type": "application/json"
            }
            
            response = requests.post(expense_url, headers=headers, json=expense_payload)
            response_data = response.json() if response.content else {}
            
            if response.status_code == 201 and response_data.get('expense'):
                return response_data
            else:
                return {"error": response_data}
                
        except Exception as e:
            return {"error": str(e)}
    
    @staticmethod
    async def create_expense_from_analysis(
        analysis: Dict, 
        supplier: Dict, 
        org_id: str,
        org_name: str,
        file_path: Optional[str] = None
    ) -> Dict:
        """
        Полный цикл создания Expense из анализа документа
        
        Args:
            analysis: Результат анализа документа
            supplier: Данные поставщика из Zoho
            org_id: ID организации
            org_name: Название организации
            file_path: Путь к файлу для прикрепления
            
        Returns:
            Dict с результатом создания
        """
        try:
            # Создаем payload
            expense_payload, error = ExpenseService.create_expense_payload(
                analysis, supplier, org_id, org_name
            )
            
            if error:
                return {"error": error}
            
            # Создаем Expense
            result = ExpenseService.create_expense(org_id, expense_payload)
            
            if 'error' in result:
                return result
            
            expense_data = result.get('expense', {})
            expense_id = expense_data.get('expense_id')
            
            # Прикрепляем файл если указан
            if file_path and expense_id:
                try:
                    import os
                    filename = os.path.basename(file_path)
                    
                    attachment_result = await AttachmentManager.attach_to_entity(
                        'expense', expense_id, org_id, file_path, get_access_token()
                    )
                    
                    if attachment_result.get('success'):
                        logger.info(f"📎 PDF успешно прикреплён к Expense {expense_id}")
                    else:
                        logger.warning(f"⚠️ Ошибка прикрепления PDF к Expense {expense_id}: {attachment_result.get('error')}")
                        
                except Exception as e:
                    logger.error(f"❌ Ошибка прикрепления файла к Expense: {e}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания Expense: {e}")
            return {"error": str(e)}
