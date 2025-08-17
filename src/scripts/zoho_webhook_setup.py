"""
Настройка Webhooks в Zoho Books
===============================

Скрипт для автоматической настройки webhooks в Zoho Books
для получения уведомлений о создании/обновлении/удалении контактов.
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Dict, List

# Добавляем корневую папку в path
sys.path.append(str(Path(__file__).parent.parent.parent))

from src.infrastructure.zoho_api import ZohoAPIClient
from src.infrastructure.config import get_config

# Логи настраиваются центрально; используем модульный логгер
logger = logging.getLogger(__name__)


class ZohoWebhookManager:
    """Менеджер для настройки Zoho Webhooks"""
    
    def __init__(self):
        self.config = get_config()
        self.zoho_api = ZohoAPIClient(
            client_id=self.config.zoho.client_id,
            client_secret=self.config.zoho.client_secret,
            refresh_token=self.config.zoho.refresh_token or ""
        )
        
        # Организации для настройки
        self.organizations = {
            "20092948714": "TaVie Europe OÜ",
            "20082562863": "PARKENTERTAINMENT Sp. z o. o."
        }
    
    async def setup_all_webhooks(self, webhook_url: str) -> Dict[str, bool]:
        """
        Настройка webhooks для всех организаций
        
        Args:
            webhook_url: URL для webhook endpoint
            
        Returns:
            Словарь с результатами для каждой организации
        """
        results = {}
        
        logger.info("🔗 Начинаем настройку webhooks для всех организаций")
        logger.info(f"📡 Webhook URL: {webhook_url}")
        
        for org_id, org_name in self.organizations.items():
            logger.info(f"\n🏢 Настройка webhook для {org_name} ({org_id})")
            
            try:
                # Удаляем старые webhooks
                await self.cleanup_old_webhooks(org_id)
                
                # Создаем новый webhook
                success = await self.create_webhook(org_id, webhook_url)
                results[org_id] = success
                
                if success:
                    logger.info(f"✅ Webhook настроен для {org_name}")
                else:
                    logger.error(f"❌ Ошибка настройки webhook для {org_name}")
                    
            except Exception as e:
                logger.error(f"❌ Исключение при настройке {org_name}: {e}")
                results[org_id] = False
        
        # Итоговая статистика
        successful = sum(1 for success in results.values() if success)
        total = len(results)
        
        logger.info(f"\n📊 ИТОГИ НАСТРОЙКИ WEBHOOKS:")
        logger.info(f"✅ Успешно: {successful}/{total}")
        logger.info(f"❌ Ошибки: {total - successful}/{total}")
        
        return results
    
    async def create_webhook(self, organization_id: str, webhook_url: str) -> bool:
        """
        Создание webhook для организации
        
        Args:
            organization_id: ID организации в Zoho
            webhook_url: URL webhook endpoint
            
        Returns:
            True если webhook создан успешно
        """
        try:
            webhook_data = {
                "webhook_url": webhook_url,
                "events": [
                    "contact.created",
                    "contact.updated", 
                    "contact.deleted"
                ],
                "description": "Contact sync webhook for invoice automation system",
                "enabled": True
            }
            
            logger.info(f"📤 Создаем webhook с событиями: {webhook_data['events']}")
            
            success = await self.zoho_api.create_webhook(webhook_data, organization_id)
            
            if success:
                logger.info(f"✅ Webhook успешно создан")
                return True
            else:
                logger.error(f"❌ Ошибка создания webhook")
                return False
                
        except Exception as e:
            logger.error(f"❌ Исключение при создании webhook: {e}")
            return False
    
    async def cleanup_old_webhooks(self, organization_id: str):
        """Очистка старых webhooks (если есть API для этого)"""
        try:
            # В реальном API может быть метод для получения списка webhook'ов
            # и их удаления. Пока оставляем заглушку.
            logger.info("🧹 Проверяем старые webhooks...")
            # await self.zoho_api.list_webhooks(organization_id)
            # await self.zoho_api.delete_webhook(webhook_id, organization_id)
            
        except Exception as e:
            logger.warning(f"⚠️ Ошибка очистки старых webhooks: {e}")
    
    async def test_webhook_endpoint(self, webhook_url: str) -> bool:
        """
        Тестирование доступности webhook endpoint
        
        Args:
            webhook_url: URL для тестирования
            
        Returns:
            True если endpoint доступен
        """
        try:
            import httpx
            
            logger.info(f"🧪 Тестируем доступность endpoint: {webhook_url}")
            
            async with httpx.AsyncClient() as client:
                # Отправляем тестовый запрос
                response = await client.post(
                    webhook_url,
                    json={
                        "event_type": "test.webhook",
                        "test": True,
                        "message": "Test webhook from setup script"
                    },
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    logger.info("✅ Endpoint доступен и отвечает")
                    return True
                else:
                    logger.warning(f"⚠️ Endpoint вернул статус: {response.status_code}")
                    return False
                    
        except Exception as e:
            logger.error(f"❌ Ошибка тестирования endpoint: {e}")
            return False
    
    def generate_webhook_url(self) -> str:
        """Генерация URL для webhook на основе конфигурации"""
        host = self.config.api.host
        port = self.config.api.port
        
        # Определяем протокол
        if host in ["localhost", "127.0.0.1"] or host.startswith("192.168."):
            protocol = "http"
        else:
            protocol = "https"
        
        # Формируем URL
        if port in [80, 443]:
            webhook_url = f"{protocol}://{host}/api/contacts/webhook/zoho"
        else:
            webhook_url = f"{protocol}://{host}:{port}/api/contacts/webhook/zoho"
        
        return webhook_url
    
    def get_webhook_instructions(self) -> str:
        """Инструкции по настройке webhook"""
        instructions = """
📋 ИНСТРУКЦИИ ПО WEBHOOK:

1. 🌐 Убедитесь что ваш сервер доступен из интернета
   - Для локальной разработки используйте ngrok или подобный туннель
   - Для продакшена используйте домен с SSL сертификатом

2. 🚀 Запустите ваш FastAPI сервер:
   python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000

3. 🔗 Webhook endpoint должен быть доступен по адресу:
   {webhook_url}

4. ✅ События которые будут отправляться:
   - contact.created - создание нового контакта
   - contact.updated - обновление контакта  
   - contact.deleted - удаление контакта

5. 🔒 В продакшене рекомендуется:
   - Использовать HTTPS
   - Валидировать подпись webhook (X-Zoho-Webhook-Signature)
   - Логировать все входящие события
        """
        
        return instructions.format(
            webhook_url=self.generate_webhook_url()
        )


async def main():
    """Главная функция"""
    print("🔗 НАСТРОЙКА ZOHO BOOKS WEBHOOKS")
    print("=" * 50)
    
    manager = ZohoWebhookManager()
    
    # Показываем инструкции
    print(manager.get_webhook_instructions())
    
    # Спрашиваем URL
    suggested_url = manager.generate_webhook_url()
    print(f"\n💡 Предлагаемый URL: {suggested_url}")
    
    webhook_url = input("Введите URL для webhook (или нажмите Enter для использования предлагаемого): ").strip()
    if not webhook_url:
        webhook_url = suggested_url
    
    print(f"\n🎯 Используем URL: {webhook_url}")
    
    # Тестируем доступность (опционально)
    test_endpoint = input("Протестировать доступность endpoint? (y/N): ").lower() == 'y'
    
    if test_endpoint:
        endpoint_ok = await manager.test_webhook_endpoint(webhook_url)
        if not endpoint_ok:
            continue_anyway = input("Endpoint недоступен. Продолжить настройку? (y/N): ").lower() == 'y'
            if not continue_anyway:
                print("❌ Настройка отменена")
                return
    
    # Настраиваем webhooks
    print(f"\n🔄 Начинаем настройку webhooks...")
    results = await manager.setup_all_webhooks(webhook_url)
    
    # Показываем результаты
    successful_orgs = [org_id for org_id, success in results.items() if success]
    
    if successful_orgs:
        print(f"\n✅ Webhooks настроены успешно!")
        print("📱 Теперь при изменении контактов в Zoho Books ваша система")
        print("   будет автоматически получать уведомления.")
        print("\n🔍 Для отладки можете проверить логи вашего сервера.")
    else:
        print(f"\n❌ Не удалось настроить webhooks")
        print("🔍 Проверьте логи для подробностей")
        print("🔑 Убедитесь что у вас есть права на создание webhooks в Zoho")


if __name__ == "__main__":
    asyncio.run(main()) 