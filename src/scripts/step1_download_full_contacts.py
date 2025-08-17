#!/usr/bin/env python3
"""
Этап 1: Скачивание полных данных контактов по организациям
==========================================================

Скачивает все контакты из каждой организации Zoho Books и сохраняет их
в отдельные файлы с полными данными (все 114 полей).

Результат:
- data/full_contacts/TaVie_Europe_20092948714_full.json
- data/full_contacts/PARKENTERTAINMENT_20082562863_full.json
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

from src.infrastructure.zoho_api import ZohoAPIClient
from src.infrastructure.config import get_config

# Логи настраиваются центрально; используем модульный логгер
logger = logging.getLogger(__name__)


class FullContactsDownloader:
    """Класс для скачивания полных данных контактов по организациям"""
    
    def __init__(self):
        self.config = get_config()
        self.setup_organizations()
        
        # Статистика загрузки
        self.stats = {
            "start_time": datetime.now(),
            "organizations": {},
            "total_contacts": 0,
            "total_api_calls": 0,
            "errors": []
        }
    
    def setup_organizations(self):
        """Настройка организаций для скачивания"""
        self.organizations = {
            "20092948714": {
                "name": "TaVie Europe OÜ",
                "file_name": "TaVie_Europe_20092948714_full.json",
                "client_id": self.config.zoho.client_id,
                "client_secret": self.config.zoho.client_secret,
                "refresh_token": self.config.zoho.refresh_token or ""
            },
            "20082562863": {
                "name": "PARKENTERTAINMENT Sp. z o. o.",
                "file_name": "PARKENTERTAINMENT_20082562863_full.json",
                "client_id": self.config.zoho.client_id,
                "client_secret": self.config.zoho.client_secret,
                "refresh_token": self.config.zoho.refresh_token or ""
            }
        }
        
        logger.info(f"📊 Настроены организации:")
        for org_id, org_info in self.organizations.items():
            logger.info(f"   {org_id}: {org_info['name']}")
    
    async def download_contacts_from_organization(self, org_id: str, org_info: dict) -> bool:
        """Скачивание контактов из одной организации"""
        logger.info(f"📥 Скачивание контактов из {org_info['name']} ({org_id})")
        
        # Создаем API клиент
        api_client = ZohoAPIClient(
            client_id=org_info["client_id"],
            client_secret=org_info["client_secret"],
            refresh_token=org_info["refresh_token"]
        )
        
        try:
            # Получаем список всех контактов (базовая информация)
            logger.info("📋 Получение списка контактов...")
            contacts_response = await api_client.get_contacts(org_id)
            contacts_list = contacts_response.get("contacts", []) if contacts_response else []
            
            if not contacts_list:
                logger.warning(f"⚠️ Нет контактов в организации {org_info['name']}")
                return False
            
            logger.info(f"📊 Найдено {len(contacts_list)} контактов")
            self.stats["total_api_calls"] += 1
            
            # Получаем детальную информацию для каждого контакта
            detailed_contacts = []
            
            for i, contact in enumerate(contacts_list, 1):
                contact_id = contact.get("contact_id")
                
                if not contact_id:
                    logger.warning(f"⚠️ Контакт без ID: {contact}")
                    continue
                
                try:
                    # Получаем детальную информацию (все 114 полей)
                    detailed_contact = await api_client.get_contact_details(org_id, contact_id)
                    
                    if detailed_contact:
                        # Добавляем organization_id к каждому контакту
                        detailed_contact["organization_id"] = org_id
                        detailed_contacts.append(detailed_contact)
                        
                        # Логируем прогресс каждые 50 контактов
                        if i % 50 == 0:
                            logger.info(f"📊 Обработано {i}/{len(contacts_list)} контактов")
                    
                    self.stats["total_api_calls"] += 1
                    
                    # Задержка для соблюдения rate limits
                    await asyncio.sleep(0.3)
                    
                except Exception as e:
                    logger.error(f"❌ Ошибка получения деталей контакта {contact_id}: {e}")
                    self.stats["errors"].append(f"Contact {contact_id}: {str(e)}")
                    continue
            
            # Сохраняем полные данные в файл
            success = await self.save_full_contacts(org_id, org_info, detailed_contacts)
            
            if success:
                logger.info(f"✅ Скачивание завершено: {len(detailed_contacts)} контактов из {org_info['name']}")
                
                # Статистика по организации
                customers = [c for c in detailed_contacts if c.get("contact_type") == "customer"]
                vendors = [c for c in detailed_contacts if c.get("contact_type") == "vendor"]
                with_vat = [c for c in detailed_contacts if c.get("cf_vat_id")]
                
                self.stats["organizations"][org_id] = {
                    "name": org_info["name"],
                    "file_name": org_info["file_name"],
                    "total": len(detailed_contacts),
                    "customers": len(customers),
                    "vendors": len(vendors),
                    "with_vat": len(with_vat)
                }
                
                return True
            else:
                return False
                
        except Exception as e:
            logger.error(f"❌ Критическая ошибка скачивания из {org_info['name']}: {e}")
            self.stats["errors"].append(f"Organization {org_id}: {str(e)}")
            return False
    
    async def save_full_contacts(self, org_id: str, org_info: dict, contacts: List[dict]) -> bool:
        """Сохранение полных данных контактов в файл"""
        try:
            # Создаем папку full_contacts если её нет
            full_contacts_dir = Path("data/full_contacts")
            full_contacts_dir.mkdir(parents=True, exist_ok=True)
            
            # Путь к файлу
            file_path = full_contacts_dir / org_info["file_name"]
            
            # Сохраняем данные
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(contacts, f, ensure_ascii=False, indent=2)
            
            file_size = file_path.stat().st_size
            logger.info(f"💾 Сохранено в {file_path} ({file_size:,} байт)")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения файла для {org_info['name']}: {e}")
            self.stats["errors"].append(f"Save {org_id}: {str(e)}")
            return False
    
    async def download_all_organizations(self) -> bool:
        """Скачивание контактов из всех организаций"""
        logger.info("🚀 Начинаем скачивание полных данных контактов")
        
        success_count = 0
        
        # Скачиваем из каждой организации
        for org_id, org_info in self.organizations.items():
            success = await self.download_contacts_from_organization(org_id, org_info)
            if success:
                success_count += 1
        
        # Подсчитываем общее количество контактов
        self.stats["total_contacts"] = sum(
            org_stats["total"] for org_stats in self.stats["organizations"].values()
        )
        
        # Выводим финальную статистику
        self.print_final_statistics()
        
        return success_count == len(self.organizations)
    
    def print_final_statistics(self) -> None:
        """Вывод финальной статистики"""
        end_time = datetime.now()
        duration = end_time - self.stats["start_time"]
        
        logger.info("="*60)
        logger.info("📊 ФИНАЛЬНАЯ СТАТИСТИКА СКАЧИВАНИЯ")
        logger.info("="*60)
        
        logger.info(f"⏱️ Время выполнения: {duration}")
        logger.info(f"📞 Всего API запросов: {self.stats['total_api_calls']}")
        logger.info(f"👥 Всего контактов: {self.stats['total_contacts']}")
        logger.info(f"🏢 Организаций обработано: {len(self.stats['organizations'])}")
        
        logger.info(f"\n📈 Статистика по организациям:")
        for org_id, org_stats in self.stats["organizations"].items():
            logger.info(f"   {org_stats['name']} ({org_id}):")
            logger.info(f"      📄 Файл: {org_stats['file_name']}")
            logger.info(f"      👥 Всего: {org_stats['total']}")
            logger.info(f"      👤 Покупателей: {org_stats['customers']}")
            logger.info(f"      🏢 Поставщиков: {org_stats['vendors']}")
            logger.info(f"      🏷️ С VAT: {org_stats['with_vat']}")
        
        if self.stats["errors"]:
            logger.warning(f"\n⚠️ Ошибки ({len(self.stats['errors'])}):")
            for error in self.stats["errors"][:5]:  # Показываем первые 5 ошибок
                logger.warning(f"   • {error}")
            if len(self.stats["errors"]) > 5:
                logger.warning(f"   ... и еще {len(self.stats['errors']) - 5} ошибок")
        
        logger.info("="*60)
        logger.info("🎯 РЕЗУЛЬТАТ ЭТАПА 1:")
        logger.info("📂 data/full_contacts/ - полные данные по организациям")
        logger.info("➡️ Следующий этап: python src/scripts/step2_create_optimized_cache.py")
        logger.info("="*60)


async def main():
    """Главная функция"""
    print("🚀 ЭТАП 1: СКАЧИВАНИЕ ПОЛНЫХ ДАННЫХ КОНТАКТОВ")
    print("="*60)
    
    # Создаем загрузчик
    downloader = FullContactsDownloader()
    
    # Подтверждение
    print("📊 Будет выполнено скачивание из:")
    for org_id, org_info in downloader.organizations.items():
        print(f"   • {org_info['name']} ({org_id})")
        print(f"     📄 Файл: data/full_contacts/{org_info['file_name']}")
    
    print("\n💡 Будет создано:")
    print("   📂 data/full_contacts/ - полные данные (все 114 полей)")
    print("   📝 Отдельный файл для каждой организации")
    
    confirm = input("\nНачать скачивание? (y/N): ").lower()
    if confirm != 'y':
        print("❌ Скачивание отменено")
        return
    
    print(f"\n📥 Начинаем скачивание полных данных...")
    
    # Запускаем скачивание
    success = await downloader.download_all_organizations()
    
    if success:
        print("\n✅ Этап 1 завершен успешно!")
        print("📂 Полные данные сохранены в data/full_contacts/")
        print("➡️ Следующий шаг: python src/scripts/step2_create_optimized_cache.py")
    else:
        print("\n❌ Этап 1 завершен с ошибками!")
        print("🔍 Проверьте логи для подробностей")


if __name__ == "__main__":
    asyncio.run(main()) 