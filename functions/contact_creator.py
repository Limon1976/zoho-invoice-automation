"""
Contact Creator for Telegram Bot
===============================

Модуль для автоматического создания новых контактов поставщиков
при обработке проформ и контрактов в Telegram боте.
"""

import sys
import os
from pathlib import Path
from typing import Dict, Optional, Any, Tuple
import logging
import asyncio

# Добавляем src в Python path
sys.path.append(str(Path(__file__).parent.parent / "src"))

from src.domain.services.contact_cache import OptimizedContactCache
from src.infrastructure.zoho_api import ZohoAPIClient
from src.infrastructure.config import get_config
from functions.agent_invoice_parser import is_our_company
from functions.phone_parser import parse_phone_number, format_phone_for_zoho

logger = logging.getLogger(__name__)

class SupplierContactCreator:
    """Создатель контактов поставщиков из документов"""
    
    def __init__(self):
        """Инициализация с конфигурацией и кэшем"""
        self.config = get_config()
        
        # Инициализируем Zoho API клиент
        if not self.config.zoho.refresh_token:
            raise ValueError("ZOHO_REFRESH_TOKEN не установлен в конфигурации")
        
        self.zoho_api = ZohoAPIClient(
            client_id=self.config.zoho.client_id,
            client_secret=self.config.zoho.client_secret,
            refresh_token=self.config.zoho.refresh_token
        )
        
        # Инициализируем кэш контактов
        cache_file = Path("data/optimized_cache/all_contacts_optimized.json")
        self.contact_cache = OptimizedContactCache(str(cache_file)) if cache_file.exists() else None
        
        # ID организаций Zoho
        self.organizations = {
            "20092948714": "TaVie Europe OÜ",    # Estonia
            "20082562863": "PARKENTERTAINMENT"   # Poland
        }
    
    async def check_and_create_supplier_contact(self, document_data: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Проверяет есть ли поставщик в базе, если нет - создает новый контакт
        
        Args:
            document_data: Данные из анализа проформы/контракта
            
        Returns:
            Tuple[success, message]: Результат операции и сообщение
        """
        try:
            # Извлекаем данные поставщика
            supplier_data = self._extract_supplier_data(document_data)
            if not supplier_data:
                return False, "❌ Не удалось извлечь данные поставщика из документа"
            
            # Проверяем, не наша ли это компания
            if self._is_our_company(supplier_data):
                return True, f"ℹ️ Пропущено: {supplier_data['name']} - это наша компания"
            
            # Проверяем существование в кэше
            existing_contact = await self._find_existing_contact(supplier_data)
            if existing_contact:
                return True, f"✅ Контакт уже существует: {existing_contact.company_name} (VAT: {existing_contact.vat_number})"
            
            # Создаем новый контакт
            success, contact_id, created_contact_data = await self._create_new_contact(supplier_data)
            if success:
                # Обновляем кэш если он есть
                if self.contact_cache and created_contact_data:
                    logger.info(f"🔄 Обновляем кэш после создания контакта: {supplier_data['name']}")
                    
                    # Определяем организацию для обновления кэша
                    org_id = self._determine_organization(supplier_data["country"])
                    org_name = "PARKENTERTAINMENT" if supplier_data["country"] == "Poland" else "TaVie Europe OÜ"
                    
                    await self._refresh_cache(org_id, org_name, new_contact_data=created_contact_data)
                    logger.info(f"✅ Кэш обновлен для {org_name}, теперь можно искать: {supplier_data['name']}")
                else:
                    logger.warning("⚠️ Кэш не инициализирован или данные контакта не получены, пропускаем обновление")
                
                return True, f"🎉 Создан новый поставщик: {supplier_data['name']} (ID: {contact_id})"
            else:
                return False, f"❌ Ошибка создания контакта для {supplier_data['name']}"
                
        except Exception as e:
            logger.error(f"Ошибка в check_and_create_supplier_contact: {e}")
            return False, f"❌ Ошибка обработки поставщика: {str(e)}"
    
    def _normalize_company_name(self, company_name: str) -> str:
        """Нормализует название компании, сокращая формы собственности"""
        if not company_name:
            return ""
        
        # Безопасное извлечение строки из разных типов данных
        if isinstance(company_name, dict):
            name = company_name.get('name', '') or company_name.get('company_name', '') or str(company_name)
        elif isinstance(company_name, str):
            name = company_name.strip()
        else:
            name = str(company_name).strip() if company_name else ""
        
        # Словарь сокращений форм собственности
        legal_forms = {
            # Польские
            "SPÓŁKA Z OGRANICZONĄ ODPOWIEDZIALNOŚCIĄ": "Sp. z o.o.",
            "Spółka z ograniczoną odpowiedzialnością": "Sp. z o.o.",
            "spółka z ograniczoną odpowiedzialnością": "Sp. z o.o.",
            "SPOLKA Z OGRANICZONA ODPOWIEDZIALNOSCIA": "Sp. z o.o.",
            "Spolka z ograniczona odpowiedzialnoscia": "Sp. z o.o.",
            "SPÓŁKA AKCYJNA": "S.A.",
            "Spółka Akcyjna": "S.A.",
            "spółka akcyjna": "S.A.",
            
            # Немецкие
            "GESELLSCHAFT MIT BESCHRÄNKTER HAFTUNG": "GmbH",
            "Gesellschaft mit beschränkter Haftung": "GmbH",
            "gesellschaft mit beschränkter haftung": "GmbH",
            "AKTIENGESELLSCHAFT": "AG",
            "Aktiengesellschaft": "AG",
            "aktiengesellschaft": "AG",
            
            # Английские
            "LIMITED LIABILITY COMPANY": "LLC",
            "Limited Liability Company": "LLC", 
            "limited liability company": "LLC",
            "LIMITED COMPANY": "Ltd",
            "Limited Company": "Ltd",
            "limited company": "Ltd",
            "CORPORATION": "Corp",
            "Corporation": "Corp",
            "corporation": "Corp",
            "INCORPORATED": "Inc",
            "Incorporated": "Inc",
            "incorporated": "Inc",
            
            # Французские
            "SOCIÉTÉ À RESPONSABILITÉ LIMITÉE": "SARL",
            "Société à responsabilité limitée": "SARL",
            "société à responsabilité limitée": "SARL",
            "SOCIÉTÉ ANONYME": "SA",
            "Société Anonyme": "SA",
            "société anonyme": "SA",
            
            # Испанские
            "SOCIEDAD DE RESPONSABILIDAD LIMITADA": "SRL",
            "Sociedad de Responsabilidad Limitada": "SRL",
            "sociedad de responsabilidad limitada": "SRL",
            "SOCIEDAD ANÓNIMA": "SA",
            "Sociedad Anónima": "SA",
            "sociedad anónima": "SA",
            
            # Итальянские
            "SOCIETÀ A RESPONSABILITÀ LIMITATA": "SRL",
            "Società a Responsabilità Limitata": "SRL",
            "società a responsabilità limitata": "SRL",
            "SOCIETÀ PER AZIONI": "SpA",
            "Società per Azioni": "SpA",
            "società per azioni": "SpA",
            
            # Русские
            "ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ": "ООО",
            "Общество с ограниченной ответственностью": "ООО",
            "общество с ограниченной ответственностью": "ООО",
            "АКЦИОНЕРНОЕ ОБЩЕСТВО": "АО",
            "Акционерное общество": "АО",
            "акционерное общество": "АО",
            "ЗАКРЫТОЕ АКЦИОНЕРНОЕ ОБЩЕСТВО": "ЗАО",
            "Закрытое акционерное общество": "ЗАО",
            "закрытое акционерное общество": "ЗАО",
            "ОТКРЫТОЕ АКЦИОНЕРНОЕ ОБЩЕСТВО": "ОАО",
            "Открытое акционерное общество": "ОАО",
            "открытое акционерное общество": "ОАО",
            
            # Эстонские
            "OSAÜHING": "OÜ",
            "Osaühing": "OÜ",
            "osaühing": "OÜ",
            "AKTSIASELTS": "AS",
            "Aktsiaselts": "AS",
            "aktsiaselts": "AS",
        }
        
        # Ищем и заменяем формы собственности
        for full_form, short_form in legal_forms.items():
            if full_form in name:
                name = name.replace(full_form, short_form)
                break
        
        # Убираем лишние пробелы и приводим к красивому виду
        name = " ".join(name.split())
        
        # Убираем дублирующиеся сокращения в конце
        name = self._remove_duplicate_legal_forms(name)
        
        return name
    
    def _remove_duplicate_legal_forms(self, name: str) -> str:
        """Убирает дублирующиеся формы собственности в названии"""
        # Список всех возможных сокращений
        short_forms = [
            "Sp. z o.o.", "S.A.", "GmbH", "AG", "LLC", "Ltd", "Corp", "Inc",
            "SARL", "SA", "SRL", "SpA", "ООО", "АО", "ЗАО", "ОАО", "OÜ", "AS"
        ]
        
        for form in short_forms:
            # Если форма встречается несколько раз, оставляем только одну в конце
            parts = name.split(form)
            if len(parts) > 2:  # Значит форма встречается больше одного раза
                # Объединяем все части кроме последней и добавляем форму в конец
                clean_name = form.join(parts[:-1]).strip()
                name = f"{clean_name} {form}" if clean_name else form
        
        return name.strip()

    def _extract_supplier_data(self, document_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Извлекает данные поставщика из проформы/контракта"""
        try:
            # Сначала проверяем иерархическую структуру supplier.*
            supplier_info = document_data.get("supplier", {})
            
            # Ищем данные поставщика в разных полях (плоские и иерархические)
            supplier_name = (
                supplier_info.get("name") or  # supplier.name
                document_data.get("supplier_name") or 
                document_data.get("vendor_name") or
                document_data.get("from_name") or
                document_data.get("company_name")
            )
            
            supplier_vat = (
                supplier_info.get("vat") or  # supplier.vat
                document_data.get("supplier_vat") or
                document_data.get("vendor_vat") or 
                document_data.get("from_vat") or
                document_data.get("vat_number")
            )
            
            # Предпочитаем структурированный адрес из LLM, затем строковый
            supplier_address = (
                supplier_info.get("address") or  # supplier.address
                document_data.get("supplier_address") or
                document_data.get("vendor_address") or
                document_data.get("from_address") or
                document_data.get("address")
            )
            street_llm = document_data.get("supplier_street")
            city_llm = document_data.get("supplier_city")
            zip_llm = document_data.get("supplier_zip_code")
            
            supplier_email = (
                supplier_info.get("email") or  # supplier.email
                document_data.get("supplier_email") or
                document_data.get("vendor_email") or
                document_data.get("from_email") or
                document_data.get("email")
            )
            
            supplier_phone = (
                supplier_info.get("phone") or  # supplier.phone
                document_data.get("supplier_phone") or
                document_data.get("phone")
            )
            
            # Извлекаем банковские реквизиты (поддержка нового LLM-формата bank.{...})
            bank_info = document_data.get("bank") or {}
            bank_name = (
                document_data.get("bank_name")
                or bank_info.get("bank_name")
                or bank_info.get("name")
            )
            iban = (
                document_data.get("iban")
                or bank_info.get("iban")
            )
            bank_account = (
                document_data.get("bank_account")
                or bank_info.get("bank_account")
            )
            swift_bic = (
                document_data.get("swift_bic")
                or document_data.get("swift")
                or bank_info.get("swift")
                or bank_info.get("swift_bic")
            )
            payment_method = (
                document_data.get("payment_method")
                or bank_info.get("payment_method")
            )
            
            # Извлекаем налоговую ставку из документа
            tax_rate = (
                document_data.get("tax_rate") or
                document_data.get("vat_rate") or
                document_data.get("tax_percentage") or
                self._extract_tax_from_text(document_data.get("extracted_text", ""))
            )
            
            # Извлекаем ZIP код (LLM приоритет)
            supplier_zip = (
                zip_llm or
                supplier_info.get("zip_code") or
                document_data.get("zip_code") or
                document_data.get("postal_code")
            )
            
            # Определяем страну - приоритет supplier.country, затем по VAT/адресу
            country = (
                supplier_info.get("country") or  # supplier.country
                document_data.get("supplier_country") or
                self._determine_country(supplier_vat or "", self._extract_address_string(supplier_address))
            )
            
            if not supplier_name:
                logger.warning("Не найдено название поставщика в документе")
                return None
            
            # 🎯 НОРМАЛИЗУЕМ НАЗВАНИЕ КОМПАНИИ
            normalized_name = self._normalize_company_name(supplier_name)
            
            # Нормализуем VAT номер
            normalized_vat = self._normalize_vat(supplier_vat or "", country)
            
            # Извлекаем контактное лицо: предпочитаем issuer_contact_person, затем contact_person
            contact_person = (
                supplier_info.get("contact_person")
                or document_data.get("issuer_contact_person")
                or document_data.get("contact_person")
                or ""
            )
            # Исключаем пользователя
            if isinstance(contact_person, str) and contact_person.strip().lower() == "pavel kaliadka":
                contact_person = ""

            return {
                "name": normalized_name,  # Теперь нормализованное
                "vat": normalized_vat,
                "address": self._extract_address_string(supplier_address),
                "zip_code": supplier_zip.strip() if supplier_zip and isinstance(supplier_zip, str) else "",
                "supplier_street": (street_llm or ""),
                "supplier_city": (city_llm or ""),
                "email": supplier_email.strip() if supplier_email and isinstance(supplier_email, str) else "",
                "country": country,
                "phone": supplier_phone.strip() if supplier_phone and isinstance(supplier_phone, str) else "",
                # Банковские реквизиты
                "bank_name": bank_name,
                "iban": iban,
                "bank_account": bank_account,
                "swift_bic": swift_bic,
                "payment_method": payment_method,
                # Контактное лицо
                "contact_person": contact_person,
                # Налоговая ставка
                "tax_rate": tax_rate
            }
            
        except Exception as e:
            logger.error(f"Ошибка извлечения данных поставщика: {e}")
            return None
    
    def _is_our_company(self, supplier_data: Dict[str, Any]) -> bool:
        """Проверяет, является ли компания нашей"""
        return is_our_company(supplier_data["name"], supplier_data["vat"])
    
    async def _find_existing_contact(self, supplier_data: Dict[str, Any]) -> Optional[Any]:
        """Ищет существующий контакт в кэше"""
        if not self.contact_cache:
            return None
        
        # Поиск по VAT (приоритет)
        if supplier_data["vat"]:
            found = self.contact_cache.search_by_vat(supplier_data["vat"])
            if found:
                return found
        
        # Поиск по названию компании
        if supplier_data["name"]:
            found = self.contact_cache.search_by_company(supplier_data["name"])
            if found:
                return found[0] if found else None
        
        # Поиск по email
        if supplier_data["email"]:
            found = self.contact_cache.search_by_email(supplier_data["email"])
            if found:
                return found
        
        return None
    
    async def _create_new_contact(self, supplier_data: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """Создает новый контакт в Zoho Books"""
        try:
            # Определяем организацию по стране поставщика
            org_id = self._determine_organization(supplier_data["country"])
            
            # Подготавливаем данные для Zoho API
            # Company Name и Display Name должны быть одинаковыми и читаемыми
            normalized_name = supplier_data["name"]
            
            # Формируем правильный адрес с разделением на поля
            billing_address = {}
            if supplier_data["address"]:
                # Отладочная информация
                logger.info(f"🔍 Обрабатываем адрес: '{supplier_data['address']}'")
                
                address_text = supplier_data["address"] if isinstance(supplier_data["address"], str) else ""
                street_llm = supplier_data.get("supplier_street") or ""
                city_llm = supplier_data.get("supplier_city") or ""
                zip_llm = supplier_data.get("zip_code") or supplier_data.get("supplier_zip_code") or ""
                
                if street_llm or city_llm or zip_llm:
                    billing_address = {
                        "address": street_llm or address_text,
                        "city": city_llm,
                        "zip": zip_llm,
                        "country": supplier_data["country"]
                    }
                    logger.info(f"✅ LLM-адрес: улица='{billing_address['address']}', город='{billing_address['city']}', индекс='{billing_address['zip']}', страна='{supplier_data['country']}'")
                elif address_text:
                    # Специальная обработка для немецких адресов с землей в строке
                    if "Baden-Württemberg" in address_text:
                        parts = [p.strip() for p in address_text.split(',')]
                        if len(parts) >= 4:
                            street = parts[0]
                            zip_code = parts[2]
                            city_part = parts[3]
                            city = city_part.split(" - ")[1].strip() if " - " in city_part else city_part
                            billing_address = {
                                "address": street,
                                "city": city,
                                "zip": zip_code,
                                "country": supplier_data["country"]
                            }
                            logger.info(f"✅ Разобран немецкий адрес: улица='{street}', город='{city}', индекс='{zip_code}'")
                        else:
                            billing_address = {"address": address_text, "country": supplier_data["country"]}
                    else:
                        parts = [p.strip() for p in address_text.split(',')]
                        if len(parts) >= 3:
                            billing_address = {
                                "address": parts[0],
                                "city": parts[1],
                                "zip": zip_llm,
                                "country": supplier_data["country"]
                            }
                            logger.info(f"✅ Разобран адрес: улица='{billing_address['address']}', город='{billing_address['city']}', индекс='{billing_address['zip']}', страна='{supplier_data['country']}'")
                        else:
                            billing_address = {"address": address_text, "country": supplier_data["country"]}
                else:
                    billing_address = {
                        "address": supplier_data["address"],
                        "country": supplier_data["country"]
                    }
            
            contact_payload = {
                "contact_name": normalized_name,    # Display Name - для отображения  
                "company_name": normalized_name,    # Company Name - основное название
                "contact_type": "vendor",
                "billing_address": billing_address,
                "shipping_address": billing_address.copy(),  # Копируем billing address в shipping
                "custom_fields": []
            }
            
            # Добавляем банковские реквизиты в remarks если есть (компактный формат для лимита 100 символов)
            remarks_parts = []
            if supplier_data.get("bank_name"):
                remarks_parts.append(supplier_data['bank_name'])
                logger.info(f"🏦 Добавляем банк: {supplier_data['bank_name']}")
            if supplier_data.get("iban"):
                remarks_parts.append(supplier_data['iban'])
            elif supplier_data.get("bank_account"):
                remarks_parts.append(supplier_data['bank_account'])
                logger.info(f"🏦 Добавляем IBAN: {supplier_data['iban']}")
            if supplier_data.get("swift_bic"):
                remarks_parts.append(supplier_data['swift_bic'])
                logger.info(f"🏦 Добавляем SWIFT: {supplier_data['swift_bic']}")
            
            if remarks_parts:
                remarks_text = "\n".join(remarks_parts)
                # Проверяем лимит 100 символов
                if len(remarks_text) > 100:
                    # Если превышает, используем только банк
                    compact_remarks = []
                    if supplier_data.get("bank_name"):
                        compact_remarks.append(supplier_data['bank_name'])
                    remarks_text = " ".join(compact_remarks)
                    
                    # Если все еще превышает, обрезаем
                    if len(remarks_text) > 100:
                        remarks_text = remarks_text[:97] + "..."
                
                # Добавляем в оба поля для совместимости
                contact_payload["remarks"] = remarks_text
                contact_payload["notes"] = remarks_text
                logger.info(f"📝 Remarks/Notes сформированы ({len(remarks_text)} символов): {remarks_text}")
            else:
                logger.warning("⚠️ Банковские реквизиты не найдены")
            
            # Добавляем VAT если есть
            if supplier_data["vat"]:
                # Определяем правильное поле VAT в зависимости от организации
                vat_field = "cf_tax_id" if org_id == "20082562863" else "cf_vat_id"
                contact_payload["custom_fields"].append({
                    "api_name": vat_field,
                    "value": supplier_data["vat"]
                })
                logger.info(f"🆔 Добавляем VAT: {supplier_data['vat']} в поле {vat_field}")
            
            # Добавляем email если есть
            if supplier_data["email"]:
                contact_payload["email"] = supplier_data["email"]
                logger.info(f"📧 Добавляем email: {supplier_data['email']}")
            else:
                logger.warning("⚠️ Email не найден")
            
            # Добавляем телефон если есть (в поля phone + phone_code + phone_country_code)
            if supplier_data["phone"]:
                # Парсим телефон и форматируем для Zoho
                phone_data = parse_phone_number(supplier_data["phone"])
                formatted_phone = phone_data.get('national_format', supplier_data["phone"])  # без +
                contact_payload["phone"] = formatted_phone
                # Заполняем коды страны для выпадающего списка
                if phone_data.get('country_calling_code'):
                    code = str(phone_data['country_calling_code'])
                    contact_payload["phone_code"] = code
                    contact_payload["phone_country_code"] = code
                if phone_data.get('is_valid'):
                    logger.info(f"📞 Добавляем телефон: {supplier_data['phone']} -> {formatted_phone} (страна: {phone_data.get('country_name', 'неизвестно')})")
                else:
                    logger.warning(f"📞 Добавляем телефон (не валиден): {supplier_data['phone']} -> {formatted_phone}")
            else:
                logger.warning("⚠️ Телефон не найден")
            
            # Создаем Primary Contact Person только если нашли реальные данные в документе
            contact_persons = []
            if supplier_data.get("contact_person") or supplier_data.get("email") or supplier_data.get("phone"):
                contact_person = {
                    "salutation": "",
                    "first_name": supplier_data.get("contact_person", "").split()[0] if supplier_data.get("contact_person") else "",
                    "last_name": supplier_data.get("contact_person", "").split()[-1] if supplier_data.get("contact_person") and len(supplier_data.get("contact_person").split()) > 1 else "",
                    "is_primary_contact": True
                }
                
                if supplier_data.get("email"):
                    contact_person["email"] = supplier_data["email"]
                    logger.info(f"👤 Добавляем email в контактное лицо: {supplier_data['email']}")
                
                if supplier_data.get("phone"):
                    # Используем тот же форматированный телефон
                    phone_data = parse_phone_number(supplier_data["phone"])
                    formatted_phone = phone_data.get('national_format', supplier_data["phone"])  # без +
                    
                    contact_person["phone"] = formatted_phone
                    logger.info(f"👤 Добавляем телефон в контактное лицо: {supplier_data['phone']} -> {formatted_phone}")
                
                # Добавляем контактное лицо только если есть хотя бы одно из полей
                if contact_person.get('first_name') or contact_person.get('last_name') or contact_person.get('email') or contact_person.get('phone'):
                    contact_persons.append(contact_person)
                    contact_payload["contact_persons"] = contact_persons
                    logger.info(f"👤 Создано контактное лицо: {contact_person.get('first_name','')} {contact_person.get('last_name','')}")
            else:
                logger.warning("⚠️ Нет данных для создания контактного лица")
            
            # Устанавливаем Tax Rate в зависимости от организации и документа
            tax_rate_id = await self._determine_tax_rate(org_id, supplier_data)
            if tax_rate_id:
                contact_payload["tax_rate_id"] = tax_rate_id
                logger.info(f"💰 Установлен Tax Rate ID: {tax_rate_id}")
            else:
                logger.warning("⚠️ Не удалось определить Tax Rate")
            
            # Создаем контакт в Zoho
            logger.info(f"Создаем контакт в Zoho: {supplier_data['name']} (org: {org_id})")
            logger.info(f"📋 Contact Payload: {contact_payload}")
            response = await self.zoho_api.create_contact(contact_payload, org_id)
            
            if response and "contact" in response:
                contact_id = response["contact"]["contact_id"]
                created_contact_data = response["contact"]  # Полные данные созданного контакта
                logger.info(f"Контакт создан успешно: {supplier_data['name']} (ID: {contact_id})")
                return True, contact_id, created_contact_data
            else:
                logger.error(f"Не удалось создать контакт: {response}")
                return False, None, None
                
        except Exception as e:
            logger.error(f"Ошибка создания контакта в Zoho: {e}")
            return False, None, None
    
    def _determine_country(self, vat: str, address: str) -> str:
        """Определяет страну по VAT префиксу или адресу"""
        if vat and len(vat) >= 2:
            # Извлекаем префикс из VAT
            vat_prefix = vat[:2].upper()
            country_map = {
                "PL": "Poland",
                "EE": "Estonia", 
                "DE": "Germany",
                "FR": "France",
                "IT": "Italy",
                "ES": "Spain",
                "NL": "Netherlands",
                "BE": "Belgium",
                "AT": "Austria",
                "SE": "Sweden",
                "DK": "Denmark", 
                "FI": "Finland",
                "GB": "United Kingdom",
                "IE": "Ireland"
            }
            if vat_prefix in country_map:
                return country_map[vat_prefix]
        
        # Попытка определить по адресу (базовая логика)
        if address:
            address_lower = address.lower()
            if any(word in address_lower for word in ["poland", "polska", "warszawa", "krakow"]):
                return "Poland"
            elif any(word in address_lower for word in ["estonia", "tallinn", "tartu"]):
                return "Estonia"
            elif any(word in address_lower for word in ["germany", "deutschland", "berlin", "münchen"]):
                return "Germany"
        
        return "Poland"  # По умолчанию для нашего региона
    
    def _extract_address_string(self, address) -> str:
        """Извлекает строку адреса из строки или словаря"""
        if not address:
            return ""
        
        if isinstance(address, str):
            return address
        
        if isinstance(address, dict):
            # Собираем адрес из компонентов
            parts = []
            if address.get('address'):
                parts.append(address['address'])
            if address.get('city'):
                parts.append(address['city'])
            if address.get('country'):
                parts.append(address['country'])
            return ", ".join(parts)
        
        return str(address)
    
    def _normalize_vat(self, vat: str, country: str) -> str:
        """Нормализует VAT номер с правильным префиксом"""
        if not vat:
            return ""
        
        # Очищаем от пробелов и символов
        clean_vat = vat.replace(" ", "").replace("-", "").upper()
        
        # Определяем префикс по стране
        country_prefixes = {
            "Poland": "PL",
            "Estonia": "EE",
            "Germany": "DE", 
            "France": "FR",
            "Italy": "IT",
            "Spain": "ES",
            "Netherlands": "NL",
            "Belgium": "BE",
            "Austria": "AT",
            "Sweden": "SE",
            "Denmark": "DK",
            "Finland": "FI",
            "United Kingdom": "GB",
            "Ireland": "IE"
        }
        
        expected_prefix = country_prefixes.get(country, "")
        
        # Если уже есть правильный префикс - возвращаем как есть
        if expected_prefix and clean_vat.startswith(expected_prefix):
            return clean_vat
        
        # Если есть другой префикс - заменяем
        if len(clean_vat) >= 2 and clean_vat[:2].isalpha():
            if expected_prefix:
                return expected_prefix + clean_vat[2:]
        
        # Если префикса нет - добавляем
        if expected_prefix and clean_vat.isdigit():
            return expected_prefix + clean_vat
        
        return clean_vat
    
    def _determine_organization(self, country: str) -> str:
        """Определяет ID организации Zoho по стране"""
        # Для польских поставщиков - PARKENTERTAINMENT
        # Для эстонских и других EU - TaVie Europe
        if country == "Poland":
            return "20082562863"  # PARKENTERTAINMENT
        else:
            return "20092948714"  # TaVie Europe OÜ
    
    async def _refresh_cache(self, org_id: Optional[str] = None, org_name: Optional[str] = None, new_contact_data: Optional[Dict[str, Any]] = None):
        """Обновляет кэш ТОЛЬКО новым контактом"""
        try:
            if self.contact_cache and new_contact_data and org_id:
                logger.info("🔄 Добавляю новый контакт в кэш после создания")
                
                # 1. Добавляем в основной кэш (главный кэш)
                self.contact_cache.add_contacts([new_contact_data])
                self.contact_cache.save_cache()
                
                logger.info(f"✅ Новый контакт добавлен в главный кэш: {new_contact_data.get('contact_name', 'Unknown')}")
                
                # 2. Добавляем новый контакт в кэш организации
                if org_name == "TaVie Europe OÜ":
                    org_cache_file = "data/optimized_cache/TaVie_Europe_optimized.json"
                elif org_name == "PARKENTERTAINMENT":
                    org_cache_file = "data/optimized_cache/PARKENTERTAINMENT_optimized.json"
                else:
                    logger.warning(f"⚠️ Неизвестная организация: {org_name}")
                    return
                
                from src.domain.services.contact_cache import OptimizedContactCache
                org_cache = OptimizedContactCache(org_cache_file)
                org_cache.add_contacts([new_contact_data])
                org_cache.save_cache()
                
                logger.info(f"✅ Новый контакт добавлен в кэш {org_name}: {new_contact_data.get('contact_name', 'Unknown')}")
                
            else:
                logger.warning("⚠️ Кэш контактов не инициализирован или данные контакта не переданы")
                
        except Exception as e:
            logger.error(f"❌ Ошибка добавления контакта в кэш: {e}")
    
    def _extract_tax_from_text(self, text: str) -> Optional[str]:
        """Извлекает налоговую ставку из текста документа"""
        if not text:
            return None
        
        import re
        
        # Ищем налоговые ставки в тексте (для PARKENTERTAINMENT: только 0%, 8%, 23%)
        # Паттерны: "23% VAT", "8 % USt.:", "0% налог"
        tax_patterns = [
            r'(\d{1,2})\s*%\s*(?:MwSt|USt|VAT|налог)',
            r'(?:MwSt|USt|VAT|налог)\s*[:,.]?\s*(\d{1,2})\s*%',
            r'(\d{1,2})\s*%\s*(?:tax|налог)',
            r'tax\s*rate\s*:\s*(\d{1,2})\s*%',
            r'(\d{1,2})\s+%\s+(?:USt|MwSt|VAT)',  # "8 % USt"
            r'(\d{1,2})\s*%\s*(?:Umsatzsteuer|Mehrwertsteuer)',  # немецкие варианты
            r'VAT\s*[:.]?\s*(\d{1,2})\s*%',  # "VAT: 8%"
            r'(\d{1,2})\s*%\s*(?:vat|VAT)'  # "8% VAT"
        ]
        
        # Разрешенные налоговые ставки для PARKENTERTAINMENT
        allowed_rates = ["0", "8", "23"]
        
        for pattern in tax_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                tax_rate = match.strip()
                if tax_rate in allowed_rates:
                    logger.info(f"🔍 Найдена РАЗРЕШЕННАЯ налоговая ставка в документе: {tax_rate}%")
                    return tax_rate
                else:
                    logger.info(f"🔍 Найдена НЕДОПУСТИМАЯ налоговая ставка: {tax_rate}% (разрешены: 0, 8, 23)")
        
        logger.info("🔍 Разрешенная налоговая ставка в документе не найдена")
        return None
    
    async def _determine_tax_rate(self, org_id: str, supplier_data: Dict[str, Any]) -> Optional[str]:
        """Определяет tax_rate_id для Zoho на основе организации и данных поставщика"""
        try:
            if org_id == "20092948714":  # TaVie Europe OÜ
                # Для TaVie Europe всегда "tax export" (0%) так как не покупают в Эстонии
                logger.info("💰 TaVie Europe OÜ -> tax export [0%]")
                return "20092948714000000073"  # tax export [0%]
                
            elif org_id == "20082562863":  # PARKENTERTAINMENT
                # Для PARKENTERTAINMENT налог ТОЛЬКО 0%, 8% или 23% из документа
                doc_tax_rate = supplier_data.get("tax_rate")
                
                # Маппинг ТОЛЬКО разрешенных налоговых ставок PARKENTERTAINMENT
                tax_mapping = {
                    "0": "20082562863000000080",   # Tax Export [0%]
                    "8": "20082562863000000081",   # Tax [8%] (льготная ставка)
                    "23": "20082562863000000079",  # Tax PL [23%] (стандартная)
                }
                
                # Если найдена разрешенная ставка в документе
                if doc_tax_rate and str(doc_tax_rate) in tax_mapping:
                    tax_id = tax_mapping[str(doc_tax_rate)]
                    logger.info(f"💰 PARKENTERTAINMENT: найдена ставка {doc_tax_rate}% в документе -> ID: {tax_id}")
                    return tax_id
                
                # Если ставка не найдена или недопустима - по умолчанию 23%
                logger.warning(f"⚠️ PARKENTERTAINMENT: налог {doc_tax_rate}% не найден или недопустим. Устанавливаю 23%")
                return tax_mapping["23"]
            
            logger.warning(f"⚠️ Неизвестная организация: {org_id}")
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка определения налоговой ставки: {e}")
            return None
    
    async def close(self):
        """Закрытие ресурсов"""
        if self.zoho_api:
            await self.zoho_api.close()

# Глобальный экземпляр для использования в боте
_supplier_creator = None

async def get_supplier_creator() -> SupplierContactCreator:
    """Получить экземпляр создателя контактов (singleton)"""
    global _supplier_creator
    if _supplier_creator is None:
        _supplier_creator = SupplierContactCreator()
    return _supplier_creator

async def create_supplier_from_document(document_data: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Главная функция для создания поставщика из документа
    
    Args:
        document_data: Данные из анализа проформы/контракта
        
    Returns:
        Tuple[success, message]: Результат операции и сообщение для пользователя
    """
    creator = await get_supplier_creator()
    return await creator.check_and_create_supplier_contact(document_data) 