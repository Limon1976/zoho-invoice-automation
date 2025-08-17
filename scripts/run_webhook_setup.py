#!/usr/bin/env python3
"""
Запуск настройки Zoho Books Webhooks
====================================

Удобный скрипт для настройки webhooks в Zoho Books.
Использование: python run_webhook_setup.py
"""

import sys
import asyncio
from pathlib import Path

# Добавляем src в путь
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.scripts.zoho_webhook_setup import main

if __name__ == "__main__":
    print("🔗 Запуск настройки Zoho Books Webhooks")
    print("=" * 50)
    
    # Запускаем настройку
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n❌ Настройка прервана пользователем")
    except Exception as e:
        print(f"\n❌ Ошибка настройки: {e}")
        sys.exit(1) 