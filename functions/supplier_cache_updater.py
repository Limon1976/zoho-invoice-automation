#!/usr/bin/env python3
"""
Supplier Cache Updater
======================

Функции для обновления кэша поставщиков при создании новых контактов в Zoho
"""

import json
import os
from typing import Dict, Any, List
from datetime import datetime
from pathlib import Path

from src.domain.services.contact_cache import OptimizedContactCache


class SupplierCacheUpdater:
    """Обновление кэша поставщиков"""
    
    def __init__(self):
        self.cache = OptimizedContactCache()
        self.data_dir = Path("data")
        self.cache_dir = self.data_dir / "optimized_cache"
    
    def update_supplier_cache(self, new_supplier_data: Dict[str, Any]) -> bool:
        """
        Обновляет кэш поставщиков при создании нового контакта
        
        Args:
            new_supplier_data: Данные нового поставщика из Zoho
            
        Returns:
            True если обновление успешно
        """
        try:
            print(f"🔄 Обновление кэша поставщиков...")
            
            # 1. Обновляем основной кэш
            self._update_main_cache(new_supplier_data)
            
            # 2. Обновляем оптимизированный кэш
            self._update_optimized_cache(new_supplier_data)
            
            # 3. Обновляем файлы данных
            self._update_data_files(new_supplier_data)
            
            print("✅ Кэш поставщиков обновлен")
            return True
            
        except Exception as e:
            print(f"❌ Ошибка обновления кэша: {e}")
            return False
    
    def _update_main_cache(self, supplier_data: Dict[str, Any]):
        """Обновление основного кэша"""
        try:
            # Добавляем нового поставщика в кэш
            contact_id = supplier_data.get('contact_id')
            contact_name = supplier_data.get('contact_name')
            
            if contact_id and contact_name:
                # Создаем запись для кэша
                cache_entry = {
                    'contact_id': contact_id,
                    'contact_name': contact_name,
                    'company_name': supplier_data.get('company_name', contact_name),
                    'email': supplier_data.get('email', ''),
                    'phone': supplier_data.get('phone', ''),
                    'vat_number': supplier_data.get('vat_number', ''),
                    'address': supplier_data.get('address', ''),
                    'country': supplier_data.get('country', ''),
                    'city': supplier_data.get('city', ''),
                    'state': supplier_data.get('state', ''),
                    'zip_code': supplier_data.get('zip_code', ''),
                    'created_time': supplier_data.get('created_time', datetime.now().isoformat()),
                    'last_modified_time': supplier_data.get('last_modified_time', datetime.now().isoformat())
                }
                
                # Добавляем в кэш
                self.cache.add_contacts([cache_entry])
                print(f"  ✅ Добавлен в основной кэш: {contact_name}")
                
        except Exception as e:
            print(f"  ❌ Ошибка обновления основного кэша: {e}")
    
    def _update_optimized_cache(self, supplier_data: Dict[str, Any]):
        """Обновление оптимизированного кэша"""
        try:
            optimized_cache_file = self.cache_dir / "all_contacts_optimized.json"
            
            if optimized_cache_file.exists():
                with open(optimized_cache_file, 'r', encoding='utf-8') as f:
                    optimized_cache = json.load(f)
            else:
                optimized_cache = {
                    'contacts': [],
                    'vat_index': {},
                    'company_index': {},
                    'last_updated': datetime.now().isoformat()
                }
            
            # Создаем оптимизированную запись
            contact_name = supplier_data.get('contact_name', '')
            vat_number = supplier_data.get('vat_number', '')
            
            optimized_entry = {
                'contact_id': supplier_data.get('contact_id'),
                'contact_name': contact_name,
                'company_name': supplier_data.get('company_name', contact_name),
                'vat_number': vat_number,
                'email': supplier_data.get('email', ''),
                'country': supplier_data.get('country', ''),
                'city': supplier_data.get('city', '')
            }
            
            # Добавляем в список контактов
            optimized_cache['contacts'].append(optimized_entry)
            
            # Обновляем индексы
            if vat_number:
                optimized_cache['vat_index'][vat_number] = contact_name
            
            if contact_name:
                optimized_cache['company_index'][contact_name.lower()] = contact_name
            
            optimized_cache['last_updated'] = datetime.now().isoformat()
            
            # Сохраняем обновленный кэш
            with open(optimized_cache_file, 'w', encoding='utf-8') as f:
                json.dump(optimized_cache, f, indent=2, ensure_ascii=False)
            
            print(f"  ✅ Обновлен оптимизированный кэш: {contact_name}")
            
        except Exception as e:
            print(f"  ❌ Ошибка обновления оптимизированного кэша: {e}")
    
    def _update_data_files(self, supplier_data: Dict[str, Any]):
        """Обновление файлов данных"""
        try:
            # Обновляем файл с полными контактами
            full_contacts_file = self.data_dir / "full_contacts" / f"{supplier_data.get('contact_name', 'unknown')}_full.json"
            
            if not full_contacts_file.parent.exists():
                full_contacts_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Сохраняем полные данные контакта
            with open(full_contacts_file, 'w', encoding='utf-8') as f:
                json.dump(supplier_data, f, indent=2, ensure_ascii=False)
            
            print(f"  ✅ Создан файл полных данных: {full_contacts_file.name}")
            
        except Exception as e:
            print(f"  ❌ Ошибка обновления файлов данных: {e}")
    
    def update_specific_supplier(self, contact_id: str, updated_data: Dict[str, Any]) -> bool:
        """
        Обновляет конкретного поставщика в кэше
        
        Args:
            contact_id: ID контакта в Zoho
            updated_data: Обновленные данные
            
        Returns:
            True если обновление успешно
        """
        try:
            print(f"🔄 Обновление поставщика {contact_id}...")
            
            # Обновляем оптимизированный кэш
            self._update_optimized_cache(updated_data)
            
            print(f"✅ Поставщик {contact_id} обновлен")
            return True
            
        except Exception as e:
            print(f"❌ Ошибка обновления поставщика: {e}")
            return False
    
    def refresh_all_caches(self) -> bool:
        """
        Обновляет все кэши из Zoho API
        
        Returns:
            True если обновление успешно
        """
        try:
            print("🔄 Полное обновление всех кэшей...")
            
            # Пересоздаем оптимизированный кэш
            self._recreate_optimized_cache()
            
            print("✅ Все кэши обновлены")
            return True
            
        except Exception as e:
            print(f"❌ Ошибка полного обновления кэшей: {e}")
            return False
    
    def _recreate_optimized_cache(self):
        """Пересоздает оптимизированный кэш"""
        try:
            # Получаем все контакты из основного кэша
            all_contacts = list(self.cache.contacts.values())
            
            optimized_cache = {
                'contacts': [],
                'vat_index': {},
                'company_index': {},
                'last_updated': datetime.now().isoformat()
            }
            
            # Создаем оптимизированные записи
            for contact in all_contacts:
                optimized_entry = {
                    'contact_id': contact.contact_id,
                    'contact_name': contact.contact_name,
                    'company_name': contact.company_name,
                    'vat_number': contact.vat_number or '',
                    'email': contact.email,
                    'country': contact.billing_address.get('country', '') if contact.billing_address else '',
                    'city': contact.billing_address.get('city', '') if contact.billing_address else ''
                }
                
                optimized_cache['contacts'].append(optimized_entry)
                
                # Обновляем индексы
                vat_number = contact.vat_number or ''
                contact_name = contact.contact_name
                
                if vat_number:
                    optimized_cache['vat_index'][vat_number] = contact_name
                
                if contact_name:
                    optimized_cache['company_index'][contact_name.lower()] = contact_name
            
            # Сохраняем оптимизированный кэш
            optimized_cache_file = self.cache_dir / "all_contacts_optimized.json"
            with open(optimized_cache_file, 'w', encoding='utf-8') as f:
                json.dump(optimized_cache, f, indent=2, ensure_ascii=False)
            
            print(f"  ✅ Пересоздан оптимизированный кэш: {len(all_contacts)} контактов")
            
        except Exception as e:
            print(f"  ❌ Ошибка пересоздания оптимизированного кэша: {e}")


# Функции для интеграции
def update_supplier_cache_after_creation(supplier_data: Dict[str, Any]) -> bool:
    """
    Обновляет кэш поставщиков после создания нового контакта
    
    Args:
        supplier_data: Данные поставщика из Zoho
        
    Returns:
        True если обновление успешно
    """
    updater = SupplierCacheUpdater()
    return updater.update_supplier_cache(supplier_data)


def update_specific_supplier_cache(contact_id: str, updated_data: Dict[str, Any]) -> bool:
    """
    Обновляет конкретного поставщика в кэше
    
    Args:
        contact_id: ID контакта в Zoho
        updated_data: Обновленные данные
        
    Returns:
        True если обновление успешно
    """
    updater = SupplierCacheUpdater()
    return updater.update_specific_supplier(contact_id, updated_data)


def refresh_all_supplier_caches() -> bool:
    """
    Обновляет все кэши поставщиков
    
    Returns:
        True если обновление успешно
    """
    updater = SupplierCacheUpdater()
    return updater.refresh_all_caches()


# Тестовая функция
def test_cache_updater():
    """Тест обновления кэша"""
    print("🧪 Тест обновления кэша поставщиков")
    
    # Тестовые данные нового поставщика
    test_supplier_data = {
        'contact_id': '460000000026049',
        'contact_name': 'Horrer Automobile GmbH',
        'company_name': 'Horrer Automobile GmbH',
        'email': 'info@horrer-automobile.de',
        'phone': '+49 (0)7031-234178',
        'vat_number': 'DE123456789',
        'address': 'Stuttgarter Strasse 116',
        'country': 'DE',
        'city': 'Böblingen',
        'state': 'Baden-Württemberg',
        'zip_code': '71032',
        'created_time': datetime.now().isoformat(),
        'last_modified_time': datetime.now().isoformat()
    }
    
    print("📋 Тестовые данные поставщика:")
    for key, value in test_supplier_data.items():
        print(f"  {key}: {value}")
    
    # Тестируем обновление кэша
    success = update_supplier_cache_after_creation(test_supplier_data)
    
    if success:
        print("✅ Тест обновления кэша успешен")
    else:
        print("❌ Тест обновления кэша не удался")


if __name__ == "__main__":
    test_cache_updater() 