# Handlers Refactoring Roadmap
*Создано: 2025-00-07*

## 🎯 Цель рефакторинга
Разбить `telegram_bot/handlers.py` (2467+ строк) на структурированные модули без потери функциональности, с интеграцией улучшенного WorkDrive Processor.

## 📊 Текущее состояние

### ❌ Проблемы handlers.py:
- **Размер**: 2467+ строк (слишком большой)
- **Смешение ответственностей**: UI + бизнес-логика + интеграции
- **Дублирование кода**: повторяющаяся логика организаций, ошибок, Zoho вызовов
- **Сложность поддержки**: трудно найти функции, Git конфликты

### ✅ Что должно остаться:
- **Вся функциональность** работает как сейчас
- **Telegram UI** остается таким же
- **Производительность** не ухудшается
- **Обратная совместимость** 100%

## 🏗️ Целевая архитектура

```
telegram_bot/
├── handlers/
│   ├── __init__.py
│   ├── base.py              # Базовые классы и декораторы
│   ├── commands.py          # /start, /help, /status
│   ├── documents.py         # handle_pdf, handle_photo
│   ├── contacts.py          # Создание/обновление контактов
│   ├── items.py            # ITEM management
│   ├── bills.py            # BILL creation
│   ├── expenses.py         # Expense creation  
│   └── callbacks.py        # Callback routing
├── services/
│   ├── __init__.py
│   ├── document_processor.py  # Обработка документов
│   ├── workdrive_service.py   # Интеграция с WorkDrive
│   ├── branch_manager.py      # Управление филиалами
│   ├── supplier_service.py    # Работа с поставщиками
│   ├── organization_service.py # Определение организации
│   ├── account_manager.py     # Унифицированная работа со счетами
│   ├── attachment_manager.py  # Прикрепление файлов (уже есть)
│   └── message_formatter.py  # Форматирование сообщений
├── utils/
│   ├── __init__.py
│   ├── decorators.py       # @with_error_handling
│   ├── validators.py       # Валидация данных
│   ├── constants.py        # Константы
│   └── callback_deduplicator.py # Уже есть
└── bot_main.py
```

## 🚀 Поэтапный план выполнения

### ФАЗА 1: Подготовка и анализ (1 час)

#### 1.1 Создание backup и структуры
```bash
# Backup существующего файла
cp telegram_bot/handlers.py telegram_bot/handlers.py.backup-$(date +%Y%m%d)

# Создание новой структуры папок
mkdir -p telegram_bot/handlers
mkdir -p telegram_bot/services  # уже частично есть
mkdir -p telegram_bot/utils     # уже частично есть
```

#### 1.2 Анализ зависимостей
- Создать карту функций: кто кого вызывает
- Выявить глобальные переменные и состояния
- Определить точки входа (handlers)

### ФАЗА 2: Создание сервисов (2-3 часа)

#### 2.1 Branch Manager (из WorkDrive Enhancement Plan)
```python
# telegram_bot/services/branch_manager.py
class BranchManager:
    """Управление филиалами - цветы → Iris flowers atelier"""
    
    @classmethod
    def determine_branch(cls, analysis: Dict) -> Dict:
        """Определяет филиал на основе анализа"""
        # Логика из WorkDrive Enhancement Plan
```

#### 2.2 Organization Service
```python
# telegram_bot/services/organization_service.py
class OrganizationService:
    """Унифицированное определение организации"""
    
    @staticmethod
    def determine_buyer_organization(analysis: Dict) -> Tuple[str, str]:
        """Вынести из handlers.py логику determine_buyer_organization"""
    
    @staticmethod
    def get_organization_info(org_id: str) -> Dict:
        """Получить информацию об организации"""
```

#### 2.3 Document Processor
```python
# telegram_bot/services/document_processor.py
class DocumentProcessor:
    """Обработка документов с интеграцией WorkDrive логики"""
    
    def __init__(self):
        self.workdrive_service = WorkDriveService()
    
    async def process_pdf(self, file_path: str) -> ProcessingResult:
        """Полная обработка PDF"""
    
    async def process_photo(self, photo_path: str) -> ProcessingResult:
        """Полная обработка фото"""
    
    def build_telegram_message(self, analysis: Dict) -> str:
        """Создание сообщения для Telegram"""
```

#### 2.4 WorkDrive Service (из Enhancement Plan)
```python
# telegram_bot/services/workdrive_service.py
class WorkDriveService:
    """Интеграция улучшенного WorkDrive Processor"""
    
    async def process_document(self, file_path: str, analysis: Dict) -> Dict:
        """Обработка через WorkDrive логику с филиалами и VAT"""
```

### ФАЗА 3: Создание handlers (2-3 часа)

#### 3.1 Base Handler
```python
# telegram_bot/handlers/base.py
class BaseHandler:
    """Базовый класс для всех handlers"""
    
    def __init__(self):
        self.document_processor = DocumentProcessor()
        self.workdrive_service = WorkDriveService()
        self.branch_manager = BranchManager()
        
    @with_error_handling
    async def handle_error(self, update: Update, error: Exception):
        """Унифицированная обработка ошибок"""
```

#### 3.2 Document Handler
```python
# telegram_bot/handlers/documents.py
class DocumentHandler(BaseHandler):
    """Обработчик документов - тонкий слой над сервисами"""
    
    async def handle_pdf(self, update: Update, context: Context):
        """Обработка PDF - только orchestration"""
        # 1. Валидация файла
        # 2. Делегирование DocumentProcessor
        # 3. Форматирование ответа
        # 4. Отправка в Telegram
    
    async def handle_photo(self, update: Update, context: Context):
        """Обработка фото - аналогично PDF"""
```

#### 3.3 Callback Router
```python
# telegram_bot/handlers/callbacks.py
class CallbackRouter(BaseHandler):
    """Маршрутизация callback запросов"""
    
    routes = {
        'smart_create_bill': BillHandler.create,
        'smart_create_expense': ExpenseHandler.create,
        'smart_create_contact': ContactHandler.create,
        'smart_create_item': ItemHandler.create,
        'upload_to_workdrive': WorkDriveHandler.upload,
    }
    
    async def route_callback(self, update: Update, context: Context):
        """Единая точка маршрутизации"""
```

#### 3.4 Специализированные handlers
```python
# telegram_bot/handlers/bills.py
class BillHandler(BaseHandler):
    async def create(self, update: Update, context: Context):
        """Создание BILL - максимум 100 строк"""

# telegram_bot/handlers/expenses.py  
class ExpenseHandler(BaseHandler):
    async def create(self, update: Update, context: Context):
        """Создание Expense - максимум 100 строк"""

# telegram_bot/handlers/contacts.py
class ContactHandler(BaseHandler):
    async def create(self, update: Update, context: Context):
        """Создание контакта - максимум 100 строк"""
```

### ФАЗА 4: Миграция и интеграция (2-3 часа)

#### 4.1 Постепенная замена в bot_main.py
```python
# telegram_bot/bot_main.py
from telegram_bot.handlers.documents import DocumentHandler
from telegram_bot.handlers.callbacks import CallbackRouter
from telegram_bot.handlers.commands import CommandHandler

def setup_handlers(application):
    """Настройка handlers с новой архитектурой"""
    
    # Документы
    doc_handler = DocumentHandler()
    application.add_handler(MessageHandler(filters.Document.PDF, doc_handler.handle_pdf))
    application.add_handler(MessageHandler(filters.PHOTO, doc_handler.handle_photo))
    
    # Callbacks
    callback_router = CallbackRouter()
    application.add_handler(CallbackQueryHandler(callback_router.route_callback))
    
    # Команды
    cmd_handler = CommandHandler()
    application.add_handler(CommandHandler("start", cmd_handler.start))
```

#### 4.2 Feature flags для безопасности
```python
# telegram_bot/utils/feature_flags.py
FEATURES = {
    'use_new_document_handler': False,  # Включаем постепенно
    'use_new_callback_router': False,
    'use_workdrive_integration': False,
    'use_branch_logic': False,
}

# В handlers используем:
if FEATURES['use_new_document_handler']:
    return await new_document_handler(update, context)
else:
    return await old_document_handler(update, context)
```

### ФАЗА 5: Тестирование и оптимизация (1-2 часа)

#### 5.1 Unit тесты для сервисов
```python
# tests/test_services.py
async def test_branch_manager():
    """Тест определения филиала для цветов"""
    
async def test_document_processor():
    """Тест полной обработки документа"""
    
async def test_workdrive_integration():
    """Тест интеграции с WorkDrive"""
```

#### 5.2 Integration тесты
```python
# tests/test_handlers.py
async def test_pdf_processing_flow():
    """Тест полного цикла обработки PDF"""
    
async def test_expense_creation_flow():
    """Тест создания Expense для чеков"""
```

#### 5.3 Performance тесты
- Замер времени обработки: до/после
- Проверка memory usage
- Нагрузочное тестирование

### ФАЗА 6: Cleanup и документация (1 час)

#### 6.1 Удаление старого кода
```python
# Когда все тесты проходят:
rm telegram_bot/handlers.py.backup-*
# Оставить только новую структуру
```

#### 6.2 Обновление документации
- README с новой архитектурой
- API документация для сервисов
- Troubleshooting guide

## 🧪 План тестирования

### Критические тесты:
1. **Обработка PDF** → создание Bill/Expense
2. **Обработка фото** → создание Bill/Expense  
3. **Создание контактов** через кнопки
4. **Прикрепление файлов** к Bills/Expenses
5. **WorkDrive интеграция** с правильными филиалами
6. **Цветочные документы** → Iris flowers atelier

### Тестовые файлы:
- Файлы за 19 августа (уже тестировались)
- Цветочные документы от HIBISPOL
- Чеки PARAGON FISKALNY
- Обычные инвойсы

## 📊 Метрики успеха

### ✅ Критерии завершения:
- **Размер файлов**: каждый handler < 300 строк
- **Размер сервисов**: каждый < 500 строк  
- **Тестовое покрытие**: > 80%
- **Производительность**: не хуже текущей
- **Функциональность**: 100% сохранена

### 📈 Ожидаемые улучшения:
- **Читаемость кода**: значительное улучшение
- **Время поиска багов**: 60 мин → 10 мин
- **Риск сломать при изменении**: высокий → минимальный
- **Скорость разработки**: +50% для новых функций

## ⚠️ Риски и митигация

### Основные риски:
1. **Сломать существующую функциональность**
   - *Митигация*: Feature flags + постепенная миграция
2. **Ухудшить производительность**
   - *Митигация*: Performance тесты на каждом этапе
3. **Потерять данные пользователей**
   - *Митигация*: Backup + тестирование на копии

### План отката:
```bash
# Быстрый откат к старой версии
git checkout main
mv telegram_bot/handlers.py.backup telegram_bot/handlers.py
systemctl restart telegram-bot
```

## 🚀 Запуск рефакторинга

### Готовность к старту:
- [ ] WorkDrive Enhancement Plan выполнен
- [ ] Backup создан
- [ ] Тестовое окружение настроено
- [ ] Feature flags реализованы
- [ ] Команда проинформирована

### Следующий шаг:
**Начать с ФАЗЫ 1** - создать backup и структуру папок

---
*Обновлено: 2025-09-07*  
*Статус: 📋 Готов к выполнению после WorkDrive Enhancement*
*Время выполнения: 8-10 часов*
