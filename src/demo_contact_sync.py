"""
Демонстрация системы кэширования и синхронизации контактов
=========================================================

Пример использования ContactCache и ContactSyncService для:
- Кэширования контактов из Zoho Books
- Поиска контактов по VAT и названию компании
- Автоматической синхронизации новых контактов
"""

import asyncio
import os
from pathlib import Path
from datetime import datetime

# Добавляем путь к проекту
import sys
sys.path.append(str(Path(__file__).parent.parent))

from src.domain.services.contact_cache import ContactCache, ContactCacheEntry
from src.domain.services.contact_sync import ContactSyncService, SyncConfig


def demo_contact_cache():
    """Демонстрация работы с кэшем контактов"""
    print("🔍 ДЕМОНСТРАЦИЯ КЭША КОНТАКТОВ")
    print("=" * 50)
    
    # Создаем кэш
    cache = ContactCache(Path("data/demo_contact_cache.json"))
    
    # Тестовые данные контактов (имитируем данные из Zoho)
    test_contacts = [
        {
            "contact_id": "445379000000107171",
            "contact_name": "CAR BEST SALLER Sp. z o. o.",
            "company_name": "CAR BEST SALLER Sp. z o. o.",
            "contact_type": "vendor",
            "custom_fields": [
                {"api_name": "cf_vat_id", "value": "PL9512495127"}
            ],
            "contact_persons": [
                {
                    "is_primary_contact": True,
                    "email": "office@carbestsaller.pl",
                    "phone": "+48 123 456 789"
                }
            ],
            "last_modified_time": "2024-01-15T10:30:00+0200"
        },
        {
            "contact_id": "445379000000107172",
            "contact_name": "TaVie Europe OÜ",
            "company_name": "TaVie Europe OÜ",
            "contact_type": "customer",
            "custom_fields": [
                {"api_name": "cf_vat_id", "value": "EE102288270"}
            ],
            "contact_persons": [
                {
                    "is_primary_contact": True,
                    "email": "info@tavie.eu",
                    "phone": "+372 123 4567"
                }
            ],
            "last_modified_time": "2024-01-15T09:15:00+0200"
        },
        {
            "contact_id": "445379000000107173",
            "contact_name": "PARKENTERTAINMENT Sp. z o. o.",
            "company_name": "PARKENTERTAINMENT Sp. z o. o.",
            "contact_type": "customer",
            "custom_fields": [
                {"api_name": "cf_vat_id", "value": "PL5272956146"}
            ],
            "contact_persons": [
                {
                    "is_primary_contact": True,
                    "email": "office@parkentertainment.pl",
                    "phone": "+48 987 654 321"
                }
            ],
            "last_modified_time": "2024-01-15T11:45:00+0200"
        }
    ]
    
    # Добавляем контакты в кэш
    org_id = "20082562863"  # TaVie Europe OÜ
    added_count = cache.add_contacts(test_contacts, org_id)
    print(f"✅ Добавлено {added_count} контактов в кэш")
    
    # Демонстрация поиска
    print("\n🔍 ТЕСТИРОВАНИЕ ПОИСКА КОНТАКТОВ:")
    print("-" * 40)
    
    # 1. Поиск по точному VAT номеру (приоритет)
    print("\n1️⃣ Поиск по VAT номеру: PL9512495127")
    result = cache.find_contact(vat_number="PL9512495127")
    if result:
        print(f"   ✅ Найден: {result.contact.contact_name}")
        print(f"   📊 Тип совпадения: {result.match_type}")
        print(f"   🎯 Уверенность: {result.confidence:.2f}")
    else:
        print("   ❌ Не найден")
    
    # 2. Поиск по названию компании (точное совпадение)
    print("\n2️⃣ Поиск по названию: TaVie Europe OÜ")
    result = cache.find_contact(company_name="TaVie Europe OÜ")
    if result:
        print(f"   ✅ Найден: {result.contact.contact_name}")
        print(f"   📊 Тип совпадения: {result.match_type}")
        print(f"   🎯 Уверенность: {result.confidence:.2f}")
    
    # 3. Нечеткий поиск по названию
    print("\n3️⃣ Нечеткий поиск: Car Best Seller")
    result = cache.find_contact(company_name="Car Best Seller", min_confidence=0.6)
    if result:
        print(f"   ✅ Найден: {result.contact.contact_name}")
        print(f"   📊 Тип совпадения: {result.match_type}")
        print(f"   🎯 Уверенность: {result.confidence:.2f}")
    
    # 4. Поиск по email
    print("\n4️⃣ Поиск по email: info@tavie.eu")
    result = cache.find_contact(email="info@tavie.eu")
    if result:
        print(f"   ✅ Найден: {result.contact.contact_name}")
        print(f"   📊 Тип совпадения: {result.match_type}")
        print(f"   🎯 Уверенность: {result.confidence:.2f}")
    
    # 5. Поиск несуществующего контакта
    print("\n5️⃣ Поиск несуществующего: Random Company Ltd")
    result = cache.find_contact(company_name="Random Company Ltd")
    if result:
        print(f"   ✅ Найден: {result.contact.contact_name}")
    else:
        print("   ❌ Не найден (ожидаемо)")
    
    # Статистика кэша
    print("\n📊 СТАТИСТИКА КЭША:")
    print("-" * 30)
    stats = cache.get_cache_stats()
    print(f"   Всего контактов: {stats['total_contacts']}")
    print(f"   Контактов с VAT: {stats['contacts_with_vat']}")
    print(f"   Организаций: {stats['organizations']}")
    
    for key, value in stats.items():
        if key.startswith("org_"):
            org_stats = value
            print(f"   Организация {key[4:]}:")
            print(f"     - Всего: {org_stats['total']}")
            print(f"     - Клиенты: {org_stats['customers']}")
            print(f"     - Поставщики: {org_stats['vendors']}")
            print(f"     - С VAT: {org_stats['with_vat']}")
    
    return cache


def demo_document_matching(cache: ContactCache):
    """Демонстрация сопоставления контактов с документами"""
    print("\n\n📄 ДЕМОНСТРАЦИЯ СОПОСТАВЛЕНИЯ С ДОКУМЕНТАМИ")
    print("=" * 55)
    
    # Имитируем данные поставщика из входящего документа
    test_documents = [
        {
            "name": "Входящий счет с точным VAT",
            "supplier": {
                "name": "CAR BEST SALLER Sp. z o. o.",
                "vat": "PL9512495127",
                "address": "Warsaw, Poland"
            }
        },
        {
            "name": "Входящий счет с похожим названием",
            "supplier": {
                "name": "Car Best Seller",  # Слегка другое написание
                "vat": "",  # Нет VAT
                "address": "Poland"
            }
        },
        {
            "name": "Счет от нашей компании",
            "supplier": {
                "name": "TaVie Europe OU",  # Слегка другое написание
                "vat": "EE102288270",
                "email": "info@tavie.eu"
            }
        },
        {
            "name": "Новый поставщик",
            "supplier": {
                "name": "Unknown Supplier Ltd",
                "vat": "GB123456789",
                "address": "London, UK"
            }
        }
    ]
    
    for i, doc in enumerate(test_documents, 1):
        print(f"\n{i}️⃣ {doc['name']}")
        print(f"   Поставщик: {doc['supplier']['name']}")
        print(f"   VAT: {doc['supplier']['vat'] or 'Не указан'}")
        
        # Ищем контакт
        result = cache.find_contact(
            vat_number=doc['supplier']['vat'],
            company_name=doc['supplier']['name'],
            email=doc['supplier'].get('email'),
            min_confidence=0.7
        )
        
        if result:
            print(f"   ✅ НАЙДЕН: {result.contact.contact_name}")
            print(f"   📊 Совпадение: {result.match_type}")
            print(f"   🎯 Уверенность: {result.confidence:.2f}")
            print(f"   🏢 Тип: {result.contact.contact_type}")
            if result.contact.vat_number:
                print(f"   🆔 VAT в базе: {result.contact.vat_number}")
        else:
            print("   ❌ НЕ НАЙДЕН - требуется создание нового контакта")


async def demo_sync_service():
    """Демонстрация сервиса синхронизации"""
    print("\n\n🔄 ДЕМОНСТРАЦИЯ СЕРВИСА СИНХРОНИЗАЦИИ")
    print("=" * 50)
    
    # Создаем кэш и конфигурацию
    cache = ContactCache(Path("data/demo_sync_cache.json"))
    
    config = SyncConfig(
        webhook_enabled=True,
        sync_interval_hours=6,
        organizations={
            "20092948714": "TaVie Europe OÜ",
            "20082562863": "PARKENTERTAINMENT Sp. z o. o."
        }
    )
    
    # Мок Zoho API клиента (в реальности это будет настоящий клиент)
    class MockZohoAPI:
        async def get_contacts(self, organization_id, page=1, per_page=200):
            # Имитируем ответ API
            return {
                "contacts": [
                    {"contact_id": "test_001", "contact_name": "Test Contact 1"},
                    {"contact_id": "test_002", "contact_name": "Test Contact 2"}
                ],
                "page_context": {"has_more_page": False}
            }
        
        async def get_contact_details(self, organization_id, contact_id):
            # Имитируем детальную информацию
            return {
                "contact_id": contact_id,
                "contact_name": f"Detailed Contact {contact_id}",
                "company_name": f"Company {contact_id}",
                "contact_type": "vendor",
                "custom_fields": [
                    {"api_name": "cf_vat_id", "value": f"VAT{contact_id}"}
                ]
            }
        
        async def create_contact(self, contact_data, organization_id):
            # Имитируем создание контакта
            new_contact_id = f"new_{datetime.now().strftime('%H%M%S')}"
            return {
                "contact": {
                    "contact_id": new_contact_id,
                    **contact_data
                }
            }
    
    # Создаем сервис синхронизации
    sync_service = ContactSyncService(
        contact_cache=cache,
        zoho_api_client=MockZohoAPI(),
        config=config
    )
    
    print("📋 Конфигурация синхронизации:")
    print(f"   Webhook включен: {config.webhook_enabled}")
    print(f"   Интервал синхронизации: {config.sync_interval_hours} часов")
    print(f"   Организаций: {len(config.organizations)}")
    
    # Демонстрация полной синхронизации
    print("\n🔄 Запуск полной синхронизации...")
    results = await sync_service.sync_all_organizations()
    
    for org_id, result in results.items():
        org_name = config.organizations[org_id]
        print(f"\n📊 Результаты для {org_name}:")
        print(f"   ✅ Успешно: {result.success}")
        print(f"   📥 Обработано: {result.contacts_processed}")
        print(f"   ➕ Создано/обновлено: {result.contacts_created}")
        print(f"   ⏱️ Время: {result.duration_seconds:.1f}с")
        if result.errors:
            print(f"   ❌ Ошибки: {', '.join(result.errors)}")
    
    # Демонстрация поиска контакта для документа
    print("\n🔍 Поиск контакта для документа...")
    supplier_data = {
        "name": "Test Supplier Ltd",
        "vat": "VATtest_001",
        "email": "test@supplier.com"
    }
    
    match_result = sync_service.find_contact_for_document(supplier_data, "20082562863")
    if match_result:
        print(f"   ✅ Найден контакт: {match_result.contact.contact_name}")
        print(f"   🎯 Уверенность: {match_result.confidence:.2f}")
    else:
        print("   ❌ Контакт не найден")
        
        # Демонстрация автоматического создания
        print("\n➕ Автоматическое создание контакта...")
        new_contact_id = await sync_service.auto_create_contact_from_document(
            supplier_data, "20082562863"
        )
        if new_contact_id:
            print(f"   ✅ Создан новый контакт: {new_contact_id}")
        else:
            print("   ❌ Ошибка создания контакта")
    
    # Статистика синхронизации
    print("\n📊 Статистика синхронизации:")
    stats = sync_service.get_sync_statistics()
    print(f"   Всего контактов в кэше: {stats['total_contacts']}")
    print(f"   Размер очереди событий: {stats['queue_size']}")
    print(f"   Webhook включен: {stats['sync_config']['webhook_enabled']}")


def main():
    """Главная функция демонстрации"""
    print("🚀 ДЕМОНСТРАЦИЯ СИСТЕМЫ КЭШИРОВАНИЯ И СИНХРОНИЗАЦИИ КОНТАКТОВ")
    print("=" * 70)
    print("Эта система решает следующие задачи:")
    print("✅ Кэширование 500+ контактов с 119 полями")
    print("✅ Быстрый поиск по VAT номеру (приоритет)")
    print("✅ Нечеткий поиск по названию компании")
    print("✅ Автоматическая синхронизация новых контактов")
    print("✅ Двусторонняя синхронизация Zoho ↔ Локальная база")
    print("✅ Webhook поддержка для real-time обновлений")
    print("")
    
    # Демонстрация кэша
    cache = demo_contact_cache()
    
    # Демонстрация сопоставления с документами
    demo_document_matching(cache)
    
    # Демонстрация синхронизации (асинхронная)
    asyncio.run(demo_sync_service())
    
    print("\n\n🎉 ДЕМОНСТРАЦИЯ ЗАВЕРШЕНА!")
    print("=" * 30)
    print("💡 Система готова к интеграции с:")
    print("   📱 Telegram Bot (для обработки документов)")
    print("   🌐 Zoho Books API (для синхронизации)")
    print("   📊 FastAPI (для webhook endpoints)")
    print("   🗄️ Локальной базой данных")


if __name__ == "__main__":
    main() 