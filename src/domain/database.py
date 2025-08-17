"""
Database Models for Contact Storage
===================================

SQLite модели для хранения контактов вместо JSON файлов.
Обеспечивает лучшую производительность и ACID транзакции.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
import json
from sqlalchemy import Column, String, DateTime, Text, Boolean, Integer, Index, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy import create_engine
from pydantic import BaseModel

Base = declarative_base()

class ContactDB(Base):
    """SQLite модель для контакта"""
    
    __tablename__ = 'contacts'
    
    # Основные поля
    contact_id = Column(String, primary_key=True, index=True)
    organization_id = Column(String, nullable=False, index=True)
    contact_name = Column(String, nullable=False)
    company_name = Column(String, nullable=True)
    contact_type = Column(String, default="customer", index=True)  # customer | vendor
    
    # Контактные данные
    vat_number = Column(String, nullable=True, index=True)
    email = Column(String, nullable=True, index=True)
    phone = Column(String, nullable=True)
    
    # Нормализованные поля для поиска
    normalized_name = Column(String, nullable=True, index=True)
    normalized_vat = Column(String, nullable=True, index=True)
    normalized_email = Column(String, nullable=True, index=True)
    
    # Метаданные
    last_modified = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Полные данные (JSON)
    full_data = Column(Text, nullable=True)  # JSON с полной информацией от Zoho
    
    # Индексы для быстрого поиска
    __table_args__ = (
        Index('idx_contact_search', 'organization_id', 'normalized_vat'),
        Index('idx_contact_name_search', 'organization_id', 'normalized_name'),
        Index('idx_contact_email_search', 'organization_id', 'normalized_email'),
        Index('idx_contact_type_org', 'organization_id', 'contact_type'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразование в словарь"""
        return {
            'contact_id': self.contact_id,
            'organization_id': self.organization_id,
            'contact_name': self.contact_name,
            'company_name': self.company_name,
            'contact_type': self.contact_type,
            'vat_number': self.vat_number,
            'email': self.email,
            'phone': self.phone,
            'last_modified': self.last_modified.isoformat() if self.last_modified else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'full_data': json.loads(self.full_data) if self.full_data else None
        }


class SyncMetadataDB(Base):
    """Метаданные синхронизации"""
    
    __tablename__ = 'sync_metadata'
    
    organization_id = Column(String, primary_key=True)
    organization_name = Column(String, nullable=True)
    last_sync = Column(DateTime, nullable=True)
    total_contacts = Column(Integer, default=0)
    contacts_with_vat = Column(Integer, default=0)
    last_error = Column(Text, nullable=True)
    sync_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class ContactDatabaseManager:
    """Менеджер для работы с базой данных контактов"""
    
    def __init__(self, database_url: str = "sqlite:///data/contacts.db"):
        self.database_url = database_url
        self.engine = create_engine(database_url, echo=False)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        
        # Создаем таблицы
        Base.metadata.create_all(bind=self.engine)
    
    def get_session(self) -> Session:
        """Получить сессию базы данных"""
        return self.SessionLocal()
    
    def add_contacts(self, contacts: List[Dict[str, Any]], organization_id: str) -> int:
        """
        Добавить/обновить контакты в базе данных
        
        Args:
            contacts: Список контактов от Zoho API
            organization_id: ID организации
            
        Returns:
            Количество добавленных/обновленных контактов
        """
        session = self.get_session()
        added_count = 0
        
        try:
            for contact_data in contacts:
                contact_id = contact_data.get("contact_id")
                if not contact_id:
                    continue
                
                # Проверяем существует ли контакт
                existing = session.query(ContactDB).filter_by(contact_id=contact_id).first()
                
                # Извлекаем и нормализуем данные
                vat_number = self._extract_vat_number(contact_data)
                email = self._extract_email(contact_data)
                company_name = contact_data.get("company_name", "")
                contact_name = contact_data.get("contact_name", "")
                
                if existing:
                    # Обновляем существующий
                    existing.contact_name = contact_name
                    existing.company_name = company_name
                    existing.vat_number = vat_number
                    existing.email = email
                    existing.phone = self._extract_phone(contact_data)
                    existing.contact_type = contact_data.get("contact_type", "customer")
                    existing.last_modified = self._parse_datetime(contact_data.get("last_modified_time"))
                    existing.full_data = json.dumps(contact_data, ensure_ascii=False)
                    
                    # Обновляем нормализованные поля
                    existing.normalized_name = self._normalize_name(company_name or contact_name)
                    existing.normalized_vat = self._normalize_vat(vat_number or "")
                    existing.normalized_email = email.lower() if email else None
                else:
                    # Создаем новый
                    contact = ContactDB(
                        contact_id=contact_id,
                        organization_id=organization_id,
                        contact_name=contact_name,
                        company_name=company_name,
                        contact_type=contact_data.get("contact_type", "customer"),
                        vat_number=vat_number,
                        email=email,
                        phone=self._extract_phone(contact_data),
                        last_modified=self._parse_datetime(contact_data.get("last_modified_time")),
                        full_data=json.dumps(contact_data, ensure_ascii=False),
                        normalized_name=self._normalize_name(company_name or contact_name),
                        normalized_vat=self._normalize_vat(vat_number or ""),
                        normalized_email=email.lower() if email else None
                    )
                    session.add(contact)
                
                added_count += 1
            
            # Обновляем метаданные синхронизации
            self._update_sync_metadata(session, organization_id)
            
            session.commit()
            return added_count
            
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()
    
    def find_contact(self, 
                    vat_number: Optional[str] = None,
                    company_name: Optional[str] = None,
                    email: Optional[str] = None,
                    organization_id: Optional[str] = None,
                    min_confidence: float = 0.7) -> Optional[Dict[str, Any]]:
        """
        Поиск контакта с приоритетом: VAT > название > email
        
        Returns:
            Словарь с контактом и метаданными поиска или None
        """
        session = self.get_session()
        
        try:
            query = session.query(ContactDB)
            
            # Ограничиваем по организации
            if organization_id:
                query = query.filter(ContactDB.organization_id == organization_id)
            
            # 1. Точный поиск по VAT (приоритет)
            if vat_number:
                normalized_vat = self._normalize_vat(vat_number)
                if normalized_vat:
                    contact = query.filter(ContactDB.normalized_vat == normalized_vat).first()
                    if contact:
                        return {
                            "contact": contact.to_dict(),
                            "match_type": "vat_exact",
                            "confidence": 1.0
                        }
            
            # 2. Точный поиск по названию компании
            if company_name:
                normalized_name = self._normalize_name(company_name)
                if normalized_name:
                    contact = query.filter(ContactDB.normalized_name == normalized_name).first()
                    if contact:
                        return {
                            "contact": contact.to_dict(),
                            "match_type": "name_exact",
                            "confidence": 0.95
                        }
            
            # 3. Нечеткий поиск по названию (LIKE)
            if company_name:
                normalized_name = self._normalize_name(company_name)
                if normalized_name and len(normalized_name) > 3:
                    # Ищем похожие названия
                    contacts = query.filter(
                        ContactDB.normalized_name.like(f"%{normalized_name[:10]}%")
                    ).limit(10).all()
                    
                    # Проверяем схожесть
                    from difflib import SequenceMatcher
                    for contact in contacts:
                        if contact.normalized_name:
                            similarity = SequenceMatcher(None, normalized_name, contact.normalized_name).ratio()
                            if similarity >= min_confidence:
                                return {
                                    "contact": contact.to_dict(),
                                    "match_type": "name_fuzzy",
                                    "confidence": similarity * 0.9
                                }
            
            # 4. Точный поиск по email
            if email:
                normalized_email = email.lower()
                contact = query.filter(ContactDB.normalized_email == normalized_email).first()
                if contact:
                    return {
                        "contact": contact.to_dict(),
                        "match_type": "email_exact",
                        "confidence": 0.85
                    }
            
            return None
            
        finally:
            session.close()
    
    def get_contacts_by_org(self, organization_id: str) -> List[Dict[str, Any]]:
        """Получить все контакты организации"""
        session = self.get_session()
        try:
            contacts = session.query(ContactDB).filter_by(organization_id=organization_id).all()
            return [contact.to_dict() for contact in contacts]
        finally:
            session.close()
    
    def get_database_stats(self) -> Dict[str, Any]:
        """Статистика базы данных"""
        session = self.get_session()
        try:
            total_contacts = session.query(ContactDB).count()
            organizations = session.query(ContactDB.organization_id).distinct().count()
            contacts_with_vat = session.query(ContactDB).filter(ContactDB.vat_number.isnot(None)).count()
            
            # Статистика по организациям
            org_stats = {}
            sync_metadata = session.query(SyncMetadataDB).all()
            for metadata in sync_metadata:
                org_stats[f"org_{metadata.organization_id}"] = {
                    "total": metadata.total_contacts,
                    "with_vat": metadata.contacts_with_vat,
                    "last_sync": metadata.last_sync.isoformat() if metadata.last_sync else None,
                    "sync_count": metadata.sync_count
                }
            
            return {
                "total_contacts": total_contacts,
                "organizations": organizations,
                "contacts_with_vat": contacts_with_vat,
                "database_url": self.database_url,
                **org_stats
            }
        finally:
            session.close()
    
    def clear_org_contacts(self, organization_id: str) -> int:
        """Очистить контакты организации"""
        session = self.get_session()
        try:
            count = session.query(ContactDB).filter_by(organization_id=organization_id).count()
            session.query(ContactDB).filter_by(organization_id=organization_id).delete()
            session.commit()
            return count
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()
    
    def _update_sync_metadata(self, session: Session, organization_id: str):
        """Обновить метаданные синхронизации"""
        metadata = session.query(SyncMetadataDB).filter_by(organization_id=organization_id).first()
        
        # Подсчитываем статистику
        total_contacts = session.query(ContactDB).filter_by(organization_id=organization_id).count()
        contacts_with_vat = session.query(ContactDB).filter_by(organization_id=organization_id).filter(ContactDB.vat_number.isnot(None)).count()
        
        if metadata:
            metadata.last_sync = datetime.now()
            metadata.total_contacts = total_contacts
            metadata.contacts_with_vat = contacts_with_vat
            metadata.sync_count += 1
        else:
            metadata = SyncMetadataDB(
                organization_id=organization_id,
                last_sync=datetime.now(),
                total_contacts=total_contacts,
                contacts_with_vat=contacts_with_vat,
                sync_count=1
            )
            session.add(metadata)
    
    @staticmethod
    def _extract_vat_number(contact_data: Dict) -> Optional[str]:
        """Извлекает VAT номер из данных контакта"""
        # Проверяем custom_fields
        if 'custom_fields' in contact_data and contact_data['custom_fields']:
            for cf in contact_data['custom_fields']:
                if cf.get('api_name') == 'cf_vat_id' or 'vat' in cf.get('label', '').lower():
                    vat = cf.get('value', '').strip()
                    if vat:
                        return vat
        
        # Проверяем custom_field_hash
        if 'custom_field_hash' in contact_data:
            vat = contact_data['custom_field_hash'].get('cf_vat_id', '').strip()
            if vat:
                return vat
        
        # Проверяем прямые поля
        for field in ['cf_vat_id', 'vat_reg_no', 'tax_reg_no', 'gst_no']:
            if field in contact_data:
                vat = contact_data[field].strip()
                if vat:
                    return vat
        
        return None
    
    @staticmethod
    def _extract_email(contact_data: Dict) -> Optional[str]:
        """Извлекает email из данных контакта"""
        # Проверяем contact_persons
        if 'contact_persons' in contact_data and contact_data['contact_persons']:
            for person in contact_data['contact_persons']:
                if person.get('is_primary_contact') and person.get('email'):
                    return person['email'].strip()
        
        # Проверяем прямое поле
        if 'email' in contact_data and contact_data['email']:
            return contact_data['email'].strip()
        
        return None
    
    @staticmethod
    def _extract_phone(contact_data: Dict) -> Optional[str]:
        """Извлекает телефон из данных контакта"""
        # Проверяем contact_persons
        if 'contact_persons' in contact_data and contact_data['contact_persons']:
            for person in contact_data['contact_persons']:
                if person.get('is_primary_contact') and person.get('phone'):
                    return person['phone'].strip()
        
        # Проверяем billing_address
        if 'billing_address' in contact_data and contact_data['billing_address'].get('phone'):
            return contact_data['billing_address']['phone'].strip()
        
        return None
    
    @staticmethod
    def _parse_datetime(dt_str: Optional[str]) -> Optional[datetime]:
        """Парсит datetime строку из Zoho"""
        if not dt_str:
            return None
        
        try:
            # Zoho формат: "2013-10-07T18:24:51+0530"
            return datetime.fromisoformat(dt_str.replace('+0530', '+05:30'))
        except (ValueError, AttributeError):
            return None
    
    @staticmethod
    def _normalize_name(name: str) -> str:
        """Нормализация названия компании"""
        if not name:
            return ""
        
        import re
        
        # Удаляем лишние символы и приводим к нижнему регистру
        normalized = re.sub(r'[^\w\s]', '', name.lower())
        
        # Удаляем типичные суффиксы компаний
        suffixes = ['ltd', 'llc', 'inc', 'corp', 'gmbh', 'sa', 'sp z o o', 'oü', 'oy', 'ab']
        for suffix in suffixes:
            normalized = re.sub(rf'\b{suffix}\b', '', normalized)
        
        # Убираем лишние пробелы
        return ' '.join(normalized.split())
    
    @staticmethod
    def _normalize_vat(vat: str) -> str:
        """Нормализация VAT номера"""
        if not vat:
            return ""
        
        import re
        # Удаляем все кроме букв и цифр
        return re.sub(r'[^A-Z0-9]', '', vat.upper()) 