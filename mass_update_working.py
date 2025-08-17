#!/usr/bin/env python3
"""
МАССОВОЕ ОБНОВЛЕНИЕ VAT ПРЕФИКСОВ
Основано на 100% рабочем коде test_both_contact_types.py
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.append(str(Path('.').parent))
from src.infrastructure.zoho_api import ZohoAPIClient
from src.infrastructure.config import get_config

async def mass_update_vat():
    print("🚀 МАССОВОЕ ОБНОВЛЕНИЕ VAT ПРЕФИКСОВ")
    print("="*60)
    print("📋 Основано на 100% рабочем коде")
    print("✅ Уже успешно обновлено: 6 контактов")
    print()
    
    confirm = input("🚀 Запустить массовое обновление? (y/N): ").lower()
    if confirm != 'y':
        print("❌ Обновление отменено")
        return
    
    print("\n🎬 НАЧИНАЕМ МАССОВОЕ ОБНОВЛЕНИЕ...")
    print("="*60)
    
    # ТОЧНО ТОТ ЖЕ API КЛИЕНТ
    config = get_config()
    api_client = ZohoAPIClient(
        client_id=config.zoho.client_id,
        client_secret=config.zoho.client_secret,
        refresh_token=config.zoho.refresh_token or ''
    )
    
    org_id = "20082562863"
    
    # ВСЕ КОНТАКТЫ ДЛЯ ОБНОВЛЕНИЯ
    all_contacts = [
        {'name': 'Carrefour Polska', 'contact_id': '281497000005007050'},
        {'name': 'CCM Construction', 'contact_id': '281497000005007187'},
        {'name': 'CHRONOS APARTAMENTY', 'contact_id': '281497000004571563'},
        {'name': 'ETERIA CONSULTING', 'contact_id': '281497000001825719'},
        {'name': 'EUROSTAR-TRANSPORT.EU', 'contact_id': '281497000005395276'},
        {'name': 'F.P.H.U. PROBOX', 'contact_id': '281497000004567718'},
        {'name': 'Faf Global', 'contact_id': '281497000005999849'},
        {'name': 'Flower Island', 'contact_id': '281497000005940057'},
        {'name': 'FN EUROPE', 'contact_id': '281497000006365071'},
        {'name': 'Globe Trade Centre', 'contact_id': '281497000006113586'},
        {'name': 'Google ADS', 'contact_id': '281497000005126385'},
        {'name': 'Grid Dynamics Poland', 'contact_id': '281497000005237353'},
        {'name': 'HOLO SP.', 'contact_id': '281497000005962003'},
        {'name': 'Indigo Mental Club', 'contact_id': '281497000005446183'},
        {'name': 'ISKRY', 'contact_id': '281497000006113397'}
    ]
    
    print(f"📊 Контактов к обновлению: {len(all_contacts)}")
    print()
    
    results = []
    
    for i, test_contact in enumerate(all_contacts, 1):
        print(f"🔬 КОНТАКТ {i}/{len(all_contacts)}: {test_contact['name']}")
        print("-" * 50)
        
        contact_id = test_contact['contact_id']
        
        try:
            # 1. ТОЧНО ТОТ ЖЕ КОД - Получаем текущие данные
            print("📥 1. Получение данных из Zoho...")
            current_data = await api_client.get_contact_details(org_id, contact_id)
            
            if not current_data:
                print("❌ Не удалось получить данные контакта")
                results.append({'contact': test_contact, 'success': False, 'error': 'Нет данных'})
                continue
            
            company_name = current_data.get('company_name', '')
            customer_type = current_data.get('customer_sub_type', '')
            current_vat = current_data.get('cf_tax_id', '')
            
            print(f"   🏢 Компания: {company_name}")
            print(f"   👤 Тип: {customer_type}")
            print(f"   🏷️ Текущий VAT: '{current_vat}'")
            
            # 2. ТОЧНО ТОТ ЖЕ КОД - Определяем нужно ли обновление
            print("\n🔧 2. Анализ необходимости обновления...")
            
            if current_vat.startswith('PL'):
                print(f"   ✅ VAT уже имеет префикс: '{current_vat}'")
                print("   ⏭️ Пропускаем обновление")
                results.append({
                    'contact': test_contact,
                    'success': True,
                    'action': 'ALREADY_UPDATED',
                    'vat': current_vat
                })
                print()
                continue
            
            if not current_vat:
                print("   ⏭️ Нет VAT номера")
                results.append({
                    'contact': test_contact,
                    'success': True,
                    'action': 'NO_VAT'
                })
                print()
                continue
            
            # 3. ТОЧНО ТОТ ЖЕ КОД - Попробуем обновление через рабочий метод
            print("📤 3. Попытка обновления через custom_fields...")
            new_vat = f"PL{current_vat}"
            
            # ТОЧНО ТОТ ЖЕ РАБОЧИЙ МЕТОД
            update_data = {
                'custom_fields': [
                    {
                        'api_name': 'cf_tax_id',
                        'value': new_vat
                    }
                ]
            }
            
            print(f"   Новый VAT: '{new_vat}'")
            print(f"   Метод: custom_fields API")
            
            response = await api_client.update_contact(
                organization_id=org_id,
                contact_id=contact_id,
                contact_data=update_data
            )
            
            if not response:
                print("   ❌ API отклонил запрос")
                results.append({
                    'contact': test_contact,
                    'success': False,
                    'error': 'API отклонил запрос'
                })
                continue
            
            print("   ✅ API принял запрос")
            
            # 4. ТОЧНО ТОТ ЖЕ КОД - Проверяем результат
            print("🔍 4. Проверка результата...")
            await asyncio.sleep(2)  # ТОЧНО ТА ЖЕ ПАУЗА
            
            updated_data = await api_client.get_contact_details(org_id, contact_id)
            
            if not updated_data:
                print("   ❌ Не удалось получить обновленные данные")
                results.append({
                    'contact': test_contact,
                    'success': False,
                    'error': 'Нет обновленных данных'
                })
                continue
            
            final_vat = updated_data.get('cf_tax_id', '')
            print(f"   📊 Финальный VAT: '{final_vat}'")
            
            # ТОЧНО ТОТ ЖЕ КОД - Анализируем результат
            if final_vat == new_vat:
                print("   🎉 УСПЕХ! VAT обновлен с префиксом!")
                print(f"   ✅ {current_vat} → {final_vat}")
                
                results.append({
                    'contact': test_contact,
                    'success': True,
                    'action': 'UPDATED',
                    'old_vat': current_vat,
                    'new_vat': final_vat
                })
                
            elif final_vat == current_vat:
                print("   ❌ VAT остался без изменений")
                print(f"   🔒 Поле защищено от редактирования")
                
                results.append({
                    'contact': test_contact,
                    'success': False,
                    'error': 'Поле защищено от API изменений',
                    'customer_type': customer_type
                })
                
            else:
                print(f"   🤷 Неожиданное значение: '{final_vat}'")
                results.append({
                    'contact': test_contact,
                    'success': False,
                    'error': f'Неожиданное значение: {final_vat}'
                })
            
        except Exception as e:
            print(f"   ❌ Ошибка: {e}")
            results.append({
                'contact': test_contact,
                'success': False,
                'error': str(e)
            })
        
        print()
        if i < len(all_contacts):
            print("⏳ Пауза 1 секунда...")
            await asyncio.sleep(1)
            print()
    
    # ИТОГОВЫЙ ОТЧЕТ
    print("📊 ИТОГОВЫЙ ОТЧЕТ МАССОВОГО ОБНОВЛЕНИЯ:")
    print("="*60)
    
    updated_count = 0
    already_updated_count = 0
    error_count = 0
    
    print("✅ УСПЕШНО ОБНОВЛЕННЫЕ:")
    for result in results:
        if result['success'] and result.get('action') == 'UPDATED':
            print(f"   🎉 {result['contact']['name']}: {result['old_vat']} → {result['new_vat']}")
            updated_count += 1
    
    print("\n✅ УЖЕ БЫЛИ ОБНОВЛЕНЫ:")
    for result in results:
        if result['success'] and result.get('action') == 'ALREADY_UPDATED':
            print(f"   ✅ {result['contact']['name']}: {result['vat']}")
            already_updated_count += 1
    
    print("\n❌ ОШИБКИ:")
    for result in results:
        if not result['success']:
            print(f"   ❌ {result['contact']['name']}: {result['error']}")
            error_count += 1
    
    print(f"\n📈 СТАТИСТИКА:")
    print(f"   🎉 Новых обновлений: {updated_count}")
    print(f"   ✅ Уже готовых: {already_updated_count}")
    print(f"   ❌ Ошибок: {error_count}")
    print(f"   📊 Всего обработано: {len(results)}")
    
    success_rate = ((updated_count + already_updated_count) / len(results)) * 100
    print(f"   💪 Успех: {success_rate:.1f}%")
    
    if success_rate >= 90:
        print("\n🏆 ОТЛИЧНЫЙ РЕЗУЛЬТАТ!")
    elif success_rate >= 70:
        print("\n👍 ХОРОШИЙ РЕЗУЛЬТАТ!")
    else:
        print("\n⚠️ ЕСТЬ ПРОБЛЕМЫ!")
    
    await api_client.client.aclose()
    return results

if __name__ == "__main__":
    print("🚀 МАССОВОЕ ОБНОВЛЕНИЕ VAT ПРЕФИКСОВ")
    print("="*60)
    print("📋 Основано на 100% рабочем коде")
    print("✅ Протестировано на 6 контактах - все успешно!")
    print()
    
    final_results = asyncio.run(mass_update_vat())
    
    if final_results:
        print("\n🎬 МАССОВОЕ ОБНОВЛЕНИЕ ЗАВЕРШЕНО!")
        print("🎯 Миссия выполнена!")
    else:
        print("\n❌ ОБНОВЛЕНИЕ ПРЕРВАНО!") 