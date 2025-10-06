# Branch Structure Update Notes
*Обновлено: 2025-09-08 23:45*

## 🎯 Обновление структуры филиалов

### ✅ Изменения в структуре:

**Старая структура:**
- PARKENTERTAINMENT (по умолчанию)
- IRIS_FLOWERS (цветочный)
- TAVIE_EUROPE

**Новая структура:**
- **HEAD_OFFICE** (главный офис) - по умолчанию
- **IRIS_FLOWERS** (основной цветочный магазин = browary)
- **BROWARY_WILENSKA** (второй цветочный магазин = praga)
- **TAVIE_EUROPE** (эстонская организация)

## 🌸 Логика определения цветочных филиалов

### Правила определения:
1. **Browary Wileńska** (второй магазин):
   - Ключевые слова: `wileńska`, `wilenska`, `praga`
   - Приоритет над основным магазином

2. **Iris flowers atelier** (основной магазин):
   - HIBISPOL без маркеров Wileńska → основной магазин
   - Ключевые слова: `iris`, `browary`, `основной магазин`
   - По умолчанию для цветочных документов

3. **Head Office** (главный офис):
   - Все не-цветочные документы
   - По умолчанию

## 🔧 Техническая реализация

### Новые методы:
```python
@classmethod
def _determine_flower_branch(cls, analysis: Dict) -> Optional[str]:
    """Определяет конкретный цветочный филиал"""
    
    # 1. Проверяем маркеры Browary Wileńska
    wilenska_keywords = ['wileńska', 'wilenska', 'praga']
    if any(kw in text for kw in wilenska_keywords):
        return 'BROWARY_WILENSKA'
    
    # 2. HIBISPOL без маркеров Wileńska → основной
    if hibispol_supplier and not any(kw in text for kw in wilenska_keywords):
        return 'IRIS_FLOWERS'
    
    # 3. По умолчанию для цветочных → основной
    return 'IRIS_FLOWERS'
```

### Обновленная конфигурация филиалов:
```python
BRANCHES = {
    'HEAD_OFFICE': {
        'org_id': '20082562863',
        'name': 'PARKENTERTAINMENT Sp. z o. o.',
        'vat': 'PL5272956146',
        'default_branch': True,
        'description': 'Head Office - главный офис'
    },
    'IRIS_FLOWERS': {
        'org_id': '20082562863',
        'name': 'Iris flowers atelier',
        'parent_org': 'HEAD_OFFICE',
        'keywords': ['flowers', 'цветы', 'коробки', 'ленточки', 'hibispol', 'browary', 'iris'],
        'description': 'Основной цветочный магазин'
    },
    'BROWARY_WILENSKA': {
        'org_id': '20082562863',
        'name': 'Browary Wileńska',
        'parent_org': 'HEAD_OFFICE',
        'keywords': ['wileńska', 'wilenska', 'praga', 'browary', 'второй магазин'],
        'description': 'Второй цветочный магазин (Praga)'
    },
    'TAVIE_EUROPE': {
        'org_id': '20092948714',
        'name': 'TaVie Europe OÜ',
        'vat': 'EE102288270',
        'description': 'Эстонская организация'
    }
}
```

## 🧪 Новые тесты

### Добавленные тесты (5 новых):
1. **test_browary_wilenska_detection_by_wilenska** - определение по слову "wileńska"
2. **test_browary_wilenska_detection_by_praga** - определение по слову "praga"
3. **test_iris_flowers_by_browary_keyword** - основной магазин по "browary"
4. **test_hibispol_default_to_iris_flowers** - HIBISPOL → основной магазин
5. **test_default_branch_selection** - обновлен для Head Office

### Общее количество тестов: 18 тестов

## 📊 Примеры логирования

### Browary Wileńska (второй магазин):
```
🏢 Начало определения филиала
🌸 Цветочный поставщик: hibispol sp. z o.o.
🌸 Определен второй цветочный магазин: Browary Wileńska (найдены: ['wileńska'])
🌸 Определен цветочный филиал: Browary Wileńska
```

### Iris flowers atelier (основной магазин):
```
🏢 Начало определения филиала
🌸 Цветочный поставщик: hibispol sp. z o.o.
🌸 HIBISPOL без маркеров Wileńska → Iris flowers atelier (основной)
🌸 Определен цветочный филиал: Iris flowers atelier
```

### Head Office (по умолчанию):
```
🏢 Начало определения филиала
📋 Документ не определен как цветочный
🏢 Филиал по умолчанию: PARKENTERTAINMENT Sp. z o. o.
```

## 🔍 Ключевые понимания

### Из обратной связи пользователя:
1. **"Iris flowers atelier это тоже самое что browary"** - понято и реализовано
2. **"Head Office - это главный branch"** - сделан филиалом по умолчанию
3. **"Browary Wileńska это второй магазин"** - добавлен как отдельный филиал
4. **"может помечаться как praga"** - добавлено в ключевые слова
5. **"все что касается цветов - это аренда магазинов"** - добавлено "аренда магазин" в flower_keywords

### Логика определения:
- **Приоритет**: wileńska/praga → Browary Wileńska
- **HIBISPOL по умолчанию**: → Iris flowers atelier (основной)
- **Fallback**: Head Office для не-цветочных

## 🚀 Следующие шаги

### ✅ Завершено:
1. **Обновлена структура филиалов** с правильными названиями
2. **Добавлена логика определения** конкретного цветочного филиала
3. **Созданы тесты** для всех сценариев
4. **Обновлено логирование** для отладки

### 🔄 Следующие задачи:
1. **Протестировать на реальных файлах** за 19 августа
2. **Исправить VAT логику** - правильные налоги и брутто цены
3. **Добавить поддержку Expense** для чеков PARAGON FISKALNY
4. **Интегрировать в Telegram handlers**

## 📝 Заметки разработчика

### Принципы реализации:
1. **Четкая иерархия**: wileńska/praga > hibispol > default
2. **Подробное логирование** для понимания логики
3. **Fallback механизмы** на каждом уровне
4. **Полное тестовое покрытие** всех сценариев

### Потенциальные улучшения:
1. **Добавить больше ключевых слов** на основе реальных документов
2. **Анализ адресов** для более точного определения
3. **Машинное обучение** для автоматического улучшения точности

---
*Создано: 2025-09-08 23:45*  
*Статус: ✅ Структура филиалов обновлена и готова к тестированию*  
*Время обновления: 45 минут*
