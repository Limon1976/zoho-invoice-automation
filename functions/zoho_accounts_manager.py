"""
Zoho Accounts Manager
Управляет получением и кэшированием accounts из Zoho Books API
"""

import json
import os
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import requests
from .zoho_api import ZohoAPI

class ZohoAccountsManager:
    def __init__(self):
        self.zoho_api = ZohoAPI()
        self.cache_file = "data/zoho_accounts_cache.json"
        self.cache_duration = timedelta(hours=24)  # Кэш на 24 часа
        
        # Создаем папку для кэша если её нет
        os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
    
    def get_all_accounts(self, force_refresh: bool = False) -> List[Dict]:
        """
        Получает все accounts из Zoho Books
        
        Args:
            force_refresh: Принудительно обновить кэш
            
        Returns:
            List[Dict]: Список всех accounts
        """
        # Проверяем кэш
        if not force_refresh:
            cached_accounts = self._load_from_cache()
            if cached_accounts:
                print(f"Loaded {len(cached_accounts)} accounts from cache")
                return cached_accounts
        
        print("Fetching accounts from Zoho API...")
        
        try:
            # Получаем все accounts через Chart of Accounts API
            accounts = self._fetch_accounts_from_api()
            
            # Сохраняем в кэш
            self._save_to_cache(accounts)
            
            print(f"Successfully fetched {len(accounts)} accounts from Zoho")
            return accounts
            
        except Exception as e:
            print(f"Error fetching accounts from Zoho: {e}")
            # Пытаемся загрузить из кэша как fallback
            cached_accounts = self._load_from_cache(ignore_expiry=True)
            if cached_accounts:
                print(f"Using cached accounts as fallback: {len(cached_accounts)} accounts")
                return cached_accounts
            return []
    
    def _fetch_accounts_from_api(self) -> List[Dict]:
        """Получает accounts из Zoho Books API"""
        all_accounts = []
        page = 1
        per_page = 200  # Максимум на страницу
        
        while True:
            try:
                # Используем Chart of Accounts API
                response = self.zoho_api.make_request(
                    'GET',
                    'chartofaccounts',
                    params={
                        'page': page,
                        'per_page': per_page
                    }
                )
                
                if response and 'chartofaccounts' in response:
                    accounts = response['chartofaccounts']
                    all_accounts.extend(accounts)
                    
                    # Проверяем есть ли еще страницы
                    page_context = response.get('page_context', {})
                    if not page_context.get('has_more_page', False):
                        break
                    
                    page += 1
                else:
                    break
                    
            except Exception as e:
                print(f"Error fetching page {page}: {e}")
                break
        
        return all_accounts
    
    def _load_from_cache(self, ignore_expiry: bool = False) -> Optional[List[Dict]]:
        """Загружает accounts из кэша"""
        if not os.path.exists(self.cache_file):
            return None
        
        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            # Проверяем срок действия кэша
            if not ignore_expiry:
                cache_time = datetime.fromisoformat(cache_data['timestamp'])
                if datetime.now() - cache_time > self.cache_duration:
                    return None
            
            return cache_data['accounts']
            
        except Exception as e:
            print(f"Error loading cache: {e}")
            return None
    
    def _save_to_cache(self, accounts: List[Dict]):
        """Сохраняет accounts в кэш"""
        try:
            cache_data = {
                'timestamp': datetime.now().isoformat(),
                'accounts': accounts
            }
            
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            print(f"Error saving cache: {e}")
    
    def find_account_by_name(self, account_name: str, accounts: Optional[List[Dict]] = None) -> Optional[Dict]:
        """
        Находит account по имени
        
        Args:
            account_name: Название account
            accounts: Список accounts (если None, получает из кэша)
            
        Returns:
            Optional[Dict]: Найденный account или None
        """
        if accounts is None:
            accounts = self.get_all_accounts()
        
        # Точное совпадение
        for account in accounts:
            if account.get('account_name', '').lower() == account_name.lower():
                return account
        
        # Частичное совпадение
        for account in accounts:
            if account_name.lower() in account.get('account_name', '').lower():
                return account
        
        return None
    
    def get_accounts_by_type(self, account_type: str, accounts: Optional[List[Dict]] = None) -> List[Dict]:
        """
        Получает accounts по типу
        
        Args:
            account_type: Тип account (expense, income, etc.)
            accounts: Список accounts (если None, получает из кэша)
            
        Returns:
            List[Dict]: Список accounts указанного типа
        """
        if accounts is None:
            accounts = self.get_all_accounts()
        
        return [
            account for account in accounts 
            if account.get('account_type', '').lower() == account_type.lower()
        ]
    
    def search_accounts(self, query: str, accounts: Optional[List[Dict]] = None) -> List[Dict]:
        """
        Поиск accounts по запросу
        
        Args:
            query: Поисковый запрос
            accounts: Список accounts (если None, получает из кэша)
            
        Returns:
            List[Dict]: Список найденных accounts
        """
        if accounts is None:
            accounts = self.get_all_accounts()
        
        query_lower = query.lower()
        results = []
        
        for account in accounts:
            account_name = account.get('account_name', '').lower()
            account_code = account.get('account_code', '').lower()
            
            if (query_lower in account_name or 
                query_lower in account_code):
                results.append(account)
        
        return results
    
    def get_accounts_summary(self) -> Dict:
        """Получает сводку по accounts"""
        accounts = self.get_all_accounts()
        
        summary = {
            'total_accounts': len(accounts),
            'by_type': {},
            'active_accounts': 0,
            'inactive_accounts': 0
        }
        
        for account in accounts:
            # Подсчет по типам
            account_type = account.get('account_type', 'unknown')
            summary['by_type'][account_type] = summary['by_type'].get(account_type, 0) + 1
            
            # Подсчет активных/неактивных
            status = account.get('status', 'active')
            if status == 'active':
                summary['active_accounts'] += 1
            else:
                summary['inactive_accounts'] += 1
        
        return summary

def test_accounts_manager():
    """Тестирует ZohoAccountsManager"""
    manager = ZohoAccountsManager()
    
    print("Testing Zoho Accounts Manager...")
    
    # Получаем все accounts
    accounts = manager.get_all_accounts()
    print(f"Total accounts: {len(accounts)}")
    
    if accounts:
        # Показываем первые 5 accounts
        print("\nFirst 5 accounts:")
        for i, account in enumerate(accounts[:5]):
            print(f"{i+1}. {account.get('account_name')} ({account.get('account_type')})")
        
        # Получаем сводку
        summary = manager.get_accounts_summary()
        print(f"\nSummary: {summary}")
        
        # Тестируем поиск
        search_results = manager.search_accounts("transport")
        print(f"\nTransport-related accounts: {len(search_results)}")
        for account in search_results[:3]:
            print(f"- {account.get('account_name')}")

if __name__ == "__main__":
    test_accounts_manager() 