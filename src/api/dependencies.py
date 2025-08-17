"""
FastAPI Dependencies
===================

Зависимости для инъекции сервисов в API endpoints.
"""

from functools import lru_cache
from pathlib import Path
from typing import Optional

from ..domain.services.contact_cache import ContactCache
from ..domain.services.contact_sync import ContactSyncService, SyncConfig
from ..infrastructure.zoho_api import ZohoAPIClient
from ..infrastructure.config import get_config


# Глобальные экземпляры сервисов
_contact_cache: Optional[ContactCache] = None
_contact_sync_service: Optional[ContactSyncService] = None
_zoho_api_client: Optional[ZohoAPIClient] = None


@lru_cache()
def get_contact_cache() -> ContactCache:
    """Получение экземпляра ContactCache"""
    global _contact_cache
    
    if _contact_cache is None:
        cache_file = Path("data/contact_cache.json")
        _contact_cache = ContactCache(cache_file)
    
    return _contact_cache


@lru_cache()
def get_zoho_api_client() -> ZohoAPIClient:
    """Получение экземпляра Zoho API клиента"""
    global _zoho_api_client
    
    if _zoho_api_client is None:
        config = get_config()
        _zoho_api_client = ZohoAPIClient(
            client_id=config.zoho.client_id,
            client_secret=config.zoho.client_secret,
            refresh_token=config.zoho.refresh_token or ""
        )
    
    return _zoho_api_client


@lru_cache()
def get_contact_sync_service() -> ContactSyncService:
    """Получение экземпляра ContactSyncService"""
    global _contact_sync_service
    
    if _contact_sync_service is None:
        cache = get_contact_cache()
        zoho_api = get_zoho_api_client()
        
        # Конфигурация синхронизации
        config = SyncConfig(
            webhook_enabled=True,
            webhook_url="https://your-domain.com/api/contacts/webhook/zoho",
            sync_interval_hours=6,
            organizations={
                "20092948714": "TaVie Europe OÜ",
                "20082562863": "PARKENTERTAINMENT Sp. z o. o."
            }
        )
        
        _contact_sync_service = ContactSyncService(
            contact_cache=cache,
            zoho_api_client=zoho_api,
            config=config
        )
    
    return _contact_sync_service


def reset_dependencies():
    """Сброс зависимостей (для тестирования)"""
    global _contact_cache, _contact_sync_service, _zoho_api_client
    
    _contact_cache = None
    _contact_sync_service = None
    _zoho_api_client = None
    
    # Очищаем кэш lru_cache
    get_contact_cache.cache_clear()
    get_zoho_api_client.cache_clear()
    get_contact_sync_service.cache_clear() 