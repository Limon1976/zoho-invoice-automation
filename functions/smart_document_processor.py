#!/usr/bin/env python3
"""
Smart Document Processor
========================

Умный процессор документов с автоматической проверкой и обновлением контактов
"""

import sys
import json
import asyncio
import shutil
from typing import Dict, List, Any, Optional, Union
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
import re

# Добавляем корневую папку в path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

# Optional import of service analyzer to avoid runtime errors when module is absent
try:
    from functions.ai_invoice_analyzer_enhanced import (
        enhanced_car_document_analysis,
        enhanced_service_document_analysis,
    )
    _HAS_SERVICE_ANALYZER = True
except Exception:  # ImportError or attribute error
    from functions.ai_invoice_analyzer_enhanced import enhanced_car_document_analysis
    _HAS_SERVICE_ANALYZER = False
from functions.agent_invoice_parser import extract_text_from_pdf
from src.domain.services.contact_cache import OptimizedContactCache

# Добавляем Pydantic модели
from pydantic import BaseModel, Field, validator
from enum import Enum

class DocumentCategory(str, Enum):
    """Категории документов"""
    CARS = "🚗 Автомобили"
    FLOWERS = "🌸 Цветы" 
    UTILITIES = "💧 Коммунальные услуги"
    SERVICES = "🛠️ Услуги"
    FOOD = "🍎 Продукты питания"
    OTHER = "📦 Прочие товары"

class VATStatus(str, Enum):
    """Статусы VAT"""
    MATCH = "match"
    MISMATCH = "mismatch"
    MISSING_IN_CACHE = "missing_in_cache"
    MISSING_IN_DOCUMENT = "missing_in_document"
    BOTH_MISSING = "both_missing"
    NAME_MISMATCH = "name_mismatch"
    UNKNOWN = "unknown"

class ContactSearchResult(BaseModel):
    """Результат поиска контакта"""
    found_in_cache: bool = False
    found_in_zoho: bool = False
    contact_data: Optional[Dict[str, Any]] = None
    cache_updated: bool = False
    search_method: str = "none"  # cache, zoho_api, not_found
    
class SupplierAnalysis(BaseModel):
    """Анализ поставщика с Pydantic валидацией"""
    name: str = Field(..., min_length=1, description="Название поставщика")
    vat_number: Optional[str] = Field(None, description="VAT номер")
    email: Optional[str] = Field(None, description="Email")
    phone: Optional[str] = Field(None, description="Телефон")
    address: Optional[str] = Field(None, description="Адрес")
    country: Optional[str] = Field(None, description="Страна")
    
    @validator('vat_number')
    def validate_vat(cls, v):
        if v and len(v.strip()) < 3:
            raise ValueError('VAT номер слишком короткий')
        return v.strip() if v else None


@dataclass
class ContactComparison:
    """Результат сравнения контактов"""
    supplier_name: str
    exists_in_cache: bool
    cached_contact: Optional[Dict[str, Any]] = None
    document_data: Optional[Dict[str, Any]] = None
    differences: Optional[List[Dict[str, str]]] = None
    confidence_match: float = 0.0
    recommended_action: str = "unknown"  # create, update, use_existing, update_vat_in_zoho, resolve_vat_conflict, resolve_name_conflict
    vat_status: str = "unknown"  # match, mismatch, missing_in_cache, missing_in_document, both_missing, name_mismatch

    def __post_init__(self):
        if self.differences is None:
            self.differences = []


@dataclass
class SKUCheckResult:
    """Результат проверки SKU"""
    vin: str
    exists_in_sku_cache: bool
    car_name: str = ""
    recommended_action: str = "unknown"  # create_item, update_item, not_car
    message: str = ""


@dataclass
class ProcessingResult:
    """Результат обработки документа"""
    success: bool
    document_analysis: Dict[str, Any]
    contact_comparison: ContactComparison
    sku_check: Optional[SKUCheckResult] = None
    suggested_actions: Optional[List[str]] = None
    errors: Optional[List[str]] = None

    def __post_init__(self):
        if self.suggested_actions is None:
            self.suggested_actions = []
        if self.errors is None:
            self.errors = []


class SmartDocumentProcessor:
    """Умный процессор документов"""

    def __init__(self):
        self.cache_file = "data/optimized_cache/all_contacts_optimized.json"
        self.full_contacts_dir = Path("data/full_contacts")
        self.cached_contacts = self._load_cached_contacts()

    def _load_cached_contacts(self) -> Dict[str, Any]:
        """Загружает кэшированные контакты"""
        try:
            if Path(self.cache_file).exists():
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {"contacts": {}, "vat_index": {}, "company_index": {}}
        except Exception as e:
            print(f"⚠️ Ошибка загрузки кэша: {e}")
            return {"contacts": {}, "vat_index": {}, "company_index": {}}

    async def process_document(self, file_path: str) -> ProcessingResult:
        """
        Основная функция обработки документа

        Args:
            file_path: Путь к PDF файлу

        Returns:
            Результат обработки с рекомендациями
        """
        result = ProcessingResult(
            success=False,
            document_analysis={},
            contact_comparison=ContactComparison(supplier_name="Unknown", exists_in_cache=False),
            suggested_actions=[],
            errors=[]
        )

        try:
            print(f"📄 Обрабатываем документ: {file_path}")

            # Шаг 1: Извлекаем текст из PDF
            extracted_text = extract_text_from_pdf(file_path)
            if not extracted_text:
                error_msg = "Не удалось извлечь текст из PDF"
                if result.errors is None:
                    result.errors = []
                result.errors.append(error_msg)
                return result

            # Сохраняем извлеченный текст для использования в _compare_supplier_with_cache
            self._last_extracted_text = extracted_text

            # Шаг 2: AI анализ документа
            print("🤖 Запускаем AI анализ...")

            # Попытка 1: новый LLM-экстрактор (прямой JSON)
            try:
                from functions.llm_document_extractor import (
                    llm_extract_fields,
                    llm_analyze_contract_risks,
                    llm_generate_car_description_en,
                )
            except Exception:
                llm_extract_fields = None  # type: ignore
                llm_analyze_contract_risks = None  # type: ignore
                llm_generate_car_description_en = None  # type: ignore

            analysis = None
            llm_data = {}
            if callable(llm_extract_fields):
                try:
                    llm_data = llm_extract_fields(extracted_text) or {}
                except Exception:
                    llm_data = {}

            print(f"🔍 DEBUG: LLM data status: {bool(llm_data)}, keys: {list(llm_data.keys()) if llm_data else 'None'}")
            if llm_data:
                # Маппинг полей LLM → analysis
                analysis = {
                    'ai_enhanced': True,
                    'supplier_name': llm_data.get('supplier_name') or '',
                    'supplier_vat': llm_data.get('vat') or '',
                    'supplier_email': llm_data.get('supplier_email') or '',
                    'supplier_phone': llm_data.get('supplier_phone') or '',
                    'supplier_country': llm_data.get('supplier_country') or '',
                    # supplier_address как строка + структурированные поля
                    'supplier_address': llm_data.get('supplier_address') or '',
                    'supplier_street': llm_data.get('supplier_street') or '',
                    'supplier_city': llm_data.get('supplier_city') or '',
                    'supplier_zip_code': llm_data.get('supplier_zip_code') or '',
                    'bill_number': llm_data.get('bill_number') or '',
                    'document_date': llm_data.get('issue_date') or llm_data.get('date') or '',
                    'due_date': llm_data.get('due_date') or (llm_data.get('bank') or {}).get('payment_due_date') or '',
                    # Всегда трактуем total_amount как NET (если доступно net_amount — берем его)
                    'total_amount': llm_data.get('net_amount') if (llm_data.get('net_amount') is not None) else llm_data.get('total_amount'),
                    'currency': llm_data.get('currency') or '',
                    'tax_rate': llm_data.get('tax_rate'),
                    'net_amount': llm_data.get('net_amount'),
                    'vat_amount': llm_data.get('vat_amount'),
                    'gross_amount': llm_data.get('gross_amount'),
                    'notes': llm_data.get('notes') or '',
                    'vin': llm_data.get('vin') or '',
                    'car_brand': llm_data.get('car_brand') or '',
                    'car_model': llm_data.get('car_model') or '',
                    'is_car_related': True if (llm_data.get('vin') or llm_data.get('car_brand') or llm_data.get('car_model')) else False,
                    'item_description': llm_data.get('item_description') or '',
                    'service_description': llm_data.get('service_description') or '',
                    'product_category': llm_data.get('product_category') or '',
                    'detected_flower_names': llm_data.get('detected_flower_names') or [],
                    'bank_name': (llm_data.get('bank') or {}).get('bank_name') or '',
                    'bank_address': (llm_data.get('bank') or {}).get('bank_address') or '',
                    'bank_account': (llm_data.get('bank') or {}).get('bank_account') or '',
                    'iban': (llm_data.get('bank') or {}).get('iban') or '',
                    'swift_bic': (llm_data.get('bank') or {}).get('swift') or '',
                    'payment_method': (llm_data.get('bank') or {}).get('payment_method') or '',
                    'issuer_name': llm_data.get('issuer_name') or llm_data.get('seller_name') or '',
                    'issuer_vat': llm_data.get('issuer_vat') or llm_data.get('seller_vat') or '',
                    'issuer_contact_person': llm_data.get('issuer_contact_person') or '',
                    # LLM категория и цветы для принудительного парсинга
                    'product_category': llm_data.get('product_category') or '',
                    'detected_flower_names': llm_data.get('detected_flower_names') or [],
                }

                # Нормализуем контактное лицо: используем issuer_contact_person, но не показываем пользователя
                try:
                    icp = (analysis.get('issuer_contact_person') or '').strip()
                    if icp and icp.lower() != 'pavel kaliadka':
                        analysis['contact_person'] = icp
                except Exception:
                    pass

                # Исправляем issuer, если по ошибке распознан нашей фирмой — используем supplier
                try:
                    issuer_name = (analysis.get('issuer_name') or '').strip().lower()
                    issuer_vat = (analysis.get('issuer_vat') or '').upper().replace(' ', '')
                    our_markers = ['tavie europe', 'parkentertainment', 'ee102288270', 'pl5272956146']
                    if any(m in issuer_name for m in our_markers) or any(v in issuer_vat for v in ['EE102288270', 'PL5272956146']):
                        analysis['issuer_name'] = analysis.get('supplier_name') or analysis.get('issuer_name')
                        analysis['issuer_vat'] = analysis.get('supplier_vat') or analysis.get('issuer_vat')
                except Exception:
                    pass

                # Человекочитаемый тип документа
                doc_type_raw = (llm_data.get('document_type') or '').lower()
                doc_map = {
                    'contract_sale': 'Договор продажи',
                    'proforma_invoice': 'Проформа',
                    'invoice': 'Инвойс',
                    'service_invoice': 'Инвойс (услуги)'
                }
                analysis['document_type'] = doc_type_raw
                analysis['document_type_readable'] = doc_map.get(doc_type_raw, 'Документ')

                # car_item_name по правилу: Brand Model + последние 5 цифр VIN
                try:
                    import re as _re
                    vin = str(analysis.get('vin') or '')
                    last5 = _re.sub(r'[^0-9]', '', vin)[-5:] if vin else ''
                    if last5 and (analysis.get('car_brand') or analysis.get('car_model')):
                        name_parts = [p for p in [analysis.get('car_brand'), analysis.get('car_model')] if p]
                        analysis['car_item_name'] = f"{' '.join(name_parts)}_{last5}"
                except Exception:
                    pass

                # Если это авто и нет описания — генерируем краткое EN описание с VIN
                try:
                    if analysis.get('is_car_related') and not (analysis.get('item_description') or '').strip():
                        if callable(llm_generate_car_description_en):
                            desc = llm_generate_car_description_en(
                                extracted_text,
                                analysis.get('car_brand') or '',
                                analysis.get('car_model') or '',
                                analysis.get('vin') or '',
                            )
                            if desc:
                                analysis['item_description'] = desc
                except Exception:
                    pass

                # Если контракт/продажа — анализ рисков
                if callable(llm_analyze_contract_risks) and ('contract' in doc_type_raw or 'sale' in doc_type_raw or 'proforma' in doc_type_raw):
                    try:
                        risks = llm_analyze_contract_risks(extracted_text) or {}
                        if risks:
                            analysis['contract_risks'] = risks
                    except Exception:
                        pass
            else:
                # Попытка 2: старая логика анализаторов (service/car)
                # Определяем тип документа и выбираем подходящий анализатор
                print("🔍 DEBUG: LLM data пустой, используем старую логику")
                document_text_lower = extracted_text.lower()
                service_keywords = ['delivery', 'transport', 'shipping', 'carriage', 'cmr', 'freight', 'logistics']
                is_service_document = any(keyword in document_text_lower for keyword in service_keywords)
                print(f"🔍 DEBUG: is_service_document={is_service_document}, keywords={service_keywords}")

                if is_service_document and _HAS_SERVICE_ANALYZER:
                    print("🔍 Обнаружен документ услуг - используем service analyzer")
                    analysis = await enhanced_service_document_analysis(extracted_text)
                    # Пост-обработка для описания услуги и человекочитаемого типа
                    if analysis and analysis.get('ai_enhanced'):
                        doc_type_map = {
                            'transport': 'Транспорт',
                            'delivery': 'Доставка',
                            'logistics': 'Логистика',
                            'service': 'Услуги',
                        }
                        readable = doc_type_map.get(str(analysis.get('document_type')).lower(), 'Услуги')
                        if analysis.get('is_final_invoice'):
                            analysis['document_type_readable'] = 'Инвойс'
                        else:
                            analysis['document_type_readable'] = readable

                        service_desc = None
                        services = analysis.get('services') or []
                        if services:
                            first = services[0]
                            if isinstance(first, dict):
                                service_desc = first.get('description')
                            elif isinstance(first, str):
                                service_desc = first
                        if not service_desc:
                            vin = analysis.get('vin') or ''
                            car = analysis.get('car_model') or analysis.get('item_details') or ''
                            if 'transport' in str(analysis.get('document_type')).lower():
                                if vin:
                                    service_desc = f"Транспортировка авто VIN {vin}"
                                elif car:
                                    service_desc = f"Транспортировка авто {car}"
                                else:
                                    service_desc = "Транспортные услуги"
                            else:
                                service_desc = readable
                        analysis['service_description'] = service_desc
                else:
                    if is_service_document and not _HAS_SERVICE_ANALYZER:
                        print("🔍 Обнаружен документ услуг, но service analyzer недоступен — используем car analyzer")
                    else:
                        print("🔍 Обнаружен автомобильный документ - используем car analyzer")
                    analysis = await enhanced_car_document_analysis(extracted_text)

            if not analysis or not analysis.get("ai_enhanced"):
                error_msg = "AI анализ не удался"
                if result.errors is None:
                    result.errors = []
                result.errors.append(error_msg)
                return result

            # ВАЖНО: Добавляем extracted_text в analysis для логики определения организации
            analysis['extracted_text'] = extracted_text

            # Эвристика: извлечь номер счета из текста, если AI дал неполный/некорректный
            def _extract_bill_number_from_text(text: str) -> Optional[str]:
                if not text:
                    return None
                candidates: list[str] = []
                # Паттерн для формата вида "TR serija Nr.0189" (литовские документы)
                pattern_lt = re.compile(r"\b([A-Z]{1,5}\s*serija\s*Nr\.?\s*\d{1,8})\b", re.IGNORECASE)
                candidates += [m.group(1) for m in pattern_lt.finditer(text)]
                # Общий паттерн: префикс из букв + номер с точками/слэшами
                pattern_generic = re.compile(r"\b([A-Z]{1,5}[\s.-]*\d{1,8}(?:/[\dA-Z]{1,6})?)\b")
                candidates += [m.group(1) for m in pattern_generic.finditer(text)]
                # Возвращаем наиболее длинного кандидата, чтобы сохранить максимально информативную форму
                if candidates:
                    candidates.sort(key=lambda s: len(s), reverse=True)
                    return candidates[0].strip()
                return None

            try:
                ocr_bill = _extract_bill_number_from_text(extracted_text)
                ai_bill = (analysis.get('bill_number') or '').strip()
                # Правило: если AI номер пустой или выглядит усечённо, а OCR дал форму с "serija"/"Nr" — берём OCR
                def looks_informative(s: str) -> bool:
                    s_low = s.lower()
                    return ('serija' in s_low) or ('nr' in s_low)
                if ocr_bill and (not ai_bill or (looks_informative(ocr_bill) and not looks_informative(ai_bill))):
                    analysis['bill_number'] = ocr_bill
            except Exception:
                pass

            result.document_analysis = analysis

            # Попытка извлечь US EIN / TAX ID из текста и добавить в analysis как supplier_vat (без префикса страны)
            try:
                ein_match = re.search(r"\b(EIN|TAX)\s*[:#]?\s*(\d{2}-\d{7})\b", extracted_text, re.IGNORECASE)
                if ein_match and not analysis.get('supplier_vat'):
                    analysis['supplier_vat'] = ein_match.group(2)
            except Exception:
                pass

            # Извлечь позиции цветов (простая эвристика для польских/PLN инвойсов)
            try:
                currency_hint = (analysis.get('currency') or '').upper()
                is_pln = currency_hint == 'PLN' or ' pln' in extracted_text.lower()
                supplier_country = (analysis.get('supplier_country') or analysis.get('supplier_address', {}).get('country') or '').lower()
                looks_flower = any(kw in extracted_text.lower() for kw in [
                    'kwiat', 'kwiaty', 'róża', 'roza', 'tulip', 'peonia', 'piwonia', 'goździk', 'gerbera', 'bukiet', 'flower', 'flowers'
                ])
                if is_pln or looks_flower:
                    flower_lines = []
                    # Регекс: имя, количество, цена единицы, опционально PLN
                    pattern = re.compile(r"^(?P<name>[A-Za-zÀ-ÿżźćńółęąśŻŹĆŃÓŁĘĄŚ0-9\-\/\s]{3,}?)\s+(?P<qty>\d{1,4}(?:[.,]\d{1,2})?)\s+(?P<price>\d{1,6}(?:[.,]\d{2}))\s*(?:PLN|zl|zł)?\b", re.IGNORECASE | re.MULTILINE)
                    for m in pattern.finditer(extracted_text):
                        name = m.group('name').strip()
                        qty = m.group('qty').replace(',', '.')
                        price = m.group('price').replace(',', '.')
                        try:
                            qty_f = float(qty)
                            price_f = float(price)
                        except Exception:
                            continue
                        # Фильтр по ключевым словам цветов в названии
                        if not any(k in name.lower() for k in ['kwiat', 'róż', 'roza', 'tulip', 'gerber', 'goźdz', 'bukiet', 'flower']):
                            continue
                        flower_lines.append({
                            'name': name,
                            'quantity': qty_f,
                            'unit_price': price_f,
                        })
                    # ОТКЛЮЧЕНО: старый regex parser блокирует новые методы в handlers.py
                    # if flower_lines:
                    #     analysis['flower_lines'] = flower_lines
            except Exception:
                pass

            # МУЛЬТИЯЗЫЧНОЕ ИЗВЛЕЧЕНИЕ VAT (в т.ч. польский NIP): если VAT ещё не найден
            try:
                def _clean_vat(s: str) -> str:
                    return ''.join(ch for ch in s.upper() if ch.isalnum())

                if not analysis.get('supplier_vat') and extracted_text:
                    # Сначала — приоритетный поиск польского NIP (10 цифр)
                    nip_match = re.search(r"\bNIP\s*[:#]?\s*(\d{10})\b", extracted_text, re.IGNORECASE)
                    if nip_match:
                        analysis['supplier_vat'] = nip_match.group(1)
                    
                # Если всё ещё нет VAT — пробуем общие шаблоны, но фильтруем ложные срабатывания (BRUTTO/NETTO/% и т.д.)
                if not analysis.get('supplier_vat') and extracted_text:
                    patterns = [
                        r"\bVAT\s*(?:NO\.|NUMBER|NR|REG\.?\s*NO\.|REGISTRATION)?\s*[:#]?\s*([A-Z]{0,2}[\s-]?[A-Z0-9][A-Z0-9\s.-]{4,})\b",
                        r"\bNIP\s*[:#]?\s*([A-Z]{0,2}[\s-]?[0-9][0-9\s.-]{7,})\b",  # Польша
                        r"\bUSt[- ]?(?:ID|IdNr\.?|Nr\.?|IDNR)\s*[:#]?\s*([A-Z]{0,2}[\s-]?[A-Z0-9][A-Z0-9\s.-]{4,})\b",  # Германия
                        r"\bTVA\s*(?:INTRA)?\s*[:#]?\s*([A-Z]{0,2}[\s-]?[A-Z0-9][A-Z0-9\s.-]{4,})\b",  # Франция/BE/RO
                        r"\bIVA\s*[:#]?\s*([A-Z]{0,2}[\s-]?[A-Z0-9][A-Z0-9\s.-]{4,})\b",  # Италия/ES/PT
                        r"\bNIF\s*[:#]?\s*([A-Z]{0,2}[\s-]?[A-Z0-9][A-Z0-9\s.-]{4,})\b",  # ES/PT
                        r"\bCIF\s*[:#]?\s*([A-Z]{0,2}[\s-]?[A-Z0-9][A-Z0-9\s.-]{4,})\b",  # ES/RO
                        r"\bI[ČC]\s*DPH\s*[:#]?\s*([A-Z]{0,2}[\s-]?[A-Z0-9][A-Z0-9\s.-]{4,})\b",  # CZ/SK IČ DPH
                        r"\bDI[ČC]\s*[:#]?\s*([A-Z]{0,2}[\s-]?[A-Z0-9][A-Z0-9\s.-]{4,})\b",  # CZ/SK DIČ
                    ]
                    found = None
                    for p in patterns:
                        m = re.search(p, extracted_text, re.IGNORECASE)
                        if m:
                            raw = m.group(1)
                            candidate = _clean_vat(raw)
                            # Отбрасываем явные ложные: упоминания BRUTTO/NETTO/% вокруг
                            context_slice = extracted_text[max(0, m.start()-10): m.end()+10].upper()
                            if any(bad in context_slice for bad in ['BRUTTO', 'NETTO', '%']):
                                continue
                            # Фильтр против EIN и слишком коротких
                            if not re.fullmatch(r"\d{2}-\d{7}", raw) and len(candidate) >= 6:
                                found = candidate
                                break
                    if found:
                        analysis['supplier_vat'] = found
            except Exception:
                pass

            # Шаг 3: Проверяем поставщика в кэше
            print("🔍 Проверяем поставщика в кэше...")
            contact_comparison = await self._compare_supplier_with_cache(analysis)
            result.contact_comparison = contact_comparison

            # Шаг 4: Проверяем SKU для автомобилей
            print("🔍 Проверяем SKU автомобиля...")
            sku_check_result = await self._check_sku_in_cache(analysis)
            result.sku_check = sku_check_result

            # Шаг 5: Определяем рекомендуемые действия на основе проверок
            suggested_actions = self._determine_smart_actions(contact_comparison, sku_check_result, analysis)
            result.suggested_actions = suggested_actions or []

            result.success = True

            # Сохраняем обработанный документ
            await self._save_processed_document(file_path, analysis)

        except Exception as e:
            error_msg = f"Ошибка обработки: {e}"
            print(f"❌ {error_msg}")
            if result.errors is None:
                result.errors = []
            result.errors.append(error_msg)

        return result

    async def _compare_supplier_with_cache(self, document_data: Dict[str, Any]) -> ContactComparison:
        """Сравнивает поставщика из документа с кэшем контактов"""
        try:
            supplier_name = (document_data.get('supplier_name') or '').strip()
            supplier_vat = (document_data.get('supplier_vat') or '').strip()
            our_company = (document_data.get('our_company') or '').strip()
            extracted_text = document_data.get('extracted_text', '')

            if not supplier_name:
                return ContactComparison(
                    supplier_name="Неизвестный поставщик",
                    exists_in_cache=False,
                    differences=[]
                )

            # Если our_company не определен AI, пытаемся определить по VAT номерам в тексте
            if not our_company and extracted_text:
                print(f"🔍 DEBUG: supplier_name={supplier_name}")
                print(f"🔍 DEBUG: supplier_vat={supplier_vat}")
                print(f"🔍 DEBUG: our_company (from AI)={our_company}")
                print(f"🔍 DEBUG: document_text length={len(extracted_text)}")

                # Ищем VAT номера в тексте (с префиксами и без)
                parkent_vat_patterns = [
                    'PL5272956146', 'PL 5272956146', '5272956146'
                ]
                tavie_vat_patterns = [
                    'EE102288270', 'EE 102288270', '102288270'
                ]

                # Проверяем PARKENTERTAINMENT VAT
                parkent_found = any(pattern in extracted_text for pattern in parkent_vat_patterns)
                print(f"🔍 DEBUG: searching for PARKENTERTAINMENT VAT patterns: {parkent_found}")
                if parkent_found:
                    found_patterns = [p for p in parkent_vat_patterns if p in extracted_text]
                    print(f"🔍 DEBUG: Found patterns: {found_patterns}")

                # Проверяем TaVie Europe VAT  
                tavie_found = any(pattern in extracted_text for pattern in tavie_vat_patterns)
                print(f"🔍 DEBUG: searching for TaVie Europe VAT patterns: {tavie_found}")

                if parkent_found:
                    our_company = 'PARKENTERTAINMENT'
                    print("🔍 DEBUG: Found PARKENTERTAINMENT VAT, setting our_company to PARKENTERTAINMENT")
                elif tavie_found:
                    our_company = 'TaVie Europe OÜ'
                    print("🔍 DEBUG: Found TaVie Europe VAT, setting our_company to TaVie Europe OÜ")

                print(f"🔍 DEBUG: Final our_company={our_company}")

                # ВАЖНО: Сохраняем определенную организацию обратно в document_data
                document_data['our_company'] = our_company

            # КАТЕГОРИЗАЦИЯ ТОВАРОВ (учитываем и название поставщика как подсказку)
            combined_text_for_category = extracted_text
            try:
                if supplier_name:
                    combined_text_for_category = f"{extracted_text}\n{supplier_name}"
            except Exception:
                pass
            # Категория документа: приоритет LLM для FLOWERS по названиям цветов, иначе CategoryDetector
            print(f"🌸 DEBUG: Entering category detection, document_data keys: {list(document_data.keys())}")
            try:
                llm_cat = (document_data.get('product_category') or '').upper()
                flower_names = document_data.get('detected_flower_names') or []
                print(f"🌸 DEBUG: llm_cat='{llm_cat}', flower_names={len(flower_names)} items")
                if llm_cat == 'FLOWERS' and flower_names:
                    document_category = DocumentCategory.FLOWERS
                    document_data['document_category'] = document_category
                    print(f"📋 Категория документа: {document_category} (source: llm, flowers={len(flower_names)})")
                else:
                    from src.domain.services.category_detector import CategoryDetector
                    detector = CategoryDetector()
                    det = detector.detect(combined_text_for_category, supplier_name=supplier_name or "", product_description=document_data.get('service_description') or document_data.get('item_details') or "")
                    document_category = det.category
                    document_data['document_category'] = document_category
                    print(f"📋 Категория документа: {document_category} (source: {det.source}, conf={det.confidence:.2f})")
            except Exception as _e:
                document_category = self._determine_document_category(combined_text_for_category)
                document_data['document_category'] = document_category
                print(f"📋 Категория документа (fallback): {document_category}")

            # Определяем файл кэша на основе our_company
            if our_company == 'PARKENTERTAINMENT':
                print("🏢 Определена организация: PARKENTERTAINMENT")
                cache_file = "data/optimized_cache/PARKENTERTAINMENT_optimized.json"
            elif our_company == 'TaVie Europe OÜ':
                print("🏢 Определена организация: TaVie Europe OÜ")
                cache_file = "data/optimized_cache/TaVie_Europe_optimized.json"
            else:
                print("🏢 Организация не определена, используем общий кэш")
                cache_file = "data/optimized_cache/all_contacts_optimized.json"

            print(f"📁 Используем кэш: {cache_file}")

            # Загружаем соответствующий кэш
            cache = OptimizedContactCache(cache_file)

            # УМНАЯ ЛОГИКА ПОИСКА С PYDANTIC:
            # 1. Сначала ищем в кэше по названию компании
            search_result = await self._search_supplier_comprehensive(supplier_name, supplier_vat, cache, our_company)

            if search_result.found_in_cache or search_result.found_in_zoho:
                cached_contact = search_result.contact_data
                # Универсальное извлечение VAT из записи Zoho/кэша
                def _extract_vat(contact: Dict[str, Any]) -> str:
                    if not contact:
                        return ''
                    for key in ['vat_number', 'tax_id', 'cf_tax_id', 'cf_vat_id']:
                        val = contact.get(key)
                        if val:
                            return str(val).strip()
                    # Также попробовать custom_fields
                    for cf in contact.get('custom_fields') or []:
                        v = (cf.get('value') or '').strip()
                        if v:
                            return v
                    return ''
                cached_vat = _extract_vat(cached_contact)
                document_vat = (supplier_vat or '').strip()

                # Если в локальном кэше VAT пуст, пробуем получить актуальный VAT напрямую из Zoho
                if not cached_vat:
                    try:
                        zoho_contact = await self._search_in_zoho_api(supplier_name, supplier_vat, our_company)
                        if zoho_contact:
                            zoho_vat = _extract_vat(zoho_contact)
                            if zoho_vat:
                                cached_contact = zoho_contact
                                cached_vat = zoho_vat
                                # Асинхронно обновим кэш, чтобы в следующий раз было значение
                                try:
                                    await self._update_cache_with_contact(zoho_contact, our_company)
                                except Exception:
                                    pass
                    except Exception:
                        pass

                print(f"   ✅ Контакт найден через: {search_result.search_method}")
                print(f"   📊 VAT сравнение: документ='{document_vat}' vs система='{cached_vat}'")

                # 2. Сравниваем VAT номера используя Pydantic Enum
                vat_status = self._compare_vat_numbers(document_vat, cached_vat)

                # 3. Определяем рекомендуемые действия на основе VAT статуса
                recommended_action, differences = self._determine_vat_actions(vat_status, document_vat, cached_vat, document_data, cached_contact)

                return ContactComparison(
                    supplier_name=supplier_name,
                    exists_in_cache=search_result.found_in_cache or search_result.found_in_zoho,  # Найден в кэше ИЛИ в Zoho
                    cached_contact=cached_contact,
                    differences=differences,
                    document_data=document_data,
                    recommended_action=recommended_action,
                    vat_status=vat_status.value
                )

            # 5. Контакт не найден нигде - создать новый
            print(f"   ❌ Контакт не найден: {supplier_name}")
            return ContactComparison(
                supplier_name=supplier_name,
                exists_in_cache=False,
                differences=[],
                document_data=document_data,
                recommended_action="create"
            )

        except Exception as e:
            print(f"❌ Ошибка сравнения с кэшем: {e}")
            return ContactComparison(
                supplier_name=supplier_name,
                exists_in_cache=False,
                differences=[]
            )

    def _is_similar_company_name(self, name1: str, name2: str, threshold: float = 0.8) -> bool:
        """Проверяет схожесть названий компаний"""
        from difflib import SequenceMatcher

        # Очищаем названия от лишних символов
        clean_name1 = self._clean_company_name(name1)
        clean_name2 = self._clean_company_name(name2)

        similarity = SequenceMatcher(None, clean_name1.lower(), clean_name2.lower()).ratio()
        return similarity >= threshold

    def _clean_company_name(self, name: str) -> str:
        """Очищает название компании от лишних символов"""
        # Убираем типовые окончания
        suffixes = ['GmbH', 'Ltd', 'LLC', 'OÜ', 'Sp. z o.o.', 'S.A.', 'B.V.']
        cleaned = name.strip()

        for suffix in suffixes:
            if cleaned.endswith(suffix):
                cleaned = cleaned[:-len(suffix)].strip()

        return cleaned

    def _find_differences(self, document_data: Dict[str, Any], cached_contact: Dict[str, Any]) -> List[Dict[str, str]]:
        """Находит различия между данными документа и кэша"""
        differences = []

        # Сравниваем основные поля
        fields_to_compare = {
            'name': 'contact_name',
            'vat': 'tax_id', 
            'country': 'country'
        }

        for doc_field, cache_field in fields_to_compare.items():
            doc_value = document_data.get(doc_field, '')
            cache_value = cached_contact.get(cache_field, '')

            if doc_value and cache_value and doc_value != cache_value:
                differences.append({
                    'field': doc_field,
                    'document_value': str(doc_value),
                    'cached_value': str(cache_value)
                })

        return differences

    async def _search_supplier_comprehensive(self, supplier_name: str, supplier_vat: str, cache: OptimizedContactCache, our_company: str) -> ContactSearchResult:
        """Комплексный поиск поставщика: кэш → Zoho API → обновление кэша"""
        
        # Шаг 1: Поиск в кэше
        found_contacts = []
        if supplier_name:
            found_contacts = cache.search_by_company(supplier_name)
            
        if found_contacts:
            print(f"   ✅ Найден в кэше по названию")
            return ContactSearchResult(
                found_in_cache=True,
                contact_data=found_contacts[0].to_dict(),
                search_method="cache"
            )
            
        # Поиск по VAT в кэше
        if supplier_vat:
            found_by_vat = cache.search_by_vat(supplier_vat)
            if found_by_vat:
                print(f"   ✅ Найден в кэше по VAT")
                return ContactSearchResult(
                    found_in_cache=True,
                    contact_data=found_by_vat.to_dict(),
                    search_method="cache_vat"
                )
        
        # Шаг 2: Поиск в Zoho API
        print(f"   🔍 Поиск в Zoho API: {supplier_name}")
        zoho_result = await self._search_in_zoho_api(supplier_name, supplier_vat, our_company)
        
        if zoho_result:
            print(f"   ✅ Найден в Zoho API - обновляем кэш")
            # Обновляем кэш с найденным контактом
            cache_updated = await self._update_cache_with_contact(zoho_result, our_company)
            
            return ContactSearchResult(
                found_in_zoho=True,
                contact_data=zoho_result,
                search_method="zoho_api",
                cache_updated=cache_updated
            )
            
        # Не найден нигде
        print(f"   ❌ Не найден ни в кэше, ни в Zoho")
        return ContactSearchResult(search_method="not_found")
    
    async def _search_in_zoho_api(self, supplier_name: str, supplier_vat: str, our_company: str) -> Optional[Dict[str, Any]]:
        """Поиск поставщика в Zoho Books API"""
        try:
            # Импортируем реальные функции поиска
            from functions.zoho_api import get_contact_by_name, get_contact_by_vat
            
            # Определяем organization_id
            organization_id = None
            if our_company == 'PARKENTERTAINMENT':
                organization_id = "20082562863"
            elif our_company == 'TaVie Europe OÜ':
                organization_id = "20092948714"
            else:
                print(f"   ⚠️ Неизвестная организация для Zoho API: {our_company}")
                return None
                
            # Поиск по названию
            if supplier_name:
                print(f"   🔍 Ищем в Zoho по названию: {supplier_name}")
                contact = get_contact_by_name(supplier_name, organization_id)
                if contact:
                    print(f"   ✅ Найден в Zoho по названию")
                    return contact
                    
            # Поиск по VAT
            if supplier_vat:
                print(f"   🔍 Ищем в Zoho по VAT: {supplier_vat}")
                contact = get_contact_by_vat(supplier_vat, organization_id)
                if contact:
                    print(f"   ✅ Найден в Zoho по VAT")
                    return contact
                    
            return None
            
        except Exception as e:
            print(f"   ❌ Ошибка поиска в Zoho API: {e}")
            return None
    
    def _compare_vat_numbers(self, document_vat: str, cached_vat: str) -> VATStatus:
        """Сравнивает VAT номера и возвращает Pydantic enum статус"""
        
        if document_vat and cached_vat:
            # Оба VAT присутствуют - сравниваем
            if document_vat.upper() == cached_vat.upper():
                print(f"   ✅ VAT совпадают")
                return VATStatus.MATCH
            else:
                print(f"   ⚠️ VAT не совпадают!")
                return VATStatus.MISMATCH
        elif document_vat and not cached_vat:
            # VAT есть в документе, но отсутствует в системе
            print(f"   ⚠️ VAT отсутствует в системе, но есть в документе")
            return VATStatus.MISSING_IN_CACHE
        elif not document_vat and cached_vat:
            # VAT есть в системе, но отсутствует в документе
            print(f"   ℹ️ VAT есть в системе, но отсутствует в документе")
            return VATStatus.MISSING_IN_DOCUMENT
        else:
            # VAT отсутствует в обоих местах
            print(f"   ℹ️ VAT отсутствует в обоих местах")
            return VATStatus.BOTH_MISSING
            
    def _determine_vat_actions(self, vat_status: VATStatus, document_vat: str, cached_vat: str, 
                              document_data: Dict[str, Any], cached_contact: Dict[str, Any]) -> tuple:
        """Определяет действия на основе VAT статуса"""
        
        if vat_status in [VATStatus.MATCH, VATStatus.BOTH_MISSING, VATStatus.MISSING_IN_DOCUMENT]:
            # Контакт найден, VAT в порядке
            recommended_action = "found"
            differences = []
        elif vat_status == VATStatus.MISSING_IN_CACHE:
            # Нужно обновить VAT в Zoho
            recommended_action = "update_vat_in_zoho"
            differences = [{"field": "vat_number", "document": document_vat, "cache": cached_vat}]
            print(f"   🎯 Рекомендация: Обновить VAT в Zoho ({document_vat})")
        elif vat_status == VATStatus.MISMATCH:
            # Конфликт VAT - требует ручного решения
            recommended_action = "resolve_vat_conflict"
            differences = [{"field": "vat_number", "document": document_vat, "cache": cached_vat}]
            print(f"   🎯 Рекомендация: Разрешить конфликт VAT")
        else:
            recommended_action = "unknown"
            differences = []

        # Находим другие различия между документом и системой
        other_differences = self._find_differences(document_data, cached_contact)
        differences.extend(other_differences)
        
        return recommended_action, differences

    async def _update_cache_with_contact(self, contact_data: Dict[str, Any], our_company: str) -> bool:
        """Обновляет кэш с контактом найденным в Zoho API"""
        try:
            # Импортируем функции обновления кэша
            from functions.refresh_zoho_cache import refresh_single_contact_cache
            
            contact_id = contact_data.get('contact_id')
            contact_name = contact_data.get('contact_name', 'Unknown')
            
            if not contact_id:
                print(f"   ❌ Нет contact_id для обновления кэша")
                return False
            
            # Определяем organization_id
            organization_id = None
            if our_company == 'PARKENTERTAINMENT':
                organization_id = "20082562863"
            elif our_company == 'TaVie Europe OÜ':
                organization_id = "20092948714"
            else:
                print(f"   ⚠️ Неизвестная организация для обновления кэша: {our_company}")
                return False
            
            print(f"   🔄 Обновляем кэш для контакта: {contact_name} (ID: {contact_id})")
            
            # Обновляем кэш для конкретного контакта
            success = await refresh_single_contact_cache(contact_id, organization_id, our_company)
            
            if success:
                print(f"   ✅ Кэш успешно обновлен для {contact_name}")
                return True
            else:
                print(f"   ❌ Ошибка обновления кэша для {contact_name}")
                return False
                
        except Exception as e:
            print(f"   ❌ Ошибка при обновлении кэша: {e}")
            return False

    def _determine_actions(self, comparison: ContactComparison, analysis: Dict[str, Any]) -> List[str]:
        """Определяет рекомендуемые действия"""
        actions = []

        if not comparison.exists_in_cache:
            actions.append("➕ Создать новый контакт в Zoho")
            actions.append("🔄 Обновить локальный кэш")
        elif comparison.differences:
            actions.append("📝 Обновить существующий контакт")
            actions.append("🔄 Обновить локальный кэш")

        if analysis.get('is_car_related'):
            actions.append("🚗 Проверить/создать автомобильный item")
            actions.append("📋 Сопоставить с существующими SKU")

        return actions

    def _determine_document_category(self, extracted_text: str) -> str:
        """Определяет категорию документа на основе содержимого с использованием Pydantic"""
        text_lower = extracted_text.lower()
        
        # Ключевые слова для автомобилей
        car_keywords = [
            'vin', 'chassis', 'vehicle', 'auto', 'car', 'bmw', 'mercedes', 'audi', 'volkswagen',
            'toyota', 'honda', 'ford', 'engine', 'transmission', 'vehicle identification',
            'registration', 'license plate', 'автомобиль', 'машина', 'двигатель'
        ]
        
        # Ключевые слова для цветов  
        flower_keywords = [
            'rose', 'roses', 'róża', 'flower', 'flowers', 'bouquet', 'petal', 'stem',
            'lily', 'tulip', 'orchid', 'carnation', 'chrysanthemum', 'dahlia', 'peony',
            'eustoma', 'delphinium', 'craspedia', 'dianthus', 'celosia', 'panicum',
            'kwiat', 'kwiaty', 'bukiet', 'płatki', 'łodyga'
        ]
        
        # Ключевые слова для коммунальных услуг
        utility_keywords = [
            'woda', 'water', 'gaz', 'gas', 'energia', 'energy', 'electricity', 'prąd',
            'heating', 'ogrzewanie', 'waste', 'śmieci', 'komunalne', 'utility', 'utilities',
            'sewage', 'kanalizacja', 'opłata', 'fee', 'media', 'bills'
        ]
        
        # Ключевые слова для общих услуг
        service_keywords = [
            'service', 'consulting', 'repair', 'maintenance', 'installation', 'support',
            'usługa', 'serwis', 'naprawa', 'konsultacja', 'instalacja', 'wsparcie',
            'parking', 'transport', 'delivery', 'dostawa'
        ]
        
        # Ключевые слова для продуктов питания
        food_keywords = [
            'food', 'jedzenie', 'żywność', 'meal', 'breakfast', 'lunch', 'dinner',
            'restaurant', 'cafe', 'catering', 'pizza', 'burger', 'bread', 'chleb'
        ]
        
        # Подсчитываем совпадения
        car_score = sum(1 for keyword in car_keywords if keyword in text_lower)
        flower_score = sum(1 for keyword in flower_keywords if keyword in text_lower)
        utility_score = sum(1 for keyword in utility_keywords if keyword in text_lower)
        service_score = sum(1 for keyword in service_keywords if keyword in text_lower)
        food_score = sum(1 for keyword in food_keywords if keyword in text_lower)
        
        # Определяем категорию по наибольшему количеству ключевых слов
        scores = {
            DocumentCategory.CARS: car_score,
            DocumentCategory.FLOWERS: flower_score,
            DocumentCategory.UTILITIES: utility_score,
            DocumentCategory.SERVICES: service_score,
            DocumentCategory.FOOD: food_score
        }
        
        # Находим максимальный счет
        max_score = max(scores.values())
        if max_score == 0:
            return DocumentCategory.OTHER
            
        # Возвращаем категорию с максимальным счетом
        for category, score in scores.items():
            if score == max_score:
                return category
                
        return DocumentCategory.OTHER

    async def _check_sku_in_cache(self, analysis: Dict[str, Any]) -> SKUCheckResult:
        """Проверяет SKU автомобиля в кэше"""
        print("   🔍 Начинаем проверку SKU...")
        # Проверяем что это автомобильный документ
        is_car = analysis.get('is_car_related')
        print(f"   🚗 Автомобильный документ: {is_car}")

        if not is_car:
            print("   ❌ Не автомобильный документ")
            return SKUCheckResult(
                vin="",
                exists_in_sku_cache=False,
                recommended_action="not_car",
                message="Документ не содержит информацию об автомобиле"
            )

        # Извлекаем VIN
        vin = analysis.get('vin') or analysis.get('item_sku', '')
        car_name = analysis.get('car_item_name', '')
        print(f"   🔢 VIN: {vin}")
        print(f"   🚗 Название: {car_name}")

        if not vin:
            print("   ❌ VIN не найден")
            return SKUCheckResult(
                vin="",
                exists_in_sku_cache=False,
                car_name=car_name,
                recommended_action="error",
                message="VIN номер не найден в документе"
            )

        try:
            print("   📋 Импортируем SKU менеджер...")
            # Импортируем менеджер SKU кэша
            sys.path.append(str(Path(__file__).parent))
            from sku_cache_manager import quick_sku_check

            print(f"   🔍 Проверяем SKU {vin}...")
            # Проверяем SKU
            sku_result = quick_sku_check(vin)
            print(f"   📊 Результат SKU: {sku_result}")

            if sku_result['exists']:
                print("   ✅ SKU найден - дубликат")
                return SKUCheckResult(
                    vin=vin,
                    exists_in_sku_cache=True,
                    car_name=car_name,
                    recommended_action="update_item",
                    message=f"ITEM с VIN {vin} существует - можно обновить"
                )
            else:
                print("   🆕 SKU не найден - можно создавать")
                return SKUCheckResult(
                    vin=vin,
                    exists_in_sku_cache=False,
                    car_name=car_name,
                    recommended_action="create_item",
                    message=f"VIN {vin} не найден - можно создавать ITEM"
                )

        except Exception as e:
            print(f"   ❌ Ошибка проверки SKU: {e}")
            return SKUCheckResult(
                vin=vin,
                exists_in_sku_cache=False,
                car_name=car_name,
                recommended_action="error",
                message=f"Ошибка проверки SKU: {str(e)}"
            )

    def _determine_smart_actions(self, contact_comparison: ContactComparison, sku_check: Optional[SKUCheckResult], analysis: Dict[str, Any]) -> List[str]:
        """Определяет умные действия на основе проверок контакта и SKU"""
        actions = []

        # УМНЫЕ ДЕЙСТВИЯ ДЛЯ КОНТАКТА НА ОСНОВЕ VAT ЛОГИКИ
        if contact_comparison.exists_in_cache:
            vat_status = getattr(contact_comparison, 'vat_status', 'unknown')
            
            if vat_status == "match":
                actions.append("✅ Поставщик найден, VAT совпадают")
            elif vat_status == "missing_in_cache":
                actions.append("🔄 Обновить VAT в Zoho Books")
                actions.append("📥 Синхронизировать кэш после обновления")
            elif vat_status == "mismatch":
                actions.append("⚠️ Разрешить конфликт VAT номеров")
                actions.append("🔍 Проверить корректность данных")
            elif vat_status == "missing_in_document":
                actions.append("✅ Поставщик найден (VAT только в кэше)")
            elif vat_status == "both_missing":
                actions.append("✅ Поставщик найден (VAT отсутствует)")
            elif vat_status == "name_mismatch":
                actions.append("🔍 Проверить переименование компании")
                actions.append("🔄 Обновить название в системе")
            else:
                actions.append("✅ Поставщик найден в системе")
        else:
            actions.append("➕ Создать нового поставщика")
            if analysis.get('supplier_vat'):
                actions.append("📝 Добавить VAT номер в профиль")

        # Действия для SKU (только если это автомобиль)
        if sku_check:
            if sku_check.recommended_action == "create_item":
                actions.append("🚗 Создать ITEM в каталоге")
            elif sku_check.recommended_action == "update_item":
                actions.append("🔄 Обновить ITEM в каталоге")
            elif sku_check.recommended_action == "error":
                error_msg = f"❌ {sku_check.message}"
                actions.append(error_msg)

        # ДЕЙСТВИЯ ДЛЯ ДОКУМЕНТОВ УСЛУГ (Bill creation)
        if analysis.get('should_create_bill') and contact_comparison.exists_in_cache:
            # Проверяем, является ли документ финальным счетом
            if analysis.get('is_final_invoice', False):
                actions.append("📋 Создать BILL в Zoho")
                if analysis.get('suggested_account'):
                    actions.append(f"💼 Account: {analysis.get('suggested_account')}")
            else:
                actions.append("📋 Документ не является финальным счетом")
        elif analysis.get('document_type') in ['delivery_note', 'transport_document', 'cmr']:
            if contact_comparison.exists_in_cache:
                actions.append("📋 Создать BILL для услуги доставки")
            else:
                actions.append("➕ Сначала создайте поставщика")

        return actions

    def generate_telegram_message(self, result: ProcessingResult) -> str:
        """Генерирует сообщение для Telegram с результатами анализа"""

        analysis = result.document_analysis
        comparison = result.contact_comparison
        sku_check = getattr(result, 'sku_check', None)

        print(f"🔍 DEBUG generate_telegram_message: analysis keys = {list(analysis.keys()) if analysis else 'None'}")
        print(f"🔍 DEBUG generate_telegram_message: comparison.exists_in_cache = {comparison.exists_in_cache if comparison else 'None'}")

        if not analysis:
            print("🔍 DEBUG: analysis is None, returning error message")
            return "❌ Анализ документа не удался"

        # Основная информация
        message = "📊 РЕЗУЛЬТАТ ОБРАБОТКИ ДОКУМЕНТА\n\n"
        message += f"🏢 Поставщик: {analysis.get('supplier_name', 'Не определен')}\n"
        
        # Категория документа (человекочитаемый вид)
        if analysis.get('document_category'):
            raw_cat = analysis.get('document_category')
            cat_map = {
                'DocumentCategory.CARS': '🚗 Автомобили', 'CARS': '🚗 Автомобили',
                'DocumentCategory.FLOWERS': '🌸 Цветы', 'FLOWERS': '🌸 Цветы',
                'DocumentCategory.UTILITIES': '💧 Коммунальные услуги', 'UTILITIES': '💧 Коммунальные услуги',
                'DocumentCategory.SERVICES': '🛠️ Услуги', 'SERVICES': '🛠️ Услуги',
                'DocumentCategory.FOOD': '🍎 Продукты питания', 'FOOD': '🍎 Продукты питания',
                'DocumentCategory.OTHER': '📦 Прочие товары', 'OTHER': '📦 Прочие товары'
            }
            readable_cat = cat_map.get(str(raw_cat), str(raw_cat))
            message += f"📋 Категория: {readable_cat}\n"

        print(f"🔍 DEBUG: Поставщик = {analysis.get('supplier_name', 'Не определен')}")

        # Email и телефон
        if analysis.get('supplier_email'):
            message += f"📧 Email: {analysis.get('supplier_email')}\n"
        if analysis.get('supplier_phone'):
            message += f"📞 Телефон: {analysis.get('supplier_phone')}\n"
        if analysis.get('contact_person'):
            message += f"👤 Контакт: {analysis.get('contact_person')}\n"

        # Тип документа
        if analysis.get('document_type_readable'):
            message += f"📄 Тип документа: {analysis.get('document_type_readable')}\n"
        if analysis.get('service_description'):
            message += f"🧾 За что: {analysis.get('service_description')}\n"
        if analysis.get('tax_rate') is not None:
            try:
                tax = float(analysis.get('tax_rate'))
                message += f"💰 Нетто/НДС: {analysis.get('total_amount', 0)} {analysis.get('currency', 'EUR')} • {tax}%\n"
            except Exception:
                message += f"💰 Нетто: {analysis.get('total_amount', 0)} {analysis.get('currency', 'EUR')}\n"

        # Notes для Bill (включая CMR)
        if analysis.get('notes') or analysis.get('notes_for_bill'):
            message += f"📝 Notes: {analysis.get('notes_for_bill') or analysis.get('notes')}\n"
        if analysis.get('additional_documents'):
            try:
                docs = ", ".join(analysis.get('additional_documents') or [])
                if docs:
                    message += f"📎 Docs: {docs}\n"
            except Exception:
                pass

        # Номер и дата документа
        if analysis.get('bill_number'):
            message += f"📄 Документ: {analysis.get('bill_number')}\n"
        if analysis.get('document_date'):
            message += f"📅 Дата: {analysis.get('document_date')}\n"
        if analysis.get('due_date'):
            message += f"⏰ Срок платежа: {analysis.get('due_date')}\n"

        # Выставитель документа
        if analysis.get('issuer_name') or analysis.get('issuer_contact_person'):
            message += "👤 Выставитель: "
            parts = []
            if analysis.get('issuer_name'):
                parts.append(str(analysis.get('issuer_name')))
            if analysis.get('issuer_contact_person'):
                parts.append(str(analysis.get('issuer_contact_person')))
            message += ", ".join(parts) + "\n"
        if analysis.get('issuer_vat'):
            message += f"   🏷️ VAT выставителя: {analysis.get('issuer_vat')}\n"

        # Статус контакта
        if comparison.exists_in_cache:
            message += "✅ Контакт: НАЙДЕН в системе\n"
        else:
            message += "🆕 Контакт: НЕ НАЙДЕН - требуется создание\n"

        # Если tax_rate уже был выведен, повторно сумму не дублируем
        if not analysis.get('tax_rate'):
            message += f"💰 Сумма: {analysis.get('total_amount', 0)} {analysis.get('currency', 'EUR')}\n"

        print(f"🔍 DEBUG: Generated message length = {len(message)}")
        print(f"🔍 DEBUG: Generated message first 200 chars = {message[:200]}")

        # Адрес поставщика (в формате Zoho Books)
        if analysis.get('supplier_address'):
            # Адрес в виде строки
            message += "📍 Адрес: " + str(analysis.get('supplier_address')) + "\n"
        elif analysis.get('supplier_street') or analysis.get('supplier_city'):
            addr_parts = []
            if analysis.get('supplier_street'):
                addr_parts.append(analysis.get('supplier_street'))
            if analysis.get('supplier_zip_code') and analysis.get('supplier_city'):
                addr_parts.append(f"{analysis.get('supplier_zip_code')} {analysis.get('supplier_city')}")
            elif analysis.get('supplier_city'):
                addr_parts.append(analysis.get('supplier_city'))
            if analysis.get('supplier_country'):
                addr_parts.append(analysis.get('supplier_country'))
            message += f"📍 Адрес: {', '.join(addr_parts)}\n"
        else:
            message += "📍 Адрес: Не определен\n"

        # VAT номер (нормализуем по стране документа)
        if analysis.get('supplier_vat'):
            try:
                from src.domain.services.vat_validator import VATValidatorService
                vvs_disp = VATValidatorService()
                country_l = (analysis.get('supplier_country') or (analysis.get('supplier_address') or {}).get('country') or '').strip().lower()
                country_to_iso = {
                    'poland': 'PL', 'polska': 'PL', 'estonia': 'EE', 'eesti': 'EE', 'germany': 'DE',
                    'deutschland': 'DE', 'latvia': 'LV', 'lithuania': 'LT', 'netherlands': 'NL',
                    'ireland': 'IE', 'france': 'FR', 'spain': 'ES', 'italy': 'IT', 'portugal': 'PT',
                    'sweden': 'SE', 'denmark': 'DK', 'united kingdom': 'GB', 'uk': 'GB'
                }
                expected_iso = country_to_iso.get(country_l)
                raw_v = analysis.get('supplier_vat')
                valid = vvs_disp.validate_vat(raw_v, expected_country=expected_iso)
                if valid.is_valid:
                    show_v = vvs_disp.add_country_prefix(valid.vat_number.value, expected_iso or valid.country_code).replace(' ', '')
                else:
                    digits = ''.join(ch for ch in str(raw_v) if ch.isdigit())
                    show_v = f"{expected_iso}{digits}" if expected_iso and digits else str(raw_v)
            except Exception:
                show_v = str(analysis.get('supplier_vat'))
            message += f"🏷️ VAT: {show_v}\n"

        # Уверенность AI
        confidence = analysis.get('confidence', 0.5)
        message += f"🎯 Уверенность AI: {confidence:.1%}\n"

        # УМНАЯ ЛОГИКА СТАТУСА КОНТАКТА НА ОСНОВЕ VAT
        if comparison.exists_in_cache:
            vat_status = getattr(comparison, 'vat_status', 'unknown')
            document_vat = analysis.get('supplier_vat', '')
            cached_vat = ''
            if comparison.cached_contact:
                cached_vat = comparison.cached_contact.get('vat_number', '')

            if vat_status == "match":
                message += "\n✅ КОНТАКТ НАЙДЕН В КЭШЕ"
                message += "\n   ✅ VAT номера совпадают"
            elif vat_status == "missing_in_cache":
                message += "\n✅ КОНТАКТ НАЙДЕН В КЭШЕ"
                message += f"\n   ⚠️ VAT отсутствует в кэше: {document_vat}"
                message += "\n   🎯 Рекомендация: Обновить VAT в Zoho Books"
            elif vat_status == "mismatch":
                message += "\n✅ КОНТАКТ НАЙДЕН В КЭШЕ"
                message += f"\n   ⚠️ VAT не совпадают:"
                message += f"\n      📄 Документ: {document_vat}"
                message += f"\n      💾 Кэш: {cached_vat}"
                message += "\n   🎯 Рекомендация: Разрешить конфликт VAT"
            elif vat_status == "missing_in_document":
                message += "\n✅ КОНТАКТ НАЙДЕН В КЭШЕ"
                message += f"\n   ℹ️ VAT есть в кэше ({cached_vat}), но отсутствует в документе"
            elif vat_status == "both_missing":
                message += "\n✅ КОНТАКТ НАЙДЕН В КЭШЕ"
                message += "\n   ℹ️ VAT отсутствует в обоих местах"
            elif vat_status == "name_mismatch":
                message += "\n⚠️ КОНТАКТ НАЙДЕН ПО VAT, НО С ДРУГИМ НАЗВАНИЕМ"
                message += f"\n   📄 Документ: {analysis.get('supplier_name', 'Unknown')}"
                cached_name = comparison.cached_contact.get('contact_name', 'Unknown') if comparison.cached_contact else 'Unknown'
                message += f"\n   💾 Кэш: {cached_name}"
                message += "\n   🎯 Рекомендация: Проверить переименование компании"
            else:
                message += "\n✅ КОНТАКТ НАЙДЕН В КЭШЕ"
                
            # Показываем другие различия, если есть
            if comparison.differences:
                vat_diff_count = sum(1 for diff in comparison.differences if diff.get('field') == 'vat_number')
                other_diff_count = len(comparison.differences) - vat_diff_count
                if other_diff_count > 0:
                    message += f"\n   📝 Другие различия: {other_diff_count} полей"
        else:
            message += "\n🆕 НОВЫЙ КОНТАКТ"
            # Нормализуем VAT из документа: цифры NIP + ISO-префикс страны
            raw_vat = (analysis.get('supplier_vat') or '').strip()
            country = (analysis.get('supplier_country') or 'Unknown')
            try:
                from src.domain.services.vat_validator import VATValidatorService
                vvs_disp = VATValidatorService()
                # Определяем ожидаемую страну по названию страны поставщика
                country_l = (country or '').strip().lower()
                country_to_iso = {
                    'poland': 'PL', 'polska': 'PL', 'estonia': 'EE', 'eesti': 'EE', 'germany': 'DE',
                    'deutschland': 'DE', 'latvia': 'LV', 'lithuania': 'LT', 'netherlands': 'NL',
                    'ireland': 'IE', 'france': 'FR', 'spain': 'ES', 'italy': 'IT', 'portugal': 'PT',
                    'sweden': 'SE', 'denmark': 'DK', 'united kingdom': 'GB', 'uk': 'GB'
                }
                expected_iso = country_to_iso.get(country_l)
                valid = vvs_disp.validate_vat(raw_vat, expected_country=expected_iso)
                if valid.is_valid:
                    show_vat = vvs_disp.add_country_prefix(valid.vat_number.value, expected_iso or valid.country_code).replace(' ', '')
                else:
                    digits_only = ''.join(ch for ch in raw_vat if ch.isdigit())
                    show_vat = f"{expected_iso}{digits_only}" if expected_iso and digits_only else (raw_vat or 'Отсутствует')
            except Exception:
                show_vat = raw_vat or 'Отсутствует'
            message += f"\n   🏷️ VAT: {show_vat}"
            message += f"\n   🌍 Страна: {country}"

        # Банковские реквизиты (если есть)
        banking_info = []
        if analysis.get('bank_name'):
            banking_info.append(f"🏦 Банк: {analysis.get('bank_name')}")
        if analysis.get('bank_account'):
            banking_info.append(f"💳 Счет: {analysis.get('bank_account')}")
        if analysis.get('bank_address'):
            banking_info.append(f"📍 Адрес банка: {analysis.get('bank_address')}")
        if analysis.get('iban'):
            banking_info.append(f"💳 IBAN: {analysis.get('iban')}")
        if analysis.get('swift_bic'):
            banking_info.append(f"🔗 SWIFT: {analysis.get('swift_bic')}")
        if analysis.get('payment_method'):
            banking_info.append(f"💸 Метод оплаты: {analysis.get('payment_method')}")

        if banking_info:
            message += "\n\n🏦 БАНКОВСКИЕ РЕКВИЗИТЫ:"
            for info in banking_info:
                message += f"\n   {info}"

        # Рекомендуемые действия формируются в Telegram-обработчике после уточнения статуса

        # Автомобильная информация
        if analysis.get('is_car_related'):
            message += "\n\n🚗 АВТОМОБИЛЬНАЯ ИНФОРМАЦИЯ:"
            if analysis.get('car_brand'):
                message += f"\n   Марка: {analysis.get('car_brand')}"
            message += f"\n   Модель: {analysis.get('car_model', 'Не определена')}"
            if analysis.get('vin'):
                message += f"\n   VIN: {analysis.get('vin')}"
            message += f"\n   Item: {analysis.get('car_item_name', 'Не создан')}"
        else:
            # даже если не is_car_related, но VIN найден — добавим отдельной строкой для наглядности
            if analysis.get('vin'):
                message += f"\nVIN: {analysis.get('vin')}"

            # Добавляем правильное описание для ITEM
            if analysis.get('item_description') or analysis.get('item_details'):
                description = analysis.get('item_description') or analysis.get('item_details')
                message += f"\n   Description: {description}"

            # Добавляем SKU если есть
            if analysis.get('item_sku'):
                message += f"\n   SKU: {analysis.get('item_sku')}"

        return message

    async def _save_processed_document(self, file_path: str, analysis: Dict[str, Any]) -> None:
        """Сохраняет обработанный документ в папку processed_files"""
        try:
            # Создаем папку для обработанных файлов, если её нет
            processed_dir = Path("processed_files")
            processed_dir.mkdir(exist_ok=True)

            # Генерируем имя файла с timestamp и информацией о поставщике
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            original_name = Path(file_path).stem

            # Добавляем информацию о поставщике в имя файла
            supplier_name = analysis.get('supplier_name', 'unknown')
            supplier_name_clean = "".join(c for c in supplier_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
            supplier_name_clean = supplier_name_clean.replace(' ', '_')[:30]  # Ограничиваем длину

            new_filename = f"{original_name}_{supplier_name_clean}_{timestamp}.pdf"
            processed_path = processed_dir / new_filename

            # Копируем файл в папку обработанных
            shutil.copy2(file_path, processed_path)

            print(f"✅ Документ сохранен: {processed_path}")

        except Exception as e:
            print(f"❌ Ошибка сохранения документа: {e}")

    async def auto_update_contact(self, comparison: ContactComparison) -> bool:
        """Автоматически обновляет контакт в Zoho и локальных файлах"""
        try:
            if comparison.recommended_action == "create" and comparison.document_data:
                return await self._create_new_contact(comparison.document_data)
            elif comparison.recommended_action == "update":
                return await self._update_existing_contact(comparison)
            return True
        except Exception as e:
            print(f"❌ Ошибка автообновления: {e}")
            return False

    async def _create_new_contact(self, document_data: Dict[str, Any]) -> bool:
        """Создает новый контакт"""
        # Здесь будет логика создания контакта в Zoho
        print(f"➕ Создание нового контакта: {document_data['name']}")
        return True

    async def _update_existing_contact(self, comparison: ContactComparison) -> bool:
        """Обновляет существующий контакт"""
        # Здесь будет логика обновления контакта в Zoho
        print(f"📝 Обновление контакта: {comparison.supplier_name}")
        return True


# Функция для тестирования
async def test_smart_processor():
    """Тест умного процессора"""

    processor = SmartDocumentProcessor()

    # Тестируем с примером
    print("🧪 ТЕСТ УМНОГО ПРОЦЕССОРА ДОКУМЕНТОВ")
    print("=" * 50)

    # Симулируем обработку документа Horrer Automobile
    test_analysis = {
        "ai_enhanced": True,
        "supplier_name": "Horrer Automobile GmbH",
        "supplier_vat": "DE123456789",
        "supplier_address": {
            "country": "DE",
            "city": "Böblingen",
            "address_line1": "Stuttgarter Strasse 116"
        },
        "total_amount": 55369.75,
        "currency": "EUR",
        "confidence": 0.95,
        "is_car_related": True,
        "car_model": "Mercedes V 300 d",
        "car_item_name": "Mercedes V 300 d_26375"
    }

    # Создаем результат для тестирования
    comparison = await processor._compare_supplier_with_cache(test_analysis)

    result = ProcessingResult(
        success=True,
        document_analysis=test_analysis,
        contact_comparison=comparison,
        suggested_actions=processor._determine_actions(comparison, test_analysis)
    )

    # Генерируем сообщение для Telegram
    telegram_message = processor.generate_telegram_message(result)
    print(telegram_message)


if __name__ == "__main__":
    asyncio.run(test_smart_processor()) 