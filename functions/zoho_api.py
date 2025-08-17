import os
import requests
import time
import calendar
from dotenv import load_dotenv
import json
import re
from typing import Optional
from datetime import datetime
# ВАЖНО: не импортируем bills_cache_manager на уровне модуля, чтобы избежать циклического импорта

# Загружаем переменные окружения
load_dotenv("/Users/macos/my_project/.env")

# API-константы
ZOHO_CLIENT_ID = os.getenv("ZOHO_CLIENT_ID")
ZOHO_CLIENT_SECRET = os.getenv("ZOHO_CLIENT_SECRET")
ZOHO_REFRESH_TOKEN = os.getenv("ZOHO_REFRESH_TOKEN")
TOKEN_URL = "https://accounts.zoho.eu/oauth/v2/token"
BILLS_URL = "https://www.zohoapis.eu/books/v3/bills"
SETTINGS_BRANCHES_URL = "https://www.zohoapis.eu/books/v3/branches"
SETTINGS_TAXES_URL = "https://www.zohoapis.eu/books/v3/settings/taxes"

# Организации (очищаем от лишних пробелов)
ORG_ID_1 = os.getenv("ZOHO_ORGANIZATION_ID_1", "").strip()
ORG_ID_2 = os.getenv("ZOHO_ORGANIZATION_ID_2", "").strip()

# Файл логов
LOG_FILE = "/Users/macos/my_project/zoho_api.log"

# Кэшируем токен в памяти
ACCESS_TOKEN = None

def log_message(message):
    """Функция для записи логов."""
    with open(LOG_FILE, "a") as log:
        log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {message}\n")
    print(message)

def get_access_token():
    """Получаем access_token и кэшируем его."""
    global ACCESS_TOKEN
    if ACCESS_TOKEN:
        return ACCESS_TOKEN

    params = {
        "refresh_token": ZOHO_REFRESH_TOKEN,
        "client_id": ZOHO_CLIENT_ID,
        "client_secret": ZOHO_CLIENT_SECRET,
        "grant_type": "refresh_token"
    }

    response = requests.post(TOKEN_URL, data=params)
    data = response.json()

    if "access_token" in data:
        ACCESS_TOKEN = data["access_token"]
        os.environ["ZOHO_ACCESS_TOKEN"] = ACCESS_TOKEN  # Обновляем переменную окружения
        log_message("✅ ZOHO_ACCESS_TOKEN обновлён и сохранён.")
        return ACCESS_TOKEN
    else:
        log_message(f"❌ Ошибка при получении токена: {data}")
        raise ValueError(f"Ошибка при получении токена: {data}")

def get_bills(org_id, year, month):
    """Получаем список Bill за указанный месяц и год."""
    access_token = get_access_token()
    headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}

    # Определяем количество дней в месяце
    last_day = calendar.monthrange(year, month)[1]
    
    params = {
        "organization_id": org_id,
        "date_start": f"{year}-{month:02d}-01",
        "date_end": f"{year}-{month:02d}-{last_day}"
    }

    log_message(f"📤 Запрос счетов с organization_id={org_id}: {params}")

    response = requests.get(BILLS_URL, headers=headers, params=params)
    if response.status_code == 401:
        log_message("🔄 Токен устарел. Обновляем...")
        global ACCESS_TOKEN
        ACCESS_TOKEN = None
        return get_bills(org_id, year, month)

    data = response.json()
    if "bills" not in data:
        log_message(f"❌ Ошибка API: {data}")
        return []

    bills_list = []
    for bill in data["bills"]:
        bill_id = bill["bill_id"]
        has_attachment = bill.get("has_attachment", False)
        attachment_id = bill_id if has_attachment else None
        bills_list.append((bill["bill_number"], bill_id, has_attachment, attachment_id))
    
    return bills_list

def get_bill_details(org_id: str, bill_id: str) -> Optional[dict]:
    """
    Возвращает полные детали счета (Bill) по bill_id
    """
    access_token = get_access_token()
    headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}
    url = f"{BILLS_URL}/{bill_id}"
    params = {"organization_id": org_id}
    response = requests.get(url, headers=headers, params=params)
    data = response.json()
    if response.status_code in (200, 201) and data.get("bill"):
        return data["bill"]
    log_message(f"❌ Ошибка получения деталей счета {bill_id}: {data}")
    return None

def download_attachment(org_id, bill_id, save_path):
    """Скачивает вложение счета."""
    access_token = get_access_token()
    headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}
    url = f"{BILLS_URL}/{bill_id}/attachment?organization_id={org_id}"

    response = requests.get(url, headers=headers, stream=True)
    if response.status_code == 200:
        file_path = os.path.join(save_path, f"invoice_{bill_id}.pdf")
        with open(file_path, "wb") as file:
            for chunk in response.iter_content(chunk_size=1024):
                file.write(chunk)
        print(f"✅ Вложение сохранено: {file_path}")
    else:
        print(f"❌ Ошибка скачивания вложения: {response.json()}")

if __name__ == "__main__":
    print("\n📌 Доступные организации:")
    print("1 - TaVie Europe OÜ")
    print("2 - PARKENTERTAINMENT Sp. z o. o.")

    choice = input("\nВведите номер организации (1 или 2): ").strip()
    org_id = ORG_ID_1 if choice == "1" else ORG_ID_2

    year = int(input("Введите год (например, 2025): ").strip())
    month = int(input("Введите месяц (например, 02): ").strip())

    bills = get_bills(org_id, year, month)

    if bills:
        print(f"\n📋 Найденные счета:")
        for bill_number, bill_id, has_attachment, attachment_id in bills:
            print(f"📄 Номер: {bill_number}, ID: {bill_id}, Вложения: {has_attachment}, Attachment ID: {attachment_id}")

        bill_id = input("\nВведите ID счета для скачивания вложения: ").strip()
        save_path = input("Введите путь для сохранения (оставьте пустым для ~/Downloads): ").strip()
        save_path = save_path if save_path else os.path.expanduser("~/Downloads")

        download_attachment(org_id, bill_id, save_path)
    else:
        print(f"\n❌ `Bill` за {year}-{month} не найдены.")


def get_existing_bill_numbers(org_id: str) -> list:
    """
    Возвращает список всех номеров счетов (bill_number) из Zoho Books для заданной организации.
    """
    access_token = get_access_token()
    headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}

    params = {
        "organization_id": org_id,
        "sort_column": "bill_number",
        "sort_order": "A",
        "per_page": 200,  # Максимально допустимое значение
        "page": 1,
    }

    bill_numbers = []

    while True:
        response = requests.get(BILLS_URL, headers=headers, params=params)
        data = response.json()

        if "bills" not in data:
            log_message(f"❌ Ошибка получения счетов: {data}")
            break

        for bill in data["bills"]:
            bill_numbers.append((bill["bill_number"], bill["vendor_name"]))

        if not data.get("page_context", {}).get("has_more_page"):
            break

        params["page"] += 1

    return bill_numbers

def bill_exists(org_id: str, bill_number: str, vendor_id: Optional[str] = None, vendor_name: Optional[str] = None) -> Optional[dict]:
    """
    Проверяет существование счета (Bill) по номеру в заданной организации.
    Если указан vendor_id, дополнительно фильтрует по поставщику.

    Returns:
        dict | None: Объект счета из Zoho, если найдено точное совпадение, иначе None.
    """
    if not bill_number:
        return None

    access_token = get_access_token()
    headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}

    # Нормализация номера: только буквы+цифры (верхний регистр) и отдельно только цифры
    def _normalize(s: str) -> str:
        return "".join(ch for ch in s.upper() if ch.isalnum())
    def _normalize_confusables(s: str) -> str:
        # Учитываем частые OCR-подмены: I<->1, O<->0, B<->8
        table = str.maketrans({
            'I': '1', 'L': '1', '|': '1',
            'O': '0', 'Q': '0',
            'B': '8'
        })
        return _normalize(s.translate(table))
    def _digits(s: str) -> str:
        return "".join(ch for ch in s if ch.isdigit())
    def _lead_letters(s: str) -> str:
        m = re.match(r"^[A-Za-z]+", s.strip())
        return (m.group(0) if m else "").upper()

    norm_target = _normalize(bill_number)
    digits_target = _digits(bill_number)
    prefix_target = _lead_letters(bill_number)

    # Нормализация и алиасы поставщиков
    BUSINESS_SUFFIXES = [
        'INC', 'INC.', 'LLC', 'L.L.C.', 'LTD', 'LTD.', 'LIMITED', 'GMBH', 'G.M.B.H.', 'OÜ', 'OU', 'BV', 'B.V.',
        'S.A.', 'SA', 'SP. Z O.O.', 'SP Z O.O.', 'SP Z OO', 'SPÓŁKA Z O.O.'
    ]
    VENDOR_ALIASES = {
        # key -> canonical
        'ANYSphere': 'CURSOR',
        'ANSPHERE': 'CURSOR',
        'ANYSHPERE': 'CURSOR',
        'ANYSPHERE, INC': 'CURSOR',
        'ANYSPHERE INC': 'CURSOR',
        'CURSOR': 'CURSOR',
    }
    def _clean_vendor_name(name: str) -> str:
        if not name:
            return ''
        s = re.sub(r"[^A-Z0-9 ]+", " ", name.upper()).strip()
        # remove multiple spaces
        s = re.sub(r"\s+", " ", s)
        # remove business suffixes at end
        for suf in BUSINESS_SUFFIXES:
            suf_u = suf.upper()
            if s.endswith(" " + suf_u):
                s = s[: -len(suf_u)-1].strip()
        # alias mapping
        s_no_punct = s.replace('.', '').replace(',', '')
        for alias, canonical in VENDOR_ALIASES.items():
            if s_no_punct.startswith(alias.upper()):
                return canonical
        return s

    def _vendor_match(input_name: Optional[str], zoho_name: Optional[str]) -> bool:
        if not input_name or not zoho_name:
            return True  # нет данных — не блокируем совпадение
        return _clean_vendor_name(input_name) == _clean_vendor_name(zoho_name)

    def _scan_with_params(base_params: dict) -> Optional[dict]:
        pages_scanned = 0
        params = base_params.copy()
        params.update({
            "organization_id": org_id,
            "per_page": 200,
            "page": 1,
        })

        while True:
            response = requests.get(BILLS_URL, headers=headers, params=params)
            data = response.json()

            if "bills" not in data:
                # Возможно параметр не поддерживается — выходим, дадим шанс другому способу
                return None

            for bill in data["bills"]:
                bn_raw = (bill.get("bill_number") or "").strip()
                bn_norm = _normalize(bn_raw)
                bn_digits = _digits(bn_raw)
                bn_prefix = _lead_letters(bn_raw)

                # Жесткое совпадение
                if bn_norm == norm_target or _normalize_confusables(bn_raw) == _normalize_confusables(bill_number):
                    if vendor_id and bill.get("vendor_id") and bill.get("vendor_id") != vendor_id:
                        continue
                    if not _vendor_match(vendor_name, bill.get("vendor_name")):
                        continue
                    return bill

                # Мягкое совпадение по числовой части + проверка поставщика (если возможно)
                if digits_target and bn_digits and bn_digits == digits_target:
                    # Совпадение по префиксу, если оба присутствуют
                    if prefix_target and bn_prefix and prefix_target != bn_prefix:
                        continue
                    # Совпадение по поставщику, если есть хоть какая-то информация
                    if vendor_id and bill.get("vendor_id") and bill.get("vendor_id") != vendor_id:
                        continue
                    if not _vendor_match(vendor_name, bill.get("vendor_name")):
                        continue
                    return bill

            pages_scanned += 1
            if not data.get("page_context", {}).get("has_more_page"):
                break
            params["page"] += 1

            # Безопасный предел страниц при поиске
            if pages_scanned > 25:
                break

        return None

    # Пытаемся более узкими фильтрами
    log_message(f"🔎 Проверка дубликата Bill: '{bill_number}' (vendor_id={vendor_id}, vendor_name={vendor_name})")
    # Пробуем разные варианты contains: как есть, без пробелов/дефисов
    bn_strip = bill_number.strip()
    bn_compact = re.sub(r"[^A-Za-z0-9]", "", bn_strip)
    found = _scan_with_params({"bill_number_contains": bn_strip}) or _scan_with_params({"bill_number_contains": bn_compact})
    if found:
        log_message(f"✅ Дубликат найден (bill_number_contains): {found.get('bill_number')} / {found.get('bill_id')}")
        return found
    found = _scan_with_params({"search_text": bill_number.strip()})
    if found:
        log_message(f"✅ Дубликат найден (search_text): {found.get('bill_number')} / {found.get('bill_id')}")
        return found

    # Фулл-скан без фильтров (ограничен лимитом страниц)
    found = _scan_with_params({})
    if found:
        log_message(f"✅ Дубликат найден (full scan): {found.get('bill_number')} / {found.get('bill_id')}")
        return found

    log_message("ℹ️ Дубликат не найден")
    return None

def bill_exists_smart(
    org_id: str,
    bill_number: str,
    vendor_id: Optional[str] = None,
    vendor_name: Optional[str] = None,
    document_date: Optional[str] = None,
    month_window: int = 2,
) -> Optional[dict]:
    """
    Расширенная проверка дубликата Bill:
    1) Сначала сканирует месяц документа и соседние месяцы (±month_window) через get_bills
       и сравнивает номера с учетом нормализации и частичного сопоставления.
       При нахождении кандидата подтягивает детали по bill_id и проверяет поставщика.
    2) Если не найдено — fallback на обычный поиск (bill_exists).
    """
    if not bill_number:
        return None

    def _normalize(s: str) -> str:
        return "".join(ch for ch in s.upper() if ch.isalnum())
    def _normalize_confusables(s: str) -> str:
        table = str.maketrans({
            'I': '1', 'L': '1', '|': '1',
            'O': '0', 'Q': '0',
            'B': '8'
        })
        return _normalize(s.translate(table))
    def _digits(s: str) -> str:
        return "".join(ch for ch in s if ch.isdigit())
    def _lead_letters(s: str) -> str:
        m = re.match(r"^[A-Za-z]+", s.strip())
        return (m.group(0) if m else "").upper()

    # Нормализация и алиасы поставщиков для SMART-проверки
    BUSINESS_SUFFIXES = [
        'INC', 'INC.', 'LLC', 'L.L.C.', 'LTD', 'LTD.', 'LIMITED', 'GMBH', 'G.M.B.H.', 'OÜ', 'OU', 'BV', 'B.V.',
        'S.A.', 'SA', 'SP. Z O.O.', 'SP Z O.O.', 'SP Z OO', 'SPÓŁKA Z O.O.'
    ]
    VENDOR_ALIASES = {
        'ANYSphere': 'CURSOR',
        'ANSPHERE': 'CURSOR',
        'ANYSHPERE': 'CURSOR',
        'ANYSPHERE, INC': 'CURSOR',
        'ANYSPHERE INC': 'CURSOR',
        'CURSOR': 'CURSOR',
    }
    def _clean_vendor_name(name: Optional[str]) -> str:
        if not name:
            return ''
        s = re.sub(r"[^A-Z0-9 ]+", " ", str(name).upper()).strip()
        s = re.sub(r"\s+", " ", s)
        for suf in BUSINESS_SUFFIXES:
            if s.endswith(" " + suf.upper()):
                s = s[: -len(suf)-1].strip()
        s_no_punct = s.replace('.', '').replace(',', '')
        for alias, canonical in VENDOR_ALIASES.items():
            if s_no_punct.startswith(alias.upper()):
                return canonical
        return s

    target_norm = _normalize(bill_number)
    target_digits = _digits(bill_number)
    target_prefix = _lead_letters(bill_number)

    def _ym_from_date(raw: str) -> Optional[tuple[int, int]]:
        raw = raw.strip()
        fmts = ["%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d", "%d-%m-%Y"]
        for fmt in fmts:
            try:
                dt = datetime.strptime(raw, fmt)
                return dt.year, dt.month
            except Exception:
                continue
        # Последняя попытка: заменить разделители на '/'
        cleaned = raw.replace(" ", "/").replace(".", "/").replace("-", "/")
        for fmt in ("%d/%m/%Y", "%Y/%m/%d", "%m/%d/%Y"):
            try:
                dt = datetime.strptime(cleaned, fmt)
                return dt.year, dt.month
            except Exception:
                continue
        return None

    def _add_month(year: int, month: int, delta: int) -> tuple[int, int]:
        idx = (year * 12 + (month - 1)) + delta
        y = idx // 12
        m = (idx % 12) + 1
        return y, m

    # 1) Месячное сканирование вокруг даты
    if document_date:
        ym = _ym_from_date(document_date)
        if ym:
            base_year, base_month = ym
            log_message(f"🔎 SMART по месяцам: '{bill_number}' дата={document_date} окно=±{month_window}")
            for d in range(-month_window, month_window + 1):
                year_i, month_i = _add_month(base_year, base_month, d)
                try:
                    bills = get_bills(org_id, year_i, month_i)
                except Exception as e:
                    log_message(f"⚠️ Ошибка get_bills({year_i}-{month_i}): {e}")
                    continue
                for bn, bid, _has_att, _att_id in bills:
                    bn_norm = _normalize(bn)
                    bn_digits = _digits(bn)
                    bn_prefix = _lead_letters(bn)
                    # Жесткое совпадение
                    match = False
                    if bn_norm == target_norm or _normalize_confusables(bn) == _normalize_confusables(bill_number):
                        match = True
                    # Мягкое — по цифрам и префиксу
                    elif target_digits and bn_digits and target_digits == bn_digits:
                        if (not target_prefix or not bn_prefix) or (target_prefix == bn_prefix):
                            match = True
                    if not match:
                        continue
                    # Если нужно — проверим поставщика по деталям
                    bill_details = get_bill_details(org_id, bid) or {}
                    if vendor_id and bill_details.get("vendor_id") and bill_details.get("vendor_id") != vendor_id:
                        continue
                    if _clean_vendor_name(vendor_name) and _clean_vendor_name(bill_details.get("vendor_name")) and _clean_vendor_name(vendor_name) != _clean_vendor_name(bill_details.get("vendor_name")):
                        continue
                    log_message(f"✅ SMART найден дубликат: {bn} / {bid} ({year_i}-{month_i})")
                    return bill_details if bill_details else {"bill_id": bid, "bill_number": bn}

    # 2) Пытаемся через кэш счетов (быстро)
    try:
        # Ленивая загрузка во избежание циклических импортов
        from .bills_cache_manager import ensure_bills_cache, find_bill_candidates_in_cache
        ensure_bills_cache(org_id, document_date)
        candidates = find_bill_candidates_in_cache(org_id, bill_number)
        for entry in candidates:
            bid = entry.get("bill_id")
            details = get_bill_details(org_id, bid) or {}
            if vendor_id and details.get("vendor_id") and details.get("vendor_id") != vendor_id:
                continue
            if _clean_vendor_name(vendor_name) and _clean_vendor_name(details.get("vendor_name")) and _clean_vendor_name(vendor_name) != _clean_vendor_name(details.get("vendor_name")):
                continue
            log_message(f"✅ Кэш найден дубликат: {entry.get('bill_number')} / {bid}")
            return details if details else {"bill_id": bid, "bill_number": entry.get("bill_number")}
    except Exception as e:
        log_message(f"⚠️ Ошибка проверки кэша счетов: {e}")

    # 3) Fallback к обычному поиску
    return bill_exists(org_id, bill_number, vendor_id, vendor_name)

def get_chart_of_accounts(org_id: str) -> list:
    """
    Получает список счетов (Chart of Accounts) из Zoho Books для заданной организации.
    """
    access_token = get_access_token()
    headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}
    url = "https://www.zohoapis.eu/books/v3/chartofaccounts"
    params = {
        "organization_id": org_id,
        "per_page": 200,
        "page": 1,
    }
    accounts = []
    while True:
        response = requests.get(url, headers=headers, params=params)
        data = response.json()
        if "chartofaccounts" not in data:
            log_message(f"❌ Ошибка получения счетов: {data}")
            break
        accounts.extend(data["chartofaccounts"])
        if not data.get("page_context", {}).get("has_more_page"):
            break
        params["page"] += 1
    return accounts

def get_all_suppliers(org_id: str) -> list:
    """
    Получает всех поставщиков (vendors) из Zoho Books для заданной организации.
    """
    access_token = get_access_token()
    headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}
    url = "https://www.zohoapis.eu/books/v3/vendors"
    params = {
        "organization_id": org_id,
        "per_page": 200,
        "page": 1,
    }
    suppliers = []
    while True:
        response = requests.get(url, headers=headers, params=params)
        data = response.json()
        if "vendors" not in data:
            log_message(f"❌ Ошибка получения поставщиков: {data}")
            break
        suppliers.extend(data["vendors"])
        if not data.get("page_context", {}).get("has_more_page"):
            break
        params["page"] += 1
    return suppliers

def get_all_customers(org_id: str) -> list:
    """
    Получает всех покупателей (contacts) из Zoho Books для заданной организации.
    """
    access_token = get_access_token()
    headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}
    url = "https://www.zohoapis.eu/books/v3/contacts"
    params = {
        "organization_id": org_id,
        "per_page": 200,
        "page": 1,
    }
    customers = []
    while True:
        response = requests.get(url, headers=headers, params=params)
        data = response.json()
        if "contacts" not in data:
            log_message(f"❌ Ошибка получения покупателей: {data}")
            break
        customers.extend(data["contacts"])
        if not data.get("page_context", {}).get("has_more_page"):
            break
        params["page"] += 1
    return customers

# ---------- Branches / Taxes helpers ----------
def _cache_path_branches(org_id: str) -> str:
    os.makedirs("data/optimized_cache", exist_ok=True)
    return f"data/optimized_cache/zoho_branches_{org_id}.json"

def _cache_path_taxes(org_id: str) -> str:
    os.makedirs("data/optimized_cache", exist_ok=True)
    return f"data/optimized_cache/zoho_taxes_{org_id}.json"

def get_branches(org_id: str, use_cache: bool = True) -> list:
    """
    Возвращает список филиалов (branches) организации в Zoho Books.
    Кэширует результат в data/optimized_cache/zoho_branches_{org_id}.json
    """
    cache_file = _cache_path_branches(org_id)
    if use_cache and os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("branches", [])
        except Exception:
            pass
    access_token = get_access_token()
    headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}
    params = {"organization_id": org_id, "per_page": 200}
    resp = requests.get(SETTINGS_BRANCHES_URL, headers=headers, params=params)
    data = resp.json()
    branches = data.get("branches", []) if resp.status_code in (200, 201) else []
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump({"branches": branches, "fetched_at": datetime.utcnow().isoformat()}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return branches

def get_warehouses(org_id: str, use_cache: bool = True) -> list:
    """
    Возвращает список складов (warehouses) организации в Zoho Books.
    Кэширует результат в data/optimized_cache/zoho_warehouses_{org_id}.json
    """
    cache_file = f"data/optimized_cache/zoho_warehouses_{org_id}.json"
    if use_cache and os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("warehouses", [])
        except Exception:
            pass
    access_token = get_access_token()
    headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}
    params = {"organization_id": org_id, "per_page": 200}
    resp = requests.get("https://www.zohoapis.eu/books/v3/settings/warehouses", headers=headers, params=params)
    data = resp.json()
    warehouses = data.get("warehouses", []) if resp.status_code in (200, 201) else []
    try:
        os.makedirs(os.path.dirname(cache_file), exist_ok=True)
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump({"warehouses": warehouses, "fetched_at": datetime.utcnow().isoformat()}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return warehouses

def find_branch_id(org_id: str, preferred_names: list[str]) -> Optional[str]:
    """
    Ищет branch_id по списку возможных названий (без учета регистра/диакритики).
    Возвращает первый найденный.
    """
    try:
        import unicodedata
        def norm(s: str) -> str:
            return unicodedata.normalize('NFKD', (s or '')).encode('ascii', 'ignore').decode('ascii').strip().lower()
        targets = [norm(n) for n in preferred_names if n]
        for b in get_branches(org_id):
            name = b.get("name") or b.get("branch_name") or ""
            if norm(name) in targets or any(t in norm(name) for t in targets):
                return b.get("branch_id")
    except Exception:
        return None
    return None

def find_warehouse_id(org_id: str, preferred_names: list[str]) -> Optional[str]:
    """
    Ищет warehouse_id по списку возможных названий (без учета регистра/диакритики).
    Возвращает первый найденный.
    """
    try:
        import unicodedata
        def norm(s: str) -> str:
            return unicodedata.normalize('NFKD', (s or '')).encode('ascii', 'ignore').decode('ascii').strip().lower()
        targets = [norm(n) for n in preferred_names if n]
        for w in get_warehouses(org_id):
            name = w.get("warehouse_name") or ""
            if norm(name) in targets or any(t in norm(name) for t in targets):
                return w.get("warehouse_id")
    except Exception:
        return None
    return None

def get_taxes(org_id: str, use_cache: bool = True) -> list:
    """
    Возвращает список налогов организации; кэширует локально.
    """
    cache_file = _cache_path_taxes(org_id)
    if use_cache and os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("taxes", [])
        except Exception:
            pass
    access_token = get_access_token()
    headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}
    params = {"organization_id": org_id, "per_page": 200}
    resp = requests.get(SETTINGS_TAXES_URL, headers=headers, params=params)
    data = resp.json()
    taxes = data.get("taxes", []) if resp.status_code in (200, 201) else []
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump({"taxes": taxes, "fetched_at": datetime.utcnow().isoformat()}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return taxes

def find_tax_by_percent(org_id: str, percent: float) -> Optional[str]:
    """
    Находит tax_id по процентной ставке (например 23.0). Возвращает tax_id или None.
    """
    try:
        target = round(float(percent or 0), 2)
    except Exception:
        return None
    for t in get_taxes(org_id):
        try:
            rate = round(float(t.get("tax_percentage") or t.get("rate") or 0), 2)
            if rate == target:
                return t.get("tax_id")
        except Exception:
            continue
    return None

def get_contact_details(org_id: str, contact_id: str) -> dict:
    """
    Получает полную информацию о контакте включая адрес, VAT, документы и другие детали.
    """
    access_token = get_access_token()
    headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}
    url = f"https://www.zohoapis.eu/books/v3/contacts/{contact_id}"
    params = {
        "organization_id": org_id,
    }
    
    response = requests.get(url, headers=headers, params=params)
    data = response.json()
    
    if "contact" not in data:
        log_message(f"❌ Ошибка получения деталей контакта {contact_id}: {data}")
        return {}
    
    return data["contact"]

def get_all_contacts_with_details(org_id: str, limit: int = 5) -> list:
    """
    Получает детальную информацию о контактах (для тестирования - ограничено количество).
    """
    # Сначала получаем список контактов
    contacts = get_all_customers(org_id)
    detailed_contacts = []
    
    log_message(f"📋 Получение детальной информации о {min(limit, len(contacts))} контактах...")
    
    for i, contact in enumerate(contacts[:limit]):
        contact_id = contact["contact_id"]
        contact_name = contact["contact_name"]
        
        log_message(f"📞 Получение деталей для {contact_name} ({contact_id})")
        details = get_contact_details(org_id, contact_id)
        
        if details:
            detailed_contacts.append(details)
        
        # Небольшая пауза чтобы не перегружать API
        import time
        time.sleep(0.5)
    
    return detailed_contacts

def extract_vat_from_contact(contact_details: dict) -> str:
    """
    Извлекает VAT номер из полной информации о контакте.
    """
    # Проверяем custom_fields - ищем cf_tax_id (правильное поле!) и cf_vat_id
    if 'custom_fields' in contact_details and contact_details['custom_fields']:
        for cf in contact_details['custom_fields']:
            field_name = cf.get('api_name', '')
            if field_name in ['cf_tax_id', 'cf_vat_id']:
                vat_value = cf.get('value', '').strip()
                if vat_value:
                    return vat_value
    
    # Проверяем custom_field_hash - ищем cf_tax_id и cf_vat_id
    if 'custom_field_hash' in contact_details:
        for field_name in ['cf_tax_id', 'cf_vat_id']:
            vat_value = contact_details['custom_field_hash'].get(field_name, '').strip()
            if vat_value:
                return vat_value
    
    # Проверяем прямые поля
    for field_name in ['cf_tax_id', 'cf_vat_id', 'tax_id', 'vat_id']:
        if field_name in contact_details:
            vat_value = contact_details[field_name]
            if vat_value and str(vat_value).strip():
                return str(vat_value).strip()
    
    return ''

def get_contact_by_name(contact_name: str, org_id: str) -> dict:
    """
    Ищет контакт по названию в Zoho Books API.
    Возвращает полную информацию о контакте или None если не найден.
    """
    access_token = get_access_token()
    headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}
    url = "https://www.zohoapis.eu/books/v3/contacts"

    def _normalize_company_name(name: str) -> str:
        s = re.sub(r"[^A-Z0-9 ]+", " ", (name or '').upper()).strip()
        s = re.sub(r"\s+", " ", s)
        s = re.sub(r"\bSP\s*Z\s*O\s*O\b", "", s)
        s = re.sub(r"\bSPOLKA\s+Z\s+OO\b", "", s)
        s = re.sub(r"\bSPOLKA\s+Z\s+O\s*O\b", "", s)
        s = re.sub(r"\bSPOLKA\b", "", s)
        s = re.sub(r"\bSPOLKA Z OGRANICZONA ODPOWIEDZIALNOSCIA\b", "", s)
        s = re.sub(r"\s+", " ", s)
        return s.strip()

    base_name = _normalize_company_name(contact_name)
    first_token = base_name.split(" ")[0] if base_name else contact_name.strip()

    def _search(query: str) -> list:
        p = {
            "organization_id": org_id,
            "contact_name_contains": query.strip(),
            "per_page": 200,
        }
        resp = requests.get(url, headers=headers, params=p)
        return resp.json().get("contacts", []) if resp.status_code in (200, 201) else []
    
    log_message(f"🔍 Поиск контакта по названию: '{contact_name}' в org_id={org_id}")
    
    # последовательные расширяющиеся запросы: исходная строка → нормализованная база → первый токен
    contacts = _search(contact_name) or _search(base_name) or _search(first_token)
    
    # Ищем точное совпадение по названию (case-insensitive)
    for contact in contacts:
        if contact.get("contact_name", "").lower().strip() == contact_name.lower().strip():
            contact_id = contact["contact_id"]
            log_message(f"✅ Найден точный контакт: {contact['contact_name']} (ID: {contact_id})")
            
            # Получаем полную информацию включая VAT
            full_contact = get_contact_details(org_id, contact_id)
            if full_contact:
                # Добавляем VAT номер
                full_contact['vat_number'] = extract_vat_from_contact(full_contact)
                return full_contact
    
    target_norm = base_name
    best = None
    for c in contacts:
        c_norm = _normalize_company_name(c.get('contact_name', ''))
        if c_norm == target_norm:
            best = c
            break
    if not best and contacts:
        best = contacts[0]
    if best:
        contact_id = best["contact_id"]
        log_message(f"⚠️ Найдено частичное совпадение: {best['contact_name']} (ID: {contact_id})")
        full_contact = get_contact_details(org_id, contact_id)
        if full_contact:
            full_contact['vat_number'] = extract_vat_from_contact(full_contact)
            return full_contact
    
    log_message(f"❌ Контакт '{contact_name}' не найден")
    return None

def get_contact_by_vat(vat_number: str, org_id: str) -> dict:
    """
    Ищет контакт по VAT номеру в Zoho Books API.
    Поскольку VAT хранится в custom_fields, получаем все контакты и ищем по VAT.
    """
    access_token = get_access_token()
    headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}
    url = "https://www.zohoapis.eu/books/v3/contacts"
    
    params = {
        "organization_id": org_id,
        "per_page": 200,
        "page": 1,
    }
    
    def _clean(s: str) -> str:
        return re.sub(r"[^A-Z0-9]", "", (s or '').upper())
    vat_clean = _clean(vat_number)
    log_message(f"🔍 Поиск контакта по VAT: '{vat_clean}' в org_id={org_id}")
    
    # Поиск по страницам (пока не найдем или не закончатся страницы)
    while True:
        response = requests.get(url, headers=headers, params=params)
        data = response.json()
        
        if "contacts" not in data:
            log_message(f"❌ Ошибка поиска по VAT: {data}")
            break
            
        contacts = data["contacts"]
        
        # Проверяем каждый контакт на странице
        for contact in contacts:
            contact_id = contact["contact_id"]
            contact_name = contact.get("contact_name", "Unknown")
            
            # Получаем полную информацию о контакте
            full_contact = get_contact_details(org_id, contact_id)
            if not full_contact:
                continue
                
            # Извлекаем VAT номер
            contact_vat = extract_vat_from_contact(full_contact)
            contact_vat_clean = _clean(contact_vat)
            # Совпадение строгое или с префиксом страны (напр. PL + 10 цифр)
            equal = contact_vat_clean == vat_clean
            if not equal and len(contact_vat_clean) > 2 and contact_vat_clean[:2].isalpha():
                equal = contact_vat_clean[2:] == vat_clean
            if not equal and len(vat_clean) > 2 and vat_clean[:2].isalpha():
                equal = vat_clean[2:] == contact_vat_clean
            if contact_vat and equal:
                log_message(f"✅ Найден контакт по VAT: {contact_name} (VAT: {contact_vat})")
                full_contact['vat_number'] = contact_vat
                return full_contact
        
        # Переходим к следующей странице
        if not data.get("page_context", {}).get("has_more_page"):
            break
        params["page"] += 1
        
        # Защита от бесконечного цикла
        if params["page"] > 10:  # Максимум 10 страниц = 2000 контактов
            log_message("⚠️ Достигнут лимит страниц при поиске по VAT")
            break
    
    log_message(f"❌ Контакт с VAT '{vat_clean}' не найден")
    return None

def find_supplier_in_zoho(org_id: str, supplier_name: Optional[str], supplier_vat: Optional[str]) -> Optional[dict]:
    """
    Комбинированный поиск поставщика: VAT (с разными вариантами) → имя (с нормализацией).
    Возвращает контакт (полные детали) или None.
    """
    try:
        # 1) По VAT (если есть)
        if supplier_vat:
            c = get_contact_by_vat(supplier_vat, org_id)
            if c:
                return c
        # 2) По имени (если есть)
        if supplier_name:
            c = get_contact_by_name(supplier_name, org_id)
            if c:
                return c
    except Exception as e:
        log_message(f"⚠️ find_supplier_in_zoho error: {e}")
    return None

def search_contacts_smart(search_term: str, org_id: str, search_type: str = "auto") -> list:
    """
    Умный поиск контактов с возможностью поиска по названию или VAT.
    
    Args:
        search_term: термин для поиска
        org_id: ID организации
        search_type: "name", "vat" или "auto" (автоопределение)
    
    Returns:
        list: список найденных контактов
    """
    results = []
    
    if search_type in ["auto", "name"]:
        # Поиск по названию
        contact = get_contact_by_name(search_term, org_id)
        if contact:
            results.append(contact)
    
    if search_type in ["auto", "vat"] and not results:
        # Поиск по VAT (если не нашли по названию или явно указан VAT поиск)
        contact = get_contact_by_vat(search_term, org_id)
        if contact:
            results.append(contact)
    
    return results

def get_full_contacts_database(org_id: str, org_name: str) -> list:
    """
    Получает полную базу контактов с VAT номерами и всеми полями.
    """
    log_message(f"🔄 Получение полной базы контактов для {org_name} (ID: {org_id})")
    
    # Сначала получаем список всех контактов
    contacts = get_all_customers(org_id)
    log_message(f"📋 Найдено {len(contacts)} контактов")
    
    full_contacts = []
    
    for i, contact in enumerate(contacts):
        contact_id = contact["contact_id"]
        contact_name = contact["contact_name"]
        contact_type = contact.get("contact_type", "unknown")
        
        log_message(f"📞 [{i+1}/{len(contacts)}] Получение деталей: {contact_name} ({contact_type})")
        
        # Получаем полную информацию
        details = get_contact_details(org_id, contact_id)
        
        if details:
            # Извлекаем VAT номер
            vat_number = extract_vat_from_contact(details)
            
            # Добавляем извлеченный VAT номер в основную структуру
            details['extracted_vat_number'] = vat_number
            
            full_contacts.append(details)
            
            # Показываем прогресс для контактов с VAT
            if vat_number:
                log_message(f"✅ VAT найден: {vat_number}")
        else:
            log_message(f"❌ Ошибка получения деталей для {contact_name}")
        
        # Небольшая пауза чтобы не перегружать API
        import time
        time.sleep(0.3)
        
        # Показываем прогресс каждые 10 контактов
        if (i + 1) % 10 == 0:
            log_message(f"📊 Обработано {i+1}/{len(contacts)} контактов")
    
    log_message(f"✅ Получена полная информация о {len(full_contacts)} контактах")
    return full_contacts

def export_full_contacts_database(org_id: str, org_name: str):
    """
    Экспортирует полную базу контактов в JSON файл.
    """
    log_message(f"🚀 Начало экспорта полной базы контактов для {org_name}")
    
    # Получаем полную базу
    full_contacts = get_full_contacts_database(org_id, org_name)
    
    # Сохраняем в файл
    filename = f"data/zoho_full_contacts_{org_id}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(full_contacts, f, ensure_ascii=False, indent=2)
    
    # Статистика
    customers = [c for c in full_contacts if c.get('contact_type') == 'customer']
    vendors = [c for c in full_contacts if c.get('contact_type') == 'vendor']
    contacts_with_vat = [c for c in full_contacts if c.get('extracted_vat_number')]
    
    log_message(f"📊 СТАТИСТИКА для {org_name}:")
    log_message(f"   Всего контактов: {len(full_contacts)}")
    log_message(f"   Customers: {len(customers)}")
    log_message(f"   Vendors: {len(vendors)}")
    log_message(f"   С VAT номерами: {len(contacts_with_vat)}")
    log_message(f"   Размер файла: {os.path.getsize(filename)} байт")
    log_message(f"✅ Сохранено в {filename}")
