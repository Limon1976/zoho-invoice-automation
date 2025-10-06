# Branch Logic Implementation
*Создано: 2025-09-0*

## 🎯 Задача
Реализовать логику филиалов для автоматического определения правильного филиала при создании Bills/Expenses на основе цветочных маркеров.

## 🌸 Логика определения филиалов

### Правила определения:
1. **Iris flowers atelier** → если LLM определил цветы, коробки, ленточки
2. **PARKENTERTAINMENT** → все остальные документы (по умолчанию)
3. **TaVie Europe OÜ** → если VAT покупателя EE102288270

### Цветочные маркеры:
- **LLM категория**: `product_category == 'FLOWERS'`
- **Найденные цветы**: `detected_flower_names` не пустой
- **Поставщик**: `supplier_name` содержит "hibispol"
- **Ключевые слова**: коробки, ленточки, flowers, цветы

## 📋 Техническая реализация

### 1. Создать Branch Manager

```python
# telegram_bot/services/branch_manager.py
"""
Управление филиалами и автоматическое определение правильного филиала
для создания Bills и Expenses в Zoho Books
"""

from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

class BranchManager:
    """Управление филиалами и определение правильной организации"""
    
    # Конфигурация филиалов
    BRANCHES = {
        'PARKENTERTAINMENT': {
            'org_id': '20082562863',
            'name': 'PARKENTERTAINMENT Sp. z o. o.',
            'vat': 'PL5272956146',
            'default_branch': True,
            'description': 'Основная польская организация'
        },
        'IRIS_FLOWERS': {
            'org_id': '20082562863',  # Тот же что и PARKENTERTAINMENT
            'name': 'Iris flowers atelier',
            'parent_org': 'PARKENTERTAINMENT',
            'branch_id': None,  # Будет определен позже из Zoho
            'keywords': ['flowers', 'цветы', 'коробки', 'ленточки', 'hibispol'],
            'description': 'Цветочный филиал PARKENTERTAINMENT'
        },
        'TAVIE_EUROPE': {
            'org_id': '20092948714',
            'name': 'TaVie Europe OÜ',
            'vat': 'EE102288270',
            'description': 'Эстонская организация'
        }
    }
    
    @classmethod
    def determine_branch(cls, analysis: Dict) -> Dict:
        """
        Определяет филиал на основе анализа документа
        
        Args:
            analysis: Результат LLM анализа документа
            
        Returns:
            Dict с информацией о филиале
        """
        logger.info("🏢 Начало определения филиала")
        
        # 1. ПРИОРИТЕТ: Цветочные маркеры → Iris flowers atelier
        if cls._is_flowers_document(analysis):
            branch = cls.BRANCHES['IRIS_FLOWERS']
            logger.info(f"🌸 Определен цветочный филиал: {branch['name']}")
            return branch
        
        # 2. По VAT покупателя (buyer_vat)
        buyer_vat = analysis.get('buyer_vat', '').replace(' ', '').upper()
        if buyer_vat:
            for branch_key, branch in cls.BRANCHES.items():
                branch_vat = branch.get('vat', '').replace(' ', '').upper()
                if branch_vat and branch_vat in buyer_vat:
                    logger.info(f"🏢 Филиал определен по VAT {buyer_vat}: {branch['name']}")
                    return branch
        
        # 3. По умолчанию PARKENTERTAINMENT
        branch = cls.BRANCHES['PARKENTERTAINMENT']
        logger.info(f"🏢 Филиал по умолчанию: {branch['name']}")
        return branch
    
    @classmethod
    def _is_flowers_document(cls, analysis: Dict) -> bool:
        """
        Проверяет является ли документ цветочным
        
        Args:
            analysis: Результат LLM анализа
            
        Returns:
            True если документ цветочный
        """
        # 1. LLM определил категорию FLOWERS
        llm_category = (analysis.get('product_category') or '').upper()
        detected_flowers = analysis.get('detected_flower_names', [])
        
        if llm_category == 'FLOWERS' and detected_flowers:
            logger.info(f"🌸 LLM определил цветы: category={llm_category}, flowers={len(detected_flowers)}")
            return True
        
        # 2. Поставщик цветов (HIBISPOL)
        supplier_name = (analysis.get('supplier_name') or '').lower()
        if 'hibispol' in supplier_name:
            logger.info(f"🌸 Цветочный поставщик: {supplier_name}")
            return True
        
        # 3. Ключевые слова в тексте документа
        text = (analysis.get('extracted_text') or '').lower()
        flower_keywords = ['коробки', 'ленточки', 'flowers', 'цветы', 'букет', 'композиция']
        
        found_keywords = [kw for kw in flower_keywords if kw in text]
        if found_keywords:
            logger.info(f"🌸 Найдены цветочные ключевые слова: {found_keywords}")
            return True
        
        # 4. Специальные маркеры в line_items
        line_items = analysis.get('line_items', [])
        for item in line_items:
            item_desc = (item.get('description', '') + item.get('name', '')).lower()
            if any(kw in item_desc for kw in flower_keywords):
                logger.info(f"🌸 Цветочные маркеры в позициях: {item_desc[:50]}...")
                return True
        
        logger.info("📋 Документ не определен как цветочный")
        return False
    
    @classmethod
    def get_branch_by_org_id(cls, org_id: str) -> Optional[Dict]:
        """
        Получает информацию о филиале по org_id
        
        Args:
            org_id: ID организации в Zoho
            
        Returns:
            Информация о филиале или None
        """
        for branch in cls.BRANCHES.values():
            if branch['org_id'] == org_id:
                return branch
        return None
    
    @classmethod
    def get_all_branches(cls) -> Dict:
        """Возвращает все настроенные филиалы"""
        return cls.BRANCHES.copy()
    
    @classmethod
    def is_flowers_branch(cls, branch_key: str) -> bool:
        """Проверяет является ли филиал цветочным"""
        return branch_key == 'IRIS_FLOWERS'
```

### 2. Интегрировать в WorkDrive Processor

```python
# В functions/workdrive_batch_processor.py добавить:

def determine_organization(self, analysis: Dict) -> str:
    """Определяет организацию для создания Bill на основе анализа документа"""
    from telegram_bot.services.branch_manager import BranchManager
    
    # Используем новую логику филиалов
    branch = BranchManager.determine_branch(analysis)
    org_id = branch['org_id']
    branch_name = branch['name']
    
    logger.info(f"🏢 Определен филиал: {branch_name} (org_id: {org_id})")
    
    # Сохраняем информацию о филиале для использования в других методах
    self.current_branch = branch
    
    # Если это цветочный филиал, добавляем специальную обработку
    if BranchManager.is_flowers_branch(self._get_branch_key(branch)):
        logger.info("🌸 Активирована специальная обработка для цветочного филиала")
        self.is_flowers_processing = True
    else:
        self.is_flowers_processing = False
    
    return org_id

def _get_branch_key(self, branch: Dict) -> str:
    """Определяет ключ филиала по его данным"""
    for key, branch_config in BranchManager.get_all_branches().items():
        if branch_config['name'] == branch['name']:
            return key
    return 'PARKENTERTAINMENT'  # fallback
```

### 3. Создать тесты для Branch Manager

```python
# tests/test_branch_manager.py
"""
Тесты для Branch Manager - определение филиалов
"""

import pytest
from telegram_bot.services.branch_manager import BranchManager

class TestBranchManager:
    """Тесты для BranchManager"""
    
    def test_flowers_detection_by_category(self):
        """Тест определения цветов по LLM категории"""
        analysis = {
            'product_category': 'FLOWERS',
            'detected_flower_names': ['роза', 'тюльпан'],
            'supplier_name': 'Test Supplier'
        }
        
        branch = BranchManager.determine_branch(analysis)
        
        assert branch['name'] == 'Iris flowers atelier'
        assert branch['org_id'] == '20082562863'
    
    def test_flowers_detection_by_supplier(self):
        """Тест определения цветов по поставщику HIBISPOL"""
        analysis = {
            'supplier_name': 'HIBISPOL Sp. z o.o.',
            'product_category': 'OTHER'
        }
        
        branch = BranchManager.determine_branch(analysis)
        
        assert branch['name'] == 'Iris flowers atelier'
    
    def test_flowers_detection_by_keywords(self):
        """Тест определения цветов по ключевым словам"""
        analysis = {
            'supplier_name': 'Regular Supplier',
            'extracted_text': 'Заказ коробки для цветов и ленточки для букета',
            'product_category': 'OTHER'
        }
        
        branch = BranchManager.determine_branch(analysis)
        
        assert branch['name'] == 'Iris flowers atelier'
    
    def test_default_branch_selection(self):
        """Тест выбора филиала по умолчанию"""
        analysis = {
            'supplier_name': 'Regular Supplier',
            'product_category': 'SERVICES',
            'extracted_text': 'Regular service invoice'
        }
        
        branch = BranchManager.determine_branch(analysis)
        
        assert branch['name'] == 'PARKENTERTAINMENT Sp. z o. o.'
        assert branch['default_branch'] is True
    
    def test_tavie_europe_by_vat(self):
        """Тест определения TaVie Europe по VAT"""
        analysis = {
            'buyer_vat': 'EE102288270',
            'supplier_name': 'Estonian Supplier'
        }
        
        branch = BranchManager.determine_branch(analysis)
        
        assert branch['name'] == 'TaVie Europe OÜ'
        assert branch['org_id'] == '20092948714'
```

## 📊 Тестирование

### Тестовые сценарии:
1. **Цветочный документ от HIBISPOL** → Iris flowers atelier
2. **Обычный инвойс** → PARKENTERTAINMENT
3. **Документ с VAT EE102288270** → TaVie Europe OÜ
4. **Документ с ключевыми словами "коробки"** → Iris flowers atelier

### Команды для тестирования:
```bash
# Запуск тестов Branch Manager
python -m pytest tests/test_branch_manager.py -v

# Тестирование на реальных файлах
python functions/workdrive_batch_processor.py --test --date 2025-08-19
```

## 🚀 Следующие шаги

1. **Создать Branch Manager** (30 минут)
2. **Интегрировать в WorkDrive Processor** (15 минут)
3. **Создать тесты** (30 минут)
4. **Протестировать на файлах за 19 августа** (15 минут)

**Общее время: 1.5 часа**

---
*Обновлено: 2025-09-08*
*Статус: 📋 Готов к реализации*
