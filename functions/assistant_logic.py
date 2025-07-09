def ensure_document_type_field(data: dict, ocr_text: str = "") -> dict:
    """
    Гарантирует наличие поля document_type в JSON. Если его нет — определяет автоматически.
    """
    if "document_type" not in data or not data["document_type"]:
        doc_type = guess_document_type(data, ocr_text)
        data["document_type"] = doc_type
        print(f"⚠️ WARNING: Не найден document_type! Определено автоматически как: {doc_type}")
    return data

def log_doc_type_and_number(data: dict, ocr_text: str = ""):
    doc_type = data.get("document_type", "").strip().lower()
    bill_no = data.get("bill_number") or data.get("proforma_number") or ""
    if not doc_type or doc_type == "unknown":
        doc_type = guess_document_type(data, ocr_text)
        data["document_type"] = doc_type
        if doc_type == "unknown":
            print(f"⚠️ Ошибка: не удалось определить тип документа! OCR (фрагмент): {ocr_text[:300]}")
            return False
    print(f"📝 Определён тип документа: {doc_type}, номер: {bill_no}")
    return True

# --- Справочник наших компаний (OUR_COMPANIES) ---
OUR_COMPANIES = [
    {
        "name": "TaVie Europe OÜ",
        "vat": "EE102288270",
        "address": "Harju maakond, Tallinn, Kesklinna linнаоса, Pirita tee 26f-11, 12011",
        "country": "Эстония",
    },
    {
        "name": "Parkentertainment Sp. z o.o.",
        "vat": "PL5272956146",
        "address": "UL. KROCHMALNA 54 /U6, 00-864, Warszawa",
        "country": "Польша",
    },
    # --- Можно добавить варианты написаний ---
    {
        "name": "TaVie Europe OU",
        "vat": "EE102288270",
        "address": "",
        "country": "",
    },
]

def guess_document_type(data: dict, ocr_text: str) -> str:
    ocr = ocr_text.lower()
    ocr_top = ocr_text[:300].lower()

    # Приоритет по словам в верхней части OCR
    if any(word in ocr_top for word in ["proforma"]):
        return "Proforma"
    if any(word in ocr_top for word in ["credit note", "gutschrift"]):
        return "Credit Note"
    if any(word in ocr_top for word in ["invoice", "rechnung", "facture", "fattura", "factura", "faktura", "счет", "bill", "retainer"]):
        # Если одновременно есть и invoice и proforma в верхней части, отдаём приоритет proforma
        if "proforma" in ocr_top:
            return "Proforma"
        return "Invoice"

    # Если не нашли в верхней части, ищем по всему тексту
    has_proforma = "proforma" in ocr
    has_invoice = any(word in ocr for word in ["invoice", "rechnung", "facture", "fattura", "factura", "faktura", "счет", "bill", "retainer"])
    has_credit_note = "credit note" in ocr or "gutschrift" in ocr

    if has_proforma and has_invoice:
        return "Proforma"
    if has_proforma:
        return "Proforma"
    if has_invoice:
        return "Invoice"
    if has_credit_note:
        return "Credit Note"

    return "unknown"

def update_country_by_address(data: dict) -> None:
    supplier = data.get("supplier", {})
    if isinstance(supplier, dict):
        address = supplier.get("address", "").lower()
        country = supplier.get("country", "").lower()
        if "berlin" in address or "deutschland" in address:
            supplier["country"] = "Germany"
        elif "warszawa" in address or "polska" in address:
            supplier["country"] = "Poland"
        elif "tallinn" in address or "eesti" in address:
            supplier["country"] = "Estonia"
        else:
            supplier["country"] = supplier.get("country", "")
        data["supplier"] = supplier

def normalize_currency(value: str) -> str:
    if not value:
        return ""
    if "€" in value:
        return "EUR"
    if "$" in value:
        return "USD"
    return value

def normalize_currencies(data: dict) -> None:
    # Normalize currency at root level
    if "currency" in data:
        data["currency"] = normalize_currency(data.get("currency", ""))
    # Normalize supplier country and currency if present
    supplier = data.get("supplier", {})
    if isinstance(supplier, dict):
        if "country" in supplier:
            country_val = supplier.get("country", "")
            if "€" in country_val:
                supplier["country"] = "EUR"
            elif "$" in country_val:
                supplier["country"] = "USD"
        if "currency" in supplier:
            supplier["currency"] = normalize_currency(supplier.get("currency", ""))
        data["supplier"] = supplier

def is_our_supplier(supplier: dict) -> bool:
    if not supplier or not isinstance(supplier, dict):
        return False
    supplier_name = (supplier.get("name") or "").lower().strip()
    supplier_vat = (supplier.get("vat") or "").replace(" ", "")
    for our in OUR_COMPANIES:
        if supplier_name == our["name"].lower().strip() or supplier_vat == our["vat"]:
            return True
    return False

def should_skip_invoice(data: dict) -> bool:
    """
    Пропускать обработку, если supplier — наша фирма (исходящий счет).
    """
    supplier = data.get("supplier", {})
    return is_our_supplier(supplier)

def fix_supplier_and_our_company(data: dict, ocr_text: str = "") -> None:
    supplier = data.get("supplier", {})
    supplier_name = supplier.get("name", "") if isinstance(supplier, dict) else ""
    supplier_vat = supplier.get("vat", "") if isinstance(supplier, dict) else ""
    our_company = data.get("our_company", "")

    # Если supplier — это наша компания, значит это исходящий счет, our_company должен быть пустым
    if should_skip_invoice(data):
        data["our_company"] = ""
        return

    # Если our_company некорректен (например, поставщик), ищем нашу фирму по OCR
    ocr_l = ocr_text.lower()
    found = None
    for our in OUR_COMPANIES:
        if our["name"].lower() in ocr_l or our["vat"].lower() in ocr_l:
            found = our["name"]
            break
    # Если нашли свою компанию среди реквизитов — подставляем
    if found:
        data["our_company"] = found
    else:
        # если не нашли, просто первая из списка (как дефолт)
        data["our_company"] = OUR_COMPANIES[0]["name"]

import json
from datetime import datetime
import re
def extract_vin_from_item_details(item_details: str) -> str:
    """
    Извлекает VIN (17 символов) из item_details, если он есть.
    """
    # Безопасно обрабатываем разные типы данных
    if isinstance(item_details, list):
        # Если список, объединяем элементы в строку
        item_details = " ".join(str(item) for item in item_details)
    elif not isinstance(item_details, str):
        # Если не строка, преобразуем в строку
        item_details = str(item_details) if item_details is not None else ""
    
    if not item_details:
        return ""
    match = re.search(r'\b([A-HJ-NPR-Z0-9]{17})\b', item_details.replace(" ", ""))
    if match:
        return match.group(1)
    return ""


SYSTEM_PROMPT = """
Ты — ассистент по структурированию документов (Proforma/Invoice) для Zoho Books. На вход получаешь только распознанный текст PDF (OCR).

1. Определи тип документа (Invoice, Proforma, Credit Note и т.д.) исключительно по заголовку или верхней части документа (например, слова 'Rechnung', 'Invoice', 'Proforma Invoice' и т.д.).
2. ВСЕГДА добавляй поле "document_type" в JSON с одним из значений: "Invoice", "Proforma", "Credit Note" и т.д.
3. Извлекай все необходимые поля даже если они разбросаны по тексту.
4. Верни ТОЛЬКО валидный JSON (см. ниже), никаких комментариев, пояснений или текста. Если поле не найдено — для строки верни "", для числа или логического значения — null.

Обязательные требования:
- Для поля "item_details" ВСЕГДА используй реальное описание товара/услуги из документа. Примеры:
    - Для услуг: "Automobilių pervežimo paslauga", "Car transportation service", "Ремонт автомобиля"
    - Для покупки автомобиля: "Mercedes Benz G63 AMG" или VIN номер
- Если в документе есть VIN (17 символов, латиница/цифры) и модель автомобиля, обязательно заполни поля "vin" и "car_model".
- Поле "car_item_name" формируется отдельно системой как "{car_model}_{5 последних цифр VIN}".
- Для поля "total_amount" — если это покупка автомобиля, используй ПОЛНУЮ стоимость автомобиля до вычета предоплат, а не итоговую сумму к доплате. Ищи "Total", "Amount", "Gesamtbetrag" перед вычетами.
- Для поля "account" — НИКОГДА не вставляй банковские реквизиты (IBAN, SWIFT, BIC, название банка, номер счета и т.д.), а только название категории расходов по ключевым словам из справочника или по тексту услуги.
- Если в документе есть строка с юридическим лицом (обычно перед строкой с VAT/EIN/NIP), supplier должен быть именно этим юридическим лицом, а не брендом/платформой. Бренд/платформу можно сохранить в отдельное поле (например, 'brand' или 'service_name'), если нужно.
- Пример: если в документе есть 'Anysphere, Inc.' перед 'US EIN 87-4436547', supplier = 'Anysphere, Inc.', supplier.vat = '87-4436547'.

Пример для Invoice:
{"document_type": "Invoice", "bill_number": "", "supplier": {"name": "", "vat": "", "address": "", "country": ""}, "date": "", "currency": "", "total_amount": null, "item_details": "", "account": "", "our_company": ""}

Пример для Proforma:
{"document_type": "Proforma", "vin": "", "cost_price": null, "supplier": {"name": "", "vat": "", "address": "", "phone": "", "country": ""}, "car_model": "", "car_item_name": "", "is_valid_for_us": null, "our_company": "", "tax_rate": "", "currency": "", "payment_terms": ""}

ВСЕГДА выдавай только валидный JSON, даже если не найдено ни одно поле. Никаких пояснений, текста, комментариев или дополнительной информации — только JSON!
"""


DESCRIPTION_TO_ACCOUNT = {
    "accounting": "Accounting fees",
    "transport": "Transportation services",
    "shipping": "Transportation services",
    "pervežimo": "Transportation services",
    "delivery": "Transportation services",
    "доставка": "Transportation services",
    "перевозка": "Transportation services",
    "przewóz": "Transportation services",
    "dostawa": "Transportation services",
    "consulting": "Consultant Expense",
    "internet": "IT and Internet Expenses",
    "software": "IT and Internet Expenses",
    "rent": "Rent Expense",
    "commission": "Consultant Expense",
    "service": "Other Expenses",
    "plan": "Accounting fees",
    "entertainment": "Meals and Entertainment",
    "advertising": "Advertising And Marketing",
    "stationery": "Printing and Stationery",
    "cleaning": "Janitorial Expense",
    "maintenance": "Repairs and Maintenance",
    # Добавляем категории для покупки автомобилей
    "ferrari": "Vehicle Purchase",
    "mercedes": "Vehicle Purchase", 
    "bmw": "Vehicle Purchase",
    "audi": "Vehicle Purchase",
    "porsche": "Vehicle Purchase",
    "lamborghini": "Vehicle Purchase",
    "bentley": "Vehicle Purchase",
    "rolls royce": "Vehicle Purchase",
    "maserati": "Vehicle Purchase",
    "aston martin": "Vehicle Purchase",
    "car": "Vehicle Purchase",
    "vehicle": "Vehicle Purchase",
    "automobile": "Vehicle Purchase",
    "coupe": "Vehicle Purchase",
    "sedan": "Vehicle Purchase",
    "suv": "Vehicle Purchase",
    "cabriolet": "Vehicle Purchase",
    "convertible": "Vehicle Purchase",
}

def force_clean_item_details_and_account(data):
    """
    Формирует car_item_name = "{car_model}_{5 последних цифр VIN}" только для автомобильных документов.
    Для account запрещает IBAN, SWIFT, банк и оставляет только по справочнику.
    НЕ изменяет item_details - оставляет описание товара/услуги как есть.
    """
    # --- car_item_name только для документов с VIN и car_model ---
    vin = data.get("vin", "")
    car_model = data.get("car_model", "")
    if vin and car_model:
        # Извлекаем только последние 5 ЦИФР из VIN
        last_5_digits = re.sub(r'[^0-9]', '', vin)[-5:] if re.sub(r'[^0-9]', '', vin) else ""
        if last_5_digits and len(last_5_digits) == 5:
            data["car_item_name"] = f"{car_model}_{last_5_digits}"

    # --- account ---
    account = data.get("account", "")
    forbidden_words = ["iban", "swift", "bic", "bank", "konto", "расчетный счет", "acc.", "acc:", "номер счета"]
    if any(word in account.lower() for word in forbidden_words):
        data["account"] = detect_account(data.get("item_details", ""))

def detect_account(item_details: str) -> str:
    # Безопасно обрабатываем разные типы данных
    if isinstance(item_details, list):
        # Если список, объединяем элементы в строку
        item_details = " ".join(str(item) for item in item_details)
    elif not isinstance(item_details, str):
        # Если не строка, преобразуем в строку
        item_details = str(item_details) if item_details is not None else ""
    
    item_lower = item_details.lower()
    # Добавлено условие для consulting/consultant
    if "consulting" in item_lower or "consultant" in item_lower:
        return "Consultant Expense"
    for keyword, account in DESCRIPTION_TO_ACCOUNT.items():
        if keyword in item_lower:
            return account
    return "Other Expenses"

def process_invoice_json(data: dict, existing_bills: list[tuple[str, str]], ocr_text: str = "") -> dict:
    """
    Обрабатывает JSON из ассистента для Invoice (услуги и прочее):
    - проверяет дубликаты bill_number
    - определяет account по назначению
    - пропускает исходящие счета
    Обработка только входящих счетов; исходящие пропускаются
    """
    data = ensure_document_type_field(data, ocr_text)
    if not log_doc_type_and_number(data, ocr_text):
        return {"skip_processing": True}
    if data.get("document_type", "").lower() == "unknown":
        print("❌ Не удалось определить тип документа — обработка остановлена.")
        return {"skip_processing": True}
    fix_supplier_and_our_company(data, ocr_text)
    update_country_by_address(data)
    normalize_currencies(data)
    # --- Гарантия извлечения VIN и car_item_name для инвойсов по авто ---
    if not data.get("vin"):
        data["vin"] = extract_vin_from_item_details(data.get("item_details", ""))
    if not data.get("car_item_name") and data.get("car_model") and data.get("vin"):
        vin = data["vin"]
        last5 = vin[-5:] if len(vin) >= 5 else vin
        data["car_item_name"] = f"{data['car_model']}_{last5}"
    if should_skip_invoice(data):
        print("🛑 Обнаружен исходящий счет — обработка пропущена.")
        return {"skip_processing": True}
    bill_no = data.get("bill_number")
    supplier_name = data.get("supplier", {}).get("name", "")
    if bill_no is not None and any(
        b[0] == bill_no and supplier_name != b[1]
        for b in existing_bills
    ):
        data["bill_number"] = f"{bill_no} (the same)"
    item_details = data.get("item_details", "")
    data["account"] = detect_account(item_details)
    # Гарантируем наличие поля document_type с актуальным значением
    if "document_type" not in data or not data["document_type"]:
        data["document_type"] = guess_document_type(data, ocr_text)
    force_clean_item_details_and_account(data)
    return data

def process_proforma_json(data: dict, ocr_text: str = "") -> dict:
    """
    Обрабатывает JSON из ассистента для Proforma (машины):
    - формирует car_item_name
    - подставляет is_valid_for_us = True
    - пропускает исходящие счета
    Обработка только входящих проформ; исходящие пропускаются
    """
    data = ensure_document_type_field(data, ocr_text)
    if not log_doc_type_and_number(data, ocr_text):
        return {"skip_processing": True}
    if data.get("document_type", "").lower() == "unknown":
        print("❌ Не удалось определить тип документа — обработка остановлена.")
        return {"skip_processing": True}
    fix_supplier_and_our_company(data, ocr_text)
    update_country_by_address(data)
    normalize_currencies(data)
    if should_skip_invoice(data):
        print("🛑 Обнаружен исходящий счет — обработка пропущена.")
        return {"skip_processing": True}
    model = data.get("car_model", "")
    vin = data.get("vin", "")
    last5 = vin[-5:] if len(vin) >= 5 else vin
    data["car_item_name"] = f"{model}_{last5}"
    data["is_valid_for_us"] = True
    # Гарантируем наличие поля document_type с актуальным значением
    if "document_type" not in data or not data["document_type"]:
        data["document_type"] = guess_document_type(data, ocr_text)
    force_clean_item_details_and_account(data)
    return data

def is_outgoing_invoice(data: dict) -> bool:
    """
    Проверяет, что invoice/проформа исходящий — supplier совпадает с одной из наших компаний.
    """
    supplier = data.get("supplier", {})
    return is_our_supplier(supplier)

def is_auto_proforma(data: dict) -> bool:
    """
    True если это проформа по автомобилю (VIN и car_model не пустые).
    """
    return bool(data.get("vin")) and bool(data.get("car_model"))

def zoho_create_quote(data: dict, ocr_text: str = ""):
    """
    Создаём quote ТОЛЬКО если это проформа по авто (document_type == Proforma и есть vin и car_model).
    Для Invoice или других типов документов — не создаём quote!
    """
    doc_type = data.get("document_type", "").strip().lower()
    vin = data.get("vin", "")
    car_model = data.get("car_model", "")
    bill_no = data.get("bill_number") or data.get("proforma_number") or ""
    if doc_type == "unknown":
        print(f"❌ Тип документа не определён! Quote не создаётся. OCR (фрагмент): {ocr_text[:300]}")
        print("❌ Quote не создан, так как тип не определён.")
        return False
    if doc_type != "proforma":
        print(f"❌ Quote не создаётся, так как тип документа '{doc_type}' не 'proforma'.")
        return False
    if not vin or not car_model:
        print("❌ Quote не создаётся, так как отсутствует VIN или модель автомобиля.")
        return False
    print(f"[ZOHO] 🚗 Был бы создан quote по типу документа: {doc_type}, VIN: {vin}, Модель: {car_model}, Номер: {bill_no}")
    return True