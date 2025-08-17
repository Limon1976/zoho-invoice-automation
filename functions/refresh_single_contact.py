#!/usr/bin/env python3
"""
Refresh Single Contact from Zoho
=================================

Функция для загрузки одного конкретного контакта из Zoho API
"""

import os
import sys
import json
import asyncio
from pathlib import Path

# Добавляем корневую папку в path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from functions.zoho_api import ZohoAPI


async def get_single_contact_from_zoho(contact_name: str, organization_id: str = None):
    """
    Загружает один контакт из Zoho по названию
    
    Args:
        contact_name: Название контакта для поиска
        organization_id: ID организации (если не указан - ищем во всех)
    """
    
    print(f"🔍 Ищем контакт: {contact_name}")
    
    zoho_api = ZohoAPI()
    
    # Организации для поиска
    organizations = {
        "20092948714": "TaVie Europe OÜ",
        "20082562863": "PARKENTERTAINMENT Sp. z o. o."
    }
    
    if organization_id:
        # Ищем только в указанной организации
        organizations = {organization_id: organizations.get(organization_id, "Unknown")}
    
    found_contacts = []
    
    for org_id, org_name in organizations.items():
        print(f"📊 Поиск в {org_name} ({org_id})...")
        
        try:
            # Получаем список контактов с поиском по имени
            response = await zoho_api.get_contacts(
                organization_id=org_id,
                search_text=contact_name
            )
            
            if response and "contacts" in response:
                contacts = response["contacts"]
                print(f"   Найдено {len(contacts)} контактов")
                
                for contact in contacts:
                    contact_id = contact.get("contact_id")
                    contact_name_found = contact.get("contact_name", "")
                    
                    # Проверяем точное совпадение или частичное
                    if contact_name.lower() in contact_name_found.lower():
                        print(f"   ✅ Найден: {contact_name_found} (ID: {contact_id})")
                        
                        # Получаем полную информацию о контакте
                        full_contact = await zoho_api.get_contact_details(org_id, contact_id)
                        if full_contact:
                            full_contact['organization_id'] = org_id
                            full_contact['organization_name'] = org_name
                            found_contacts.append(full_contact)
            else:
                print(f"   ❌ Контакты не найдены в {org_name}")
                
        except Exception as e:
            print(f"   ❌ Ошибка поиска в {org_name}: {e}")
    
    return found_contacts


async def update_contact_in_files(contact_data: dict):
    """
    Обновляет контакт в соответствующем файле организации
    """
    org_id = contact_data.get('organization_id')
    contact_id = contact_data.get('contact_id')
    contact_name = contact_data.get('contact_name')
    
    # Определяем файл для организации
    if org_id == "20092948714":
        file_path = "data/full_contacts/TaVie_Europe_20092948714_full.json"
    elif org_id == "20082562863":
        file_path = "data/full_contacts/PARKENTERTAINMENT_20082562863_full.json"
    else:
        print(f"❌ Неизвестная организация: {org_id}")
        return False
    
    file_path = Path(file_path)
    
    if not file_path.exists():
        print(f"❌ Файл не существует: {file_path}")
        return False
    
    print(f"📄 Обновляем файл: {file_path}")
    
    # Загружаем существующие контакты
    with open(file_path, 'r', encoding='utf-8') as f:
        contacts = json.load(f)
    
    # Ищем существующий контакт
    contact_updated = False
    for i, existing_contact in enumerate(contacts):
        if existing_contact.get('contact_id') == contact_id:
            contacts[i] = contact_data
            contact_updated = True
            print(f"   ✅ Контакт обновлен: {contact_name}")
            break
    
    # Если контакт не найден, добавляем новый
    if not contact_updated:
        contacts.append(contact_data)
        print(f"   ➕ Контакт добавлен: {contact_name}")
    
    # Сохраняем обновленный файл
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(contacts, f, ensure_ascii=False, indent=2)
    
    print(f"   💾 Файл сохранен с {len(contacts)} контактами")
    return True


async def main():
    """Основная функция"""
    
    print("🔄 ОБНОВЛЕНИЕ ОДНОГО КОНТАКТА ИЗ ZOHO")
    print("=" * 50)
    
    # Можно указать конкретный контакт
    contact_name = input("Введите название контакта для поиска: ").strip()
    
    if not contact_name:
        contact_name = "Horrer Automobile"  # По умолчанию
        print(f"Используем по умолчанию: {contact_name}")
    
    # Ищем контакт в Zoho
    found_contacts = await get_single_contact_from_zoho(contact_name)
    
    if not found_contacts:
        print("❌ Контакт не найден в Zoho")
        return
    
    print(f"\n✅ Найдено {len(found_contacts)} контактов:")
    
    # Обновляем каждый найденный контакт в соответствующем файле
    for contact in found_contacts:
        org_name = contact.get('organization_name')
        contact_name_found = contact.get('contact_name')
        
        print(f"\n📋 Обрабатываем: {contact_name_found} ({org_name})")
        
        success = await update_contact_in_files(contact)
        if success:
            print(f"   ✅ Контакт успешно обновлен в файле")
        else:
            print(f"   ❌ Ошибка обновления контакта")
    
    print(f"\n🎉 Обновление завершено!")


if __name__ == "__main__":
    asyncio.run(main()) 