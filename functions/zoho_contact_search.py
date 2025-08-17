"""
Точечный поиск контактов в Zoho Books API
"""
import requests
import json
import time
from typing import Optional, Dict, Any, List

# Импорт с обработкой автономного запуска
try:
    from .zoho_api import get_access_token, log_message
except ImportError:
    # Автономный запуск
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from zoho_api import get_access_token, log_message


class ZohoContactSearcher:
    """Класс для точечного поиска контактов в Zoho Books"""
    
    def __init__(self):
        self.base_url = "https://www.zohoapis.eu/books/v3"
        
    def search_contact_by_name(self, company_name: str, organization_id: str) -> Optional[Dict[str, Any]]:
        """
        Точечный поиск контакта по названию компании
        
        Args:
            company_name: Название компании для поиска
            organization_id: ID организации (20092948714 или 20082562863)
            
        Returns:
            Словарь с данными контакта или None если не найден
        """
        try:
            access_token = get_access_token()
            if not access_token:
                log_message("ERROR: Не удалось получить access token")
                return None
                
            # Поиск контакта по названию
            search_url = f"{self.base_url}/contacts"
            params = {
                'organization_id': organization_id,
                'contact_name_contains': company_name
            }
            
            headers = {
                'Authorization': f'Zoho-oauthtoken {access_token}',
                'Content-Type': 'application/json'
            }
            
            log_message(f"🔍 Ищу контакт: {company_name} в организации {organization_id}")
            
            response = requests.get(search_url, headers=headers, params=params)
            
            if response.status_code == 200:
                data = response.json()
                contacts = data.get('contacts', [])
                
                if contacts:
                    # Ищем точное совпадение или наиболее похожее
                    exact_match = None
                    best_match = None
                    best_score = 0
                    
                    for contact in contacts:
                        contact_name = contact.get('contact_name', '')
                        company_name_field = contact.get('company_name', '')
                        
                        # Проверяем точное совпадение
                        if (contact_name.lower() == company_name.lower() or 
                            company_name_field.lower() == company_name.lower()):
                            exact_match = contact
                            break
                            
                        # Вычисляем схожесть для частичного совпадения
                        score = self._calculate_similarity(company_name, contact_name)
                        if score > best_score:
                            best_score = score
                            best_match = contact
                    
                    found_contact = exact_match or best_match
                    if found_contact:
                        log_message(f"✅ Найден контакт: {found_contact.get('contact_name')} (ID: {found_contact.get('contact_id')})")
                        
                        # Получаем полную информацию о контакте
                        return self._get_full_contact_details(found_contact.get('contact_id'), organization_id)
                    
                log_message(f"❌ Контакт '{company_name}' не найден в организации {organization_id}")
                return None
                
            else:
                log_message(f"ERROR: Ошибка поиска контакта: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            log_message(f"ERROR: Исключение при поиске контакта: {str(e)}")
            return None
            
    def _get_full_contact_details(self, contact_id: str, organization_id: str) -> Optional[Dict[str, Any]]:
        """Получает полную информацию о контакте по ID"""
        try:
            access_token = get_access_token()
            if not access_token:
                return None
                
            details_url = f"{self.base_url}/contacts/{contact_id}"
            params = {'organization_id': organization_id}
            
            headers = {
                'Authorization': f'Zoho-oauthtoken {access_token}',
                'Content-Type': 'application/json'
            }
            
            response = requests.get(details_url, headers=headers, params=params)
            
            if response.status_code == 200:
                data = response.json()
                contact = data.get('contact', {})
                
                # Извлекаем VAT номер из custom_fields
                vat_number = None
                custom_fields = contact.get('custom_fields', [])
                for field in custom_fields:
                    if field.get('api_name') == 'cf_tax_id':
                        vat_number = field.get('value')
                        break
                
                # Формируем стандартизированные данные контакта
                standardized_contact = {
                    'contact_id': contact.get('contact_id'),
                    'contact_name': contact.get('contact_name'),
                    'company_name': contact.get('company_name'),
                    'contact_type': contact.get('contact_type'),
                    'email': contact.get('email'),
                    'phone': contact.get('phone'),
                    'website': contact.get('website'),
                    'vat_number': vat_number,
                    'billing_address': contact.get('billing_address', {}),
                    'shipping_address': contact.get('shipping_address', {}),
                    'contact_persons': contact.get('contact_persons', []),
                    'custom_fields': custom_fields,
                    'organization_id': organization_id,
                    'last_modified_time': contact.get('last_modified_time'),
                    'created_time': contact.get('created_time')
                }
                
                if vat_number:
                    log_message(f"✅ VAT найден: {vat_number}")
                
                return standardized_contact
                
            else:
                log_message(f"ERROR: Ошибка получения деталей контакта: {response.status_code}")
                return None
                
        except Exception as e:
            log_message(f"ERROR: Исключение при получении деталей контакта: {str(e)}")
            return None
            
    def _calculate_similarity(self, str1: str, str2: str) -> float:
        """Вычисляет схожесть между двумя строками"""
        from difflib import SequenceMatcher
        return SequenceMatcher(None, str1.lower(), str2.lower()).ratio()
        
    def search_in_both_organizations(self, company_name: str) -> Optional[Dict[str, Any]]:
        """
        Ищет контакт в обеих организациях
        
        Args:
            company_name: Название компании для поиска
            
        Returns:
            Словарь с данными контакта или None если не найден
        """
        organizations = {
            "20092948714": "TaVie Europe OÜ",
            "20082562863": "PARKENTERTAINMENT"
        }
        
        for org_id, org_name in organizations.items():
            log_message(f"🔍 Поиск в {org_name} ({org_id})")
            
            contact = self.search_contact_by_name(company_name, org_id)
            if contact:
                contact['organization_name'] = org_name
                return contact
                
        log_message(f"❌ Контакт '{company_name}' не найден ни в одной организации")
        return None


def search_contact_by_name(company_name: str, organization_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Удобная функция для поиска контакта
    
    Args:
        company_name: Название компании
        organization_id: ID организации (если None, ищет в обеих)
        
    Returns:
        Данные контакта или None
    """
    searcher = ZohoContactSearcher()
    
    if organization_id:
        return searcher.search_contact_by_name(company_name, organization_id)
    else:
        return searcher.search_in_both_organizations(company_name)


if __name__ == "__main__":
    # Тест поиска
    result = search_contact_by_name("Horrer Automobile GmbH")
    if result:
        print(f"✅ Найден контакт: {result['contact_name']}")
        print(f"📧 Email: {result.get('email', 'Не указан')}")
        print(f"🏢 Организация: {result.get('organization_name', 'Неизвестно')}")
        if result.get('vat_number'):
            print(f"🔢 VAT: {result['vat_number']}")
    else:
        print("❌ Контакт не найден") 