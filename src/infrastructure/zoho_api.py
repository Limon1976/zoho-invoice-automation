"""
Zoho API Client
===============

Клиент для работы с Zoho Books API.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
import asyncio
import httpx
import logging

logger = logging.getLogger(__name__)


class ZohoAPIClient:
    """Клиент для работы с Zoho Books API"""
    
    def __init__(self, client_id: str, client_secret: str, refresh_token: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.access_token: Optional[str] = None
        # Используем правильный zohoapis домен для EU региона
        self.base_url = "https://www.zohoapis.eu/books/v3"
        
        # HTTP клиент с таймаутами
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
        )
    
    async def get_contacts(self, 
                          organization_id: str, 
                          page: int = 1, 
                          per_page: int = 200) -> Optional[Dict[str, Any]]:
        """Получение списка контактов"""
        try:
            url = f"{self.base_url}/contacts"
            params = {
                "organization_id": organization_id,
                "page": page,
                "per_page": per_page
            }
            
            response = await self._make_request("GET", url, params=params)
            return response
            
        except Exception as e:
            logger.error(f"Ошибка получения контактов: {e}")
            return None
    
    async def get_contact_details(self, 
                                 organization_id: str, 
                                 contact_id: str) -> Optional[Dict[str, Any]]:
        """Получение детальной информации о контакте"""
        try:
            url = f"{self.base_url}/contacts/{contact_id}"
            params = {"organization_id": organization_id}
            
            response = await self._make_request("GET", url, params=params)
            return response.get("contact") if response else None
            
        except Exception as e:
            logger.error(f"Ошибка получения деталей контакта {contact_id}: {e}")
            return None

    async def search_contacts(
        self,
        organization_id: str,
        contact_type: Optional[str] = None,
        contact_name_contains: Optional[str] = None,
        email_contains: Optional[str] = None,
        page: int = 1,
        per_page: int = 200,
    ) -> Optional[Dict[str, Any]]:
        """Поиск контактов по фильтрам (имя, email, тип).

        Возвращает сырой ответ API (dict) с ключом "contacts" при успехе.
        """
        try:
            url = f"{self.base_url}/contacts"
            params: Dict[str, Any] = {
                "organization_id": organization_id,
                "page": page,
                "per_page": per_page,
            }
            if contact_type:
                params["contact_type"] = contact_type
            if contact_name_contains:
                params["contact_name_contains"] = contact_name_contains
            if email_contains:
                params["email_contains"] = email_contains

            response = await self._make_request("GET", url, params=params)
            return response
        except Exception as e:
            logger.error(f"Ошибка поиска контактов: {e}")
            return None
    
    async def create_contact(self, 
                           contact_data: Dict[str, Any], 
                           organization_id: str) -> Optional[Dict[str, Any]]:
        """Создание нового контакта"""
        try:
            url = f"{self.base_url}/contacts"
            params = {"organization_id": organization_id}
            
            response = await self._make_request("POST", url, params=params, json=contact_data)
            return response
            
        except Exception as e:
            logger.error(f"Ошибка создания контакта: {e}")
            return None
    
    async def update_contact(self, 
                           contact_id: str,
                           contact_data: Dict[str, Any], 
                           organization_id: str) -> Optional[Dict[str, Any]]:
        """Обновление контакта"""
        try:
            url = f"{self.base_url}/contacts/{contact_id}"
            params = {"organization_id": organization_id}
            
            # API допускает оба формата: плоский JSON или {"contact": {...}}.
            # Оставим плоский, как в других местах.
            response = await self._make_request("PUT", url, params=params, json=contact_data)
            return response
            
        except Exception as e:
            logger.error(f"Ошибка обновления контакта {contact_id}: {e}")
            return None
    
    async def create_webhook(self, 
                           webhook_data: Dict[str, Any], 
                           organization_id: str) -> bool:
        """Создание webhook"""
        try:
            url = f"{self.base_url}/webhooks"
            params = {"organization_id": organization_id}
            
            response = await self._make_request("POST", url, params=params, json=webhook_data)
            return response is not None
            
        except Exception as e:
            logger.error(f"Ошибка создания webhook: {e}")
            return False

    async def get_contact_custom_fields(self, organization_id: str) -> Optional[Dict[str, Any]]:
        """Возвращает метаданные кастомных полей модуля contacts (для получения index/label)."""
        try:
            url = f"{self.base_url}/settings/customfields"
            params = {"organization_id": organization_id, "module": "contacts"}
            response = await self._make_request("GET", url, params=params)
            return response
        except Exception as e:
            logger.error(f"Ошибка получения customfields (contacts): {e}")
            return None
    
    async def _make_request(self, 
                          method: str, 
                          url: str, 
                          params: Optional[Dict] = None,
                          json: Optional[Dict] = None) -> Optional[Dict[str, Any]]:
        """Выполнение HTTP запроса к Zoho API"""
        try:
            # Проверяем и обновляем access token
            if not self.access_token:
                await self._refresh_access_token()
            
            headers = {
                "Authorization": f"Zoho-oauthtoken {self.access_token}",
                "Content-Type": "application/json"
            }
            
            response = await self.client.request(
                method=method,
                url=url,
                params=params,
                json=json,
                headers=headers
            )
            
            # Проверяем статус ответа
            if response.status_code == 401:
                # Токен истек, обновляем и повторяем запрос
                await self._refresh_access_token()
                headers["Authorization"] = f"Zoho-oauthtoken {self.access_token}"
                
                response = await self.client.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json,
                    headers=headers
                )
            
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as e:
                # Расширенный лог с телом запроса/ответа для диагностики
                try:
                    safe_json = json if not isinstance(json, dict) else {k: (v if k.lower() != 'authorization' else '***') for k, v in json.items()}
                except Exception:
                    safe_json = json
                try:
                    logger.error(f"Zoho {method} {url} params={params} payload={safe_json} -> {response.status_code} {response.text}")
                except Exception:
                    logger.error(f"Zoho {method} {url} -> {response.status_code}")
                raise
            return response.json()
            
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP ошибка {e.response.status_code}: {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Ошибка запроса к Zoho API: {e}")
            return None
    
    async def _refresh_access_token(self):
        """Обновление access token"""
        try:
            # Используем EU регион как в рабочей конфигурации
            url = "https://accounts.zoho.eu/oauth/v2/token"
            data = {
                "refresh_token": self.refresh_token,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "refresh_token"
            }
            
            response = await self.client.post(url, data=data)
            
            # Добавляем отладку для понимания ответа
            logger.info(f"OAuth response status: {response.status_code}")
            logger.info(f"OAuth response headers: {dict(response.headers)}")
            
            if response.status_code != 200:
                logger.error(f"OAuth error response: {response.text}")
            response.raise_for_status()
            
            token_data = response.json()
            logger.info(f"Token data received: {list(token_data.keys())}")
            
            # Проверяем наличие access_token в ответе
            if "access_token" not in token_data:
                logger.error(f"No access_token in response. Full response: {token_data}")
                raise ValueError("access_token not found in OAuth response")
            
            self.access_token = token_data["access_token"]
            logger.info("Access token обновлен успешно")
            
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP ошибка при обновлении токена: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Ошибка обновления access token: {e}")
            raise
    
    async def close(self):
        """Закрытие HTTP клиента"""
        await self.client.aclose() 