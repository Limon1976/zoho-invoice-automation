"""
Contact Cache Service
====================

Система кэширования и поиска контактов из Zoho Books.
Приоритет поиска: VAT номер > название компании > email.
"""

from typing import Dict, List, Optional, Set, Tuple, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from pathlib import Path
import json
import re
from difflib import SequenceMatcher
from pydantic import BaseModel, Field, ConfigDict
import logging

logger = logging.getLogger(__name__)

@dataclass
class OptimizedContactCacheEntry:
    """Оптимизированная структура контакта с только нужными полями"""
    contact_id: str
    contact_name: str
    company_name: str
    email: str
    vat_number: Optional[str]           # cf_vat_id
    contact_type: str                   # customer/vendor
    billing_address: Optional[dict]     # адрес плательщика
    shipping_address: Optional[dict]    # адрес доставки
    phone: Optional[str]                # телефон контакта
    contact_person: Optional[str]       # имя контактного лица
    notes: Optional[str]                # банковские реквизиты и другие заметки
    organization_id: str
    last_modified: str
    
    def to_dict(self) -> dict:
        """Преобразование в словарь для JSON сериализации"""
        return {
            'contact_id': self.contact_id,
            'contact_name': self.contact_name,
            'company_name': self.company_name,
            'email': self.email,
            'vat_number': self.vat_number,
            'contact_type': self.contact_type,
            'billing_address': self.billing_address,
            'shipping_address': self.shipping_address,
            'phone': self.phone,
            'contact_person': self.contact_person,
            'notes': self.notes,
            'organization_id': self.organization_id,
            'last_modified': self.last_modified
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'OptimizedContactCacheEntry':
        """Создание из словаря"""
        return cls(
            contact_id=data['contact_id'],
            contact_name=data['contact_name'],
            company_name=data['company_name'],
            email=data['email'],
            vat_number=data.get('vat_number'),
            contact_type=data['contact_type'],
            billing_address=data.get('billing_address'),
            shipping_address=data.get('shipping_address'),
            phone=data.get('phone'),
            contact_person=data.get('contact_person'),
            notes=data.get('notes'),
            organization_id=data.get('organization_id', ''),
            last_modified=data.get('last_modified', '')
        )

class OptimizedContactCache:
    """Оптимизированный кэш контактов с минимальными данными"""
    
    def __init__(self, cache_file: str = "data/optimized_contact_cache.json"):
        self.cache_file = Path(cache_file)
        self.contacts: Dict[str, OptimizedContactCacheEntry] = {}
        self.vat_index: Dict[str, str] = {}  # normalized VAT (A-Z0-9, upper) -> contact_id
        self.vat_digits_index: Dict[str, str] = {}  # digits only -> contact_id
        self.company_index: Dict[str, List[str]] = {}  # company_name -> [contact_ids]
        self.email_index: Dict[str, str] = {}  # email -> contact_id
        self.load_cache()
    
    def extract_minimal_data(self, contact_data: dict) -> OptimizedContactCacheEntry:
        """Извлечение только нужных полей из полного контакта"""
        # Извлечение VAT/TAX номера (разные поля в разных организациях)
        vat_number = None
        if 'cf_vat_id' in contact_data and contact_data['cf_vat_id']:
            vat_number = contact_data['cf_vat_id']
        elif 'cf_tax_id' in contact_data and contact_data['cf_tax_id']:
            vat_number = contact_data['cf_tax_id']
        elif 'extracted_vat_number' in contact_data:
            vat_number = contact_data['extracted_vat_number']
        
        # Извлечение адресов (только нужные поля)
        billing_address = None
        shipping_address = None
        
        if 'billing_address' in contact_data and contact_data['billing_address']:
            billing_address = {
                'address': contact_data['billing_address'].get('address', ''),
                'city': contact_data['billing_address'].get('city', ''),
                'state': contact_data['billing_address'].get('state', ''),
                'zip': contact_data['billing_address'].get('zip', ''),
                'country': contact_data['billing_address'].get('country', ''),
                'country_code': contact_data['billing_address'].get('country_code', '')
            }
        
        if 'shipping_address' in contact_data and contact_data['shipping_address']:
            shipping_address = {
                'address': contact_data['shipping_address'].get('address', ''),
                'city': contact_data['shipping_address'].get('city', ''),
                'state': contact_data['shipping_address'].get('state', ''),
                'zip': contact_data['shipping_address'].get('zip', ''),
                'country': contact_data['shipping_address'].get('country', ''),
                'country_code': contact_data['shipping_address'].get('country_code', '')
            }
        
        # Извлекаем phone (mobile приоритетнее чем phone)
        phone = contact_data.get('mobile', '') or contact_data.get('phone', '')
        
        # Извлекаем contact_person из first_name + last_name
        first_name = contact_data.get('first_name', '')
        last_name = contact_data.get('last_name', '')
        contact_person = f"{first_name} {last_name}".strip() if first_name or last_name else ''
        
        # Извлекаем notes (банковские реквизиты)
        notes = contact_data.get('notes', '')
        
        return OptimizedContactCacheEntry(
            contact_id=contact_data['contact_id'],
            contact_name=contact_data.get('contact_name', ''),
            company_name=contact_data.get('company_name', ''),
            email=contact_data.get('email', ''),
            vat_number=vat_number,
            contact_type=contact_data.get('contact_type', ''),
            billing_address=billing_address,
            shipping_address=shipping_address,
            phone=phone,
            contact_person=contact_person,
            notes=notes,
            organization_id=contact_data.get('organization_id', ''),
            last_modified=contact_data.get('last_modified_time', '')
        )
    
    def _remove_indices_for_contact(self, entry: OptimizedContactCacheEntry) -> None:
        """Удаляет индексы старой версии контакта, чтобы не оставлять мусор."""
        if not entry:
            return
        # VAT индексы
        if entry.vat_number:
            raw = entry.vat_number or ''
            norm = re.sub(r"[^A-Z0-9]", "", str(raw).upper())
            digits = re.sub(r"\D", "", norm)
            try:
                if norm in self.vat_index and self.vat_index.get(norm) == entry.contact_id:
                    self.vat_index.pop(norm, None)
            except Exception:
                pass
            try:
                if digits in self.vat_digits_index and self.vat_digits_index.get(digits) == entry.contact_id:
                    self.vat_digits_index.pop(digits, None)
            except Exception:
                pass
        # Company index
        if entry.company_name and entry.company_name in self.company_index:
            try:
                lst = self.company_index.get(entry.company_name, [])
                if entry.contact_id in lst:
                    lst = [cid for cid in lst if cid != entry.contact_id]
                    if lst:
                        self.company_index[entry.company_name] = lst
                    else:
                        self.company_index.pop(entry.company_name, None)
            except Exception:
                pass
        # Email index
        if entry.email and self.email_index.get(entry.email) == entry.contact_id:
            self.email_index.pop(entry.email, None)

    def upsert_contact_from_zoho(self, full_contact: dict) -> OptimizedContactCacheEntry:
        """Добавляет/обновляет один контакт из полного ответа Zoho.
        Без создания дублей: заменяет запись по contact_id и корректно перестраивает индексы.
        """
        new_entry = self.extract_minimal_data(full_contact)
        old_entry = self.contacts.get(new_entry.contact_id)
        if old_entry:
            self._remove_indices_for_contact(old_entry)
        # Записываем новую версию и добавляем индексы аналогично add_contacts
        self.contacts[new_entry.contact_id] = new_entry
        if new_entry.vat_number:
            raw = new_entry.vat_number or ''
            norm = re.sub(r"[^A-Z0-9]", "", str(raw).upper())
            digits = re.sub(r"\D", "", norm)
            if norm:
                self.vat_index[norm] = new_entry.contact_id
            if digits:
                self.vat_digits_index[digits] = new_entry.contact_id
        if new_entry.company_name:
            self.company_index.setdefault(new_entry.company_name, [])
            if new_entry.contact_id not in self.company_index[new_entry.company_name]:
                self.company_index[new_entry.company_name].append(new_entry.contact_id)
        if new_entry.email:
            self.email_index[new_entry.email] = new_entry.contact_id
        return new_entry

    def add_contacts(self, contacts_data: List[dict]) -> None:
        """Добавление контактов в кэш (только нужные поля)"""
        for contact_data in contacts_data:
            entry = self.extract_minimal_data(contact_data)
            self.contacts[entry.contact_id] = entry
        
            # Обновление индексов
            if entry.vat_number:
                # Нормализуем VAT для индексации: A-Z0-9 и цифры без префикса
                raw = entry.vat_number or ''
                norm = re.sub(r"[^A-Z0-9]", "", str(raw).upper())
                digits = re.sub(r"\D", "", norm)
                if norm:
                    self.vat_index[norm] = entry.contact_id
                if digits:
                    self.vat_digits_index[digits] = entry.contact_id
        
            if entry.company_name:
                if entry.company_name not in self.company_index:
                    self.company_index[entry.company_name] = []
                self.company_index[entry.company_name].append(entry.contact_id)
        
            if entry.email:
                self.email_index[entry.email] = entry.contact_id
    
    def search_by_vat(self, vat_number: str) -> Optional[OptimizedContactCacheEntry]:
        """Поиск контакта по VAT номеру (учитывает префикс/без префикса)."""
        if not vat_number:
            return None
        norm = re.sub(r"[^A-Z0-9]", "", str(vat_number).upper())
        digits = re.sub(r"\D", "", norm)
        # 1) Полное совпадение нормализованного VAT
        contact_id = self.vat_index.get(norm)
        if contact_id and contact_id in self.contacts:
            return self.contacts[contact_id]
        # 2) По цифрам (без префикса)
        contact_id = self.vat_digits_index.get(digits)
        if contact_id and contact_id in self.contacts:
            return self.contacts[contact_id]
        return None
    
    def search_by_company(self, company_name: str) -> List[OptimizedContactCacheEntry]:
        """Поиск контактов по названию компании"""
        contact_ids = self.company_index.get(company_name, [])
        return [self.contacts[cid] for cid in contact_ids if cid in self.contacts]
    
    def search_by_email(self, email: str) -> Optional[OptimizedContactCacheEntry]:
        """Поиск контакта по email"""
        contact_id = self.email_index.get(email)
        return self.contacts.get(contact_id) if contact_id else None
    
    def get_contact_address(self, contact_id: str, address_type: str = 'billing') -> Optional[dict]:
        """Получение адреса контакта"""
        contact = self.contacts.get(contact_id)
        if not contact:
            return None
        
        if address_type == 'billing':
            return contact.billing_address
        elif address_type == 'shipping':
            return contact.shipping_address
        return None
    
    def get_contacts_by_type(self, contact_type: str) -> List[OptimizedContactCacheEntry]:
        """Получение контактов по типу (customer/vendor)"""
        return [contact for contact in self.contacts.values() 
                if contact.contact_type == contact_type]
    
    def get_contacts_with_vat(self) -> List[OptimizedContactCacheEntry]:
        """Получение контактов с VAT номерами"""
        return [contact for contact in self.contacts.values() 
                if contact.vat_number]
    
    def save_cache(self) -> None:
        """Сохранение кэша в файл"""
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_data = {
                'contacts': {cid: contact.to_dict() for cid, contact in self.contacts.items()},
                'vat_index': self.vat_index,
                'vat_digits_index': self.vat_digits_index,
                'company_index': self.company_index,
                'email_index': self.email_index
            }
            
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Кэш сохранен: {len(self.contacts)} контактов в {self.cache_file}")
        except Exception as e:
            logger.error(f"Ошибка сохранения кэша: {e}")
    
    def load_cache(self) -> None:
        """Загрузка кэша из файла"""
        try:
            if self.cache_file.exists():
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                
                # Загрузка контактов
                for cid, contact_data in cache_data.get('contacts', {}).items():
                    self.contacts[cid] = OptimizedContactCacheEntry.from_dict(contact_data)
                
                # Загрузка индексов
                self.vat_index = cache_data.get('vat_index', {})
                self.vat_digits_index = cache_data.get('vat_digits_index', {})
                self.company_index = cache_data.get('company_index', {})
                self.email_index = cache_data.get('email_index', {})
                
                logger.info(f"Кэш загружен: {len(self.contacts)} контактов")
        except Exception as e:
            logger.error(f"Ошибка загрузки кэша: {e}")
    
    def get_statistics(self) -> dict:
        """Получение статистики кэша"""
        total_contacts = len(self.contacts)
        contacts_with_vat = len([c for c in self.contacts.values() if c.vat_number])
        customers = len([c for c in self.contacts.values() if c.contact_type == 'customer'])
        vendors = len([c for c in self.contacts.values() if c.contact_type == 'vendor'])
        
        return {
            'total_contacts': total_contacts,
            'contacts_with_vat': contacts_with_vat,
            'customers': customers,
            'vendors': vendors,
            'cache_file_size': self.cache_file.stat().st_size if self.cache_file.exists() else 0
        } 