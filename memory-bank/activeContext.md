# Active Context: Zoho Invoice Automation

## Current Work Focus
**WORKDRIVE BATCH PROCESSOR ПОЛНОСТЬЮ НАСТРОЕН**
- Завершена настройка автоматической обработки файлов из WorkDrive
- Исправлена логика филиалов для HIBISPOL поставщиков
- Реализован Mark as Final с зелеными галочками в WorkDrive
- Настроены Telegram уведомления для всех сценариев обработки
- Система готова к ежедневной автоматической работе

## Recent Changes
- **18 сентября 2025**: WorkDrive Batch Processor полностью настроен и протестирован
- **Mark as Final**: Реализована автоматическая пометка файлов как Final в WorkDrive
- **Логика филиалов**: Исправлена для HIBISPOL (БЕЗ маркеров → Iris, С praga/wileńska → Wileńska)
- **Синхронизация дубликатов**: Обработка ошибки 13011 как триггер для синхронизации
- **Telegram интеграция**: Уведомления для всех сценариев (создание, синхронизация, ошибки)
- **Тестирование**: Успешно протестировано на файлах 22-27 августа

## Next Steps
- **Запустить WorkDrive автоматизацию** в продакшене для ежедневной обработки
- **Продолжить handlers_v2** разработку параллельно с рабочей системой
- **Завершить CallbackRouterV2** - маршрутизация callback запросов
- **Тестировать handlers_v2** через bot_v2_test.py
- **Планировать интеграцию** новой архитектуры с рабочими процессами

## Active Decisions and Considerations
- **Memory Bank интеграция**: Полностью настроена через MCP сервер
- **Архитектура**: Современная структура в src/ с dependency injection
- **AI фреймворки**: Использование PydanticAI 0.4.2 для агентов
- **Безопасность**: Соблюдение Flow Control правил (DIAGNOSE → OPTIONS → WAIT → PATCH)

## Important Patterns and Preferences
- **Язык проекта**: Польский приоритетный для PARKENTERTAINMENT
- **VAT обработка**: Автоматические префиксы (PL-, IE-, и т.д.)
- **Контакты**: Pavel Kaliadka исключается из supplier contacts
- **Телеграм бот**: Всегда запуск в venv и из корня проекта
- **Линтер**: КРИТИЧЕСКИ ВАЖНО исправлять ВСЕ ошибки
- **Подтверждения**: Flow Control требует подтверждения перед изменениями

## Learnings and Project Insights
- **PDFPlumber приоритет**: При наличии текстового слоя избегать OCR дубликатов
- **Zoho Books ссылки**: Правильный формат https://books.zoho.eu/app/{org_id}#/inventory/items/{item_id}
- **Автомобили**: VIN как SKU, проверка дубликатов перед созданием ITEM
- **Цветочный бизнес**: Browary относится только к Iris flowers atelier, НЕ к Wileńska
- **Memory Bank**: Автоматические обновления при создании файлов/изменении архитектуры

## Current Technical Status
- **Virtual Environment**: venv/ активна и готова
- **Dependencies**: requirements-optimized-2025.txt обновлен
- **AI Libraries**: Pydantic V2.11.7, PydanticAI 0.4.2, все современные SDK
- **Memory Bank MCP**: Сервер развернут в mcp_servers/mcp-memory-bank/
- **Кэш данных**: Контакты и SKU кэш актуальны
- **Telegram Bot**: Требует проверки статуса после восстановления
