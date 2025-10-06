"""
Universal Supplier Creator
Универсальная функция создания поставщиков для всех модулей проекта
"""

import logging
from typing import Dict, Optional, Tuple
from functions.contact_creator import create_supplier_from_document

logger = logging.getLogger(__name__)


async def create_supplier_universal(analysis: Dict, org_id: str) -> Optional[Dict]:
    """
    Универсальная функция создания поставщика из анализа документа
    
    Использует правильную логику из contact_creator.py с разделением адреса на поля
    Может вызываться из любого модуля: WorkDrive, Telegram, Universal Processor
    
    Args:
        analysis: Результат анализа документа LLM
        org_id: ID организации Zoho
        
    Returns:
        Dict с данными созданного поставщика или None при ошибке
    """
    try:
        # Подготавливаем данные в формате, ожидаемом contact_creator.py
        document_data = {
            # Основные данные поставщика
            'supplier_name': analysis.get('supplier_name'),
            'supplier_vat': analysis.get('supplier_vat'),
            'supplier_email': analysis.get('supplier_email'),
            'supplier_phone': analysis.get('supplier_phone'),
            'supplier_address': analysis.get('supplier_address'),
            
            # Структурированный адрес из LLM (приоритет)
            'supplier_street': analysis.get('supplier_street'),
            'supplier_city': analysis.get('supplier_city'),
            'supplier_zip_code': analysis.get('supplier_zip_code'),
            'supplier_country': analysis.get('supplier_country') or 'Poland',
            
            # Банковские реквизиты
            'bank_name': analysis.get('bank_name'),
            'iban': analysis.get('iban'),
            'bank_account': analysis.get('bank_account'),
            'swift_bic': analysis.get('swift_bic'),
            
            # Контактное лицо
            'contact_person': analysis.get('contact_person'),
            'issuer_contact_person': analysis.get('issuer_contact_person'),
            
            # Целевая организация
            'target_org_id': org_id,
            
            # Дополнительные данные для анализа
            'extracted_text': analysis.get('extracted_text', ''),
            'our_company': analysis.get('our_company', ''),
            'tax_rate': analysis.get('tax_rate'),
            
            # Валюта из документа
            'currency': analysis.get('currency'),
            'document_currency': analysis.get('document_currency')
        }
        
        # Логируем что создаем поставщика
        supplier_name = analysis.get('supplier_name', 'Unknown')
        supplier_vat = analysis.get('supplier_vat', 'Unknown')
        
        logger.info(f"🏢 UNIVERSAL_SUPPLIER_CREATOR: создаем {supplier_name}")
        logger.info(f"🆔 VAT: {supplier_vat}, org_id: {org_id}")
        
        # Используем проверенную логику из contact_creator.py
        success, message = await create_supplier_from_document(document_data)
        
        if success:
            logger.info(f"✅ UNIVERSAL_SUPPLIER_CREATOR: {message}")
            
            # Возвращаем базовые данные созданного контакта
            return {
                'contact_id': None,  # contact_creator.py не возвращает ID
                'contact_name': supplier_name,
                'vat_number': supplier_vat,
                'status': 'created_via_universal_creator'
            }
        else:
            logger.error(f"❌ UNIVERSAL_SUPPLIER_CREATOR: {message}")
            return None
            
    except Exception as e:
        logger.error(f"❌ UNIVERSAL_SUPPLIER_CREATOR exception: {e}")
        return None


def get_proper_address_from_analysis(analysis: Dict) -> Dict:
    """
    Извлекает правильно структурированный адрес из анализа документа
    
    Returns:
        Dict с полями address, city, zip, country
    """
    # Получаем данные адреса
    street_llm = analysis.get("supplier_street") or ""
    city_llm = analysis.get("supplier_city") or ""  
    zip_llm = analysis.get("supplier_zip_code") or analysis.get("zip_code") or ""
    country_llm = analysis.get("supplier_country") or "Poland"
    
    doc_address = analysis.get('supplier_address') or analysis.get('address') or ""
    
    if street_llm or city_llm or zip_llm:
        # LLM предоставил структурированный адрес
        return {
            "address": street_llm or doc_address,
            "city": city_llm,
            "zip": zip_llm,
            "country": country_llm
        }
    elif doc_address:
        # Пытаемся разобрать строковый адрес
        address_parts = [p.strip() for p in doc_address.split(',')]
        if len(address_parts) >= 3:
            return {
                "address": address_parts[0],
                "city": address_parts[1],
                "zip": zip_llm or "",
                "country": country_llm
            }
        else:
            return {
                "address": doc_address,
                "city": "",
                "zip": "",
                "country": country_llm
            }
    else:
        return {
            "address": "",
            "city": "",
            "zip": "",
            "country": country_llm
        }


# Для обратной совместимости с existing кодом
create_supplier_from_analysis = create_supplier_universal

