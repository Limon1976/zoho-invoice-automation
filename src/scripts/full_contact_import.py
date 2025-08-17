#!/usr/bin/env python3
"""
Full Contact Import Script
==========================

Полный импорт контактов из Zoho Books с оптимизированным кэшированием
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Dict, Any, Optional

# Добавляем корневую папку в path
sys.path.append(str(Path(__file__).parent.parent.parent))

from src.domain.services.contact_cache import OptimizedContactCache
from src.domain.services.contact_sync import ContactSyncService, SyncConfig
from src.infrastructure.zoho_api import ZohoAPIClient
from src.infrastructure.config import get_config

# Логи настраиваются центрально; используем модульный логгер
logger = logging.getLogger(__name__)


class ContactImporter:
    """Класс для полного импорта контактов"""
    
    def __init__(self):
        self.config = get_config()
        self.setup_services()
        
        # Статистика импорта
        self.stats = {
            "start_time": datetime.now(),
            "organizations_processed": 0,
            "total_contacts_imported": 0,
            "total_api_calls": 0,
            "errors": []
        }
    
    def setup_services(self):
        """Настройка сервисов"""
        # Создаем папки
        Path("data").mkdir(exist_ok=True)
        Path("logs").mkdir(exist_ok=True)
        
        # Кэш контактов
        self.cache = OptimizedContactCache(Path("data/production_contact_cache.json"))
        
        # Zoho API клиент
        self.zoho_api = ZohoAPIClient(
            client_id=self.config.zoho.client_id,
            client_secret=self.config.zoho.client_secret,
            refresh_token=self.config.zoho.refresh_token or ""
        )
        
        # Конфигурация синхронизации
        sync_config = SyncConfig(
            webhook_enabled=True,
            webhook_url=f"http://{self.config.api.host}:{self.config.api.port}/api/contacts/webhook/zoho",
            sync_interval_hours=6,
            organizations={
                "20092948714": "TaVie Europe OÜ",
                "20082562863": "PARKENTERTAINMENT Sp. z o. o."
            }
        )
        
        # Сервис синхронизации
        self.sync_service = ContactSyncService(
            contact_cache=self.cache,
            zoho_api_client=self.zoho_api,
            config=sync_config
        )
    
    async def import_all_contacts(self, force_refresh: bool = False) -> bool:
        """
        Импорт всех контактов из всех организаций
        
        Args:
            force_refresh: Принудительно обновить кэш даже если он свежий
            
        Returns:
            True если импорт прошел успешно
        """
        try:
            logger.info("🚀 Начинаем полный импорт контактов из Zoho Books")
            
            # Проверяем текущий кэш
            current_stats = self.cache.get_cache_stats()
            logger.info(f"📊 Текущий кэш: {current_stats['total_contacts']} контактов")
            
            # Импортируем по организациям
            for org_id, org_name in self.sync_service.config.organizations.items():
                await self.import_organization_contacts(org_id, org_name, force_refresh)
            
            # Финальная статистика
            await self.print_final_stats()
            return True
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка импорта: {e}")
            self.stats["errors"].append(f"Critical error: {str(e)}")
            return False
    
    async def import_organization_contacts(self, org_id: str, org_name: str, force_refresh: bool):
        """Импорт контактов конкретной организации"""
        try:
            logger.info(f"\n🏢 Импорт контактов: {org_name} ({org_id})")
            
            # Проверяем нужно ли обновлять
            if not force_refresh and not self.cache.is_cache_stale(org_id, max_age_hours=24):
                logger.info(f"✅ Кэш для {org_name} свежий, пропускаем")
                return
            
            # Очищаем старый кэш организации
            old_count = self.cache.clear_org_cache(org_id)
            if old_count > 0:
                logger.info(f"🗑️ Очищен старый кэш: {old_count} контактов")
            
            # Получаем все контакты
            logger.info(f"📥 Загружаем контакты из Zoho API...")
            all_contacts = await self.fetch_all_contacts_optimized(org_id)
            
            if not all_contacts:
                logger.warning(f"⚠️ Не найдено контактов для {org_name}")
                return
            
            # Добавляем в кэш
            added_count = self.cache.add_contacts(all_contacts, org_id)
            
            # Обновляем статистику
            self.stats["organizations_processed"] += 1
            self.stats["total_contacts_imported"] += added_count
            
            logger.info(f"✅ {org_name}: {added_count} контактов импортировано")
            
        except Exception as e:
            logger.error(f"❌ Ошибка импорта {org_name}: {e}")
            self.stats["errors"].append(f"{org_name}: {str(e)}")
    
    async def fetch_all_contacts_optimized(self, org_id: str) -> list:
        """
        Оптимизированная загрузка всех контактов
        
        Стратегия:
        1. Получаем список всех контактов (минимум полей)
        2. Для каждого контакта получаем детальную информацию
        3. Используем паузы для соблюдения rate limit
        """
        all_contacts = []
        page = 1
        per_page = 200
        
        logger.info(f"📋 Получаем список контактов...")
        
        # Этап 1: Получаем список всех контактов
        contact_ids = []
        while True:
            try:
                response = await self.zoho_api.get_contacts(
                    organization_id=org_id,
                    page=page,
                    per_page=per_page
                )
                
                self.stats["total_api_calls"] += 1
                
                if not response or "contacts" not in response:
                    break
                
                contacts = response["contacts"]
                if not contacts:
                    break
                
                # Собираем только ID контактов
                for contact in contacts:
                    if contact.get("contact_id"):
                        contact_ids.append(contact["contact_id"])
                
                logger.info(f"   Страница {page}: {len(contacts)} контактов")
                
                # Проверяем есть ли еще страницы
                page_context = response.get("page_context", {})
                if not page_context.get("has_more_page", False):
                    break
                
                page += 1
                
                # Небольшая пауза между запросами списка
                await asyncio.sleep(0.2)
                
            except Exception as e:
                logger.error(f"❌ Ошибка получения списка контактов (страница {page}): {e}")
                break
        
        logger.info(f"📋 Найдено контактов: {len(contact_ids)}")
        
        # Этап 2: Получаем детальную информацию
        logger.info(f"🔍 Получаем детальную информацию...")
        
        for i, contact_id in enumerate(contact_ids, 1):
            try:
                details = await self.zoho_api.get_contact_details(org_id, contact_id)
                self.stats["total_api_calls"] += 1
                
                if details:
                    all_contacts.append(details)
                
                # Прогресс
                if i % 50 == 0:
                    logger.info(f"   Обработано: {i}/{len(contact_ids)} ({i/len(contact_ids)*100:.1f}%)")
                
                # Пауза для соблюдения rate limit (важно!)
                await asyncio.sleep(0.3)
                
            except Exception as e:
                logger.error(f"❌ Ошибка получения деталей контакта {contact_id}: {e}")
                self.stats["errors"].append(f"Contact {contact_id}: {str(e)}")
                continue
        
        logger.info(f"✅ Получено детальной информации: {len(all_contacts)} контактов")
        return all_contacts
    
    async def print_final_stats(self):
        """Печать финальной статистики"""
        duration = datetime.now() - self.stats["start_time"]
        
        logger.info("\n" + "="*60)
        logger.info("📊 ИТОГОВАЯ СТАТИСТИКА ИМПОРТА")
        logger.info("="*60)
        logger.info(f"⏱️  Время выполнения: {duration}")
        logger.info(f"🏢 Организаций обработано: {self.stats['organizations_processed']}")
        logger.info(f"👥 Всего контактов импортировано: {self.stats['total_contacts_imported']}")
        logger.info(f"🔌 Всего API запросов: {self.stats['total_api_calls']}")
        
        if self.stats["errors"]:
            logger.warning(f"⚠️  Ошибки: {len(self.stats['errors'])}")
            for error in self.stats["errors"][:5]:  # Показываем первые 5
                logger.warning(f"   - {error}")
            if len(self.stats["errors"]) > 5:
                logger.warning(f"   ... и еще {len(self.stats['errors']) - 5} ошибок")
        
        # Финальная статистика кэша
        final_stats = self.cache.get_cache_stats()
        logger.info(f"\n💾 ФИНАЛЬНЫЙ КЭША:")
        logger.info(f"   Всего контактов: {final_stats['total_contacts']}")
        logger.info(f"   Организаций: {final_stats['organizations']}")
        logger.info(f"   Контактов с VAT: {final_stats['contacts_with_vat']}")
        
        for org_stat_key, org_stat_value in final_stats.items():
            if org_stat_key.startswith("org_"):
                org_id = org_stat_key.replace("org_", "")
                org_name = self.sync_service.config.organizations.get(org_id, org_id)
                logger.info(f"   {org_name}: {org_stat_value}")
        
        logger.info("="*60)


async def main():
    """Главная функция"""
    print("🚀 ПОЛНЫЙ ИМПОРТ КОНТАКТОВ ИЗ ZOHO BOOKS")
    print("="*50)
    
    # Создаем импортер
    importer = ContactImporter()
    
    # Спрашиваем у пользователя
    force = input("Принудительно обновить кэш? (y/N): ").lower() == 'y'
    
    print(f"\n📥 Начинаем импорт (force_refresh={force})...")
    
    # Запускаем импорт
    success = await importer.import_all_contacts(force_refresh=force)
    
    if success:
        print("\n✅ Импорт завершен успешно!")
        print("💡 Теперь можно запускать основное приложение")
    else:
        print("\n❌ Импорт завершен с ошибками!")
        print("🔍 Проверьте логи для подробностей")


if __name__ == "__main__":
    asyncio.run(main()) 