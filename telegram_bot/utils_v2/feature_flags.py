"""
Feature Flags для безопасного перехода на новую архитектуру
"""

# Переключатели функций - начинаем с False для безопасности
FEATURES = {
    # Handlers v2
    'use_new_document_handler': False,  # Новый обработчик документов
    'use_new_expense_handler': False,   # Новый обработчик Expense
    'use_new_bill_handler': False,      # Новый обработчик Bills
    'use_new_contact_handler': False,   # Новый обработчик контактов
    'use_new_callback_router': False,   # Новый роутер callbacks
    
    # Services v2
    'use_expense_service': True,        # ExpenseService уже работает ✅
    'use_workdrive_service': False,     # WorkDrive сервис
    'use_jpeg_processing': False,       # Обработка JPEG файлов
    
    # Integrations
    'use_branch_manager': True,         # Branch Manager уже работает ✅
    'use_account_manager': True,        # Account Manager уже работает ✅
    'use_attachment_manager': True,     # Attachment Manager уже работает ✅
}

def is_enabled(feature: str) -> bool:
    """Проверяет включена ли функция"""
    return FEATURES.get(feature, False)

def enable_feature(feature: str):
    """Включает функцию (для тестирования)"""
    if feature in FEATURES:
        FEATURES[feature] = True
        print(f"✅ Функция включена: {feature}")
    else:
        print(f"❌ Неизвестная функция: {feature}")

def disable_feature(feature: str):
    """Отключает функцию (для отката)"""
    if feature in FEATURES:
        FEATURES[feature] = False
        print(f"❌ Функция отключена: {feature}")
    else:
        print(f"❌ Неизвестная функция: {feature}")

def get_enabled_features() -> list:
    """Возвращает список включенных функций"""
    return [feature for feature, enabled in FEATURES.items() if enabled]
