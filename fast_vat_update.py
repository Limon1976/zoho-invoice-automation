#!/usr/bin/env python3
"""БЫСТРОЕ МАССОВОЕ ОБНОВЛЕНИЕ VAT ПРЕФИКСОВ"""

import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.append(str(Path('.').parent))
from src.infrastructure.zoho_api import ZohoAPIClient
from src.infrastructure.config import get_config

async def main():
    print("🚀 БЫСТРОЕ ОБНОВЛЕНИЕ VAT ПРЕФИКСОВ")
    print("="*50)
    print("⚡ Без пауз - максимальная скорость!")
    print()
    
    confirm = input("🚀 Запустить? (y/N): ").lower()
    if confirm != 'y':
        print("❌ Отменено")
        return
    
    # API
    config = get_config()
    api = ZohoAPIClient(
        client_id=config.zoho.client_id,
        client_secret=config.zoho.client_secret,
        refresh_token=config.zoho.refresh_token or ''
    )
    
    org_id = "20082562863"
    
    # Контакты
    with open('data/full_contacts/PARKENTERTAINMENT_20082562863_full.json', 'r') as f:
        all_contacts = json.load(f)
    
    target_ids = [
        '281497000005903525', '281497000006344068', '281497000006068005',
        '281497000005903457', '281497000005903389', '281497000005007050',
        '281497000005007187', '281497000004571563', '281497000001825719',
        '281497000005395276', '281497000004567718', '281497000005999849',
        '281497000005940057', '281497000006365071', '281497000006113586',
        '281497000005126385', '281497000005237353', '281497000005962003',
        '281497000005446183', '281497000006113397'
    ]
    
    contacts = [c for c in all_contacts if c.get('contact_id') in target_ids]
    
    print(f"📊 Контактов: {len(contacts)}")
    print()
    
    # Статистика
    updated = 0
    already_ok = 0
    errors = 0
    
    # Обработка
    for i, contact in enumerate(contacts, 1):
        name = contact.get('company_name', 'Unknown')[:35]
        contact_id = contact.get('contact_id')
        
        print(f"{i:2d}/{len(contacts)} {name}...", end=" ")
        
        try:
            # Текущие данные
            current = await api.get_contact_details(org_id, contact_id)
            if not current:
                print("❌ Нет данных")
                errors += 1
                continue
            
            vat = current.get('cf_tax_id', '')
            
            # Проверка
            if vat.startswith('PL'):
                print(f"✅ OK ({vat})")
                already_ok += 1
                continue
            
            if not vat:
                print("⏭️ Нет VAT")
                continue
            
            # Обновление
            new_vat = f"PL{vat}"
            data = {'custom_fields': [{'api_name': 'cf_tax_id', 'value': new_vat}]}
            
            resp = await api.update_contact(org_id, data, contact_id)
            
            if resp:
                await asyncio.sleep(0.1)
                check = await api.get_contact_details(org_id, contact_id)
                
                if check and check.get('cf_tax_id') == new_vat:
                    print(f"🎉 {vat} → {new_vat}")
                    updated += 1
                else:
                    print("❌ Не изменился")
                    errors += 1
            else:
                print("❌ API ошибка")
                errors += 1
                
        except Exception as e:
            print(f"❌ {str(e)[:20]}...")
            errors += 1
    
    # Итоги
    print()
    print("📊 ИТОГИ:")
    print(f"   🎉 Обновлено: {updated}")
    print(f"   ✅ Уже готово: {already_ok}")
    print(f"   ❌ Ошибок: {errors}")
    print(f"   📈 Успех: {((updated + already_ok) / len(contacts) * 100):.1f}%")
    
    await api.client.aclose()

if __name__ == "__main__":
    asyncio.run(main())
