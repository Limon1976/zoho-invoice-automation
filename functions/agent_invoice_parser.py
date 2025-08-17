import os
import json
import time
import logging
import re
from openai import OpenAI, APIConnectionError
from requests.exceptions import RequestException
from dotenv import load_dotenv

from functions.assistant_logic import process_invoice_json, process_proforma_json, SYSTEM_PROMPT, detect_account
from functions.llm_document_extractor import llm_extract_fields, llm_analyze_contract_risks
from functions.zoho_api import get_existing_bill_numbers
from mcp_connector.pdf_parser import extract_text_from_pdf

load_dotenv()
# Логи настраиваются централизованно в telegram_bot/bot_main.py

# Наши компании - только основные варианты (VAT решает!)
OUR_COMPANIES = [
    {"name": "TaVie Europe OÜ", "vat": "EE102288270"},
    {"name": "Parkentertainment Sp. z o.o.", "vat": "PL5272956146"},
]

def is_our_company(name: str, vat: str) -> bool:
    """
    Проверяет, является ли компания нашей.
    ПРИОРИТЕТ: VAT номер - это решающий критерий!
    Названия могут содержать опечатки, но VAT всегда точный.
    """
    # Нормализуем VAT для сравнения (убираем пробелы, приводим к верхнему регистру)
    vat_normalized = vat.replace(" ", "").replace("-", "").upper() if vat else ""
    
    for comp in OUR_COMPANIES:
        comp_vat_normalized = comp["vat"].replace(" ", "").replace("-", "").upper()
        
        # 1. ПРИОРИТЕТ: Проверка по VAT (точное совпадение)
        if vat_normalized and vat_normalized == comp_vat_normalized:
            return True
        
        # 2. Проверка по VAT без префикса (например, "5272956146" vs "PL5272956146")
        if vat_normalized and len(vat_normalized) >= 7:
            # Убираем префикс из нашего VAT для сравнения
            comp_vat_digits = re.sub(r'^[A-Z]{2}', '', comp_vat_normalized)
            if vat_normalized == comp_vat_digits or comp_vat_normalized == vat_normalized:
                return True
        
        # 3. FALLBACK: Проверка по имени (только если VAT отсутствует)
        # Используется только как fallback, когда VAT данные отсутствуют
        if name and not vat_normalized:  # Только если VAT отсутствует
            name_variants = normalize_company_name_for_comparison(name)
            comp_variants = normalize_company_name_for_comparison(comp["name"])
            
            if name_variants == comp_variants:
                logging.info(f"✅ Компания найдена по названию (fallback): {name}")
                return True
    
    return False

def normalize_company_name_for_comparison(name: str) -> str:
    """Нормализует название компании для более гибкого сравнения"""
    if not name:
        return ""
    
    name = name.lower().strip()
    
    # Заменяем диакритические знаки на обычные буквы
    replacements = {
        'ü': 'u', 'ö': 'o', 'ä': 'a', 'ß': 'ss',
        'ç': 'c', 'ñ': 'n', 'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
        'à': 'a', 'á': 'a', 'â': 'a', 'ã': 'a', 'å': 'a',
        'ì': 'i', 'í': 'i', 'î': 'i', 'ï': 'i',
        'ò': 'o', 'ó': 'o', 'ô': 'o', 'õ': 'o', 'ø': 'o',
        'ù': 'u', 'ú': 'u', 'û': 'u',
        'ý': 'y', 'ÿ': 'y'
    }
    
    for original, replacement in replacements.items():
        name = name.replace(original, replacement)
    
    # Добавляем польские символы
    polish_chars = {
        'ł': 'l', 'ą': 'a', 'ć': 'c', 'ę': 'e', 'ń': 'n', 'ó': 'o',
        'ś': 's', 'ź': 'z', 'ż': 'z'
    }
    for original, replacement in polish_chars.items():
        name = name.replace(original, replacement)
    
    # Стандартизируем юридические формы
    legal_forms = {
        'oü': 'ou',  # Эстонские компании
        'o.ü.': 'ou',
        'sp. z o.o.': 'spzoo',
        'sp.z o.o.': 'spzoo',
        'sp z o.o.': 'spzoo',
        'sp z o o': 'spzoo',
        'spolka z o.o.': 'spzoo',
        'spółka z o.o.': 'spzoo',
        'spółka z ograniczoną odpowiedzialnością': 'spzoo',
        'spółka z ograniczona odpowiedzialnoscia': 'spzoo',
        'limited': 'ltd',
        'corporation': 'corp',
        'incorporated': 'inc',
        'gesellschaft mit beschränkter haftung': 'gmbh'
    }
    
    for original, replacement in legal_forms.items():
        name = name.replace(original, replacement)
    
    # Убираем лишние пробелы и знаки препинания
    name = re.sub(r'[^\w\s]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    
    return name

def extract_legal_entity_and_vat_excluding_our_companies(text: str) -> tuple[str, str]:
    """
    Поиск юридического лица и VAT, исключая наши компании.
    Возвращает (название_компании, vat/tax_number)
    """
    lines = text.splitlines()
    found_companies = []
    
    # Все возможные обозначения VAT/налоговых номеров на разных языках
    tax_keywords = [
        # Английский
        r'VAT', r'VAT ID', r'VAT NUMBER', r'TAX ID', r'TAX NUMBER', r'(?:US )?EIN',
        r'VAT reg\. no', r'VAT registration no',
        # Польский  
        r'NIP', r'Nr VAT', r'Numer VAT',
        # Немецкий
        r'USt-IdNr', r'Umsatzsteuer-ID', r'Steuernummer',
        # Французский
        r'TVA', r'Numéro TVA', r'N° TVA',
        # Испанский
        r'CIF', r'NIF', r'IVA',
        # Итальянский
        r'P\.IVA', r'Partita IVA',
        # Эстонский
        r'KMKR', r'KM reg',
        # Латышский
        r'PVN', r'PVN reģ',
        # Литовский
        r'PVM', r'PVM kodas',
        # Чешский
        r'DIČ', r'DPH',
        # Венгерский
        r'ÁFÁSZ',
        # Русский
        r'НДС', r'ИНН', r'Налоговый номер',
        # Шведский
        r'Corporate id no', r'Org\.nr', r'Organisationsnummer'
    ]
    
    # Сначала ищем все полные номера с префиксом (например, "PL 5273095344")
    for line in lines:
        full_vat_match = re.search(r'([A-Z]{2}[ \-\.]*[0-9]{7,15})', line)
        if full_vat_match:
            vat_candidate = full_vat_match.group(1)
            vat_clean = re.sub(r'[ \-\.]', '', vat_candidate)
            if len(re.sub(r'[^0-9]', '', vat_clean)) >= 7:
                # Ищем название компании для этого VAT
                company_name = find_company_name_for_vat(lines, vat_clean)
                if company_name and not is_our_company(company_name, vat_clean):
                    found_companies.append((company_name, vat_clean))
    
    # Ищем VAT в одной строке с ключевыми словами
    tax_pattern = r'(?:' + '|'.join(tax_keywords) + r')[ :\-\.]*([A-Z]{0,2}[ \-\.]*[0-9]{4,15})'
    for i, line in enumerate(lines):
        tax_match = re.search(tax_pattern, line, re.IGNORECASE)
        if tax_match:
            vat_raw = tax_match.group(1).strip()
            # Для EIN убираем дефисы, для остальных оставляем как есть
            if 'EIN' in line.upper():
                vat_clean = re.sub(r'[ \-\.]', '', vat_raw)
            else:
                vat_clean = re.sub(r'(?<=[A-Z])[ \-\.](?=[0-9])', '', vat_raw)
                vat_clean = re.sub(r'(?<=[0-9])[ \-\.](?=[0-9])', '', vat_clean)
            
            if len(re.sub(r'[^0-9]', '', vat_clean)) >= 4:
                company_name = find_company_name_for_vat(lines, vat_clean)
                if company_name and not is_our_company(company_name, vat_clean):
                    found_companies.append((company_name, vat_clean))
    
    # Ищем ключевое слово и номер в соседних строках
    for i, line in enumerate(lines):
        if re.match(r'^\s*(?:' + '|'.join(tax_keywords) + r')\s*$', line, re.IGNORECASE):
            for j in range(i+1, min(i+4, len(lines))):
                next_line = lines[j].strip()
                vat_match = re.search(r'^([A-Z]{0,2}[ \-\.]*[0-9]{4,15})$', next_line)
                if vat_match:
                    vat_raw = vat_match.group(1).strip()
                    vat_clean = re.sub(r'[ \-\.]', '', vat_raw)
                    if len(re.sub(r'[^0-9]', '', vat_clean)) >= 4:
                        company_name = find_company_name_for_vat(lines, vat_clean)
                        if company_name and not is_our_company(company_name, vat_clean):
                            found_companies.append((company_name, vat_clean))
    
    # Специальный поиск для US EIN (может быть записан как "US EIN 87-4436547")
    us_ein_pattern = r'(?:US )?EIN[ :\-]*([0-9\-]{9,12})'
    for i, line in enumerate(lines):
        ein_match = re.search(us_ein_pattern, line, re.IGNORECASE)
        if ein_match:
            ein_raw = ein_match.group(1).strip()
            ein_clean = re.sub(r'[ \-\.]', '', ein_raw)
            if len(re.sub(r'[^0-9]', '', ein_clean)) >= 9:  # EIN должен содержать 9 цифр
                company_name = find_company_name_for_vat(lines, ein_clean)
                if company_name and not is_our_company(company_name, ein_clean):
                    found_companies.append((company_name, ein_clean))
    
    # Возвращаем первую найденную компанию, которая не является нашей
    if found_companies:
        return found_companies[0]
    
    return "", ""

def find_company_name_for_vat(lines: list, vat: str) -> str:
    """
    Находит название компании для указанного VAT номера
    """
    # Находим строку с VAT (поиск по полному номеру и только по цифрам)
    vat_line_index = -1
    vat_digits = re.sub(r'[^0-9]', '', vat)
    
    for i, line in enumerate(lines):
        # Ищем точное совпадение или совпадение только по цифрам
        if vat in line:
            vat_line_index = i
            break
        # Извлекаем цифры из строки и сравниваем
        line_digits = re.sub(r'[^0-9]', '', line)
        if vat_digits and line_digits and vat_digits in line_digits:
            vat_line_index = i
            break
    
    potential_companies = []
    
    # Ищем компании во всем документе, но с приоритетом для разных областей
    for j, company_line in enumerate(lines):
        company_line = company_line.strip()
        if not company_line:
            continue
            
        # Пропускаем служебные строки
        if re.search(r'^(e-mail:|tel\.|phone|fax|website|www\.|http|№|nr\.|no\.|number)', company_line, re.IGNORECASE):
            continue
        if re.search(r'^(kraj|country|POLSKA|POLAND|USA|United States|Deutschland|France|España|Italia|Россия|Sweden|Sverige|Estonia)', company_line, re.IGNORECASE):
            continue
        if re.search(r'^(\d+$|\d+\.\d{2}$|^@|Invoice|Page|\d{4}-\d{2}-\d{2})', company_line):
            continue
        # Пропускаем строки только с VAT keywords
        if re.search(r'^(VAT|NIP|Corporate id no|Org\.nr|Tax|Registration|VAT reg\. no)[ \.\:]*$', company_line, re.IGNORECASE):
            continue
        # Пропускаем банковские и платежные реквизиты
        if re.search(r'^(IBAN|BIC|Swift|Plusgiro|Bankgiro|Account|Bank|DUE PAYMENT)', company_line, re.IGNORECASE):
            continue
            
        # Пропускаем адреса и почтовые индексы
        if re.search(r'^\d+\s+(ul\.|street|str\.|avenue|ave\.|road|rd\.)', company_line, re.IGNORECASE):
            continue
        if re.search(r'^\d{2,5}[\s\-]\d{2,5}', company_line):  # почтовые индексы
            continue
        # Пропускаем строки, которые выглядят как адреса (начинаются с цифр и содержат город)
        if re.search(r'^\d+.*?(tallinn|kalmar|warszawa|berlin|stockholm)', company_line, re.IGNORECASE):
            continue
        # Пропускаем строки с только цифрами или короткие аббревиатуры
        if re.search(r'^\d+\s*\w{1,3}\s*$', company_line) or len(company_line.replace(' ', '')) < 4:
            continue
        
        # Ищем название компании
        if re.search(r'[A-Za-zА-Яа-яÀ-ÿ]{2,}', company_line) and len(company_line) > 2:
            priority = 0
            
            # Высокий приоритет: компании с типичными окончаниями
            company_suffixes = r'(Sp\. z o\.o\.|Ltd|Inc|GmbH|LLC|Corp|SA|SRL|OÜ|Oy|SIA|UAB|AS|AB|BV|NV|SARL|SAS|Srl|SpA|AG|KG|OHG|eV|Kft|Zrt|d\.o\.o\.|s\.r\.o\.)'
            if re.search(company_suffixes, company_line, re.IGNORECASE):
                priority = 10
            # Средний приоритет: строки без служебных слов
            elif not re.search(r'(\d{5,}|@|\+\d|bank|account|iban|VAT|Corporate id|Tax|Invoice|Page|Payment|Total|Amount|Date|Cust)', company_line, re.IGNORECASE):
                # Проверяем, не является ли это просто служебным словом
                if company_line.lower() not in ['corporate id no', 'vat reg. no', 'tax id', 'registration no', 'address', 'phone', 'e-mail', 'web address']:
                    # Особый случай: если это просто одно слово и в верхней части документа (может быть брендом)
                    words = company_line.split()
                    if len(words) == 1 and j < len(lines) // 4:  # Первая четверть документа
                        priority = 7
                    # Дополнительный приоритет для названий в верхней части документа
                    elif j < len(lines) // 3:  # Первая треть документа
                        priority = 8
                    else:
                        priority = 5
            
            # Дополнительный приоритет, если это рядом с VAT
            if vat_line_index >= 0 and abs(j - vat_line_index) <= 5:
                priority += 2
            
            if priority > 0:
                potential_companies.append((company_line, priority, j))
    
    # Сортируем по приоритету, затем по позиции в документе
    if potential_companies:
        potential_companies.sort(key=lambda x: (x[1], -x[2]), reverse=True)
        return potential_companies[0][0]
    
    return ""

def extract_legal_entity_and_vat(text: str) -> tuple[str, str]:
    """
    Универсальный поиск юридического лица и VAT/налогового номера.
    Поддерживает все страны и языки.
    Возвращает (название_компании, vat/tax_number)
    """
    lines = text.splitlines()
    found_company = ""
    found_vat = ""
    
    # Все возможные обозначения VAT/налоговых номеров на разных языках
    tax_keywords = [
        # Английский
        r'VAT', r'VAT ID', r'VAT NUMBER', r'TAX ID', r'TAX NUMBER', r'US EIN', r'EIN',
        # Польский  
        r'NIP', r'Nr VAT', r'Numer VAT',
        # Немецкий
        r'USt-IdNr', r'Umsatzsteuer-ID', r'Steuernummer',
        # Французский
        r'TVA', r'Numéro TVA', r'N° TVA',
        # Испанский
        r'CIF', r'NIF', r'IVA',
        # Итальянский
        r'P\.IVA', r'Partita IVA',
        # Эстонский
        r'KMKR', r'KM reg',
        # Латышский
        r'PVN', r'PVN reģ',
        # Литовский
        r'PVM', r'PVM kodas',
        # Чешский
        r'DIČ', r'DPH',
        # Венгерский
        r'ÁFASZ',
        # Русский
        r'НДС', r'ИНН', r'Налоговый номер'
    ]
    
    # Создаем паттерн для поиска любого налогового номера в одной строке
    tax_pattern = r'(?:' + '|'.join(tax_keywords) + r')[ :\-\.]*([A-Z]{0,2}[ \-\.]*[0-9]{4,15})'
    
    # Сначала ищем полные номера с префиксом (например, "PL 5273095344")
    for line in lines:
        # Ищем строки с полным VAT номером (с префиксом страны)
        full_vat_match = re.search(r'([A-Z]{2}[ \-\.]*[0-9]{7,15})', line)
        if full_vat_match:
            vat_candidate = full_vat_match.group(1)
            vat_clean = re.sub(r'[ \-\.]', '', vat_candidate)
            if len(re.sub(r'[^0-9]', '', vat_clean)) >= 7:  # Минимум 7 цифр для полного VAT
                found_vat = vat_clean
                break
    
    # Если не нашли полный VAT, ищем в одной строке
    if not found_vat:
        for i, line in enumerate(lines):
            tax_match = re.search(tax_pattern, line, re.IGNORECASE)
            if tax_match:
                vat_raw = tax_match.group(1).strip()
                vat_clean = re.sub(r'(?<=[A-Z])[ \-\.](?=[0-9])', '', vat_raw)
                vat_clean = re.sub(r'(?<=[0-9])[ \-\.](?=[0-9])', '', vat_clean)
                
                if len(re.sub(r'[^0-9]', '', vat_clean)) >= 4:
                    found_vat = vat_clean
                    break
    
    # Если не нашли VAT в одной строке, ищем ключевое слово и номер в соседних строках
    if not found_vat:
        for i, line in enumerate(lines):
            # Ищем строку только с ключевым словом
            if re.match(r'^\s*(?:' + '|'.join(tax_keywords) + r')\s*$', line, re.IGNORECASE):
                # Проверяем следующие 3 строки на наличие номера
                for j in range(i+1, min(i+4, len(lines))):
                    next_line = lines[j].strip()
                    # Ищем номер (с префиксом или без)
                    vat_match = re.search(r'^([A-Z]{0,2}[ \-\.]*[0-9]{4,15})$', next_line)
                    if vat_match:
                        vat_raw = vat_match.group(1).strip()
                        vat_clean = re.sub(r'[ \-\.]', '', vat_raw)
                        if len(re.sub(r'[^0-9]', '', vat_clean)) >= 4:
                            found_vat = vat_clean
                            break
                if found_vat:
                    break
    
    # Если нашли VAT, ищем название компании в предыдущих строках
    if found_vat:
        # Находим строку с VAT
        vat_line_index = -1
        for i, line in enumerate(lines):
            if found_vat in line or re.sub(r'[^0-9]', '', found_vat) in line:
                vat_line_index = i
                break
        
        if vat_line_index >= 0:
            # Ищем название компании в предыдущих строках
            for j in range(vat_line_index-1, max(vat_line_index-15, -1), -1):
                company_line = lines[j].strip()
                if not company_line:
                    continue
                    
                # Пропускаем служебные строки
                if re.search(r'^(e-mail:|tel\.|phone|fax|website|www\.|http|№|nr\.|no\.|number)', company_line, re.IGNORECASE):
                    continue
                if re.search(r'^(kraj|country|POLSKA|POLAND|USA|United States|Deutschland|France|España|Italia|Россия)', company_line, re.IGNORECASE):
                    continue
                if re.search(r'^(\d+$|\d+\.\d{2}$|^@)', company_line):
                    continue
                    
                # Пропускаем адреса
                if re.search(r'(ul\.|street|str\.|avenue|ave\.|road|rd\.|nr\.|lok\.|apt\.|suite|kod|zip|\d{2}-\d{3}|\d{5})', company_line, re.IGNORECASE):
                    continue
                
                # Ищем название компании
                if re.search(r'[A-Za-zА-Яа-яÀ-ÿ]{3,}', company_line) and len(company_line) > 5:
                    # Приоритет компаниям с типичными окончаниями
                    company_suffixes = r'(Sp\. z o\.o\.|Ltd|Inc|GmbH|LLC|Corp|SA|SRL|OÜ|Oy|SIA|UAB|AS|AB|BV|NV|SARL|SAS|Srl|SpA|AG|KG|OHG|eV|Kft|Zrt|d\.o\.o\.|s\.r\.o\.)'
                    if re.search(company_suffixes, company_line, re.IGNORECASE):
                        found_company = company_line
                        break
                    # Или содержательная строка без служебных элементов
                    elif not re.search(r'(\d{5,}|@|\+\d|bank|account|iban)', company_line, re.IGNORECASE):
                        if not found_company:  # Берем первую подходящую
                            found_company = company_line
    
    # Fallback: ищем VAT отдельно по всему документу
    if found_company and not found_vat:
        # Расширенные паттерны для поиска VAT (с сохранением префикса)
        fallback_patterns = [
            r'([A-Z]{2}[ \-]*[0-9]{7,15})',  # Европейский формат: DE123456789, PL 1234567890
            r'([0-9]{7,15})',                # Только цифры: 1234567890
            r'EIN[ :\-]*([0-9\-]{9,12})',    # US EIN: 12-3456789
            r'ИНН[ :\-]*([0-9]{10,12})',     # Российский ИНН
        ]
        
        for pattern in fallback_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                # Для европейского формата сохраняем префикс
                if re.match(r'^[A-Z]{2}', match):
                    clean_vat = re.sub(r'[ \-\.]', '', match)
                else:
                    clean_vat = re.sub(r'[ \-\.]', '', match)
                    
                if len(re.sub(r'[^0-9]', '', clean_vat)) >= 4:
                    found_vat = clean_vat
                    break
            if found_vat:
                break
    
    return found_company, found_vat

def extract_supplier_address(ocr_text: str, supplier_name: str) -> tuple[str, str]:
    """
    Извлекает адрес и страну поставщика из OCR текста
    Возвращает (address, country)
    """
    if not supplier_name or not ocr_text:
        return "", ""
    
    lines = ocr_text.splitlines()
    supplier_line_index = -1
    
    # Ищем строку с названием поставщика
    for i, line in enumerate(lines):
        if supplier_name.lower() in line.lower():
            supplier_line_index = i
            break
    
    if supplier_line_index == -1:
        return "", ""
    
    # Ищем адрес в следующих строках после названия поставщика
    address_parts = []
    country = ""
    
    # Список стран для определения
    countries = [
        "Sweden", "Sverige", "Poland", "Polska", "Germany", "Deutschland", 
        "Estonia", "Eesti", "Latvia", "Latvija", "Lithuania", "Lietuva",
        "Finland", "Suomi", "Denmark", "Danmark", "Norway", "Norge",
        "France", "Frankreich", "Spain", "España", "Italy", "Italia",
        "Netherlands", "Nederland", "Belgium", "België", "Austria", "Österreich",
        "Czech Republic", "Czechia", "Slovakia", "Hungary", "Magyarország",
        "USA", "United States", "Canada", "UK", "United Kingdom"
    ]
    
    # Проверяем строки после названия поставщика (до 10 строк)
    for i in range(supplier_line_index + 1, min(supplier_line_index + 11, len(lines))):
        line = lines[i].strip()
        if not line:
            continue
            
        # Пропускаем служебные строки
        if re.search(r'^(phone|tel|fax|email|e-mail|website|www|vat|tax|invoice|total|amount)', line, re.IGNORECASE):
            break
        
        # Проверяем, не является ли это страной
        line_is_country = False
        for country_name in countries:
            if country_name.lower() == line.lower():
                country = country_name
                line_is_country = True
                break
        
        if line_is_country:
            continue
            
        # Пропускаем строки с только цифрами или VAT номерами
        if re.match(r'^\d+$', line) or re.match(r'^[A-Z]{2}\d+$', line):
            continue
            
        # Добавляем в адрес
        address_parts.append(line)
        
        # Если нашли строку со страной внутри, извлекаем её
        for country_name in countries:
            if country_name.lower() in line.lower():
                country = country_name
                break
    
    # Объединяем части адреса
    address = ", ".join(address_parts) if address_parts else ""
    
    return address, country

def extract_supplier_email(text: str) -> str:
    """
    Ищет email поставщика во всём документе
    """
    # Ищем все email адреса в документе
    email_pattern = r'[\w\.-]+@[\w\.-]+\.\w+'
    emails = re.findall(email_pattern, text)
    
    if not emails:
        return ""
    
    # Если только один email - возвращаем его
    if len(emails) == 1:
        return emails[0]
    
    # Если несколько email'ов, пытаемся найти тот, который относится к поставщику
    text_lines = text.splitlines()
    
    # Ключевые слова наших компаний для исключения
    our_companies_keywords = ['tavie', 'parkentertainment']
    
    for email in emails:
        email_lower = email.lower()
        # Пропускаем email'ы наших компаний
        if any(keyword in email_lower for keyword in our_companies_keywords):
            continue
        
        # Ищем контекст вокруг email'а
        for i, line in enumerate(text_lines):
            if email in line:
                # Проверяем несколько строк вокруг email'а
                context_lines = []
                for j in range(max(0, i-3), min(len(text_lines), i+4)):
                    context_lines.append(text_lines[j].lower())
                context = " ".join(context_lines)
                
                # Если в контексте нет упоминаний наших компаний, считаем это email поставщика
                if not any(keyword in context for keyword in our_companies_keywords):
                    return email
    
    # Если не удалось определить по контексту, возвращаем первый email
    return emails[0]

def extract_full_car_price(ocr_text: str, current_amount: float) -> float:
    """
    Извлекает полную стоимость автомобиля из документа (до вычета предоплат).
    Ищет строки с "Total", "Amount", "Gesamtbetrag" которые идут ДО строк с "Less", "Down payment", etc.
    """
    if not ocr_text or not current_amount:
        return current_amount
    
    lines = ocr_text.splitlines()
    amounts = []
    
    # Ищем все суммы в документе
    for i, line in enumerate(lines):
        line_clean = line.strip()
        
        # Пропускаем строки с вычетами/доплатами
        if re.search(r'(?:less|down payment|anzahlung|acompte|предоплата|minus|abzug)', line_clean, re.IGNORECASE):
            continue
        
        # Ищем строки с общей суммой
        if re.search(r'(?:total|amount|gesamtbetrag|итого|сумма)[^a-zA-Z]*[:]*', line_clean, re.IGNORECASE):
            # Ищем число в этой строке или в следующих строках
            for j in range(i, min(i + 3, len(lines))):
                check_line = lines[j].strip()
                # Ищем большие суммы (больше 1000) в формате европейских цен
                money_match = re.search(r'([0-9]{1,3}(?:[.,][0-9]{3})*(?:[.,][0-9]{2})?)', check_line)
                if money_match:
                    amount_str = money_match.group(1)
                    # Нормализуем формат (европейский формат: 251.933,00 или 251,933.00)
                    if ',' in amount_str and '.' in amount_str:
                        # Если есть и запятая и точка, предполагаем европейский формат
                        if amount_str.rindex(',') > amount_str.rindex('.'):
                            # Запятая после точки - европейский формат: 251.933,00
                            amount_str = amount_str.replace('.', '').replace(',', '.')
                        else:
                            # Точка после запятой - американский формат: 251,933.00
                            amount_str = amount_str.replace(',', '')
                    elif ',' in amount_str and len(amount_str.split(',')[-1]) == 2:
                        # Только запятая как десятичный разделитель: 251933,00
                        amount_str = amount_str.replace(',', '.')
                    elif '.' in amount_str and len(amount_str.split('.')[-1]) == 3:
                        # Точка как разделитель тысяч: 251.933
                        amount_str = amount_str.replace('.', '')
                    
                    try:
                        amount = float(amount_str)
                        if amount > 1000 and amount != current_amount:  # Исключаем мелкие суммы и текущую сумму
                            amounts.append(amount)
                    except ValueError:
                        continue
    
    # Возвращаем максимальную найденную сумму (обычно это полная стоимость)
    if amounts:
        max_amount = max(amounts)
        # Проверяем, что найденная сумма больше текущей (логично для полной стоимости vs суммы к доплате)
        if max_amount > current_amount:
            return max_amount
    
    return current_amount

def enhance_car_details_for_purchase(item_details: str, vin: str, car_model: str, ocr_text: str) -> str:
    """
    Расширяет item_details для покупки автомобиля, добавляя VIN и дополнительные детали из документа
    (цвет, пробег, год и т.д.)
    """
    if not vin:
        return item_details
    
    # Начинаем с базового описания (модель автомобиля или текущего item_details)
    base_description = car_model if car_model else item_details
    if not base_description:
        base_description = "Автомобиль"
    
    # Добавляем VIN
    enhanced_details = f"{base_description}, VIN: {vin}"
    
    # Ищем дополнительные детали в OCR
    lines = ocr_text.splitlines()
    additional_details = []
    
    for line in lines:
        line_clean = line.strip()
        
        # Ищем цвет (Exterieur, Color, etc.)
        color_match = re.search(r'(?:exterieur|color|colour|farbe|couleur|цвет)[:\s]*([a-zA-Zа-яёА-ЯЁ\s]+)', line_clean, re.IGNORECASE)
        if color_match:
            color = color_match.group(1).strip()
            if color and len(color) < 30 and not any(color.lower() in detail.lower() for detail in additional_details):
                additional_details.append(f"Color: {color}")
        
        # Ищем пробег (Km, Mileage, etc.)
        mileage_match = re.search(r'(?:km|miles|mileage|пробег)[.:\s]*([0-9,.]+)(?:\s*(?:km|miles|миль|км))?', line_clean, re.IGNORECASE)
        if mileage_match:
            mileage = mileage_match.group(1).strip()
            if mileage and not any("mileage" in detail.lower() or "km" in detail.lower() for detail in additional_details):
                additional_details.append(f"Mileage: {mileage} km")
        
        # Ищем год (EZ, Year, Baujahr, etc.)
        year_match = re.search(r'(?:ez|year|baujahr|année|год)[:\s]*([0-9]{4})', line_clean, re.IGNORECASE)
        if year_match:
            year = year_match.group(1).strip()
            if year and not any("year" in detail.lower() for detail in additional_details):
                additional_details.append(f"Year: {year}")
        
        # Ищем тип двигателя или объем
        engine_match = re.search(r'([0-9]+[.,][0-9]+\s*(?:l|liter|литр))', line_clean, re.IGNORECASE)
        if engine_match:
            engine = engine_match.group(1).strip()
            if engine and not any("engine" in detail.lower() for detail in additional_details):
                additional_details.append(f"Engine: {engine}")
    
    # Добавляем найденные детали
    if additional_details:
        enhanced_details += ", " + ", ".join(additional_details)
    
    return enhanced_details

def extract_service_description(ocr_text: str) -> str:
    """
    Извлекает описание услуги из OCR текста.
    Ищет строки с ключевыми словами услуг.
    """
    if not ocr_text:
        return ""
    
    lines = ocr_text.splitlines()
    
    # Ключевые слова для поиска услуг
    service_keywords = [
        "pervežimo", "paslauga", "service", "transport", "shipping", "delivery",
        "доставка", "услуга", "перевозка", "ремонт", "repair", "maintenance",
        "przewóz", "dostawa", "usługa", "serwis", "naprawa"
    ]
    
    # Ищем строки с описанием услуг
    for line in lines:
        line_clean = line.strip()
        if not line_clean or len(line_clean) < 5:
            continue
            
        # Пропускаем строки с только цифрами, VAT номерами и т.д.
        if re.match(r'^\d+$', line_clean) or re.match(r'^[A-Z]{2}\d+$', line_clean):
            continue
        if re.match(r'^[A-HJ-NPR-Z0-9]{17}$', line_clean):  # VIN номер
            continue
        if re.search(r'^(VAT|NIP|Email|Tel|Phone|Fax|IBAN|BIC)', line_clean, re.IGNORECASE):
            continue
            
        # Проверяем наличие ключевых слов услуг
        line_lower = line_clean.lower()
        for keyword in service_keywords:
            if keyword in line_lower:
                # Если нашли строку с описанием услуги, возвращаем её
                return line_clean
    
    return ""

def is_car_purchase_vs_service(item_details: str, ocr_text: str) -> bool:
    """
    Определяет, покупаем ли мы автомобили или оплачиваем услуги по автомобилям.
    Возвращает True если покупка машин, False если услуга
    """
    # Безопасно обрабатываем item_details
    if isinstance(item_details, list):
        item_details = " ".join(str(item) for item in item_details)
    elif not isinstance(item_details, str):
        item_details = str(item_details) if item_details is not None else ""
    
    # Объединяем item_details и OCR для анализа
    text_to_analyze = f"{item_details} {ocr_text}".lower()
    
    # Ключевые слова услуг по автомобилям
    service_keywords = [
        "доставка", "delivery", "transportation service", "transport service", "przewóz", "dostawa",
        "ремонт", "repair", "naprawa", "serwis maintenance", 
        "техосмотр", "inspection", "przegląd", "kontrola",
        "мойка", "wash", "mycie", "cleaning", "czyszczenie",
        "парковка", "parking", "parkowanie", "стоянка",
        "страхование", "insurance", "ubezpieczenie", "assurance",
        "регистрация", "registration", "rejestracja", "enregistrement",
        "таможня", "customs", "cło", "douane", "clearance",
        "логистика", "logistics", "logistyka", "logistique",
        "перевозка автомобил", "автомобильные услуги", "car service", "auto service",
        "техническое обслуживание", "тюнинг", "tuning"
    ]
    
    # Ключевые слова покупки автомобилей
    purchase_keywords = [
        "продажа", "sale", "sprzedaż", "vente", "покупка", "purchase", "zakup", "achat",
        "цена автомобиля", "car price", "cena samochodu", "prix voiture",
        "стоимость машины", "vehicle cost", "koszt pojazdu", "coût véhicule",
        "down payment", "предоплата", "anzahlung", "аванс", "задаток", "deposit"
    ]
    
    # Сильные индикаторы покупки (приоритет)
    strong_purchase_indicators = [
        "down payment", "предоплата", "anzahlung", "deposit", "final invoice",
        "invoice", "rechnung", "facture", "счет на оплату", "faktura"
    ]
    
    # Проверяем сильные индикаторы покупки
    strong_purchase_count = sum(1 for indicator in strong_purchase_indicators if indicator in text_to_analyze)
    if strong_purchase_count > 0:
        # Если есть сильные индикаторы покупки, проверяем, что это не просто услуга с инвойсом
        explicit_service_count = sum(1 for keyword in ["transportation service", "transport service", "car service", "auto service", "доставка автомобил", "перевозка автомобил"] if keyword in text_to_analyze)
        if explicit_service_count == 0:
            return True  # Это покупка
    
    # Подсчитываем обычные вхождения
    service_count = sum(1 for keyword in service_keywords if keyword in text_to_analyze)
    purchase_count = sum(1 for keyword in purchase_keywords if keyword in text_to_analyze)
    
    # Если есть явные признаки услуг (и нет сильных индикаторов покупки) - это услуга
    if service_count > 0 and strong_purchase_count == 0:
        return False
    
    # Если есть явные признаки покупки - это покупка  
    if purchase_count > 0:
        return True
    
    # Эвристика: если в документе есть VIN + модель автомобиля + большая сумма (>10000) + invoice/rechnung/faktura - скорее всего покупка
    has_vin = bool(re.search(r'[A-HJ-NPR-Z0-9]{17}', text_to_analyze))
    has_car_model = bool(re.search(r'(ferrari|mercedes|bmw|audi|porsche|lamborghini|bentley|maserati|aston martin|jaguar|land rover|volkswagen|skoda|seat|volvo|saab|alfa romeo|fiat|peugeot|citroen|renault|toyota|honda|nissan|mazda|mitsubishi|subaru|lexus|infiniti)', text_to_analyze))
    has_invoice = bool(re.search(r'(invoice|rechnung|faktura|facture|счет)', text_to_analyze))
    
    # Ищем большие суммы (больше 10,000)
    large_amounts = re.findall(r'([0-9]{1,3}(?:[.,][0-9]{3})+)', text_to_analyze)
    has_large_amount = any(float(amount.replace(',', '').replace('.', '')) > 10000 for amount in large_amounts if amount.replace(',', '').replace('.', '').isdigit())
    
    if has_vin and has_car_model and has_invoice and has_large_amount:
        return True
    
    # По умолчанию считаем услугой, если не определено однозначно
    return False

def detect_country_by_indirect_signs(data: dict, ocr_text: str) -> dict:
    """
    Определяет страну поставщика по косвенным признакам:
    - Формат VAT номера (префикс или характерные цифры)
    - Ключевые слова в адресе  
    - Языковые особенности документа
    - Характерные названия городов
    - Валюта счета
    """
    supplier = data.get("supplier", {})
    if not isinstance(supplier, dict):
        return data
        
    supplier_vat = supplier.get("vat", "")
    
    # Если страна уже определена, все равно проверяем VAT префикс
    if supplier.get("country"):
        existing_country = supplier.get("country", "")
        # Добавляем префикс к VAT если нужно
        if supplier_vat and not (len(supplier_vat) >= 2 and supplier_vat[:2].isalpha()):
            supplier["vat"] = add_country_prefix_to_vat(supplier_vat, existing_country)
            logging.info(f"🏷️ Добавлен префикс к VAT (страна уже определена): {supplier['vat']}")
            data["supplier"] = supplier
        return data
    supplier_address = supplier.get("address", "").lower()
    currency = data.get("currency", "").upper()
    
    detected_country = ""
    confidence = 0
    
    # 1. Определение по формату VAT номера
    if supplier_vat:
        # Убираем пробелы и дефисы
        clean_vat = supplier_vat.replace(" ", "").replace("-", "")
        
        # Если уже есть префикс страны
        if len(clean_vat) >= 2 and clean_vat[:2].isalpha():
            country_code = clean_vat[:2].upper()
            country_mapping = {
                'PL': 'Poland', 'DE': 'Germany', 'SE': 'Sweden', 'EE': 'Estonia',
                'FR': 'France', 'IT': 'Italy', 'ES': 'Spain', 'NL': 'Netherlands',
                'BE': 'Belgium', 'AT': 'Austria', 'CZ': 'Czech Republic',
                'HU': 'Hungary', 'LV': 'Latvia', 'LT': 'Lithuania'
            }
            if country_code in country_mapping:
                detected_country = country_mapping[country_code]
                confidence = 90
        
        # Определение по длине и формату VAT (без префикса)
        elif len(clean_vat) == 10 and clean_vat.isdigit():
            # Польский NIP - 10 цифр
            detected_country = "Poland"
            confidence = 80
        elif len(clean_vat) == 12 and clean_vat.endswith('01'):
            # Шведский VAT (organisationsnummer + 01)
            detected_country = "Sweden" 
            confidence = 85
        elif len(clean_vat) == 9 and clean_vat.isdigit():
            # Немецкий или эстонский VAT
            if currency == "EUR":
                detected_country = "Germany"  # Предположение
                confidence = 60
        
    # 2. Определение по адресу и городам
    if not detected_country and supplier_address:
        city_country_mapping = {
            # Польша
            'warszawa': 'Poland', 'kraków': 'Poland', 'gdansk': 'Poland', 'wrocław': 'Poland',
            'łódź': 'Poland', 'poznań': 'Poland', 'łochów': 'Poland',
            # Германия  
            'berlin': 'Germany', 'münchen': 'Germany', 'hamburg': 'Germany', 'köln': 'Germany',
            'frankfurt': 'Germany', 'stuttgart': 'Germany', 'düsseldorf': 'Germany',
            # Швеция
            'stockholm': 'Sweden', 'göteborg': 'Sweden', 'malmö': 'Sweden', 'uppsala': 'Sweden',
            'södertälje': 'Sweden', 'växjö': 'Sweden',
            # Эстония
            'tallinn': 'Estonia', 'tartu': 'Estonia', 'narva': 'Estonia', 'pärnu': 'Estonia',
            # Другие страны
            'paris': 'France', 'rome': 'Italy', 'madrid': 'Spain', 'amsterdam': 'Netherlands',
            'brussels': 'Belgium', 'vienna': 'Austria', 'prague': 'Czech Republic'
        }
        
        for city, country in city_country_mapping.items():
            if city in supplier_address:
                if not detected_country:
                    detected_country = country
                    confidence = 75
                elif detected_country == country:
                    confidence = max(confidence, 85)  # Усиливаем уверенность
                break
    
    # 3. Определение по языковым особенностям документа
    if not detected_country or confidence < 70:
        ocr_lower = ocr_text.lower()
        
        language_indicators = {
            'Poland': ['sprzedawca', 'nabywca', 'faktura', 'nip:', 'zł', 'pln', 'warszawa', 'ul.', 'do zapłaty'],
            'Germany': ['rechnung', 'lieferant', 'kunde', 'ustid', 'ust-id', 'mwst', '€', 'deutschland'],
            'Sweden': ['försäljare', 'köpare', 'org.nr', 'organisationsnummer', 'sverige', 'sek', 'kr'],
            'Estonia': ['müüja', 'ostja', 'arve', 'kmkr', 'estonia', 'eesti', 'tallinn'],
            'France': ['vendeur', 'acheteur', 'facture', 'n° tva', 'france', '€'],
            'Italy': ['venditore', 'acquirente', 'fattura', 'p.iva', 'italia', '€']
        }
        
        for country, keywords in language_indicators.items():
            matches = sum(1 for keyword in keywords if keyword in ocr_lower)
            if matches >= 2:  # Минимум 2 совпадения
                if not detected_country:
                    detected_country = country
                    confidence = 50 + (matches * 10)  # Увеличиваем уверенность за каждое совпадение
                elif detected_country == country:
                    confidence = max(confidence, 70 + (matches * 5))
    
    # 4. Дополнительные индикаторы по валюте
    if detected_country and currency:
        currency_boost = {
            'PLN': ['Poland'],
            'SEK': ['Sweden'], 
            'EUR': ['Germany', 'France', 'Italy', 'Spain', 'Netherlands', 'Belgium', 'Austria', 'Estonia']
        }
        
        if currency in currency_boost and detected_country in currency_boost[currency]:
            confidence = min(confidence + 10, 95)
    
    # Применяем результат если уверенность достаточна
    if detected_country and confidence >= 60:
        supplier["country"] = detected_country
        logging.info(f"🌍 Определена страна поставщика по косвенным признакам: {detected_country} (уверенность: {confidence}%)")
        
        # Добавляем префикс к VAT если нужно
        if supplier_vat and not (len(supplier_vat) >= 2 and supplier_vat[:2].isalpha()):
            supplier["vat"] = add_country_prefix_to_vat(supplier_vat, detected_country)
            logging.info(f"🏷️ Добавлен префикс к VAT: {supplier['vat']}")
    
    data["supplier"] = supplier
    return data

def add_country_prefix_to_vat(vat: str, country: str) -> str:
    """
    Добавляет префикс страны к VAT номеру, если его нет
    """
    if not vat or not country:
        return vat
    
    # Если VAT уже содержит префикс страны (начинается с 2 букв)
    if len(vat) >= 2 and vat[:2].isalpha():
        return vat
    
    # Определяем префикс по стране
    country_lower = country.lower()
    country_prefixes = {
        'poland': 'PL',
        'polska': 'PL',
        'pl': 'PL',
        'germany': 'DE', 
        'deutschland': 'DE',
        'de': 'DE',
        'estonia': 'EE',
        'eesti': 'EE',
        'ee': 'EE',
        'sweden': 'SE',
        'sverige': 'SE',
        'se': 'SE',
        'france': 'FR',
        'frança': 'FR',
        'fr': 'FR',
        'spain': 'ES',
        'españa': 'ES',
        'es': 'ES',
        'italy': 'IT',
        'italia': 'IT',
        'it': 'IT',
        'netherlands': 'NL',
        'nederland': 'NL',
        'nl': 'NL',
        'united kingdom': 'GB',
        'uk': 'GB',
        'gb': 'GB',
        'czech republic': 'CZ',
        'czechia': 'CZ',
        'cz': 'CZ',
        'hungary': 'HU',
        'magyarország': 'HU',
        'hu': 'HU',
        'austria': 'AT',
        'österreich': 'AT',
        'at': 'AT',
        'belgium': 'BE',
        'belgië': 'BE',
        'be': 'BE',
        'latvia': 'LV',
        'latvija': 'LV',
        'lv': 'LV',
        'lithuania': 'LT',
        'lietuva': 'LT',
        'lt': 'LT',
    }
    
    # Ищем префикс для страны (точное совпадение или начало строки)
    for country_name, prefix in country_prefixes.items():
        if country_lower == country_name or country_lower.startswith(country_name):
            return f"{prefix}{vat}"
    
    # Если не нашли - возвращаем как есть
    return vat

def fix_supplier_if_needed(data: dict, ocr_text: str) -> dict:
    """
    Исправляет supplier только если найдено явное несоответствие.
    Более умная логика, которая не подгоняет под конкретный документ.
    """
    # Получаем данные от Assistant
    supplier = data.get("supplier", {})
    our_company = data.get("our_company", {})
    
    # Безопасно извлекаем данные supplier
    supplier_name = ""
    supplier_vat = ""
    if isinstance(supplier, dict):
        supplier_name = supplier.get("name", "")
        supplier_vat = supplier.get("vat", "")
    elif isinstance(supplier, str):
        supplier_name = supplier
    elif isinstance(supplier, list) and len(supplier) > 0:
        first_item = supplier[0]
        if isinstance(first_item, dict):
            supplier_name = first_item.get("name", "")
            supplier_vat = first_item.get("vat", "")
        else:
            supplier_name = str(first_item)
    
    # Безопасно извлекаем данные our_company
    our_company_name = ""
    our_company_vat = ""
    if isinstance(our_company, dict):
        our_company_name = our_company.get("name", "")
        our_company_vat = our_company.get("vat", "")
    elif isinstance(our_company, str):
        our_company_name = our_company
    elif isinstance(our_company, list) and len(our_company) > 0:
        first_item = our_company[0]
        if isinstance(first_item, dict):
            our_company_name = first_item.get("name", "")
            our_company_vat = first_item.get("vat", "")
        else:
            our_company_name = str(first_item)
    
    # Проверяем, не спутал ли Assistant поставщика с нашей компанией
    if supplier_name and is_our_company(supplier_name, supplier_vat):
        logging.info("🔄 Supplier определен как наша компания, исправляем...")
        # Ищем правильного поставщика в OCR тексте
        real_supplier_name, real_supplier_vat = extract_legal_entity_and_vat_excluding_our_companies(ocr_text)
        if real_supplier_name:
            # Извлекаем адрес и страну
            supplier_address, supplier_country = extract_supplier_address(ocr_text, real_supplier_name)
            data["supplier"] = {
                "name": real_supplier_name,
                "vat": real_supplier_vat,
                "address": supplier_address,
                "country": supplier_country,
                "email": extract_supplier_email(ocr_text),
                "contact_person": ""
            }
            logging.info(f"✅ Исправлен supplier на: {real_supplier_name} (Адрес: {supplier_address}, Страна: {supplier_country})")
        return data
    
    # Проверяем, есть ли недостающие данные у поставщика
    if supplier_name and not supplier_vat:
        # Пытаемся найти VAT для существующего поставщика
        real_supplier_name, real_supplier_vat = extract_legal_entity_and_vat_excluding_our_companies(ocr_text)
        if real_supplier_vat and supplier_name.lower() in real_supplier_name.lower():
            logging.info(f"🔍 Supplier имеет неполные данные, пытаемся улучшить...")
            data["supplier"]["vat"] = real_supplier_vat
            if not data["supplier"].get("email"):
                data["supplier"]["email"] = extract_supplier_email(ocr_text)
            # Добавляем адрес если его нет
            if not data["supplier"].get("address"):
                supplier_address, supplier_country = extract_supplier_address(ocr_text, supplier_name)
                data["supplier"]["address"] = supplier_address
                data["supplier"]["country"] = supplier_country
            logging.info(f"✅ Улучшен supplier: {supplier_name} (VAT: {real_supplier_vat}, Email: {data['supplier'].get('email', '')}, Адрес: {data['supplier'].get('address', '')})")
        return data
    
    # Если supplier пустой или содержит только служебные слова
    if not supplier_name or supplier_name.lower() in ['corporate id no', 'vat reg. no', 'tax id', 'registration no']:
        logging.info("🔍 Supplier имеет неполные данные, пытаемся улучшить...")
        real_supplier_name, real_supplier_vat = extract_legal_entity_and_vat_excluding_our_companies(ocr_text)
        if real_supplier_name:
            # Извлекаем адрес и страну
            supplier_address, supplier_country = extract_supplier_address(ocr_text, real_supplier_name)
            data["supplier"] = {
                "name": real_supplier_name,
                "vat": real_supplier_vat,
                "address": supplier_address,
                "country": supplier_country,
                "email": extract_supplier_email(ocr_text),
                "contact_person": supplier.get("contact_person", "") if isinstance(supplier, dict) else ""
            }
            logging.info(f"✅ Улучшен supplier: {real_supplier_name} (VAT: {real_supplier_vat}, Email: {data['supplier'].get('email', '')}, Адрес: {supplier_address})")
        return data
    
    # Если у поставщика нет адреса, пытаемся его найти
    if supplier_name and not data["supplier"].get("address"):
        supplier_address, supplier_country = extract_supplier_address(ocr_text, supplier_name)
        if supplier_address:
            data["supplier"]["address"] = supplier_address
            data["supplier"]["country"] = supplier_country
            logging.info(f"✅ Добавлен адрес поставщика: {supplier_address}, Страна: {supplier_country}")
    
    return data

def check_document_ownership(data: dict, ocr_text: str) -> dict:
    """
    Проверяет, принадлежит ли документ нам
    """
    supplier = data.get("supplier", {})
    our_company = data.get("our_company", "")
    
    supplier_name = supplier.get("name", "") if isinstance(supplier, dict) else ""
    supplier_vat = supplier.get("vat", "") if isinstance(supplier, dict) else ""
    
    # Безопасно извлекаем данные our_company
    our_company_name = ""
    our_company_vat = ""
    if isinstance(our_company, dict):
        our_company_name = our_company.get("name", "")
        our_company_vat = our_company.get("vat", "")
    elif isinstance(our_company, str):
        our_company_name = our_company
    elif isinstance(our_company, list) and len(our_company) > 0:
        # Если our_company - список, берем первый элемент
        first_item = our_company[0]
        if isinstance(first_item, dict):
            our_company_name = first_item.get("name", "")
            our_company_vat = first_item.get("vat", "")
        elif isinstance(first_item, str):
            our_company_name = first_item
    
    # Улучшенная проверка наличия нашей компании в документе
    # ПРИОРИТЕТ: VAT номер - это ЕДИНСТВЕННЫЙ решающий критерий!
    our_company_found_in_doc = False
    
    # 1. ПРИОРИТЕТ: Проверяем VAT наших компаний (полный номер с префиксом)
    for comp in OUR_COMPANIES:
        comp_vat = comp["vat"]
        if comp_vat in ocr_text:
            our_company_found_in_doc = True
            logging.info(f"✅ Найден VAT нашей компании в документе: {comp_vat}")
            break
    
    # 2. Проверяем VAT без префикса (например, "5272956146" в документе vs "PL5272956146" в системе)
    if not our_company_found_in_doc:
        for comp in OUR_COMPANIES:
            comp_vat = comp["vat"]
            # Убираем префикс из VAT для поиска
            vat_digits = re.sub(r'^[A-Z]{2}', '', comp_vat)
            if len(vat_digits) >= 7 and vat_digits in ocr_text:
                our_company_found_in_doc = True
                logging.info(f"✅ Найден VAT нашей компании без префикса: {vat_digits} (полный: {comp_vat})")
                break
    
    # 2.1. УЛУЧШЕННЫЙ ПОИСК: Проверяем VAT с форматированием (например, "527-295-61-46" -> "PL5272956146")
    if not our_company_found_in_doc:
        # Нормализуем OCR текст (убираем пробелы и дефисы)
        ocr_normalized = re.sub(r'[\s\-]', '', ocr_text)
        
        for comp in OUR_COMPANIES:
            comp_vat = comp["vat"]
            vat_digits = re.sub(r'^[A-Z]{2}', '', comp_vat)
            
            # Проверяем нормализованный VAT
            if len(vat_digits) >= 8 and vat_digits in ocr_normalized:
                our_company_found_in_doc = True
                logging.info(f"✅ Найден VAT нашей компании (нормализованный): {vat_digits} (полный: {comp_vat})")
                break
        
    # 2.2. КОНТЕКСТНЫЙ ПОИСК: Ищем VAT с префиксами NIP:, VAT:, etc.
    if not our_company_found_in_doc:
        for comp in OUR_COMPANIES:
            comp_vat = comp["vat"]
            vat_digits = re.sub(r'^[A-Z]{2}', '', comp_vat)
            
            if len(vat_digits) == 10:  # Polish VAT
                # Ищем форматы: 527-295-61-46, NIP: 527-295-61-46, etc.
                formatted_patterns = [
                    f"{vat_digits[:3]}-{vat_digits[3:6]}-{vat_digits[6:8]}-{vat_digits[8:]}",  # 527-295-61-46
                    f"{vat_digits[:3]} {vat_digits[3:6]} {vat_digits[6:8]} {vat_digits[8:]}",   # 527 295 61 46
                ]
                
                for pattern in formatted_patterns:
                    if pattern in ocr_text:
                        our_company_found_in_doc = True
                        logging.info(f"✅ Найден VAT нашей компании (форматированный): {pattern} (полный: {comp_vat})")
                        break
                
                if our_company_found_in_doc:
                    break
                
                # Поиск с контекстными словами
                vat_context_patterns = [
                    rf'NIP:\s*{re.escape(vat_digits[:3])}.{re.escape(vat_digits[3:6])}.{re.escape(vat_digits[6:8])}.{re.escape(vat_digits[8:])}',
                    rf'VAT:\s*{re.escape(comp_vat)}',
                    rf'TAX\s*ID:\s*{re.escape(vat_digits)}',
                ]
                
                for pattern in vat_context_patterns:
                    if re.search(pattern, ocr_text, re.IGNORECASE):
                        our_company_found_in_doc = True
                        logging.info(f"✅ Найден VAT нашей компании (контекстный): {pattern} (полный: {comp_vat})")
                        break
                
                if our_company_found_in_doc:
                    break
    
    # 3. Проверяем VAT в данных от OpenAI (supplier и our_company)
    if not our_company_found_in_doc:
        if is_our_company("", supplier_vat) or is_our_company("", our_company_vat):
            our_company_found_in_doc = True
            logging.info("✅ Наша компания найдена через OpenAI определение (по VAT)")
    
    # 4. FALLBACK: Если VAT не найден, проверяем по названию (только если нет VAT данных)
    # Это обрабатывает случай, когда VAT номер забыли указать в документе
    if not our_company_found_in_doc:
        # Проверяем, есть ли VAT данные в документе
        has_vat_data = bool(supplier_vat) or bool(our_company_vat)
        
        if not has_vat_data:
            # VAT данных нет - можем проверить по названию (fallback)
            logging.info("⚠️ VAT данные отсутствуют, проверяем по названию компании...")
            for comp in OUR_COMPANIES:
                comp_normalized = normalize_company_name_for_comparison(comp["name"])
                ocr_normalized = normalize_company_name_for_comparison(ocr_text)
                if comp_normalized in ocr_normalized:
                    our_company_found_in_doc = True
                    logging.info(f"✅ Найдена наша компания по названию (fallback): {comp['name']}")
                    break
        else:
            # VAT данные есть, но не совпадают - отклоняем
            # Это важно для безопасности: если VAT указан, он должен быть правильным
            logging.warning("❌ VAT данные присутствуют, но не совпадают с нашими - документ отклонен")
    
    # Если наша компания не найдена, документ не относится к нам
    if not our_company_found_in_doc:
        data["skip_processing"] = True
        data["ownership_message"] = "Документ не относится к нашему документообороту"
        logging.warning("❗️ Внимание: Наша компания не найдена в документе!")
        return data
    
    # Проверяем корректность ролей: supplier должен быть внешней компанией, our_company - нашей
    supplier_is_our_company = is_our_company(supplier_name, supplier_vat)
    our_company_is_our_company = is_our_company(our_company_name, our_company_vat)
    
    # Если supplier - наша компания, а our_company - не наша, меняем местами
    if supplier_is_our_company and not our_company_is_our_company:
        logging.info("🔄 Поменяли местами supplier и our_company (supplier был нашей компанией)")
        data["supplier"], data["our_company"] = data["our_company"], data["supplier"]
        return data
    
    # Если наша компания не в our_company, пытаемся найти её по VAT
    if not our_company_is_our_company:
        logging.info("🔍 Our_company не является нашей компанией, ищем правильную по VAT...")
        found_our_company = None
        
        # 1. Поиск по полному VAT
        for comp in OUR_COMPANIES:
            if comp["vat"] in ocr_text:
                found_our_company = comp
                logging.info(f"✅ Найдена наша компания по VAT: {comp['name']} ({comp['vat']})")
                break
        
        # 2. Поиск по VAT без префикса
        if not found_our_company:
            for comp in OUR_COMPANIES:
                vat_digits = re.sub(r'^[A-Z]{2}', '', comp["vat"])
                if len(vat_digits) >= 7 and vat_digits in ocr_text:
                    found_our_company = comp
                    logging.info(f"✅ Найдена наша компания по VAT без префикса: {comp['name']} ({vat_digits})")
                    break
        
        # Устанавливаем найденную компанию (только если найдена по VAT)
        if found_our_company:
            data["our_company"] = {
                "name": found_our_company["name"],
                "vat": found_our_company["vat"],
                "address": "",
                "country": ""
            }
    
    # Убеждаемся, что у нашей компании есть VAT с правильным префиксом
    if isinstance(data.get("our_company"), dict):
        current_vat = data["our_company"].get("vat", "")
        our_comp_name = data["our_company"].get("name", "")
        
        # Если VAT отсутствует или без префикса (только цифры), добавляем правильный VAT
        needs_vat_fix = not current_vat or (current_vat.isdigit() and len(current_vat) >= 7)
        
        if needs_vat_fix:
            for comp in OUR_COMPANIES:
                # Гибкое сопоставление: проверяем как точное совпадение, так и вхождение
                our_normalized = normalize_company_name_for_comparison(our_comp_name)
                comp_normalized = normalize_company_name_for_comparison(comp["name"])
                
                # Гибкое сопоставление: точное совпадение, вхождение, или общая основа названия
                match = False
                if our_normalized == comp_normalized:
                    match = True  # Точное совпадение
                elif comp_normalized in our_normalized or our_normalized in comp_normalized:
                    match = True  # Одно содержит другое
                else:
                    # Проверяем общую основу (первые значимые слова)
                    our_words = our_normalized.split()
                    comp_words = comp_normalized.split()
                    if our_words and comp_words and our_words[0] == comp_words[0] and len(our_words[0]) >= 5:
                        match = True  # Общая основа из значимого слова (>=5 символов)
                
                if match:
                    data["our_company"]["vat"] = comp["vat"]
                    logging.info(f"✅ Добавлен VAT нашей компании с префиксом: {comp['vat']}")
                    break
    
    # Убеждаемся, что у поставщика есть email
    if isinstance(data.get("supplier"), dict) and not data["supplier"].get("email"):
        supplier_email = extract_supplier_email(ocr_text)
        if supplier_email:
            data["supplier"]["email"] = supplier_email
            logging.info(f"✅ Добавлен email поставщика: {supplier_email}")
    
    # Убираем флаг пропуска, если документ принадлежит нам
    if "skip_processing" in data:
        del data["skip_processing"]
    if "ownership_message" in data:
        del data["ownership_message"]
    
    return data

# Lazy и безопасная инициализация OpenAI клиента, чтобы импорт модуля не падал
try:
    from openai import OpenAI  # type: ignore
except Exception:
    OpenAI = None  # type: ignore

client = None
ASSISTANT_ID = os.getenv("OPENAI_ASSISTANT_ID") or ""

def _ensure_openai_client():
    global client
    if client is not None:
        return client
    try:
        api_key = os.getenv("OPENAI_API_KEY")
        if not OpenAI or not api_key or not ASSISTANT_ID:
            return None
        # Некоторые версии SDK могут не поддерживать аргумент proxies; используем минимальный вызов
        client_local = OpenAI(api_key=api_key)
        client = client_local
        return client
    except Exception:
        return None

def extract_json_block(text: str) -> str:
    """Извлекает JSON-блок из строки"""
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        return match.group(1)
    match = re.search(r"(\{.*\})", text, re.DOTALL)
    if match:
        return match.group(1)
    return ""

def analyze_proforma_via_agent(file_path: str) -> dict:
    """
    Анализирует документ через OpenAI Assistant и возвращает структурированные данные
    """
    try:
        # Определяем тип файла и получаем текст
        if file_path.lower().endswith('.pdf'):
            # Для PDF - используем Google Vision OCR
            logging.info(f"PDF файл обнаружен: {file_path}, запускаем OCR...")
            ocr_text = extract_text_from_pdf(file_path)
            if not ocr_text or len(ocr_text.strip()) == 0:
                raise Exception("OCR не смог извлечь текст из PDF")
        elif file_path.lower().endswith('.txt'):
            # Для текстовых файлов - читаем как обычно
            with open(file_path, 'r', encoding='utf-8') as file:
                ocr_text = file.read()
        else:
            raise Exception(f"Неподдерживаемый формат файла: {file_path}")
        
        logging.info(f"Анализируем файл: {file_path}")
        
        # 1) Пытаемся извлечь поля через GPT-4 (function-calling JSON)
        data = llm_extract_fields(ocr_text) or {}
        # Если это потенциально «цветочный» документ — параллельно включаем проверку через Assistants API
        looks_flower = any(k in (ocr_text or '').lower() for k in ["kwiat", "kwiaty", "flowers", "róża", "tulip", "stawka vat", "cena brutto"]) 
        if looks_flower:
            try:
                cli = _ensure_openai_client()
                if cli:
                    thread = cli.beta.threads.create()
                    cli.beta.threads.messages.create(
                        thread_id=thread.id,
                        role="user",
                        content=(
                            "Extract full structured JSON for a Polish flower invoice, including per-line items (name, qty, unit, unit_price_net, vat_percent), "
                            "document_number, dates, supplier (name, vat, address with street/city/zip/country), and totals (net_amount, vat_amount, gross_amount).\n\n" 
                            + ocr_text
                        ),
                    )
                    run = cli.beta.threads.runs.create(thread_id=thread.id, assistant_id=str(ASSISTANT_ID))
                    while True:
                        run_status = cli.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
                        if run_status.status == 'completed':
                            break
                        if run_status.status == 'failed':
                            raise Exception(f"Assistant failed: {run_status.last_error}")
                        time.sleep(1)
                    messages = cli.beta.threads.messages.list(thread_id=thread.id)
                    response_text = None
                    for block in messages.data[0].content:
                        if getattr(block, "type", None) == "text":
                            text_obj = getattr(block, "text", None)
                            if text_obj and hasattr(text_obj, "value"):
                                response_text = text_obj.value
                                break
                    json_str = extract_json_block(response_text or '')
                    if json_str:
                        assistant_data = json.loads(json_str)
                        # Сливаем важные поля, если у LLM пусто
                        for key in ["supplier_address", "supplier_country", "supplier_street", "supplier_city", "supplier_zip_code", "net_amount", "vat_amount", "gross_amount", "flower_lines"]:
                            if (not data.get(key)) and assistant_data.get(key):
                                data[key] = assistant_data.get(key)
            except Exception:
                pass
        if not data:
            # 2) Fallback на прежнюю схему Assistant API
            cli = _ensure_openai_client()
            if not cli:
                raise Exception("OpenAI клиент недоступен: проверьте OPENAI_API_KEY/ASSISTANT_ID")
            thread = cli.beta.threads.create()
            message = cli.beta.threads.messages.create(
                thread_id=thread.id,
                role="user",
                content=f"Проанализируй этот документ:\n\n{ocr_text}"
            )
            run = cli.beta.threads.runs.create(
                thread_id=thread.id,
                assistant_id=str(ASSISTANT_ID)
            )
            while True:
                run_status = cli.beta.threads.runs.retrieve(
                    thread_id=thread.id,
                    run_id=run.id
                )
                if run_status.status == 'completed':
                    break
                elif run_status.status == 'failed':
                    raise Exception(f"Assistant failed: {run_status.last_error}")
                time.sleep(1)
            messages = cli.beta.threads.messages.list(thread_id=thread.id)
            response_text = None
            for block in messages.data[0].content:
                if getattr(block, "type", None) == "text":
                    text_obj = getattr(block, "text", None)
                    if text_obj and hasattr(text_obj, "value"):
                        response_text = text_obj.value
                        break
            if response_text is None:
                response_text = ''
            json_str = extract_json_block(response_text or '')
            if not json_str:
                raise Exception("Не удалось извлечь JSON из ответа assistant")
            data = json.loads(json_str)
        
        # Сначала исправляем supplier если нужно
        data = fix_supplier_if_needed(data, ocr_text or "")
        
        # Затем определяем страну по косвенным признакам
        data = detect_country_by_indirect_signs(data, ocr_text or "")
        
        # Затем проверяем принадлежность документа
        data = check_document_ownership(data, ocr_text or "")
        
        # Всегда вычисляем account на основе item_details
        item_details = data.get("item_details", "") or ""
        # Безопасно обрабатываем item_details
        if isinstance(item_details, list):
            item_details = " ".join(str(item) for item in item_details)
        elif not isinstance(item_details, str):
            item_details = str(item_details) if item_details is not None else ""
        
        if item_details:
            supplier_name = data.get("supplier", {}).get("name", "")
            data["account"] = detect_account(item_details, supplier_name=supplier_name, full_text=ocr_text)
        
        # Определяем, покупаем ли мы машины или оплачиваем услуги
        is_car_purchase = is_car_purchase_vs_service(item_details, ocr_text or "")
        
        # Для автомобильных документов обрабатываем VIN и car_item_name
        vin = data.get("vin", "")
        # Попытаемся взять car_brand/model из LLM-экстракции
        extracted_brand = data.get("car_brand") or ""
        extracted_model = data.get("car_model") or data.get("model") or ""
        if vin and len(vin) >= 17:
            if is_car_purchase:
                # Для покупки автомобиля: расширяем item_details добавив VIN и доп. детали
                car_model = extracted_model
                enhanced_details = enhance_car_details_for_purchase(item_details, vin, car_model, ocr_text or "")
                data["item_details"] = enhanced_details
                logging.info(f"🚗 Покупка автомобиля: item_details расширен деталями: {enhanced_details}")
            else:
                # Для услуг НЕ меняем item_details - оставляем описание услуги
                logging.info(f"🚚 Услуга по автомобилю: item_details оставлен как описание услуги: {item_details}")
            
            # Исправляем car_item_name - последние 5 ЦИФР VIN (для всех типов документов с VIN)
            last_5_digits = re.sub(r'[^0-9]', '', vin)[-5:] if re.sub(r'[^0-9]', '', vin) else ""
            if last_5_digits and len(last_5_digits) == 5:
                car_brand = extracted_brand
                car_model = extracted_model
                name_parts = [p for p in [car_brand, car_model] if p]
                if name_parts:
                    data["car_item_name"] = f"{' '.join(name_parts)}_{last_5_digits}"
        
        # Для услуг - убеждаемся, что item_details содержит описание услуги
        if not is_car_purchase:
            # Проверяем, что item_details содержит описание услуги, а не VIN
            current_item_details = data.get("item_details", "")
            if current_item_details and len(current_item_details) == 17 and re.match(r'^[A-HJ-NPR-Z0-9]{17}$', current_item_details):
                # item_details содержит только VIN - ищем описание услуги в OCR
                service_description = extract_service_description(ocr_text or "")
                if service_description:
                    data["item_details"] = service_description
                    logging.info(f"🔧 Исправлен item_details для услуги: {service_description}")
                else:
                    # Если не нашли описание услуги, оставляем VIN но добавляем пометку что это услуга
                    data["item_details"] = f"Услуга по автомобилю {current_item_details}"
                    logging.info(f"🔧 Добавлена пометка об услуге: {data['item_details']}")

        # Обрабатываем массив машин только если это ПОКУПКА машин
        cars_array = data.get("cars", [])
        if cars_array and isinstance(cars_array, list):
            if is_car_purchase:
                logging.info(f"📄 Это покупка автомобилей - сохраняем детали {len(cars_array)} машин")
                # Сохраняем массив машин как есть для покупки
                pass
            else:
                logging.info(f"🚚 Это услуга по автомобилям (доставка/ремонт и т.д.) - не выделяем машины отдельно")
                # Для услуг удаляем массив машин, оставляем только общее описание в item_details
                if "cars" in data:
                    del data["cars"]
                # Также удаляем индивидуальные поля car_* если это услуга
                for key in ["vin", "car_model", "car_item_name"]:
                    if key in data:
                        del data[key]
        
        # Исправляем total_amount для покупки автомобилей (ищем полную стоимость, а не сумму к доплате)
        if is_car_purchase and data.get("total_amount"):
            corrected_amount = extract_full_car_price(ocr_text or "", data.get("total_amount", 0))
            if corrected_amount and corrected_amount != data.get("total_amount"):
                data["total_amount"] = corrected_amount
                logging.info(f"💰 Исправлена сумма для покупки автомобиля: {corrected_amount}€ (была: {data.get('total_amount', 0)}€)")
        
        # Проверяем, есть ли наша VAT в документе (только если документ не был пропущен)
        if not data.get("skip_processing", False):
            our_vat_found = False
            # Проверяем полный VAT
            for comp in OUR_COMPANIES:
                if comp["vat"] in (ocr_text or ""):
                    our_vat_found = True
                    break
            # Проверяем VAT без префикса
            if not our_vat_found:
                for comp in OUR_COMPANIES:
                    vat_digits = re.sub(r'^[A-Z]{2}', '', comp["vat"])
                    if len(vat_digits) >= 7 and vat_digits in (ocr_text or ""):
                        our_vat_found = True
                        break
            
            if not our_vat_found:
                logging.warning("❗️ Внимание: VAT вашей компании не найден в документе!")
        
        # 3) Если документ — контракт/продажа, дополнительно анализируем риски
        doc_type = (data.get("document_type") or "").lower()
        if any(k in doc_type for k in ["contract", "sale", "proforma", "purchase"]):
            risks = llm_analyze_contract_risks(ocr_text) or {}
            if risks:
                data["contract_risks"] = risks

        # Проставим контактное лицо, если LLM его дал
        contact_person = data.get("contact_person") or data.get("issuer_contact_person")
        if contact_person:
            data.setdefault("supplier", {})
            data["supplier"]["contact_person"] = contact_person

        logging.info(f"Результат анализа: {json.dumps(data, ensure_ascii=False, indent=2)}")
        return data
        
    except Exception as e:
        logging.error(f"Ошибка при анализе {file_path}: {str(e)}")
        return {
            "error": str(e),
            "file_path": file_path,
            "skip_processing": True
        }
