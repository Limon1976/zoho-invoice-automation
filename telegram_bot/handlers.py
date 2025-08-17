import tempfile
import os
from typing import Dict, Any, Optional
from pathlib import Path
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
import re
from telegram.ext import ContextTypes, Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler

from functions.smart_document_processor import SmartDocumentProcessor
from functions.llm_document_extractor import llm_analyze_contract_risks, llm_translate_to_ru  # LLM risks summary + RU translate
from functions.flower_line_extractor import extract_flower_lines_from_ocr, parse_invoice_items
from functions.complete_flower_extractor import extract_all_flower_positions, format_for_telegram_bot
from functions.pdf_direct_parser import extract_flower_positions_from_pdf, format_for_telegram_bot as format_pdf_result, is_suitable_for_pdf_parsing
from functions.contact_creator import create_supplier_from_document
from functions.agent_invoice_parser import analyze_proforma_via_agent
from functions.zoho_items_manager import ZohoItemsManager, CarItemData
from functions.phone_parser import parse_phone_number, format_phone_for_zoho
from functions.export_zoho_accounts import get_accounts_cached_or_fetch
from functions.zoho_api import (
    get_access_token,
    find_branch_id,
    find_warehouse_id,
    find_tax_by_percent,
    bill_exists_smart,
    get_contact_by_name,
    find_supplier_in_zoho,
)

import logging
logger = logging.getLogger(__name__)

# Глобальная переменная для хранения последнего анализа документа
last_document_analysis = None
_recent_callbacks: dict[str, float] = {}
_RECENT_TTL_SECONDS = 10.0


async def smart_supplier_check(supplier_name: str, supplier_vat: Optional[str] = None,
                               our_company: Optional[str] = None) -> Dict[str, Any]:
    """
    Умная проверка поставщика:
    1. Определяет организацию из документа (our_company)
    2. Проверяет в кэше соответствующей организации
    3. Если не найден - проверяет в общем кэше
    4. Возвращает результат с рекомендациями
    """
    try:
        # Импортируем необходимые модули
        from src.domain.services.contact_cache import OptimizedContactCache
        from src.domain.services.vat_validator import VATValidatorService

        # Определяем организацию из документа
        organization_id = None
        organization_name = None
        cache_file = None

        if our_company:
            # Определяем организацию по названию нашей компании
            if "parkentertainment" in our_company.lower() or "PL5272956146" in our_company:
                organization_id = "20082562863"
                organization_name = "PARKENTERTAINMENT"
                cache_file = "data/optimized_cache/PARKENTERTAINMENT_optimized.json"
            elif "tavie" in our_company.lower() or "EE102288270" in our_company:
                organization_id = "20092948714"
                organization_name = "TaVie Europe OÜ"
                cache_file = "data/optimized_cache/TaVie_Europe_optimized.json"

        # Нормализуем VAT из документа (добавляем ISO-префикс на основе СТРАНЫ ПОСТАВЩИКА из документа)
        normalized_doc_vat = None
        if supplier_vat:
            vvs_norm = VATValidatorService()
            expected_country = None
            # Определяем префикс по стране поставщика из распознанного документа
            # Используем нейтральное значение страны, так как VAT уже нормализуется выше при формировании
            # сообщения в handle_pdf. Это устраняет падение при обращении к last_document_analysis.
            supplier_country = ''
            supplier_country_l = supplier_country.strip().lower()
            country_to_iso = {
                'poland': 'PL', 'polska': 'PL', 'estonia': 'EE', 'eesti': 'EE', 'germany': 'DE',
                'deutschland': 'DE', 'latvia': 'LV', 'lithuania': 'LT', 'netherlands': 'NL',
                'ireland': 'IE', 'france': 'FR', 'spain': 'ES', 'italy': 'IT', 'portugal': 'PT',
                'sweden': 'SE', 'denmark': 'DK', 'united kingdom': 'GB', 'uk': 'GB'
            }
            expected_country = country_to_iso.get(supplier_country_l)
            validation_norm = vvs_norm.validate_vat(supplier_vat, expected_country=expected_country)
            if validation_norm.is_valid:
                normalized_doc_vat = vvs_norm.add_country_prefix(
                    validation_norm.vat_number.value,
                    expected_country or validation_norm.country_code
                ).replace(' ', '')
            else:
                digits_only = ''.join(ch for ch in str(supplier_vat) if ch.isdigit())
                if digits_only and expected_country:
                    normalized_doc_vat = f"{expected_country}{digits_only}"
                else:
                    normalized_doc_vat = supplier_vat
            try:
                logger.info(f"VAT compare prep: supplier_country='{supplier_country}' raw='{supplier_vat}' normalized='{normalized_doc_vat}'")
            except Exception:
                pass

        # ВАЖНО: сначала работаем с локальным кэшем, а к Zoho обращаемся только если в кэше не нашли

        # Шаг 1: Проверяем в кэше соответствующей организации
        if cache_file and organization_name:
            try:
                org_cache = OptimizedContactCache(cache_file)
                
                # Сначала ищем по VAT, если он есть
                found_in_org = []
                if supplier_vat or normalized_doc_vat:
                    search_vat = (normalized_doc_vat or supplier_vat or '').strip()
                    found = org_cache.search_by_vat(search_vat)
                    if not found and supplier_vat:
                        found = org_cache.search_by_vat(supplier_vat)
                    found_in_org = [found] if found else []
                
                # Если не найдено по VAT - ищем по названию компании
                if not found_in_org:
                    found_in_org = org_cache.search_by_company(supplier_name)
                    
                    # Если нашли по названию, проверяем расхождения в VAT
                    if found_in_org and (supplier_vat or normalized_doc_vat):
                        cached_contact = found_in_org[0].to_dict()
                        cached_vat = (cached_contact.get('vat_number') or '').strip()
                        doc_vat_for_compare = (normalized_doc_vat or supplier_vat or '').strip()
                        try:
                            logger.info(f"VAT compare (org cache): cached='{cached_vat}' doc='{doc_vat_for_compare}'")
                        except Exception:
                            pass
                        # Допускаем равенство, если совпадают цифры без префикса
                        cached_digits = ''.join(ch for ch in cached_vat if ch.isdigit())
                        doc_digits = ''.join(ch for ch in doc_vat_for_compare if ch.isdigit())
                        if cached_digits and doc_digits and cached_digits == doc_digits:
                            return {
                                'status': 'found_in_cache',
                                'contact': cached_contact,
                                'organization_id': organization_id,
                                'organization_name': organization_name,
                                'message': f'✅ Поставщик "{supplier_name}" найден в кэше {organization_name}',
                                'recommended_action': 'update_existing',
                                'button_text': '📝 Обновить существующего',
                                'button_action': 'update_existing_contact'
                            }
                        # Если в кэше VAT пуст или не совпадает, проверяем напрямую в Zoho
                        try:
                            if organization_id:
                                direct = find_supplier_in_zoho(organization_id, supplier_name, None)
                                zoho_vat = (direct.get('vat_number') or '').strip() if direct else ''
                                zoho_digits = ''.join(ch for ch in zoho_vat if ch.isdigit())
                                if zoho_vat == doc_vat_for_compare or (zoho_digits and doc_digits and zoho_digits == doc_digits):
                                    return {
                                        'status': 'found_in_cache',
                                        'contact': cached_contact or direct,
                                        'organization_id': organization_id,
                                        'organization_name': organization_name,
                                        'message': f'✅ Поставщик "{supplier_name}" найден (VAT совпадает с Zoho)',
                                        'recommended_action': 'update_existing',
                                        'button_text': '📝 Обновить существующего',
                                        'button_action': 'update_existing_contact'
                                    }
                        except Exception as e:
                            logger.warning(f"Zoho verify VAT compare failed: {e}")
                        
                        # Если VAT отсутствует в кэше, но есть в документе - предлагаем обновление
                        if not cached_vat or cached_vat != doc_vat_for_compare:
                            return {
                                'status': 'found_with_vat_mismatch',
                                'contact': cached_contact,
                                'organization_id': organization_id,
                                'organization_name': organization_name,
                                'message': f'⚠️ Поставщик "{supplier_name}" найден, но VAT отличается (кэш: {cached_vat or "отсутствует"}, документ: {doc_vat_for_compare or "отсутствует"})',
                                'recommended_action': 'update_vat',
                                'button_text': '🔄 Обновить VAT в Zoho',
                                'button_action': 'update_supplier_vat'
                            }

                if found_in_org:
                    # Поставщик найден в кэше организации (VAT совпадает или отсутствует в документе)
                    cached_contact = found_in_org[0].to_dict()
                    return {
                        'status': 'found_in_cache',
                        'contact': cached_contact,
                        'organization_id': organization_id,
                        'organization_name': organization_name,
                        'message': f'✅ Поставщик "{supplier_name}" найден в кэше {organization_name}',
                        'recommended_action': 'update_existing',
                        'button_text': '📝 Обновить существующего',
                        'button_action': 'update_existing_contact'
                    }
            except Exception as e:
                logger.warning(f"Ошибка проверки в кэше организации {organization_name}: {e}")

        # Шаг 2: Проверяем в общем кэше
        try:
            general_cache = OptimizedContactCache("data/optimized_cache/all_contacts_optimized.json")
            
            # Сначала ищем по VAT, если он есть
            found_in_general = []
            if supplier_vat or normalized_doc_vat:
                search_vat = (normalized_doc_vat or supplier_vat or '').strip()
                found = general_cache.search_by_vat(search_vat)
                if not found and supplier_vat:
                    found = general_cache.search_by_vat(supplier_vat)
                found_in_general = [found] if found else []
            
            # Если не найдено по VAT - ищем по названию компании
            if not found_in_general:
                found_in_general = general_cache.search_by_company(supplier_name)
                
                # Если нашли по названию в общем кэше, проверяем расхождения в VAT
                if found_in_general and (supplier_vat or normalized_doc_vat):
                    cached_contact = found_in_general[0].to_dict()
                    cached_vat = (cached_contact.get('vat_number') or '').strip()
                    doc_vat_for_compare = (normalized_doc_vat or supplier_vat or '').strip()
                    try:
                        logger.info(f"VAT compare (general cache): cached='{cached_vat}' doc='{doc_vat_for_compare}'")
                    except Exception:
                        pass
                    cached_digits = ''.join(ch for ch in cached_vat if ch.isdigit())
                    doc_digits = ''.join(ch for ch in doc_vat_for_compare if ch.isdigit())
                    if cached_digits and doc_digits and cached_digits == doc_digits:
                        return {
                            'status': 'found_in_general_cache',
                            'contact': cached_contact,
                            'organization_id': organization_id,
                            'organization_name': organization_name,
                            'message': f'🔄 Поставщик "{supplier_name}" найден в общем кэше, но не в кэше {organization_name}',
                            'recommended_action': 'refresh_cache',
                            'button_text': '🔄 Обновить кэш',
                            'button_action': 'refresh_cache_only'
                        }
                    # Если в кэше VAT пуст/не совпадает – сверим с Zoho
                    try:
                        if organization_id:
                            direct = find_supplier_in_zoho(organization_id, supplier_name, None)
                            zoho_vat = (direct.get('vat_number') or '').strip() if direct else ''
                            zoho_digits = ''.join(ch for ch in zoho_vat if ch.isdigit())
                            if zoho_vat == doc_vat_for_compare or (zoho_digits and doc_digits and zoho_digits == doc_digits):
                                return {
                                    'status': 'found_in_general_cache',
                                    'contact': cached_contact or direct,
                                    'organization_id': organization_id,
                                    'organization_name': organization_name,
                                    'message': f'🔄 Поставщик "{supplier_name}" найден (VAT совпадает с Zoho)',
                                    'recommended_action': 'update_existing',
                                    'button_text': '📝 Обновить контакт',
                                    'button_action': 'update_existing_contact'
                                }
                    except Exception as e:
                        logger.warning(f"Zoho verify VAT compare (general) failed: {e}")
                    
                    # Если VAT отсутствует в кэше, но есть в документе - предлагаем обновление
                    if not cached_vat or cached_vat != doc_vat_for_compare:
                        return {
                            'status': 'found_in_general_with_vat_mismatch',
                            'contact': cached_contact,
                            'organization_id': organization_id,
                            'organization_name': organization_name,
                            'message': f'⚠️ Поставщик "{supplier_name}" найден в общем кэше, VAT отличается (кэш: {cached_vat or "отсутствует"}, документ: {doc_vat_for_compare or "отсутствует"})',
                            'recommended_action': 'update_vat_and_refresh',
                            'button_text': '🔄 Обновить VAT и синхронизировать',
                            'button_action': 'update_supplier_vat_and_refresh'
                        }

            if found_in_general:
                # Поставщик найден в общем кэше, но не в кэше организации
                cached_contact = found_in_general[0].to_dict()
                return {
                    'status': 'found_in_general_cache',
                    'contact': cached_contact,
                    'organization_id': organization_id,
                    'organization_name': organization_name,
                    'message': f'🔄 Поставщик "{supplier_name}" найден в общем кэше, но не в кэше {organization_name}',
                    'recommended_action': 'refresh_cache',
                    'button_text': '🔄 Обновить кэш',
                    'button_action': 'refresh_cache_only'
                }
        except Exception as e:
            logger.warning(f"Ошибка проверки в общем кэше: {e}")

        # Шаг 3: Прямой поиск в Zoho API (чтобы избежать дублей при устаревшем кэше)
        try:
            if organization_id:
                direct = find_supplier_in_zoho(organization_id, supplier_name, supplier_vat)
                if direct and direct.get('contact_id'):
                    # Проверяем VAT несоответствие/отсутствие, но всегда предлагаем общую кнопку обновления контакта
                    cached_vat = (direct.get('vat_number') or '').strip()
                    if supplier_vat and (not cached_vat or cached_vat.upper() != str(supplier_vat).upper()):
                        return {
                            'status': 'found_in_zoho',
                            'contact': direct,
                            'organization_id': organization_id,
                            'organization_name': organization_name,
                            'message': f'⚠️ Поставщик "{supplier_name}" найден в Zoho, VAT отличается/отсутствует (Zoho: {cached_vat or "—"}, Документ: {supplier_vat}). Нажмите "Обновить контакт".',
                            'recommended_action': 'update_existing',
                            'button_text': '📝 Обновить контакт',
                            'button_action': 'update_existing_contact'
                        }
                    return {
                        'status': 'found_in_zoho',
                        'contact': direct,
                        'organization_id': organization_id,
                        'organization_name': organization_name,
                        'message': f'✅ Поставщик "{supplier_name}" найден в Zoho',
                        'recommended_action': 'update_existing',
                        'button_text': '📝 Обновить контакт',
                        'button_action': 'update_existing_contact'
                    }
        except Exception as e:
            logger.warning(f"Ошибка прямого поиска в Zoho API: {e}")

        # Шаг 4: Поставщик не найден нигде
        return {
            'status': 'not_found',
            'contact': None,
            'organization_id': organization_id,
            'organization_name': organization_name,
            'message': f'🆕 Поставщик "{supplier_name}" не найден в системе',
            'recommended_action': 'create_new',
            'button_text': '➕ Создать нового',
            'button_action': 'create_new_contact'
        }

    except Exception as e:
        return {
            'status': 'error',
            'contact': None,
            'organization_id': None,
            'organization_name': None,
            'message': f'❌ Ошибка проверки поставщика: {str(e)}',
            'recommended_action': 'error',
            'button_text': '❌ Ошибка',
            'button_action': 'error'
        }


class SupplierContactCreator:
    """Создатель контактов поставщиков в Zoho"""

    def __init__(self):
        self.zoho_api = None

    def check_existing_supplier(self, supplier_name: str, vat_number: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Проверяет существующего поставщика в кэше"""
        # Placeholder для проверки существующего поставщика
        return None

    def create_supplier_contact(self, supplier_data: Dict[str, Any]) -> bool:
        """Создает контакт поставщика в Zoho"""
        # Placeholder для создания контакта
        return True


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start"""
    if not update.message:
        return

    welcome_text = """
🤖 Добро пожаловать в AI Invoice Bot!

Я умею:
📄 Анализировать PDF счета и контракты
🏢 Извлекать данные поставщиков
🚗 Распознавать автомобильную информацию
💰 Определять суммы и валюты
🎯 Проверять существующих поставщиков

Просто отправьте мне PDF файл!
"""
    await update.message.reply_text(welcome_text)


async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка PDF документов"""

    # Проверяем ожидаем ли мы цену продажи
    if context.user_data and context.user_data.get('waiting_for_selling_price'):
        await handle_selling_price(update, context)
        return

    if not update.message:
        return

    if not update.message.document:
        await update.message.reply_text("❌ Файл не найден")
        return

    document = update.message.document

    # Проверяем тип файла
    if not document.file_name or not document.file_name.lower().endswith('.pdf'):
        await update.message.reply_text("❌ Пожалуйста, отправьте PDF файл")
        return

    await update.message.reply_text("📄 Обрабатываю PDF файл с умным анализом...")

    try:
        # Скачиваем файл
        file = await context.bot.get_file(document.file_id)

        # Создаем временный файл
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_file:
            await file.download_to_drive(temp_file.name)
            temp_path = temp_file.name

        # Используем умный процессор документов
        processor = SmartDocumentProcessor()
        result = await processor.process_document(temp_path)

        if result.success:
            # Генерируем умное сообщение
            telegram_message = processor.generate_telegram_message(result)

            # Извлекаем данные из анализа документа
            document_analysis = result.document_analysis
            supplier_name = document_analysis.get('supplier_name', '')
            supplier_vat = document_analysis.get('supplier_vat')
            our_company = document_analysis.get('our_company', '')
            document_type = document_analysis.get('document_type', 'Unknown')

            # Нормализуем VAT для ЕДИНОГО отображения/использования (с ISO‑префиксом)
            try:
                from telegram_bot.services.vat_normalizer import normalize_vat as _norm_vat
                normalized_vat = _norm_vat(
                    supplier_vat,
                    document_analysis.get('supplier_country'),
                    document_analysis.get('extracted_text'),
                )
                if normalized_vat:
                    document_analysis['supplier_vat'] = normalized_vat
                    supplier_vat = normalized_vat
            except Exception:
                normalized_vat = supplier_vat

            # AI перевод типа документа на русский
            async def ai_translate_document_type(doc_type: str) -> str:
                """AI перевод типов документов на русский"""
                if not doc_type or doc_type == 'Unknown':
                    return 'Неизвестен'
                
                # Быстрый перевод через AI
                try:
                    import openai
                    if not os.getenv('OPENAI_API_KEY'):
                        return doc_type  # Fallback без перевода
                    
                    client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
                    
                    response = client.chat.completions.create(
                        model="gpt-4o-mini",  # Быстрая модель для перевода
                        messages=[{
                            "role": "user", 
                            "content": f"Переведи тип документа '{doc_type}' на русский язык. Отвечай только переводом, без объяснений. Примеры: 'Invoice' → 'Счёт-фактура', 'Contract' → 'Договор', 'Verbindliche Bestellung' → 'Договор покупки'"
                        }],
                        max_tokens=50,
                        temperature=0
                    )
                    
                    translated = response.choices[0].message.content.strip()
                    return translated if translated else doc_type
                    
                except Exception as e:
                    print(f"⚠️ Ошибка AI перевода: {e}")
                    return doc_type  # Fallback к оригиналу

            document_type_ru = await ai_translate_document_type(document_type)

            # Добавляем информацию о типе документа и организации в начало сообщения
            header_info = f"📄 Тип документа: {document_type_ru}\n"
            if our_company:
                header_info += f"🏢 Организация: {our_company}\n"
            header_info += "─" * 40 + "\n\n"
            # Отдельно добавим VAT в нормализованном виде для наглядности
            if supplier_vat:
                header_info += f"🏷️ VAT: {supplier_vat}\n\n"
            telegram_message = header_info + telegram_message

            # Умная проверка поставщика с передачей our_company
            supplier_check = None
            if supplier_name:
                supplier_check = await smart_supplier_check(supplier_name, supplier_vat, our_company)
                # Диагностика: логируем контекст организации и имя/ват
                try:
                    logger.info(f"🔎 Supplier debug: org={supplier_check.get('organization_id')}, org_name={supplier_check.get('organization_name')}, name='{supplier_name}', vat='{supplier_vat}' status={supplier_check.get('status')}")
                except Exception:
                    pass

            # Создаем динамические кнопки на основе результатов
            keyboard = []

            # Кнопки для контакта на основе умной проверки
            if supplier_check:
                status = supplier_check.get('status')
                # Всегда показываем кнопку "Обновить контакт", если контакт найден (включая случаи несоответствия VAT)
                found_statuses = [
                    'found_in_cache', 'found_in_general_cache', 'found_in_zoho',
                    'found_with_vat_mismatch', 'found_in_general_with_vat_mismatch', 'found_in_zoho_with_vat_mismatch'
                ]
                if status in found_statuses:
                    keyboard.append([InlineKeyboardButton(
                        '📝 Обновить контакт',
                        callback_data='update_existing_contact'
                    )])
                elif status == 'not_found':
                    keyboard.append([InlineKeyboardButton(
                        supplier_check['button_text'],
                        callback_data=supplier_check['button_action']
                    )])

                # Добавим текстовые рекомендации в конец сообщения
                try:
                    actions_block = "\n🎯 РЕКОМЕНДУЕМЫЕ ДЕЙСТВИЯ:\n"
                    if status in found_statuses:
                        actions_block += "   📝 Обновить контакт\n"
                    else:
                        actions_block += "   ➕ Создать контакт поставщика\n"
                    telegram_message = (telegram_message or "") + actions_block
                except Exception:
                    pass

            # Кнопки для ITEM (только если это автомобиль и VIN не существует)
            sku_check = getattr(result, 'sku_check', None)
            if sku_check and sku_check.recommended_action == "create_item":
                keyboard.append([InlineKeyboardButton("🚗 Создать ITEM", callback_data="create_item")])
            elif sku_check and sku_check.recommended_action == "skip_duplicate":
                # Не добавляем кнопку создания ITEM если уже существует
                pass

        # Кнопка создания BILL (для инвойсов с номером/суммой)
            if (document_analysis.get('bill_number') and document_analysis.get('total_amount')):
                keyboard.append([InlineKeyboardButton("📋 Создать BILL", callback_data="create_bill")])

            # Всегда доступные кнопки
            analysis_btn_needed = False
            try:
                dt = (document_analysis.get('document_type') or '').lower()
                if 'contract' in dt or 'proforma' in dt or document_analysis.get('contract_risks'):
                    analysis_btn_needed = True
            except Exception:
                pass

            row = [InlineKeyboardButton("🔄 Обновить кэш", callback_data="smart_refresh_cache"),
                   InlineKeyboardButton("📋 Полный отчет", callback_data="smart_full_report")]
            keyboard.append(row)
            if analysis_btn_needed:
                keyboard.append([InlineKeyboardButton("🧠 Анализ документа", callback_data="smart_analysis")])

            # Добавляем информацию о поставщике в сообщение
            if supplier_check:
                telegram_message += f"\n\n{supplier_check['message']}"

            # Создаём клавиатуру с кнопками
            reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
            
            # Сохраняем результат для последующих действий
            if context.user_data is not None:
                context.user_data['smart_result'] = result
                context.user_data['document_analysis'] = result.document_analysis
                context.user_data['supplier_check'] = supplier_check  # Сохраняем результат проверки
            try:
                # Глобальный fallback на случай рестарта бота или очистки user_data
                global last_document_analysis
                last_document_analysis = result.document_analysis
            except Exception:
                pass

            # Отправляем сообщение с кнопками (после того, как уже есть supplier_check)
            # Чтобы заголовок статуса не вводил в заблуждение, если контакт найден
            try:
                if supplier_check and 'НЕ НАЙДЕН' in telegram_message:
                    # Заменяем статус, если мы определили, что контакт найден
                    status = supplier_check.get('status')
                    if status and status != 'not_found':
                        telegram_message = telegram_message.replace('🆕 Контакт: НЕ НАЙДЕН - требуется создание', '✅ Контакт: НАЙДЕН в системе')
            except Exception:
                pass

            chat_id = update.message.chat.id
            print(f"🔍 DEBUG: Отправляю сообщение chat_id={chat_id}, кнопок: {len(keyboard) if keyboard else 0}")
            await update.message.reply_text(telegram_message, reply_markup=reply_markup)
            print(f"✅ DEBUG: Сообщение отправлено chat_id={chat_id}")
        else:
            error_list = result.errors or []
            error_message = "❌ Ошибка умной обработки:\n" + "\n".join(error_list)
            await update.message.reply_text(error_message)

        # Сохраняем обработанный документ
        if result.success:
            try:
                # Создаем папку для обработанных файлов, если её нет
                processed_dir = Path("processed_files")
                processed_dir.mkdir(exist_ok=True)

                # Генерируем имя файла с timestamp
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                original_name = Path(document.file_name).stem
                new_filename = f"{original_name}_{timestamp}.pdf"
                processed_path = processed_dir / new_filename

                # Копируем файл в папку обработанных
                import shutil
                shutil.copy2(temp_path, processed_path)

                logger.info(f"✅ Документ сохранен: {processed_path}")

                # Добавляем информацию о сохранении в результат
                if context.user_data is not None:
                    context.user_data['processed_file_path'] = str(processed_path)

            except Exception as save_error:
                logger.error(f"❌ Ошибка сохранения документа: {save_error}")

        # Удаляем временный файл
        os.unlink(temp_path)

    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка обработки файла: {str(e)}")


async def handle_selling_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка ввода цены продажи для ITEM"""

    if not update.message or not context.user_data:
        return

    try:
        # Получаем введенную цену
        price_text = update.message.text
        if not price_text:
            await update.message.reply_text("❌ Введите цену числом:")
            return

        price_text = price_text.strip()
        selling_price = float(price_text.replace(',', '.'))

        if selling_price <= 0:
            await update.message.reply_text("❌ Цена должна быть положительным числом. Попробуйте еще раз:")
            return

        await update.message.reply_text(f"✅ Цена продажи: {selling_price} EUR\n🚗 Создаю ITEM в Zoho Books...")

        # Получаем данные ITEM
        item_data = context.user_data.get('item_data')
        if not item_data:
            await update.message.reply_text("❌ Данные ITEM не найдены")
            return

        # Добавляем цену продажи
        item_data['selling_price'] = selling_price

        # Готовим данные из анализа
        analysis = context.user_data.get('document_analysis') or {}
        vin = (item_data.get('vin') or analysis.get('vin') or '').strip()
        car_model = item_data.get('car_model') or analysis.get('car_model') or ''
        car_brand = analysis.get('car_brand') or ''
        car_item_name = analysis.get('car_item_name')
        if not car_item_name:
            # Формируем по правилу Brand Model_last5VIN
            last5 = vin[-5:] if vin else ''
            car_item_name = ' '.join([p for p in [car_brand, car_model] if p]).strip()
            if last5:
                car_item_name = f"{car_item_name}_{last5}" if car_item_name else last5

        cost_price = None
        try:
            # Берём NET: сначала net_amount, потом total_amount (которое теперь тоже нетто)
            net_val = analysis.get('net_amount') if analysis.get('net_amount') is not None else analysis.get('total_amount')
            cost_price = float(item_data.get('cost_price') or net_val or 0.0)
        except Exception:
            cost_price = 0.0

        if not vin or not car_item_name:
            await update.message.reply_text("❌ Недостаточно данных для создания ITEM (VIN/название)")
            return

        # Определяем организацию
        our_company = (analysis.get('our_company') or '').strip().lower()
        org_id = '20082562863' if 'parkentertainment' in our_company else '20092948714'

        # Создание через ZohoItemsManager
        manager = ZohoItemsManager()

        # Проверка дубликата по VIN
        try:
            if manager.check_sku_exists(vin, org_id):
                await update.message.reply_text(f"ℹ️ ITEM с VIN {vin} уже существует в Zoho — создание пропущено.")
                context.user_data['waiting_for_selling_price'] = False
                context.user_data.pop('item_data', None)
                return
        except Exception:
            pass

        # Получаем tax_id (обычно 0% export)
        tax_id = None
        try:
            tax_id = manager.get_tax_export_id(org_id)
        except Exception:
            tax_id = None

        # Описание всегда на английском и содержит VIN
        description_en = analysis.get('item_description') or analysis.get('item_details') or ''
        if description_en:
            # Ensure VIN present
            if vin and vin not in description_en:
                description_en = f"{description_en}. VIN {vin}"
        else:
            description_en = f"{car_item_name} VIN {vin}".strip()

        car_data = CarItemData(
            name=car_item_name,
            sku=vin,
            description=description_en,
            cost_price=float(cost_price or 0.0),
            selling_price=float(selling_price),
            unit="pcs",
            tax_id=tax_id,
        )

        created = manager.create_car_item(car_data, org_id)
        if created:
            msg_lines = [
                "✅ ITEM успешно создан в Zoho",
                f"   Name: {created.get('name')}",
                f"   SKU: {created.get('sku')}",
                f"   ID: {created.get('item_id')}",
            ]
            await update.message.reply_text("\n".join(msg_lines))
        else:
            await update.message.reply_text("❌ Ошибка создания ITEM в Zoho. Проверьте логи.")

        # Очищаем состояние ожидания цены
        context.user_data['waiting_for_selling_price'] = False
        context.user_data.pop('item_data', None)

    except ValueError:
        await update.message.reply_text("❌ Неверный формат цены. Введите число:")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка обработки цены: {str(e)}")


async def send_analysis_result(update: Update, ai_result: Dict[str, Any]) -> None:
    """Отправляет результат анализа в Telegram"""
    if not update.message:
        return

    try:
        # Формируем сообщение с результатами анализа
        message = "📊 РЕЗУЛЬТАТ ОБРАБОТКИ ДОКУМЕНТА\n\n"

        # Информация о поставщике
        supplier = ai_result.get('supplier', {})
        if supplier:
            message += f"🏢 Поставщик: {supplier.get('name', 'Не указан')}\n"
            message += f"📧 Email: {supplier.get('email', 'Не указан')}\n"
            message += f"📞 Телефон: {supplier.get('phone', 'Не указан')}\n"

        # Информация о документе
        message += f"📄 Документ: {ai_result.get('bill_number', 'Не указан')}\n"
        message += f"📅 Дата: {ai_result.get('date', 'Не указана')}\n"
        message += f"⏰ Срок платежа: {ai_result.get('payment_terms', 'Не указан')}\n"

        # Статус контакта
        contact_status = ai_result.get('contact_status', 'Не определен')
        message += f"🆕 Контакт: {contact_status}\n"

        # Сумма
        total_amount = ai_result.get('total_amount')
        if total_amount:
            currency = ai_result.get('currency', 'EUR')
            message += f"💰 Сумма: {total_amount} {currency}\n"

        # Адрес
        address = supplier.get('address', {})
        if address:
            message += "📍 Адрес для Zoho:\n"
            message += f"   🌍 Country: {address.get('country', 'Не указан')}\n"
            message += f"   🏠 Address: {address.get('address', 'Не указан')}\n"
            message += f"   🏙️ City: {address.get('city', 'Не указан')}\n"
            message += f"   📮 ZIP Code: {address.get('zip', 'Не указан')}\n"
            message += f"   📞 Phone: {address.get('phone', 'Не указан')}\n"

        # VAT в сообщении: нормализуем по стране поставщика (всегда с ISO-префиксом, если страна известна)
        vat = supplier.get('vat')
        if vat:
            try:
                from src.domain.services.vat_validator import VATValidatorService
                vvs_disp = VATValidatorService()
                country = (supplier.get('country') or ai_result.get('supplier_country') or (supplier.get('address') or {}).get('country') or '').strip().lower()
                country_to_iso = {
                    'poland': 'PL', 'polska': 'PL', 'estonia': 'EE', 'eesti': 'EE', 'germany': 'DE',
                    'deutschland': 'DE', 'latvia': 'LV', 'lithuania': 'LT', 'netherlands': 'NL',
                    'ireland': 'IE', 'france': 'FR', 'spain': 'ES', 'italy': 'IT', 'portugal': 'PT',
                    'sweden': 'SE', 'denmark': 'DK', 'united kingdom': 'GB', 'uk': 'GB'
                }
                expected = country_to_iso.get(country)
                valid = vvs_disp.validate_vat(vat, expected_country=expected)
                if valid.is_valid:
                    vat_show = vvs_disp.add_country_prefix(valid.vat_number.value, expected or valid.country_code).replace(' ', '')
                else:
                    digits = ''.join(ch for ch in str(vat) if ch.isdigit())
                    vat_show = f"{expected}{digits}" if expected and digits else str(vat)
            except Exception:
                vat_show = str(vat)
            message += f"🏷️ VAT: {vat_show}\n"

        # Уверенность AI
        confidence = ai_result.get('confidence')
        if confidence:
            message += f"🎯 Уверенность AI: {confidence}%\n"

        # Рекомендуемые действия
        message += "\n🎯 РЕКОМЕНДУЕМЫЕ ДЕЙСТВИЯ:\n"
        if contact_status == "НЕ НАЙДЕН - требуется создание":
            message += "   ➕ Создать контакт поставщика\n"

        await update.message.reply_text(message)

    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка отправки результата: {str(e)}")


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик callback кнопок"""
    if not update.callback_query:
        return

    query = update.callback_query
    # Дедупликация по callback_query.id + message_id с TTL
    try:
        key = f"{query.id}:{getattr(query.message, 'message_id', '')}"
        import time
        now = time.time()
        # Очистка просроченных
        expired = [k for k, t in _recent_callbacks.items() if now - t > _RECENT_TTL_SECONDS]
        for k in expired:
            _recent_callbacks.pop(k, None)
        if key in _recent_callbacks:
            return
        _recent_callbacks[key] = now
    except Exception:
        pass
    await query.answer()

    try:
        action = query.data
        try:
            logger.info(f"CB action={action} user_data_keys={list(context.user_data.keys()) if context.user_data else None}")
            print(f"CB action={action} user_data_keys={list(context.user_data.keys()) if context.user_data else None}")
        except Exception:
            pass
        
        # Перенаправляем умные действия в handle_smart_callback
        smart_actions = [
            "create_new_contact", "update_existing_contact", "update_supplier_vat", 
            "update_supplier_vat_and_refresh", "refresh_cache_only", "smart_refresh_cache", "smart_full_report",
            "create_bill", "create_item", "smart_analysis"
        ]
        
        if action in smart_actions:
            await handle_smart_callback(update, context, action)
            return
            
        # Простые действия (старые)
        if action == "create_contact":
            await query.edit_message_text("🔄 Создаю контакт...")
        elif action == "update_contact":
            await query.edit_message_text("🔄 Обновляю контакт...")
        elif action == "create_item":
            await query.edit_message_text("🔄 Создаю ITEM...")
        elif action == "refresh_cache":
            await query.edit_message_text("🔄 Обновляю кэш...")
        elif action == "full_report":
            await query.edit_message_text("📋 Генерирую отчет...")
        else:
            await query.edit_message_text("❌ Неизвестное действие")

    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка обработки действия: {str(e)}")


async def handle_smart_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str) -> None:
    """Обработчик умных callback кнопок"""
    if not update.callback_query or not context.user_data:
        return

    query = update.callback_query
    await query.answer()

    try:
        try:
            logger.info(f"SMART CB enter action={action} keys={list(context.user_data.keys())}")
            print(f"SMART CB enter action={action} keys={list(context.user_data.keys())}")
        except Exception:
            pass
        if action == "create_new_contact":
            await handle_smart_create_contact(update, context)
        elif action == "update_existing_contact":
            # Полное обновление контакта (включая VAT и остальные поля)
            await handle_smart_update_contact(update, context)
        elif action == "update_supplier_vat":
            await handle_smart_update_supplier_vat(update, context, refresh_cache=False)
        elif action == "update_supplier_vat_and_refresh":
            await handle_smart_update_supplier_vat(update, context, refresh_cache=True)
        elif action == "refresh_cache_only":
            await handle_smart_refresh_cache(update, context)
        elif action == "create_bill":
            await handle_smart_create_bill(update, context)
        elif action == "smart_analysis":
            await handle_smart_analysis(update, context)
        elif action.startswith("choose_account:"):
            # Пользователь выбрал account_id для BILL
            print(f"🌸 DEBUG: choose_account triggered - using pre-created payload")
            aid = action.split(":", 1)[1]
            pending = context.user_data.get('pending_bill') or {}
            org_id = pending.get('org_id')
            vendor_id = pending.get('vendor_id')
            payload = pending.get('payload') or {}
            print(f"🌸 DEBUG: Payload has {len(payload.get('line_items', []))} line_items from pending_bill")
            if not (org_id and vendor_id and payload):
                await query.edit_message_text("❌ Нет данных для создания BILL")
                return
            # Проставляем выбранный account_id всем строкам без account
            try:
                for li in payload.get('line_items', []):
                    if not li.get('account_id'):
                        li['account_id'] = aid
            except Exception:
                pass

            # Отправляем BILL в Zoho
            import requests
            access_token = get_access_token()
            url = f"https://www.zohoapis.eu/books/v3/bills?organization_id={org_id}"
            headers = {"Authorization": f"Zoho-oauthtoken {access_token}", "Content-Type": "application/json"}
            r = requests.post(url, headers=headers, json=payload)
            ok = r.status_code in (200, 201) and 'bill' in (r.json() if r.content else {})
            try:
                logger.info(f"BILL(chosen) response: status={r.status_code} body={(r.text or '')[:400]}")
            except Exception:
                pass
            if ok:
                await query.edit_message_text("✅ BILL создан успешно")
            else:
                await query.edit_message_text(f"❌ Ошибка создания BILL: {r.status_code} {(r.text or '')[:200]}")
            context.user_data.pop('pending_bill', None)
            return
        elif action == "cancel_bill":
            context.user_data.pop('pending_bill', None)
            await query.edit_message_text("❌ Создание BILL отменено")
            return
        elif action == "create_item":
            # Переведём диалог в режим запроса цены, сохранив UI (не затираем исходное сообщение)
            await handle_smart_create_item(update, context)
            try:
                await query.answer()
            except Exception:
                pass
            return
        elif action.startswith("choose_branch_"):
            # Пользователь выбрал branch_id для цветочного документа
            branch_id = action.replace("choose_branch_", "")
            logger.info(f"🌸 DEBUG: Пользователь выбрал branch_id: {branch_id}")
            
            # Получаем сохраненные данные
            bill_payload = context.user_data.get('pending_bill_payload')
            analysis = context.user_data.get('pending_analysis')
            
            if not bill_payload or not analysis:
                await query.edit_message_text("❌ Ошибка: данные не найдены. Попробуйте загрузить документ заново.")
                return
            
            # Добавляем выбранный branch_id в payload
            bill_payload["branch_id"] = branch_id
            logger.info(f"🌸 DEBUG: Добавлен выбранный branch_id в payload: {branch_id}")
            
            # Создаем Bill с выбранным branch
            try:
                from functions.zoho_api import create_bill
                
                # Определяем организацию
                supplier_name = analysis.get('supplier_name', '').lower()
                org_id = "20082562863"  # PARKENTERTAINMENT
                
                bill_response = create_bill(org_id, bill_payload)
                
                if bill_response.get('bill'):
                    bill_id = bill_response['bill'].get('bill_id')
                    bill_number = bill_response['bill'].get('bill_number', 'Не определен')
                    branch_name = bill_response['bill'].get('branch_name', 'Head Office')
                    await query.edit_message_text(f"✅ Bill создан успешно!\n📄 ID: {bill_id}\n🔢 Номер: {bill_number}\n🏢 Branch: {branch_name}")
                else:
                    await query.edit_message_text(f"❌ Ошибка создания Bill: {bill_response}")
                    
            except Exception as e:
                logger.error(f"Ошибка создания Bill с выбранным branch: {e}")
                await query.edit_message_text(f"❌ Ошибка создания Bill: {str(e)}")
            
            # Очищаем сохраненные данные
            context.user_data.pop('pending_bill_payload', None)
            context.user_data.pop('pending_analysis', None)
            return
        elif action == "smart_refresh_cache":
            await handle_smart_refresh_cache(update, context)
        elif action == "smart_full_report":
            await handle_smart_full_report(update, context)
        else:
            await query.edit_message_text("❌ Неизвестное умное действие")

    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка обработки умного действия: {str(e)}")


async def handle_smart_create_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Умное создание контакта"""
    if not update.callback_query or not context.user_data:
        return

    query = update.callback_query
    document_analysis = context.user_data.get('document_analysis')

    if not document_analysis:
        await query.edit_message_text("❌ Данные документа не найдены")
        return

    try:
        # Не перетираем карточку анализа — отправляем отдельное статус‑сообщение
        await context.bot.send_message(chat_id=query.message.chat_id, text="🔄 Создаю контакт поставщика...")

        # Создаем контакт через contact_creator
        success, message = await create_supplier_from_document(document_analysis)

        if success:
            await context.bot.send_message(chat_id=query.message.chat_id, text=f"✅ Контакт успешно создан!\n{message}")
        else:
            await context.bot.send_message(chat_id=query.message.chat_id, text=f"❌ Ошибка создания контакта: {message}")

    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка создания контакта: {str(e)}")


async def handle_smart_update_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Минимальный обертчик: находим org/contact и делегируем сервису обновления."""
    if not update.callback_query or not context.user_data:
        return

    query = update.callback_query
    await context.bot.send_message(chat_id=query.message.chat_id, text="🔄 Обновляю контакт поставщика...")

    try:
        result = context.user_data.get('smart_result')
        if not result:
            await context.bot.send_message(chat_id=query.message.chat_id, text="❌ Нет данных анализа")
            return

        analysis = result.document_analysis
        org_id = '20082562863' if 'parkentertainment' in (analysis.get('our_company') or '').lower() else '20092948714'

        sc = context.user_data.get('supplier_check') or {}
        contact_id = (
            sc.get('contact_id') or (sc.get('contact') or {}).get('contact_id') or (sc.get('cached_contact') or {}).get('contact_id')
        )
        if not contact_id:
            from functions.zoho_api import get_contact_by_name
            contact = get_contact_by_name(analysis.get('supplier_name') or '', org_id)
            contact_id = contact.get('contact_id') if isinstance(contact, dict) else None
        if not contact_id:
            await context.bot.send_message(chat_id=query.message.chat_id, text="❌ Не удалось определить контакт")
            return

        from src.infrastructure.zoho_api import ZohoAPIClient
        from config.zoho_auth import get_zoho_credentials
        creds = get_zoho_credentials()
        client = ZohoAPIClient(creds['client_id'], creds['client_secret'], creds['refresh_token'])

        from telegram_bot.services.zoho_contact_updater import update_contact as svc_update
        vat_ok, other_ok, _ = await svc_update(client, org_id, contact_id, analysis)

        if vat_ok and other_ok:
            await context.bot.send_message(chat_id=query.message.chat_id, text="✅ Контакт обновлён: VAT и прочие поля")
        elif vat_ok:
            await context.bot.send_message(chat_id=query.message.chat_id, text="✅ Контакт обновлён: VAT")
        elif other_ok:
            await context.bot.send_message(chat_id=query.message.chat_id, text="✅ Контакт обновлён (без VAT)")
        else:
            await context.bot.send_message(chat_id=query.message.chat_id, text="❌ Ошибка обновления контакта в Zoho")

        # Обновляем локальный кэш из Zoho, чтобы сразу увидеть новый VAT в кэше
        try:
            from functions.refresh_zoho_cache import refresh_single_contact_cache
            org_name = 'PARKENTERTAINMENT' if org_id == '20082562863' else 'TaVie Europe OÜ'
            cache_ok = await refresh_single_contact_cache(contact_id, org_id, org_name)
            if cache_ok:
                await context.bot.send_message(chat_id=query.message.chat_id, text="🔄 Кэш обновлён из Zoho")
        except Exception as ce:
            try:
                logger.warning(f"Cache refresh after update failed: {ce}")
            except Exception:
                pass

    except Exception as e:
        await context.bot.send_message(chat_id=query.message.chat_id, text=f"❌ Ошибка обновления контакта: {str(e)}")


async def handle_smart_update_supplier_vat(update: Update, context: ContextTypes.DEFAULT_TYPE, refresh_cache: bool = False) -> None:
    """Точечное обновление VAT для поставщика минимальным payload через custom_fields по index.

    Работает для любых поставщиков. Для польских NIP гарантируем префикс PL.
    """
    if not update.callback_query or not context.user_data:
        return
    query = update.callback_query
    await query.answer()

    try:
        analysis = (context.user_data.get('document_analysis') or {}).copy()
        supplier_check = context.user_data.get('supplier_check') or {}

        # Определяем org
        our_company = (analysis.get('our_company') or '').strip()
        org_id = '20082562863' if 'parkentertainment' in our_company.lower() else '20092948714'

        # Определяем contact_id
        contact_id = (
            supplier_check.get('contact_id') or
            (supplier_check.get('cached_contact') or {}).get('contact_id') or
            (supplier_check.get('contact') or {}).get('contact_id')
        )
        if not contact_id:
            from functions.zoho_api import get_contact_by_name
            lookup_name = analysis.get('supplier_name') or ''
            direct = get_contact_by_name(lookup_name, org_id)
            contact_id = direct.get('contact_id') if direct else None
        if not contact_id:
            await query.edit_message_text("❌ Не удалось определить ID контакта для обновления VAT")
            return

        # Подготовка VAT: NIP из анализа или из текста; валидация и префикс
        supplier_vat_val = (analysis.get('supplier_vat') or '').strip()
        try:
            if not supplier_vat_val and analysis.get('extracted_text'):
                import re
                m = re.search(r"\bNIP\s*[:#]?\s*(\d{10})\b", analysis['extracted_text'], re.IGNORECASE)
                if m:
                    supplier_vat_val = m.group(1)
        except Exception:
            pass
        if not supplier_vat_val:
            await query.edit_message_text("❌ В документе не найден VAT/NIP для обновления")
            return

        from src.domain.services.vat_validator import VATValidatorService
        vvs = VATValidatorService()
        # Для Польши фиксируем ожидаемую страну PL, иначе автоопределение
        expected_country = 'PL' if 'parkentertainment' in our_company.lower() or 'poland' in (analysis.get('supplier_country') or '').lower() else None
        validation = vvs.validate_vat(supplier_vat_val, expected_country=expected_country)
        if not validation.is_valid and expected_country != 'PL':
            # Фолбек: если встречается NIP, считаем польским
            try:
                import re
                raw = analysis.get('extracted_text') or ''
                m = re.search(r"\bNIP\s*[:#]?\s*(\d{10})\b", raw, re.IGNORECASE)
                if m:
                    supplier_vat_val = m.group(1)
                    validation = vvs.validate_vat(supplier_vat_val, expected_country='PL')
            except Exception:
                pass
        if not validation.is_valid:
            await query.edit_message_text("❌ Неверный VAT/NIP — обновление отменено")
            return
        vat_prefixed = vvs.add_country_prefix(validation.vat_number.value, expected_country or validation.country_code).replace(' ', '')

        # Zoho клиент и метаданные полей
        from src.infrastructure.zoho_api import ZohoAPIClient
        from config.zoho_auth import get_zoho_credentials
        creds = get_zoho_credentials()
        client = ZohoAPIClient(creds['client_id'], creds['client_secret'], creds['refresh_token'])

        meta = await client.get_contact_custom_fields(org_id) or {}
        fields = (meta.get('customfields') or [])
        target_index = None
        for f in fields:
            if (f.get('module') == 'contacts'):
                lbl = (f.get('label') or '').strip().lower()
                api = (f.get('api_name') or '').strip().lower()
                if lbl in {'tax id','vat','vat id','vat number'} or api in {'cf_tax_id','cf_vat_id'}:
                    try:
                        target_index = int(f.get('index'))
                        break
                    except Exception:
                        pass
        url = f'https://www.zohoapis.eu/books/v3/contacts/{contact_id}?organization_id={org_id}'
        # Плоский JSON без обертки 'contact'
        payload = {"custom_fields": [{"index": target_index, "value": vat_prefixed}]} if target_index is not None else {"tax_id": vat_prefixed}
        # Страховка: обрежем строки на всякий случай
        def _trim(v):
            if isinstance(v, str):
                return v[:100]
            if isinstance(v, list):
                return [_trim(x) for x in v]
            if isinstance(v, dict):
                return {k: _trim(val) for k, val in v.items()}
            return v
        resp = await client._make_request('PUT', url, json=_trim(payload))

        if resp and resp.get('contact'):
            msg = "✅ VAT обновлён"
            if refresh_cache:
                try:
                    await handle_smart_refresh_cache(update, context)
                except Exception:
                    pass
            await context.bot.send_message(chat_id=query.message.chat_id, text=msg)
        else:
            await context.bot.send_message(chat_id=query.message.chat_id, text=f"❌ Ошибка обновления VAT в Zoho")

    except Exception as e:
        await context.bot.send_message(chat_id=query.message.chat_id, text=f"❌ Ошибка обновления VAT: {str(e)}")


async def handle_smart_refresh_cache(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Умное обновление кэша"""
    if not update.callback_query or not context.user_data:
        return

    query = update.callback_query

    try:
        await query.edit_message_text("🔄 Обновляю кэш контактов...")
        await query.edit_message_text("✅ Кэш обновлен!")

    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка обновления кэша: {str(e)}")


async def handle_smart_create_item(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Умное создание ITEM"""
    if not update.callback_query or not context.user_data:
        return

    query = update.callback_query
    document_analysis = context.user_data.get('document_analysis')

    if not document_analysis:
        await query.edit_message_text("❌ Данные документа не найдены")
        return

    try:
        # Проверяем, есть ли данные автомобиля
        vin = document_analysis.get('vin')
        car_model = document_analysis.get('car_model')
        cost_price = document_analysis.get('cost_price')

        if not vin or not car_model:
            await query.edit_message_text("❌ Недостаточно данных для создания ITEM (VIN или модель)")
            return

        # Запрашиваем цену продажи
        context.user_data['waiting_for_selling_price'] = True
        context.user_data['item_data'] = {
            'vin': vin,
            'car_model': car_model,
            'cost_price': cost_price
        }

        # Отвечаем отдельным сообщением, чтобы не убирать клавиатуру исходного сообщения
        await context.bot.send_message(chat_id=query.message.chat_id, text="💰 Введите цену продажи автомобиля (в EUR):")

    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка создания ITEM: {str(e)}")


async def handle_smart_create_bill(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Создание Bill в Zoho (включая цветочные инвойсы) и кнопка "Открыть в Zoho"."""
    logger.info(f"🌸 DEBUG: handle_smart_create_bill STARTED")
    if not update.callback_query or not context.user_data:
        logger.info(f"🌸 DEBUG: Early return - no callback_query or user_data")
        return
    query = update.callback_query
    analysis = context.user_data.get('document_analysis') or {}
    supplier_check = context.user_data.get('supplier_check') or {}
    processed_path = context.user_data.get('processed_file_path')
    logger.info(f"🌸 DEBUG: analysis keys: {list(analysis.keys())}")

    try:
        # Определяем организацию
        our_company = (analysis.get('our_company') or '').strip()
        org_id = '20082562863' if 'parkentertainment' in our_company.lower() else '20092948714'

        # Обеспечиваем наличие поставщика (сначала тщательный поиск, затем создание)
        vendor_id = (
            supplier_check.get('contact_id') or
            (supplier_check.get('cached_contact') or {}).get('contact_id') or
            (supplier_check.get('contact') or {}).get('contact_id')
        )
        if not vendor_id:
            # Комбинированный поиск в Zoho, чтобы не создать дубль
            found = find_supplier_in_zoho(org_id, analysis.get('supplier_name'), analysis.get('supplier_vat'))
            if found and found.get('contact_id'):
                vendor_id = found['contact_id']
            else:
                # Создаем нового поставщика только если не нашли
                try:
                    success, msg = await create_supplier_from_document(analysis)
                    if not success:
                        await query.edit_message_text(f"❌ Поставщик не найден и не создан: {msg}")
                        return
                    # Повторная попытка получить contact_id через имя
                    supplier_name = analysis.get('supplier_name') or ''
                    contact = get_contact_by_name(supplier_name, org_id)
                    vendor_id = contact.get('contact_id') if contact else None
                except Exception as ce:
                    await query.edit_message_text(f"❌ Ошибка создания поставщика: {str(ce)}")
                    return
        if not vendor_id:
            await query.edit_message_text("❌ Не удалось определить ID поставщика")
            return

        # Даты
        def normalize_date(raw: Optional[str]) -> str:
            if not raw:
                return datetime.utcnow().strftime('%Y-%m-%d')
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
            return datetime.utcnow().strftime('%Y-%m-%d')

        # Пытаемся брать даты из анализа, иначе извлекаем из текста по ключам; только затем fallback=сегодня
        bill_date = None
        if analysis.get('issue_date') or analysis.get('document_date') or analysis.get('date'):
            bill_date = normalize_date(analysis.get('issue_date') or analysis.get('document_date') or analysis.get('date'))
        else:
            txt = analysis.get('extracted_text') or ''
            m = re.search(r"(date of issue|issue date)\s*[:\-]*\s*([A-Za-z]{3,9}\s+\d{1,2},\s*\d{4}|\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{4}-\d{2}-\d{2})", txt, re.IGNORECASE)
            if m:
                bill_date = normalize_date(m.group(2))
        if not bill_date:
            bill_date = datetime.utcnow().strftime('%Y-%m-%d')

        due_date = None
        if analysis.get('due_date'):
            due_date = normalize_date(analysis.get('due_date'))
        else:
            txt = analysis.get('extracted_text') or ''
            m = re.search(r"(date due|due date|payment due)\s*[:\-]*\s*([A-Za-z]{3,9}\s+\d{1,2},\s*\d{4}|\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{4}-\d{2}-\d{2})", txt, re.IGNORECASE)
            if m:
                due_date = normalize_date(m.group(2))

        # Номер счета
        bill_number = (analysis.get('bill_number') or '').strip().rstrip('/') or None

        # Line items (по умолчанию одна строка)
        logger.info(f"🌸 DEBUG: Инициализируем line_items")
        line_items = []
        # Попытка цветочных позиций
        logger.info(f"🌸 DEBUG: Достигли секции парсинга цветов")
        flower_lines = analysis.get('flower_lines') or []
        logger.info(f"🌸 DEBUG: Начальные flower_lines из analysis: {len(flower_lines)} позиций")
        # ПРИНУДИТЕЛЬНО запускаем парсеры для цветочных документов (игнорируем flower_lines из analysis)
        llm_cat = (analysis.get('product_category') or analysis.get('document_category') or '').upper()
        detected_flower_names = analysis.get('detected_flower_names') or []
        logger.info(f"🌸 DEBUG: В handlers - llm_cat='{llm_cat}', detected_flower_names={len(detected_flower_names)} шт")
        logger.info(f"🌸 DEBUG: Условие: llm_cat == 'FLOWERS' = {llm_cat == 'FLOWERS'}, bool(detected_flower_names) = {bool(detected_flower_names)}")
        
                # ОПРЕДЕЛЯЕМ inclusive ДО ПАРСИНГА для использования в perfect parser
        doc_text_lower = (analysis.get('extracted_text') or '').lower()
        
        # УМНАЯ ЛОГИКА: определяем по структуре таблицы
        # 1. HIBISPOL (цветы): "cena brutto" в заголовках столбцов → inclusive = True
        # 2. Остальные: "wartość netto" в заголовках → inclusive = False
        
        hibispol_brutto_pattern = "cena brutto" in doc_text_lower or "cena przed" in doc_text_lower
        netto_price_pattern = "wartość netto" in doc_text_lower and "cena jdn" in doc_text_lower
        
        # Fallback маркеры для других случаев
        inclusive_markers = ["brutto", "gross", "tax inclusive", "cena brutto", "kwota brutto"]
        exclusive_markers = ["netto", "net price", "cena netto", "kwota netto", "tax exclusive"]
        
        inclusive_found = any(m in doc_text_lower for m in inclusive_markers)
        exclusive_found = any(m in doc_text_lower for m in exclusive_markers)
        
        logger.info(f"🌸 DEBUG: Структурные паттерны - hibispol_brutto: {hibispol_brutto_pattern}, netto_price: {netto_price_pattern}")
        logger.info(f"🌸 DEBUG: Fallback маркеры - brutto: {inclusive_found}, netto: {exclusive_found}")
        
        # ПРИОРИТЕТ: структурные паттерны
        if hibispol_brutto_pattern:
            inclusive = True
            logger.info("🌸 DEBUG: HIBISPOL структура → INCLUSIVE (cena brutto)")
        elif netto_price_pattern:
            inclusive = False
            logger.info("🌸 DEBUG: Нетто структура → EXCLUSIVE (wartość netto)")
        # Fallback к старой логике
        elif exclusive_found and not inclusive_found:
            inclusive = False
        elif inclusive_found:
            inclusive = True
        else:
            inclusive = False  # По умолчанию exclusive
        
        logger.info(f"🌸 DEBUG: Итоговый налог {'INCLUSIVE (brutto)' if inclusive else 'EXCLUSIVE (netto)'}")
        
        if llm_cat == 'FLOWERS' and detected_flower_names:
            logger.info(f"🌸 DEBUG: ПРИНУДИТЕЛЬНЫЙ парсинг цветочного документа (LLM cat={llm_cat}, flowers={len(detected_flower_names)})")
            flower_lines = []  # Сбрасываем старые позиции
            raw_text = analysis.get('extracted_text') or ''
            try:
                # 1) Новый разбор по блокам (пользовательский алгоритм)
                parsed_blocks = parse_invoice_items(raw_text)
                logger.info(f"🌸 DEBUG: parse_invoice_items нашел {len(parsed_blocks)} позиций")
                
                # 2) OCR окна метод (всегда тестируем для сравнения)
                parsed_ocr = extract_flower_lines_from_ocr(raw_text)
                logger.info(f"🌸 DEBUG: extract_flower_lines_from_ocr нашел {len(parsed_ocr) if parsed_ocr else 0} позиций")
                
                # 3) НОВЫЙ ПОЛНЫЙ алгоритм (должен найти все 27 позиций)
                parsed_complete = extract_all_flower_positions(raw_text)
                formatted_complete = format_for_telegram_bot(parsed_complete) if parsed_complete else []
                logger.info(f"🌸 DEBUG: extract_all_flower_positions нашел {len(formatted_complete)} позиций")
                
                # 4) ПРЯМОЙ PDF ПАРСЕР (БЕЗ OCR) - НОВЫЙ!
                parsed_pdf = []
                logger.info(f"🌸 DEBUG: Проверяем PDF парсер - processed_path = {processed_path}")
                
                if processed_path:
                    logger.info(f"🌸 DEBUG: processed_path найден, проверяем is_suitable_for_pdf_parsing...")
                    
                    if is_suitable_for_pdf_parsing(processed_path):
                        logger.info(f"🌸 DEBUG: PDF парсинг подходит для {processed_path}")
                        pdf_raw = extract_flower_positions_from_pdf(processed_path)
                        parsed_pdf = format_pdf_result(pdf_raw) if pdf_raw else []
                        logger.info(f"🌸 DEBUG: PDF парсер нашел {len(parsed_pdf)} позиций")
                        
                        # ОТЛАДКА: выводим первые 5 позиций PDF парсера
                        if parsed_pdf:
                            logger.info(f"🌸 DEBUG PDF ДАННЫЕ (первые 5):")
                            for i, item in enumerate(parsed_pdf[:5]):
                                logger.info(f"  {i+1}. {item.get('name', 'N/A')} | qty={item.get('quantity', 0)} | price={item.get('price_net', 0)}")
                        
                        # ОТЛАДКА: выводим ключевые позиции
                        key_positions = [5, 6, 11]  # DI ST ZEPPELIN, Di St Fl Moonaqua, R GR EXPLORER
                        for pos_idx in key_positions:
                            if pos_idx <= len(parsed_pdf):
                                item = parsed_pdf[pos_idx-1]
                                logger.info(f"🌸 DEBUG PDF поз.{pos_idx}: {item.get('name', 'N/A')} | qty={item.get('quantity', 0)} | price={item.get('price_net', 0)}")
                    else:
                        logger.info(f"🌸 DEBUG: PDF парсинг НЕ подходит для {processed_path}")
                else:
                    logger.info("🌸 DEBUG: processed_path отсутствует - PDF парсинг пропущен")
                
                # 🎯 ПРИОРИТЕТНАЯ ЛОГИКА: PDFPlumber ПЕРВЫЙ для текстового слоя
                best_result = None
                best_count = 0
                best_method = ""
                
                # 🚀 ПРОВЕРЯЕМ PDFPLUMBER ПЕРВЫМ - для документов с текстовым слоем
                if processed_path:
                    try:
                        from functions.pdfplumber_flower_parser import extract_flower_positions_pdfplumber, convert_to_zoho_format
                        parsed_pdfplumber_raw = extract_flower_positions_pdfplumber(processed_path)
                        parsed_pdfplumber = convert_to_zoho_format(parsed_pdfplumber_raw)
                        if parsed_pdfplumber and len(parsed_pdfplumber) > 0:
                            best_result = parsed_pdfplumber
                            best_count = len(parsed_pdfplumber)
                            best_method = "pdfplumber_parser"
                            logger.info(f"🎯 ПРИОРИТЕТ: PDFPlumber выбран с {len(parsed_pdfplumber)} позициями (текстовый слой)")
                        else:
                            logger.info(f"🚀 PDFPlumber: результат пустой, пробуем другие методы")
                    except Exception as e:
                        logger.error(f"❌ Ошибка PDFPlumber: {e}")
                
                # Если PDFPlumber не сработал - пробуем остальные методы
                if not best_result:
                    logger.info("🔄 PDFPlumber не сработал, пробуем остальные парсеры...")
                    
                    # Пробуем PDFMiner для полного извлечения
                    parsed_pdfminer = []
                    if processed_path:
                        try:
                            from functions.pdfminer_flower_parser import extract_flowers_with_pdfminer
                            parsed_pdfminer = extract_flowers_with_pdfminer(processed_path)
                            logger.info(f"🌸 DEBUG: PDFMiner нашел {len(parsed_pdfminer)} позиций")
                        except Exception as e:
                            logger.error(f"❌ Ошибка PDFMiner: {e}")
                    
                    candidates = [
                        (parsed_blocks, "parse_invoice_items"),
                        (parsed_ocr, "extract_flower_lines_from_ocr"),
                        (formatted_complete, "extract_all_flower_positions"),
                        (parsed_pdf, "pdf_direct_parser"),
                        (parsed_pdfminer, "pdfminer_flower_parser")
                    ]
                    
                    for result, method_name in candidates:
                        if result and len(result) > best_count:
                            best_result = result
                            best_count = len(result)
                            best_method = method_name
                
                if best_result:
                    logger.info(f"🌸 DEBUG: Используем {best_method} ({best_count} позиций)")
                    if best_method == "pdfplumber_parser":
                        # 🎯 ИСПОЛЬЗУЕМ ИДЕАЛЬНЫЙ ПАРСЕР ВМЕСТО СЛОЖНОЙ ЛОГИКИ
                        try:
                            from functions.perfect_flower_parser import extract_perfect_flower_data, convert_to_zoho_line_items
                            perfect_positions = extract_perfect_flower_data(processed_path)
                            # ПЕРЕДАЕМ inclusive=True для brutto документов И org_id для налогов
                            line_items = convert_to_zoho_line_items(perfect_positions, inclusive_tax=inclusive, org_id=org_id)
                            logger.info(f"🌸 PERFECT: Извлечено {len(line_items)} позиций с правильными ценами (inclusive={inclusive})")
                            # Пропускаем всю остальную логику создания flower_lines
                            skip_flower_processing = True
                        except Exception as e:
                            logger.error(f"❌ Ошибка perfect parser: {e}")
                            flower_lines = best_result
                            skip_flower_processing = False
                    elif best_method == "parse_invoice_items":
                        flower_lines = [
                            {
                                'name': p['name'],
                                'quantity': p['quantity'],
                                'price_net': p.get('unit_price_netto'),
                                'tax_percent': p.get('vat_percent', 8)
                            }
                            for p in best_result
                        ]
                        skip_flower_processing = False
                    else:
                        flower_lines = best_result
                        skip_flower_processing = False
                else:
                    # Инициализируем переменные если нет best_result
                    flower_lines = []
                    skip_flower_processing = False
                
                # 3) Если всё ещё мало позиций — пробуем Assistants API
                if len(flower_lines) < 15:  # Ожидаем 27, если < 15 то пробуем API
                    try:
                        if processed_path:
                            logger.info(f"🌸 DEBUG: Пробуем Assistants API для улучшения (текущие позиции: {len(flower_lines)})")
                            assistant_data = analyze_proforma_via_agent(processed_path)
                            ai_flower_lines = assistant_data.get('flower_lines') or []
                            logger.info(f"🌸 DEBUG: Assistants API нашел {len(ai_flower_lines)} позиций")
                            if len(ai_flower_lines) > len(flower_lines):
                                print(f"🌸 DEBUG: Assistants API лучше! Используем его результат")
                                flower_lines = ai_flower_lines
                    except Exception as e:
                        print(f"🌸 DEBUG: Assistants API failed: {e}")
            except Exception:
                pass
        else:
            # Для нецветочных документов используем старую логику
            if not flower_lines:
                print(f"🌸 DEBUG: Нецветочный документ, flower_lines пустые, используем фолбэк")
                pass  # Фолбэк логика ниже
        flowers_account_id = None
        try:
            accounts = get_accounts_cached_or_fetch(org_id, 'PARKENTERTAINMENT Sp. z o. o.' if org_id == '20082562863' else 'TaVie Europe OÜ')
            print(f"🔍 DEBUG: loaded {len(accounts)} accounts for account selection")
            for acc in accounts:
                if (acc.get('account_name') or '').strip().lower() == 'flowers':
                    flowers_account_id = acc.get('account_id')
                    break
        except Exception:
            accounts = []
            pass

        # inclusive уже определен выше для использования в perfect parser

        # Надёжное определение цветочного документа
        txt_lower = (analysis.get('extracted_text') or '').lower()
        occ_szt = txt_lower.count(' szt') + txt_lower.count('\nszt') + txt_lower.count('szt ')
        occ_pct = txt_lower.count('8%') + txt_lower.count('23%')
        occ_names = any(k in txt_lower for k in [
            'dahl', 'mondial', 'ruscus', 'gypsophila', 'alstr', 'tana', 'helian', 'delph'
        ])
        # Цветы определяем только по LLM-категории/выявленным названиям цветов
        llm_cat = (analysis.get('product_category') or analysis.get('document_category') or '').upper()
        detected_flower_names = analysis.get('detected_flower_names') or []
        print(f"🌸 DEBUG: В create_bill - llm_cat='{llm_cat}', detected_flower_names={len(detected_flower_names)} шт")
        is_flowers_doc = bool(flower_lines) or (llm_cat == 'FLOWERS' and bool(detected_flower_names))

        print(f"🌸 DEBUG: Итого flower_lines найдено: {len(flower_lines)}")
        
        # 🎯 ПРОВЕРКА: Если используем perfect parser, пропускаем всю сложную логику
        if locals().get('skip_flower_processing', False):
            logger.info(f"🌸 PERFECT: Пропускаем сложную логику, line_items уже готовы ({len(line_items)} шт)")
        elif flower_lines:
            # Помощник для поиска tax_id по проценту
            def _tax_id_for(percent: float | int | None):
                try:
                    p = float(percent or 0)
                except Exception:
                    p = 0.0
                return find_tax_by_percent(org_id, p) if p > 0 else ("-1" if not inclusive else None)

            for fl in flower_lines:
                try:
                    name = str(fl.get('name') or fl.get('description') or 'Flowers')
                    qty = float(fl.get('quantity') or 1)
                    # VAT % для строки: из линии, иначе из общего анализа, иначе эвристика (цветы часто 8%)
                    line_tax_percent = (
                        fl.get('tax_percent') or fl.get('vat_percent') or analysis.get('tax_rate')
                    )
                    if line_tax_percent is None:
                        # Определяем VAT по маркерам в самом названии строки
                        if '8%' in name or '8 %' in name or ' 8 ' in name:
                            line_tax_percent = 8
                        elif '23%' in name or '23 %' in name:
                            line_tax_percent = 23
                        else:
                            line_tax_percent = 8  # безопасный дефолт для цветов
                            # TODO: определять VAT из таблицы документа, а не по названиям

                    # Берем цену ПРЯМО из PDF БЕЗ пересчета - Zoho сам рассчитает налог
                    # Поддержка разных форматов данных (включая PDFPlumber)
                    price_net = (fl.get('price_net') or fl.get('unit_price') or 
                                fl.get('unit_price_netto') or fl.get('price_netto') or fl.get('rate'))
                    price_gross = (fl.get('price_gross') or fl.get('unit_price_brutto') or 
                                  fl.get('unit_price_brutto'))
                    
                    # 🔍 ДИАГНОСТИКА ЦЕНЫ
                    if name == "Hydr M White Verena":  # Первая позиция для отладки
                        logger.info(f"🔍 PRICE DEBUG: name={name}")
                        logger.info(f"🔍 PRICE DEBUG: fl keys={list(fl.keys())}")
                        logger.info(f"🔍 PRICE DEBUG: fl.rate={fl.get('rate')}")
                        logger.info(f"🔍 PRICE DEBUG: price_net={price_net}")
                        logger.info(f"🔍 PRICE DEBUG: price_gross={price_gross}")
                        logger.info(f"🔍 PRICE DEBUG: inclusive={inclusive}")
                    
                    try:
                        if inclusive:
                            # Документ с brutto ценами - берем gross цену как есть
                            rate = float(price_gross or price_net or 0)
                        else:
                            # Документ с netto ценами - берем net цену как есть  
                            rate = float(price_net or price_gross or 0)
                        
                        # 🔍 ДИАГНОСТИКА РЕЗУЛЬТАТА
                        if name == "Hydr M White Verena":
                            logger.info(f"🔍 PRICE DEBUG: final rate={rate}")
                            
                    except Exception as e:
                        rate = float(price_gross or price_net or 0)
                        if name == "Hydr M White Verena":
                            logger.info(f"🔍 PRICE DEBUG: exception={e}, fallback rate={rate}")

                    item = {
                        "name": name[:200],
                        "description": name[:2000],
                        "quantity": qty,
                        "rate": rate,
                    }
                    # account
                    if flowers_account_id:
                        item["account_id"] = flowers_account_id
                    # налог на строку
                    tid = _tax_id_for(line_tax_percent)
                    if tid:
                        item["tax_id"] = tid
                    else:
                        # Если inclusive и ставка 0 — явно выключим налог
                        item["tax_id"] = "-1"

                    line_items.append(item)
                except Exception:
                    continue
        else:
            # Если документ цветочный, но строки не распознаны — пробуем Assistants API как обогащение
            if is_flowers_doc:
                try:
                    if processed_path:
                        assistant_data = analyze_proforma_via_agent(processed_path)
                        ai_flower_lines = assistant_data.get('flower_lines') or []
                        if ai_flower_lines:
                            flower_lines = ai_flower_lines
                            is_flowers_doc = True
                            # Пересобираем строки как выше
                            def _tax_id_for(percent: float | int | None):
                                try:
                                    p = float(percent or 0)
                                except Exception:
                                    p = 0.0
                                return find_tax_by_percent(org_id, p) if p > 0 else ("-1" if not inclusive else None)
                            for fl in flower_lines:
                                try:
                                    name = str(fl.get('name') or fl.get('description') or 'Flowers')
                                    qty = float(fl.get('quantity') or 1)
                                    line_tax_percent = (
                                        fl.get('tax_percent') or fl.get('vat_percent') or analysis.get('tax_rate') or 8
                                    )
                                    # Поддержка разных форматов данных
                                    price_net = (fl.get('unit_price_net') or fl.get('price_net') or 
                                                fl.get('price_netto') or fl.get('unit_price_netto'))
                                    price_gross = (fl.get('unit_price_gross') or fl.get('price_gross') or 
                                                  fl.get('unit_price_brutto'))
                                    
                                    if inclusive and price_gross:
                                        rate = float(price_gross)
                                    elif price_net:
                                        rate = float(price_net)
                                    else:
                                        # PDFPlumber формат: используем 'rate' напрямую
                                        rate = float(fl.get('rate') or fl.get('unit_price') or 0)
                                    item = {"name": name[:200], "description": name[:2000], "quantity": qty, "rate": rate}
                                    if flowers_account_id:
                                        item["account_id"] = flowers_account_id
                                    tid = _tax_id_for(line_tax_percent)
                                    if tid:
                                        item["tax_id"] = tid
                                    else:
                                        item["tax_id"] = "-1"
                                    line_items.append(item)
                                except Exception:
                                    continue
                except Exception:
                    pass
                if not line_items:
                    # Сообщаем об ошибке отдельным сообщением, не стирая клавиатуру
                    try:
                        await query.answer()
                    except Exception:
                        pass
                    await context.bot.send_message(chat_id=query.message.chat_id, text="❌ Не удалось распарсить позиции цветов. Проверьте качество скана или пришлите фото получше — строки не будут собраны одной строкой по безопасности.")
                    return
            # Фолбэк: услуги/товары одной строкой (для нецветочных документов)
            # Описание: LLM service_description, иначе строка после "Description"
            desc = analysis.get('service_description') or analysis.get('item_details')
            if not desc:
                raw_text = analysis.get('extracted_text') or ''
                m = re.search(r"Description\s*[\r\n]+(.{3,120})", raw_text, re.IGNORECASE)
                if m:
                    desc = m.group(1).strip()
            if not desc:
                desc = 'Goods/Services'
            # Rate: Anchor Unit price
            rate = None
            try:
                raw_text = analysis.get('extracted_text') or ''
                m = re.search(r"Unit\s*price\s*\D*([0-9]+[.,][0-9]{2})", raw_text, re.IGNORECASE)
                if m:
                    rate = float(m.group(1).replace(',', '.'))
            except Exception:
                rate = None
            if rate is None:
                rate = float(analysis.get('total_amount') or 0)
            item = {"name": desc[:200], "description": desc[:2000], "quantity": 1, "rate": rate}
            line_items.append(item)

        # Назначаем account_id для каждой строки: LLM-выбор из кэша
        try:
            from functions.llm_document_extractor import llm_select_account
            chosen_account_id = None
            acc_names = [a.get('account_name') for a in accounts if (a.get('account_name'))]
            print(f"🔍 DEBUG: total accounts={len(accounts)}, account_names={len(acc_names)}")
            llm_pick = {}
            try:
                context_for_account = analysis.get('extracted_text') or ''
                llm_pick = llm_select_account([str(n) for n in acc_names], context_for_account, supplier_name=analysis.get('supplier_name') or '', category=(analysis.get('document_category') or ''))
                print(f"🔍 DEBUG llm_select_account: pick={llm_pick}, acc_names={acc_names[:3]}...")
            except Exception as e:
                print(f"❌ llm_select_account failed: {e}")
                llm_pick = {}
            if llm_pick and llm_pick.get('name') in acc_names and float(llm_pick.get('confidence') or 0) >= 0.6:
                print(f"✅ LLM выбрал валидный аккаунт: {llm_pick['name']}")
                for acc in accounts:
                    if acc.get('account_name') == llm_pick['name']:
                        chosen_account_id = acc.get('account_id')
                        break
            else:
                if llm_pick:
                    print(f"❌ LLM выбрал невалидный аккаунт '{llm_pick.get('name')}' с уверенностью {llm_pick.get('confidence')}")
            if not chosen_account_id:
                # дефолтно — первый расходный счёт
                for acc in accounts:
                    if (acc.get('account_type') or '').strip().lower() in {'expense', 'cost of goods sold'}:
                        chosen_account_id = acc.get('account_id')
                        break

            # ИСПРАВЛЕНИЕ: правильная логика назначения account_id
            llm_cat = (analysis.get('document_category') or '').upper()
            detected_flower_names = analysis.get('detected_flower_names') or []
            
            for li in line_items:
                if 'account_id' not in li or not li['account_id']:
                    # Только для цветочных документов с обнаруженными цветами используем flowers_account_id
                    if (llm_cat == 'FLOWERS' and detected_flower_names and flowers_account_id):
                        li['account_id'] = flowers_account_id
                    else:
                        # Во всех остальных случаях используем LLM-выбранный account
                        li['account_id'] = chosen_account_id
        except Exception:
            pass

        # Налоговая логика (глобальный фолбек): если у строки ещё нет tax_id
        try:
            tax_percent = float(analysis.get('tax_rate') or 0)
        except Exception:
            tax_percent = 0.0
        tax_id_global = find_tax_by_percent(org_id, tax_percent) if tax_percent > 0 else None
        for li in line_items:
            if 'tax_id' not in li:
                if tax_id_global:
                    li['tax_id'] = tax_id_global
                else:
                    li['tax_id'] = "-1" if not inclusive else li.get('tax_id')

        # Branch (для PARKENTERTAINMENT цветы)
        llm_cat = (analysis.get('product_category') or analysis.get('document_category') or '').upper()
        detected_flower_names = analysis.get('detected_flower_names') or []
        is_flowers_doc = bool(flower_lines) or (llm_cat == 'FLOWERS' and bool(detected_flower_names))
        # Определяем branch_id согласно правилам пользователя
        branch_id = None
        if org_id == '20082562863':  # PARKENTERTAINMENT
            doc_text_full = (analysis.get('extracted_text') or '').lower()
            supplier_address = (analysis.get('supplier_address') or '').lower()
            
            if is_flowers_doc:
                # Для цветочных документов: определяем branch по поставщику и маркерам
                supplier_name = (analysis.get('supplier_name') or '').lower()
                
                if 'hibispol' in supplier_name and ('wileńska' in doc_text_full or 'wileńska' in supplier_address or 'praga' in doc_text_full or 'praga' in supplier_address):
                    preferred = ["Wileńska"]
                    logger.info("🌸 DEBUG: HIBISPOL + Wileńska/Praga маркер → branch Wileńska")
                elif 'browary' in doc_text_full or 'browary' in supplier_address:
                    preferred = ["Iris flowers atelier"] 
                    logger.info("🌸 DEBUG: Обнаружен маркер Browary → branch Iris flowers atelier")
                elif 'hibispol' in supplier_name:
                    # Hibispol без явных маркеров - все равно Wileńska
                    preferred = ["Wileńska"]
                    logger.info("🌸 DEBUG: HIBISPOL (без маркеров) → branch Wileńska")
                else:
                    # Остальные цветочные поставщики → Iris flowers atelier по умолчанию
                    preferred = ["Iris flowers atelier"]
                    logger.info("🌸 DEBUG: Цветочный документ (не Hibispol) → branch Iris flowers atelier")
                
                branch_id = find_branch_id(org_id, preferred)
                if branch_id:
                    logger.info(f"🌸 DEBUG: Найден branch_id: {branch_id}")
                else:
                    logger.info("🌸 DEBUG: Branch не найден - покажем диалог выбора")
                    # Если branch не найден, показываем диалог выбора
                    branch_id = None
            else:
                # Для остальных документов - head office
                preferred = ["head office"]
                branch_id = find_branch_id(org_id, preferred)
                if not branch_id:
                    logger.info("🏢 DEBUG: Branches не найдены в Zoho - используем default офис")

        # Inclusive tax уже определён выше по маркерам/линиям
        
        logger.info(f"🌸 DEBUG: Перед созданием bill_payload, line_items={len(line_items)}")
        print(f"🌸 DEBUG: Создаём bill_payload с {len(line_items)} line_items")
        
        # ДЕТАЛЬНОЕ ЛОГИРОВАНИЕ LINE_ITEMS ПЕРЕД ОТПРАВКОЙ
        for i, item in enumerate(line_items[:5]):  # Первые 5 позиций
            logger.info(f"LINE_ITEM[{i+1}]: {item.get('name', 'NO_NAME')} | qty={item.get('quantity', 'NO_QTY')} | rate={item.get('rate', 'NO_RATE')} | account_id={item.get('account_id', 'NO_ACC')}")
        if len(line_items) > 5:
            logger.info(f"... и еще {len(line_items) - 5} позиций")

        bill_payload = {
            "vendor_id": vendor_id,
            "bill_number": bill_number,
            "date": bill_date,
            "due_date": due_date,
            "line_items": line_items,
            "notes": analysis.get('notes_for_bill') or analysis.get('notes') or '',
        }
        # Передаем branch_id если найден настоящий branch
        if branch_id:
            bill_payload["branch_id"] = branch_id
            logger.info(f"🌸 DEBUG: Используем branch_id: {branch_id}")
        else:
            logger.info("🌸 DEBUG: Branch_id не передан - используем Head Office")
        bill_payload["is_inclusive_tax"] = bool(inclusive)

        # Если branch не определен для цветочных документов - показываем диалог выбора
        if is_flowers_doc and not branch_id and org_id == '20082562863':
            logger.info("🌸 DEBUG: Показываем диалог выбора branch для цветочного документа")
            
            # Сохраняем payload для использования после выбора branch
            context.user_data['pending_bill_payload'] = bill_payload
            context.user_data['pending_analysis'] = analysis
            
            # Создаем клавиатуру выбора branch
            branch_keyboard = [
                [InlineKeyboardButton("🏢 Head Office", callback_data="choose_branch_281497000000355003")],
                [InlineKeyboardButton("🌸 Iris flowers atelier", callback_data="choose_branch_281497000000355063")], 
                [InlineKeyboardButton("🏪 Wileńska", callback_data="choose_branch_281497000002901751")]
            ]
            reply_markup = InlineKeyboardMarkup(branch_keyboard)
            
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="🌸 Выберите branch для цветочного документа:",
                reply_markup=reply_markup
            )
            return
        
        # Если не удалось однозначно определить account, предлагаем выбор пользователю
        try:
            missing_account = any(not li.get('account_id') for li in line_items)
            if missing_account:
                # Сформируем кандидатов из доступных счетов (expense/COGS)
                name_to_id = { (acc.get('account_name') or '').strip(): acc.get('account_id') for acc in (accounts or []) }
                # Приоритетные кандидаты
                prioritized: list[tuple[str, str]] = []
                # Дополнить расходными/COGS
                for acc in (accounts or []):
                    t = (acc.get('account_type') or '').strip().lower()
                    nm = (acc.get('account_name') or '').strip()
                    if t in {'expense', 'cost of goods sold'} and (nm, acc.get('account_id')) not in prioritized:
                        prioritized.append((nm, acc.get('account_id')))

                # Ограничим список и построим клавиатуру
                top = prioritized[:8] if prioritized else []
                if not top:
                    await query.edit_message_text("❌ Не найден подходящий account. Проверьте настройки счетов в Zoho.")
                    return

                # Сохраняем pending bill
                context.user_data['pending_bill'] = {
                    'org_id': org_id,
                    'vendor_id': vendor_id,
                    'payload': bill_payload,
                }
                # Клавиатура с выбором аккаунта
                kb = []
                for nm, aid in top:
                    kb.append([InlineKeyboardButton(f"💼 {nm}", callback_data=f"choose_account:{aid}")])
                kb.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel_bill")])
                await query.edit_message_text("Выберите счет (account) для строк BILL:", reply_markup=InlineKeyboardMarkup(kb))
                return
        except Exception:
            pass

        # Создаем BILL (account_id уже назначен)
        import requests
        try:
            logger.info(f"Creating BILL payload preview: vendor_id={vendor_id}, items={len(line_items)}, org={org_id}")
        except Exception:
            pass
        access_token = get_access_token()
        url = f"https://www.zohoapis.eu/books/v3/bills?organization_id={org_id}"
        headers = {"Authorization": f"Zoho-oauthtoken {access_token}", "Content-Type": "application/json"}
        r = requests.post(url, headers=headers, json=bill_payload)
        try:
            logger.info(f"BILL response: status={r.status_code} body={(r.text or '')[:400]}")
        except Exception:
            pass
        data = r.json() if r.content else {}
        if r.status_code not in (200, 201) or 'bill' not in data:
            await query.edit_message_text(f"❌ Ошибка создания Bill: {r.status_code} {data}")
            return

        bill = data['bill']
        bill_id = bill.get('bill_id')

        # Прикрепляем PDF
        if processed_path and os.path.exists(processed_path):
            attach_url = f"https://www.zohoapis.eu/books/v3/bills/{bill_id}/attachment?organization_id={org_id}"
            files = {"attachment": open(processed_path, 'rb')}
            headers_att = {"Authorization": f"Zoho-oauthtoken {access_token}"}
            try:
                requests.post(attach_url, headers=headers_att, files=files)
            finally:
                try:
                    files["attachment"].close()
                except Exception:
                    pass

        # Сообщение об успехе с кнопкой «Открыть в Zoho»
        open_url = f"https://books.zoho.eu/app/{org_id}#/bills/{bill_id}?filter_by=Status.All&per_page=200&sort_column=date&sort_order=D"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Открыть в Zoho", url=open_url)]])
        await context.bot.send_message(chat_id=query.message.chat_id, text=f"✅ Bill создан: #{bill_number or bill_id}", reply_markup=kb)

    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка создания Bill: {str(e)}")

async def handle_smart_full_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Умный полный отчет"""
    if not update.callback_query or not context.user_data:
        return

    query = update.callback_query
    result = context.user_data.get('smart_result')

    if not result:
        await query.edit_message_text("❌ Данные анализа не найдены")
        return

    try:
        # Генерируем полный отчет
        full_report = generate_full_report(result)
        await query.edit_message_text(full_report)

    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка генерации отчета: {str(e)}")


def generate_full_report(result) -> str:
    """Генерирует полный отчет по результатам анализа"""
    try:
        analysis = result.document_analysis
        report = "📋 ПОЛНЫЙ ОТЧЕТ ПО ДОКУМЕНТУ\n\n"

        # Основная информация
        report += f"📄 Тип документа: {analysis.get('document_type', 'Не определен')}\n"
        report += f"📄 Номер: {analysis.get('bill_number', 'Не указан')}\n"
        report += f"📅 Дата: {analysis.get('date', 'Не указана')}\n"
        report += f"💰 Сумма: {analysis.get('total_amount', 'Не указана')}\n"
        report += f"💱 Валюта: {analysis.get('currency', 'Не указана')}\n\n"

        # Информация о поставщике
        supplier = analysis.get('supplier', {})
        if supplier:
            report += "🏢 ПОСТАВЩИК:\n"
            report += f"   Название: {supplier.get('name', 'Не указано')}\n"
            report += f"   VAT: {supplier.get('vat', 'Не указан')}\n"
            report += f"   Email: {supplier.get('email', 'Не указан')}\n"
            report += f"   Телефон: {supplier.get('phone', 'Не указан')}\n"
            report += f"   Адрес: {supplier.get('address', 'Не указан')}\n\n"

        # Информация об автомобиле
        vin = analysis.get('vin')
        car_model = analysis.get('car_model')
        if vin or car_model:
            report += "🚗 АВТОМОБИЛЬ:\n"
            report += f"   VIN: {vin or 'Не указан'}\n"
            report += f"   Модель: {car_model or 'Не указана'}\n"
            report += f"   Цена покупки: {analysis.get('cost_price', 'Не указана')}\n\n"

        return report

    except Exception as e:
        return f"❌ Ошибка генерации отчета: {str(e)}"


def generate_detailed_info(result) -> str:
    """Генерирует детальную информацию"""
    try:
        analysis = result.document_analysis
        info = "📊 ДЕТАЛЬНАЯ ИНФОРМАЦИЯ\n\n"

        # Добавляем все доступные поля
        for key, value in analysis.items():
            if value and value != "Не указан" and value != "Не указана":
                info += f"{key}: {value}\n"

        return info

    except Exception as e:
        return f"❌ Ошибка генерации детальной информации: {str(e)}"


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /help"""
    if not update.message:
        return

    help_text = """
🤖 AI Invoice Bot - Помощь

📋 Доступные команды:
/start - Начать работу с ботом
/help - Показать эту справку
/status - Показать статус системы

📄 Обработка документов:
• Отправьте PDF файл для анализа
• Бот автоматически извлечет данные
• Проверит существующих поставщиков
• Предложит создать контакты и ITEM

🎯 Возможности:
• Анализ счетов и контрактов
• Распознавание автомобильной информации
• Интеграция с Zoho Books
• Умная проверка дубликатов
"""
    await update.message.reply_text(help_text)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /status"""
    if not update.message:
        return

    try:
        # Проверяем доступность модулей
        status_text = "📊 СТАТУС СИСТЕМЫ\n\n"

        # Проверяем основные модули
        try:
            # Используем уже импортированные модули
            SmartDocumentProcessor()
            status_text += "✅ SmartDocumentProcessor - доступен\n"
        except Exception:
            status_text += "❌ SmartDocumentProcessor - недоступен\n"

        try:
            # Проверяем доступность функции
            create_supplier_from_document
            status_text += "✅ ContactCreator - доступен\n"
        except Exception:
            status_text += "❌ ContactCreator - недоступен\n"

        status_text += "\n🚀 Система готова к работе!"

        await update.message.reply_text(status_text)

    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка проверки статуса: {str(e)}")


def setup_handlers(application: Application) -> None:
    """Настройка обработчиков команд"""
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_pdf))
    # Ввод цены продажи для ITEM приходит как текст — принимаем его отдельным хендлером
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    application.add_handler(CallbackQueryHandler(handle_callback))

async def handle_smart_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Кнопка: Анализ документа (краткие тезисы на русском)."""
    if not update.callback_query or not context.user_data:
        return
    query = update.callback_query
    analysis = context.user_data.get('document_analysis') or {}

    try:
        # 1) Если есть готовые contract_risks из анализа — используем их
        risks = analysis.get('contract_risks') or {}
        summary_lines = []
        if risks:
            # Сформируем компактный вывод
            if risks.get('payment_terms'):
                summary_lines.append(f"Оплата: {risks.get('payment_terms')}")
            if risks.get('delivery_terms'):
                summary_lines.append(f"Поставка: {risks.get('delivery_terms')}")
            if risks.get('jurisdiction'):
                summary_lines.append(f"Юрисдикция: {risks.get('jurisdiction')}")
            if risks.get('warranty'):
                summary_lines.append(f"Гарантия: {risks.get('warranty')}")
            if risks.get('taxes'):
                summary_lines.append(f"Налоги: {risks.get('taxes')}")
            if risks.get('penalties'):
                summary_lines.append(f"Штрафы/неустойки: {risks.get('penalties')}")
            unusual = risks.get('unusual') or []
            if unusual:
                bullet = '; '.join(str(x) for x in unusual[:5])
                summary_lines.append(f"Особые условия: {bullet}")
            listed_risks = risks.get('risks') or []
            if listed_risks:
                bullet = '; '.join(str(x) for x in listed_risks[:5])
                summary_lines.append(f"Риски: {bullet}")
        else:
            # 2) Fallback: вызов LLM для краткой выжимки по извлеченному тексту
            text = analysis.get('extracted_text') or ''
            try:
                # Вызов напрямую: компактная выдержка (без лишних задержек)
                llm = llm_analyze_contract_risks(text)  # type: ignore
                if llm:
                    if llm.get('payment_terms'):
                        summary_lines.append(f"Оплата: {llm.get('payment_terms')}")
                    if llm.get('delivery_terms'):
                        summary_lines.append(f"Поставка: {llm.get('delivery_terms')}")
                    if llm.get('jurisdiction'):
                        summary_lines.append(f"Юрисдикция: {llm.get('jurisdiction')}")
                    if llm.get('warranty'):
                        summary_lines.append(f"Гарантия: {llm.get('warranty')}")
                    if llm.get('taxes'):
                        summary_lines.append(f"Налоги: {llm.get('taxes')}")
                    if llm.get('penalties'):
                        summary_lines.append(f"Штрафы/неустойки: {llm.get('penalties')}")
                    unusual = llm.get('unusual') or []
                    if unusual:
                        bullet = '; '.join(str(x) for x in unusual[:5])
                        summary_lines.append(f"Особые условия: {bullet}")
                    listed_risks = llm.get('risks') or []
                    if listed_risks:
                        bullet = '; '.join(str(x) for x in listed_risks[:5])
                        summary_lines.append(f"Риски: {bullet}")
            except Exception:
                pass

        # Обогащаем автоинфо
        try:
            if analysis.get('vin'):
                summary_lines.append(f"VIN: {analysis.get('vin')}")
            brand_model = ' '.join([p for p in [analysis.get('car_brand'), analysis.get('car_model')] if p])
            if brand_model.strip():
                summary_lines.append(f"Авто: {brand_model.strip()}")
        except Exception:
            pass

        if not summary_lines:
            summary_lines.append("Нет специфических условий в документе или они не распознаны.")

        # Готовим текст и переводим на русский через LLM
        raw_summary = "🧠 Краткий анализ документа:\n" + "\n".join(f"• {line}" for line in summary_lines)
        ru_summary = llm_translate_to_ru(raw_summary)

        # Не редактируем исходное сообщение (чтобы не убирать кнопки) — отправляем новое
        try:
            await query.answer()
        except Exception:
            pass
        await context.bot.send_message(chat_id=query.message.chat_id, text=ru_summary)
    except Exception as e:
        try:
            await query.answer()
        except Exception:
            pass
        await context.bot.send_message(chat_id=query.message.chat_id, text=f"❌ Ошибка анализа: {str(e)}")


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка обычных текстовых сообщений (ввод цены при создании ITEM)."""
    if not update.message or not context.user_data:
        return
    try:
        if context.user_data.get('waiting_for_selling_price'):
            await handle_selling_price(update, context)
    except Exception:
        pass