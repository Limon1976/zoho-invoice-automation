"""
WorkDrive Scheduler
Планировщик для ежедневного запуска batch processor в 23:59:59 Warsaw time
"""

import asyncio
import logging
import schedule
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from functions.workdrive_batch_processor import run_daily_batch

logger = logging.getLogger(__name__)

def schedule_daily_job():
    """Настраивает ежедневное расписание"""
    # Запуск каждый день в 23:59:59 Warsaw time
    schedule.every().day.at("23:59:59").do(run_job_async)
    logger.info("📅 Запланирован ежедневный запуск в 23:59:59 (Warsaw time)")

def run_job_async():
    """Обёртка для запуска async функции"""
    try:
        warsaw_time = datetime.now(ZoneInfo("Europe/Warsaw"))
        logger.info(f"🚀 Запуск ежедневной обработки WorkDrive в {warsaw_time}")
        
        # Запускаем async функцию в новом event loop
        asyncio.run(run_daily_batch())
        
    except Exception as e:
        logger.error(f"❌ Ошибка в планировщике: {e}")

def run_scheduler():
    """Запускает планировщик"""
    schedule_daily_job()
    
    logger.info("⏰ Планировщик WorkDrive запущен")
    logger.info("🕐 Следующий запуск: каждый день в 23:59:59 (Warsaw time)")
    
    while True:
        schedule.run_pending()
        time.sleep(60)  # Проверяем каждую минуту

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    run_scheduler()


