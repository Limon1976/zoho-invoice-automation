# План рефакторинга telegram_bot/handlers.py

## 🎯 Текущие проблемы

### 1. **Размер файла: 2467 строк**
- Невозможно быстро найти нужную функцию
- Сложно понять flow обработки
- Git конфликты при командной работе

### 2. **Смешение ответственностей**
- UI логика (кнопки, сообщения)
- Бизнес-логика (обработка документов)
- Интеграции (Zoho, AI)
- Утилиты (форматирование, валидация)

### 3. **Дублирование кода**
- Повторяющаяся логика определения организации
- Одинаковая обработка ошибок
- Дублирование Zoho вызовов

## 📦 Предлагаемая структура

```
telegram_bot/
├── handlers/
│   ├── __init__.py
│   ├── base.py              # Базовые классы и декораторы
│   ├── commands.py          # /start, /help, /status
│   ├── documents.py         # Обработка PDF
│   ├── contacts.py          # Создание/обновление контактов
│   ├── items.py            # ITEM management
│   ├── bills.py            # BILL creation
│   └── callbacks.py        # Callback handlers
├── services/
│   ├── document_processor.py  # Логика обработки документов
│   ├── supplier_service.py   # Работа с поставщиками
│   ├── organization_service.py # Определение организации
│   └── message_formatter.py   # Форматирование сообщений
├── utils/
│   ├── decorators.py       # @with_error_handling и т.д.
│   ├── validators.py       # Валидация данных
│   └── constants.py        # Константы
└── bot_main.py

```

## 🔧 План рефакторинга (поэтапный)

### Фаза 1: Извлечение сервисов (1-2 дня)

```python
# services/organization_service.py
class OrganizationService:
    """Сервис для работы с организациями"""
    
    VAT_TO_ORG = {
        'PL5272956146': ('20082562863', 'PARKENTERTAINMENT'),
        'EE102288270': ('20092948714', 'TaVie Europe OÜ')
    }
    
    @staticmethod
    def determine_buyer(analysis: dict) -> tuple[str, str]:
        """Универсальное определение организации-покупателя"""
        # Вынести логику из determine_buyer_organization
        pass

# services/supplier_service.py  
class SupplierService:
    """Сервис для работы с поставщиками"""
    
    @staticmethod
    def extract_supplier_info(analysis: dict) -> SupplierInfo:
        """Извлечение информации о поставщике"""
        # Вынести логику из get_supplier_info
        pass
    
    async def smart_check(self, supplier: SupplierInfo) -> CheckResult:
        """Умная проверка поставщика"""
        # Вынести логику из smart_supplier_check
        pass
```

### Фаза 2: Разделение handlers (2-3 дня)

```python
# handlers/documents.py
class DocumentHandler:
    """Обработчик документов"""
    
    def __init__(self, 
                 doc_processor: DocumentProcessor,
                 supplier_service: SupplierService):
        self.doc_processor = doc_processor
        self.supplier_service = supplier_service
    
    async def handle_pdf(self, update: Update, context: Context):
        """Обработка PDF - только UI логика"""
        try:
            # 1. Скачивание файла
            file = await self._download_file(update, context)
            
            # 2. Делегирование обработки сервису
            result = await self.doc_processor.process(file)
            
            # 3. Форматирование ответа
            message = self._format_message(result)
            keyboard = self._build_keyboard(result)
            
            # 4. Отправка ответа
            await update.message.reply_text(message, reply_markup=keyboard)
            
        except Exception as e:
            await self._handle_error(update, e)

# handlers/bills.py
class BillHandler:
    """Обработчик создания BILL"""
    
    async def create_bill(self, update: Update, context: Context):
        """Создание BILL - максимум 100 строк"""
        # Вся сложная логика в сервисах
        pass
```

### Фаза 3: Улучшение архитектуры (3-4 дня)

```python
# utils/decorators.py
def with_error_handling(func):
    """Декоратор для единообразной обработки ошибок"""
    @wraps(func)
    async def wrapper(self, update: Update, context: Context):
        try:
            return await func(self, update, context)
        except ValidationError as e:
            await update.message.reply_text(f"❌ Ошибка валидации: {e}")
        except ZohoAPIError as e:
            await update.message.reply_text(f"❌ Ошибка Zoho: {e}")
        except Exception as e:
            logger.exception("Unexpected error")
            await update.message.reply_text("❌ Произошла ошибка")
    return wrapper

# Использование
class DocumentHandler:
    @with_error_handling
    async def handle_pdf(self, update: Update, context: Context):
        # Код без try/except - чище и проще
        pass
```

## 🐛 Исправление известных багов

### 1. **Race condition при параллельных запросах**
```python
# Проблема: дублирование callback обработки
_recent_callbacks: dict[str, float] = {}  # Глобальная переменная - плохо!

# Решение: использовать Redis или thread-safe структуру
class CallbackDeduplicator:
    def __init__(self, redis_client):
        self.redis = redis_client
    
    async def is_duplicate(self, callback_id: str) -> bool:
        key = f"callback:{callback_id}"
        if await self.redis.exists(key):
            return True
        await self.redis.setex(key, 10, "1")  # TTL 10 секунд
        return False
```

### 2. **Потеря контекста при рестарте бота**
```python
# Проблема: использование context.user_data
context.user_data['smart_result'] = result  # Теряется при рестарте

# Решение: персистентное хранение
class SessionStorage:
    async def save_session(self, user_id: int, data: dict):
        await self.redis.setex(
            f"session:{user_id}", 
            3600,  # 1 час
            json.dumps(data)
        )
    
    async def load_session(self, user_id: int) -> dict:
        data = await self.redis.get(f"session:{user_id}")
        return json.loads(data) if data else {}
```

### 3. **Обработка больших файлов**
```python
# Проблема: загрузка всего файла в память
with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_file:
    await file.download_to_drive(temp_file.name)  # Может быть 100MB+

# Решение: streaming и ограничения
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

async def download_with_limit(file, max_size: int):
    if file.file_size > max_size:
        raise ValueError(f"Файл слишком большой: {file.file_size / 1024 / 1024:.1f}MB")
    
    # Streaming download
    async with aiofiles.open(temp_path, 'wb') as f:
        async for chunk in file.download_stream():
            await f.write(chunk)
```

## 🚀 Порядок внедрения

### Неделя 1: Подготовка
1. **Создать тесты** для критических функций
2. **Задокументировать** текущее поведение
3. **Feature flag** для нового кода

### Неделя 2: Рефакторинг
1. **Извлечь сервисы** (не меняя handlers)
2. **Создать новую структуру** папок
3. **Постепенно переносить** функции

### Неделя 3: Тестирование
1. **A/B тестирование** старого и нового кода
2. **Исправление багов**
3. **Оптимизация производительности**

### Неделя 4: Завершение
1. **Удаление старого кода**
2. **Документация**
3. **Обучение команды**

## ⚡ Quick Wins (можно сделать сразу)

### 1. Вынести константы
```python
# utils/constants.py
class Organizations:
    PARKENTERTAINMENT = {
        'id': '20082562863',
        'name': 'PARKENTERTAINMENT Sp. z o. o.',
        'vat': 'PL5272956146'
    }
    
    TAVIE_EUROPE = {
        'id': '20092948714', 
        'name': 'TaVie Europe OÜ',
        'vat': 'EE102288270'
    }
```

### 2. Улучшить логирование
```python
# Заменить print() на структурированное логирование
import structlog
logger = structlog.get_logger()

# Было
print(f"🔍 DEBUG: {data}")

# Стало
logger.debug("processing_document", data=data, step="validation")
```

### 3. Кэширование тяжелых операций
```python
from functools import lru_cache

@lru_cache(maxsize=100)
def get_accounts_for_org(org_id: str):
    # Кэшируем на время сессии
    return fetch_accounts_from_zoho(org_id)
```

## 📊 Ожидаемые результаты

### До рефакторинга:
- 1 файл на 2467 строк
- Время поиска бага: 30-60 минут
- Риск сломать при изменении: высокий
- Тестовое покрытие: ~0%

### После рефакторинга:
- 10-15 файлов по 100-300 строк
- Время поиска бага: 5-10 минут
- Риск сломать: минимальный
- Тестовое покрытие: >80%

## ✅ Критерии успеха

1. **Все тесты проходят** (старые и новые)
2. **Производительность не упала** (или улучшилась)
3. **Код читаем** и понятен новым разработчикам
4. **Баги исправлены** и покрыты тестами
5. **Документация обновлена**


