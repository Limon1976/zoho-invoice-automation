#!/usr/bin/env python3
"""
Refresh Zoho Cache
==================

Функции для обновления кэша поставщиков из Zoho API
"""

import os
import json
import asyncio
from typing import Dict, List, Any
from datetime import datetime
from pathlib import Path

from src.infrastructure.zoho_api import ZohoAPIClient
from src.domain.services.contact_cache import OptimizedContactCache


class ZohoCacheRefresher:
    """Обновление кэша из Zoho API"""
    
    def __init__(self):
        # Временно убираем зависимость от ZohoAPIClient для простоты
        # self.zoho_api = ZohoAPIClient()
        self.cache = OptimizedContactCache()
        self.data_dir = Path("data")
        self.cache_dir = self.data_dir / "optimized_cache"
    
    async def refresh_cache_from_zoho(self) -> bool:
        """
        Обновляет кэш поставщиков из Zoho API
        
        Returns:
            True если обновление успешно
        """
        try:
            print("🔄 Обновление кэша из Zoho API...")
            
            # Получаем все контакты из Zoho
            contacts = await self.zoho_api.get_all_contacts()
            
            if not contacts:
                print("❌ Не удалось получить контакты из Zoho")
                return False
            
            print(f"📊 Получено {len(contacts)} контактов из Zoho")
            
            # Обновляем кэш
            self.cache.add_contacts(contacts)
            
            # Сохраняем кэш
            self.cache.save_cache()
            
            # Пересоздаем оптимизированный кэш
            self._recreate_optimized_cache(contacts)
            
            print("✅ Кэш успешно обновлен из Zoho")
            return True
            
        except Exception as e:
            print(f"❌ Ошибка обновления кэша из Zoho: {e}")
            return False
    
    def _recreate_optimized_cache(self, contacts: List[Dict[str, Any]]):
        """Пересоздает оптимизированный кэш"""
        try:
            optimized_cache = {
                'contacts': [],
                'vat_index': {},
                'company_index': {},
                'last_updated': datetime.now().isoformat()
            }
            
            # Создаем оптимизированные записи
            for contact in contacts:
                # Извлекаем минимальные данные
                cache_entry = self.cache.extract_minimal_data(contact)
                
                optimized_entry = {
                    'contact_id': cache_entry.contact_id,
                    'contact_name': cache_entry.contact_name,
                    'company_name': cache_entry.company_name,
                    'vat_number': cache_entry.vat_number or '',
                    'email': cache_entry.email,
                    'country': cache_entry.billing_address.get('country', '') if cache_entry.billing_address else '',
                    'city': cache_entry.billing_address.get('city', '') if cache_entry.billing_address else ''
                }
                
                optimized_cache['contacts'].append(optimized_entry)
                
                # Обновляем индексы
                vat_number = cache_entry.vat_number or ''
                contact_name = cache_entry.contact_name
                
                if vat_number:
                    optimized_cache['vat_index'][vat_number] = contact_name
                
                if contact_name:
                    optimized_cache['company_index'][contact_name.lower()] = contact_name
            
            # Сохраняем оптимизированный кэш
            optimized_cache_file = self.cache_dir / "all_contacts_optimized.json"
            with open(optimized_cache_file, 'w', encoding='utf-8') as f:
                json.dump(optimized_cache, f, indent=2, ensure_ascii=False)
            
            print(f"  ✅ Пересоздан оптимизированный кэш: {len(contacts)} контактов")
            
        except Exception as e:
            print(f"  ❌ Ошибка пересоздания оптимизированного кэша: {e}")
    
    async def check_supplier_exists(self, supplier_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Проверяет существование поставщика в кэше
        
        Args:
            supplier_data: Данные поставщика
            
        Returns:
            Данные существующего поставщика или None
        """
        try:
            # Проверяем по VAT номеру
            vat_number = supplier_data.get('vat', '')
            if vat_number:
                existing = self.cache.search_by_vat(vat_number)
                if existing:
                    return {
                        'contact_id': existing.contact_id,
                        'name': existing.contact_name,
                        'vat': existing.vat_number,
                        'email': existing.email,
                        'country': existing.billing_address.get('country', '') if existing.billing_address else '',
                        'city': existing.billing_address.get('city', '') if existing.billing_address else '',
                        'address': existing.billing_address.get('address', '') if existing.billing_address else ''
                    }
            
            # Проверяем по названию компании
            company_name = supplier_data.get('name', '')
            if company_name:
                existing_list = self.cache.search_by_company(company_name)
                if existing_list:
                    existing = existing_list[0]  # Берем первый найденный
                    return {
                        'contact_id': existing.contact_id,
                        'name': existing.contact_name,
                        'vat': existing.vat_number,
                        'email': existing.email,
                        'country': existing.billing_address.get('country', '') if existing.billing_address else '',
                        'city': existing.billing_address.get('city', '') if existing.billing_address else '',
                        'address': existing.billing_address.get('address', '') if existing.billing_address else ''
                    }
            
            return None
            
        except Exception as e:
            print(f"❌ Ошибка проверки существования поставщика: {e}")
            return None


# Функции для интеграции
async def refresh_zoho_cache():
    """
    Обновляет кэш поставщиков из Zoho API
    
    Returns:
        True если обновление успешно
    """
    refresher = ZohoCacheRefresher()
    return await refresher.refresh_cache_from_zoho()


async def check_supplier_in_cache(supplier_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Проверяет существование поставщика в кэше
    
    Args:
        supplier_data: Данные поставщика
        
    Returns:
        Данные существующего поставщика или None
    """
    refresher = ZohoCacheRefresher()
    return await refresher.check_supplier_exists(supplier_data)


# Тестовая функция
async def test_cache_refresh():
    """Тест обновления кэша"""
    print("🧪 Тест обновления кэша из Zoho")
    
    success = await refresh_zoho_cache()
    
    if success:
        print("✅ Кэш успешно обновлен из Zoho")
        
        # Тестируем поиск поставщика
        test_supplier = {
            'name': 'Horrer Automobile GmbH',
            'vat': 'DE123456789'
        }
        
        existing = await check_supplier_in_cache(test_supplier)
        if existing:
            print(f"✅ Найден существующий поставщик: {existing['name']}")
        else:
            print("❌ Поставщик не найден в кэше")
    else:
        print("❌ Ошибка обновления кэша")


def update_contact_in_full_cache(contact_data: dict, organization_name: str) -> bool:
    """
    Обновляет контакт в полном кэше data/full_contacts/
    
    Args:
        contact_data: Полные данные контакта из Zoho API
        organization_name: Название организации
    
    Returns:
        bool: True если обновление успешно
    """
    try:
        # Определяем файл полного кэша
        if organization_name == 'TaVie Europe OÜ':
            full_cache_file = "data/full_contacts/TaVie_Europe_20092948714_full.json"
        elif organization_name == 'PARKENTERTAINMENT':
            full_cache_file = "data/full_contacts/PARKENTERTAINMENT_20082562863_full.json" 
        else:
            print(f"   ❌ Неизвестная организация: {organization_name}")
            return False
            
        if not os.path.exists(full_cache_file):
            print(f"   ❌ Файл полного кэша не найден: {full_cache_file}")
            return False
            
        # Загружаем полный кэш
        with open(full_cache_file, 'r', encoding='utf-8') as f:
            full_contacts = json.load(f)
            
        contact_id = contact_data.get('contact_id')
        contact_name = contact_data.get('contact_name', 'Unknown')
        
        # Ищем контакт в полном кэше
        contact_found = False
        for i, contact in enumerate(full_contacts):
            if contact.get('contact_id') == contact_id:
                # Обновляем контакт
                full_contacts[i] = contact_data
                contact_found = True
                print(f"   ✅ Контакт {contact_name} обновлен в полном кэше")
                break
                
        if not contact_found:
            # Добавляем новый контакт если не найден
            full_contacts.append(contact_data)
            print(f"   ✅ Контакт {contact_name} добавлен в полный кэш")
            
        # Сохраняем обновленный полный кэш
        with open(full_cache_file, 'w', encoding='utf-8') as f:
            json.dump(full_contacts, f, ensure_ascii=False, indent=2)
            
        print(f"   💾 Полный кэш сохранен: {full_cache_file}")
        return True
        
    except Exception as e:
        print(f"   ❌ Ошибка обновления полного кэша: {e}")
        return False


def rebuild_optimized_cache_from_full(organization_name: str) -> bool:
    """
    Пересоздает оптимизированный кэш из полного кэша
    
    Args:
        organization_name: Название организации
    
    Returns:
        bool: True если пересоздание успешно
    """
    try:
        from src.domain.services.contact_cache import OptimizedContactCache
        
        # Определяем файлы кэшей
        if organization_name == 'TaVie Europe OÜ':
            full_cache_file = "data/full_contacts/TaVie_Europe_20092948714_full.json"
            optimized_cache_file = "data/optimized_cache/TaVie_Europe_optimized.json"
        elif organization_name == 'PARKENTERTAINMENT':
            full_cache_file = "data/full_contacts/PARKENTERTAINMENT_20082562863_full.json"
            optimized_cache_file = "data/optimized_cache/PARKENTERTAINMENT_optimized.json"
        else:
            print(f"   ❌ Неизвестная организация: {organization_name}")
            return False
            
        if not os.path.exists(full_cache_file):
            print(f"   ❌ Файл полного кэша не найден: {full_cache_file}")
            return False
            
        # Загружаем полный кэш
        with open(full_cache_file, 'r', encoding='utf-8') as f:
            full_contacts = json.load(f)
            
        print(f"   🔄 Пересоздаем оптимизированный кэш из {len(full_contacts)} контактов")
        
        # Создаем новый оптимизированный кэш
        cache = OptimizedContactCache(optimized_cache_file)
        
        # Добавляем все контакты из полного кэша
        cache.add_contacts(full_contacts)
        
        # Сохраняем оптимизированный кэш
        cache.save_cache()
        
        print(f"   ✅ Оптимизированный кэш пересоздан: {optimized_cache_file}")
        
        # Также обновляем общий кэш all_contacts_optimized.json
        rebuild_combined_optimized_cache()
        
        return True
        
    except Exception as e:
        print(f"   ❌ Ошибка пересоздания оптимизированного кэша: {e}")
        return False


def rebuild_combined_optimized_cache() -> bool:
    """
    Пересоздает объединенный оптимизированный кэш all_contacts_optimized.json
    """
    try:
        from src.domain.services.contact_cache import OptimizedContactCache
        
        all_contacts = []
        
        # Загружаем контакты из всех организаций
        full_cache_files = [
            "data/full_contacts/TaVie_Europe_20092948714_full.json",
            "data/full_contacts/PARKENTERTAINMENT_20082562863_full.json"
        ]
        
        for full_cache_file in full_cache_files:
            if os.path.exists(full_cache_file):
                with open(full_cache_file, 'r', encoding='utf-8') as f:
                    contacts = json.load(f)
                    all_contacts.extend(contacts)
                    
        print(f"   🔄 Пересоздаем объединенный кэш из {len(all_contacts)} контактов")
        
        # Создаем объединенный оптимизированный кэш
        combined_cache_file = "data/optimized_cache/all_contacts_optimized.json"
        cache = OptimizedContactCache(combined_cache_file)
        
        # Добавляем все контакты
        cache.add_contacts(all_contacts)
        
        # Сохраняем кэш
        cache.save_cache()
        
        print(f"   ✅ Объединенный кэш пересоздан: {combined_cache_file}")
        return True
        
    except Exception as e:
        print(f"   ❌ Ошибка пересоздания объединенного кэша: {e}")
        return False


async def refresh_single_contact_cache(contact_id: str, organization_id: str, organization_name: str) -> bool:
    """
    НОВАЯ АРХИТЕКТУРА: Обновляет кэш для одного контакта
    1. Получает данные из Zoho API
    2. Обновляет полный кэш (data/full_contacts/)
    3. Пересоздает оптимизированный кэш из полного
    
    Args:
        contact_id: ID контакта в Zoho
        organization_id: ID организации в Zoho
        organization_name: Название организации (PARKENTERTAINMENT или TaVie Europe OÜ)
    
    Returns:
        bool: True если обновление успешно
    """
    try:
        from functions.zoho_api import get_contact_details
        
        print(f"   🔄 Обновляем кэш для контакта ID: {contact_id}")
        
        # ШАГ 1: Получаем полную информацию о контакте из Zoho API
        contact_details = get_contact_details(organization_id, contact_id)
        if not contact_details:
            print(f"   ❌ Не удалось получить детали контакта {contact_id}")
            return False
        
        contact_name = contact_details.get('contact_name', 'Unknown')
        print(f"   📋 Контакт: {contact_name}")
        
        # ШАГ 2: Обновляем полный кэш
        print(f"   📂 Обновляем полный кэш...")
        if not update_contact_in_full_cache(contact_details, organization_name):
            print(f"   ❌ Ошибка обновления полного кэша")
            return False
        
        # ШАГ 3: Пересоздаем оптимизированный кэш из полного
        print(f"   🔄 Пересоздаем оптимизированный кэш...")
        if not rebuild_optimized_cache_from_full(organization_name):
            print(f"   ❌ Ошибка пересоздания оптимизированного кэша")
            return False
        
        print(f"   ✅ Кэш успешно обновлен для контакта {contact_name}")
        return True
        
    except Exception as e:
        print(f"   ❌ Ошибка обновления кэша: {e}")
        return False


if __name__ == "__main__":
    asyncio.run(test_cache_refresh()) 