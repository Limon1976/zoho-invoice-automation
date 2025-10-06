# Tech Context: Zoho Invoice Automation

## Technologies Used

### Core Technologies:
- **Python 3.11+**: Основной язык разработки
- **Virtual Environment (venv)**: Изоляция зависимостей
- **Pydantic V2.11.7**: Валидация данных и сериализация
- **PydanticAI 0.4.2**: Современный фреймворк для AI агентов
- **FastAPI 0.115.14**: RESTful API веб-сервер

### AI/ML Technologies:
- **OpenAI GPT-4**: Анализ документов и извлечение данных
- **OpenAI SDKs**: Интеграция с OpenAI API
- **Google Vision API**: OCR распознавание текста из PDF
- **Anthropic Claude**: Дополнительный AI provider
- **Google GenAI**: Дополнительный AI provider
- **Cohere**: Дополнительный AI provider

### Document Processing:
- **PDFPlumber 0.11.7**: Приоритетный парсер PDF (при наличии текстового слоя)
- **PyMuPDF 1.26.1**: Альтернативный PDF парсер
- **Google Cloud Vision**: OCR для сканированных документов

### Integration APIs:
- **Zoho Books API**: Интеграция с учетной системой
- **Telegram Bot API (python-telegram-bot 20.7)**: Пользовательский интерфейс
- **HTTP клиенты**: httpx >=0.28.1,<1.0.0 для API запросов

### Development Tools:
- **Memory Bank MCP Server**: Автоматическое управление контекстом
- **Logging**: RotatingFileHandler для логов
- **Environment Variables**: python-dotenv для конфигурации

## Development Setup

### Структура проекта:
```
/Users/macos/my_project/
├── venv/                    # Виртуальная среда (ОБЯЗАТЕЛЬНО)
├── src/                     # Современная архитектура (33 файла)
├── functions/               # Основная логика обработки
├── telegram_bot/            # Telegram интерфейс (31 файл)
├── mcp_connector/           # MCP коннектор
├── mcp_servers/mcp-memory-bank/  # Memory Bank сервер
├── config/                  # Конфигурация
├── data/                    # Кэш и данные
├── inbox/                   # Входящие документы
├── memory-bank/             # Memory Bank файлы
└── requirements/            # Зависимости
```

### Настройка окружения:
1. **Virtual Environment**: `source venv/bin/activate` (ВСЕГДА)
2. **Dependencies**: `pip install -r requirements-optimized-2025.txt`
3. **Environment Variables**: `.env` файл с API ключами
4. **Telegram Bot**: Запуск ТОЛЬКО из корня проекта

### API Ключи (через .env):
- `OPENAI_API_KEY`: OpenAI GPT-4 доступ
- `GOOGLE_APPLICATION_CREDENTIALS`: Google Vision API
- `TELEGRAM_BOT_TOKEN`: Telegram бот токен
- `ZOHO_CLIENT_ID`, `ZOHO_CLIENT_SECRET`: Zoho Books API

## Technical Constraints

### Performance Constraints:
- **Обработка документа**: < 2 минут максимум
- **OCR лимиты**: Google Vision API rate limits
- **API лимиты**: Zoho Books API quotas (1000 запросов/час)
- **Память**: Large PDF файлы могут требовать много RAM

### Integration Constraints:
- **Zoho Books regions**: EU (books.zoho.eu) vs US (books.zoho.com)
- **Multi-organization**: PARKENTERTAINMENT vs TaVie Europe OÜ
- **VAT formats**: Различные форматы по странам (PL-, IE-, и т.д.)
- **Language support**: Польский, английский, эстонский, шведский

### Security Constraints:
- **API ключи**: Только через .env, НЕ в коде
- **Virtual Environment**: Обязательная изоляция
- **Flow Control**: DIAGNOSE → OPTIONS → WAIT → PATCH
- **Валидация**: Все данные через Pydantic модели

## Dependencies

### Core Dependencies (requirements-optimized-2025.txt):
```python
# AI и ML
openai>=1.30.1
pydantic>=2.11.7
pydantic-ai>=0.4.2
anthropic>=latest
google-generativeai>=latest
cohere>=latest

# API интеграции
fastapi>=0.115.14
python-telegram-bot>=20.7
httpx>=0.28.1,<1.0.0

# Обработка документов
pdfplumber>=0.11.7
pymupdf>=1.26.1
google-cloud-vision>=3.10.2

# Утилиты
python-dotenv>=latest
pydantic-settings>=latest
```

### Development Dependencies:
- **pytest**: Тестирование
- **black**: Форматирование кода
- **flake8**: Линтинг (КРИТИЧЕСКИ ВАЖНО исправлять ВСЕ ошибки)
- **mypy**: Проверка типов

## Tool Usage Patterns

### Telegram Bot:
- **Singleton Pattern**: Строгий singleton, pkill перед запуском
- **Запуск**: ТОЛЬКО из корня проекта в venv
- **Логирование**: RotatingFileHandler в logs/

### Document Processing:
- **PDFPlumber First**: Приоритет при наличии текстового слоя
- **OCR Fallback**: Google Vision для сканированных документов
- **AI Analysis**: OpenAI GPT-4 для извлечения структурированных данных

### Zoho Integration:
- **Кэширование**: data/optimized_cache/ для контактов и SKU
- **Rate Limiting**: Соблюдение API лимитов
- **Organization Selection**: Автоматический выбор по документу

### Memory Bank:
- **MCP Server**: Автоматические обновления при изменениях
- **File Structure**: memory-bank/ с 7 основными файлами
- **Sync Strategy**: Обновление при создании файлов/архитектурных изменениях

### Error Handling:
- **Centralized Logging**: logs/ директория для всех компонентов
- **Retry Logic**: Автоматические повторы для временных ошибок
- **User Notifications**: Telegram уведомления о статусе

### Development Workflow:
- **Virtual Environment**: ВСЕГДА активна при работе
- **Flow Control**: Обязательное подтверждение перед изменениями
- **Linting**: Исправление ВСЕХ ошибок линтера
- **Memory Bank Updates**: При каждом значимом изменении

