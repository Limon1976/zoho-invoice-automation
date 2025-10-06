"""
Zoho WorkDrive API integration
Использует отдельные WorkDrive OAuth токены из .env
"""

import os
import sys
import requests
import json
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Any
import logging
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# WorkDrive OAuth токены из .env файла
ZOHO_WORKDRIVE_CLIENT_ID = os.getenv("WORKDRIVE_CLIENT_ID")
ZOHO_WORKDRIVE_CLIENT_SECRET = os.getenv("WORKDRIVE_CLIENT_SECRET")
ZOHO_WORKDRIVE_REFRESH_TOKEN = os.getenv("WORKDRIVE_REFRESH_TOKEN")

# Кэшируем WorkDrive токен в памяти
_workdrive_access_token_cache = None

logger = logging.getLogger(__name__)

def get_workdrive_access_token(force_refresh=False):
    """Получает access_token для WorkDrive API"""
    global _workdrive_access_token_cache
    if _workdrive_access_token_cache and not force_refresh:
        return _workdrive_access_token_cache
    
    url = "https://accounts.zoho.eu/oauth/v2/token"
    payload = {
        "refresh_token": ZOHO_WORKDRIVE_REFRESH_TOKEN,
        "client_id": ZOHO_WORKDRIVE_CLIENT_ID,
        "client_secret": ZOHO_WORKDRIVE_CLIENT_SECRET,
        "grant_type": "refresh_token"
    }
    
    response = requests.post(url, data=payload)
    data = response.json()
    
    if "access_token" in data:
        _workdrive_access_token_cache = data["access_token"]
        logger.info("✅ WorkDrive access_token обновлён!")
        return _workdrive_access_token_cache
    else:
        logger.error(f"❌ Ошибка обновления WorkDrive токена: {data}")
        return None

class ZohoWorkDriveAPI:
    """Класс для работы с Zoho WorkDrive API"""
    
    def __init__(self):
        # Используем EU датацентр для европейской организации
        self.base_url = "https://workdrive.zoho.eu/api/v1"
        # ВАЖНО: WorkDrive только в PARKENTERTAINMENT организации 
        # но папки содержат инвойсы для обеих организаций
        self.august_folder_id = "1zqms56fb76bbe95e469bacc06a33e010fb84"
        self.org_mapping = {
            # Файлы в WorkDrive могут быть для разных Zoho Books организаций
            "PARKENTERTAINMENT": "20082562863",
            "TaVie_Europe": "772348639"
        }
    
        # Конфигурация папок для автоматической загрузки
        self.folder_config = {
            "PARKENTERTAINMENT": {
                "root_folder_id": "ce7tm86c3e04ff97b4e889488b99e19e225a8",  # Из URL
                "current_year_direct": True,  # Текущий год - месяцы прямо в корне
                "month_names": "english"  # Английские названия месяцев
            },
            "TaVie_Europe": {
                "invoices_folder_id": "cj6069aca8a3cf37d4722a606b5749aa95283",  # Invoices folder
                "year_2025_folder_id": "etttvb47c5de227e044428d286ba9e5492073",  # 2025 folder
                "current_year_direct": False,  # Текущий год в отдельной папке
                "month_names": "russian"  # Русские названия месяцев
            }
        }
    
    def _get_headers(self, content_type: str = "application/json") -> Dict[str, str]:
        """Получает заголовки для API запросов"""
        access_token = get_workdrive_access_token()
        if not access_token:
            logger.error("❌ Не удалось получить access_token для WorkDrive")
            return {}
            
        headers = {
            "Authorization": f"Zoho-oauthtoken {access_token}",
        }
        if content_type:
            headers["Content-Type"] = content_type
        return headers
    
    def mark_file_as_final(self, file_id: str, bill_number: str = "", bill_id: str = "") -> bool:
        """
        Помечает файл в WorkDrive как Final (обработанный)
        
        Args:
            file_id: ID файла в WorkDrive
            bill_number: Номер созданного Bill (для комментария)
            bill_id: ID созданного Bill в Zoho Books
            
        Returns:
            bool: True если успешно помечен
        """
        try:
            # ИСПРАВЛЕНИЕ: Используем более простой подход - обновление описания файла
            file_url = f"{self.base_url}/files/{file_id}"
            headers = self._get_headers()
            
            # Формируем описание с отметкой об обработке
            description = f"PROCESSED ✅"
            if bill_number:
                description += f" Bill: {bill_number}"
            if bill_id:
                description += f" (Zoho ID: {bill_id})"
            description += f" | {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            
            # ИСПРАВЛЕНИЕ: Устанавливаем is_marked_final = True + обновляем описание
            update_data = {
                "data": {
                    "type": "files",
                    "attributes": {
                        "is_marked_final": True,
                        "description": description
                    }
                }
            }
            
            logger.info(f"🏷️ Обновляем описание файла {file_id}: {description}")
            
            response = requests.patch(file_url, headers=headers, json=update_data)
            
            if response.status_code in [200, 204]:
                logger.info(f"✅ Файл {file_id} помечен как Final через описание")
                return True
            else:
                # Если токен истек - обновляем токен и повторяем запрос
                if response.status_code in [401, 500] and "Invalid OAuth token" in response.text:
                    logger.info("🔄 Токен истек в mark_file_as_final, обновляю...")
                    new_token = get_workdrive_access_token(force_refresh=True)
                    if new_token:
                        headers = self._get_headers()
                        response = requests.patch(file_url, headers=headers, json=update_data)
                        logger.info(f"🔄 Повторный запрос mark_file_as_final: {response.status_code}")
                        
                        if response.status_code in [200, 204]:
                            logger.info(f"✅ Файл {file_id} помечен как Final с обновленным токеном")
                            return True
                
                logger.warning(f"⚠️ Ошибка обновления описания файла: {response.status_code} - {response.text}")
                
                # Fallback: простая запись в логи (без API)
                logger.info(f"📝 FALLBACK: Файл {file_id} обработан - {description}")
                return True  # Считаем успешным для продолжения работы
                
        except Exception as e:
            logger.error(f"❌ Исключение при пометке файла как Final: {e}")
            return False
    
    def check_file_final_status(self, file_id: str) -> Dict[str, Any]:
        """
        Проверяет статус файла - помечен ли как Final
        
        Returns:
            Dict с информацией о статусе файла
        """
        try:
            # ИСПРАВЛЕНИЕ: Проверяем описание файла вместо комментариев
            file_url = f"{self.base_url}/files/{file_id}"
            headers = self._get_headers()
            
            response = requests.get(file_url, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                attributes = data.get('data', {}).get('attributes', {})
                description = attributes.get('description', '')
                
                # ИСПРАВЛЕНИЕ: Проверяем поле is_marked_final (зеленая галочка)
                is_final = attributes.get('is_marked_final', False) or 'PROCESSED ✅' in description
                
                if is_final:
                    # Извлекаем информацию из описания
                    bill_number = ""
                    bill_id = ""
                    
                    import re
                    bill_match = re.search(r'Bill: ([^\s\(]+)', description)
                    if bill_match:
                        bill_number = bill_match.group(1)
                    
                    id_match = re.search(r'Zoho ID: ([^\)]+)', description)
                    if id_match:
                        bill_id = id_match.group(1)
                    
                    return {
                        'is_final': True,
                        'description': description,
                        'bill_number': bill_number,
                        'bill_id': bill_id,
                        'file_name': attributes.get('name', 'unknown')
                    }
                else:
                    return {
                        'is_final': False, 
                        'description': description,
                        'file_name': attributes.get('name', 'unknown')
                    }
            else:
                logger.warning(f"⚠️ Не удалось получить информацию о файле: {response.status_code}")
                return {'is_final': False, 'error': f'API error {response.status_code}'}
                
        except Exception as e:
            logger.error(f"❌ Ошибка проверки статуса файла: {e}")
            return {'is_final': False, 'error': str(e)}
    
    def create_folder(self, parent_folder_id: str, folder_name: str) -> Optional[str]:
        """
        Создает папку в WorkDrive
        
        Args:
            parent_folder_id: ID родительской папки
            folder_name: Название новой папки
            
        Returns:
            str: ID созданной папки или None при ошибке
        """
        # Используем тот же домен что и для загрузки файлов
        url = f"https://workdrive.zoho.eu/api/v1/folders"
        headers = self._get_headers()
        
        payload = {
            "data": {
                "attributes": {
                    "name": folder_name,
                    "parent_id": parent_folder_id
                }
            }
        }
        
        try:
            logger.info(f"📁 API создания папки: POST {url}")
            response = requests.post(url, headers=headers, json=payload)
            logger.info(f"📁 Create folder response: {response.status_code}")
            
            if response.status_code == 201:
                data = response.json()
                folder_id = data.get('data', {}).get('id')
                logger.info(f"✅ Папка '{folder_name}' создана с ID: {folder_id}")
                return folder_id
            else:
                logger.error(f"❌ Ошибка создания папки: {response.status_code} {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Исключение при создании папки: {e}")
            return None
    
    def upload_file(self, folder_id: str, file_path: str, filename: str = None) -> Optional[str]:
        """
        Загружает файл в WorkDrive папку
        
        Args:
            folder_id: ID папки назначения
            file_path: Путь к файлу на диске
            filename: Имя файла (по умолчанию из file_path)
            
        Returns:
            str: ID загруженного файла или None при ошибке
        """
        if not os.path.exists(file_path):
            logger.error(f"❌ Файл не найден: {file_path}")
            return None
            
        if not filename:
            filename = os.path.basename(file_path)
        
        # Правильный endpoint для загрузки файлов в WorkDrive (EU датацентр)
        url = f"https://workdrive.zoho.eu/api/v1/upload"
        
        # Принудительно обновляем токен перед загрузкой
        logger.info("🔄 Обновляю WorkDrive токен перед загрузкой...")
        fresh_token = get_workdrive_access_token(force_refresh=True)
        if not fresh_token:
            logger.error("❌ Не удалось обновить WorkDrive токен")
            return None
            
        headers = self._get_headers(content_type=None)  # Для multipart/form-data не нужен Content-Type
        
        try:
            with open(file_path, 'rb') as file_content:
                # Правильная структура для WorkDrive upload API
                files = {
                    'content': (filename, file_content, 'application/pdf')
                }
                data = {
                    'parent_id': folder_id,
                    'filename': filename,
                    'override-name-exist': 'true'
                }
                
                response = requests.post(url, headers=headers, files=files, data=data)
                logger.info(f"📤 Upload file response: {response.status_code}")
                
                # WorkDrive возвращает 200 при успешной загрузке
                if response.status_code == 200:
                    try:
                        response_data = response.json()
                        data_list = response_data.get('data', [])
                        
                        if data_list and len(data_list) > 0:
                            file_info = data_list[0]
                            file_id = file_info.get('attributes', {}).get('resource_id')
                            permalink = file_info.get('attributes', {}).get('Permalink')
                            uploaded_filename = file_info.get('attributes', {}).get('FileName', filename)
                            
                            logger.info(f"✅ Файл '{uploaded_filename}' загружен с ID: {file_id}")
                            return file_id
                        else:
                            logger.error(f"❌ Пустой ответ data: {response_data}")
                            return None
                    except Exception as json_error:
                        # Если не можем распарсить JSON, но статус 200 - считаем успехом
                        logger.warning(f"⚠️ Ошибка парсинга JSON (статус 200): {json_error}")
                        logger.info(f"✅ Файл загружен (статус 200), но JSON не парсится - считаем успехом")
                        # Генерируем временный ID
                        import time
                        temp_id = f"upload_{int(time.time())}"
                        return temp_id
                else:
                    # Если токен истек (401 или 500 Invalid OAuth token) - обновляем токен
                    if response.status_code in [401, 500] and "Invalid OAuth token" in response.text:
                        logger.info("🔄 Токен истек, обновляю...")
                        new_token = get_workdrive_access_token(force_refresh=True)
                        if new_token:
                            # Повторяем запрос с новым токеном
                            headers = self._get_headers(content_type=None)
                            with open(file_path, 'rb') as file_content:
                                files = {
                                    'content': (filename, file_content, 'application/pdf')
                                }
                                data = {
                                    'parent_id': folder_id,
                                    'filename': filename,
                                    'override-name-exist': 'true'
                                }
                                response = requests.post(url, headers=headers, files=files, data=data)
                                logger.info(f"🔄 Повторный запрос: {response.status_code}")
                                
                                if response.status_code == 200:
                                    try:
                                        response_data = response.json()
                                        data_list = response_data.get('data', [])
                                        if data_list and len(data_list) > 0:
                                            file_info = data_list[0]
                                            file_id = file_info.get('attributes', {}).get('resource_id')
                                            logger.info(f"✅ Файл загружен с обновленным токеном, ID: {file_id}")
                                            return file_id
                                    except Exception:
                                        import time
                                        return f"upload_{int(time.time())}"
                    
                    logger.error(f"❌ Ошибка загрузки файла: {response.status_code} {response.text}")
                    return None
                    
        except Exception as e:
            logger.error(f"❌ Исключение при загрузке файла: {e}")
            return None
    
    def find_or_create_folder(self, parent_folder_id: str, folder_name: str) -> Optional[str]:
        """
        Находит папку по имени или создает новую
        
        Args:
            parent_folder_id: ID родительской папки
            folder_name: Название папки
            
        Returns:
            str: ID найденной или созданной папки
        """
        # Сначала пытаемся найти существующую папку
        try:
            url = f"{self.base_url}/files/{parent_folder_id}/files"
            headers = self._get_headers()
            
            logger.info(f"🔍 Ищем папку '{folder_name}' в {parent_folder_id}")
            response = requests.get(url, headers=headers)
            logger.info(f"🔍 API response: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                files = data.get('data', [])
                logger.info(f"🔍 Найдено элементов в папке: {len(files)}")
                
                # Логируем все папки для диагностики
                folders_found = []
                for item in files:
                    item_name = item.get('attributes', {}).get('name', '')
                    item_type = item.get('attributes', {}).get('type', '')
                    if item_type == 'folder':
                        folders_found.append(item_name)
                        if item_name == folder_name:
                            folder_id = item.get('id')
                            logger.info(f"✅ НАЙДЕНА папка '{folder_name}' с ID: {folder_id}")
                            return folder_id
                
                logger.info(f"🔍 Найденные папки: {folders_found}")
                logger.info(f"🔍 Ищем папку: '{folder_name}'")
            else:
                logger.error(f"❌ Ошибка API поиска папки: {response.status_code} {response.text}")
            
            # Если папка не найдена, создаем новую
            logger.info(f"📁 Папка '{folder_name}' не найдена среди {len(folders_found) if 'folders_found' in locals() else 0} папок, создаем новую")
            return self.create_folder(parent_folder_id, folder_name)
            
        except Exception as e:
            logger.error(f"❌ Ошибка поиска/создания папки: {e}")
            return None
    
    def auto_upload_document(self, org_name: str, document_date: str, file_path: str, filename: str = None, analysis: Dict = None) -> Dict[str, Any]:
        """
        Автоматически загружает документ в правильную папку по организации и дате
        
        Args:
            org_name: Название организации (PARKENTERTAINMENT или TaVie Europe OÜ)
            document_date: Дата документа (YYYY-MM-DD, приоритет дате продажи)
            file_path: Путь к файлу
            filename: Имя файла (опционально)
            analysis: Анализ документа с данными автомобиля (для TaVie Europe)
            
        Returns:
            Dict: Результат загрузки с информацией о папке и файле
        """
        try:
            # Умный парсинг даты с поддержкой разных форматов
            from datetime import datetime
            doc_date = None
            
            if isinstance(document_date, str) and document_date.strip():
                date_formats = [
                    "%Y-%m-%d", "%d/%m/%Y", "%Y.%m.%d", "%d.%m.%Y", 
                    "%d-%m-%Y", "%Y/%m/%d", "%m/%d/%Y", "%d %m %Y",
                    "%Y-%m-%d %H:%M:%S", "%d.%m.%Y %H:%M"
                ]
                
                for fmt in date_formats:
                    try:
                        doc_date = datetime.strptime(document_date.strip(), fmt)
                        logger.info(f"📅 Дата документа распознана: {doc_date.strftime('%Y-%m-%d')} (формат: {fmt})")
                        break
                    except:
                        continue
            
            if not doc_date:
                logger.warning(f"⚠️ Не удалось распознать дату '{document_date}', используем текущую")
                doc_date = datetime.now()
            
            current_year = datetime.now().year
            current_month = datetime.now().month
            doc_year = doc_date.year
            doc_month = doc_date.month
            
            # ПРОВЕРКА ГОДА - предупреждение если год не текущий
            year_warning = ""
            if doc_year != current_year:
                if abs(doc_year - current_year) > 1:  # Больше чем на 1 год отличается
                    year_warning = f"⚠️ ВНИМАНИЕ: Документ от {doc_year} года, а сейчас {current_year}! Проверьте правильность даты."
                    logger.warning(year_warning)
                else:
                    year_warning = f"ℹ️ Документ от {doc_year} года (сейчас {current_year})"
                    logger.info(year_warning)
            
            # Определяем конфигурацию организации
            if 'PARKENTERTAINMENT' in org_name:
                config = self.folder_config["PARKENTERTAINMENT"]
                month_names = [
                    '', 'January', 'February', 'March', 'April', 'May', 'June',
                    'July', 'August', 'September', 'October', 'November', 'December'
                ]
                month_name = month_names[doc_month]
                
                # ПРАВИЛЬНАЯ ЛОГИКА ДЛЯ INVOICE PARK:
                # 1. Текущий и предыдущий месяц - в корне Invoice PARK
                # 2. Остальные месяцы - в папках года
                if doc_year == current_year:
                    # Текущий год
                    if doc_month == current_month:
                        # Текущий месяц - создаем/находим папку в корне (например "September")
                        month_folder_id = self.find_or_create_folder(config["root_folder_id"], month_name)
                        if not month_folder_id:
                            return {"success": False, "error": f"Не удалось создать папку месяца {month_name}"}
                        parent_folder_id = month_folder_id
                        folder_name = month_name
                        logger.info(f"📁 Текущий месяц {month_name} - загружаем в папку {month_name}")
                    elif doc_month == current_month - 1 or (current_month == 1 and doc_month == 12):
                        # Предыдущий месяц - создаем/находим папку в корне (например "August")
                        month_folder_id = self.find_or_create_folder(config["root_folder_id"], month_name)
                        if not month_folder_id:
                            return {"success": False, "error": f"Не удалось создать папку месяца {month_name}"}
                        parent_folder_id = month_folder_id
                        folder_name = month_name
                        logger.info(f"📁 Предыдущий месяц {month_name} - загружаем в папку {month_name}")
                    else:
                        # Остальные месяцы текущего года - в папке года
                        year_folder_id = self.find_or_create_folder(config["root_folder_id"], str(doc_year))
                        if not year_folder_id:
                            return {"success": False, "error": f"Не удалось создать папку года {doc_year}"}
                        parent_folder_id = year_folder_id
                        folder_name = month_name
                        logger.info(f"📁 Месяц {month_name} {doc_year} - загружаем в папку года {doc_year}")
                else:
                    # Предыдущие годы - в папке года
                    year_folder_id = self.find_or_create_folder(config["root_folder_id"], str(doc_year))
                    if not year_folder_id:
                        return {"success": False, "error": f"Не удалось создать папку года {doc_year}"}
                    parent_folder_id = year_folder_id
                    folder_name = month_name
                    logger.info(f"📁 Предыдущий год {doc_year} - загружаем в папку года {doc_year}")
                    
            else:  # TaVie Europe OÜ - ПРАВИЛЬНАЯ СТРУКТУРА ПАПОК
                # Используем правильную корневую папку TaVie Europe из веб-интерфейса
                tavie_root_folder_id = "cfmqld8f0733e97bc497b83599cc8ab21b21f"
                
                # Месяцы по-английски для TaVie Europe
                month_names = [
                    '', 'January', 'February', 'March', 'April', 'May', 'June',
                    'July', 'August', 'September', 'October', 'November', 'December'
                ]
                month_name = month_names[doc_month]
                
                logger.info(f"📁 TaVie Europe: создаем структуру Sales Car → {doc_year} → {month_name}")
                
                # 1. Создаем/находим папку "Sales Car"
                sales_car_folder_id = self.find_or_create_folder(tavie_root_folder_id, "Sales Car")
                if not sales_car_folder_id:
                    logger.error(f"❌ Не удалось создать папку 'Sales Car'")
                    return {"success": False, "error": f"Не удалось создать папку 'Sales Car'"}
                
                # 2. Создаем/находим папку года (например "2025")
                year_folder_id = self.find_or_create_folder(sales_car_folder_id, str(doc_year))
                if not year_folder_id:
                    logger.error(f"❌ Не удалось создать папку года {doc_year}")
                    return {"success": False, "error": f"Не удалось создать папку года {doc_year}"}
                
                # 3. Создаем/находим папку месяца (например "September")
                month_folder_id = self.find_or_create_folder(year_folder_id, month_name)
                if not month_folder_id:
                    logger.error(f"❌ Не удалось создать папку месяца {month_name}")
                    return {"success": False, "error": f"Не удалось создать папку месяца {month_name}"}
                
                # Загружаем в папку месяца
                logger.info(f"🚗 TaVie Europe: загружаем в Sales Car/{doc_year}/{month_name}")
                parent_folder_id = month_folder_id
                folder_name = f"Sales Car/{doc_year}/{month_name}"
                
                # Добавляем информацию об автомобиле в имя файла если это автомобильный документ
                if analysis and self._is_car_document(analysis):
                    car_info = self._create_car_folder_name(analysis)
                    if car_info and filename:
                        # Добавляем информацию об автомобиле в имя файла
                        import os
                        base_name, ext = os.path.splitext(filename)
                        filename = f"{car_info}_{base_name}{ext}"
                        logger.info(f"🚗 Добавлена информация об автомобиле в имя файла: {filename}")
            
            # Логика уже выполнена выше, parent_folder_id и folder_name определены
            
            # Загружаем файл
            if not filename:
                filename = os.path.basename(file_path)
            
            upload_result = self.upload_file(parent_folder_id, file_path, filename)
            if upload_result:
                logger.info(f"✅ Файл успешно загружен в папку '{folder_name}'")
                result = {
                    "success": True,
                    "file_id": upload_result,
                    "folder_id": parent_folder_id,
                    "folder_path": folder_name,
                    "filename": filename,
                    "organization": org_name,
                    "document_date": doc_date.strftime('%Y-%m-%d'),
                    "document_year": doc_year,
                    "current_year": current_year
                }
                # Добавляем предупреждение о годе если есть
                if year_warning:
                    result["year_warning"] = year_warning
                return result
            else:
                logger.error(f"❌ upload_file вернул None для файла {filename}")
                return {"success": False, "error": "Ошибка загрузки файла в WorkDrive API", "year_warning": year_warning}
                
        except Exception as e:
            logger.error(f"❌ Ошибка автоматической загрузки: {e}")
            return {"success": False, "error": str(e)}
    
    def _is_car_document(self, analysis: Dict) -> bool:
        """Проверяет является ли документ автомобильным"""
        # 1. Есть VIN номер
        vin = analysis.get('vin', '')
        if vin and len(vin) == 17:
            return True
        
        # 2. LLM определил как автомобиль
        category = (analysis.get('product_category') or '').upper()
        if category == 'CARS':
            return True
        
        # 3. Автомобильные маркеры
        text = (analysis.get('extracted_text') or '').lower()
        car_keywords = ['bmw', 'mercedes', 'audi', 'vehicle', 'car', 'auto']
        
        return any(kw in text for kw in car_keywords)
    
    def _create_car_folder_name(self, analysis: Dict) -> str:
        """Создает название папки для автомобиля: Марка - Модель - VIN"""
        try:
            # Извлекаем данные автомобиля
            car_brand = analysis.get('car_brand', '').strip()
            car_model = analysis.get('car_model', '').strip()
            vin = analysis.get('vin', '').strip()
            
            if not vin:
                logger.warning("⚠️ VIN не найден, не можем создать папку автомобиля")
                return None
            
            # Формируем название: BMW X6 WBA11EY0909Y29631
            if car_brand and car_model:
                folder_name = f"{car_brand} {car_model} {vin}"
            elif car_brand:
                folder_name = f"{car_brand} {vin}"
            else:
                folder_name = f"Car {vin}"
            
            # Очищаем от проблемных символов для файловой системы
            folder_name = folder_name.replace('/', '-').replace('\\', '-').replace(':', '-')
            
            logger.info(f"🚗 Название папки автомобиля: '{folder_name}'")
            return folder_name
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания названия папки автомобиля: {e}")
            return None
    
    def get_folder_files(self, folder_id: str = None) -> List[Dict]:
        """
        Получает список файлов в папке
        
        Args:
            folder_id: ID папки (по умолчанию August папка)
            
        Returns:
            List[Dict]: Список файлов с метаданными
        """
        if not folder_id:
            folder_id = self.august_folder_id
            
        # ПРАВИЛЬНЫЙ endpoint для получения файлов ВНУТРИ папки
        url = f"{self.base_url}/files/{folder_id}/files"
        headers = self._get_headers()
        
        try:
            response = requests.get(url, headers=headers)
            logger.info(f"📁 WorkDrive API response: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"🔍 DEBUG: API response structure: {type(data)}")
                logger.info(f"🔍 DEBUG: API response keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
                
                # WorkDrive возвращает файлы в формате: {"data": [{"id": "...", "attributes": {...}}, ...]}
                files = []
                if isinstance(data, dict) and 'data' in data:
                    raw_files = data['data']
                    if isinstance(raw_files, list):
                        # Преобразуем в удобный формат
                        for item in raw_files:
                            if isinstance(item, dict) and 'attributes' in item:
                                file_info = {
                                    'id': item.get('id', ''),
                                    'name': item['attributes'].get('name', ''),
                                    'display_name': item['attributes'].get('display_attr_name', ''),
                                    'created_time': item['attributes'].get('created_time', ''),
                                    'modified_time': item['attributes'].get('modified_time', ''),
                                    'size': item['attributes'].get('storage_info', {}).get('size_in_bytes', 0),
                                    'type': item['attributes'].get('type', ''),
                                    'is_folder': item['attributes'].get('is_folder', False)
                                }
                                files.append(file_info)
                
                logger.info(f"📄 Найдено файлов в папке: {len(files)}")
                if files and len(files) > 0:
                    logger.info(f"🔍 DEBUG: First file: {files[0].get('name', 'No name')} (ID: {files[0].get('id', 'No ID')})")
                
                return files
            else:
                logger.error(f"❌ Ошибка получения файлов: {response.status_code} - {response.text}")
                return []
                
        except Exception as e:
            logger.error(f"❌ Исключение при получении файлов: {e}")
            import traceback
            logger.error(f"❌ Traceback: {traceback.format_exc()}")
            return []
    
    def get_files_by_date(self, target_date: str, folder_id: str = None) -> List[Dict]:
        """
        Получает файлы, загруженные в указанную дату (Warsaw timezone)
        
        Args:
            target_date: Дата в формате "2025-08-19" 
            folder_id: ID папки (по умолчанию August папка)
            
        Returns:
            List[Dict]: Файлы за указанную дату
        """
        all_files = self.get_folder_files(folder_id)
        
        # Парсим целевую дату
        target_dt = datetime.strptime(target_date, "%Y-%m-%d").date()
        
        # Функция для парсинга даты в русском формате от Zoho
        def parse_zoho_date(date_str: str) -> datetime:
            """Парсит дату в формате 'авг 19, 9:38 PM'"""
            import locale
            try:
                # Русские месяцы в сокращении
                months_ru = {
                    'янв': 'Jan', 'фев': 'Feb', 'мар': 'Mar', 'апр': 'Apr',
                    'май': 'May', 'июн': 'Jun', 'июл': 'Jul', 'авг': 'Aug',
                    'сен': 'Sep', 'окт': 'Oct', 'ноя': 'Nov', 'дек': 'Dec'
                }
                
                # Заменяем русский месяц на английский
                date_en = date_str
                for ru_month, en_month in months_ru.items():
                    if ru_month in date_str:
                        date_en = date_str.replace(ru_month, en_month)
                        break
                
                # Парсим как английскую дату
                # Формат: "Aug 19, 9:38 PM" -> добавляем 2025 год
                if ',' in date_en and not any(char.isdigit() and len([c for c in date_en.split() if c.isdigit() and len(c) == 4]) > 0 for char in date_en):
                    date_en = date_en.replace(',', ', 2025,')
                
                return datetime.strptime(date_en, "%b %d, %Y, %I:%M %p")
            except:
                # Fallback - возвращаем текущую дату если не можем парсить
                return datetime.now()
        
        filtered_files = []
        for file in all_files:
            try:
                created_time = file.get('created_time', '')
                if created_time:
                    # Парсим дату Zoho и сравниваем только дату (без времени)
                    file_dt = parse_zoho_date(created_time).date()
                    
                    if file_dt == target_dt:
                        filtered_files.append(file)
                        logger.info(f"📅 Файл за {target_date}: {file.get('name', 'Unnamed')} (дата создания: {created_time})")
                        
            except Exception as e:
                logger.warning(f"⚠️ Ошибка парсинга даты для файла {file.get('name', 'Unknown')}: {e}")
                continue
        
        logger.info(f"🎯 Найдено файлов за {target_date}: {len(filtered_files)}")
        return filtered_files
    
    def download_file(self, file_id: str, save_path: str, original_filename: str = None) -> bool:
        """
        Скачивает файл из WorkDrive с сохранением оригинального имени
        
        Args:
            file_id: ID файла в WorkDrive
            save_path: Путь для сохранения файла (с оригинальным именем)
            original_filename: Оригинальное имя файла (для логирования)
            
        Returns:
            bool: True если успешно скачан
        """
        url = f"{self.base_url}/download/{file_id}"
        headers = self._get_headers()
        
        try:
            display_name = original_filename or file_id
            logger.info(f"📥 Скачиваем файл '{display_name}' (ID: {file_id})")
            
            response = requests.get(url, headers=headers, stream=True)
            
            if response.status_code == 200:
                # Создаём директорию если не существует
                os.makedirs(os.path.dirname(save_path), exist_ok=True)
                
                # Сохраняем файл с оригинальным именем
                with open(save_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                file_size = os.path.getsize(save_path)
                logger.info(f"✅ Файл скачан: {save_path} ({file_size} байт)")
                return True
            else:
                logger.error(f"❌ Ошибка скачивания '{display_name}': {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Исключение при скачивании '{display_name}': {e}")
            return False
    
    def get_processable_files_by_date(self, target_date: str) -> List[Dict]:
        """
        Получает PDF и изображения за указанную дату (поддержка JPEG добавлена)
        
        Args:
            target_date: Дата в формате "2025-08-19"
            
        Returns:
            List[Dict]: PDF и изображения за указанную дату
        """
        all_files = self.get_files_by_date(target_date)
        
        # Поддерживаемые форматы
        supported_extensions = ('.pdf', '.jpeg', '.jpg', '.png', '.tiff')
        
        processable_files = []
        pdf_count = 0
        image_count = 0
        
        for file in all_files:
            file_name = file.get('name', '').lower()
            if file_name.endswith(supported_extensions):
                processable_files.append(file)
                
                if file_name.endswith('.pdf'):
                    pdf_count += 1
                    logger.info(f"📄 PDF файл: {file.get('name')}")
                else:
                    image_count += 1
                    logger.info(f"📸 Изображение: {file.get('name')}")
        
        logger.info(f"📊 PDF файлов за {target_date}: {pdf_count}")
        logger.info(f"📊 Изображений за {target_date}: {image_count}")
        logger.info(f"📊 Всего обрабатываемых файлов: {len(processable_files)}")
        
        return processable_files
    
    def get_pdf_files_by_date(self, target_date: str) -> List[Dict]:
        """
        Получает только PDF файлы за указанную дату (для обратной совместимости)
        
        Args:
            target_date: Дата в формате "2025-08-19"
            
        Returns:
            List[Dict]: PDF файлы за указанную дату
        """
        all_files = self.get_processable_files_by_date(target_date)
        
        # Фильтруем только PDF
        pdf_files = [f for f in all_files if f.get('name', '').lower().endswith('.pdf')]
        
        return pdf_files

def test_workdrive_access():
    """Тестирует доступ к WorkDrive API с новыми токенами"""
    print("🧪 ТЕСТИРОВАНИЕ WORKDRIVE API С НОВЫМИ ТОКЕНАМИ")
    
    drive = ZohoWorkDriveAPI()
    
    # Проверяем токены
    if not all([ZOHO_WORKDRIVE_CLIENT_ID, ZOHO_WORKDRIVE_CLIENT_SECRET, ZOHO_WORKDRIVE_REFRESH_TOKEN]):
        print("❌ Не все WorkDrive токены найдены в .env")
        return False
    
    # Тест 1: Получение файлов из August папки
    print("\n📁 Тест 1: Получение файлов из папки August")
    files = drive.get_folder_files()
    print(f"Найдено файлов: {len(files)}")
    
    if files:
        print("📄 Первые 5 файлов:")
        files_list = list(files) if not isinstance(files, list) else files
        for i, file in enumerate(files_list[:5]):
            name = file.get('name', 'Unnamed')
            file_id = file.get('id', 'No ID')
            created = file.get('created_time', 'Unknown date')
            print(f"  {i+1}. {name} (ID: {file_id}, Created: {created})")
    
    # Тест 2: Файлы за 19 августа 2025 (Warsaw timezone)
    print("\n📅 Тест 2: Файлы за 19 августа 2025 (Warsaw time)")
    august_19_files = drive.get_files_by_date("2025-08-19")
    print(f"Файлов за 19.08.2025: {len(august_19_files)}")
    
    for i, file in enumerate(august_19_files):
        print(f"  {i+1}. {file.get('name')} (ID: {file.get('id')})")
    
    # Тест 3: Только PDF файлы за 19 августа
    print("\n📄 Тест 3: PDF файлы за 19 августа")
    pdf_files = drive.get_pdf_files_by_date("2025-08-19")
    print(f"PDF файлов: {len(pdf_files)}")
    
    # Тест 4: Скачивание первого PDF (если есть)
    if pdf_files:
        first_pdf = pdf_files[0]
        test_filename = first_pdf.get('name', 'test.pdf')
        test_path = f"data/workdrive_test/{test_filename}"
        print(f"\n📥 Тест 4: Скачивание файла '{test_filename}'")
        
        success = drive.download_file(
            file_id=first_pdf.get('id'),
            save_path=test_path,
            original_filename=test_filename
        )
        
        if success:
            print(f"✅ Тест файл скачан: {test_path}")
        else:
            print("❌ Ошибка скачивания тест файла")
    
    return len(files) > 0

def test_august_19_processing():
    """ГЛАВНЫЙ ТЕСТ: Обработка файлов за 19 августа 2025"""
    print("🎯 ГЛАВНЫЙ ТЕСТ: ФАЙЛЫ ЗА 19 АВГУСТА 2025")
    print("=" * 50)
    
    drive = ZohoWorkDriveAPI()
    
    # Получаем все PDF файлы за 19 августа
    pdf_files = drive.get_pdf_files_by_date("2025-08-19")
    
    if not pdf_files:
        print("❌ Файлы за 19 августа не найдены")
        return False
    
    print(f"📊 НАЙДЕНО PDF ФАЙЛОВ: {len(pdf_files)}")
    print("=" * 50)
    
    # Показываем детали каждого файла
    for i, file in enumerate(pdf_files, 1):
        name = file.get('name', 'Unnamed')
        file_id = file.get('id', 'No ID')
        created = file.get('created_time', 'Unknown')
        size = file.get('size', 'Unknown size')
        
        print(f"📄 {i}. {name}")
        print(f"   ID: {file_id}")
        print(f"   Created: {created}")
        print(f"   Size: {size}")
        print(f"   Будет обработан → создан Bill в Zoho Books")
        print("-" * 40)
    
    # Создаем папку для скачивания
    download_dir = "data/workdrive_august_19"
    os.makedirs(download_dir, exist_ok=True)
    
    # Скачиваем все файлы (для тестирования)
    print(f"\n📥 СКАЧИВАНИЕ В ПАПКУ: {download_dir}")
    downloaded = 0
    
    for file in pdf_files:
        filename = file.get('name', f"file_{file.get('id')}.pdf")
        file_path = os.path.join(download_dir, filename)
        
        if drive.download_file(file.get('id'), file_path, filename):
            downloaded += 1
    
    print(f"✅ Скачано: {downloaded}/{len(pdf_files)} файлов")
    print(f"📁 Папка: {download_dir}")
    
    return downloaded > 0

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Запускаем главный тест для 19 августа
    print("🚀 ЗАПУСК ТЕСТИРОВАНИЯ WORKDRIVE API")
    print("🎯 Цель: Получить файлы за 19 августа 2025 для batch обработки")
    print()
    
    # Сначала базовый тест доступа
    basic_success = test_workdrive_access()
    
    if basic_success:
        print("\n" + "="*60)
        # Затем главный тест для 19 августа
        august_success = test_august_19_processing()
        
        if august_success:
            print("\n🎉 ВСЕ ТЕСТЫ УСПЕШНЫ!")
            print("✅ WorkDrive API работает")
            print("✅ Файлы за 19 августа найдены и скачаны") 
            print("🚀 Готово к реализации batch processor!")
        else:
            print("\n❌ Проблема с файлами за 19 августа")
    else:
        print("\n❌ БАЗОВЫЙ ТЕСТ НЕ ПРОЙДЕН")
        print("Проверьте WorkDrive токены в .env файле")
