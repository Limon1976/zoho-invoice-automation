"""
Universal Document Processor
===========================

Единый сервис обработки документов для Telegram Bot и WorkDrive Batch Processor.
Исключает дублирование кода и обеспечивает единообразную логику.
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime

# Импорты
from functions.zoho_api import find_supplier_in_zoho, create_bill, get_chart_of_accounts, find_tax_by_percent
from functions.llm_document_extractor import llm_select_account
from config.zoho_auth import get_access_token
import requests

logger = logging.getLogger(__name__)

class UniversalDocumentProcessor:
    """Универсальный процессор документов"""
    
    def __init__(self):
        self.logger = logging.getLogger('universal_processor')
    
    def normalize_company_name(self, company_name: str) -> str:
        """Сокращает юридические названия компаний"""
        if not company_name:
            return ""
        
        name = company_name.strip()
        
        # Польские сокращения
        name = name.replace("SPÓŁKA Z OGRANICZONĄ ODPOWIEDZIALNOŚCIĄ SPÓŁKA KOMANDYTOWA", "Sp. z o.o. S.K.")
        name = name.replace("SPÓŁKA Z OGRANICZONĄ ODPOWIEDZIALNOŚCIĄ", "Sp. z o.o.")
        name = name.replace("SPÓŁKA AKCYJNA", "S.A.")
        
        # Немецкие
        name = name.replace("GESELLSCHAFT MIT BESCHRÄNKTER HAFTUNG", "GmbH")
        name = name.replace("AKTIENGESELLSCHAFT", "AG")
        
        # Английские
        name = name.replace("LIMITED LIABILITY COMPANY", "LLC")
        name = name.replace("LIMITED COMPANY", "Ltd")
        name = name.replace("CORPORATION", "Corp")
        name = name.replace("INCORPORATED", "Inc")
        
        # Убираем лишние пробелы
        name = " ".join(name.split())
        
        logger.info(f"📝 Название сокращено: {company_name[:30]}... → {name}")
        return name
    
    def extract_item_details(self, analysis: Dict) -> str:
        """Универсальное извлечение item_details из анализа документа"""
        
        # 1. Приоритет: line_items (детальные позиции)
        line_items = analysis.get('line_items', [])
        if line_items and len(line_items) > 0:
            first_item = line_items[0]
            description = first_item.get('description') or first_item.get('name')
            if description and len(description.strip()) > 3:
                logger.info(f"✅ Item details из line_items: {description[:50]}...")
                return description
        
        # 2. Прямые поля описания
        for field in ['item_details', 'service_description', 'description']:
            value = analysis.get(field)
            if value and len(str(value).strip()) > 3:
                logger.info(f"✅ Item details из {field}: {str(value)[:50]}...")
                return str(value)
        
        # 3. Fallback
        fallback = f"Services from {analysis.get('supplier_name', 'Supplier')}"
        logger.warning(f"⚠️ Item details fallback: {fallback}")
        return fallback
    
    async def find_or_create_supplier(self, analysis: Dict, org_id: str) -> Optional[Dict]:
        """Универсальный поиск или создание поставщика"""
        
        supplier_name = analysis.get('supplier_name', '')
        supplier_vat = analysis.get('vat', '') or analysis.get('supplier_vat', '')
        
        logger.info(f"🔍 ПОИСК ПОСТАВЩИКА: {supplier_name} (VAT: {supplier_vat})")
        
        # 1. Ищем существующего
        supplier = find_supplier_in_zoho(org_id, supplier_name, supplier_vat)
        
        if supplier:
            logger.info(f"✅ Поставщик найден: {supplier.get('contact_id')}")
            
            # Автообновление контакта дополнительными данными
            await self._auto_update_contact(supplier, analysis, org_id)
            return supplier
        
        # 2. Создаем нового
        logger.info(f"🆕 Создаем нового поставщика: {supplier_name}")
        return await self._create_new_contact(supplier_name, supplier_vat, analysis, org_id)
    
    async def _auto_update_contact(self, supplier: Dict, analysis: Dict, org_id: str):
        """Автообновление контакта дополнительными данными"""
        
        contact_id = supplier.get('contact_id')
        if not contact_id:
            return
        
        update_data = {}
        
        # Email
        doc_email = analysis.get('supplier_email') or analysis.get('email')
        if doc_email and '@' in doc_email:
            update_data['email'] = doc_email
            logger.info(f"📧 Добавляем email: {doc_email}")
        
        # Телефон  
        doc_phone = analysis.get('supplier_phone') or analysis.get('phone')
        if doc_phone and len(doc_phone) > 5:
            update_data['phone'] = doc_phone
            logger.info(f"📞 Добавляем телефон: {doc_phone}")
        
        # Адрес
        doc_address = analysis.get('supplier_address') or analysis.get('address')
        if doc_address and len(doc_address) > 10:
            update_data['billing_address'] = {'address': doc_address}
            logger.info(f"📍 Добавляем адрес: {doc_address[:50]}...")
        
        # VAT (если в кэше null)
        doc_vat = analysis.get('supplier_vat') or analysis.get('vat')
        if doc_vat and not supplier.get('vat_number'):
            vat_field = "cf_tax_id" if org_id == "20082562863" else "cf_vat_id"
            update_data['custom_fields'] = [{"api_name": vat_field, "value": doc_vat}]
            logger.info(f"🏷️ Добавляем VAT: {doc_vat}")
        
        # Обновляем если есть данные
        if update_data:
            await self._update_contact_in_zoho(contact_id, update_data, org_id)
    
    async def _create_new_contact(self, supplier_name: str, supplier_vat: str, analysis: Dict, org_id: str) -> Optional[Dict]:
        """Создание нового контакта в Zoho"""
        
        # Сокращаем название для Display Name и Company Name
        normalized_name = self.normalize_company_name(supplier_name)
        
        contact_payload = {
            "contact_name": normalized_name,    # Display Name - сокращенное
            "company_name": normalized_name,    # Company Name - сокращенное  
            "contact_type": "vendor",
            "custom_fields": []
        }
        
        # Банковские реквизиты в Remarks
        bank_details = []
        if analysis.get('bank_name'):
            bank_details.append(f"Bank: {analysis.get('bank_name')}")
        if analysis.get('iban'):
            bank_details.append(f"IBAN: {analysis.get('iban')}")
        elif analysis.get('bank_account'):
            bank_details.append(f"Account: {analysis.get('bank_account')}")
        if analysis.get('swift_bic'):
            bank_details.append(f"SWIFT: {analysis.get('swift_bic')}")
        
        if bank_details:
            contact_payload['remarks'] = "\n".join(bank_details)
            logger.info(f"🏦 Банковские реквизиты: {len(bank_details)} полей")
        
        # Добавляем VAT
        if supplier_vat:
            vat_field = "cf_tax_id" if org_id == "20082562863" else "cf_vat_id"
            contact_payload["custom_fields"].append({
                "api_name": vat_field,
                "value": supplier_vat
            })
        
        # Добавляем email
        doc_email = analysis.get('supplier_email') or analysis.get('email')
        if doc_email:
            contact_payload['email'] = doc_email
        
        # Добавляем адрес - ПРАВИЛЬНОЕ разделение на поля как в contact_creator.py
        doc_address = analysis.get('supplier_address') or analysis.get('address')
        if doc_address:
            # Извлекаем структурированный адрес из LLM анализа
            street_llm = analysis.get("supplier_street") or ""
            city_llm = analysis.get("supplier_city") or ""
            zip_llm = analysis.get("supplier_zip_code") or analysis.get("zip_code") or ""
            country_llm = analysis.get("supplier_country") or "Poland"
            
            if street_llm or city_llm or zip_llm:
                # Используем структурированный адрес из LLM
                billing_address = {
                    "address": street_llm or doc_address,
                    "city": city_llm,
                    "zip": zip_llm,
                    "country": country_llm
                }
                logger.info(f"✅ LLM-адрес: улица='{billing_address['address']}', город='{billing_address['city']}', индекс='{billing_address['zip']}', страна='{billing_address['country']}'")
            else:
                # Пытаемся разобрать строковый адрес
                address_parts = [p.strip() for p in doc_address.split(',')]
                if len(address_parts) >= 3:
                    billing_address = {
                        "address": address_parts[0],
                        "city": address_parts[1], 
                        "zip": zip_llm or "",
                        "country": country_llm
                    }
                    logger.info(f"✅ Разобран адрес: улица='{billing_address['address']}', город='{billing_address['city']}', страна='{billing_address['country']}'")
                else:
                    # Fallback - только адрес и страна
                    billing_address = {
                        "address": doc_address,
                        "country": country_llm
                    }
                    logger.info(f"✅ Простой адрес: '{billing_address['address']}', страна='{billing_address['country']}'")
            
            contact_payload['billing_address'] = billing_address
            contact_payload['shipping_address'] = billing_address.copy()  # Копируем billing в shipping
        
        # Primary Contact Person из документа
        contact_person = analysis.get('contact_person') or analysis.get('issuer_contact_person')
        if contact_person and contact_person.strip():
            # Исключаем пользователя Pavel Kaliadka
            if 'pavel kaliadka' not in contact_person.lower():
                contact_persons = [{
                    "first_name": contact_person.split()[0] if contact_person.split() else "",
                    "last_name": " ".join(contact_person.split()[1:]) if len(contact_person.split()) > 1 else "",
                    "is_primary_contact": True
                }]
                
                # Добавляем email к контактному лицу если есть
                if analysis.get('supplier_email'):
                    contact_persons[0]['email'] = analysis.get('supplier_email')
                
                contact_payload['contact_persons'] = contact_persons
                logger.info(f"👤 Primary Contact: {contact_person}")
        
        # Создаем через API
        try:
            access_token = get_access_token()
            headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}
            url = f"https://www.zohoapis.eu/books/v3/contacts?organization_id={org_id}"
            
            response = requests.post(url, json=contact_payload, headers=headers)
            
            if response.status_code == 201:
                created_contact = response.json().get('contact', {})
                contact_id = created_contact.get('contact_id')
                
                result = {
                    'contact_id': contact_id,
                    'contact_name': supplier_name,
                    'vat_number': supplier_vat
                }
                
                logger.info(f"✅ Новый контакт создан: {supplier_name} (ID: {contact_id})")
                return result
            else:
                error_data = response.json() if response.content else {'error': 'Unknown error'}
                logger.error(f"❌ Ошибка создания контакта: {error_data}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Исключение при создании контакта: {e}")
            return None
    
    async def _update_contact_in_zoho(self, contact_id: str, update_data: Dict, org_id: str):
        """Обновление контакта в Zoho"""
        
        try:
            access_token = get_access_token()
            headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}
            url = f"https://www.zohoapis.eu/books/v3/contacts/{contact_id}?organization_id={org_id}"
            
            response = requests.put(url, json=update_data, headers=headers)
            
            if response.status_code == 200:
                logger.info(f"✅ Контакт {contact_id} обновлен: {list(update_data.keys())}")
            else:
                logger.warning(f"⚠️ Не удалось обновить контакт {contact_id}: {response.status_code}")
                
        except Exception as e:
            logger.warning(f"⚠️ Ошибка обновления контакта: {e}")
    
    async def _attach_file_to_bill(self, org_id: str, bill_id: str, file_path: str):
        """Прикрепление файла к Bill (КАК В TELEGRAM BOT)"""
        
        try:
            import os
            
            if not os.path.exists(file_path):
                logger.warning(f"⚠️ Файл не найден для прикрепления: {file_path}")
                return
            
            access_token = get_access_token()
            headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}
            
            url = f"https://www.zohoapis.eu/books/v3/bills/{bill_id}/attachment?organization_id={org_id}"
            
            filename = os.path.basename(file_path)
            
            with open(file_path, 'rb') as f:
                files = {'attachment': (filename, f, 'application/pdf')}
                
                response = requests.post(url, files=files, headers=headers)
                
                if response.status_code == 201:
                    logger.info(f"✅ Файл прикреплен к Bill {bill_id}: {filename}")
                else:
                    logger.warning(f"⚠️ Не удалось прикрепить файл: {response.status_code}")
                    
        except Exception as e:
            logger.error(f"❌ Ошибка прикрепления файла: {e}")
    
    def select_account(self, analysis: Dict, accounts: List[Dict], item_description: str) -> Tuple[str, str]:
        """Универсальный выбор account через LLM с цветочной логикой"""
        
        account_names = [acc.get('account_name', '') for acc in accounts]
        
        # ПРИОРИТЕТ: IRIS Цветочные категории → точное соответствие
        description_lower = item_description.lower()
        supplier_lower = analysis.get('supplier_name', '').lower()
        
        logger.info(f"🌸 Проверка IRIS цветочных категорий в: '{item_description[:50]}...'")
        
        # IRIS ЦВЕТОЧНЫЕ КАТЕГОРИИ (точное соответствие)
        iris_categories = {
            'Paper, ribons': ['papier', 'paper', 'bibuła', 'ribon', 'ribbon', 'wstążka', 'taśma'],
            'Balloons': ['balon', 'balloon', 'balony'],
            'Boxes': ['pudełko', 'box', 'boxes', 'opakowanie'],
            'Flowers': ['kwiat', 'flower', 'róża', 'rose', 'tulip', 'irys', 'iris'],
            'Vases': ['wazon', 'vase', 'doniczka', 'pojemnik']
        }
        
        # Проверяем каждую категорию
        matched_category = None
        found_keywords = []
        
        for category, keywords in iris_categories.items():
            for keyword in keywords:
                if keyword in description_lower or keyword in supplier_lower:
                    matched_category = category
                    found_keywords.append(keyword)
                    break
            if matched_category:
                break
        
        if matched_category:
            # Ищем точный IRIS account
            for acc in accounts:
                account_name = acc.get('account_name', '').strip()
                if account_name == matched_category:
                    logger.info(f"✅ IRIS ЦВЕТОЧНЫЙ ACCOUNT найден: {account_name} (ключевые слова: {found_keywords})")
                    return account_name, acc.get('account_id')
            
            logger.warning(f"⚠️ IRIS категория найдена ({matched_category}), но account отсутствует")
        
        # Обычный LLM выбор
        context_text = f"Supplier: {analysis.get('supplier_name', '')}, Service: {item_description}, Bill: {analysis.get('bill_number', '')}, Category: {analysis.get('product_category', '')}"
        
        logger.info(f"🔍 LLM контекст: {context_text[:100]}...")
        
        account_result = llm_select_account(
            account_names=account_names,
            context_text=context_text,
            supplier_name=analysis.get('supplier_name', ''),
            category=analysis.get('product_category', '')
        )
        
        # Фильтруем неправильные результаты
        llm_account_name = account_result.get('name', '')
        
        if llm_account_name == 'Uncategorized' or not llm_account_name:
            account_name = account_names[0] if account_names else 'Other Expenses'
            logger.warning(f"⚠️ LLM выбрал Uncategorized, используем fallback: {account_name}")
        else:
            account_name = llm_account_name
            logger.info(f"✅ LLM выбрал account: {account_name} (confidence: {account_result.get('confidence', 0)})")
        
        # Ищем account_id
        account_id = None
        for acc in accounts:
            if acc.get('account_name', '').strip().lower() == account_name.lower():
                account_id = acc.get('account_id')
                break
        
        if not account_id:
            logger.warning(f"⚠️ Account_id не найден для: {account_name}")
        
        return account_name, account_id
    
    def create_line_items(self, analysis: Dict, accounts: List[Dict], org_id: str) -> List[Dict]:
        """Универсальное создание line_items с поддержкой множественных позиций"""
        
        # ПРИОРИТЕТ 1: Используем line_items из LLM анализа если есть
        llm_line_items = analysis.get('line_items', [])
        
        if llm_line_items and isinstance(llm_line_items, list) and len(llm_line_items) > 0:
            logger.info(f"📋 Используем {len(llm_line_items)} line_items из LLM анализа")
            
            created_items = []
            expense_accounts = [acc for acc in accounts if acc.get('account_type') == 'expense']
            default_account_id = expense_accounts[0].get('account_id') if expense_accounts else None
            
            for i, item in enumerate(llm_line_items, 1):
                # Извлекаем данные из LLM line_item
                name = item.get('description') or item.get('name') or f"Item {i}"
                net_amount = item.get('net_amount') or item.get('rate', 0)
                vat_rate = item.get('vat_rate') or item.get('tax_percentage', 23)
                quantity = item.get('quantity', 1.0)
                
                # ИСПРАВЛЕНИЕ: Для Rozliczenie dodatkowe - VAT = 0%
                if 'rozlicz' in name.lower() or 'dodatkow' in name.lower():
                    vat_rate = 0
                    logger.info(f"🔧 Rozliczenie dodatkowe → VAT = 0%")
                
                # Получаем tax_id для VAT ставки
                tax_id = find_tax_by_percent(org_id, vat_rate)
                
                # Создаем Zoho line_item
                zoho_item = {
                    "name": str(name)[:200],
                    "description": f"Invoice {analysis.get('bill_number', analysis.get('invoice_number', ''))}",
                    "rate": float(net_amount),
                    "quantity": float(quantity),
                    "account_id": default_account_id
                }
                
                if tax_id:
                    zoho_item["tax_id"] = tax_id
                
                created_items.append(zoho_item)
                
                logger.info(f"✅ Line item {i}: {name[:30]}... | {net_amount} PLN | VAT {vat_rate}%")
            
            logger.info(f"✅ Создано {len(created_items)} line items из LLM анализа")
            return created_items
        
        # FALLBACK: Старая логика для одной позиции
        logger.info("📋 Fallback: создаем единственный line_item (LLM не предоставил массив)")
        
        # Извлекаем описание товара/услуги
        item_description = self.extract_item_details(analysis)
        
        # Выбираем account
        account_name, account_id = self.select_account(analysis, accounts, item_description)
        
        # Определяем налог
        tax_rate = analysis.get('tax_rate', 23)  # По умолчанию 23% для Польши
        tax_id = find_tax_by_percent(org_id, tax_rate)
        
        # Сумма
        amount = analysis.get('net_amount') or analysis.get('total_amount', 0)
        
        # Создаем line_item
        line_item = {
            "name": item_description[:200],
            "description": f"Invoice {analysis.get('bill_number', analysis.get('invoice_number', ''))}",
            "rate": float(amount),
            "quantity": 1.0,
        }
        
        if account_id:
            line_item["account_id"] = account_id
        if tax_id:
            line_item["tax_id"] = tax_id
        
        logger.info(f"✅ Fallback line item: {item_description[:50]}... (account: {account_name})")
        
        return [line_item]
    
    def determine_document_type(self, analysis: Dict) -> str:
        """
        Определяет тип документа для правильной обработки
        Returns: 'expense' для парагонов фискальных, 'bill' для фактур
        """
        extracted_text = analysis.get('extracted_text', '').lower()
        document_type = analysis.get('document_type', '').lower()
        
        # Логика определения PARAGON FISKALNY (как в Telegram handlers)
        is_paragon = (
            'paragon' in document_type or 
            'fiskalny' in document_type or
            'paragon fiskalny' in extracted_text or
            ('paragon' in extracted_text and 'fiskalny' in extracted_text) or
            'receipt' in document_type
        )
        
        if is_paragon:
            logger.info("🧾 PARAGON FISKALNY определен → создаем EXPENSE")
            return 'expense'
        else:
            logger.info("📄 ФАКТУРА определена → создаем BILL")
            return 'bill'

    async def process_document_universal(self, analysis: Dict, org_id: str, file_path: str = None) -> Dict:
        """
        Универсальная обработка документа
        
        Args:
            analysis: Результат LLM анализа документа
            org_id: ID организации Zoho
            
        Returns:
            Результат обработки (success, bill_id, error, etc.)
        """
        
        result = {
            'success': False,
            'bill_id': None,
            'error': None,
            'supplier_info': None
        }
        
        try:
            # 1. Находим или создаем поставщика
            supplier = await self.find_or_create_supplier(analysis, org_id)
            if not supplier:
                result['error'] = "Не удалось найти или создать поставщика"
                return result
            
            # 2. ЦВЕТОЧНАЯ ЛОГИКА: Определяем филиал для Bills
            branch_info = self._determine_flower_branch_if_needed(analysis, org_id)
            
            result['supplier_info'] = supplier
            
            # 2. Получаем accounts для выбора
            accounts = get_chart_of_accounts(org_id)
            expense_accounts = [
                acc for acc in accounts 
                if acc.get('account_type', '').lower() in ['expense', 'cost_of_goods_sold', 'other_expense']
            ]
            
            # 3. Создаем line_items
            line_items = self.create_line_items(analysis, expense_accounts, org_id)
            
            # 4. Правильная дата документа и due_date (КАК В TELEGRAM BOT)
            bill_date = None
            for date_field in ['issue_date', 'document_date', 'date', 'invoice_date']:
                if analysis.get(date_field):
                    bill_date = analysis.get(date_field)
                    break
            
            if not bill_date:
                # Fallback: ищем дату в тексте
                extracted_text = analysis.get('extracted_text', '')
                import re
                date_match = re.search(r'(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})', extracted_text)
                if date_match:
                    bill_date = date_match.group(1)
                else:
                    bill_date = datetime.now().strftime('%Y-%m-%d')
            
            # Правильная due_date
            due_date = analysis.get('due_date') or analysis.get('payment_due_date')
            
            logger.info(f"📅 Дата документа: {bill_date}")
            if due_date:
                logger.info(f"📅 Due Date: {due_date}")
            
            # 5. Определяем тип документа (парагон → Expense, фактура → Bill)
            doc_type = self.determine_document_type(analysis)
            
            if doc_type == 'expense':
                # ПАРАГОН ФИСКАЛЬНЫЙ → EXPENSE
                logger.info("🧾 Создание Expense для парагона...")
                
                try:
                    # Используем СУЩЕСТВУЮЩИЙ ExpenseService из telegram_bot
                    from telegram_bot.services.expense_service import ExpenseService
                    
                    # Определяем org_name как в WorkDriveBatchProcessor
                    org_name = "PARKENTERTAINMENT" if org_id == '20082562863' else "TaVie Europe OÜ"
                    
                    expense_result = await ExpenseService.create_expense_from_analysis(
                        analysis=analysis, 
                        supplier=supplier, 
                        org_id=org_id,
                        org_name=org_name,
                        file_path=file_path
                    )
                    
                    if expense_result.get('success'):
                        result['success'] = True
                        result['expense_id'] = expense_result.get('expense_id')
                        result['document_type'] = 'expense'
                        logger.info(f"✅ Expense создан: {result['expense_id']}")
                        return result
                    else:
                        error_msg = expense_result.get('error', 'Unknown error')
                        result['error'] = f'Ошибка создания Expense: {error_msg}'
                        return result
                        
                except Exception as e:
                    logger.error(f"❌ Ошибка создания Expense: {e}")
                    result['error'] = f'Ошибка Expense: {str(e)}'
                    return result
            
            # ФАКТУРА → BILL
            logger.info("💰 Создание Bill для фактуры...")
            bill_payload = {
                "vendor_id": supplier.get('contact_id'),
                "bill_number": analysis.get('bill_number') or analysis.get('invoice_number', ''),
                "date": bill_date,
                "line_items": line_items,
                "is_inclusive_tax": analysis.get('is_inclusive_tax', False),
                "notes": f"Создан автоматически из WorkDrive: {analysis.get('original_filename', '')}"
            }
            
            # Добавляем due_date если есть
            if due_date:
                bill_payload['due_date'] = due_date
            
            # Добавляем branch_id для цветочных Bills
            if branch_info and branch_info.get('branch_id'):
                bill_payload['branch_id'] = branch_info['branch_id']
                self.logger.info(f"🌸 Добавлен филиал в Bill: {branch_info['name']} (ID: {branch_info['branch_id']})")
            
            logger.info(f"📤 Отправка Bill в Zoho: {bill_payload['bill_number']}")
            bill_response = create_bill(org_id, bill_payload)
            
            if 'error' in bill_response:
                logger.error(f"❌ Ошибка создания Bill: {bill_response['error']}")
                result['error'] = f"Ошибка создания Bill: {bill_response['error']}"
                return result
            
            # Успех
            bill = bill_response.get('bill', {})
            result['success'] = True
            result['bill_id'] = bill.get('bill_id')
            result['bill_number'] = bill.get('bill_number')
            
            logger.info(f"✅ Bill создан универсально: {result['bill_id']}")
            
            # 6. ПРИКРЕПЛЯЕМ ФАЙЛ (как в Telegram Bot)
            if file_path and result['bill_id']:
                logger.info(f"📎 Прикрепляем файл к Bill: {file_path}")
                await self._attach_file_to_bill(org_id, result['bill_id'], file_path)
            
            result['document_type'] = 'bill'
            
            return result
            
        except Exception as e:
            result['error'] = f"Исключение при обработке: {str(e)}"
            logger.error(f"❌ Ошибка универсальной обработки: {e}")
            return result
    
    def _determine_flower_branch_if_needed(self, analysis: Dict, org_id: str) -> Optional[Dict]:
        """Определяет цветочный филиал для FLORIMA и других цветочных поставщиков"""
        
        # Проверяем только для PARKENTERTAINMENT
        if org_id != '20082562863':
            return None
        
        supplier_name = analysis.get('supplier_name', '').lower()
        extracted_text = analysis.get('extracted_text', '').lower()
        
        # FLORIMA и другие цветочные поставщики → Iris flowers atelier
        flower_suppliers = ['florima', 'hibispol']
        is_flower_supplier = any(supplier in supplier_name for supplier in flower_suppliers)
        
        # Цветочные материалы в описании
        flower_materials = ['paper', 'papier', 'bibuła', 'flowers', 'kwiat', 'balloons', 'boxes', 'vases']
        has_flower_materials = any(material in extracted_text for material in flower_materials)
        
        if is_flower_supplier or has_flower_materials:
            # Iris flowers atelier
            iris_branch = {
                'name': 'Iris flowers atelier',
                'branch_id': '281497000000355063',
                'org_id': org_id
            }
            
            self.logger.info(f"🌸 ЦВЕТОЧНЫЙ ФИЛИАЛ: {supplier_name} → Iris flowers atelier")
            return iris_branch
        
        return None

# Глобальный экземпляр для использования
_universal_processor = None

def get_universal_processor() -> UniversalDocumentProcessor:
    """Получение глобального экземпляра процессора"""
    global _universal_processor
    if _universal_processor is None:
        _universal_processor = UniversalDocumentProcessor()
    return _universal_processor

# Удобные функции для прямого использования
async def process_document_universal(analysis: Dict, org_id: str) -> Dict:
    """Универсальная обработка документа"""
    processor = get_universal_processor()
    return await processor.process_document_universal(analysis, org_id)

def extract_item_details_universal(analysis: Dict) -> str:
    """Универсальное извлечение item_details"""
    processor = get_universal_processor()
    return processor.extract_item_details(analysis)

async def find_or_create_supplier_universal(analysis: Dict, org_id: str) -> Optional[Dict]:
    """Универсальный поиск/создание поставщика"""
    processor = get_universal_processor()
    return await processor.find_or_create_supplier(analysis, org_id)
