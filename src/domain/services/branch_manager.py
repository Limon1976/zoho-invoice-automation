"""
Branch Manager - Модуль для интеллектуального управления ветками Zoho Books.

Функциональность:
- Автоматическая фильтрация активных веток
- Попытка активации неактивных веток через API (если есть права)
- Умный fallback к Head Office
- Кэширование с TTL
- Подробное логирование
"""

import json
import os
import requests
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

@dataclass
class BranchInfo:
    """Информация о ветке Zoho Books"""
    branch_id: str
    name: str
    is_active: bool
    status: str
    address: str
    email: str
    is_primary: bool = False

class BranchManager:
    """
    Интеллектуальный менеджер веток для Zoho Books.
    
    Особенности:
    - Фильтрует только активные ветки
    - Пытается активировать неактивные ветки при необходимости
    - Предоставляет fallback к Head Office
    - Кэширует результаты с TTL 24 часа
    """
    
    def __init__(self, access_token: str, cache_dir: str = "data/optimized_cache"):
        self.access_token = access_token
        self.cache_dir = cache_dir
        self.cache_ttl_hours = 24
        self.api_base_url = "https://www.zohoapis.eu/books/v3"
        
        # Создаем директорию для кэша
        os.makedirs(cache_dir, exist_ok=True)
    
    def _get_cache_path(self, org_id: str) -> str:
        """Путь к файлу кэша веток"""
        return os.path.join(self.cache_dir, f"branches_manager_{org_id}.json")
    
    def _is_cache_valid(self, cache_path: str) -> bool:
        """Проверяет валидность кэша по TTL"""
        if not os.path.exists(cache_path):
            return False
        
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            cached_at = datetime.fromisoformat(data.get('cached_at', ''))
            return datetime.now() - cached_at < timedelta(hours=self.cache_ttl_hours)
        except Exception:
            return False
    
    def _load_cache(self, org_id: str) -> Optional[List[BranchInfo]]:
        """Загружает ветки из кэша если он валиден"""
        cache_path = self._get_cache_path(org_id)
        
        if not self._is_cache_valid(cache_path):
            return None
        
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            branches = []
            for branch_data in data.get('branches', []):
                branches.append(BranchInfo(**branch_data))
            
            logger.info(f"🏢 Загружено {len(branches)} веток из кэша для org {org_id}")
            return branches
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки кэша веток: {e}")
            return None
    
    def _save_cache(self, org_id: str, branches: List[BranchInfo]) -> None:
        """Сохраняет ветки в кэш"""
        cache_path = self._get_cache_path(org_id)
        
        try:
            data = {
                'cached_at': datetime.now().isoformat(),
                'org_id': org_id,
                'branches': [
                    {
                        'branch_id': b.branch_id,
                        'name': b.name,
                        'is_active': b.is_active,
                        'status': b.status,
                        'address': b.address,
                        'email': b.email,
                        'is_primary': b.is_primary
                    }
                    for b in branches
                ]
            }
            
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"💾 Кэш веток сохранен: {len(branches)} веток для org {org_id}")
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения кэша веток: {e}")
    
    def _fetch_branches_from_api(self, org_id: str) -> List[BranchInfo]:
        """Загружает ветки из Zoho API"""
        url = f"{self.api_base_url}/branches"
        headers = {"Authorization": f"Zoho-oauthtoken {self.access_token}"}
        params = {"organization_id": org_id, "per_page": 200}
        
        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            
            data = response.json()
            raw_branches = data.get('branches', [])
            
            branches = []
            for branch in raw_branches:
                branch_info = BranchInfo(
                    branch_id=branch.get('branch_id', ''),
                    name=branch.get('branch_name', ''),
                    is_active=branch.get('is_branch_active', False),
                    status=branch.get('branch_status', 'unknown'),
                    address=branch.get('address_formatted', ''),
                    email=branch.get('email', ''),
                    is_primary=branch.get('is_primary_branch', False)
                )
                branches.append(branch_info)
            
            logger.info(f"🌐 Загружено {len(branches)} веток из Zoho API для org {org_id}")
            return branches
            
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки веток из API: {e}")
            return []
    
    def get_active_branches(self, org_id: str, force_refresh: bool = False) -> List[BranchInfo]:
        """
        Возвращает только активные ветки.
        
        Args:
            org_id: ID организации Zoho
            force_refresh: Принудительно обновить кэш
        
        Returns:
            Список активных веток
        """
        # Пытаемся загрузить из кэша
        if not force_refresh:
            cached_branches = self._load_cache(org_id)
            if cached_branches is not None:
                active_branches = [b for b in cached_branches if b.is_active]
                logger.info(f"✅ Найдено {len(active_branches)} активных веток в кэше")
                return active_branches
        
        # Загружаем из API
        logger.info("🔄 Обновляем список веток из Zoho API...")
        all_branches = self._fetch_branches_from_api(org_id)
        
        # Фильтруем только активные
        active_branches = [b for b in all_branches if b.is_active]
        inactive_branches = [b for b in all_branches if not b.is_active]
        
        logger.info(f"📊 Статистика веток:")
        logger.info(f"  ✅ Активных: {len(active_branches)}")
        logger.info(f"  ❌ Неактивных: {len(inactive_branches)}")
        
        if inactive_branches:
            logger.warning("⚠️ Найдены неактивные ветки:")
            for branch in inactive_branches:
                logger.warning(f"  - {branch.name} (ID: {branch.branch_id}, Status: {branch.status})")
        
        # Сохраняем в кэш только активные ветки
        self._save_cache(org_id, active_branches)
        
        return active_branches
    
    def find_branch_by_names(self, org_id: str, preferred_names: List[str]) -> Optional[BranchInfo]:
        """
        Ищет активную ветку по списку предпочтительных названий.
        
        Args:
            org_id: ID организации
            preferred_names: Список названий для поиска
        
        Returns:
            Найденная активная ветка или None
        """
        import unicodedata
        
        def normalize(text: str) -> str:
            """Нормализует текст для поиска"""
            if not text:
                return ""
            normalized = unicodedata.normalize('NFKD', text)
            ascii_text = normalized.encode('ascii', 'ignore').decode('ascii')
            return ascii_text.strip().lower()
        
        # Нормализуем искомые названия
        normalized_targets = [normalize(name) for name in preferred_names if name]
        
        # Получаем активные ветки
        active_branches = self.get_active_branches(org_id)
        
        # Ищем по точному совпадению
        for branch in active_branches:
            normalized_branch = normalize(branch.name)
            if normalized_branch in normalized_targets:
                logger.info(f"🎯 Найдена активная ветка по точному совпадению: {branch.name}")
                return branch
        
        # Ищем по частичному совпадению
        for branch in active_branches:
            normalized_branch = normalize(branch.name)
            for target in normalized_targets:
                if target in normalized_branch or normalized_branch in target:
                    logger.info(f"🎯 Найдена активная ветка по частичному совпадению: {branch.name}")
                    return branch
        
        logger.warning(f"⚠️ Не найдена активная ветка среди: {preferred_names}")
        return None
    
    def get_head_office(self, org_id: str) -> Optional[BranchInfo]:
        """Возвращает Head Office (всегда активный fallback)"""
        active_branches = self.get_active_branches(org_id)
        
        # Ищем primary branch
        for branch in active_branches:
            if branch.is_primary:
                logger.info(f"🏢 Найден Head Office (primary): {branch.name}")
                return branch
        
        # Ищем по названию
        head_office = self.find_branch_by_names(org_id, ["head office", "головной офис"])
        if head_office:
            return head_office
        
        # Возвращаем первую активную ветку
        if active_branches:
            fallback = active_branches[0]
            logger.warning(f"⚠️ Head Office не найден, используем fallback: {fallback.name}")
            return fallback
        
        logger.error("❌ Не найдено ни одной активной ветки!")
        return None
    
    def try_activate_branch(self, org_id: str, branch_id: str) -> bool:
        """
        Пытается активировать неактивную ветку через API.
        
        Args:
            org_id: ID организации
            branch_id: ID ветки для активации
        
        Returns:
            True если активация успешна, False в противном случае
        """
        url = f"{self.api_base_url}/branches/{branch_id}"
        headers = {"Authorization": f"Zoho-oauthtoken {self.access_token}"}
        params = {"organization_id": org_id}
        
        # Данные для активации
        data = {
            "is_branch_active": True,
            "branch_status": "active"
        }
        
        try:
            response = requests.put(url, headers=headers, params=params, json=data)
            
            if response.status_code == 200:
                logger.info(f"✅ Ветка {branch_id} успешно активирована")
                # Принудительно обновляем кэш
                self.get_active_branches(org_id, force_refresh=True)
                return True
            else:
                logger.warning(f"⚠️ Не удалось активировать ветку {branch_id}: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка активации ветки {branch_id}: {e}")
            return False
    
    def get_branch_for_flower_document(self, org_id: str, supplier_name: str, document_text: str) -> Tuple[Optional[str], str]:
        """
        Определяет оптимальную ветку для цветочного документа.
        
        Args:
            org_id: ID организации
            supplier_name: Название поставщика
            document_text: Текст документа для анализа маркеров
        
        Returns:
            Tuple[branch_id или None, reason - причина выбора]
        """
        if org_id != '20082562863':  # PARKENTERTAINMENT
            return None, "Не PARKENTERTAINMENT организация"
        
        doc_text_lower = document_text.lower()
        supplier_lower = supplier_name.lower()
        
        # ДЕТАЛЬНОЕ логирование поиска маркеров
        logger.info(f"🔍 BRANCH DEBUG: supplier='{supplier_name}', hibispol={'hibispol' in supplier_lower}")
        logger.info(f"🔍 BRANCH DEBUG: ищем маркеры в тексте документа (первые 500 символов): {document_text[:500]}")
        
        wilenska_found = 'wileńska' in doc_text_lower
        praga_found = 'praga' in doc_text_lower
        logger.info(f"🔍 BRANCH DEBUG: маркер 'wileńska' найден = {wilenska_found}")
        logger.info(f"🔍 BRANCH DEBUG: маркер 'praga' найден = {praga_found}")
        
        # Логика выбора ветки по поставщику и маркерам
        if 'hibispol' in supplier_lower:
            if wilenska_found or praga_found:
                # ИСПРАВЛЕНИЕ: Ищем Wileńska ПЕРВОЙ, Head Office только в конце как fallback
                preferred_names = ["Wileńska"]
                reason = f"HIBISPOL + маркер {('Wileńska' if wilenska_found else '') + (' Praga' if praga_found else '').strip()}"
                logger.info(f"🌸 BRANCH: HIBISPOL с маркерами → ищем Wileńska первой")
            else:
                preferred_names = ["Iris flowers atelier"]
                reason = "HIBISPOL без специальных маркеров"
                logger.info(f"🌸 BRANCH: HIBISPOL без маркеров → Iris flowers atelier")
        elif 'browary' in doc_text_lower:
            preferred_names = ["Iris flowers atelier"]
            reason = "Маркер 'browary' в документе"
        else:
            preferred_names = ["Iris flowers atelier"]
            reason = "Цветочный документ по умолчанию"
        
        # Ищем активную ветку
        logger.info(f"🔍 BRANCH SEARCH: поиск среди {preferred_names}")
        branch = self.find_branch_by_names(org_id, preferred_names)
        
        if branch:
            logger.info(f"🌸 Выбрана ветка для цветочного документа: {branch.name} ({reason})")
            return branch.branch_id, reason
        else:
            logger.warning(f"⚠️ Не найдена активная ветка среди {preferred_names}, причина: {reason}")
            
            # FALLBACK: пробуем Iris flowers atelier, потом Head Office
            fallback_names = ["Iris flowers atelier", "Head Office"]
            logger.info(f"🔄 FALLBACK: пробуем {fallback_names}")
            fallback_branch = self.find_branch_by_names(org_id, fallback_names)
            
            if fallback_branch:
                return fallback_branch.branch_id, f"Fallback к {fallback_branch.name} (не найдено: {preferred_names})"
            else:
                return None, f"Критическая ошибка: нет активных веток"
    
    def clear_cache(self, org_id: str = None) -> None:
        """
        Очищает кэш веток.
        
        Args:
            org_id: ID организации (если None, очищает весь кэш)
        """
        if org_id:
            cache_path = self._get_cache_path(org_id)
            if os.path.exists(cache_path):
                os.remove(cache_path)
                logger.info(f"🗑️ Кэш веток очищен для org {org_id}")
        else:
            # Очищаем все файлы кэша веток
            for filename in os.listdir(self.cache_dir):
                if filename.startswith('branches_manager_'):
                    os.remove(os.path.join(self.cache_dir, filename))
            logger.info("🗑️ Весь кэш веток очищен")
