"""
Унифицированный менеджер для работы со счетами Zoho Books.
Выделен из handlers.py для переиспользования в BILL и Expense creation.
"""

import logging
from typing import Optional, List, Dict, Tuple
from functions.export_zoho_accounts import get_accounts_cached_or_fetch
from functions.llm_document_extractor import llm_select_account

logger = logging.getLogger(__name__)


class AccountManager:
    """Унифицированная работа со счетами Zoho"""
    
    @staticmethod
    def get_expense_account(
        org_id: str, 
        org_name: str,
        context_text: str = "",
        supplier_name: str = "",
        category: str = ""
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Получить expense account используя LLM и fallback логику.
        
        Returns:
            Tuple[account_id, account_name] или (None, None) если не найдено
        """
        try:
            # Загружаем все счета
            accounts = get_accounts_cached_or_fetch(org_id, org_name)
            if not accounts:
                logger.error(f"❌ Не удалось загрузить счета для {org_name}")
                return None, None
            
            # ПРИОРИТЕТ 1: Цветочные accounts для PARKENTERTAINMENT
            expense_account_id = None
            expense_account_name = None
            
            # Проверяем цветочную логику для PARKENTERTAINMENT
            if org_id == '20082562863' and org_name == 'PARKENTERTAINMENT':
                flower_account = AccountManager._detect_flower_expense_account(
                    context_text, supplier_name, category, accounts
                )
                if flower_account:
                    expense_account_id, expense_account_name = flower_account
                    logger.info(f"🌸 ЦВЕТОЧНЫЙ account выбран: {expense_account_name} (ID: {expense_account_id})")
            
            # ПРИОРИТЕТ 2: LLM если цветочный не найден
            if not expense_account_id:
                acc_names = [a.get('account_name') for a in accounts if a.get('account_name')]
                
                try:
                    llm_pick = llm_select_account(acc_names, context_text, supplier_name, category)
                    if llm_pick and llm_pick.get('name') in acc_names:
                        for acc in accounts:
                            if acc.get('account_name') == llm_pick['name']:
                                expense_account_id = acc.get('account_id')
                                expense_account_name = acc.get('account_name')
                                logger.info(f"📊 LLM выбрал expense account: {expense_account_name} (ID: {expense_account_id})")
                                break
                except Exception as e:
                    logger.warning(f"⚠️ LLM выбор account не сработал: {e}")
            
            # Fallback к первому expense account
            if not expense_account_id:
                for acc in accounts:
                    acc_type = (acc.get('account_type') or '').lower()
                    if acc_type == 'expense':
                        expense_account_id = acc.get('account_id')
                        expense_account_name = acc.get('account_name')
                        logger.info(f"📊 Fallback expense account: {expense_account_name} (ID: {expense_account_id})")
                        break
            
            return expense_account_id, expense_account_name
            
        except Exception as e:
            logger.error(f"❌ Ошибка в get_expense_account: {e}")
            return None, None
    
    @staticmethod
    def get_paid_through_account(
        org_id: str,
        org_name: str, 
        payment_type: str = "business"
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Получить счет для оплаты (банк, касса, карта).
        
        Args:
            payment_type: "business" или "personal"
            
        Returns:
            Tuple[account_id, account_name] или (None, None) если не найдено
        """
        try:
            # Загружаем все счета
            accounts = get_accounts_cached_or_fetch(org_id, org_name)
            if not accounts:
                logger.error(f"❌ Не удалось загрузить счета для {org_name}")
                return None, None
            
            paid_through_account_id = None
            paid_through_account_name = None
            
            # Поиск по ключевым словам И типу счета
            for acc in accounts:
                acc_name = (acc.get('account_name') or '').lower()
                acc_type = (acc.get('account_type') or '').lower()
                
                # Проверяем что это валидный тип счета для paid_through (bank, cash, credit_card)
                if acc_type not in ['bank', 'cash', 'credit_card']:
                    continue
                
                if payment_type == "business":
                    # Приоритет для польского бизнес-счета
                    if 'konto firmowe' in acc_name:
                        paid_through_account_id = acc.get('account_id')
                        paid_through_account_name = acc.get('account_name')
                        logger.info(f"💳 Найден польский бизнес счет: {paid_through_account_name} (ID: {paid_through_account_id}, type: {acc_type})")
                        break
                    # Fallback к другим бизнес счетам
                    elif any(keyword in acc_name for keyword in ['wise', 'business', 'company', 'checking', 'pko']):
                        paid_through_account_id = acc.get('account_id')
                        paid_through_account_name = acc.get('account_name')
                        logger.info(f"💳 Найден бизнес счет: {paid_through_account_name} (ID: {paid_through_account_id}, type: {acc_type})")
                        # Продолжаем поиск, может найдем Konto Firmowe
                else:  # personal
                    # Ищем личные счета
                    if any(keyword in acc_name for keyword in ['petty cash', 'cash', 'personal', 'owner']):
                        paid_through_account_id = acc.get('account_id')
                        paid_through_account_name = acc.get('account_name')
                        logger.info(f"💰 Найден личный счет: {paid_through_account_name} (ID: {paid_through_account_id}, type: {acc_type})")
                        break
            
            # Fallback к первому банковскому счету
            if not paid_through_account_id:
                for acc in accounts:
                    acc_type = (acc.get('account_type') or '').lower()
                    if acc_type in ['bank', 'cash', 'credit_card']:
                        paid_through_account_id = acc.get('account_id')
                        paid_through_account_name = acc.get('account_name')
                        logger.info(f"💳 Fallback счет: {paid_through_account_name} (ID: {paid_through_account_id})")
                        break
            
            return paid_through_account_id, paid_through_account_name
            
        except Exception as e:
            logger.error(f"❌ Ошибка в get_paid_through_account: {e}")
            return None, None
    
    @staticmethod
    def _detect_flower_expense_account(
        context_text: str, 
        supplier_name: str, 
        category: str, 
        accounts: List[Dict]
    ) -> Optional[Tuple[str, str]]:
        """
        Определяет цветочный expense account по ключевым словам
        
        Returns:
            Tuple[account_id, account_name] или None
        """
        
        # Все тексты в нижний регистр для поиска
        text_lower = (context_text or '').lower()
        supplier_lower = (supplier_name or '').lower()
        category_lower = (category or '').lower()
        
        # Цветочные keywords и соответствующие accounts
        flower_mapping = {
            'flowers': ['цветы', 'flowers', 'flower', 'kwiat', 'kwiaty', 'róża', 'roza', 'tulip', 'bukiet'],
            'boxes': ['коробки', 'коробка', 'pudełko', 'pudełka', 'box', 'boxes', 'opakowanie', 'packaging'],
            'paper, ribons': ['ленточки', 'ленточка', 'лента', 'ribbon', 'ribons', 'wstążka', 'wstążki', 'paper', 'papier'],
            'vases': ['ваза', 'вазы', 'vase', 'vases', 'wazon', 'wazony'],
            'balloons': ['шарики', 'шарик', 'balloon', 'balloons', 'balon', 'balony']
        }
        
        # Поиск по keywords
        for account_name, keywords in flower_mapping.items():
            for keyword in keywords:
                if (keyword in text_lower or 
                    keyword in supplier_lower):
                    
                    # Ищем соответствующий account в списке
                    for acc in accounts:
                        acc_name = (acc.get('account_name') or '').lower()
                        if account_name.lower() in acc_name:
                            logger.info(f"🌸 Найден цветочный account по keyword '{keyword}': {acc.get('account_name')}")
                            return acc.get('account_id'), acc.get('account_name')
        
        # Специальная логика для поставщиков
        flower_suppliers = ['hibispol', 'rožany', 'rozany']
        for supplier_keyword in flower_suppliers:
            if supplier_keyword in supplier_lower:
                # Для цветочных поставщиков используем основной "Flowers" account
                for acc in accounts:
                    acc_name = (acc.get('account_name') or '').lower()
                    if 'flowers' in acc_name and 'expenses' not in acc_name:  # Избегаем "Expenses IRIS"
                        logger.info(f"🌸 Найден цветочный account для поставщика '{supplier_name}': {acc.get('account_name')}")
                        return acc.get('account_id'), acc.get('account_name')
        
        # Если категория FLOWERS
        if 'flower' in category_lower:
            for acc in accounts:
                acc_name = (acc.get('account_name') or '').lower()
                if 'flowers' in acc_name and 'expenses' not in acc_name:
                    logger.info(f"🌸 Найден цветочный account по категории: {acc.get('account_name')}")
                    return acc.get('account_id'), acc.get('account_name')
        
        return None
    
    @staticmethod
    def get_accounts_for_selection(
        org_id: str, 
        org_name: str,
        account_types: List[str] = None
    ) -> List[Dict[str, str]]:
        """
        Получить список счетов для выбора пользователем.
        
        Args:
            account_types: Фильтр по типам счетов ['expense', 'cost of goods sold']
            
        Returns:
            List[{account_id, account_name, account_type}]
        """
        try:
            accounts = get_accounts_cached_or_fetch(org_id, org_name)
            if not accounts:
                return []
            
            # Фильтруем по типам если указаны
            if account_types:
                filtered = []
                for acc in accounts:
                    acc_type = (acc.get('account_type') or '').lower()
                    if acc_type in [t.lower() for t in account_types]:
                        filtered.append({
                            'account_id': acc.get('account_id'),
                            'account_name': acc.get('account_name'),
                            'account_type': acc.get('account_type')
                        })
                return filtered
            
            # Возвращаем все счета
            return [{
                'account_id': acc.get('account_id'),
                'account_name': acc.get('account_name'), 
                'account_type': acc.get('account_type')
            } for acc in accounts]
            
        except Exception as e:
            logger.error(f"❌ Ошибка в get_accounts_for_selection: {e}")
            return []
