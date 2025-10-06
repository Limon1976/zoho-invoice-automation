# WorkDrive Enhancement Plan
*Создано: 2025-09-07*

## 🎯 Цель
Улучшить существующий `functions/workdrive_batch_processor.py` с добавлением:
1. **Логики филиалов** (Branch Management) с цветочными маркерами
2. **Корректной VAT логики** - применение правильных налогов и брутто цен
3. **Поддержки Expense** для чеков (PARAGON FISKALNY)
4. **Интеграции в Telegram handlers** без увеличения размера файла

## 📋 Текущее состояние

### ✅ Что уже работает в WorkDrive Processor:
- Автоматическая обработка файлов из WorkDrive за определенную дату
- LLM анализ документов через `analyze_proforma_via_agent()`
- Создание Bills в Zoho Books
- Perfect Flower Parser для цветочных документов
- Telegram уведомления с отчетами
- Обработка дубликатов
- Прикрепление PDF к созданным Bills
- Логирование обработанных файлов

### ❌ Что нужно улучшить:
1. **Логика филиалов отсутствует** - все Bills создаются в PARKENTERTAINMENT
2. **VAT логика неточная** - не всегда применяются правильные налоги
3. **Нет поддержки Expense** для чеков PARAGON FISKALNY
4. **Нет интеграции с handlers** - работает только standalone

## 🏗️ План улучшений

### Этап 1: Добавление логики филиалов (2-3 часа)

#### 1.1 Создать Branch Manager
```python
# telegram_bot/services/branch_manager.py
class BranchManager:
    """Управление филиалами и определение правильной организации"""
    
    BRANCHES = {
        'PARKENTERTAINMENT': {
            'org_id': '20082562863',
            'name': 'PARKENTERTAINMENT Sp. z o. o.',
            'vat': 'PL5272956146',
            'default_branch': True
        },
        'IRIS_FLOWERS': {
            'org_id': '20082562863',  # Тот же как PARKENTERTAINMENT
            'name': 'Iris flowers atelier',
            'branch_id': 'iris_flowers_branch_id',  # Нужно получить из Zoho
            'keywords': ['flowers', 'цветы', 'коробки', 'ленточки', 'hibispol']
        },
        'TAVIE_EUROPE': {
            'org_id': '20092948714',
            'name': 'TaVie Europe OÜ',
            'vat': 'EE102288270'
        }
    }
    
    @classmethod
    def determine_branch(cls, analysis: Dict) -> Dict:
        """Определяет филиал на основе анализа документа"""
        
        # 1. Цветочные маркеры → Iris flowers atelier
        if cls._is_flowers_document(analysis):
            return cls.BRANCHES['IRIS_FLOWERS']
        
        # 2. По VAT покупателя
        buyer_vat = analysis.get('buyer_vat', '').replace(' ', '').upper()
        for branch_key, branch in cls.BRANCHES.items():
            if branch.get('vat', '').replace(' ', '').upper() in buyer_vat:
                return branch
        
        # 3. По умолчанию PARKENTERTAINMENT
        return cls.BRANCHES['PARKENTERTAINMENT']
    
    @classmethod
    def _is_flowers_document(cls, analysis: Dict) -> bool:
        """Проверяет является ли документ цветочным"""
        
        # LLM определил цветы
        llm_cat = (analysis.get('product_category') or '').upper()
        detected_flowers = analysis.get('detected_flower_names', [])
        
        if llm_cat == 'FLOWERS' and detected_flowers:
            return True
        
        # Поставщик цветов (HIBISPOL)
        supplier_name = (analysis.get('supplier_name') or '').lower()
        if 'hibispol' in supplier_name:
            return True
        
        # Ключевые слова в описании
        text = (analysis.get('extracted_text') or '').lower()
        flower_keywords = ['коробки', 'ленточки', 'flowers', 'цветы']
        
        return any(keyword in text for keyword in flower_keywords)
```

#### 1.2 Интегрировать в WorkDrive Processor
```python
# В functions/workdrive_batch_processor.py
def determine_organization(self, analysis: Dict) -> str:
    """Определяет организацию для создания Bill на основе анализа документа"""
    from telegram_bot.services.branch_manager import BranchManager
    
    branch = BranchManager.determine_branch(analysis)
    org_id = branch['org_id']
    
    logger.info(f"🏢 Определен филиал: {branch['name']} (org_id: {org_id})")
    
    # Если это Iris flowers atelier, добавляем branch_id к payload
    if branch.get('branch_id'):
        # Сохраняем для использования в create_bill_payload
        self.current_branch = branch
    
    return org_id
```

### Этап 2: Исправление VAT логики (1-2 часа)

#### 2.1 Улучшить определение inclusive/exclusive налога
```python
# В create_bill_payload метод
def _determine_tax_inclusion(self, analysis: Dict) -> bool:
    """Точное определение inclusive/exclusive налога"""
    
    doc_text = (analysis.get('extracted_text') or '').lower()
    
    # 1. ПРИОРИТЕТ: Структурные паттерны
    hibispol_brutto = "cena brutto" in doc_text or "cena przed" in doc_text
    netto_structure = "wartość netto" in doc_text and "cena jdn" in doc_text
    
    if hibispol_brutto:
        logger.info("💰 VAT: INCLUSIVE (структура HIBISPOL - cena brutto)")
        return True
    
    if netto_structure:
        logger.info("💰 VAT: EXCLUSIVE (структура netto - wartość netto)")
        return False
    
    # 2. Анализ сумм из LLM
    gross_amount = analysis.get('gross_amount', 0)
    net_amount = analysis.get('net_amount', 0)
    vat_amount = analysis.get('vat_amount', 0)
    
    if gross_amount and net_amount and vat_amount:
        # Проверяем соответствие: gross = net + vat
        calculated_gross = net_amount + vat_amount
        if abs(gross_amount - calculated_gross) < 0.01:
            logger.info("💰 VAT: EXCLUSIVE (суммы: gross = net + vat)")
            return False
        else:
            logger.info("💰 VAT: INCLUSIVE (суммы не соответствуют net + vat)")
            return True
    
    # 3. Fallback по ключевым словам
    inclusive_words = ["brutto", "gross", "tax inclusive", "kwota brutto"]
    exclusive_words = ["netto", "net", "tax exclusive", "kwota netto"]
    
    inclusive_count = sum(1 for word in inclusive_words if word in doc_text)
    exclusive_count = sum(1 for word in exclusive_words if word in doc_text)
    
    if exclusive_count > inclusive_count:
        logger.info(f"💰 VAT: EXCLUSIVE (keywords: {exclusive_count} vs {inclusive_count})")
        return False
    
    logger.info(f"💰 VAT: INCLUSIVE по умолчанию (keywords: {inclusive_count} vs {exclusive_count})")
    return True
```

#### 2.2 Правильное применение налогов к line_items
```python
def _apply_correct_tax_to_line_items(self, line_items: List[Dict], analysis: Dict, org_id: str, inclusive: bool) -> List[Dict]:
    """Применяет правильные налоги к line_items"""
    from functions.zoho_api import find_tax_by_percent
    
    # Получаем налоговую ставку из анализа
    tax_rate = analysis.get('tax_rate', 23)  # По умолчанию 23% для Польши
    tax_id = find_tax_by_percent(org_id, tax_rate)
    
    logger.info(f"💰 Применяем налог: {tax_rate}% (tax_id: {tax_id}, inclusive: {inclusive})")
    
    for item in line_items:
        if tax_id:
            item['tax_id'] = tax_id
        
        # Для inclusive налога корректируем rate
        if inclusive and tax_rate > 0:
            original_rate = float(item.get('rate', 0))
            # Rate уже включает налог, оставляем как есть
            logger.info(f"💰 Line item rate (inclusive): {original_rate}")
        else:
            # Rate без налога, налог будет добавлен Zoho автоматически
            original_rate = float(item.get('rate', 0))
            logger.info(f"💰 Line item rate (exclusive): {original_rate}")
    
    return line_items
```

### Этап 3: Поддержка Expense для чеков (2-3 часа)

#### 3.1 Добавить определение типа документа
```python
def determine_document_action(self, analysis: Dict) -> str:
    """Определяет что создавать: BILL или EXPENSE"""
    
    document_type = analysis.get('document_type', '').lower()
    supplier_name = (analysis.get('supplier_name') or '').lower()
    
    # PARAGON FISKALNY → EXPENSE
    is_paragon = (
        document_type == 'receipt' or
        'paragon' in (analysis.get('extracted_text') or '').lower() or
        'fiskalny' in (analysis.get('extracted_text') or '').lower() or
        'leroy-merlin' in supplier_name or
        'biedronka' in supplier_name
    )
    
    if is_paragon:
        logger.info("📋 Документ определен как PARAGON FISKALNY → создаем EXPENSE")
        return 'EXPENSE'
    
    logger.info("📋 Документ определен как INVOICE → создаем BILL")
    return 'BILL'
```

#### 3.2 Добавить создание Expense
```python
async def create_expense_from_analysis(self, analysis: Dict, supplier: Dict, org_id: str) -> Dict:
    """Создает Expense из анализа чека"""
    from telegram_bot.services.account_manager import AccountManager
    from functions.zoho_api import create_expense, find_tax_by_percent
    
    # Определяем способ оплаты из текста
    text = (analysis.get('extracted_text') or '').lower()
    if 'gotówka' in text or 'cash' in text:
        payment_type = 'personal'  # Petty Cash
    else:
        payment_type = 'business'  # Konto Firmowe
    
    # Получаем счета
    paid_through_account_id = AccountManager.get_paid_through_account(org_id, payment_type)
    expense_account_id = AccountManager.get_expense_account(
        org_id, 
        f"Supplier: {analysis.get('supplier_name')}, Items: {analysis.get('service_description')}"
    )
    
    # Налоги
    tax_rate = analysis.get('tax_rate', 23)
    tax_id = find_tax_by_percent(org_id, tax_rate)
    
    # Сумма (используем gross для чеков)
    amount = analysis.get('gross_amount') or analysis.get('total_amount', 0)
    
    expense_payload = {
        "account_id": expense_account_id,
        "paid_through_account_id": paid_through_account_id,
        "vendor_id": supplier.get('contact_id'),
        "currency_code": analysis.get('currency', 'PLN'),
        "amount": float(amount),
        "date": analysis.get('issue_date') or datetime.now().strftime('%Y-%m-%d'),
        "reference_number": analysis.get('bill_number', ''),
        "description": f"Чек от {analysis.get('supplier_name')}",
        "notes": self._create_expense_notes(analysis)
    }
    
    if tax_id and tax_rate > 0:
        expense_payload.update({
            "tax_id": tax_id,
            "tax_amount": float(analysis.get('vat_amount', 0))
        })
    
    logger.info(f"💳 Создание Expense: {amount} {analysis.get('currency', 'PLN')} (payment: {payment_type})")
    
    return create_expense(org_id, expense_payload)
```

### Этап 4: Интеграция с Telegram handlers (1-2 часа)

#### 4.1 Создать WorkDrive Service
```python
# telegram_bot/services/workdrive_service.py
class WorkDriveService:
    """Сервис для интеграции WorkDrive Processor с Telegram handlers"""
    
    def __init__(self):
        self.processor = WorkDriveBatchProcessor()
    
    async def process_single_document(self, file_path: str, analysis: Dict) -> Dict:
        """Обрабатывает один документ через WorkDrive логику"""
        
        # Используем логику из WorkDrive Processor
        branch = BranchManager.determine_branch(analysis)
        org_id = branch['org_id']
        
        # Определяем тип действия
        action = self.processor.determine_document_action(analysis)
        
        if action == 'EXPENSE':
            return await self.processor.create_expense_from_analysis(analysis, supplier, org_id)
        else:
            return await self.processor.create_bill_from_analysis(analysis, supplier, org_id)
```

#### 4.2 Интегрировать в handlers без увеличения размера
```python
# В telegram_bot/handlers.py добавить только:
from telegram_bot.services.workdrive_service import WorkDriveService

# Заменить существующие вызовы создания Bill/Expense на:
workdrive_service = WorkDriveService()
result = await workdrive_service.process_single_document(file_path, analysis)
```

## 📊 Метрики успеха

### ✅ Критерии завершения:
1. **Логика филиалов работает** - цветочные документы создаются для Iris flowers atelier
2. **VAT логика точная** - правильное определение inclusive/exclusive
3. **Expense поддержка** - чеки создают Expense вместо Bill
4. **Размер handlers.py не увеличился** - вся логика в сервисах
5. **Обратная совместимость** - существующий функционал работает

### 📈 Ожидаемые улучшения:
- **Точность VAT**: 85% → 98%
- **Правильность филиалов**: 50% → 100%  
- **Обработка чеков**: 0% → 100%
- **Читаемость кода**: Значительное улучшение

## 🚀 Следующие шаги

1. **Создать Branch Manager** (30 минут)
2. **Улучшить VAT логику** (60 минут)  
3. **Добавить Expense поддержку** (90 минут)
4. **Создать WorkDrive Service** (45 минут)
5. **Интегрировать в handlers** (30 минут)
6. **Тестирование на файлах за 19 августа** (30 минут)

**Общее время: 5-6 часов**

---
*Обновлено: 2025-09-08*
*Статус: 📋 План готов к выполнению*
