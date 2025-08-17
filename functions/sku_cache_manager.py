"""
SKU Cache Manager
=================

Быстрая система кэширования SKU для проверки дубликатов без API запросов.
"""
import json
import os
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pathlib import Path


class SKUCacheManager:
    """Менеджер локального кэша SKU"""
    
    def __init__(self, cache_dir: str = "data/sku_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.tavie_cache_file = self.cache_dir / "tavie_europe_skus.json"
        
    def load_sku_cache(self, organization_id: str = "20092948714") -> Dict[str, Any]:
        """
        Загрузка кэша SKU из файла
        
        Args:
            organization_id: ID организации
            
        Returns:
            Данные кэша или пустой кэш
        """
        if organization_id == "20092948714":
            cache_file = self.tavie_cache_file
        else:
            cache_file = self.cache_dir / f"{organization_id}_skus.json"
            
        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"❌ Ошибка загрузки кэша SKU: {e}")
                
        return self._empty_cache(organization_id)
        
    def _empty_cache(self, organization_id: str) -> Dict[str, Any]:
        """Создание пустого кэша"""
        org_names = {
            "20092948714": "TaVie Europe OÜ",
            "20082562863": "PARKENTERTAINMENT"
        }
        
        return {
            "organization_id": organization_id,
            "organization_name": org_names.get(organization_id, "Unknown"),
            "total_skus": 0,
            "last_updated": None,
            "skus": []
        }
        
    def save_sku_cache(self, sku_data: Dict[str, Any], organization_id: str = "20092948714"):
        """
        Сохранение кэша SKU в файл
        
        Args:
            sku_data: Данные для сохранения
            organization_id: ID организации
        """
        if organization_id == "20092948714":
            cache_file = self.tavie_cache_file
        else:
            cache_file = self.cache_dir / f"{organization_id}_skus.json"
            
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(sku_data, f, indent=2, ensure_ascii=False)
            print(f"✅ Кэш SKU сохранен: {cache_file}")
        except Exception as e:
            print(f"❌ Ошибка сохранения кэша SKU: {e}")
            
    def is_sku_cached(self, vin: str, organization_id: str = "20092948714") -> bool:
        """
        Быстрая проверка SKU в локальном кэше
        
        Args:
            vin: VIN номер для проверки
            organization_id: ID организации
            
        Returns:
            True если SKU найден в кэше
        """
        cache_data = self.load_sku_cache(organization_id)
        skus = cache_data.get('skus', [])
        return vin in skus
        
    def add_sku_to_cache(self, vin: str, organization_id: str = "20092948714"):
        """
        Добавление нового SKU в кэш
        
        Args:
            vin: VIN номер для добавления
            organization_id: ID организации
        """
        cache_data = self.load_sku_cache(organization_id)
        
        if vin not in cache_data['skus']:
            cache_data['skus'].append(vin)
            cache_data['total_skus'] = len(cache_data['skus'])
            cache_data['last_updated'] = datetime.now().isoformat()
            
            self.save_sku_cache(cache_data, organization_id)
            print(f"✅ SKU {vin} добавлен в кэш")
        else:
            print(f"ℹ️ SKU {vin} уже в кэше")
            
    def is_cache_fresh(self, organization_id: str = "20092948714", max_age_hours: int = 24) -> bool:
        """
        Проверка актуальности кэша
        
        Args:
            organization_id: ID организации
            max_age_hours: Максимальный возраст кэша в часах
            
        Returns:
            True если кэш свежий
        """
        cache_data = self.load_sku_cache(organization_id)
        last_updated = cache_data.get('last_updated')
        
        if not last_updated:
            return False
            
        try:
            updated_time = datetime.fromisoformat(last_updated)
            now = datetime.now()
            age = now - updated_time
            
            return age < timedelta(hours=max_age_hours)
        except Exception:
            return False
            
    def get_cache_stats(self, organization_id: str = "20092948714") -> Dict[str, Any]:
        """
        Получение статистики кэша
        
        Args:
            organization_id: ID организации
            
        Returns:
            Статистика кэша
        """
        cache_data = self.load_sku_cache(organization_id)
        
        stats = {
            "organization_name": cache_data.get('organization_name'),
            "total_skus": cache_data.get('total_skus', 0),
            "last_updated": cache_data.get('last_updated'),
            "is_fresh": self.is_cache_fresh(organization_id),
            "cache_age_hours": None
        }
        
        if cache_data.get('last_updated'):
            try:
                updated_time = datetime.fromisoformat(cache_data['last_updated'])
                age = datetime.now() - updated_time
                stats["cache_age_hours"] = round(age.total_seconds() / 3600, 2)
            except Exception:
                pass
                
        return stats
        
    def refresh_cache_from_api(self, organization_id: str = "20092948714") -> bool:
        """
        Обновление кэша из Zoho API
        
        Args:
            organization_id: ID организации
            
        Returns:
            True если обновление успешно
        """
        try:
            # Импортируем только при необходимости
            from zoho_items_manager import ZohoItemsManager
            
            manager = ZohoItemsManager()
            print(f"🔄 Обновляю кэш SKU для {organization_id}...")
            
            # Получаем все SKU из API
            skus = manager.get_all_items_sku(organization_id)
            
            if skus:
                # Создаем структуру кэша
                org_names = {
                    "20092948714": "TaVie Europe OÜ",
                    "20082562863": "PARKENTERTAINMENT"
                }
                
                sku_cache = {
                    'organization_id': organization_id,
                    'organization_name': org_names.get(organization_id, "Unknown"),
                    'total_skus': len(skus),
                    'last_updated': datetime.now().isoformat(),
                    'skus': skus
                }
                
                # Сохраняем
                self.save_sku_cache(sku_cache, organization_id)
                print(f"✅ Кэш обновлен: {len(skus)} SKU")
                return True
            else:
                print("❌ Не удалось получить SKU из API")
                return False
                
        except Exception as e:
            print(f"❌ Ошибка обновления кэша: {e}")
            return False


def quick_sku_check(vin: str, organization_id: str = "20092948714") -> Dict[str, Any]:
    """
    Быстрая проверка SKU с автоматическим обновлением кэша при необходимости
    
    Args:
        vin: VIN номер для проверки
        organization_id: ID организации
        
    Returns:
        Результат проверки
    """
    manager = SKUCacheManager()
    
    # Проверяем актуальность кэша
    if not manager.is_cache_fresh(organization_id):
        print("⚠️ Кэш устарел, обновляю...")
        manager.refresh_cache_from_api(organization_id)
    
    # Проверяем SKU
    exists = manager.is_sku_cached(vin, organization_id)
    stats = manager.get_cache_stats(organization_id)
    
    return {
        "vin": vin,
        "exists": exists,
        "organization_id": organization_id,
        "organization_name": stats["organization_name"],
        "cache_stats": stats,
        "recommendation": "create" if not exists else "update_item"
    }


if __name__ == "__main__":
    # Тест системы кэширования
    manager = SKUCacheManager()
    
    # Статистика кэша
    stats = manager.get_cache_stats()
    print(f"📊 Статистика кэша TaVie Europe:")
    print(f"   SKU: {stats['total_skus']}")
    print(f"   Обновлен: {stats['last_updated']}")
    print(f"   Свежий: {'✅' if stats['is_fresh'] else '❌'}")
    if stats['cache_age_hours']:
        print(f"   Возраст: {stats['cache_age_hours']} часов")
    
    # Тест проверки VIN
    test_vin = "W1V44781313926375"
    result = quick_sku_check(test_vin)
    print(f"\n🔍 Проверка VIN {test_vin}:")
    print(f"   Существует: {'❌ Да' if result['exists'] else '✅ Нет'}")
    print(f"   Рекомендация: {result['recommendation']}") 