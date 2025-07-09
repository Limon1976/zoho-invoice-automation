from mcp_connector.models import Proforma, Invoice, Supplier
import re

# --- Вспомогательные функции ---

def detect_document_type(text: str) -> str:
    """
    Определяет тип документа: proforma/invoice/credit_note/unknown.
    """
    # Приводим к нижнему регистру для удобства поиска
    text_lower = text.lower()

    # Ключевые слова для разных типов документов
    proforma_keywords = ["proforma"]
    invoice_keywords = [
        "invoice", "Rechnung", "bill", "tagasiside", "faktura", "счет", "facture", "fattura", "factura", "nota", "factuur"
    ]
    credit_note_keywords = ["credit note", "gutschrift", "nota de crédito", "avoir"]

    for word in proforma_keywords:
        if word in text_lower:
            return "proforma"
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
    brands = ["BMW", "Audi", "Volkswagen", "Mercedes", "Toyota", "Land Rover", "Range Rover", "RR", "Porsche", "Volvo", "Ford"]
    lines = text.splitlines()
    for line in lines:
        for brand in brands:
            if brand in line and not re.search(r'\b[A-HJ-NPR-Z0-9]{17}\b', line):
                return line.strip()
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
    # Твои фирмы
    if "TaVie Europe OÜ" in text or "EE102288270" in text:
        return "TaVie Europe OÜ"
    if "Parkentertainment Sp. z o.o." in text or "PL5272956146" in text:
        return "Parkentertainment Sp. z o.o."
    return ""

def extract_supplier(text: str) -> Supplier:
    # Упрощённо: ищет строку "Supplier" или "Seller" и ближайшие строки
    name = vat = address = phone = country = tax_id = None
    for line in text.splitlines():
        if re.search(r'(Supplier|Seller|Поставщик|Продавец)', line, re.IGNORECASE):
            name = line.split(":")[-1].strip()
        if re.search(r'VAT|TAX ID|НДС', line, re.IGNORECASE):
            vat = re.search(r'[A-Z]{2}\d{5,12}', line)
            vat = vat.group(0) if vat else line.split(":")[-1].strip()
        if re.search(r'Address|Адрес', line, re.IGNORECASE):
            address = line.split(":")[-1].strip()
        if re.search(r'Phone|Телефон', line, re.IGNORECASE):
            phone = line.split(":")[-1].strip()
        if re.search(r'Poland|Estonia|Эстония|Польша', line, re.IGNORECASE):
            country = "Польша" if "Poland" in line or "Польша" in line else "Эстония"
        if re.search(r'TAX ID|VAT', line, re.IGNORECASE):
            tax_id = line.split(":")[-1].strip()
    return Supplier(name, vat, address, phone, country, tax_id)

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