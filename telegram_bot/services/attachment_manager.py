"""
Унифицированный менеджер для прикрепления файлов к сущностям Zoho Books.
Выделен из handlers.py для переиспользования в BILL, Expense, Invoice и других сущностях.
"""

import os
import logging
import requests
from typing import Optional, Dict, Any
from functions.zoho_api import get_access_token

logger = logging.getLogger(__name__)


class AttachmentManager:
    """Унифицированная работа с прикреплением файлов к Zoho сущностям"""
    
    # Маппинг типов сущностей на URL endpoints
    ENTITY_ENDPOINTS = {
        'bill': 'bills',
        'expense': 'expenses',
        'invoice': 'invoices',
        'salesorder': 'salesorders',
        'purchaseorder': 'purchaseorders',
        'creditnote': 'creditnotes',
        'contact': 'contacts',
        'item': 'items'
    }
    
    @staticmethod
    async def attach_to_entity(
        entity_type: str,
        entity_id: str,
        org_id: str,
        file_path: str,
        access_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Универсальное прикрепление файлов к любой сущности Zoho.
        
        Args:
            entity_type: Тип сущности ('bill', 'expense', 'invoice' и т.д.)
            entity_id: ID сущности в Zoho
            org_id: ID организации
            file_path: Путь к файлу для прикрепления
            access_token: Токен доступа (если None, получит автоматически)
            
        Returns:
            Dict с результатом:
                - success: bool
                - message: str
                - response_data: dict (при успехе)
                - error: str (при ошибке)
        """
        
        # Валидация входных данных
        if entity_type not in AttachmentManager.ENTITY_ENDPOINTS:
            return {
                'success': False,
                'error': f'Неподдерживаемый тип сущности: {entity_type}'
            }
            
        if not os.path.exists(file_path):
            logger.warning(f"⚠️ Файл не найден для прикрепления: {file_path}")
            return {
                'success': False,
                'error': f'Файл не найден: {file_path}'
            }
            
        # Получаем токен если не передан
        if not access_token:
            access_token = get_access_token()
            if not access_token:
                return {
                    'success': False,
                    'error': 'Не удалось получить токен доступа'
                }
        
        # Формируем URL
        endpoint = AttachmentManager.ENTITY_ENDPOINTS[entity_type]
        attach_url = f"https://www.zohoapis.eu/books/v3/{endpoint}/{entity_id}/attachment?organization_id={org_id}"
        
        logger.info(f"📎 Прикрепляем файл {os.path.basename(file_path)} к {entity_type} {entity_id}")
        
        try:
            # Открываем файл и отправляем
            with open(file_path, 'rb') as file_obj:
                files = {'attachment': (os.path.basename(file_path), file_obj)}
                headers = {'Authorization': f'Zoho-oauthtoken {access_token}'}
                
                response = requests.post(attach_url, headers=headers, files=files)
                response_data = response.json() if response.content else {}
                
                logger.info(f"📎 ATTACH response: status={response.status_code}")
                
                # Обработка результата
                if response.status_code in [200, 201]:
                    # Успех - разные API могут возвращать разные структуры
                    if response_data.get('code') == 0 or response_data.get('message') == 'success':
                        logger.info(f"✅ Файл успешно прикреплен к {entity_type} (статус {response.status_code})")
                        return {
                            'success': True,
                            'message': f'Файл успешно прикреплен к {entity_type}',
                            'response_data': response_data
                        }
                    else:
                        # Статус OK, но есть ошибка в ответе
                        error_msg = response_data.get('message', 'Неизвестная ошибка')
                        logger.error(f"❌ Ошибка в ответе: {error_msg}")
                        return {
                            'success': False,
                            'error': error_msg,
                            'response_data': response_data
                        }
                        
                elif response.status_code == 401:
                    # Токен истек - пробуем обновить и повторить
                    logger.info("🔄 Токен истек, обновляю...")
                    new_token = get_access_token()
                    if new_token and new_token != access_token:
                        # Рекурсивный вызов с новым токеном
                        return await AttachmentManager.attach_to_entity(
                            entity_type, entity_id, org_id, file_path, new_token
                        )
                    else:
                        return {
                            'success': False,
                            'error': 'Не удалось обновить токен доступа'
                        }
                        
                else:
                    # Другие ошибки
                    error_msg = response_data.get('message', f'HTTP {response.status_code}')
                    logger.error(f"❌ Ошибка прикрепления файла: {response.status_code} - {error_msg}")
                    return {
                        'success': False,
                        'error': f'Ошибка {response.status_code}: {error_msg}',
                        'response_data': response_data
                    }
                    
        except Exception as e:
            logger.error(f"❌ Исключение при прикреплении файла: {e}")
            return {
                'success': False,
                'error': f'Исключение: {str(e)}'
            }
    
    @staticmethod
    async def attach_multiple(
        entity_type: str,
        entity_id: str,
        org_id: str,
        file_paths: list[str],
        access_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Прикрепление нескольких файлов к одной сущности.
        
        Returns:
            Dict с результатами:
                - success: bool (True если все файлы прикреплены)
                - attached: list[str] (успешно прикрепленные файлы)
                - failed: list[dict] (файлы с ошибками)
        """
        attached = []
        failed = []
        
        for file_path in file_paths:
            result = await AttachmentManager.attach_to_entity(
                entity_type, entity_id, org_id, file_path, access_token
            )
            
            if result['success']:
                attached.append(file_path)
            else:
                failed.append({
                    'file': file_path,
                    'error': result.get('error', 'Unknown error')
                })
                
        return {
            'success': len(failed) == 0,
            'attached': attached,
            'failed': failed
        }
    
    @staticmethod
    def get_attachment_url(entity_type: str, entity_id: str, org_id: str) -> str:
        """
        Получить URL для скачивания прикрепленных файлов.
        
        Returns:
            URL для API запроса списка вложений
        """
        if entity_type not in AttachmentManager.ENTITY_ENDPOINTS:
            raise ValueError(f'Неподдерживаемый тип сущности: {entity_type}')
            
        endpoint = AttachmentManager.ENTITY_ENDPOINTS[entity_type]
        return f"https://www.zohoapis.eu/books/v3/{endpoint}/{entity_id}/attachments?organization_id={org_id}"
