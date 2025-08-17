from mcp_connector.models import Proforma, Invoice, Supplier, Contract
import re

# --- Вспомогательные функции ---

def detect_document_type(text: str) -> str:
    """
    Определяет тип документа: proforma/invoice/credit_note/contract/unknown.
    """
    # Приводим к нижнему регистру для удобства поиска
    text_lower = text.lower()

    # Ключевые слова для разных типов документов
    proforma_keywords = ["proforma"]
    invoice_keywords = [
        "invoice", "Rechnung", "bill", "tagasiside", "faktura", "счет", "facture", "fattura", "factura", "nota", "factuur"
    ]
    credit_note_keywords = ["credit note", "gutschrift", "nota de crédito", "avoir"]
    contract_keywords = ["contract", "vertrag", "bestellung", "purchase order", "договор", "контракт"]

    for word in proforma_keywords:
        if word in text_lower:
            return "proforma"
    for word in contract_keywords:
        if word in text_lower:
            return "contract"
    for word in invoice_keywords:
        if word in text_lower:
            return "invoice"
    for word in credit_note_keywords:
        if word in text_lower:
            return "credit_note"
    return "unknown"

def is_car_invoice(text: str) -> bool:
    """
    True если есть VIN и марка авто (упрощённо).
    """
    return bool(extract_vin(text)) and bool(extract_car_model(text))

def extract_vin(text: str) -> str:
    # Ищет 17-значный VIN
    vin_pattern = r'\b[A-HJ-NPR-Z0-9]{17}\b'
    match = re.search(vin_pattern, text)
    return match.group(0) if match else ""

def extract_car_model(text: str) -> str:
    """
    Извлекает ПОЛНОЕ название автомобиля (МАРКА + МОДЕЛЬ).
    Примеры: "RANGE ROVER SPORT PHEV", "BMW X5 M50d", "MERCEDES BENZ S65 AMG"
    """
    lines = text.splitlines()
    
    # Сначала ищем конкретные модели в формате "X5 M50d", "A6 quattro" и т.д.
    for line in lines:
        line = line.strip()
        # Ищем паттерн: буквы+цифры (модель) + буквы/цифры (версия)
        model_match = re.search(r'\b([A-Z]\d+\w*(?:\s+[A-Za-z0-9]+)*)\b', line)
        if model_match:
            model_part = model_match.group(1)
            # Проверяем, что это автомобильная модель
            if any(car_indicator in model_part.upper() for car_indicator in ['X5', 'X6', 'A6', 'S65', 'E500', 'SPORT']):
                # Добавляем марку BMW если нужно
                if 'BMW' not in line.upper() and any(bmw_model in model_part.upper() for bmw_model in ['X5', 'X6', 'M50', 'M3', 'M5']):
                    return f"BMW {model_part}"
                elif 'BMW' in line.upper():
                    # Извлекаем BMW + модель
                    bmw_start = line.upper().find('BMW')
                    if bmw_start != -1:
                        rest_line = line[bmw_start:].strip()
                        # Останавливаемся на скобках или лишней информации
                        stop_match = re.search(r'[\(\)]|[0-9]{4,}|CV\d+', rest_line)
                        if stop_match:
                            rest_line = rest_line[:stop_match.start()].strip()
                        # Очищаем от лишних слов
                        clean_line = re.sub(r'\b(Vertragshändler|Händler|Individual|Live|Cockpit)\b', '', rest_line, flags=re.IGNORECASE).strip()
                        if len(clean_line) > 3:  # Должно быть больше чем просто "BMW"
                            return clean_line
                return model_part
    
    # Резервный поиск по брендам (старая логика)
    brands = [
        "BMW", "AUDI", "VOLKSWAGEN", "MERCEDES", "MERCEDES BENZ", 
        "TOYOTA", "LAND ROVER", "RANGE ROVER", "RR", "PORSCHE", 
        "VOLVO", "FORD", "FERRARI", "LAMBORGHINI", "BENTLEY", "MASERATI"
    ]
    
    # Исключаемые слова (не модели автомобилей)
    exclude_words = [
        "VERTRAGSHÄNDLER", "HÄNDLER", "DEALER", "AUTOHAUS", "GARAGE",
        "SERVICE", "CENTER", "WORKSHOP", "REPAIR", "PARTS", "WWW", "EMAIL", "@"
    ]
    
    for line in lines:
        line_upper = line.upper().strip()
        
        # Пропускаем строки с исключаемыми словами
        if any(exclude_word in line_upper for exclude_word in exclude_words):
            continue
            
        for brand in brands:
            if brand in line_upper:
                # Извлекаем часть строки с автомобилем
                brand_start = line_upper.find(brand)
                if brand_start == -1:
                    continue
                    
                # Берем часть строки от бренда
                car_part = line[brand_start:].strip()
                
                # Удаляем все после первого числа/цены/VIN
                # Останавливаемся на: больших числах, VIN, "vir", ценах, подчеркивании, скобках
                stop_pattern = r'(\d{4,}|[A-HJ-NPR-Z0-9]{17}|\bvir\b|\bvin\b|\b\d+\s*(EUR|USD|PLN|€|\$)|_|\bprice\b|\(.*\))'
                match = re.search(stop_pattern, car_part, re.IGNORECASE)
                if match:
                    car_part = car_part[:match.start()].strip()
                
                # Убираем лишние символы в конце
                car_part = re.sub(r'[^\w\s]', '', car_part).strip()
                
                # Проверяем, что это действительно модель автомобиля
                # Должна содержать марку и что-то еще (модель)
                if len(car_part) > len(brand) and not any(exclude_word in car_part.upper() for exclude_word in exclude_words):
                    return car_part
    
    return ""

def extract_cost_price(text: str) -> float:
    # Ищет сумму, формат: 112000.00, 112 000,00, 112,000.00, 2000 EUR и т.п.
    price_pattern = r'([\d\.,\s]{3,})\s?(EUR|USD|PLN|€|\$)?'
    matches = re.findall(price_pattern, text)
    # ищем максимальную сумму вхождения
    max_val = 0
    for m in matches:
        s = m[0].replace(" ", "").replace(",", ".")
        try:
            val = float(s)
            if val > max_val:
                max_val = val
        except Exception:
            pass
    return max_val

def extract_currency(text: str) -> str:
    # Просто ищет первую валюту по тексту
    if "EUR" in text or "€" in text:
        return "EUR"
    if "USD" in text or "$" in text:
        return "USD"
    if "PLN" in text:
        return "PLN"
    return ""

def extract_company(text: str) -> str:
    # Наши компании
    if "TaVie Europe OÜ" in text or "TaVie Europe OU" in text or "EE102288270" in text:
        return "TaVie Europe OÜ"
    if any(name in text for name in ["Parkentertainment Sp. z o.o.", "Parkentertainment", "PL5272956146"]):
        return "Parkentertainment Sp. z o.o."
    return ""

def extract_supplier(text: str) -> Supplier:
    # Упрощённо: ищет строку "Supplier" или "Seller" и ближайшие строки
    import re
    name = vat = address = phone = country = tax_id = email = None
    
    lines = text.splitlines()
    
    # Сначала найдем название поставщика
    supplier_section_start = -1
    supplier_section_end = -1
    
    for i, line in enumerate(lines):
        line = line.strip()
        
        # Ищем название компании (первая строка с GmbH, Inc, Ltd, etc.)
        if not name and any(suffix in line for suffix in ['GmbH', 'Inc.', 'Ltd', 'LLC', 'AG', 'KG', 'Co.', 'Sp.', 'OÜ', 'AS']):
            # Исключаем нашу компанию (покупателя)
            if not any(our_name in line for our_name in ['Parkentertainment', 'TaVie']):
                name = line
                supplier_section_start = i
                # Определяем конец секции поставщика (до нашей компании)
                for j in range(i + 1, min(i + 50, len(lines))):  # Увеличиваем поиск до 50 строк
                    if any(our_name in lines[j] for our_name in ['Parkentertainment', 'TaVie']):
                        supplier_section_end = j
                        break
                if supplier_section_end == -1:
                    supplier_section_end = min(i + 50, len(lines))
                break
    
    # Если нашли секцию поставщика, ищем данные только в ней
    search_lines = lines[supplier_section_start:supplier_section_end] if supplier_section_start != -1 else lines[:50]
    
    for i, line in enumerate(search_lines):
        line = line.strip()
            
        # Ищем VAT/TAX ID/USt-IdNr
        if any(keyword in line.upper() for keyword in ['VAT', 'TAX ID', 'НДС', 'UST-IDNR', 'STEUERNUMMER', 'TAX NO']):
            # Извлекаем VAT номер из этой строки или следующей
            vat_match = re.search(r'([A-Z]{2}\d{5,15}|\d{8,15})', line)
            if vat_match:
                vat = vat_match.group(1)
            elif i + 1 < len(search_lines):
                # Проверяем следующую строку
                next_line = search_lines[i + 1].strip()
                vat_match = re.search(r'([A-Z]{2}\d{5,15}|\d{8,15})', next_line)
                if vat_match:
                    vat = vat_match.group(1)
                    
        # Ищем адрес (строки с номерами домов и почтовыми индексами)
        if not address and re.search(r'\d{2,5}\s+[A-Za-zÄÖÜäöüß]+', line):
            address = line
            
        # Ищем телефон
        if not phone and re.search(r'[\+]?[\d\s\-\(\)]{8,}', line) and any(keyword in line.upper() for keyword in ['TEL', 'PHONE', 'TELEFON']):
            phone_match = re.search(r'[\+]?[\d\s\-\(\)]{8,}', line)
            if phone_match:
                phone = phone_match.group(0).strip()
                
        # Ищем email
        if not email and re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', line):
            email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', line)
            if email_match:
                email = email_match.group(0)
        
        # Определяем страну по контексту ТОЛЬКО в секции поставщика
        if any(country_word in line.upper() for country_word in ['GERMANY', 'DEUTSCHLAND', 'HAMELN', 'BERLIN', 'MÜNCHEN', 'HANNOVER']):
            country = "Germany"
        elif any(country_word in line.upper() for country_word in ['POLAND', 'POLSKA', 'WARSZAWA', 'KRAKÓW', 'GDANSK']):
            country = "Poland"
        elif any(country_word in line.upper() for country_word in ['ESTONIA', 'EESTI', 'TALLINN']):
            country = "Estonia"
    
    # Если email не найден в секции поставщика, ищем в первой половине документа
    if not email:
        for line in lines[:len(lines)//2]:  # Первая половина документа
            email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', line)
            if email_match:
                found_email = email_match.group(0)
                # Проверяем, что это не email нашей компании
                if not any(our_domain in found_email.lower() for our_domain in ['tavie', 'parkentertainment']):
                    email = found_email
                    break
    
    # Если страна не определена, попробуем по адресу
    if not country and address:
        if any(city in address.upper() for city in ['HAMELN', 'BERLIN', 'MÜNCHEN', 'HANNOVER']):
            country = "Germany"
        elif any(city in address.upper() for city in ['WARSZAWA', 'KRAKÓW', 'GDANSK']):
            country = "Poland"
        elif any(city in address.upper() for city in ['TALLINN']):
            country = "Estonia"
            
    return Supplier(name, vat, address, phone, country, tax_id, email)

def extract_payment_terms(text: str) -> str:
    # Ищет условия оплаты по ключевым словам
    for line in text.splitlines():
        if re.search(r'(Payment Terms|Срок оплаты|Due date|Оплата до)', line, re.IGNORECASE):
            return line.split(":")[-1].strip()
    return ""

def extract_bill_number(text: str) -> str:
    # Ищет номер счета (по ключевым словам)
    match = re.search(r'(No\.|Nr\.?|№)\s?([A-Z0-9-]+)', text, re.IGNORECASE)
    if match:
        return match.group(2)
    return ""

def extract_date(text: str) -> str:
    # Простейшее: ищет YYYY-MM-DD или DD.MM.YYYY
    match = re.search(r'(\d{4}-\d{2}-\d{2})|(\d{2}[./]\d{2}[./]\d{4})', text)
    if match:
        return match.group(0)
    return ""

def extract_item_details(text: str) -> str:
    # Находит назначение платежа
    keywords = ["Accounting Plan", "Transport", "Commission", "Service", "Перевозка", "Комиссия"]
    for k in keywords:
        if k.lower() in text.lower():
            return k
    # Если не найдено — первые 2 строки после supplier
    return text.splitlines()[5] if len(text.splitlines()) > 5 else ""

def map_account(item_details: str) -> str:
    # Маппинг для Zoho (сокращённый пример)
    mapping = {
        "Accounting Plan": "Accounting fees",
        "Transport": "Transportation services",
        "Commission": "Consultant Expense",
        "Service": "Consultant Expense",
        "Перевозка": "Transportation services",
        "Комиссия": "Consultant Expense",
    }
    for key, acc in mapping.items():
        if key.lower() in item_details.lower():
            return acc
    return "General Expense"

def extract_tax_rate(text: str, our_company: str, supplier: Supplier) -> str:
    # Логика: если обе эстонские — 22, если обе польские — 23, иначе 0
    if our_company == "TaVie Europe OÜ" and supplier and supplier.country and "Эстония" in supplier.country:
        return "EST - 22"
    if our_company == "Parkentertainment Sp. z o.o." and supplier and supplier.country and "Польша" in supplier.country:
        return "PL - 23"
    return "0"

# --- Основная функция маршрутизации ---

def route_document(text: str):
    doc_type = detect_document_type(text)
    our_company = extract_company(text)
    supplier = extract_supplier(text)
    
    if doc_type == "proforma" and is_car_invoice(text):
        vin = extract_vin(text)
        car_model = extract_car_model(text)
        car_item_name = f"{car_model}_{vin[-5:]}" if vin else ""
        cost_price = extract_cost_price(text)
        currency = extract_currency(text)
        payment_terms = extract_payment_terms(text)
        tax_rate = extract_tax_rate(text, our_company, supplier)
        return Proforma(
            vin=vin,
            cost_price=cost_price,
            supplier=supplier,
            car_model=car_model,
            car_item_name=car_item_name,
            is_valid_for_us=True,
            our_company=our_company,
            tax_rate=tax_rate,
            currency=currency,
            payment_terms=payment_terms
        )
    elif doc_type == "contract" and is_car_invoice(text):
        # Обработка контрактов на покупку автомобилей
        vin = extract_vin(text)
        car_model = extract_car_model(text)
        car_item_name = f"{car_model}_{vin[-5:]}" if vin else ""
        bill_number = extract_bill_number(text)
        date = extract_date(text)
        currency = extract_currency(text)
        total_amount = extract_cost_price(text)
        item_details = f"{car_model}, VIN: {vin}" if vin else car_model
        payment_terms = extract_payment_terms(text)
        
        return Contract(
            bill_number=bill_number,
            supplier=supplier,
            date=date,
            currency=currency,
            total_amount=total_amount,
            item_details=item_details,
            account="Vehicle Purchase",
            our_company=our_company,
            vin=vin,
            car_model=car_model,
            car_item_name=car_item_name,
            contract_type="purchase",
            payment_terms=payment_terms
        )
    elif doc_type == "invoice" and not is_car_invoice(text):
        bill_number = extract_bill_number(text)
        date = extract_date(text)
        currency = extract_currency(text)
        total_amount = extract_cost_price(text)
        item_details = extract_item_details(text)
        account = map_account(item_details)
        return Invoice(
            bill_number=bill_number,
            supplier=supplier,
            date=date,
            currency=currency,
            total_amount=total_amount,
            item_details=item_details,
            account=account,
            our_company=our_company
        )
    # Если не определено — None
    return None