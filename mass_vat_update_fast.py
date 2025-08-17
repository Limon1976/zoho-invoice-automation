#!/usr/bin/env python3
"""
БЫСТРОЕ МАССОВОЕ ОБНОВЛЕНИЕ VAT ПРЕФИКСОВ
Ускоренная версия без длинных пауз
"""

import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.append(str(Path('.').parent))
from src.infrastructure.zoho_api import ZohoAPIClient
from src.infrastructure.config import get_config

async def fast_mass_update_vat():
    print("🚀 БЫСТРОЕ МАССОВОЕ ОБНОВЛЕНИЕ VAT ПРЕФИКСОВ")
    print("="*60)
    print(f"⏰ Начало: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("⚡ Режим: БЫСТРЫЙ (без пауз)")
    print()
    
    confirm = input("🚀 Запустить быстрое обновление? (y/N): ").lower()
    if confirm != 'y':
        print("❌ Обновление отменено")
        return
    
    print("\n🎬 ЗАПУСК...")
    print("="*60)
    
    # API клиент
    config = get_config()
    api_client = ZohoAPIClient(
        client_id=config.zoho.client_id,
        client_secret=config.zoho.client_secret,
        refresh_token=config.zoho.refresh_token or ''
    )
    
    org_id = "20082562863"
    
    # Загружаем контакты
    with open('data/full_contacts/PARKENTERTAINMENT_20082562863_full.json', 'r', encoding='utf-8') as f:
        all_contacts = json.load(f)
    
    # Целевые ID
    target_ids = [
        '281497000005903525',  # AEvent
        '281497000006344068',  # AFanna fleur
        '281497000006068005',  # Awokado Project
        '281497000005903457',  # Be Unique
        '281497000005903389',  # Bimboo
        '281497000005007050',  # Carrefour Polska
        '281497000005007187',  # CCM Construction
        '281497000004571563',  # CHRONOS APARTAMENTY
        '281497000001825719',  # ETERIA CONSULTING
        '281497000005395276',  # EUROSTAR-TRANSPORT.EU
        '281497000004567718',  # F.P.H.U. PROBOX
        '281497000005999849',  # Faf Global
        '281497000005940057',  # Flower Island
        '281497000006365071',  # FN EUROPE
        '281497000006113586',  # Globe Trade Centre
        '281497000005126385',  # Google ADS
        '281497000005237353',  # Grid Dynamics Poland
        '281497000005962003',  # HOLO SP.
        '281497000005446183',  # Indigo Mental Club
        '281497000006113397'   # ISKRY
    ]
    
    # Фильтрация контактов
    contacts = []
    for contact in all_contacts:
        if contact.get('contact_id') in target_ids:
            contacts.append({
                'id': contact.get('contact_id'),
                'name': contact.get('company_name', 'Unknown'),
                'type': contact.get('customer_sub_type', 'unknown'),
                'vat': contact.get('cf_tax_id', '')
            })
    
    print(f"📊 Контактов к обработке: {len(contacts)}")
    print()
    
    # Статистика
    stats = {'total': len(contacts), 'updated': 0, 'already_ok': 0, 'errors': 0}
    
    # Обработка
    for i, contact in enumerate(contacts, 1):
        print(f"{i:2d}/{len(contacts)} {contact['name'][:40]}...", end=" ")
        
        try:
            # Получаем актуальные данные
            current = await api_client.get_contact_details(org_id, contact['id'])
            
            if not current:
                print("❌ Нет данных")
                stats['errors'] += 1
                continue
            
            current_vat = current.get('cf_tax_id', '')
            
            # Проверяем префикс
            if current_vat.startswith('PL'):
                print(f"✅ Уже OK ({current_vat})")
                stats['already_ok'] += 1
                continue
            
            if not current_vat:
                print("⏭️ Нет VAT")
                continue
            
            # Обновляем
            new_vat = f"PL{current_vat}"
            update_data = {
                'custom_fields': [{'api_name': 'cf_tax_id', 'value': new_vat}]
            }
            
                         response = await api_client.update_contact(org_id, update_data, contact['id'])
            
            if response:
                # Быстрая проверка
                await asyncio.sleep(0.2)
                updated = await api_client.get_contact_details(org_id, contact['id'])
                
                if updated and updated.get('cf_tax_id', '') == new_vat:
                    print(f"🎉 {current_vat} → {new_vat}")
                    stats['updated'] += 1
                else:
                    print("❌ Не обновился")
                    stats['errors'] += 1
            else:
                print("❌ API ошибка")
                stats['errors'] += 1
                
        except Exception as e:
            print(f"❌ {str(e)[:30]}...")
            stats['errors'] += 1
    
    # Итоги
    print()
    print("📊 ИТОГИ:")
    print(f"   🎯 Всего: {stats['total']}")
    print(f"   🎉 Обновлено: {stats['updated']}")
    print(f"   ✅ Уже готово: {stats['already_ok']}")
    print(f"   ❌ Ошибок: {stats['errors']}")
    
    success_rate = ((stats['updated'] + stats['already_ok']) / stats['total']) * 100
    print(f"   📈 Успех: {success_rate:.1f}%")
    
    if success_rate >= 90:
        print("🏆 ОТЛИЧНО!")
    elif success_rate >= 70:
        print("👍 ХОРОШО!")
    else:
        print("⚠️ ЕСТЬ ПРОБЛЕМЫ!")
    
    print(f"⏰ Завершено: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    await api_client.client.aclose()
    return stats

if __name__ == "__main__":
    results = asyncio.run(fast_mass_update_vat())
    if results:
        print("\n🎉 МАССОВОЕ ОБНОВЛЕНИЕ ЗАВЕРШЕНО!")
    else:
        print("\n❌ ОБНОВЛЕНИЕ ПРЕРВАНО!") 