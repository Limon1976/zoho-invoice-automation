"""
Временный доступ к WorkDrive через публичные ссылки
Пока не обновлены OAuth scopes
"""

import requests
import json
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

def test_folder_access():
    """
    Тестирует доступ к папке через публичную ссылку
    """
    folder_url = "https://workdrive.zoho.eu/folder/1zqms56fb76bbe95e469bacc06a33e010fb84"
    
    print(f"🧪 ТЕСТ: Доступ к папке August")
    print(f"🔗 URL: {folder_url}")
    
    try:
        # Попробуем получить HTML страницу
        response = requests.get(folder_url)
        print(f"📊 Status Code: {response.status_code}")
        print(f"📏 Content Length: {len(response.content)}")
        
        if response.status_code == 200:
            # Проверим содержимое
            content = response.text
            if "workdrive" in content.lower():
                print("✅ Страница WorkDrive загружена")
                
                # Попробуем найти упоминания файлов
                if ".pdf" in content.lower():
                    print("📄 Найдены упоминания PDF файлов")
                else:
                    print("❌ PDF файлы не найдены в HTML")
                    
                return True
            else:
                print("❌ Не похоже на страницу WorkDrive")
                return False
        else:
            print(f"❌ Ошибка доступа: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Исключение: {e}")
        return False

if __name__ == "__main__":
    test_folder_access()


