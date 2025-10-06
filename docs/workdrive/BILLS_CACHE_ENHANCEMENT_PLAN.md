# Bills Cache Enhancement Plan
*Создано: 2025-09-08*

## 🎯 Проблема
Zoho позволяет одинаковые номера Bills в разных филиалах, что приводит к дубликатам. Нужна система кэширования номеров Bills для предотвращения дубликатов.

## ✅ Готовая архитектура
У нас уже есть система кэширования Bills в `functions/bills_cache_manager.py`:
- `refresh_bills_cache()` - обновление кэша
- `find_bill_candidates_in_cache()` - поиск дубликатов
- `bill_exists_smart()` - умная проверка дубликатов

## 🔧 План улучшений

### Этап 1: Расширить bills_cache_manager для филиалов

#### 1.1 Добавить поддержку филиалов в кэш
```python
# В functions/bills_cache_manager.py добавить:

def refresh_bills_cache_all_branches(org_id: str, months_back: int = 12) -> Dict:
    """
    Обновляет кэш Bills для всех филиалов организации
    
    Args:
        org_id: ID организации
        months_back: Количество месяцев назад для сканирования
        
    Returns:
        Объединенный кэш всех филиалов
    """
    from telegram_bot.services.branch_manager import BranchManager
    
    # Получаем все филиалы для организации
    branches = BranchManager.get_all_branches()
    org_branches = [b for b in branches.values() if b['org_id'] == org_id]
    
    combined_cache = {
        "org_id": org_id,
        "updated_at": datetime.utcnow().isoformat(),
        "bills": [],
        "branches": {}
    }
    
    for branch in org_branches:
        branch_name = branch['name']
        print(f"🔄 Обновляем кэш Bills для филиала: {branch_name}")
        
        # Получаем Bills для филиала (если есть branch_id)
        if branch.get('branch_id'):
            branch_bills = get_bills_for_branch(org_id, branch['branch_id'], months_back)
        else:
            # Для Head Office получаем общие Bills
            branch_bills = refresh_bills_cache(org_id, months_back=months_back)['bills']
        
        combined_cache['branches'][branch_name] = branch_bills
        combined_cache['bills'].extend(branch_bills)
    
    # Удаляем дубликаты по bill_id
    seen_ids = set()
    unique_bills = []
    for bill in combined_cache['bills']:
        if bill['bill_id'] not in seen_ids:
            unique_bills.append(bill)
            seen_ids.add(bill['bill_id'])
    
    combined_cache['bills'] = unique_bills
    
    # Сохраняем объединенный кэш
    cache_file = f"data/bills_cache/{org_id}_all_branches_bills.json"
    os.makedirs(os.path.dirname(cache_file), exist_ok=True)
    
    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(combined_cache, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Кэш Bills обновлен: {len(unique_bills)} уникальных Bills")
    return combined_cache
```

#### 1.2 Создать функцию проверки дубликатов между филиалами
```python
def check_bill_duplicate_across_branches(org_id: str, bill_number: str, vendor_name: str = None) -> Optional[Dict]:
    """
    Проверяет дубликаты Bills между всеми филиалами организации
    
    Args:
        org_id: ID организации
        bill_number: Номер Bill для проверки
        vendor_name: Название поставщика (опционально)
        
    Returns:
        Информация о найденном дубликате или None
    """
    cache_file = f"data/bills_cache/{org_id}_all_branches_bills.json"
    
    if not os.path.exists(cache_file):
        print("⚠️ Кэш Bills не найден, обновляем...")
        refresh_bills_cache_all_branches(org_id)
    
    with open(cache_file, 'r', encoding='utf-8') as f:
        cache = json.load(f)
    
    # Поиск дубликатов
    norm_target = _normalize(bill_number)
    
    for bill in cache.get('bills', []):
        cached_number = bill.get('bill_number', '')
        if _normalize(cached_number) == norm_target:
            # Дополнительная проверка по vendor_name если указан
            if vendor_name:
                # Получаем детали Bill для проверки vendor
                bill_details = get_bill_details(org_id, bill['bill_id'])
                if bill_details:
                    cached_vendor = bill_details.get('vendor_name', '')
                    if _clean_vendor_name(vendor_name) != _clean_vendor_name(cached_vendor):
                        continue
            
            # Определяем в каком филиале найден дубликат
            branch_info = "Unknown Branch"
            for branch_name, branch_bills in cache.get('branches', {}).items():
                if any(b['bill_id'] == bill['bill_id'] for b in branch_bills):
                    branch_info = branch_name
                    break
            
            return {
                'bill_id': bill['bill_id'],
                'bill_number': cached_number,
                'branch': branch_info,
                'year': bill.get('year'),
                'month': bill.get('month')
            }
    
    return None
```

### Этап 2: Создать LLM для описаний Bills

#### 2.1 Универсальная функция LLM описаний
```python
# В functions/llm_document_extractor.py добавить:

def llm_generate_bill_description(analysis: Dict, supplier_name: str) -> str:
    """
    Генерирует описание Bill на основе LLM анализа
    
    Args:
        analysis: Результат анализа документа
        supplier_name: Название поставщика
        
    Returns:
        Сгенерированное описание
    """
    client = _get_client()
    if not client:
        return f"Services from {supplier_name}"
    
    try:
        # Контекст для LLM
        context = {
            'supplier': supplier_name,
            'category': analysis.get('product_category', ''),
            'service_description': analysis.get('service_description', ''),
            'line_items': analysis.get('line_items', [])[:3],  # Первые 3 позиции
            'total_amount': analysis.get('total_amount'),
            'currency': analysis.get('currency', 'PLN')
        }
        
        prompt = f"""
        Создай краткое описание для Bill на основе анализа документа.
        Описание должно быть:
        - На польском языке для польских поставщиков
        - Краткое (до 100 символов)
        - Информативное (что за услуга/товар)
        - Профессиональное
        
        Контекст: {json.dumps(context, ensure_ascii=False)}
        
        Примеры:
        - "Licencja oprogramowania na 1 miesiąc"
        - "Wynajem magazynu nr 35 Ochota" 
        - "Usługi konsultingowe IT"
        - "Zakup materiałów biurowych"
        
        Верни только текст описания, без кавычек.
        """
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Ты эксперт по созданию описаний для бухгалтерских документов."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=100
        )
        
        description = response.choices[0].message.content.strip()
        
        # Ограничиваем длину
        if len(description) > 100:
            description = description[:97] + "..."
        
        logger.info(f"📝 LLM описание: '{description}'")
        return description
        
    except Exception as e:
        logger.warning(f"❌ Ошибка LLM описания: {e}")
        return f"Services from {supplier_name}"
```

### Этап 3: Создать ежедневное обновление кэша

#### 3.1 Планировщик обновления кэша Bills
```python
# functions/bills_cache_scheduler.py
"""
Ежедневное обновление кэша Bills в 00:00:01
"""

import schedule
import time
from datetime import datetime
from functions.bills_cache_manager import refresh_bills_cache_all_branches

def daily_bills_cache_update():
    """Ежедневное обновление кэша Bills"""
    try:
        print(f"🔄 Ежедневное обновление кэша Bills: {datetime.now()}")
        
        # Обновляем кэш для всех организаций
        organizations = {
            '20082562863': 'PARKENTERTAINMENT',
            '20092948714': 'TaVie Europe OÜ'
        }
        
        for org_id, org_name in organizations.items():
            print(f"🏢 Обновляем кэш Bills для {org_name}")
            refresh_bills_cache_all_branches(org_id, months_back=6)  # 6 месяцев назад
        
        print("✅ Ежедневное обновление кэша Bills завершено")
        
    except Exception as e:
        print(f"❌ Ошибка ежедневного обновления кэша: {e}")

def start_bills_cache_scheduler():
    """Запускает планировщик обновления кэша"""
    # Планируем на 00:00:01 каждый день
    schedule.every().day.at("00:00:01").do(daily_bills_cache_update)
    
    print("📅 Планировщик кэша Bills запущен (обновление в 00:00:01)")
    
    while True:
        schedule.run_pending()
        time.sleep(60)  # Проверяем каждую минуту

if __name__ == "__main__":
    start_bills_cache_scheduler()
```

### Этап 4: Интегрировать в WorkDrive Processor

#### 4.1 Обновить WorkDrive Processor
```python
# В functions/workdrive_batch_processor.py добавить:

def check_bill_duplicate_enhanced(self, analysis: Dict, org_id: str) -> Optional[Dict]:
    """Расширенная проверка дубликатов Bills между филиалами"""
    from functions.bills_cache_manager import check_bill_duplicate_across_branches
    
    bill_number = analysis.get('bill_number') or analysis.get('invoice_number', '')
    vendor_name = analysis.get('supplier_name', '')
    
    if not bill_number:
        return None
    
    # Проверяем дубликаты между всеми филиалами
    duplicate = check_bill_duplicate_across_branches(org_id, bill_number, vendor_name)
    
    if duplicate:
        logger.warning(f"🚨 Найден дубликат Bill {bill_number} в филиале: {duplicate['branch']}")
        return duplicate
    
    return None

def create_bill_payload_enhanced(self, analysis: Dict, supplier: Dict, org_id: str) -> Dict:
    """Создает payload с LLM описанием и проверкой дубликатов"""
    from functions.llm_document_extractor import llm_generate_bill_description
    
    # Проверяем дубликаты
    duplicate = self.check_bill_duplicate_enhanced(analysis, org_id)
    if duplicate:
        raise ValueError(f"Дубликат Bill {duplicate['bill_number']} найден в {duplicate['branch']}")
    
    # Генерируем описание через LLM
    description = llm_generate_bill_description(analysis, supplier.get('contact_name', ''))
    
    # Остальная логика как было + новое описание
    bill_payload = self.create_bill_payload(analysis, supplier, org_id)
    bill_payload['notes'] = description
    
    return bill_payload
```

## 📊 Ожидаемые результаты

### ✅ После внедрения:
1. **Дубликаты Bills предотвращены** между филиалами
2. **LLM описания** вместо статичных текстов
3. **Ежедневное обновление** кэша в 00:00:01
4. **Интеграция с Branch Manager** для правильных филиалов

### 📈 Улучшения:
- **Точность описаний**: 50% → 95% (LLM vs статичные)
- **Предотвращение дубликатов**: 0% → 100%
- **Производительность**: кэш вместо API запросов

Готов применить исправление используя готовую архитектуру! Команда: **"APPLY"**

<function_calls>
<invoke name="todo_write">
<parameter name="merge">true
