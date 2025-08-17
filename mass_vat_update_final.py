#!/usr/bin/env python3
"""
МАССОВОЕ ОБНОВЛЕНИЕ VAT ПРЕФИКСОВ
Финальный скрипт для обновления всех контактов PARKENTERTAINMENT
Использует проверенный рабочий метод: custom_fields API
"""

import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.append(str(Path('.').parent))
from src.infrastructure.zoho_api import ZohoAPIClient
from src.infrastructure.config import get_config

async def mass_update_vat_prefixes():
    print("🚀 МАССОВОЕ ОБНОВЛЕНИЕ VAT ПРЕФИКСОВ")
    print("="*70)
    print(f"⏰ Начало: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("🔧 Метод: custom_fields API (проверенный)")
    print("🎯 Цель: Добавить польские префиксы PL ко всем VAT номерам")
    print()
    
    # Подтверждение запуска
    print("⚠️ ВНИМАНИЕ: Этот скрипт обновит VAT номера в Zoho Books!")
    print("📋 Список контактов будет обработан автоматически")
    print()
    
    confirm = input("🤔 Продолжить массовое обновление? (y/N): ").lower()
    if confirm != 'y':
        print("❌ Массовое обновление отменено")
        return
    
    print("\n🎬 НАЧИНАЕМ МАССОВОЕ ОБНОВЛЕНИЕ...")
    print("="*70)
    
    # Настройка API клиента
    config = get_config()
    api_client = ZohoAPIClient(
        client_id=config.zoho.client_id,
        client_secret=config.zoho.client_secret,
        refresh_token=config.zoho.refresh_token or ''
    )
    
    org_id = "20082562863"
    
    # Загружаем данные контактов
    print("📁 Загрузка списка контактов...")
    with open('data/full_contacts/PARKENTERTAINMENT_20082562863_full.json', 'r', encoding='utf-8') as f:
        all_contacts = json.load(f)
    
    # Целевые контакты (исходный список)
    target_contact_ids = [
        '281497000005903525',  # AEvent (уже обновлен)
        '281497000006344068',  # AFanna fleur (уже обновлен)
        '281497000006068005',  # Awokado Project (уже обновлен)
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
    
    # Фильтруем контакты
    contacts_to_process = []
    
    for contact in all_contacts:
        if contact.get('contact_id') in target_contact_ids:
            company_name = contact.get('company_name', 'Unknown')
            contact_id = contact.get('contact_id')
            customer_sub_type = contact.get('customer_sub_type', 'Unknown')
            vat = contact.get('cf_tax_id', '')
            country = contact.get('billing_address', {}).get('country', '')
            
            contacts_to_process.append({
                'contact_id': contact_id,
                'company_name': company_name,
                'customer_sub_type': customer_sub_type,
                'current_vat': vat,
                'country': country
            })
    
    print(f"📊 Найдено контактов для обработки: {len(contacts_to_process)}")
    print()
    
    # Обрабатываем контакты
    results = {
        'total': len(contacts_to_process),
        'updated': 0,
        'already_updated': 0,
        'skipped': 0,
        'errors': 0,
        'details': []
    }
    
    for i, contact_info in enumerate(contacts_to_process, 1):
        contact_id = contact_info['contact_id']
        company_name = contact_info['company_name']
        
        print(f"🔄 КОНТАКТ {i}/{len(contacts_to_process)}: {company_name[:50]}...")
        
        try:
            # Получаем актуальные данные из Zoho
            current_data = await api_client.get_contact_details(org_id, contact_id)
            
            if not current_data:
                print(f"   ❌ Не удалось получить данные")
                results['errors'] += 1
                results['details'].append({
                    'contact': contact_info,
                    'status': 'ERROR',
                    'message': 'Не удалось получить данные из Zoho'
                })
                continue
            
            current_vat = current_data.get('cf_tax_id', '')
            customer_type = current_data.get('customer_sub_type', '')
            
            print(f"   📊 VAT: '{current_vat}' | Тип: {customer_type}")
            
            # Проверяем нужно ли обновление
            if current_vat.startswith('PL'):
                print(f"   ✅ Уже имеет префикс - пропускаем")
                results['already_updated'] += 1
                results['details'].append({
                    'contact': contact_info,
                    'status': 'ALREADY_UPDATED',
                    'vat': current_vat
                })
                continue
            
            # Пропускаем контакты без VAT
            if not current_vat or current_vat.strip() == '':
                print(f"   ⏭️ Нет VAT номера - пропускаем")
                results['skipped'] += 1
                results['details'].append({
                    'contact': contact_info,
                    'status': 'SKIPPED',
                    'message': 'Нет VAT номера'
                })
                continue
            
            # Обновляем VAT
            new_vat = f"PL{current_vat}"
            print(f"   🔧 Обновляем: '{current_vat}' → '{new_vat}'")
            
            # РАБОЧИЙ МЕТОД: custom_fields
            update_data = {
                'custom_fields': [
                    {
                        'api_name': 'cf_tax_id',
                        'value': new_vat
                    }
                ]
            }
            
            response = await api_client.update_contact(
                organization_id=org_id,
                contact_id=contact_id,
                contact_data=update_data
            )
            
            if not response:
                print(f"   ❌ API отклонил запрос")
                results['errors'] += 1
                results['details'].append({
                    'contact': contact_info,
                    'status': 'ERROR',
                    'message': 'API отклонил запрос'
                })
                continue
            
                                      # Проверяем результат
             await asyncio.sleep(0.3)  # Минимальная пауза для применения изменений
            
            updated_data = await api_client.get_contact_details(org_id, contact_id)
            
            if updated_data:
                final_vat = updated_data.get('cf_tax_id', '')
                
                if final_vat == new_vat:
                    print(f"   🎉 УСПЕХ! VAT обновлен")
                    results['updated'] += 1
                    results['details'].append({
                        'contact': contact_info,
                        'status': 'UPDATED',
                        'old_vat': current_vat,
                        'new_vat': final_vat
                    })
                else:
                    print(f"   ❌ VAT не изменился: '{final_vat}'")
                    results['errors'] += 1
                    results['details'].append({
                        'contact': contact_info,
                        'status': 'ERROR',
                        'message': f'VAT не обновился: {final_vat}'
                    })
            else:
                print(f"   ❌ Не удалось проверить результат")
                results['errors'] += 1
                results['details'].append({
                    'contact': contact_info,
                    'status': 'ERROR',
                    'message': 'Не удалось проверить результат'
                })
            
        except Exception as e:
            print(f"   ❌ Ошибка: {e}")
            results['errors'] += 1
            results['details'].append({
                'contact': contact_info,
                'status': 'ERROR',
                'message': str(e)
            })
        
                 # Минимальная пауза между контактами
         if i < len(contacts_to_process):
             await asyncio.sleep(0.1)  # Быстрая обработка
        
        print()
    
    # Итоговый отчет
    print("📊 ФИНАЛЬНЫЙ ОТЧЕТ МАССОВОГО ОБНОВЛЕНИЯ")
    print("="*70)
    print(f"⏰ Завершено: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print(f"📈 СТАТИСТИКА:")
    print(f"   🎯 Всего контактов: {results['total']}")
    print(f"   ✅ Успешно обновлено: {results['updated']}")
    print(f"   ✅ Уже обновлено: {results['already_updated']}")
    print(f"   ⏭️ Пропущено: {results['skipped']}")
    print(f"   ❌ Ошибок: {results['errors']}")
    print()
    
    # Детальный отчет
    if results['updated'] > 0:
        print("🎉 УСПЕШНО ОБНОВЛЕННЫЕ КОНТАКТЫ:")
        for detail in results['details']:
            if detail['status'] == 'UPDATED':
                contact = detail['contact']
                print(f"   ✅ {contact['company_name'][:50]}...")
                print(f"      {detail['old_vat']} → {detail['new_vat']}")
        print()
    
    if results['already_updated'] > 0:
        print("✅ УЖЕ ОБНОВЛЕННЫЕ КОНТАКТЫ:")
        for detail in results['details']:
            if detail['status'] == 'ALREADY_UPDATED':
                contact = detail['contact']
                print(f"   ✅ {contact['company_name'][:50]}... (VAT: {detail['vat']})")
        print()
    
    if results['errors'] > 0:
        print("❌ ОШИБКИ:")
        for detail in results['details']:
            if detail['status'] == 'ERROR':
                contact = detail['contact']
                print(f"   ❌ {contact['company_name'][:50]}...")
                print(f"      Причина: {detail['message']}")
        print()
    
    success_rate = ((results['updated'] + results['already_updated']) / results['total']) * 100
    print(f"📈 ПРОЦЕНТ УСПЕХА: {success_rate:.1f}%")
    
    if success_rate >= 90:
        print("🏆 ОТЛИЧНЫЙ РЕЗУЛЬТАТ! Массовое обновление прошло успешно!")
    elif success_rate >= 70:
        print("👍 ХОРОШИЙ РЕЗУЛЬТАТ! Большинство контактов обновлено!")
    else:
        print("⚠️ ЕСТЬ ПРОБЛЕМЫ! Нужно проанализировать ошибки!")
    
    await api_client.client.aclose()
    return results

if __name__ == "__main__":
    print("🚀 ЗАПУСК МАССОВОГО ОБНОВЛЕНИЯ VAT ПРЕФИКСОВ")
    print("="*70)
    print("🎯 Цель: Добавить префикс PL ко всем VAT номерам польских контактов")
    print("🔧 Метод: Проверенный custom_fields API")
    print("⚠️ ВНИМАНИЕ: Это изменит данные в Zoho Books!")
    print()
    
    final_results = asyncio.run(mass_update_vat_prefixes())
    
    if final_results:
        print("\n🎬 МАССОВОЕ ОБНОВЛЕНИЕ ЗАВЕРШЕНО!")
        success_rate = ((final_results['updated'] + final_results['already_updated']) / final_results['total']) * 100
        if success_rate >= 90:
            print("🎉 МИССИЯ ВЫПОЛНЕНА! VAT префиксы обновлены!")
        else:
            print("⚠️ МИССИЯ ЧАСТИЧНО ВЫПОЛНЕНА! Есть что доработать!")
    else:
        print("\n❌ МАССОВОЕ ОБНОВЛЕНИЕ ПРЕРВАНО!") 