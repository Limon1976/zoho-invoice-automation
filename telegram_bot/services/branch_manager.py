"""
Branch Manager - Управление филиалами и автоматическое определение правильного филиала
для создания Bills и Expenses в Zoho Books

Создано: 2025-09-07
Цель: Автоматически определять филиал Iris flowers atelier (browary) и Wileńska для цветочных документов
"""

from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

class BranchManager:
    """Управление филиалами и определение правильной организации"""
    
    # Конфигурация филиалов
    BRANCHES = {
        'HEAD_OFFICE': {
            'org_id': '20082562863',
            'name': 'PARKENTERTAINMENT Sp. z o. o.',
            'vat': 'PL5272956146',
            'branch_id': '281497000000355003',  # Реальный branch_id из Zoho
            'default_branch': True,
            'description': 'Head Office - главный офис'
        },
        'IRIS_FLOWERS': {
            'org_id': '20082562863',  # Тот же что и Head Office
            'name': 'Iris flowers atelier',
            'parent_org': 'HEAD_OFFICE',
            'branch_id': '281497000000355063',  # Реальный branch_id из Zoho
            'keywords': ['flowers', 'цветы', 'коробки', 'ленточки', 'hibispol', 'browary', 'iris'],
            'description': 'Основной цветочный магазин'
        },
        'WILENSKA': {
            'org_id': '20082562863',  # Тот же что и Head Office
            'name': 'Wileńska',
            'parent_org': 'HEAD_OFFICE',
            'branch_id': '281497000002901751',  # Реальный branch_id из Zoho
            'keywords': ['wileńska', 'wilenska', 'praga', 'второй магазин'],
            'description': 'Второй цветочный магазин (Praga)'
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
        
        # 1. ПРИОРИТЕТ: Покупки автомобилей → Head Office
        if cls._is_car_purchase(analysis):
            branch = cls.BRANCHES['HEAD_OFFICE']
            logger.info(f"🚗 Покупка автомобиля → Head Office: {branch['name']}")
            return branch
        
        # 2. Цветочные маркеры → определяем конкретный цветочный филиал
        if cls._is_flowers_document(analysis):
            flower_branch_key = cls._determine_flower_branch(analysis)
            branch = cls.BRANCHES[flower_branch_key]
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
        
        # 3. По умолчанию Head Office
        branch = cls.BRANCHES['HEAD_OFFICE']
        logger.info(f"🏢 Филиал по умолчанию: {branch['name']}")
        return branch
    
    @classmethod
    def _determine_flower_branch(cls, analysis: Dict) -> Optional[str]:
        """
        Определяет конкретный цветочный филиал
        
        Args:
            analysis: Результат LLM анализа
            
        Returns:
            Ключ цветочного филиала или None
        """
        text = (analysis.get('extracted_text') or '').lower()
        supplier_name = (analysis.get('supplier_name') or '').lower()
        
        # ИСПРАВЛЕННАЯ ЛОГИКА: Сначала проверяем HIBISPOL, потом общие маркеры
        hibispol_supplier = 'hibispol' in supplier_name
        
        if hibispol_supplier:
            # Для HIBISPOL: сначала ищем явные маркеры Wileńska
            wilenska_keywords = [
                'wileńska', 'wilenska', 'wileńśka', 'wilenska', 
                'praga', 'warszawa praga', 'praga warszawa',
                'wileńska 21', 'wileńska 22', 'wileńska 23', 'wileńska 24', 'wileńska 25',
                'wileńśka 21', 'wileńśka 22', 'wileńśka 23', 'wileńśka 24', 'wileńśka 25'
            ]
            
            found_wilenska = [kw for kw in wilenska_keywords if kw in text]
            if found_wilenska:
                logger.info(f"🌸 HIBISPOL с маркерами Wileńska → Wileńska (найдены: {found_wilenska})")
                return 'WILENSKA'
            
            # HIBISPOL без маркеров Wileńska → Iris flowers atelier по умолчанию
            logger.info(f"🌸 HIBISPOL без маркеров Wileńska → Iris flowers atelier (основной по умолчанию)")
            return 'IRIS_FLOWERS'
        
        # Для НЕ-HIBISPOL поставщиков: общие маркеры филиалов
        wilenska_keywords = ['wileńska', 'wilenska', 'wileńśka', 'praga']
        found_wilenska = [kw for kw in wilenska_keywords if kw in text]
        if found_wilenska:
            logger.info(f"🌸 Определен второй цветочный магазин: Wileńska (найдены: {found_wilenska})")
            return 'WILENSKA'
        
        # Проверяем маркеры для основного Iris flowers atelier
        iris_keywords = ['iris', 'browary', 'основной магазин']
        found_iris_keywords = [kw for kw in iris_keywords if kw in text]
        if found_iris_keywords:
            logger.info(f"🌸 Определен основной цветочный магазин: Iris flowers atelier (найдены: {found_iris_keywords})")
            return 'IRIS_FLOWERS'
        
        # По умолчанию для цветочных документов - основной магазин
        logger.info(f"🌸 Цветочный документ → Iris flowers atelier (по умолчанию)")
        return 'IRIS_FLOWERS'
    
    @classmethod
    def _is_flowers_document(cls, analysis: Dict) -> bool:
        """
        Проверяет является ли документ цветочным или относящимся к обслуживанию цветочных магазинов
        
        Args:
            analysis: Результат LLM анализа
            
        Returns:
            True если документ относится к цветочному бизнесу
        """
        text = (analysis.get('extracted_text') or '').lower()
        supplier_name = (analysis.get('supplier_name') or '').lower()
        
        # 1. LLM определил категорию FLOWERS
        llm_category = (analysis.get('product_category') or '').upper()
        detected_flowers = analysis.get('detected_flower_names', [])
        
        if llm_category == 'FLOWERS' and detected_flowers:
            logger.info(f"🌸 LLM определил цветы: category={llm_category}, flowers={len(detected_flowers)}")
            return True
        
        # 2. Поставщик цветов (HIBISPOL)
        if 'hibispol' in supplier_name:
            logger.info(f"🌸 Цветочный поставщик: {supplier_name}")
            return True
        
        # 3. DOTYPOSPL - лицензии для цветочных филиалов
        if 'dotypospl' in supplier_name:
            logger.info(f"🌸 DOTYPOSPL лицензии → Iris flowers atelier (общие для 2 филиалов)")
            return True
        
        # 4. Маркеры обслуживания цветочных магазинов
        service_markers = [
            'iris flowers - gw005',  # Вода для Iris flowers
            'iris flowers',          # Общий маркер магазина
            'browary',              # Адрес Iris flowers atelier
            'wileńska',             # Адрес Wileńska
            'wilenska',
            'praga'                 # Район Wileńska
        ]
        
        found_service_markers = [marker for marker in service_markers if marker in text]
        if found_service_markers:
            logger.info(f"🌸 Найдены маркеры обслуживания цветочных магазинов: {found_service_markers}")
            return True
        
        # 5. Ключевые слова цветочного бизнеса
        flower_keywords = ['коробки', 'ленточки', 'flowers', 'цветы', 'букет', 'композиция', 'аренда магазин']
        
        found_keywords = [kw for kw in flower_keywords if kw in text]
        if found_keywords:
            logger.info(f"🌸 Найдены цветочные ключевые слова: {found_keywords}")
            return True
        
        # 6. Специальные маркеры в line_items
        line_items = analysis.get('line_items', [])
        for item in line_items:
            item_desc = (item.get('description', '') + item.get('name', '')).lower()
            if any(kw in item_desc for kw in flower_keywords + service_markers):
                logger.info(f"🌸 Цветочные/сервисные маркеры в позициях: {item_desc[:50]}...")
                return True
        
        # 7. Анализ типа услуг для цветочного бизнеса
        service_desc = (analysis.get('service_description') or '').lower()
        if any(marker in service_desc for marker in service_markers + flower_keywords):
            logger.info(f"🌸 Цветочные маркеры в описании услуг: {service_desc[:50]}...")
            return True
        
        logger.info("📋 Документ не определен как относящийся к цветочному бизнесу")
        return False
    
    @classmethod
    def _is_car_purchase(cls, analysis: Dict) -> bool:
        """
        Проверяет является ли документ покупкой автомобиля
        
        Args:
            analysis: Результат LLM анализа
            
        Returns:
            True если это покупка автомобиля
        """
        # 1. VIN номер в документе
        vin = analysis.get('vin', '')
        if vin and len(vin) == 17:
            logger.info(f"🚗 Найден VIN номер: {vin}")
            return True
        
        # 2. LLM определил категорию CARS
        llm_category = (analysis.get('product_category') or '').upper()
        if llm_category == 'CARS':
            logger.info(f"🚗 LLM определил автомобиль: category={llm_category}")
            return True
        
        # 3. Автомобильные марки в тексте
        text = (analysis.get('extracted_text') or '').lower()
        car_brands = ['bmw', 'mercedes', 'audi', 'volkswagen', 'porsche', 'toyota', 'honda', 'ford']
        
        found_brands = [brand for brand in car_brands if brand in text]
        if found_brands:
            # Дополнительно проверяем автомобильные ключевые слова
            car_keywords = ['vehicle', 'car', 'auto', 'fahrzeug', 'samochód', 'pojazd']
            if any(kw in text for kw in car_keywords):
                logger.info(f"🚗 Найдены автомобильные маркеры: brands={found_brands}, keywords={[kw for kw in car_keywords if kw in text]}")
                return True
        
        # 4. Автомобильные поставщики
        supplier_name = (analysis.get('supplier_name') or '').lower()
        auto_suppliers = ['autohaus', 'auto', 'car', 'mobile.de', 'autoscout']
        
        if any(supplier in supplier_name for supplier in auto_suppliers):
            logger.info(f"🚗 Автомобильный поставщик: {supplier_name}")
            return True
        
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
    
    @classmethod
    def get_branch_key_by_name(cls, branch_name: str) -> Optional[str]:
        """
        Получает ключ филиала по его названию
        
        Args:
            branch_name: Название филиала
            
        Returns:
            Ключ филиала или None
        """
        for key, branch in cls.BRANCHES.items():
            if branch['name'] == branch_name:
                return key
        return None
    
    @classmethod
    def get_branch_display_info(cls, branch: Dict) -> str:
        """
        Создает красивое отображение информации о филиале
        
        Args:
            branch: Информация о филиале
            
        Returns:
            Форматированная строка с информацией
        """
        name = branch.get('name', 'Unknown Branch')
        org_id = branch.get('org_id', 'Unknown')
        
        if branch.get('description'):
            return f"{name} (org_id: {org_id}) - {branch['description']}"
        else:
            return f"{name} (org_id: {org_id})"
