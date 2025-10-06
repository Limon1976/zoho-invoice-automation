# System Patterns: Zoho Invoice Automation

## System Architecture

### Общая архитектура:
```
PDF Document → OCR (Google Vision) → AI Analysis (OpenAI GPT-4) → Zoho Books API
                                                ↓
                              Telegram Bot ← Data Validation → Cache System
```

### Модульная структура:
- **functions/**: Основная логика обработки документов
- **src/**: Современная архитектура с dependency injection, async/await
- **telegram_bot/**: Интерфейс пользователя через Telegram
- **mcp_connector/**: MCP коннектор для расширяемости
- **mcp_servers/**: Memory Bank MCP сервер

## Key Technical Decisions

- **Pydantic V2 + PydanticAI**: Современные фреймворки для типизации и AI агентов
- **FastAPI**: RESTful API сервер для веб-интерфейса
- **Async/Await**: Асинхронная обработка для производительности
- **PDFPlumber приоритет**: При наличии текстового слоя избегать OCR дубликатов
- **Memory Bank MCP**: Автоматическая интеграция для контекста между сессиями
- **Virtual Environment**: Обязательный venv для изоляции зависимостей
- **Flow Control**: DIAGNOSE → OPTIONS → WAIT → PATCH для безопасности

## Design Patterns in Use

### Паттерны обработки документов:
- **Chain of Responsibility**: OCR → AI Analysis → Data Extraction → Validation
- **Strategy Pattern**: Различные парсеры для разных типов документов
- **Factory Pattern**: Создание соответствующих обработчиков по типу документа
- **Observer Pattern**: Уведомления через Telegram о статусе обработки

### Паттерны интеграции:
- **Repository Pattern**: Абстракция доступа к Zoho Books API
- **Cache Pattern**: Кэширование контактов и SKU для производительности
- **Retry Pattern**: Повторы при временных ошибках API
- **Circuit Breaker**: Защита от перегрузки внешних API

### Паттерны безопасности:
- **Singleton Pattern**: Строгий singleton для Telegram бота
- **Validation Pattern**: Pydantic модели для валидации данных
- **Error Handling**: Централизованная обработка ошибок с логированием
- **Rate Limiting**: Контроль частоты обращений к API

## Component Relationships

### Основные компоненты:
1. **PDF Parser** (pdfplumber_flower_parser.py) ↔ **OCR Service** (Google Vision API)
2. **AI Analyzer** (ai_invoice_analyzer.py) ↔ **OpenAI GPT-4 API**
3. **Zoho Integration** (zoho_api.py) ↔ **Zoho Books API**
4. **Telegram Bot** (bot_main.py) ↔ **User Interface**
5. **Cache Manager** (bills_cache_manager.py) ↔ **Local Data Store**

### Потоки данных:
- **Входящие документы**: inbox/ → functions/ → Zoho Books
- **Кэш данных**: data/optimized_cache/ ← zoho_api.py → Zoho API
- **Логирование**: logs/ ← все компоненты
- **Конфигурация**: config/ → все компоненты

## Critical Implementation Paths

### Обработка автомобильных документов:
1. **PDF → OCR/PDFPlumber** (распознавание текста)
2. **Text → AI Analysis** (извлечение VIN, модели, данных)
3. **VIN Validation** (проверка дубликатов в Zoho SKU)
4. **Item Creation** (создание товара с правильными полями)
5. **Bill Creation** (создание счета с привязкой к товару)

### Мультистрановая обработка:
1. **Document Analysis** (определение страны по косвенным признакам)
2. **VAT Processing** (добавление правильных префиксов)
3. **Contact Management** (поиск/создание контактов с правильными VAT)
4. **Organization Selection** (выбор правильной организации в Zoho)

### Цветочный бизнес:
1. **Location Detection** (browary vs wileńska определение)
2. **Branch Selection** (выбор правильного филиала PARKENTERTAINMENT)
3. **Rental Processing** (специальная обработка аренды помещений)

### Критические пути безопасности:
1. **Data Validation** (Pydantic валидация всех данных)
2. **Error Recovery** (система восстановления после ошибок)
3. **Memory Bank Sync** (автоматическое обновление контекста)
4. **Flow Control** (обязательное подтверждение перед изменениями)

