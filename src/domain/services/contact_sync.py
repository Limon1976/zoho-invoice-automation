"""
Contact Sync Service
===================

Сервис синхронизации контактов между различными источниками
"""

from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timedelta
from pathlib import Path
import json
import logging
from enum import Enum
from dataclasses import dataclass, field

from pydantic import BaseModel, Field, ConfigDict

from .contact_cache import OptimizedContactCache, OptimizedContactCacheEntry
from ..entities import Company
from ..value_objects import VATNumber, Email

logger = logging.getLogger(__name__)


class SyncStatus(Enum):
    """Статус синхронизации"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class SyncConfig:
    """Конфигурация синхронизации"""
    batch_size: int = 100
    retry_attempts: int = 3
    retry_delay: float = 1.0
    backup_before_sync: bool = True
    organizations: Dict[str, str] = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.organizations:
            self.organizations = {
                "TaVie Europe OÜ": "60036337079",
                "PARKENTERTAINMENT": "20082562863"
            }


class ContactSyncResult(BaseModel):
    """Результат синхронизации контактов"""
    model_config = ConfigDict(extra='allow')
    
    total_processed: int = Field(default=0)
    successful_syncs: int = Field(default=0)
    failed_syncs: int = Field(default=0)
    duplicates_found: int = Field(default=0)
    errors: List[str] = Field(default_factory=list)
    sync_duration: float = Field(default=0.0)
    timestamp: datetime = Field(default_factory=datetime.now)


class ContactSyncService:
    """Сервис синхронизации контактов"""
    
    def __init__(self, 
                 contact_cache: OptimizedContactCache,
                 zoho_api_client: Any,  # ZohoAPI client
                 config: Optional[SyncConfig] = None):
        self.cache = contact_cache
        self.zoho_api = zoho_api_client
        self.config = config or SyncConfig()
        self.sync_log: List[Dict[str, Any]] = []
    
    async def sync_from_zoho(self, organization_id: str = None) -> ContactSyncResult:
        """Синхронизация контактов из Zoho Books"""
        result = ContactSyncResult()
        start_time = datetime.now()
        
        try:
            logger.info(f"Начинаю синхронизацию из Zoho для организации: {organization_id}")
            
            # Получаем контакты из Zoho
            zoho_contacts = await self._fetch_zoho_contacts(organization_id)
            result.total_processed = len(zoho_contacts)
            
            # Обрабатываем батчами
            for i in range(0, len(zoho_contacts), self.config.batch_size):
                batch = zoho_contacts[i:i + self.config.batch_size]
                batch_result = await self._process_contact_batch(batch)
                
                result.successful_syncs += batch_result['successful']
                result.failed_syncs += batch_result['failed']
                result.duplicates_found += batch_result['duplicates']
                result.errors.extend(batch_result['errors'])
            
        except Exception as e:
            logger.error(f"Ошибка синхронизации: {e}")
            result.errors.append(str(e))
        
        finally:
            result.sync_duration = (datetime.now() - start_time).total_seconds()
            
        return result
    
    async def _fetch_zoho_contacts(self, organization_id: str = None) -> List[Dict[str, Any]]:
        """Получение контактов из Zoho Books"""
        try:
            if organization_id:
                contacts = await self.zoho_api.get_all_contacts(organization_id)
            else:
                # Получаем из всех организаций
                all_contacts = []
                for org_name, org_id in self.config.organizations.items():
                    org_contacts = await self.zoho_api.get_all_contacts(org_id)
                    all_contacts.extend(org_contacts)
                contacts = all_contacts
            
            logger.info(f"Получено {len(contacts)} контактов из Zoho")
            return contacts
            
        except Exception as e:
            logger.error(f"Ошибка получения контактов из Zoho: {e}")
            raise
    
    async def _process_contact_batch(self, contacts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Обработка батча контактов"""
        result = {
            'successful': 0,
            'failed': 0,
            'duplicates': 0,
            'errors': []
        }
        
        for contact_data in contacts:
            try:
                # Проверяем на дубликаты
                if self._is_duplicate_contact(contact_data):
                    result['duplicates'] += 1
                    continue
                
                # Добавляем в кэш
                optimized_contact = self.cache.extract_minimal_data(contact_data)
                self.cache.contacts[optimized_contact.contact_id] = optimized_contact
                
                # Обновляем индексы
                self._update_cache_indexes(optimized_contact)
                
                result['successful'] += 1
                
            except Exception as e:
                logger.error(f"Ошибка обработки контакта {contact_data.get('contact_id', 'unknown')}: {e}")
                result['failed'] += 1
                result['errors'].append(str(e))
        
        return result
    
    def _is_duplicate_contact(self, contact_data: Dict[str, Any]) -> bool:
        """Проверка на дубликат контакта"""
        contact_id = contact_data.get('contact_id')
        
        # Проверяем по ID
        if contact_id and contact_id in self.cache.contacts:
            return True
        
        # Проверяем по VAT номеру
        vat_number = contact_data.get('cf_vat_id') or contact_data.get('cf_tax_id')
        if vat_number:
            existing = self.cache.search_by_vat(vat_number)
            if existing:
                return True
        
        # Проверяем по email
        email = contact_data.get('email')
        if email:
            existing = self.cache.search_by_email(email)
            if existing:
                return True
        
        return False
    
    def _update_cache_indexes(self, contact: OptimizedContactCacheEntry):
        """Обновление индексов кэша"""
        # VAT индекс
        if contact.vat_number:
            self.cache.vat_index[contact.vat_number] = contact.contact_id
        
        # Email индекс
        if contact.email:
            self.cache.email_index[contact.email] = contact.contact_id
        
        # Company индекс
        if contact.company_name:
            if contact.company_name not in self.cache.company_index:
                self.cache.company_index[contact.company_name] = []
            if contact.contact_id not in self.cache.company_index[contact.company_name]:
                self.cache.company_index[contact.company_name].append(contact.contact_id)
    
    def search_contact(self, 
                      vat_number: str = None, 
                      company_name: str = None, 
                      email: str = None) -> Optional[OptimizedContactCacheEntry]:
        """Поиск контакта по различным критериям"""
        
        # Приоритет поиска: VAT > Company > Email
        if vat_number:
            return self.cache.search_by_vat(vat_number)
        
        if company_name:
            results = self.cache.search_by_company(company_name)
            return results[0] if results else None
        
        if email:
            return self.cache.search_by_email(email)
        
        return None
    
    def get_sync_statistics(self) -> Dict[str, Any]:
        """Получение статистики синхронизации"""
        total_contacts = len(self.cache.contacts)
        contacts_with_vat = len([c for c in self.cache.contacts.values() if c.vat_number])
        
        return {
            "total_contacts": total_contacts,
            "contacts_with_vat": contacts_with_vat,
            "vat_coverage": contacts_with_vat / total_contacts if total_contacts > 0 else 0,
            "companies_count": len(self.cache.company_index),
            "emails_count": len(self.cache.email_index),
            "last_sync": max([entry.get('timestamp', datetime.min) for entry in self.sync_log]) if self.sync_log else None
        }
    
    async def validate_sync_integrity(self) -> Dict[str, Any]:
        """Валидация целостности синхронизации"""
        validation_result = {
            "valid": True,
            "issues": [],
            "statistics": {}
        }
        
        try:
            # Проверяем целостность индексов
            vat_index_issues = self._validate_vat_index()
            if vat_index_issues:
                validation_result["issues"].extend(vat_index_issues)
                validation_result["valid"] = False
            
            # Проверяем дубликаты
            duplicate_issues = self._find_duplicates()
            if duplicate_issues:
                validation_result["issues"].extend(duplicate_issues)
                validation_result["valid"] = False
            
            validation_result["statistics"] = self.get_sync_statistics()
            
        except Exception as e:
            validation_result["valid"] = False
            validation_result["issues"].append(f"Ошибка валидации: {e}")
        
        return validation_result
    
    def _validate_vat_index(self) -> List[str]:
        """Валидация VAT индекса"""
        issues = []
        
        for vat_number, contact_id in self.cache.vat_index.items():
            if contact_id not in self.cache.contacts:
                issues.append(f"VAT индекс указывает на несуществующий контакт: {contact_id}")
            else:
                contact = self.cache.contacts[contact_id]
                if contact.vat_number != vat_number:
                    issues.append(f"Несоответствие VAT в индексе: {vat_number} != {contact.vat_number}")
        
        return issues
    
    def _find_duplicates(self) -> List[str]:
        """Поиск потенциальных дубликатов"""
        issues = []
        
        # Группируем по VAT номерам
        vat_groups = {}
        for contact in self.cache.contacts.values():
            if contact.vat_number:
                if contact.vat_number not in vat_groups:
                    vat_groups[contact.vat_number] = []
                vat_groups[contact.vat_number].append(contact.contact_id)
        
        for vat_number, contact_ids in vat_groups.items():
            if len(contact_ids) > 1:
                issues.append(f"Дубликаты по VAT {vat_number}: {contact_ids}")
        
        return issues 