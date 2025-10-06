"""
Bill Duplicate Checker - Простая проверка дубликатов Bills для предотвращения ошибок

Создано: 2025-09-08
Цель: Предупреждать о дубликатах Bills и спрашивать пользователя о создании
"""

from typing import Dict, List, Optional
import logging
import json
import os
from datetime import datetime

logger = logging.getLogger(__name__)

class BillDuplicateChecker:
    """Простая проверка дубликатов Bills для предотвращения ошибок"""
    
    def __init__(self):
        self.cache_dir = "data/bills_cache"
        os.makedirs(self.cache_dir, exist_ok=True)
    
    def check_duplicate(self, org_id: str, bill_number: str, vendor_name: str) -> Optional[Dict]:
        """
        Проверяет дубликат Bill в пределах организации
        
        Args:
            org_id: ID организации
            bill_number: Номер Bill
            vendor_name: Название поставщика
            
        Returns:
            Информация о дубликате или None
        """
        try:
            # Используем существующую функцию из bills_cache_manager
            from functions.bills_cache_manager import find_bill_candidates_in_cache, ensure_bills_cache
            
            # Обеспечиваем актуальность кэша
            ensure_bills_cache(org_id)
            
            # Ищем кандидатов
            candidates = find_bill_candidates_in_cache(org_id, bill_number)
            
            if candidates:
                logger.info(f"🚨 Найдены потенциальные дубликаты Bills: {len(candidates)}")
                
                # Проверяем через API для получения деталей
                from functions.zoho_api import get_bill_details
                
                for candidate in candidates:
                    bill_id = candidate.get('bill_id')
                    bill_details = get_bill_details(org_id, bill_id)
                    
                    if bill_details:
                        cached_vendor = bill_details.get('vendor_name', '')
                        cached_number = bill_details.get('bill_number', '')
                        
                        # Проверяем совпадение поставщика и номера
                        if (self._normalize_name(vendor_name) == self._normalize_name(cached_vendor) and
                            self._normalize_bill_number(bill_number) == self._normalize_bill_number(cached_number)):
                            
                            return {
                                'bill_id': bill_id,
                                'bill_number': cached_number,
                                'vendor_name': cached_vendor,
                                'date': bill_details.get('date'),
                                'branch_id': bill_details.get('branch_id'),
                                'amount': bill_details.get('total'),
                                'currency': bill_details.get('currency_code')
                            }
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка проверки дубликатов: {e}")
            return None
    
    def _normalize_name(self, name: str) -> str:
        """Нормализует название для сравнения"""
        if not name:
            return ""
        
        # Убираем лишние пробелы, приводим к верхнему регистру
        normalized = " ".join(name.upper().split())
        
        # Убираем общие сокращения
        replacements = {
            'SPÓŁKA Z OGRANICZONĄ ODPOWIEDZIALNOŚCIĄ': 'SP Z O O',
            'SP. Z O.O.': 'SP Z O O',
            'SP Z O O': 'SP Z O O',
            'GMBH': 'GMBH',
            'LIMITED': 'LTD',
            'LLC': 'LLC'
        }
        
        for old, new in replacements.items():
            normalized = normalized.replace(old, new)
        
        return normalized.strip()
    
    def _normalize_bill_number(self, bill_number: str) -> str:
        """Нормализует номер Bill для сравнения"""
        if not bill_number:
            return ""
        
        # Убираем пробелы и приводим к верхнему регистру
        return bill_number.replace(' ', '').upper()
    
    def create_duplicate_warning_message(self, duplicate: Dict, new_bill_data: Dict) -> str:
        """
        Создает сообщение-предупреждение о дубликате
        
        Args:
            duplicate: Информация о найденном дубликате
            new_bill_data: Данные нового Bill
            
        Returns:
            Форматированное сообщение
        """
        message = f"🚨 ВНИМАНИЕ: Найден возможный дубликат Bill!\n\n"
        
        message += f"📋 **СУЩЕСТВУЮЩИЙ BILL:**\n"
        message += f"• Номер: {duplicate['bill_number']}\n"
        message += f"• Поставщик: {duplicate['vendor_name']}\n"
        message += f"• Дата: {duplicate['date']}\n"
        message += f"• Сумма: {duplicate.get('amount', 'N/A')} {duplicate.get('currency', '')}\n"
        message += f"• ID: {duplicate['bill_id']}\n\n"
        
        message += f"📄 **НОВЫЙ BILL:**\n"
        message += f"• Номер: {new_bill_data.get('bill_number')}\n"
        message += f"• Поставщик: {new_bill_data.get('vendor_name')}\n"
        message += f"• Дата: {new_bill_data.get('date')}\n"
        message += f"• Сумма: {new_bill_data.get('total_amount')} {new_bill_data.get('currency', 'PLN')}\n\n"
        
        message += f"❓ **Создать новый Bill?**\n"
        message += f"(Zoho позволяет одинаковые номера в разных филиалах)"
        
        return message
    
    @classmethod
    def get_branch_by_org_id(cls, org_id: str) -> Optional[Dict]:
