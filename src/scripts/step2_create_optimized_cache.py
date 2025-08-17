#!/usr/bin/env python3
"""
Этап 2: Создание оптимизированного кэша из полных данных
=======================================================

Читает полные данные контактов из файлов data/full_contacts/ и создает
оптимизированные кэши для быстрого поиска (только 10 нужных полей).

Результат:
- data/optimized_cache/all_contacts_optimized.json (общий кэш для поиска)
- data/optimized_cache/TaVie_Europe_optimized.json (кэш по организации)
- data/optimized_cache/PARKENTERTAINMENT_optimized.json (кэш по организации)
"""

import asyncio
import logging
import json
import time
from datetime import datetime
from pathlib import Path
import sys
from typing import Dict, List, Optional

# Добавляем корневую папку в path
sys.path.append(str(Path(__file__).parent.parent.parent))

from src.domain.services.contact_cache import OptimizedContactCache

# Логи настраиваются центрально; используем модульный логгер
logger = logging.getLogger(__name__)


class OptimizedCacheCreator:
    """Класс для создания оптимизированных кэшей из полных данных"""
    
    def __init__(self):
        self.setup_organizations()
        
        # Статистика создания кэшей
        self.stats = {
            "start_time": datetime.now(),
            "organizations": {},
            "total_contacts": 0,
            "caches_created": 0,
            "errors": []
        }
    
    def setup_organizations(self):
        """Настройка организаций для обработки"""
        self.organizations = {
            "20092948714": {
                "name": "TaVie Europe OÜ",
                "full_data_file": "data/full_contacts/TaVie_Europe_20092948714_full.json",
                "cache_file": "data/optimized_cache/TaVie_Europe_optimized.json"
            },
            "20082562863": {
                "name": "PARKENTERTAINMENT Sp. z o. o.",
                "full_data_file": "data/full_contacts/PARKENTERTAINMENT_20082562863_full.json",
                "cache_file": "data/optimized_cache/PARKENTERTAINMENT_optimized.json"
            }
        }
        
        logger.info(f"📊 Настроены организации:")
        for org_id, org_info in self.organizations.items():
            logger.info(f"   {org_id}: {org_info['name']}")
    
    def load_full_contacts(self, org_id: str, org_info: dict) -> Optional[List[dict]]:
        """Загрузка полных данных контактов из файла"""
        try:
            file_path = Path(org_info["full_data_file"])
            
            if not file_path.exists():
                logger.error(f"❌ Файл не найден: {file_path}")
                return None
            
            with open(file_path, 'r', encoding='utf-8') as f:
                contacts = json.load(f)
            
            file_size = file_path.stat().st_size
            logger.info(f"📂 Загружено {len(contacts)} контактов из {file_path} ({file_size:,} байт)")
            
            return contacts
            
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки файла {org_info['full_data_file']}: {e}")
            self.stats["errors"].append(f"Load {org_id}: {str(e)}")
            return None
    
    def create_organization_cache(self, org_id: str, org_info: dict) -> bool:
        """Создание оптимизированного кэша для одной организации"""
        logger.info(f"🔄 Создание кэша для {org_info['name']} ({org_id})")
        
        try:
            # Загружаем полные данные
            contacts = self.load_full_contacts(org_id, org_info)
            
            if not contacts:
                return False
            
            # Создаем оптимизированный кэш
            cache = OptimizedContactCache(org_info["cache_file"])
            
            # Добавляем контакты в кэш
            cache.add_contacts(contacts)
            
            # Сохраняем кэш
            cache.save_cache()
            
            # Получаем статистику кэша
            stats = cache.get_statistics()
            
            logger.info(f"✅ Кэш создан для {org_info['name']}:")
            logger.info(f"   📊 Всего контактов: {stats['total_contacts']}")
            logger.info(f"   🏷️ С VAT номерами: {stats['contacts_with_vat']}")
            logger.info(f"   👤 Покупателей: {stats['customers']}")
            logger.info(f"   🏢 Поставщиков: {stats['vendors']}")
            logger.info(f"   💾 Размер кэша: {stats['cache_file_size']:,} байт")
            
            # Сохраняем статистику
            self.stats["organizations"][org_id] = {
                "name": org_info["name"],
                "cache_file": org_info["cache_file"],
                "total": stats['total_contacts'],
                "customers": stats['customers'],
                "vendors": stats['vendors'],
                "with_vat": stats['contacts_with_vat'],
                "cache_size": stats['cache_file_size']
            }
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания кэша для {org_info['name']}: {e}")
            self.stats["errors"].append(f"Cache {org_id}: {str(e)}")
            return False
    
    def create_combined_cache(self) -> bool:
        """Создание объединенного кэша для всех организаций"""
        logger.info("🔄 Создание объединенного кэша для всех организаций")
        
        try:
            all_contacts = []
            
            # Загружаем контакты из всех организаций
            for org_id, org_info in self.organizations.items():
                contacts = self.load_full_contacts(org_id, org_info)
                if contacts:
                    all_contacts.extend(contacts)
            
            if not all_contacts:
                logger.error("❌ Нет данных для создания объединенного кэша")
                return False
            
            # Создаем папку optimized_cache если её нет
            cache_dir = Path("data/optimized_cache")
            cache_dir.mkdir(parents=True, exist_ok=True)
            
            # Создаем объединенный кэш
            combined_cache_file = "data/optimized_cache/all_contacts_optimized.json"
            cache = OptimizedContactCache(combined_cache_file)
            
            # Добавляем все контакты в кэш
            cache.add_contacts(all_contacts)
            
            # Сохраняем кэш
            cache.save_cache()
            
            # Получаем статистику кэша
            stats = cache.get_statistics()
            
            logger.info(f"✅ Объединенный кэш создан:")
            logger.info(f"   📊 Всего контактов: {stats['total_contacts']}")
            logger.info(f"   🏷️ С VAT номерами: {stats['contacts_with_vat']}")
            logger.info(f"   👤 Покупателей: {stats['customers']}")
            logger.info(f"   🏢 Поставщиков: {stats['vendors']}")
            logger.info(f"   💾 Размер кэша: {stats['cache_file_size']:,} байт")
            logger.info(f"   📄 Файл: {combined_cache_file}")
            
            # Сохраняем статистику объединенного кэша
            self.stats["combined_cache"] = {
                "file": combined_cache_file,
                "total": stats['total_contacts'],
                "customers": stats['customers'],
                "vendors": stats['vendors'],
                "with_vat": stats['contacts_with_vat'],
                "cache_size": stats['cache_file_size']
            }
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания объединенного кэша: {e}")
            self.stats["errors"].append(f"Combined cache: {str(e)}")
            return False
    
    def create_all_caches(self) -> bool:
        """Создание всех кэшей"""
        logger.info("🚀 Начинаем создание оптимизированных кэшей")
        
        success_count = 0
        
        # Создаем кэши для каждой организации
        for org_id, org_info in self.organizations.items():
            success = self.create_organization_cache(org_id, org_info)
            if success:
                success_count += 1
                self.stats["caches_created"] += 1
        
        # Создаем объединенный кэш
        combined_success = self.create_combined_cache()
        if combined_success:
            self.stats["caches_created"] += 1
        
        # Подсчитываем общее количество контактов
        self.stats["total_contacts"] = sum(
            org_stats["total"] for org_stats in self.stats["organizations"].values()
        )
        
        # Выводим финальную статистику
        self.print_final_statistics()
        
        return success_count == len(self.organizations) and combined_success
    
    def print_final_statistics(self) -> None:
        """Вывод финальной статистики"""
        end_time = datetime.now()
        duration = end_time - self.stats["start_time"]
        
        logger.info("="*60)
        logger.info("📊 ФИНАЛЬНАЯ СТАТИСТИКА СОЗДАНИЯ КЭШЕЙ")
        logger.info("="*60)
        
        logger.info(f"⏱️ Время выполнения: {duration}")
        logger.info(f"👥 Всего контактов: {self.stats['total_contacts']}")
        logger.info(f"🔄 Кэшей создано: {self.stats['caches_created']}")
        logger.info(f"🏢 Организаций обработано: {len(self.stats['organizations'])}")
        
        # Статистика по организациям
        logger.info(f"\n📈 Кэши по организациям:")
        for org_id, org_stats in self.stats["organizations"].items():
            logger.info(f"   {org_stats['name']} ({org_id}):")
            logger.info(f"      📄 Файл: {org_stats['cache_file']}")
            logger.info(f"      👥 Всего: {org_stats['total']}")
            logger.info(f"      👤 Покупателей: {org_stats['customers']}")
            logger.info(f"      🏢 Поставщиков: {org_stats['vendors']}")
            logger.info(f"      🏷️ С VAT: {org_stats['with_vat']}")
            logger.info(f"      💾 Размер: {org_stats['cache_size']:,} байт")
        
        # Статистика объединенного кэша
        if "combined_cache" in self.stats:
            combined = self.stats["combined_cache"]
            logger.info(f"\n📈 Объединенный кэш:")
            logger.info(f"   📄 Файл: {combined['file']}")
            logger.info(f"   👥 Всего: {combined['total']}")
            logger.info(f"   👤 Покупателей: {combined['customers']}")
            logger.info(f"   🏢 Поставщиков: {combined['vendors']}")
            logger.info(f"   🏷️ С VAT: {combined['with_vat']}")
            logger.info(f"   💾 Размер: {combined['cache_size']:,} байт")
        
        if self.stats["errors"]:
            logger.warning(f"\n⚠️ Ошибки ({len(self.stats['errors'])}):")
            for error in self.stats["errors"]:
                logger.warning(f"   • {error}")
        
        logger.info("="*60)
        logger.info("🎯 РЕЗУЛЬТАТ ЭТАПА 2:")
        logger.info("📂 data/optimized_cache/ - кэши для быстрого поиска")
        logger.info("🔍 all_contacts_optimized.json - главный кэш для поиска")
        logger.info("✅ Система готова к использованию!")
        logger.info("="*60)
    
    def demonstrate_cache_usage(self) -> None:
        """Демонстрация использования кэша"""
        logger.info("🔍 Демонстрация использования кэша:")
        
        try:
            # Загружаем объединенный кэш
            cache = OptimizedContactCache("data/optimized_cache/all_contacts_optimized.json")
            
            # Получаем статистику
            stats = cache.get_statistics()
            logger.info(f"   📊 Загружен кэш: {stats['total_contacts']} контактов")
            
            # Примеры поиска
            logger.info("   🔍 Примеры поиска:")
            
            # Поиск контактов с VAT номерами
            vat_contacts = cache.get_contacts_with_vat()
            logger.info(f"      • Контакты с VAT: {len(vat_contacts)}")
            
            # Поиск покупателей
            customers = cache.get_contacts_by_type('customer')
            logger.info(f"      • Покупатели: {len(customers)}")
            
            # Поиск поставщиков
            vendors = cache.get_contacts_by_type('vendor')
            logger.info(f"      • Поставщики: {len(vendors)}")
            
            # Пример поиска по VAT (если есть контакты с VAT)
            if vat_contacts:
                example_vat = vat_contacts[0].vat_number
                if example_vat:
                    found_contact = cache.search_by_vat(example_vat)
                    if found_contact:
                        logger.info(f"      • Поиск по VAT '{example_vat}': {found_contact.company_name}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка демонстрации: {e}")


def main():
    """Главная функция"""
    print("🚀 ЭТАП 2: СОЗДАНИЕ ОПТИМИЗИРОВАННЫХ КЭШЕЙ")
    print("="*60)
    
    # Создаем создатель кэшей
    creator = OptimizedCacheCreator()
    
    # Проверяем наличие полных данных
    print("📊 Проверка исходных данных:")
    missing_files = []
    
    for org_id, org_info in creator.organizations.items():
        file_path = Path(org_info["full_data_file"])
        if file_path.exists():
            file_size = file_path.stat().st_size
            print(f"   ✅ {org_info['name']}: {file_path} ({file_size:,} байт)")
        else:
            print(f"   ❌ {org_info['name']}: {file_path} - НЕ НАЙДЕН")
            missing_files.append(file_path)
    
    if missing_files:
        print(f"\n❌ Отсутствуют файлы с полными данными:")
        for file_path in missing_files:
            print(f"   • {file_path}")
        print("➡️ Сначала запустите: python src/scripts/step1_download_full_contacts.py")
        return
    
    # Подтверждение
    print("\n💡 Будет создано:")
    print("   📂 data/optimized_cache/ - кэши для быстрого поиска")
    print("   🔍 all_contacts_optimized.json - главный кэш (объединенный)")
    print("   📄 Отдельные кэши для каждой организации")
    
    confirm = input("\nСоздать кэши? (y/N): ").lower()
    if confirm != 'y':
        print("❌ Создание кэшей отменено")
        return
    
    print(f"\n🔄 Начинаем создание кэшей...")
    
    # Запускаем создание кэшей
    success = creator.create_all_caches()
    
    if success:
        print("\n✅ Этап 2 завершен успешно!")
        print("📂 Кэши сохранены в data/optimized_cache/")
        print("🔍 Главный кэш: data/optimized_cache/all_contacts_optimized.json")
        
        # Демонстрируем использование
        creator.demonstrate_cache_usage()
        
        print("\n🎉 Система готова к использованию!")
    else:
        print("\n❌ Этап 2 завершен с ошибками!")
        print("🔍 Проверьте логи для подробностей")


if __name__ == "__main__":
    main() 