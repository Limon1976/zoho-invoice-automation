#!/usr/bin/env python3
"""
Диагностика обновления VAT номеров - показываем полные ответы API
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent))

from src.infrastructure.zoho_api import ZohoAPIClient
from src.infrastructure.config import get_config

async def debug_api_responses():
    """Детальная диагностика ответов Zoho API"""
    
    print('🔍 ДЕТАЛЬНАЯ ДИАГНОСТИКА ZOHO API:')
    print('='*60)
    
    config = get_config()
    api_client = ZohoAPIClient(
        client_id=config.zoho.client_id,
        client_secret=config.zoho.client_secret,
        refresh_token=config.zoho.refresh_token or ''
    )
    
    # Тестовый контакт
    org_id = '20082562863'
    contact_id = '281497000005903525'
    
    print(f'🎯 Тестируем Contact ID: {contact_id}')
    print(f'🏢 Организация: {org_id}')
    print()
    
    try:
        # 1. Получаем текущие данные
        print('1️⃣ ПОЛУЧЕНИЕ ТЕКУЩИХ ДАННЫХ:')
        print('-' * 40)
        
        current_response = await api_client.get_contact_details(org_id, contact_id)
        if current_response:
            current_vat = current_response.get('cf_tax_id', '')
            print(f'✅ Текущий VAT: "{current_vat}"')
            print(f'✅ Имя компании: {current_response.get("company_name", "Unknown")}')
        else:
            print('❌ Ошибка получения данных')
            return
        
        print()
        
        # 2. Создаем модифицированный API клиент с детальным логированием
        print('2️⃣ ТЕСТИРОВАНИЕ ОБНОВЛЕНИЯ VAT:')
        print('-' * 40)
        
        # Подготавливаем данные для обновления
        update_data = {
            'cf_tax_id': 'PL9512598212'
        }
        
        print(f'📤 Отправляем данные: {json.dumps(update_data, ensure_ascii=False)}')
        
        # Выполняем запрос с детальным логированием
        url = f"{api_client.base_url}/contacts/{contact_id}"
        params = {"organization_id": org_id}
        
        print(f'🌐 URL: {url}')
        print(f'📊 Параметры: {params}')
        
        # Проверяем токен
        if not api_client.access_token:
            await api_client._refresh_access_token()
        
        headers = {
            "Authorization": f"Zoho-oauthtoken {api_client.access_token}",
            "Content-Type": "application/json"
        }
        
        print(f'🔑 Токен: ...{api_client.access_token[-10:] if api_client.access_token else "None"}')
        
        # Выполняем запрос
        response = await api_client.client.request(
            method='PUT',
            url=url,
            params=params,
            json=update_data,
            headers=headers
        )
        
        print(f'📥 Статус ответа: {response.status_code}')
        print(f'📥 Заголовки ответа: {dict(response.headers)}')
        
        # Показываем тело ответа
        try:
            response_data = response.json()
            print(f'📥 Тело ответа:')
            print(json.dumps(response_data, ensure_ascii=False, indent=2))
        except:
            response_text = response.text
            print(f'📥 Текст ответа: {response_text}')
        
        print()
        
        # 3. Проверяем результат
        print('3️⃣ ПРОВЕРКА РЕЗУЛЬТАТА:')
        print('-' * 40)
        
        await asyncio.sleep(2)  # Пауза для обработки
        
        updated_response = await api_client.get_contact_details(org_id, contact_id)
        if updated_response:
            updated_vat = updated_response.get('cf_tax_id', '')
            updated_vat_unformatted = updated_response.get('cf_tax_id_unformatted', '')
            
            print(f'📊 Результат после обновления:')
            print(f'   cf_tax_id: "{updated_vat}"')
            print(f'   cf_tax_id_unformatted: "{updated_vat_unformatted}"')
            
            if updated_vat == 'PL9512598212':
                print('✅ УСПЕХ! VAT номер обновлен')
            else:
                print('❌ VAT номер НЕ изменился')
                
                # Анализируем возможные причины
                print()
                print('🔍 ВОЗМОЖНЫЕ ПРИЧИНЫ:')
                print('   • Поле cf_tax_id доступно только для чтения')
                print('   • Нужны особые права доступа для изменения VAT')
                print('   • Zoho Books не позволяет изменять VAT после создания')
                print('   • Нужно использовать другой API endpoint')
                print('   • Требуется проверка в веб-интерфейсе Zoho')
        
        print()
        
        # 4. Попробуем альтернативные поля
        print('4️⃣ ТЕСТИРОВАНИЕ АЛЬТЕРНАТИВНЫХ ПОЛЕЙ:')
        print('-' * 40)
        
        alternative_updates = [
            {'tax_id': 'PL9512598212'},
            {'vat_number': 'PL9512598212'},
            {'tax_number': 'PL9512598212'},
            {'cf_vat_id': 'PL9512598212'},  # Как в эстонской организации
        ]
        
        for i, alt_data in enumerate(alternative_updates, 1):
            print(f'Тест {i}: {list(alt_data.keys())[0]} = {list(alt_data.values())[0]}')
            
            alt_response = await api_client.client.request(
                method='PUT',
                url=url,
                params=params,
                json=alt_data,
                headers=headers
            )
            
            print(f'   Статус: {alt_response.status_code}')
            
            try:
                alt_data_response = alt_response.json()
                if 'message' in alt_data_response:
                    print(f'   Сообщение: {alt_data_response["message"]}')
                if 'errors' in alt_data_response:
                    print(f'   Ошибки: {alt_data_response["errors"]}')
            except:
                print(f'   Ответ: {alt_response.text[:100]}...')
            
            await asyncio.sleep(1)
        
    except Exception as e:
        print(f'❌ Ошибка: {e}')
    
    finally:
        await api_client.client.aclose()

if __name__ == "__main__":
    asyncio.run(debug_api_responses()) 