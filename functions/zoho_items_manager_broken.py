"""
Zoho Books Items Manager
========================

Система управления товарами (ITEMS) в Zoho Books для автомобилей.
"""
import requests
import json
import time
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

# Импорт с обработкой автономного запуска
try:
    from .zoho_api import get_access_token, log_message
except ImportError:
    # Автономный запуск
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from zoho_api import get_access_token, log_message


@dataclass
class CarItemData:
    """Данные для создания автомобильного ITEM"""
    name: str              # "Mercedes Benz V300d_26375"
    sku: str               # VIN номер
    description: str       # Описание из документа
    cost_price: float      # Цена покупки
    selling_price: float   # Цена продажи
    unit: str = "pcs"      # Единица измерения
    tax_id: Optional[str] = None  # ID налога из Zoho
    # НОВЫЕ ПОЛЯ ДЛЯ PARKENTERTAINMENT
    mileage: Optional[int] = None  # Пробег в км для определения категории
    vin: Optional[str] = None      # VIN номер для специального поля
    original_currency: Optional[str] = None  # Валюта документа (EUR, USD)
    document_date: Optional[str] = None      # Дата документа для курса валют
    
    def to_zoho_format(self, organization_id: Optional[str] = None) -> Dict[str, Any]:
        """Конвертация в формат Zoho Books API"""
        item_data = {
            "name": self.name,
            "sku": self.sku,
            "unit": self.unit,
            "item_type": "inventory",
            "product_type": "goods",
            "description": self.description,
            "rate": self.selling_price,  # Цена продажи
            "purchase_rate": self.cost_price,  # Цена покупки
            "purchase_description": self.description,
            "purchase_account_name": "cost of good sold",
            "account_name": "sales",  # Sales account
            "track_inventory": True,
            "inventory_account_name": "inventory asset",
            "inventory_valuation_method": "fifo",
            "initial_stock": 0,  # ВСЕГДА 0
            "initial_stock_rate": 0  # ВСЕГДА 0
        }
        
        # СПЕЦИАЛЬНЫЕ НАСТРОЙКИ ДЛЯ PARKENTERTAINMENT
        if organization_id == "20082562863":  # PARKENTERTAINMENT
            # Определяем категорию по пробегу
            category = "Used car"  # По умолчанию
            if self.mileage is not None and self.mileage <= 100:
                category = "New car"
                log_message(f"🚗 Категория: {category} (пробег: {self.mileage} км)")
            else:
                log_message(f"🚗 Категория: {category} (пробег: {self.mileage or 'N/A'} км)")
            
            item_data.update({
                # Track Inventory уже установлен в базовом item_data
                "track_serial_number": True,    # ✅ Advanced Inventory Tracking: Track Serial Number
                "enable_bin_tracking": True,    # ✅ Track Bin location for this item (альтернативное поле)
                "category_name": category,      # ✅ Category: New car/Used car (исправленное поле)
            })
            
            # Добавляем VIN в специальное поле если есть
            if self.vin:
                # Пробуем разные поля для VIN
                item_data["serial_number"] = self.vin  # Возможно VIN должен быть в serial_number
                item_data["notes"] = f"VIN: {self.vin}"  # Дублируем в notes
                # Альтернативно: item_data["vin"] = self.vin
                log_message(f"🚗 VIN добавлен в serial_number и notes: {self.vin}")
            
            log_message(f"🇵🇱 PARKENTERTAINMENT: Track Serial Number=True, Bin Tracking=True, Category={category}")
        
        # Добавляем tax_id только если он есть
        if self.tax_id:
            item_data["tax_id"] = self.tax_id
            
        return item_data


def convert_currency_to_pln(amount: float, from_currency: str, document_date: str, organization_id: str) -> float:
    """
    Конвертирует валюту в PLN используя курс Zoho на дату документа
    
    Args:
        amount: Сумма для конвертации
        from_currency: Исходная валюта (EUR, USD)
        document_date: Дата документа для определения курса
        organization_id: ID организации для запроса курса
    
    Returns:
        Сумма в PLN
    """
    if from_currency.upper() == "PLN":
        return amount
    
    try:
        # TODO: Реализовать запрос курса валют из Zoho API
        # Пока используем примерные курсы
        rates = {
            "EUR": 4.3,  # 1 EUR = 4.3 PLN (примерный курс)
            "USD": 4.0,  # 1 USD = 4.0 PLN (примерный курс)
        }
        
        rate = rates.get(from_currency.upper(), 1.0)
        converted = amount * rate
        
        log_message(f"💱 Конвертация: {amount} {from_currency} → {converted:.2f} PLN (курс: {rate})")
        return converted
        
    except Exception as e:
        log_message(f"❌ Ошибка конвертации валют: {e}")
        return amount  # Возвращаем оригинальную сумму


class ZohoItemsManager:
    """Менеджер для работы с товарами в Zoho Books"""
    
    def __init__(self):
        self.base_url = "https://www.zohoapis.eu/books/v3"
        self.tavie_org_id = "20092948714"  # TaVie Europe OÜ
        
    def get_tax_export_id(self, organization_id: Optional[str] = None) -> Optional[str]:
        """
        Получение ID налога 'tax export' из Zoho Books
        
        Returns:
            ID налога или None при ошибке
        """
        if not organization_id:
            organization_id = self.tavie_org_id
            
        try:
            access_token = get_access_token()
            if not access_token:
                return None
                
            # Получаем список налогов
            taxes_url = f"{self.base_url}/settings/taxes"
            params = {'organization_id': organization_id}
            
            headers = {
                'Authorization': f'Zoho-oauthtoken {access_token}',
                'Content-Type': 'application/json'
            }
            
            response = requests.get(taxes_url, headers=headers, params=params)
            
            # Если ошибка 401 - обновляем токен и повторяем запрос
            if response.status_code == 401:
                log_message("🔄 Токен истек при получении налогов, обновляю...")
                from .zoho_api import get_access_token
                # Сбрасываем кэшированный токен и получаем новый
                import functions.zoho_api as zoho_api
                zoho_api.ACCESS_TOKEN = None
                new_token = get_access_token()
                if new_token:
                    headers['Authorization'] = f'Zoho-oauthtoken {new_token}'
                    response = requests.get(taxes_url, headers=headers, params=params)
                    log_message(f"🔄 Повторный запрос налогов: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                taxes = data.get('taxes', [])
                
                # Ищем налог с названием "tax export" или tax_percentage = 0
                for tax in taxes:
                    tax_name = tax.get('tax_name', '').lower()
                    tax_percentage = tax.get('tax_percentage', 0)
                    
                    if 'export' in tax_name or tax_percentage == 0:
                        tax_id = tax.get('tax_id')
                        log_message(f"✅ Найден tax export: {tax.get('tax_name')} (ID: {tax_id})")
                        return tax_id
                        
                # Если не найден, используем первый с 0%
                for tax in taxes:
                    if tax.get('tax_percentage', 0) == 0:
                        tax_id = tax.get('tax_id')
                        log_message(f"✅ Используем налог 0%: {tax.get('tax_name')} (ID: {tax_id})")
                        return tax_id
                        
                log_message(f"⚠️ Налог 'tax export' не найден, доступные налоги:")
                for tax in taxes[:5]:  # Показываем первые 5
                    log_message(f"   - {tax.get('tax_name')}: {tax.get('tax_percentage')}% (ID: {tax.get('tax_id')})")
                    
                return None
                
            else:
                log_message(f"ERROR: Ошибка получения налогов: {response.status_code}")
                return None
                
        except Exception as e:
            log_message(f"ERROR: Исключение при получении tax_id: {str(e)}")
            return None
            
    def get_all_items_sku(self, organization_id: Optional[str] = None) -> List[str]:
        """
        Получение всех SKU из Zoho Books
        
        Returns:
            Список всех SKU в организации
        """
        if not organization_id:
            organization_id = self.tavie_org_id
            
        try:
            access_token = get_access_token()
            if not access_token:
                log_message("ERROR: Не удалось получить access token")
                return []
                
            # Получаем список всех товаров
            items_url = f"{self.base_url}/items"
            params = {
                'organization_id': organization_id,
                'per_page': 200  # Максимум за запрос
            }
            
            headers = {
                'Authorization': f'Zoho-oauthtoken {access_token}',
                'Content-Type': 'application/json'
            }
            
            all_skus = []
            page = 1
            
            while True:
                params['page'] = page
                log_message(f"🔍 Загружаю ITEMS страница {page}")
                
                response = requests.get(items_url, headers=headers, params=params)
                
                if response.status_code == 200:
                    data = response.json()
                    items = data.get('items', [])
                    
                    if not items:
                        break  # Больше нет товаров
                        
                    # Извлекаем SKU
                    page_skus = [item.get('sku', '') for item in items if item.get('sku')]
                    all_skus.extend(page_skus)
                    
                    log_message(f"✅ Страница {page}: найдено {len(page_skus)} SKU")
                    
                    # Проверяем есть ли еще страницы
                    page_context = data.get('page_context', {})
                    if not page_context.get('has_more_page', False):
                        break
                        
                    page += 1
                    time.sleep(0.5)  # Пауза между запросами
                    
                else:
                    log_message(f"ERROR: Ошибка получения ITEMS: {response.status_code} - {response.text}")
                    break
                    
            log_message(f"✅ Всего загружено SKU: {len(all_skus)}")
            return all_skus
            
        except Exception as e:
            log_message(f"ERROR: Исключение при получении SKU: {str(e)}")
            return []
            
    def check_sku_exists(self, vin: str, organization_id: Optional[str] = None) -> bool:
        """
        Проверка существования VIN как SKU в Zoho
        
        Args:
            vin: VIN номер для проверки
            organization_id: ID организации
            
        Returns:
            True если SKU существует, False если нет
        """
        if not organization_id:
            organization_id = self.tavie_org_id
            
        try:
            access_token = get_access_token()
            if not access_token:
                return False
                
            # Поиск товара по SKU
            search_url = f"{self.base_url}/items"
            params = {
                'organization_id': organization_id,
                'sku': vin
            }
            
            headers = {
                'Authorization': f'Zoho-oauthtoken {access_token}',
                'Content-Type': 'application/json'
            }
            
            response = requests.get(search_url, headers=headers, params=params)
            
            # Если ошибка 401 - обновляем токен и повторяем запрос
            if response.status_code == 401:
                log_message("🔄 Токен истек при проверке SKU, обновляю...")
                from .zoho_api import get_access_token
                # Сбрасываем кэшированный токен и получаем новый
                import functions.zoho_api as zoho_api
                zoho_api.ACCESS_TOKEN = None
                new_token = get_access_token()
                if new_token:
                    headers['Authorization'] = f'Zoho-oauthtoken {new_token}'
                    response = requests.get(search_url, headers=headers, params=params)
                    log_message(f"🔄 Повторный запрос SKU: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                items = data.get('items', [])
                
                for item in items:
                    if item.get('sku') == vin:
                        log_message(f"✅ SKU {vin} уже существует: {item.get('name')}")
                        return True
                        
                log_message(f"🆕 SKU {vin} не найден - можно создавать")
                return False
                
            else:
                log_message(f"ERROR: Ошибка поиска SKU: {response.status_code}")
                return False
                
        except Exception as e:
            log_message(f"ERROR: Исключение при проверке SKU: {str(e)}")
            return False
            
    def create_car_item(self, car_data: CarItemData, organization_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Создание товара для автомобиля в Zoho Books
        
        Args:
            car_data: Данные автомобиля
            organization_id: ID организации
            
        Returns:
            Созданный товар или None при ошибке
        """
        if not organization_id:
            organization_id = self.tavie_org_id
            
        try:
            # Проверяем что SKU не существует
            if self.check_sku_exists(car_data.sku, organization_id):
                log_message(f"❌ ITEM с SKU {car_data.sku} уже существует!")
                return None
                
            # Получаем правильный tax_id для экспорта
            if not car_data.tax_id:
                tax_id = self.get_tax_export_id(organization_id)
                if tax_id:
                    car_data.tax_id = tax_id
                else:
                    log_message("⚠️ Не удалось получить tax_id, создаем без налога")
                
            access_token = get_access_token()
            if not access_token:
                log_message("ERROR: Не удалось получить access token")
                return None
                
            # Создаем товар
            create_url = f"{self.base_url}/items"
            params = {'organization_id': organization_id}
            
            headers = {
                'Authorization': f'Zoho-oauthtoken {access_token}',
                'Content-Type': 'application/json'
            }
            
            item_data = car_data.to_zoho_format(organization_id)
            log_message(f"🚗 Создаю ITEM: {car_data.name} (SKU: {car_data.sku})")
            log_message(f"📋 DEBUG: Отправляемый JSON в Zoho: {item_data}")
            
            response = requests.post(create_url, headers=headers, params=params, json=item_data)
            
            # Если ошибка 401 - обновляем токен и повторяем запрос
            if response.status_code == 401:
                log_message("🔄 Токен истек, обновляю и повторяю запрос...")
                from .zoho_api import get_access_token
                # Сбрасываем кэшированный токен и получаем новый
                import functions.zoho_api as zoho_api
                zoho_api.ACCESS_TOKEN = None
                new_token = get_access_token()
                if new_token:
                    headers['Authorization'] = f'Zoho-oauthtoken {new_token}'
                    response = requests.post(create_url, headers=headers, params=params, json=item_data)
                    log_message(f"🔄 Повторный запрос: {response.status_code}")
                else:
                    log_message("❌ Не удалось обновить токен")
            
            if response.status_code == 201:
                data = response.json()
                created_item = data.get('item', {})
                
                log_message(f"✅ ITEM создан успешно!")
                log_message(f"   ID: {created_item.get('item_id')}")
                log_message(f"   Name: {created_item.get('name')}")
                log_message(f"   SKU: {created_item.get('sku')}")
                
                # Обновляем локальный кэш SKU сразу после создания
                try:
                    from .sku_cache_manager import SKUCacheManager
                    sku_manager = SKUCacheManager()
                    sku_manager.add_sku_to_cache(car_data.sku, organization_id)
                    log_message(f"✅ SKU {car_data.sku} добавлен в локальный кэш")
                except Exception as e:
                    log_message(f"⚠️ Не удалось обновить кэш SKU: {str(e)}")
                
                return created_item
                
            else:
                log_message(f"ERROR: Ошибка создания ITEM: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            log_message(f"ERROR: Исключение при создании ITEM: {str(e)}")
            return None
    
    def get_item_by_sku(self, sku: str, organization_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Получение товара по SKU из Zoho Books
        
        Args:
            sku: SKU товара для поиска
            organization_id: ID организации
            
        Returns:
            Найденный товар или None если не найден
        """
        if not organization_id:
            organization_id = self.tavie_org_id
            
        try:
            access_token = get_access_token()
            if not access_token:
                log_message("ERROR: Не удалось получить access token")
                return None
                
            # Ищем товар по SKU
            search_url = f"{self.base_url}/items"
            params = {
                'organization_id': organization_id,
                'sku': sku
            }
            
            headers = {
                'Authorization': f'Zoho-oauthtoken {access_token}',
                'Content-Type': 'application/json'
            }
            
            response = requests.get(search_url, headers=headers, params=params)
            
            if response.status_code == 200:
                data = response.json()
                items = data.get('items', [])
                
                if items:
                    found_item = items[0]  # Первый найденный товар
                    log_message(f"✅ Найден ITEM по SKU {sku}: {found_item.get('name')}")
                    return found_item
                else:
                    log_message(f"❌ ITEM с SKU {sku} не найден")
                    return None
                    
            else:
                log_message(f"ERROR: Ошибка поиска ITEM: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            log_message(f"ERROR: Исключение при поиске ITEM: {str(e)}")
            return None
    
    def update_car_item(self, car_data: CarItemData, organization_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Обновление товара для автомобиля в Zoho Books
        
        Args:
            car_data: Обновленные данные автомобиля
            organization_id: ID организации
            
        Returns:
            Обновленный товар или None при ошибке
        """
        if not organization_id:
            organization_id = self.tavie_org_id
            
        try:
            # Ищем существующий товар по SKU
            existing_item = self.get_item_by_sku(car_data.sku, organization_id)
            if not existing_item:
                log_message(f"❌ ITEM с SKU {car_data.sku} не найден для обновления!")
                return None
                
            item_id = existing_item.get('item_id')
            if not item_id:
                log_message(f"❌ Не удалось получить item_id для SKU {car_data.sku}")
                return None
                
            # Получаем правильный tax_id для экспорта (если не указан)
            if not car_data.tax_id:
                tax_id = self.get_tax_export_id(organization_id)
                if tax_id:
                    car_data.tax_id = tax_id
                else:
                    log_message("⚠️ Не удалось получить tax_id, обновляем без изменения налога")
                
            access_token = get_access_token()
            if not access_token:
                log_message("ERROR: Не удалось получить access token")
                return None
                
            # Обновляем товар
            update_url = f"{self.base_url}/items/{item_id}"
            params = {'organization_id': organization_id}
            
            headers = {
                'Authorization': f'Zoho-oauthtoken {access_token}',
                'Content-Type': 'application/json'
            }
            
            item_data = car_data.to_zoho_format(organization_id)
            log_message(f"🔄 Обновляю ITEM: {car_data.name} (SKU: {car_data.sku})")
            
            response = requests.put(update_url, headers=headers, params=params, json=item_data)
            
            if response.status_code == 200:
                data = response.json()
                updated_item = data.get('item', {})
                
                log_message(f"✅ ITEM обновлен успешно!")
                log_message(f"   ID: {updated_item.get('item_id')}")
                log_message(f"   Name: {updated_item.get('name')}")
                log_message(f"   SKU: {updated_item.get('sku')}")
                log_message(f"   New Rate: {updated_item.get('rate')}")
                
                return updated_item
                
            else:
                log_message(f"ERROR: Ошибка обновления ITEM: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            log_message(f"ERROR: Исключение при обновлении ITEM: {str(e)}")
            return None
            
    def process_car_document(self, document_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """
        Обработка автомобильного документа и создание ITEM если нужно
        
        Args:
            document_analysis: Результат анализа документа
            
        Returns:
            Результат обработки с информацией о созданном/существующем ITEM
        """
        try:
            # Проверяем что это автомобиль
            if not document_analysis.get('is_car_related'):
                return {
                    'status': 'not_car',
                    'message': 'Документ не связан с автомобилем'
                }
                
            # Извлекаем данные
            vin = document_analysis.get('vin') or document_analysis.get('item_sku')
            car_name = document_analysis.get('car_item_name')
            description = document_analysis.get('item_description') or document_analysis.get('item_details')
            cost_price = document_analysis.get('total_amount', 0)
            
            if not vin:
                return {
                    'status': 'error',
                    'message': 'VIN номер не найден в документе'
                }
                
            if not car_name:
                return {
                    'status': 'error', 
                    'message': 'Название автомобиля не определено'
                }
                
            # Проверяем существование SKU
            if self.check_sku_exists(vin):
                return {
                    'status': 'exists',
                    'message': f'ITEM с VIN {vin} уже существует в Zoho',
                    'vin': vin,
                    'car_name': car_name
                }
                
            # Создаем новый ITEM
            selling_price = document_analysis.get('selling_price', float(cost_price) if cost_price else 0.0)
            
            car_data = CarItemData(
                name=car_name,
                sku=vin,
                description=description or f"Автомобиль {car_name}",
                cost_price=float(cost_price) if cost_price else 0.0,
                selling_price=float(selling_price)
            )
            
            created_item = self.create_car_item(car_data)
            
            if created_item:
                # Обновляем локальный кэш SKU
                try:
                    from .sku_cache_manager import SKUCacheManager
                    sku_manager = SKUCacheManager()
                    sku_manager.add_sku_to_cache(vin, self.tavie_org_id)
                    log_message(f"✅ SKU {vin} добавлен в локальный кэш")
                except Exception as e:
                    log_message(f"⚠️ Не удалось обновить кэш SKU: {str(e)}")
                
                return {
                    'status': 'created',
                    'message': f'ITEM успешно создан в Zoho',
                    'item_id': created_item.get('item_id'),
                    'item_name': created_item.get('name'),
                    'vin': vin,
                    'cost_price': cost_price
                }
            else:
                return {
                    'status': 'error',
                    'message': 'Ошибка создания ITEM в Zoho'
                }
                
        except Exception as e:
            log_message(f"ERROR: Исключение при обработке автомобильного документа: {str(e)}")
            return {
                'status': 'error',
                'message': f'Ошибка обработки: {str(e)}'
            }


def create_car_item_from_document(document_analysis: Dict[str, Any]) -> Dict[str, Any]:
    """
    Удобная функция для создания ITEM из анализа документа
    
    Args:
        document_analysis: Результат анализа документа
        
    Returns:
        Результат создания ITEM
    """
    manager = ZohoItemsManager()
    return manager.process_car_document(document_analysis)


def update_car_item_from_document(document_analysis: Dict[str, Any]) -> Dict[str, Any]:
    """
    Удобная функция для обновления ITEM из анализа документа
    
    Args:
        document_analysis: Результат анализа документа (должен содержать selling_price)
        
    Returns:
        Результат обновления ITEM
    """
    try:
        # Проверяем что это автомобиль
        if not document_analysis.get('is_car_related'):
            return {
                'status': 'error',
                'message': 'Документ не связан с автомобилем'
            }
            
        # Извлекаем данные
        vin = document_analysis.get('vin') or document_analysis.get('item_sku')
        car_name = document_analysis.get('car_item_name')
        description = document_analysis.get('item_description') or document_analysis.get('item_details')
        cost_price = document_analysis.get('total_amount', 0)
        selling_price = document_analysis.get('selling_price')
        
        if not vin:
            return {
                'status': 'error',
                'message': 'VIN номер не найден в документе'
            }
            
        if not car_name:
            return {
                'status': 'error', 
                'message': 'Название автомобиля не определено'
            }
            
        if not selling_price:
            return {
                'status': 'error',
                'message': 'Цена продажи не указана'
            }
            
        # Создаем объект с данными для обновления
        car_data = CarItemData(
            name=car_name,
            sku=vin,
            description=description or f"Автомобиль {car_name}",
            cost_price=float(cost_price) if cost_price else 0.0,
            selling_price=float(selling_price),
            unit="pcs"
        )
        
        # Обновляем ITEM через менеджер
        manager = ZohoItemsManager()
        updated_item = manager.update_car_item(car_data)
        
        if updated_item:
            return {
                'status': 'success',
                'message': f'ITEM {car_name} успешно обновлен',
                'item_id': updated_item.get('item_id'),
                'name': updated_item.get('name'),
                'sku': updated_item.get('sku'),
                'cost_price': updated_item.get('purchase_rate', 0),
                'selling_price': updated_item.get('rate', selling_price)
            }
        else:
            return {
                'status': 'error',
                'message': f'Не удалось обновить ITEM для VIN {vin}'
            }
            
    except Exception as e:
        return {
            'status': 'error',
            'message': f'Ошибка обновления ITEM: {str(e)}'
        }


if __name__ == "__main__":
    # Тест получения SKU
    manager = ZohoItemsManager()
    
    print("🔍 Загружаю все SKU из TaVie Europe...")
    skus = manager.get_all_items_sku()
    print(f"✅ Найдено SKU: {len(skus)}")
    
    if skus:
        print("📋 Первые 10 SKU:")
        for i, sku in enumerate(skus[:10]):
            print(f"   {i+1}. {sku}")
            
    # Тест проверки конкретного VIN
    test_vin = "W1V44781313926375"
    exists = manager.check_sku_exists(test_vin)
    print(f"\n🔍 Проверка VIN {test_vin}: {'❌ Существует' if exists else '✅ Не найден'}") 