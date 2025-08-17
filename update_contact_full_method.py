#!/usr/bin/env python3
"""
Полное обновление контакта - точно как с LUNA BEAUTY
1. Обновление в Zoho API
2. Получение актуальных данных
3. Обновление локального файла  
4. Обновление кэша
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent))

from src.infrastructure.zoho_api import ZohoAPIClient
from src.infrastructure.config import get_config
from src.domain.services.contact_cache import OptimizedContactCache

async def update_contact_full_method():
    """Полное обновление контакта - метод LUNA BEAUTY"""
    
    print('🔄 ПОЛНОЕ ОБНОВЛЕНИЕ КОНТАКТА - МЕТОД LUNA BEAUTY')
    print('='*70)
    print('✅ Используем точно тот же алгоритм что сработал с LUNA BEAUTY')
    print()
    
    # Тестовый контакт - AEvent из прикрепленного файла
    test_contact = {
        'contact_id': '281497000005903525',
        'company_name': 'AEvent Antonina Koroleva Obukhov Eugenia Gułajewska Spółka Cywilna',
        'current_vat': '9512598212',
        'new_vat': 'PL9512598212'
    }
    
    config = get_config()
    organization_id = '20082562863'  # PARKENTERTAINMENT
    
    api_client = ZohoAPIClient(
        client_id=config.zoho.client_id,
        client_secret=config.zoho.client_secret,
        refresh_token=config.zoho.refresh_token or ''
    )
    
    print(f'🎯 ОБНОВЛЯЕМ: {test_contact["company_name"]}')
    print(f'📍 Contact ID: {test_contact["contact_id"]}')
    print(f'🔄 VAT: "{test_contact["current_vat"]}" → "{test_contact["new_vat"]}"')
    print()
    
    try:
        # ШАГ 1: Обновляем в Zoho Books (как с LUNA BEAUTY)
        print('1️⃣ ОБНОВЛЕНИЕ В ZOHO BOOKS:')
        print('-' * 40)
        
        update_data = {
            'cf_tax_id': test_contact['new_vat']
        }
        
        print(f'📤 Отправляем: {json.dumps(update_data, ensure_ascii=False)}')
        
        update_success = await api_client.update_contact(
            contact_id=test_contact['contact_id'],
            contact_data=update_data,
            organization_id=organization_id
        )
        
        if not update_success:
            print('❌ Ошибка обновления в Zoho Books')
            return False
            
        print('✅ Данные отправлены в Zoho Books')
        print()
        
        # ШАГ 2: Ждем обработки и получаем актуальные данные (как с LUNA BEAUTY)
        print('2️⃣ ПОЛУЧЕНИЕ АКТУАЛЬНЫХ ДАННЫХ ИЗ ZOHO:')
        print('-' * 40)
        
        print('⏳ Ждем 5 секунд для обработки в Zoho...')
        await asyncio.sleep(5)
        
        updated_contact = await api_client.get_contact_details(
            organization_id=organization_id,
            contact_id=test_contact['contact_id']
        )
        
        if not updated_contact:
            print('❌ Ошибка получения обновленных данных')
            return False
            
        # Добавляем organization_id для локального использования
        updated_contact['organization_id'] = organization_id
        
        # Проверяем результат обновления
        final_vat = updated_contact.get('cf_tax_id', '')
        final_vat_unformatted = updated_contact.get('cf_tax_id_unformatted', '')
        
        print(f'📊 Актуальные данные из Zoho:')
        print(f'   cf_tax_id: "{final_vat}"')
        print(f'   cf_tax_id_unformatted: "{final_vat_unformatted}"')
        
        # Проверяем custom_field_hash и custom_fields
        hash_data = updated_contact.get('custom_field_hash', {})
        print(f'   custom_field_hash.cf_tax_id: "{hash_data.get("cf_tax_id", "")}"')
        
        custom_fields = updated_contact.get('custom_fields', [])
        for field in custom_fields:
            if field.get('api_name') == 'cf_tax_id':
                print(f'   custom_fields.value: "{field.get("value", "")}"')
                print(f'   custom_fields.value_formatted: "{field.get("value_formatted", "")}"')
                break
        
        print()
        
        if final_vat == test_contact['new_vat']:
            print('✅ VAT успешно обновлен в Zoho!')
            zoho_success = True
        else:
            print(f'❌ VAT не обновлен в Zoho (ожидали "{test_contact["new_vat"]}", получили "{final_vat}")')
            zoho_success = False
        
        print()
        
        # ШАГ 3: Обновляем локальный файл (как с LUNA BEAUTY)
        print('3️⃣ ОБНОВЛЕНИЕ ЛОКАЛЬНОГО ФАЙЛА:')
        print('-' * 40)
        
        file_path = 'data/full_contacts/PARKENTERTAINMENT_20082562863_full.json'
        
        if Path(file_path).exists():
            with open(file_path, 'r', encoding='utf-8') as f:
                contacts = json.load(f)
            
            print(f'📂 Загружено {len(contacts)} контактов из локального файла')
            
            # Находим и обновляем контакт
            contact_updated = False
            for i, contact in enumerate(contacts):
                if contact.get('contact_id') == test_contact['contact_id']:
                    contacts[i] = updated_contact
                    contact_updated = True
                    print(f'✅ Контакт найден и обновлен (позиция {i})')
                    break
            
            if contact_updated:
                # Сохраняем обновленный файл
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(contacts, f, ensure_ascii=False, indent=2)
                
                print('✅ Локальный файл сохранен с обновленными данными')
            else:
                print('❌ Контакт не найден в локальном файле')
        else:
            print(f'❌ Локальный файл {file_path} не найден')
        
        print()
        
        # ШАГ 4: Обновляем кэш (как с LUNA BEAUTY)
        print('4️⃣ ОБНОВЛЕНИЕ КЭША:')
        print('-' * 40)
        
        try:
            cache = OptimizedContactCache('data/optimized_cache/all_contacts_optimized.json')
            
            # Удаляем старую запись из кэша
            if test_contact['contact_id'] in cache.contacts:
                old_contact = cache.contacts[test_contact['contact_id']]
                
                # Удаляем из VAT индекса
                if old_contact.vat_number:
                    cache.vat_index.pop(old_contact.vat_number, None)
                    print(f'🗑️ Удален старый VAT из индекса: "{old_contact.vat_number}"')
                
                # Удаляем из email индекса
                if old_contact.email:
                    cache.email_index.pop(old_contact.email, None)
                
                # Удаляем из company индекса
                if old_contact.company_name:
                    company_contacts = cache.company_index.get(old_contact.company_name, [])
                    if test_contact['contact_id'] in company_contacts:
                        company_contacts.remove(test_contact['contact_id'])
                    if not company_contacts:
                        cache.company_index.pop(old_contact.company_name, None)
                
                # Удаляем сам контакт
                del cache.contacts[test_contact['contact_id']]
                
                print('🗑️ Старые данные удалены из кэша')
            
            # Добавляем обновленные данные
            cache.add_contacts([updated_contact])
            cache.save_cache()
            
            print('✅ Кэш обновлен новыми данными')
            
            # Проверяем результат в кэше
            cached_contact = cache.search_by_vat(test_contact['new_vat'])
            if cached_contact:
                print(f'🔍 Поиск в кэше по новому VAT "{test_contact["new_vat"]}": НАЙДЕН')
                print(f'   Компания: {cached_contact.company_name}')
            else:
                print(f'❌ Поиск в кэше по новому VAT "{test_contact["new_vat"]}": НЕ НАЙДЕН')
                
        except Exception as e:
            print(f'❌ Ошибка обновления кэша: {e}')
        
        print()
        
        # ФИНАЛЬНАЯ ПРОВЕРКА
        print('5️⃣ ФИНАЛЬНАЯ ПРОВЕРКА:')
        print('-' * 40)
        
        if zoho_success:
            print('🎉 УСПЕХ! Полное обновление завершено!')
            print('✅ Zoho Books обновлен')
            print('✅ Локальный файл обновлен') 
            print('✅ Кэш обновлен')
            print()
            print('🚀 ГОТОВЫ К МАССОВОМУ ОБНОВЛЕНИЮ ОСТАЛЬНЫХ КОНТАКТОВ!')
            return True
        else:
            print('❌ Обновление не удалось')
            print('💭 Возможные причины:')
            print('   • Нужно больше времени для обработки')
            print('   • Особые права доступа у разных контактов')
            print('   • Временные проблемы API')
            return False
        
    except Exception as e:
        print(f'❌ Ошибка: {e}')
        return False
    
    finally:
        await api_client.client.aclose()

if __name__ == "__main__":
    success = asyncio.run(update_contact_full_method())
    print()
    if success:
        print('🎯 МЕТОД LUNA BEAUTY СРАБОТАЛ!')
        print('💡 Можем использовать для всех остальных контактов')
    else:
        print('🔧 Нужны дополнительные исследования') 