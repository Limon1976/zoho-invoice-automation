"""
WorkDrive Batch Processor
Ежедневная обработка инвойсов из Zoho WorkDrive с созданием Bills и Telegram уведомлениями
"""

import os
import sys
import json
import asyncio
import logging
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional, Tuple
from pathlib import Path

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from functions.zoho_workdrive import ZohoWorkDriveAPI, get_workdrive_access_token
from functions.agent_invoice_parser import analyze_proforma_via_agent
from functions.zoho_api import bill_exists_smart, create_bill, find_supplier_in_zoho
from functions.contact_creator import create_supplier_from_document
from functions.universal_document_processor import process_document_universal
# Функция отправки сообщений в Telegram будет определена ниже
from dotenv import load_dotenv


# Загружаем переменные окружения
load_dotenv()

# НАСТРОЙКА ДЕТАЛЬНОГО ЛОГИРОВАНИЯ
class WorkDriveLogger:
    """Детальное логирование WorkDrive обработки"""
    
    def __init__(self):
        self.logger = logging.getLogger('workdrive_batch')
        
        # Создаем отдельный файл для логов WorkDrive
        os.makedirs('logs', exist_ok=True)
        handler = logging.FileHandler('logs/workdrive_batch.log', encoding='utf-8')
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        
        if not self.logger.handlers:
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)
    
    def step(self, step_num: int, description: str, **kwargs):
        """Логирует шаг обработки"""
        msg = f"🔄 ШАГ {step_num}: {description}"
        if kwargs:
            details = ", ".join(f"{k}={v}" for k, v in kwargs.items())
            msg += f" | {details}"
        self.logger.info(msg)
        print(msg)  # Дублируем в консоль
    
    def success(self, operation: str, **kwargs):
        """Логирует успешную операцию"""
        msg = f"✅ УСПЕХ: {operation}"
        if kwargs:
            details = ", ".join(f"{k}={v}" for k, v in kwargs.items())
            msg += f" | {details}"
        self.logger.info(msg)
        print(msg)
    
    def error(self, operation: str, error: str, **kwargs):
        """Логирует ошибку"""
        msg = f"❌ ОШИБКА: {operation} | {error}"
        if kwargs:
            details = ", ".join(f"{k}={v}" for k, v in kwargs.items())
            msg += f" | {details}"
        self.logger.error(msg)
        print(msg)
    
    def warning(self, operation: str, warning: str, **kwargs):
        """Логирует предупреждение"""
        msg = f"⚠️ ПРЕДУПРЕЖДЕНИЕ: {operation} | {warning}"
        if kwargs:
            details = ", ".join(f"{k}={v}" for k, v in kwargs.items())
            msg += f" | {details}"
        self.logger.warning(msg)
        print(msg)

logger = logging.getLogger(__name__)

async def send_message_to_admin(message: str, parse_mode: str = None):
    """Отправляет сообщение админу в Telegram"""
    try:
        import requests
        
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        admin_id = os.getenv("ADMIN_ID")
        
        if not bot_token or not admin_id:
            logger.error("❌ Не найдены TELEGRAM_BOT_TOKEN или ADMIN_ID в .env")
            return
        
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        data = {
            "chat_id": admin_id,
            "text": message
        }
        
        if parse_mode:
            data["parse_mode"] = parse_mode
        
        response = requests.post(url, json=data)
        if response.status_code == 200:
            logger.info("📱 Сообщение отправлено в Telegram")
        else:
            logger.error(f"❌ Ошибка отправки в Telegram: {response.status_code} - {response.text}")
            
    except Exception as e:
        logger.error(f"❌ Исключение при отправке в Telegram: {e}")

class WorkDriveBatchProcessor:
    """Класс для пакетной обработки инвойсов из WorkDrive"""
    
    def __init__(self):
        self.workdrive = ZohoWorkDriveAPI()
        self.admin_id = os.getenv("ADMIN_ID")
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        
        # Папки для обработки
        self.download_dir = "data/workdrive_batch"
        self.processed_log = "data/workdrive_processed.json"
        
        # Убеждаемся что папки существуют
        os.makedirs(self.download_dir, exist_ok=True)
        os.makedirs(os.path.dirname(self.processed_log), exist_ok=True)
        
        # ИНИЦИАЛИЗАЦИЯ ДЕТАЛЬНОГО ЛОГГЕРА
        self.workdrive_logger = WorkDriveLogger()
    
    def get_processed_files(self) -> Dict[str, str]:
        """Получает список уже обработанных файлов"""
        try:
            if os.path.exists(self.processed_log):
                with open(self.processed_log, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Ошибка чтения лога обработанных файлов: {e}")
        return {}
    
    def mark_file_processed(self, file_id: str, file_name: str, bill_id: str = None, error: str = None):
        """Отмечает файл как обработанный"""
        try:
            processed = self.get_processed_files()
            processed[file_id] = {
                "file_name": file_name,
                "processed_at": datetime.now().isoformat(),
                "bill_id": bill_id,
                "status": "success" if bill_id else "error",
                "error": error
            }
            
            with open(self.processed_log, 'w', encoding='utf-8') as f:
                json.dump(processed, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            logger.error(f"Ошибка записи в лог обработанных файлов: {e}")
    
    def get_files_for_date(self, target_date: str) -> List[Dict]:
        """Получает PDF файлы за указанную дату, исключая уже обработанные"""
        logger.info(f"🔍 Поиск файлов за {target_date}")
        
        # Получаем все PDF и изображения за дату
        all_files = self.workdrive.get_processable_files_by_date(target_date)
        
        # Исключаем уже обработанные
        processed = self.get_processed_files()
        new_files = []
        
        for file in all_files:
            file_id = file.get('id')
            if file_id not in processed:
                new_files.append(file)
                logger.info(f"📄 Новый файл: {file.get('name')}")
            elif processed[file_id].get('status') == 'error':
                new_files.append(file)
                logger.info(f"🔄 Повторная обработка файла с ошибкой: {file.get('name')}")
            else:
                logger.info(f"⏭️ Файл уже обработан: {file.get('name')}")
        
        logger.info(f"📊 Файлов для обработки: {len(new_files)}/{len(all_files)} (новые + с ошибками)")
        return new_files
    
    async def process_single_file(self, file: Dict) -> Dict:
        """Обрабатывает один файл с детальным логированием каждого шага"""
        """Обрабатывает один файл: скачивание → LLM анализ → создание Bill"""
        file_id = file.get('id')
        file_name = file.get('name', f'file_{file_id}.pdf')
        
        self.workdrive_logger.step(1, "НАЧАЛО ОБРАБОТКИ", file_name=file_name, file_id=file_id)
        
        result = {
            'file_id': file_id,
            'file_name': file_name,
            'success': False,
            'bill_id': None,
            'bill_number': None,
            'error': None,
            'supplier_name': None,
            'org_id': None
        }
        
        try:
            self.workdrive_logger.step(2, "СКАЧИВАНИЕ ФАЙЛА", file_name=file_name)
            
            # 1. Скачиваем файл
            local_path = os.path.join(self.download_dir, file_name)
            download_success = self.workdrive.download_file(file_id, local_path, file_name)
            
            if not download_success:
                self.workdrive_logger.error("СКАЧИВАНИЕ ФАЙЛА", "Ошибка скачивания", file_name=file_name)
                result['error'] = "Ошибка скачивания файла"
                return result
            
            file_size_mb = os.path.getsize(local_path) / (1024*1024)
            self.workdrive_logger.success("ФАЙЛ СКАЧАН", file_path=local_path, size_mb=f"{file_size_mb:.1f}")
            
            # 2. Обрабатываем через LLM pipeline
            self.workdrive_logger.step(3, "LLM АНАЛИЗ", file_name=file_name, file_type="image" if file_name.lower().endswith(('.jpeg', '.jpg', '.png', '.tiff')) else "pdf")
            
            # Проверяем тип файла и обрабатываем соответственно
            if file_name.lower().endswith(('.jpeg', '.jpg', '.png', '.tiff')):
                # Изображение - конвертируем в PDF и анализируем
                self.workdrive_logger.step(4, "КОНВЕРТАЦИЯ IMAGE→PDF", file_name=file_name)
                pdf_path = await self._convert_image_to_pdf(local_path, file_name)
                self.workdrive_logger.success("PDF СОЗДАН", pdf_path=pdf_path)
                
                analysis = analyze_proforma_via_agent(pdf_path)
                # Используем PDF для дальнейшей обработки
                local_path = pdf_path
            else:
                # PDF файл - обрабатываем как обычно
                analysis = analyze_proforma_via_agent(local_path)
            
            # Добавляем original_filename для perfect parser
            if analysis:
                analysis['original_filename'] = file_name
            
            if not analysis or 'error' in analysis:
                self.workdrive_logger.error("LLM АНАЛИЗ", f"Ошибка: {analysis.get('error', 'Unknown error')}", file_name=file_name)
                result['error'] = f"Ошибка LLM анализа: {analysis.get('error', 'Unknown error')}"
                return result
            
            # 3. Определяем организацию для создания Bill
            supplier_name = analysis.get('supplier_name', '')
            result['supplier_name'] = supplier_name
            
            # ДЕТАЛЬНЫЙ ЛОГ РЕЗУЛЬТАТОВ LLM АНАЛИЗА
            self.workdrive_logger.success("LLM АНАЛИЗ ЗАВЕРШЕН", 
                supplier_name=supplier_name, 
                supplier_vat=analysis.get('supplier_vat', ''),
                bill_number=analysis.get('bill_number', ''),
                total_amount=analysis.get('total_amount', 0))
            
            # Логируем поля для item_details
            available_descriptions = []
            if analysis.get('line_items'):
                line_items = analysis.get('line_items', [])
                if line_items:
                    first_desc = line_items[0].get('description', '')
                    available_descriptions.append(f"line_items[0]: '{first_desc[:50]}...'")
            
            for field in ['item_details', 'service_description', 'description']:
                value = analysis.get(field)
                if value:
                    available_descriptions.append(f"{field}: '{str(value)[:50]}...'")
            
            self.workdrive_logger.success("ДОСТУПНЫЕ ОПИСАНИЯ", 
                count=len(available_descriptions),
                descriptions=available_descriptions[:3])
            
            # Логика определения организации (как в telegram bot)
            org_id = self.determine_organization(analysis)
            result['org_id'] = org_id
            
            # 5. Проверяем дубликаты
            bill_number = analysis.get('bill_number') or analysis.get('invoice_number', '')
            document_date = analysis.get('invoice_date') or analysis.get('document_date', '')
            
            self.workdrive_logger.step(5, "ПРОВЕРКА ДУБЛИКАТОВ", bill_number=bill_number, vendor_name=supplier_name)
            
            existing_bill = bill_exists_smart(
                org_id=org_id,
                bill_number=bill_number,
                vendor_name=supplier_name,
                document_date=document_date
            )
            
            if existing_bill:
                # 🔄 НОВОЕ: Синхронизация - если Bill есть в Zoho но файл в WorkDrive не Final
                logger.info(f"🔍 Найден существующий Bill: {existing_bill.get('bill_id')}")
                
                # Проверяем статус файла в WorkDrive
                file_status = self.workdrive.check_file_final_status(file_id)
                
                if not file_status.get('is_final'):
                    logger.info(f"🔄 СИНХРОНИЗАЦИЯ: Bill есть в Zoho, но файл в WorkDrive не Final - помечаем")
                    
                    mark_success = self.workdrive.mark_file_as_final(
                        file_id,
                        existing_bill.get('bill_number', bill_number),
                        existing_bill.get('bill_id')
                    )
                    
                    if mark_success:
                        result['success'] = True
                        result['bill_id'] = existing_bill.get('bill_id')
                        result['bill_number'] = existing_bill.get('bill_number', bill_number)
                        result['sync_action'] = 'marked_as_final'
                        
                        logger.info(f"✅ СИНХРОНИЗАЦИЯ: Файл помечен как Final (Bill уже существовал)")
                        
                        # Уведомление о синхронизации
                        await self.send_sync_notification(result, analysis, existing_bill)
                        return result
                
                result['error'] = f"Дубликат: Bill {existing_bill.get('bill_number')} уже существует"
                result['bill_id'] = existing_bill.get('bill_id')
                return result
            
            # 6. УНИВЕРСАЛЬНАЯ ОБРАБОТКА через общий сервис
            self.workdrive_logger.step(6, "УНИВЕРСАЛЬНАЯ ОБРАБОТКА ДОКУМЕНТА", supplier_name=supplier_name, org_id=org_id)
            
            # Добавляем file_path для прикрепления файла
            analysis['file_path'] = local_path
            
            universal_result = await process_document_universal(analysis, org_id)
            
            if universal_result.get('success'):
                self.workdrive_logger.success("УНИВЕРСАЛЬНАЯ ОБРАБОТКА ЗАВЕРШЕНА", 
                    bill_id=universal_result.get('bill_id'),
                    bill_number=universal_result.get('bill_number'))
                
                # Копируем результат
                result['success'] = True
                result['bill_id'] = universal_result.get('bill_id')
                result['bill_number'] = universal_result.get('bill_number')
                
                # Помечаем файл как Final
                try:
                    mark_success = self.workdrive.mark_file_as_final(
                        file_id, 
                        result['bill_number'], 
                        result['bill_id']
                    )
                    
                    if mark_success:
                        self.workdrive_logger.success("MARK AS FINAL")
                        
                        # ОТПРАВЛЯЕМ TELEGRAM УВЕДОМЛЕНИЕ
                        await self.send_success_notification(result, analysis, mark_final_success=True)
                    
                except Exception as mark_e:
                    self.workdrive_logger.warning("MARK AS FINAL", f"Ошибка: {mark_e}")
                
                return result
            else:
                self.workdrive_logger.error("УНИВЕРСАЛЬНАЯ ОБРАБОТКА", universal_result.get('error', 'Unknown error'))
                result['error'] = universal_result.get('error')
                return result
            
            if not supplier:
                self.workdrive_logger.step(7, "СОЗДАНИЕ НОВОГО ПОСТАВЩИКА", supplier_name=supplier_name, supplier_vat=supplier_vat)
                
                # УНИВЕРСАЛЬНАЯ ЛОГИКА: Создаем новый контакт в Zoho если не найден
                try:
                    from functions.zoho_api import get_contact_details
                    
                    # Формируем данные для создания контакта
                    contact_payload = {
                        "contact_name": supplier_name,
                        "company_name": supplier_name,
                        "contact_type": "vendor",
                        "custom_fields": []
                    }
                    
                    # Добавляем VAT если есть
                    if supplier_vat:
                        vat_field = "cf_tax_id" if org_id == "20082562863" else "cf_vat_id"
                        contact_payload["custom_fields"].append({
                            "api_name": vat_field,
                            "value": supplier_vat
                        })
                        self.workdrive_logger.success("VAT ДОБАВЛЕН", vat_field=vat_field, vat_value=supplier_vat)
                    
                    # Создаем контакт напрямую через Zoho API
                    from config.zoho_auth import get_access_token
                    import requests
                    
                    access_token = get_access_token()
                    headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}
                    url = f"https://www.zohoapis.eu/books/v3/contacts?organization_id={org_id}"
                    
                    response = requests.post(url, json=contact_payload, headers=headers)
                    
                    if response.status_code == 201:
                        created_contact = response.json().get('contact', {})
                        contact_id = created_contact.get('contact_id')
                        
                        supplier = {
                            'contact_id': contact_id,
                            'contact_name': supplier_name,
                            'vat_number': supplier_vat
                        }
                        
                        self.workdrive_logger.success("НОВЫЙ КОНТАКТ СОЗДАН", 
                            contact_id=contact_id, 
                            supplier_name=supplier_name,
                            org_id=org_id)
                    else:
                        error_data = response.json() if response.content else {'error': 'Unknown error'}
                        self.workdrive_logger.error("СОЗДАНИЕ КОНТАКТА", f"Zoho API ошибка: {error_data}", supplier_name=supplier_name)
                        result['error'] = f"Не удалось создать контакт: {error_data}"
                        return result
                    
                    # Обновляем кэш контактов после создания нового
                    logger.info("🔄 Обновляем кэш контактов после создания поставщика...")
                    try:
                        import sys
                        from pathlib import Path
                        sys.path.append(str(Path(__file__).parent.parent))
                        from src.domain.services.contact_cache import OptimizedContactCache
                        from functions.zoho_api import get_contact_by_name
                        
                        # Получаем свежую информацию о созданном контакте
                        # Пробуем поиск по VAT (более надежно чем по имени)
                        fresh_contact = None
                        if supplier_vat:
                            from functions.zoho_api import get_contact_by_vat
                            fresh_contact = get_contact_by_vat(supplier_vat, org_id)
                        
                        # Fallback: поиск по имени
                        if not fresh_contact:
                            fresh_contact = get_contact_by_name(supplier_name, org_id)
                            
                        if fresh_contact:
                            # Определяем файл кэша для организации
                            if org_id == "20082562863":  # PARKENTERTAINMENT
                                cache_file = "data/optimized_cache/PARKENTERTAINMENT_optimized.json"
                            elif org_id == "772348639":  # TaVie Europe
                                cache_file = "data/optimized_cache/TAVIE_EUROPE_optimized.json"
                            else:
                                cache_file = "data/optimized_cache/all_contacts_optimized.json"
                            
                            # Обновляем кэш
                            cache = OptimizedContactCache(cache_file)
                            cache.upsert_contact_from_zoho(fresh_contact)
                            cache.save_cache()
                            logger.info("✅ Кэш контактов обновлен")
                        else:
                            logger.warning("⚠️ Свежий контакт не найден для обновления кэша")
                    except Exception as cache_e:
                        logger.warning(f"⚠️ Не удалось обновить кэш: {cache_e}")
                    
                    # Используем найденный fresh_contact или повторно ищем
                    if fresh_contact:
                        supplier = fresh_contact
                        logger.info(f"✅ Используем найденный контакт: {fresh_contact.get('contact_name')} (ID: {fresh_contact.get('contact_id')})")
                    else:
                        # Повторно ищем созданного поставщика с правильным VAT
                        supplier = find_supplier_in_zoho(
                            org_id=org_id,
                            supplier_name=supplier_name,
                            supplier_vat=supplier_vat  # Используем правильную переменную
                        )
                    
                    # Если всё ещё не найден, извлекаем contact_id из сообщения ContactCreator
                    if not supplier and 'message' in locals():
                        self.workdrive_logger.step(8, "ИЗВЛЕЧЕНИЕ CONTACT_ID ИЗ СООБЩЕНИЯ", message=message)
                        
                        # Ищем ID в сообщении ContactCreator
                        import re
                        contact_id_match = re.search(r'ID:\s*([0-9]+)', message)
                        if contact_id_match:
                            contact_id = contact_id_match.group(1)
                            
                            # Создаем объект поставщика с найденным ID
                            supplier = {
                                'contact_id': contact_id,
                                'contact_name': supplier_name,
                                'vat_number': supplier_vat
                            }
                            self.workdrive_logger.success("CONTACT_ID ИЗВЛЕЧЕН", contact_id=contact_id, supplier_name=supplier_name)
                        else:
                            self.workdrive_logger.error("ИЗВЛЕЧЕНИЕ CONTACT_ID", "ID не найден в сообщении", message=message)
                    
                    # Последний fallback
                    if not supplier:
                        self.workdrive_logger.warning("FALLBACK ПОСТАВЩИК", "Поставщик не найден после создания, используем fallback")
                        supplier = {
                            'contact_id': None,
                            'contact_name': supplier_name,
                            'vat_number': supplier_vat
                        }
                        # Пропускаем создание Bill если нет contact_id
                        result['error'] = f"Не удалось найти созданного поставщика: {supplier_name}"
                        return result
                        
                except Exception as e:
                    logger.error(f"❌ Исключение при создании поставщика: {e}")
                    result['error'] = f"Исключение при создании поставщика: {str(e)}"
                    return result
            
            # 6. Определяем тип документа (Bill или Expense)
            document_action = self.determine_document_action(analysis)
            
            if document_action == 'EXPENSE':
                # Создаем Expense для парагонов фискальных
                logger.info(f"💳 Создание Expense в Zoho для: {supplier_name}")
                expense_response = await self.create_expense_from_analysis(analysis, supplier, org_id, local_path)
                
                if 'error' in expense_response:
                    result['error'] = f"Ошибка создания Expense: {expense_response['error']}"
                    return result
                
                expense = expense_response.get('expense', {})
                result['bill_id'] = expense.get('expense_id')  # Используем expense_id как bill_id
                result['bill_number'] = expense.get('expense_number')
                
                # ExpenseService уже прикрепил файл, логируем это
                logger.info(f"📎 Файл уже прикреплен к Expense через ExpenseService")
                
            else:
                # Создаем Bill для обычных инвойсов
                self.workdrive_logger.step(9, "СОЗДАНИЕ BILL PAYLOAD", supplier_name=supplier_name, org_id=org_id)
                bill_payload = self.create_bill_payload(analysis, supplier, org_id, local_path)
                
                # Логируем ключевые параметры payload
                line_items = bill_payload.get('line_items', [])
                vendor_id = bill_payload.get('vendor_id')
                total_amount = sum(float(item.get('rate', 0)) * float(item.get('quantity', 0)) for item in line_items)
                
                self.workdrive_logger.success("BILL PAYLOAD СОЗДАН", 
                    vendor_id=vendor_id, 
                    line_items_count=len(line_items),
                    total_amount=f"{total_amount:.2f}")
                
                # Детальный лог первого line_item для отладки
                if line_items:
                    first_item = line_items[0]
                    self.workdrive_logger.success("ПЕРВЫЙ LINE_ITEM", 
                        description=first_item.get('description', ''),
                        account_id=first_item.get('account_id', ''),
                        rate=first_item.get('rate', 0))
                
                self.workdrive_logger.step(10, "ОТПРАВКА В ZOHO", bill_number=bill_number)
                bill_response = create_bill(org_id, bill_payload)
                
                if 'error' in bill_response:
                    error_msg = bill_response['error']
                    self.workdrive_logger.error("СОЗДАНИЕ BILL", f"Zoho API ошибка: {error_msg}", bill_number=bill_number)
                    
                    # 🔄 ОБРАБОТКА ОШИБКИ ДУБЛИКАТА (13011) - АКТИВИРУЕМ СИНХРОНИЗАЦИЮ
                    if ('13011' in str(error_msg) or 'already been created' in str(error_msg)):
                        logger.info(f"🔄 Ошибка дубликата обнаружена - ищем существующий Bill для синхронизации")
                        
                        # Принудительно ищем существующий Bill
                        from functions.zoho_api import get_bills, get_bill_details
                        
                        try:
                            # Ищем Bill по номеру через улучшенный поиск
                            found_bill = None
                            
                            # Метод 1: Прямой поиск через bill_exists_smart
                            try:
                                existing = bill_exists_smart(org_id, bill_number, None, supplier_name, document_date)
                                if existing:
                                    found_bill = existing
                                    logger.info(f"🔍 Найден через bill_exists_smart: {existing.get('bill_id')}")
                            except Exception as e:
                                logger.warning(f"⚠️ bill_exists_smart не сработал: {e}")
                            
                            # Метод 2: Поиск по месяцам если первый метод не сработал
                            if not found_bill:
                                current_year = datetime.now().year
                                for month in [8, 7, 9]:  # Проверяем август, июль, сентябрь
                                    try:
                                        bills = get_bills(org_id, current_year, month)
                                        for bill_num, bill_id_found, _, _ in bills:
                                            # Улучшенное сравнение номеров
                                            if (bill_number.strip() in bill_num or 
                                                bill_num in bill_number.strip() or
                                                bill_number.replace('/', '-') == bill_num.replace('/', '-')):
                                                found_bill = get_bill_details(org_id, bill_id_found)
                                                if found_bill:
                                                    logger.info(f"🔍 Найден через месячный поиск ({month}): {bill_id_found}")
                                                    break
                                        if found_bill:
                                            break
                                    except Exception as e:
                                        logger.warning(f"⚠️ Ошибка поиска в месяце {month}: {e}")
                            
                            if found_bill:
                                logger.info(f"🔍 Найден существующий Bill для синхронизации: {found_bill.get('bill_id')}")
                                
                                # Проверяем статус файла в WorkDrive
                                file_status = self.workdrive.check_file_final_status(file_id)
                                
                                if not file_status.get('is_final'):
                                    logger.info(f"🔄 СИНХРОНИЗАЦИЯ: Помечаем файл как Final")
                                    
                                    mark_success = self.workdrive.mark_file_as_final(
                                        file_id,
                                        found_bill.get('bill_number', bill_number),
                                        found_bill.get('bill_id')
                                    )
                                    
                                    if mark_success:
                                        result['success'] = True
                                        result['bill_id'] = found_bill.get('bill_id')
                                        result['bill_number'] = found_bill.get('bill_number', bill_number)
                                        result['sync_action'] = 'duplicate_error_sync'
                                        
                                        logger.info(f"✅ СИНХРОНИЗАЦИЯ: Файл помечен как Final (найден через ошибку дубликата)")
                                        
                                        # Уведомление о синхронизации
                                        await self.send_sync_notification(result, analysis, found_bill)
                                        return result
                                else:
                                    logger.info(f"ℹ️ Файл уже помечен как Final, дубликат игнорируется")
                                    result['success'] = True
                                    result['bill_id'] = found_bill.get('bill_id')
                                    result['bill_number'] = found_bill.get('bill_number', bill_number)
                                    result['sync_action'] = 'already_final'
                                    
                                    # 📱 ИСПРАВЛЕНИЕ: Отправляем уведомление для already_final
                                    await self.send_sync_notification(result, analysis, found_bill)
                                    return result
                                    
                        except Exception as sync_error:
                            logger.error(f"❌ Ошибка синхронизации при дубликате: {sync_error}")
                    
                    result['error'] = f"Ошибка создания Bill: {error_msg}"
                    return result
                
                bill = bill_response.get('bill', {})
                result['bill_id'] = bill.get('bill_id')
                result['bill_number'] = bill.get('bill_number')
                
                # 🏷️ НОВОЕ: Помечаем файл как Final в WorkDrive после успешного создания Bill
                logger.info(f"🏷️ Помечаем файл {file_id} как Final в WorkDrive...")
                mark_success = self.workdrive.mark_file_as_final(
                    file_id, 
                    result['bill_number'], 
                    result['bill_id']
                )
                
                if mark_success:
                    logger.info(f"✅ Файл {file_id} помечен как Final в WorkDrive")
                    result['marked_as_final'] = True
                else:
                    logger.warning(f"⚠️ Не удалось пометить файл {file_id} как Final в WorkDrive")
                    result['marked_as_final'] = False
                
                # Прикрепляем файл к Bill через AttachmentManager
                try:
                    from telegram_bot.services.attachment_manager import AttachmentManager
                    from functions.zoho_api import get_access_token
                    
                    attach_result = await AttachmentManager.attach_to_entity(
                        entity_type='bill',
                        entity_id=result['bill_id'],
                        org_id=org_id,
                        file_path=local_path,
                        access_token=get_access_token()
                    )
                    
                    if attach_result.get('success'):
                        logger.info(f"📎 Файл успешно прикреплен к Bill через AttachmentManager")
                    else:
                        logger.warning(f"⚠️ Ошибка прикрепления файла: {attach_result.get('error')}")
                        
                except Exception as e:
                    logger.error(f"❌ Ошибка прикрепления файла к Bill: {e}")
            
            
            result['success'] = True
            logger.info(f"✅ Файл {file_name} успешно обработан → Bill #{result['bill_number']}")
            
            # 📱 НОВОЕ: Отправляем Telegram уведомление об успешной обработке
            try:
                await self.send_success_notification(result, analysis, result.get('marked_as_final', False))
                logger.info(f"📱 Telegram уведомление отправлено")
            except Exception as notif_error:
                logger.error(f"❌ Ошибка отправки Telegram уведомления: {notif_error}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка обработки файла {file_name}: {e}")
            result['error'] = str(e)
        
        finally:
            # Удаляем временный файл
            try:
                if os.path.exists(local_path):
                    os.remove(local_path)
            except Exception:
                pass
        
        return result
    
    async def send_success_notification(self, result: Dict, analysis: Dict, mark_final_success: bool = False):
        """Отправляет уведомление об успешной обработке"""
        try:
            message = f"✅ WORKDRIVE УСПЕШНО ОБРАБОТАН\n\n"
            message += f"📄 Файл: {result['file_name']}\n"
            message += f"🏪 Поставщик: {result['supplier_name']}\n"
            message += f"📋 Bill: #{result['bill_number']} (ID: {result['bill_id']})\n"
            message += f"🏢 Организация: {'PARKENTERTAINMENT' if result['org_id'] == '20082562863' else 'TaVie Europe OÜ'}\n"
            
            if analysis.get('total_amount'):
                message += f"💰 Сумма: {analysis['total_amount']} {analysis.get('currency', 'PLN')}\n"
            
            # Статус пометки как Final
            if mark_final_success:
                message += f"🏷️ Файл помечен как Final в WorkDrive ✅\n"
            else:
                message += f"⚠️ Файл НЕ помечен как Final в WorkDrive\n"
            
            # Ссылка на Bill в Zoho
            bill_url = f"https://books.zoho.eu/app/{result['org_id']}#/bills/{result['bill_id']}"
            message += f"\n🔗 Открыть в Zoho: {bill_url}"
            
            await send_message_to_admin(message)
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки уведомления об успехе: {e}")
            
            await send_message_to_admin(message)
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки уведомления об успехе: {e}")
    
    async def send_sync_notification(self, result: Dict, analysis: Dict, existing_bill: Dict):
        """Отправляет уведомление о синхронизации (файл помечен как Final для существующего Bill)"""
        try:
            message = f"🔄 СИНХРОНИЗАЦИЯ WORKDRIVE\n\n"
            message += f"📄 Файл: {result['file_name']}\n"
            message += f"🏪 Поставщик: {result['supplier_name']}\n"
            message += f"📋 Существующий Bill: #{result['bill_number']} (ID: {result['bill_id']})\n"
            message += f"🏢 Организация: {'PARKENTERTAINMENT' if result['org_id'] == '20082562863' else 'TaVie Europe OÜ'}\n"
            message += f"\n🏷️ Файл помечен как Final в WorkDrive ✅\n"
            message += f"ℹ️ Bill уже существовал в Zoho Books\n"
            
            # Ссылка на Bill в Zoho
            bill_url = f"https://books.zoho.eu/app/{result['org_id']}#/bills/{result['bill_id']}"
            message += f"\n🔗 Открыть в Zoho: {bill_url}"
            
            await send_message_to_admin(message)
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки уведомления о синхронизации: {e}")
    
    def determine_organization(self, analysis: Dict) -> str:
        """Определяет организацию для создания Bill на основе анализа документа"""
        # Используем новую логику филиалов с Branch Manager
        try:
            from telegram_bot.services.branch_manager import BranchManager
            
            # Определяем филиал через Branch Manager
            branch = BranchManager.determine_branch(analysis)
            org_id = branch['org_id']
            branch_name = branch['name']
            
            logger.info(f"🏢 Определен филиал: {branch_name} (org_id: {org_id})")
            
            # Сохраняем информацию о филиале для использования в других методах
            self.current_branch = branch
            
            # Определяем ключ филиала
            branch_key = None
            for key, branch_config in BranchManager.get_all_branches().items():
                if branch_config['name'] == branch['name']:
                    branch_key = key
                    break
            
            # Если это цветочный филиал, активируем специальную обработку
            if branch_key and BranchManager.is_flowers_branch(branch_key):
                logger.info("🌸 Активирована специальная обработка для цветочного филиала")
                self.is_flowers_processing = True
            else:
                self.is_flowers_processing = False
            
            return org_id
            
        except ImportError:
            # Fallback если Branch Manager недоступен
            logger.warning("⚠️ Branch Manager недоступен, используем PARKENTERTAINMENT по умолчанию")
            return "20082562863"  # PARKENTERTAINMENT
    
    def create_bill_payload(self, analysis: Dict, supplier: Dict, org_id: str, local_path: str) -> Dict:
        """Создает payload для Zoho Bill API из анализа документа - ТОЧНАЯ КОПИЯ ЛОГИКИ ИЗ TELEGRAM BOT"""
        from functions.llm_document_extractor import llm_select_account
        from functions.zoho_api import get_chart_of_accounts, find_tax_by_percent
        
        logger.info(f"📋 Создание Bill payload для {supplier.get('contact_name', 'Unknown supplier')}")
        
        # 1. ОПРЕДЕЛЯЕМ ТИП ДОКУМЕНТА (как в Telegram bot)
        llm_cat = (analysis.get('product_category') or analysis.get('document_category') or '').upper()
        detected_flower_names = analysis.get('detected_flower_names') or []
        supplier_name = (analysis.get('supplier_name') or '').lower()
        
        # 🌸 HIBISPOL всегда цветочный поставщик
        is_hibispol_flower_supplier = 'hibispol' in supplier_name
        is_flowers_doc = (llm_cat == 'FLOWERS' and bool(detected_flower_names)) or is_hibispol_flower_supplier
        
        logger.info(f"🌸 DEBUG: llm_cat='{llm_cat}', detected_flowers={len(detected_flower_names)}, hibispol={is_hibispol_flower_supplier}")
        logger.info(f"🌸 DEBUG: is_flowers_doc={is_flowers_doc}")
        
        # 2. ОПРЕДЕЛЯЕМ INCLUSIVE/EXCLUSIVE НАЛОГ (ТОЧНАЯ КОПИЯ ИЗ TELEGRAM BOT)
        doc_text_lower = (analysis.get('extracted_text') or '').lower()
        
        # DEBUG: проверяем что в extracted_text
        logger.info(f"🔍 DEBUG extracted_text (первые 200 символов): {repr(doc_text_lower[:200])}")
        logger.info(f"🔍 DEBUG extracted_text длина: {len(doc_text_lower)}")
        
        # ТОЧНАЯ КОПИЯ ЛОГИКИ ИЗ HANDLERS.PY (строки 2131-2172)
        # УМНАЯ ЛОГИКА: определяем по структуре таблицы
        # 1. HIBISPOL (цветы): "cena brutto" в заголовках столбцов → inclusive = True
        # 2. Остальные: "wartość netto" в заголовках → inclusive = False
        
        # УНИВЕРСАЛЬНЫЕ ПАТТЕРНЫ (не привязанные к конкретным поставщикам)
        brutto_pattern = "wartość brutto" in doc_text_lower or "cena brutto" in doc_text_lower or "brutto" in doc_text_lower
        netto_price_pattern = "wartość netto" in doc_text_lower
        
        # Fallback маркеры для других случаев
        inclusive_markers = ["brutto", "gross", "tax inclusive", "cena brutto", "kwota brutto", "wartość brutto"]
        exclusive_markers = ["netto", "net price", "cena netto", "kwota netto", "tax exclusive", "wartość netto"]
        
        inclusive_found = any(m in doc_text_lower for m in inclusive_markers)
        exclusive_found = any(m in doc_text_lower for m in exclusive_markers)
        
        logger.info(f"🌸 DEBUG: Структурные паттерны - brutto_pattern: {brutto_pattern}, netto_price: {netto_price_pattern}")
        logger.info(f"🌸 DEBUG: Fallback маркеры - brutto: {inclusive_found}, netto: {exclusive_found}")
        
        # ИСПРАВЛЕННАЯ ЛОГИКА: если есть И нетто И брутто - это EXCLUSIVE документ
        if netto_price_pattern:
            inclusive = False
            logger.info("🌸 DEBUG: Нетто структура → EXCLUSIVE (wartość netto найдено)")
        elif brutto_pattern and not netto_price_pattern:
            inclusive = True
            logger.info("🌸 DEBUG: ТОЛЬКО brutto → INCLUSIVE (wartość brutto без netto)")
        # Fallback к старой логике с приоритетом EXCLUSIVE
        elif exclusive_found and not inclusive_found:
            inclusive = False
            logger.info("🌸 DEBUG: Fallback маркеры → EXCLUSIVE (только netto)")
        elif inclusive_found and not exclusive_found:
            inclusive = True
            logger.info("🌸 DEBUG: Fallback маркеры → INCLUSIVE (только brutto)")
        elif exclusive_found and inclusive_found:
            # Если найдены оба, приоритет EXCLUSIVE (более точный)
            inclusive = False
            logger.info("🌸 DEBUG: Fallback маркеры → EXCLUSIVE (оба найдены, приоритет netto)")
        else:
            inclusive = False  # По умолчанию exclusive
            logger.info("🌸 DEBUG: Fallback → EXCLUSIVE (по умолчанию)")
        
        logger.info(f"🌸 DEBUG: Итоговый налог {'INCLUSIVE (brutto)' if inclusive else 'EXCLUSIVE (netto)'}")
        
        # 3. ПОЛУЧАЕМ ACCOUNTS (исключаем Income accounts для входящих Bills)
        accounts = get_chart_of_accounts(org_id)
        
        # Фильтруем только Expense accounts (исключаем Income для входящих счетов)
        expense_accounts = []
        for acc in accounts:
            account_type = acc.get('account_type', '').lower()
            if account_type not in ['income', 'other_income', 'revenue']:
                expense_accounts.append(acc)
        
        account_names = [acc.get('account_name', '') for acc in expense_accounts]
        logger.info(f"🔍 DEBUG: Отфильтровано {len(expense_accounts)}/{len(accounts)} expense accounts (исключены Income)")
        
        # Ищем подходящий expense account для наших расходов
        preferred_account_id = None
        
        if is_flowers_doc:
            # Для цветов ищем Flowers account  
            for acc in expense_accounts:
                account_name = (acc.get('account_name') or '').strip().lower()
                if account_name == 'flowers':
                    preferred_account_id = acc.get('account_id')
                    self.workdrive_logger.success("ЦВЕТОЧНЫЙ ACCOUNT", account_name=acc.get('account_name'), account_id=preferred_account_id)
                    break
        
        if not preferred_account_id:
            # Fallback - первый expense account
            if expense_accounts:
                preferred_account_id = expense_accounts[0].get('account_id')
                self.workdrive_logger.success("FALLBACK EXPENSE ACCOUNT", account_name=expense_accounts[0].get('account_name'), account_id=preferred_account_id)
        
        line_items = []
        
        # 4. ЦВЕТОЧНЫЕ ДОКУМЕНТЫ: используем PERFECT FLOWER PARSER (как в Telegram bot)
        if is_flowers_doc:
            logger.info("🌸 ИСПОЛЬЗУЕМ PERFECT FLOWER PARSER для цветочного документа")
            try:
                # Сначала определяем путь к файлу (используем local_path для конвертированных файлов)
                file_name = analysis.get('original_filename', '')
                pdf_path = local_path  # Используем актуальный путь (для JPEG это конвертированный PDF)
                
                # Импортируем perfect parser
                from functions.perfect_flower_parser import extract_perfect_flower_data, convert_to_zoho_line_items
                
                # Извлекаем позиции через perfect parser
                perfect_positions = extract_perfect_flower_data(pdf_path)
                logger.info(f"🌸 PERFECT: Извлечено {len(perfect_positions)} позиций")
                
                # Конвертируем в line_items (передаем inclusive и org_id как в Telegram bot)
                line_items = convert_to_zoho_line_items(perfect_positions, inclusive_tax=inclusive, org_id=org_id)
                logger.info(f"🌸 PERFECT: Создано {len(line_items)} line_items (inclusive={inclusive})")
                
                # Если Perfect Parser не смог извлечь позиции, используем LLM
                if not line_items or len(line_items) == 0:
                    logger.info("🌸 PERFECT PARSER НЕ СМОГ ИЗВЛЕЧЬ ПОЗИЦИИ → используем LLM fallback")
                    line_items = self._create_llm_line_items(analysis, expense_accounts, preferred_account_id, org_id, inclusive)
                else:
                    # Добавляем flowers account_id для всех позиций
                    if preferred_account_id:
                        for item in line_items:
                            item["account_id"] = preferred_account_id
                        
            except Exception as e:
                logger.error(f"❌ Ошибка perfect parser: {e}")
                # Fallback: используем LLM line_items для цветов
                logger.info("🌸 FALLBACK: Используем LLM line_items для цветочного документа")
                line_items = self._create_llm_line_items(analysis, expense_accounts, preferred_account_id, org_id, inclusive)
        
        # 5. НЕ-ЦВЕТОЧНЫЕ ДОКУМЕНТЫ: используем LLM account selection
        else:
            logger.info(f"📋 Создание line item для не-цветочного документа (category: {llm_cat})")
            line_items = self._create_fallback_line_item(analysis, expense_accounts, None, org_id)
        
        # Конвертируем даты в правильный формат для Zoho (YYYY-MM-DD)
        def convert_date_format(date_str: str) -> str:
            """Конвертирует дату из DD.MM.YYYY в YYYY-MM-DD"""
            if not date_str:
                return datetime.now().strftime('%Y-%m-%d')
            
            try:
                # Пробуем разные форматы
                for fmt in ['%d.%m.%Y', '%Y-%m-%d', '%d/%m/%Y']:
                    try:
                        dt = datetime.strptime(date_str, fmt)
                        return dt.strftime('%Y-%m-%d')
                    except ValueError:
                        continue
                # Fallback
                return datetime.now().strftime('%Y-%m-%d')
            except Exception:
                return datetime.now().strftime('%Y-%m-%d')
        
        # ТОЧНАЯ КОПИЯ ЛОГИКИ ДАТ ИЗ HANDLERS.PY (строки 2094-2112)
        import re
        
        # BILL DATE (дата продажи)
        bill_date = None
        if analysis.get('issue_date') or analysis.get('document_date') or analysis.get('date'):
            bill_date = self._normalize_date(analysis.get('issue_date') or analysis.get('document_date') or analysis.get('date'))
        else:
            txt = analysis.get('extracted_text') or ''
            m = re.search(r"(date of issue|issue date)\s*[:\-]*\s*([A-Za-z]{3,9}\s+\d{1,2},\s*\d{4}|\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{4}-\d{2}-\d{2})", txt, re.IGNORECASE)
            if m:
                bill_date = self._normalize_date(m.group(2))
        if not bill_date:
            bill_date = datetime.now().strftime('%Y-%m-%d')
        
        # DUE DATE (срок платежа)
        due_date = None
        if analysis.get('due_date'):
            due_date = self._normalize_date(analysis.get('due_date'))
        else:
            txt = analysis.get('extracted_text') or ''
            m = re.search(r"(date due|due date|payment due|termin płatności)\s*[:\-]*\s*([A-Za-z]{3,9}\s+\d{1,2},\s*\d{4}|\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{4}-\d{2}-\d{2})", txt, re.IGNORECASE)
            if m:
                due_date = self._normalize_date(m.group(2))
        
        invoice_date = bill_date
        logger.info(f"🗓️ Определение дат: bill_date='{bill_date}', due_date='{due_date}'")
        
        # Используем due_date из документа как есть (без принудительной корректировки)
        
        # Получаем bill_number из разных полей
        bill_number = (
            analysis.get('invoice_number') or 
            analysis.get('bill_number') or 
            analysis.get('document_number') or 
            f"INV-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        )
        
        logger.info(f"🔍 Определение bill_number:")
        logger.info(f"  invoice_number: {analysis.get('invoice_number')}")
        logger.info(f"  bill_number: {analysis.get('bill_number')}")
        logger.info(f"  document_number: {analysis.get('document_number')}")
        logger.info(f"  ✅ Итоговый bill_number: {bill_number}")
        
        # Основной payload  
        bill_payload = {
            "vendor_id": supplier.get('contact_id'),
            "bill_number": bill_number,
            "date": invoice_date,
            "reference_number": analysis.get('reference_number', ''),
            "notes": analysis.get('service_description', '') or f"Автоматически создан из WorkDrive файла: {analysis.get('original_filename', '')}",
            "terms": "",
            "line_items": line_items,
            "is_inclusive_tax": inclusive  # Используем вычисленное значение, а не из LLM
        }
        
        # Добавляем due_date только если он определен
        if due_date:
            bill_payload["due_date"] = due_date
            logger.info(f"🗓️ Добавлен due_date: {due_date}")
        
        # Добавляем branch_id для цветочных документов
        if is_flowers_doc and org_id == '20082562863':
            # Iris flowers atelier branch ID
            branch_id = '281497000000355063'
            bill_payload["branch_id"] = branch_id
            logger.info(f"🌸 Добавлен branch_id для цветочного документа: {branch_id}")
        
        return bill_payload
    
    def _create_fallback_line_item(self, analysis: Dict, accounts: List, preferred_account_id: str, org_id: str) -> List[Dict]:
        """Создает fallback line item для документов без детальных позиций"""
        from functions.llm_document_extractor import llm_select_account
        from functions.zoho_api import find_tax_by_percent, get_chart_of_accounts
        
        account_names = [acc.get('account_name', '') for acc in accounts]
        
        # ПРАВИЛЬНОЕ извлечение item_details ПЕРЕД использованием
        # Приоритет: реальное описание из документа
        item_description = None
        
        # 1. Ищем в line_items (детальные позиции)
        line_items_desc = analysis.get('line_items', [])
        if line_items_desc and len(line_items_desc) > 0:
            first_item = line_items_desc[0]
            item_description = first_item.get('description') or first_item.get('name')
        
        # 2. Fallback на прямые поля
        if not item_description:
            item_description = (
                analysis.get('item_details') or 
                analysis.get('service_description') or
                analysis.get('description')
            )
        
        # 3. Последний fallback
        if not item_description:
            item_description = f"Services from {analysis.get('supplier_name', 'Supplier')}"
        
        self.workdrive_logger.success("ITEM_DESCRIPTION ОПРЕДЕЛЕН", 
            description=item_description[:100],
            source="line_items" if line_items_desc else "direct_fields")
        
        # Определяем account через LLM с ПРАВИЛЬНЫМ контекстом
        context_text = f"Supplier: {analysis.get('supplier_name', '')}, Service: {item_description}, Bill: {analysis.get('bill_number', '')}"
        
        self.workdrive_logger.step(11, "LLM ВЫБОР ACCOUNT", context=context_text[:100])
        
        account_result = llm_select_account(
            account_names=account_names,
            context_text=context_text,
            supplier_name=analysis.get('supplier_name', ''),
            category=analysis.get('product_category', '')
        )
        
        # ИСПРАВЛЯЕМ выбор account - НЕ используем "Uncategorized"
        llm_account_name = account_result.get('name', '')
        
        if llm_account_name == 'Uncategorized' or not llm_account_name:
            # Используем fallback account
            account_name = account_names[0] if account_names else 'Other Expenses'
            self.workdrive_logger.warning("LLM ВЫБРАЛ UNCATEGORIZED", f"Используем fallback: {account_name}")
        else:
            account_name = llm_account_name
            self.workdrive_logger.success("LLM ACCOUNT ВЫБРАН", 
                account_name=account_name,
                confidence=account_result.get('confidence', 0))
        
        # Ищем account_id среди expense_accounts
        account_id = preferred_account_id
        if not account_id:
            # Получаем expense_accounts из основной функции
            all_accounts = get_chart_of_accounts(org_id)
            expense_accounts = [acc for acc in all_accounts if acc.get('account_type', '').lower() not in ['income', 'other_income', 'revenue']]
            account_id = next((acc['account_id'] for acc in expense_accounts if acc.get('account_name') == account_name), None)
        
        # Определяем tax
        tax_rate = analysis.get('tax_rate', 23)  # default 23%
        tax_id = find_tax_by_percent(org_id, tax_rate)
        
        # Используем net_amount или total_amount
        amount = analysis.get('net_amount', analysis.get('total_amount', 0))
        
        line_item = {
            "name": item_description[:200],  # Используем РЕАЛЬНОЕ описание из документа
            "description": f"Invoice {analysis.get('bill_number', analysis.get('invoice_number', ''))}",
            "rate": float(amount),
            "quantity": 1.0,
        }
        
        self.workdrive_logger.success("ITEM_DETAILS ИЗВЛЕЧЕН", 
            item_description=item_description[:50],
            source="item_details" if analysis.get('item_details') else "service_description")
        
        if account_id:
            line_item["account_id"] = account_id
        if tax_id:
            line_item["tax_id"] = tax_id
            
        return [line_item]
    
    def _create_llm_line_items(self, analysis: Dict, accounts: List, preferred_account_id: str, org_id: str, inclusive: bool = False) -> List[Dict]:
        """Создает line_items на основе LLM анализа (для цветочных документов)"""
        from functions.zoho_api import find_tax_by_percent
        
        # Получаем line_items из LLM анализа
        llm_line_items = analysis.get('line_items', [])
        
        if not llm_line_items:
            logger.warning("⚠️ LLM line_items пустые, используем fallback")
            return self._create_fallback_line_item(analysis, accounts, preferred_account_id, org_id)
        
        logger.info(f"🌸 Создание {len(llm_line_items)} line_items из LLM анализа")
        
        line_items = []
        tax_rate = analysis.get('tax_rate', 8)  # Для цветов часто 8%
        tax_id = find_tax_by_percent(org_id, tax_rate)
        
        for i, llm_item in enumerate(llm_line_items):
            # Используем данные из LLM
            name = llm_item.get('description') or llm_item.get('description_en', f'Item {i+1}')
            quantity = float(llm_item.get('quantity', 1))
            
            # ТОЧНАЯ КОПИЯ ЛОГИКИ ЦЕН ИЗ HANDLERS.PY (строки 2477-2488)
            # Поддержка разных форматов данных
            price_net = (llm_item.get('unit_price_net') or llm_item.get('price_net') or 
                        llm_item.get('price_netto') or llm_item.get('unit_price_netto') or llm_item.get('net_amount'))
            price_gross = (llm_item.get('unit_price_gross') or llm_item.get('price_gross') or 
                          llm_item.get('unit_price_brutto') or llm_item.get('gross_amount'))
            
            # Используем inclusive параметр переданный из create_bill_payload
            if inclusive and price_gross:
                # Документ с brutto ценами - берем gross цену как есть
                rate = float(price_gross) / quantity if quantity > 0 else float(price_gross)
                logger.info(f"🌸 Используем БРУТТО цену: {rate:.2f} (price_gross: {price_gross}, qty: {quantity})")
            elif price_net:
                rate = float(price_net) / quantity if quantity > 0 else float(price_net)
                logger.info(f"🌸 Используем НЕТТО цену: {rate:.2f} (price_net: {price_net}, qty: {quantity})")
            else:
                # PDFPlumber формат: используем 'rate' напрямую
                rate = float(llm_item.get('rate') or llm_item.get('unit_price') or 0)
                logger.info(f"🌸 Используем ПРЯМУЮ цену: {rate:.2f} (fallback)")
                
            logger.info(f"🔍 PRICE DEBUG: name={name[:30]}")
            logger.info(f"🔍 PRICE DEBUG: price_net={price_net}, price_gross={price_gross}")
            logger.info(f"🔍 PRICE DEBUG: inclusive={inclusive}, final_rate={rate:.2f}")
            
            item = {
                "name": name[:200],
                "description": name[:2000],
                "quantity": quantity,
                "rate": rate
            }
            
            # Добавляем account_id
            if preferred_account_id:  # Flowers account для цветов
                item["account_id"] = preferred_account_id
            
            # Добавляем tax_id
            if tax_id:
                item["tax_id"] = tax_id
            
            line_items.append(item)
            
            logger.info(f"🌸 Line item {i+1}: {name[:30]} (qty: {quantity}, rate: {rate:.2f})")
        
        return line_items
    
    def _normalize_date(self, raw: Optional[str]) -> str:
        """Нормализация дат (копия из handlers.py)"""
        if not raw:
            return datetime.now().strftime('%Y-%m-%d')
        raw = raw.strip()
        fmts = ["%d/%m/%Y", "%Y-%m-%d", "%d.%m.%Y", "%Y.%m.%d", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d", "%B %d, %Y", "%b %d, %Y"]
        for fmt in fmts:
            try:
                return datetime.strptime(raw, fmt).strftime('%Y-%m-%d')
            except Exception:
                continue
        cleaned = raw.replace(' ', '/').replace('.', '/').replace('-', '/')
        for fmt in ("%d/%m/%Y", "%Y/%m/%d", "%m/%d/%Y"):
            try:
                return datetime.strptime(cleaned, fmt).strftime('%Y-%m-%d')
            except Exception:
                continue
        return datetime.now().strftime('%Y-%m-%d')
    
    def determine_document_action(self, analysis: Dict) -> str:
        """Определяет что создавать: BILL или EXPENSE (используя готовую логику из handlers)"""
        
        document_type = analysis.get('document_type', '').lower()
        extracted_text = (analysis.get('extracted_text') or '').lower()
        supplier_name = (analysis.get('supplier_name') or '').lower()
        
        # PARAGON FISKALNY → EXPENSE (только по содержимому документа)
        is_paragon = (
            document_type == 'receipt' or
            'paragon' in document_type or 
            'fiskalny' in document_type or
            'paragon fiskalny' in extracted_text or
            ('paragon' in extracted_text and 'fiskalny' in extracted_text)
        )
        
        if is_paragon:
            logger.info("🧾 PARAGON FISKALNY определен → создаем EXPENSE")
            return 'EXPENSE'
        
        logger.info("📋 Обычный инвойс определен → создаем BILL")
        return 'BILL'
    
    async def create_expense_from_analysis(self, analysis: Dict, supplier: Dict, org_id: str, file_path: str) -> Dict:
        """Создает Expense из анализа парагона фискального используя ExpenseService"""
        from telegram_bot.services.expense_service import ExpenseService
        
        # Определяем org_name
        org_name = "PARKENTERTAINMENT" if org_id == '20082562863' else "TaVie Europe OÜ"
        
        logger.info(f"💳 Создание Expense через ExpenseService: org={org_name}, supplier={supplier.get('contact_id')}")
        
        # Используем ExpenseService для создания Expense
        return await ExpenseService.create_expense_from_analysis(
            analysis=analysis,
            supplier=supplier,
            org_id=org_id,
            org_name=org_name,
            file_path=file_path
        )
    
    async def _convert_image_to_pdf(self, image_path: str, original_filename: str) -> str:
        """Конвертирует изображение в PDF (готовая логика из handlers)"""
        try:
            from PIL import Image
            import os
            
            logger.info(f"🔄 Конвертация изображения в PDF: {original_filename}")
            
            # Открываем изображение
            image = Image.open(image_path)
            
            # Конвертируем в RGB если нужно
            if image.mode != 'RGB':
                image = image.convert('RGB')
                logger.info(f"🎨 Конвертирован режим изображения в RGB")
            
            # Создаем PDF путь
            pdf_path = os.path.splitext(image_path)[0] + '_converted.pdf'
            
            # Сохраняем как PDF
            image.save(pdf_path, "PDF", resolution=100.0)
            
            logger.info(f"✅ Изображение сконвертировано в PDF: {pdf_path}")
            return pdf_path
            
        except Exception as e:
            logger.error(f"❌ Ошибка конвертации изображения {original_filename}: {e}")
            raise
    
    
    async def attach_pdf_to_bill(self, org_id: str, bill_id: str, file_path: str, filename: str):
        """Прикрепляет PDF файл к созданному Bill"""
        try:
            import requests
            from functions.zoho_api import get_access_token
            
            access_token = get_access_token()
            url = f"https://www.zohoapis.eu/books/v3/bills/{bill_id}/attachment?organization_id={org_id}"
            
            headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}
            files = {"attachment": (filename, open(file_path, 'rb'), 'application/pdf')}
            
            response = requests.post(url, headers=headers, files=files)
            files["attachment"][1].close()
            
            if response.status_code in (200, 201):
                logger.info(f"📎 PDF успешно прикреплён к Bill {bill_id}")
            else:
                logger.warning(f"⚠️ Ошибка прикрепления PDF к Bill {bill_id}: {response.status_code}")
                
        except Exception as e:
            logger.error(f"❌ Ошибка прикрепления PDF: {e}")
    
    def _auto_update_contact_if_needed(self, supplier: Dict, analysis: Dict, org_id: str):
        """Автоматически обновляет контакт дополнительными данными из документа"""
        try:
            contact_id = supplier.get('contact_id')
            if not contact_id:
                return
            
            # Собираем дополнительные данные из документа
            update_data = {}
            
            # Email из документа
            doc_email = analysis.get('supplier_email') or analysis.get('email')
            if doc_email and '@' in doc_email:
                update_data['email'] = doc_email
                self.workdrive_logger.success("EMAIL ИЗ ДОКУМЕНТА", email=doc_email)
            
            # Телефон из документа  
            doc_phone = analysis.get('supplier_phone') or analysis.get('phone')
            if doc_phone and len(doc_phone) > 5:
                update_data['phone'] = doc_phone
                self.workdrive_logger.success("ТЕЛЕФОН ИЗ ДОКУМЕНТА", phone=doc_phone)
            
            # Адрес из документа
            doc_address = analysis.get('supplier_address') or analysis.get('address')
            if doc_address and len(doc_address) > 10:
                update_data['billing_address'] = {'address': doc_address}
                self.workdrive_logger.success("АДРЕС ИЗ ДОКУМЕНТА", address=doc_address[:50])
            
            # VAT из документа (если в кэше null)
            doc_vat = analysis.get('supplier_vat') or analysis.get('vat')
            if doc_vat and not supplier.get('vat_number'):
                vat_field = "cf_tax_id" if org_id == "20082562863" else "cf_vat_id"
                update_data['custom_fields'] = [{"api_name": vat_field, "value": doc_vat}]
                self.workdrive_logger.success("VAT ИЗ ДОКУМЕНТА", vat=doc_vat, field=vat_field)
            
            # Если есть данные для обновления - обновляем
            if update_data:
                self.workdrive_logger.step(12, "ОБНОВЛЕНИЕ КОНТАКТА", contact_id=contact_id, fields=list(update_data.keys()))
                
                from config.zoho_auth import get_access_token
                import requests
                
                access_token = get_access_token()
                headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}
                url = f"https://www.zohoapis.eu/books/v3/contacts/{contact_id}?organization_id={org_id}"
                
                response = requests.put(url, json=update_data, headers=headers)
                
                if response.status_code == 200:
                    self.workdrive_logger.success("КОНТАКТ ОБНОВЛЕН", contact_id=contact_id, updated_fields=list(update_data.keys()))
                else:
                    self.workdrive_logger.warning("ОБНОВЛЕНИЕ КОНТАКТА", f"Не удалось обновить: {response.status_code}")
            else:
                self.workdrive_logger.success("КОНТАКТ АКТУАЛЕН", "Дополнительных данных для обновления нет")
                
        except Exception as e:
            self.workdrive_logger.warning("АВТООБНОВЛЕНИЕ КОНТАКТА", f"Ошибка: {e}")

    async def send_telegram_report(self, date_str: str, results: List[Dict]):
        """Отправляет отчёт о обработке в Telegram"""
        try:
            successful = [r for r in results if r['success']]
            failed = [r for r in results if not r['success']]
            
            # Функция для экранирования специальных символов Markdown
            def escape_markdown(text: str) -> str:
                """Экранирует специальные символы для Telegram Markdown"""
                special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
                for char in special_chars:
                    text = text.replace(char, f'\\{char}')
                return text
            
            # Формируем сообщение (обычный текст без Markdown)
            message = f"📊 ОТЧЁТ ОБРАБОТКИ WORKDRIVE за {date_str}\n\n"
            
            if successful:
                message += f"✅ УСПЕШНО ОБРАБОТАНО: {len(successful)}\n"
                for result in successful:
                    bill_id = result['bill_id']
                    bill_number = result['bill_number']
                    supplier = result['supplier_name']
                    org_id = result['org_id']
                    
                    # Создаём ссылку на Bill в Zoho (обычный текст)
                    zoho_url = f"https://books.zoho.eu/app/{org_id}#/bills/{bill_id}"
                    
                    message += f"• {bill_number} - {supplier}\n"
                    message += f"  Ссылка: {zoho_url}\n"
                
                message += "\n"
            
            if failed:
                message += f"❌ ОШИБКИ: {len(failed)}\n"
                for result in failed:
                    file_name = result['file_name']
                    error = result['error'][:100] + "..." if len(result['error']) > 100 else result['error']
                    message += f"• {file_name}\n"
                    message += f"  Ошибка: {error}\n"
                
                message += "\n"
            
            if not successful and not failed:
                message += "ℹ️ Новых файлов для обработки не найдено\n"
            
            message += f"🕐 Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            
            # Отправляем в Telegram БЕЗ Markdown
            await send_message_to_admin(message)
            logger.info("📱 Telegram отчёт отправлен")
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки Telegram отчёта: {e}")
            # Fallback: отправляем простое сообщение
            try:
                fallback_message = f"❌ Ошибка отчёта WorkDrive за {date_str}. Обработано {len([r for r in results if r['success']])}/{len(results)} файлов."
                await send_message_to_admin(fallback_message)
            except Exception:
                pass
    
    async def process_date(self, target_date: str) -> List[Dict]:
        """Обрабатывает все файлы за указанную дату"""
        logger.info(f"🚀 Начало пакетной обработки за {target_date}")
        
        # Получаем файлы для обработки
        files = self.get_files_for_date(target_date)
        
        if not files:
            logger.info(f"📭 Новых файлов за {target_date} не найдено")
            return []
        
        # Обрабатываем каждый файл
        results = []
        for i, file in enumerate(files, 1):
            logger.info(f"📄 Обработка {i}/{len(files)}: {file.get('name')}")
            
            result = await self.process_single_file(file)
            results.append(result)
            
            # Отмечаем как обработанный независимо от результата
            self.mark_file_processed(
                file_id=result['file_id'],
                file_name=result['file_name'],
                bill_id=result.get('bill_id'),
                error=result.get('error')
            )
        
        logger.info(f"✅ Пакетная обработка завершена: {len([r for r in results if r['success']])}/{len(results)} успешно")
        return results

async def run_daily_batch(target_date: str = None):
    """Запускает ежедневную пакетную обработку"""
    if not target_date:
        # По умолчанию обрабатываем вчерашний день
        yesterday = date.today() - timedelta(days=1)
        target_date = yesterday.strftime('%Y-%m-%d')
    
    processor = WorkDriveBatchProcessor()
    
    try:
        # Обрабатываем файлы
        results = await processor.process_date(target_date)
        
        # Отправляем отчёт в Telegram
        await processor.send_telegram_report(target_date, results)
        
        return results
        
    except Exception as e:
        logger.error(f"❌ Ошибка ежедневной обработки: {e}")
        # Отправляем сообщение об ошибке в Telegram
        try:
            await send_message_to_admin(f"❌ Ошибка WorkDrive обработки за {target_date}: {str(e)}")
        except Exception:
            pass
        raise

if __name__ == "__main__":
    import argparse
    
    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Парсинг аргументов
    parser = argparse.ArgumentParser(description='WorkDrive Batch Processor')
    parser.add_argument('--date', type=str, help='Дата для обработки в формате YYYY-MM-DD (по умолчанию вчера)')
    parser.add_argument('--test', action='store_true', help='Тестовый режим (обработка файлов за 19 августа)')
    
    args = parser.parse_args()
    
    if args.test:
        target_date = "2025-08-19"
        print(f"🧪 ТЕСТОВЫЙ РЕЖИМ: обработка файлов за {target_date}")
    else:
        target_date = args.date
    
    # Запуск
    asyncio.run(run_daily_batch(target_date))
