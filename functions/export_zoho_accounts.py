import os
import json
from functions.zoho_api import get_chart_of_accounts, get_all_customers
from typing import List, Dict

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

# Получаем organization_id из env
ORG_IDS = [
    os.environ.get("ZOHO_ORGANIZATION_ID_1"),
    os.environ.get("ZOHO_ORGANIZATION_ID_2")
]

def export_accounts_for_org(org_id, org_name):
    """Экспортирует Chart of Accounts для организации"""
    print(f"\n📊 Экспорт Chart of Accounts для {org_name} (ID: {org_id})")
    accounts = get_chart_of_accounts(org_id)
    
    filename = f"data/zoho_accounts_{org_id}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(accounts, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Сохранено {len(accounts)} счетов в {filename}")

def load_accounts_from_cache(org_id: str) -> List[Dict]:
    """
    Загружает Chart of Accounts из локального кэша data/zoho_accounts_{org_id}.json,
    если файл существует. Иначе возвращает пустой список.
    """
    filename = f"data/zoho_accounts_{org_id}.json"
    if not os.path.exists(filename):
        return []
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def get_accounts_cached_or_fetch(org_id: str, org_name: str) -> List[Dict]:
    """
    Возвращает список счетов из локального кэша или выгружает из Zoho и кэширует,
    если кэша нет. Удобная обертка для хэндлеров.
    """
    accounts = load_accounts_from_cache(org_id)
    if accounts:
        return accounts
    # Кэша нет — выгружаем и возвращаем
    export_accounts_for_org(org_id, org_name)
    return load_accounts_from_cache(org_id)

def export_suppliers_for_org(org_id, org_name):
    """Экспортирует поставщиков (vendors) для организации из уже выгруженных contacts"""
    print(f"\n📦 Экспорт поставщиков для {org_name} (ID: {org_id})")
    
    # Читаем уже выгруженные контакты
    contacts_filename = f"data/zoho_customers_{org_id}.json"
    
    if not os.path.exists(contacts_filename):
        print(f"❌ Файл {contacts_filename} не найден. Сначала выгрузите контакты.")
        return
    
    with open(contacts_filename, "r", encoding="utf-8") as f:
        all_contacts = json.load(f)
    
    # Фильтруем только vendors
    vendors = [contact for contact in all_contacts if contact.get('contact_type') == 'vendor']
    
    filename = f"data/zoho_vendors_{org_id}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(vendors, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Сохранено {len(vendors)} поставщиков в {filename}")

def export_customers_for_org(org_id, org_name):
    """Экспортирует покупателей (customers) для организации"""
    print(f"\n👥 Экспорт покупателей для {org_name} (ID: {org_id})")
    
    # Читаем уже выгруженные контакты
    contacts_filename = f"data/zoho_customers_{org_id}.json"
    
    if not os.path.exists(contacts_filename):
        print(f"📞 Выгружаем контакты для {org_name}...")
        all_contacts = get_all_customers(org_id)
        
        # Сохраняем все контакты
        with open(contacts_filename, "w", encoding="utf-8") as f:
            json.dump(all_contacts, f, ensure_ascii=False, indent=2)
        print(f"✅ Сохранено {len(all_contacts)} контактов в {contacts_filename}")
    else:
        with open(contacts_filename, "r", encoding="utf-8") as f:
            all_contacts = json.load(f)
        print(f"📁 Загружено {len(all_contacts)} контактов из {contacts_filename}")
    
    # Фильтруем только customers
    customers = [contact for contact in all_contacts if contact.get('contact_type') == 'customer']
    
    customers_filename = f"data/zoho_customers_only_{org_id}.json"
    with open(customers_filename, "w", encoding="utf-8") as f:
        json.dump(customers, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Сохранено {len(customers)} покупателей в {customers_filename}")

if __name__ == "__main__":
    # Mapping организаций
    org_mapping = {
        "20092948714": "TaVie Europe OÜ",
        "20082562863": "PARKENTERTAINMENT Sp. z o. o."
    }
    
    for org_id in ORG_IDS:
        if org_id:
            org_name = org_mapping.get(org_id, f"Organization {org_id}")
            print(f"\n🏢 Обработка организации: {org_name} (ID: {org_id})")
            
            export_accounts_for_org(org_id, org_name)
            export_suppliers_for_org(org_id, org_name)
            export_customers_for_org(org_id, org_name)
        else:
            print("Organization ID not set in environment.") 