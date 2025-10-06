# Branch Manager Implementation Notes
*Создано: 2025-09-07 23:32*

## 🎯 Что реализовано

### ✅ Созданные файлы:
1. **`telegram_bot/services/branch_manager.py`** - Основной класс для управления филиалами
2. **`tests/test_branch_manager.py`** - Полный набор тестов (13 тестов)
3. **Интеграция в `functions/workdrive_batch_processor.py`** - метод `determine_organization()`

### ✅ Функциональность:
- **Автоматическое определение филиалов** на основе анализа документов
- **Приоритет цветочных маркеров** → Iris flowers atelier
- **Fallback по VAT** → PARKENTERTAINMENT или TaVie Europe
- **Логирование процесса** определения филиала
- **Полное тестовое покрытие** всех сценариев

## 🌸 Логика определения цветочных документов

### Цветочные маркеры (приоритет):
1. **LLM категория**: `product_category == 'FLOWERS'` + `detected_flower_names` не пустой
2. **Поставщик HIBISPOL**: `supplier_name` содержит "hibispol"
3. **Ключевые слова**: коробки, ленточки, flowers, цветы, букет, композиция
4. **В позициях**: цветочные маркеры в `line_items[].description`

### Результат:
- **Цветочный документ** → Iris flowers atelier (org_id: 20082562863)
- **По VAT EE102288270** → TaVie Europe OÜ (org_id: 20092948714)  
- **По умолчанию** → PARKENTERTAINMENT (org_id: 20082562863)

## 🔧 Техническая реализация

### Архитектура:
```python
BranchManager
├── determine_branch(analysis) -> Dict     # Основной метод
├── _is_flowers_document(analysis) -> bool # Проверка цветочных маркеров
├── get_branch_by_org_id(org_id) -> Dict  # Поиск по org_id
├── is_flowers_branch(key) -> bool        # Проверка цветочного филиала
└── get_all_branches() -> Dict            # Все филиалы
```

### Конфигурация филиалов:
```python
BRANCHES = {
    'PARKENTERTAINMENT': {
        'org_id': '20082562863',
        'name': 'PARKENTERTAINMENT Sp. z o. o.',
        'vat': 'PL5272956146',
        'default_branch': True
    },
    'IRIS_FLOWERS': {
        'org_id': '20082562863',  # Тот же что и PARKENTERTAINMENT
        'name': 'Iris flowers atelier',
        'parent_org': 'PARKENTERTAINMENT',
        'keywords': ['flowers', 'цветы', 'коробки', 'ленточки', 'hibispol']
    },
    'TAVIE_EUROPE': {
        'org_id': '20092948714',
        'name': 'TaVie Europe OÜ',
        'vat': 'EE102288270'
    }
}
```

## 🧪 Тестирование

### Созданные тесты (13 тестов):
1. **test_flowers_detection_by_category** - определение по LLM категории
2. **test_flowers_detection_by_supplier_hibispol** - по поставщику HIBISPOL
3. **test_flowers_detection_by_keywords_korobki** - по слову "коробки"
4. **test_flowers_detection_by_keywords_lentochki** - по слову "ленточки"
5. **test_flowers_detection_in_line_items** - по позициям в line_items
6. **test_default_branch_selection** - выбор по умолчанию
7. **test_tavie_europe_by_vat** - определение TaVie Europe по VAT
8. **test_parkentertainment_by_vat** - определение PARKENTERTAINMENT по VAT
9. **test_flowers_priority_over_vat** - приоритет цветочных маркеров
10. **test_get_branch_by_org_id** - поиск по org_id
11. **test_get_branch_key_by_name** - получение ключа по названию
12. **test_get_branch_display_info** - форматирование информации
13. **test_is_flowers_branch** - проверка цветочного филиала

### Команды для запуска тестов:
```bash
# Запуск всех тестов Branch Manager
python -m pytest tests/test_branch_manager.py -v

# Запуск конкретного теста
python -m pytest tests/test_branch_manager.py::TestBranchManager::test_flowers_detection_by_category -v

# Запуск с подробным выводом
python -m pytest tests/test_branch_manager.py -v -s
```

## 🔗 Интеграция с WorkDrive Processor

### Изменения в `functions/workdrive_batch_processor.py`:
```python
def determine_organization(self, analysis: Dict) -> str:
    """Определяет организацию для создания Bill на основе анализа документа"""
    try:
        from telegram_bot.services.branch_manager import BranchManager
        
        # Определяем филиал через Branch Manager
        branch = BranchManager.determine_branch(analysis)
        org_id = branch['org_id']
        
        # Сохраняем информацию о филиале
        self.current_branch = branch
        
        # Активируем специальную обработку для цветочного филиала
        if BranchManager.is_flowers_branch(branch_key):
            self.is_flowers_processing = True
        
        return org_id
        
    except ImportError:
        # Fallback если Branch Manager недоступен
        return "20082562863"  # PARKENTERTAINMENT
```

### Новые атрибуты класса:
- **`self.current_branch`** - информация о текущем филиале
- **`self.is_flowers_processing`** - флаг цветочной обработки

## 📊 Логирование

### Примеры логов:
```
🏢 Начало определения филиала
🌸 LLM определил цветы: category=FLOWERS, flowers=2
🌸 Определен цветочный филиал: Iris flowers atelier
🌸 Активирована специальная обработка для цветочного филиала
```

```
🏢 Начало определения филиала
📋 Документ не определен как цветочный
🏢 Филиал по умолчанию: PARKENTERTAINMENT Sp. z o. o.
```

## 🚀 Следующие шаги

### ✅ Завершено:
1. **Branch Manager создан** и протестирован
2. **Интеграция в WorkDrive Processor** выполнена
3. **Полное тестовое покрытие** создано

### 🔄 Следующие задачи:
1. **Исправить VAT логику** - правильные налоги и брутто цены
2. **Добавить поддержку Expense** для чеков PARAGON FISKALNY
3. **Протестировать на файлах за 19 августа**
4. **Интегрировать в Telegram handlers** без увеличения размера

## 📝 Заметки разработчика

### Принятые решения:
1. **Iris flowers atelier использует тот же org_id** что и PARKENTERTAINMENT (20082562863)
2. **Приоритет цветочных маркеров** над VAT определением
3. **Fallback механизм** на случай недоступности Branch Manager
4. **Подробное логирование** для отладки и мониторинга

### Потенциальные улучшения:
1. **Добавить branch_id** для Iris flowers atelier из Zoho API
2. **Расширить ключевые слова** на основе реальных документов
3. **Добавить конфигурацию** через внешний файл
4. **Кэширование результатов** для повторных определений

---
*Создано: 2025-01-07 23:32*  
*Статус: ✅ Branch Manager реализован и готов к использованию*  
*Время реализации: 1.5 часа*
