"""
Contacts API Router
==================

API endpoints для управления контактами и обработки webhooks от Zoho Books.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import logging

from ..dependencies import get_contact_cache, get_contact_sync_service
from ...domain.services.contact_cache import ContactCache, ContactMatchResult
from ...domain.services.contact_sync import ContactSyncService, ContactSyncEvent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/contacts", tags=["contacts"])


# Pydantic модели для API
class ContactSearchRequest(BaseModel):
    """Запрос поиска контакта"""
    vat_number: Optional[str] = Field(None, description="VAT номер")
    company_name: Optional[str] = Field(None, description="Название компании")
    email: Optional[str] = Field(None, description="Email")
    organization_id: Optional[str] = Field(None, description="ID организации")
    min_confidence: float = Field(0.7, ge=0.0, le=1.0, description="Минимальная уверенность")


class ContactSearchResponse(BaseModel):
    """Ответ поиска контакта"""
    found: bool = Field(..., description="Найден ли контакт")
    contact: Optional[Dict[str, Any]] = Field(None, description="Данные контакта")
    match_type: Optional[str] = Field(None, description="Тип совпадения")
    confidence: Optional[float] = Field(None, description="Уверенность")
    organization_id: Optional[str] = Field(None, description="ID организации")


class ContactCreateRequest(BaseModel):
    """Запрос создания контакта"""
    contact_name: str = Field(..., description="Название контакта")
    company_name: Optional[str] = Field(None, description="Название компании")
    contact_type: str = Field("vendor", description="Тип контакта")
    vat_number: Optional[str] = Field(None, description="VAT номер")
    email: Optional[str] = Field(None, description="Email")
    phone: Optional[str] = Field(None, description="Телефон")
    address: Optional[str] = Field(None, description="Адрес")
    country: Optional[str] = Field(None, description="Страна")
    organization_id: str = Field(..., description="ID организации")


class ZohoWebhookEvent(BaseModel):
    """Webhook событие от Zoho"""
    event_type: str = Field(..., description="Тип события")
    contact_id: Optional[str] = Field(None, description="ID контакта")
    organization_id: str = Field(..., description="ID организации")
    data: Dict[str, Any] = Field(default_factory=dict, description="Данные события")


class SyncRequest(BaseModel):
    """Запрос синхронизации"""
    organization_id: Optional[str] = Field(None, description="ID организации (все если не указан)")
    force: bool = Field(False, description="Принудительная синхронизация")


class CacheStatsResponse(BaseModel):
    """Статистика кэша"""
    total_contacts: int
    organizations: int
    contacts_with_vat: int
    cache_file_exists: bool
    last_sync_times: Dict[str, str]


@router.post("/search", response_model=ContactSearchResponse)
async def search_contact(
    request: ContactSearchRequest,
    cache: ContactCache = Depends(get_contact_cache)
):
    """
    Поиск контакта по VAT номеру, названию компании или email
    
    Приоритет поиска:
    1. Точное совпадение по VAT номеру
    2. Точное совпадение по названию компании
    3. Нечеткое совпадение по названию компании
    4. Точное совпадение по email
    """
    try:
        result = cache.find_contact(
            vat_number=request.vat_number,
            company_name=request.company_name,
            email=request.email,
            organization_id=request.organization_id,
            min_confidence=request.min_confidence
        )
        
        if result:
            return ContactSearchResponse(
                found=True,
                contact={
                    "contact_id": result.contact.contact_id,
                    "contact_name": result.contact.contact_name,
                    "company_name": result.contact.company_name,
                    "vat_number": result.contact.vat_number,
                    "email": result.contact.email,
                    "phone": result.contact.phone,
                    "contact_type": result.contact.contact_type,
                    "organization_id": result.contact.organization_id
                },
                match_type=result.match_type,
                confidence=result.confidence,
                organization_id=result.organization_id
            )
        else:
            return ContactSearchResponse(found=False)
            
    except Exception as e:
        logger.error(f"Ошибка поиска контакта: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка поиска контакта: {str(e)}")


@router.post("/create")
async def create_contact(
    request: ContactCreateRequest,
    background_tasks: BackgroundTasks,
    sync_service: ContactSyncService = Depends(get_contact_sync_service)
):
    """Создание нового контакта в Zoho Books"""
    try:
        # Подготавливаем данные контакта
        contact_data = {
            "contact_name": request.contact_name,
            "company_name": request.company_name or request.contact_name,
            "contact_type": request.contact_type
        }
        
        # Добавляем VAT номер в custom fields
        if request.vat_number:
            contact_data["custom_fields"] = [{
                "api_name": "cf_vat_id",
                "value": request.vat_number
            }]
        
        # Добавляем адрес
        if request.address or request.country:
            contact_data["billing_address"] = {
                "address": request.address or "",
                "country": request.country or ""
            }
        
        # Добавляем контактное лицо
        if request.email or request.phone:
            contact_data["contact_persons"] = [{
                "first_name": "Contact",
                "last_name": "Person",
                "email": request.email or "",
                "phone": request.phone or "",
                "is_primary_contact": True
            }]
        
        # Создаем контакт асинхронно
        background_tasks.add_task(
            sync_service.create_contact_in_zoho,
            contact_data,
            request.organization_id
        )
        
        return {
            "success": True,
            "message": "Контакт добавлен в очередь создания",
            "contact_name": request.contact_name
        }
        
    except Exception as e:
        logger.error(f"Ошибка создания контакта: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка создания контакта: {str(e)}")


@router.post("/webhook/zoho")
async def zoho_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    sync_service: ContactSyncService = Depends(get_contact_sync_service),
    x_zoho_webhook_signature: Optional[str] = Header(None)
):
    """
    Webhook endpoint для получения событий от Zoho Books
    
    Zoho отправляет события при создании, обновлении или удалении контактов.
    """
    try:
        # Получаем данные webhook
        body = await request.body()
        webhook_data = await request.json()
        
        logger.info(f"Получен webhook от Zoho: {webhook_data.get('event_type')}")
        
        # Проверяем подпись (в реальном проекте)
        # if not verify_zoho_signature(body, x_zoho_webhook_signature):
        #     raise HTTPException(status_code=401, detail="Invalid signature")
        
        # Обрабатываем событие в фоне
        background_tasks.add_task(
            sync_service.handle_webhook_event,
            webhook_data
        )
        
        return {"status": "received", "event_type": webhook_data.get("event_type")}
        
    except Exception as e:
        logger.error(f"Ошибка обработки webhook: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка обработки webhook: {str(e)}")


@router.post("/sync")
async def sync_contacts(
    request: SyncRequest,
    background_tasks: BackgroundTasks,
    sync_service: ContactSyncService = Depends(get_contact_sync_service)
):
    """Запуск синхронизации контактов с Zoho Books"""
    try:
        if request.organization_id:
            # Синхронизация конкретной организации
            background_tasks.add_task(
                sync_service.full_sync_organization,
                request.organization_id
            )
            message = f"Запущена синхронизация организации {request.organization_id}"
        else:
            # Синхронизация всех организаций
            background_tasks.add_task(sync_service.sync_all_organizations)
            message = "Запущена синхронизация всех организаций"
        
        return {
            "success": True,
            "message": message,
            "force": request.force
        }
        
    except Exception as e:
        logger.error(f"Ошибка запуска синхронизации: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка синхронизации: {str(e)}")


@router.get("/stats", response_model=CacheStatsResponse)
async def get_cache_stats(
    cache: ContactCache = Depends(get_contact_cache),
    sync_service: ContactSyncService = Depends(get_contact_sync_service)
):
    """Получение статистики кэша контактов"""
    try:
        cache_stats = cache.get_cache_stats()
        sync_stats = sync_service.get_sync_statistics()
        
        return CacheStatsResponse(
            total_contacts=cache_stats["total_contacts"],
            organizations=cache_stats["organizations"],
            contacts_with_vat=cache_stats["contacts_with_vat"],
            cache_file_exists=cache_stats["cache_file_exists"],
            last_sync_times=cache_stats["last_sync_times"]
        )
        
    except Exception as e:
        logger.error(f"Ошибка получения статистики: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка получения статистики: {str(e)}")


@router.get("/organizations/{organization_id}")
async def get_organization_contacts(
    organization_id: str,
    cache: ContactCache = Depends(get_contact_cache)
):
    """Получение всех контактов организации"""
    try:
        contacts = cache.get_contacts_by_org(organization_id)
        
        contacts_data = []
        for contact in contacts:
            contacts_data.append({
                "contact_id": contact.contact_id,
                "contact_name": contact.contact_name,
                "company_name": contact.company_name,
                "vat_number": contact.vat_number,
                "email": contact.email,
                "phone": contact.phone,
                "contact_type": contact.contact_type,
                "last_modified": contact.last_modified.isoformat() if contact.last_modified else None
            })
        
        return {
            "organization_id": organization_id,
            "total_contacts": len(contacts_data),
            "contacts": contacts_data
        }
        
    except Exception as e:
        logger.error(f"Ошибка получения контактов организации: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка получения контактов: {str(e)}")


@router.delete("/cache/{organization_id}")
async def clear_organization_cache(
    organization_id: str,
    cache: ContactCache = Depends(get_contact_cache)
):
    """Очистка кэша для конкретной организации"""
    try:
        cleared_count = cache.clear_org_cache(organization_id)
        
        return {
            "success": True,
            "message": f"Очищен кэш для организации {organization_id}",
            "cleared_contacts": cleared_count
        }
        
    except Exception as e:
        logger.error(f"Ошибка очистки кэша: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка очистки кэша: {str(e)}")


@router.post("/match-document")
async def match_document_supplier(
    supplier_data: Dict[str, Any],
    organization_id: Optional[str] = None,
    sync_service: ContactSyncService = Depends(get_contact_sync_service)
):
    """
    Сопоставление поставщика из документа с существующими контактами
    
    Используется при обработке входящих документов в Telegram боте.
    """
    try:
        # Ищем существующий контакт
        match_result = sync_service.find_contact_for_document(
            supplier_data, organization_id
        )
        
        if match_result:
            return {
                "found": True,
                "contact": {
                    "contact_id": match_result.contact.contact_id,
                    "contact_name": match_result.contact.contact_name,
                    "company_name": match_result.contact.company_name,
                    "vat_number": match_result.contact.vat_number,
                    "contact_type": match_result.contact.contact_type
                },
                "match_type": match_result.match_type,
                "confidence": match_result.confidence,
                "organization_id": match_result.organization_id
            }
        else:
            return {
                "found": False,
                "suggestion": {
                    "action": "create_new_contact",
                    "contact_name": supplier_data.get("name", "Unknown"),
                    "vat_number": supplier_data.get("vat"),
                    "email": supplier_data.get("email"),
                    "address": supplier_data.get("address")
                }
            }
            
    except Exception as e:
        logger.error(f"Ошибка сопоставления документа: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка сопоставления: {str(e)}")


@router.post("/auto-create-from-document")
async def auto_create_from_document(
    supplier_data: Dict[str, Any],
    organization_id: str,
    background_tasks: BackgroundTasks,
    sync_service: ContactSyncService = Depends(get_contact_sync_service)
):
    """
    Автоматическое создание контакта из данных документа
    
    Используется когда контакт не найден и нужно создать новый.
    """
    try:
        # Проверяем минимальные требования
        if not supplier_data.get("name"):
            raise HTTPException(
                status_code=400, 
                detail="Недостаточно данных: требуется название компании"
            )
        
        # Создаем контакт асинхронно
        background_tasks.add_task(
            sync_service.auto_create_contact_from_document,
            supplier_data,
            organization_id
        )
        
        return {
            "success": True,
            "message": f"Контакт '{supplier_data['name']}' добавлен в очередь создания",
            "organization_id": organization_id,
            "supplier_data": supplier_data
        }
        
    except Exception as e:
        logger.error(f"Ошибка автоматического создания контакта: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка создания контакта: {str(e)}")


# Дополнительные утилиты
def verify_zoho_signature(body: bytes, signature: str) -> bool:
    """Проверка подписи webhook от Zoho (заглушка)"""
    # В реальном проекте здесь должна быть проверка HMAC подписи
    # используя секретный ключ от Zoho
    return True 