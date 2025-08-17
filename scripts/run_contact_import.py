#!/usr/bin/env python3
"""
Запуск импорта контактов из Zoho Books
=====================================

Удобный скрипт для импорта всех контактов.
Использование: python run_contact_import.py [--force]
"""

import sys
import asyncio
from pathlib import Path

# Добавляем корневую папку проекта в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.scripts.full_contact_import import main

if __name__ == "__main__":
    print("🚀 Запуск импорта контактов из Zoho Books")
    
    # Проверяем аргументы
    force_refresh = "--force" in sys.argv
    if force_refresh:
        print("⚡ Режим: принудительное обновление")
    
    # Запускаем импорт
    try:
        asyncio.run(main())
        print("✅ Импорт контактов завершен успешно!")
    except Exception as e:
        print(f"❌ Ошибка импорта: {e}")
        sys.exit(1) 