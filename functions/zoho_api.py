import os
import requests
import time
import calendar
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv("/Users/macos/my_project/.env")

# API-константы
ZOHO_CLIENT_ID = os.getenv("ZOHO_CLIENT_ID")
ZOHO_CLIENT_SECRET = os.getenv("ZOHO_CLIENT_SECRET")
ZOHO_REFRESH_TOKEN = os.getenv("ZOHO_REFRESH_TOKEN")
TOKEN_URL = "https://accounts.zoho.eu/oauth/v2/token"
BILLS_URL = "https://www.zohoapis.eu/books/v3/bills"

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
