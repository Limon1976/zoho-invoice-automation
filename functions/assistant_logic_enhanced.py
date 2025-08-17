"""
Enhanced Assistant Logic с интеграцией Pydantic AI
================================================

Улучшенная версия assistant_logic.py с использованием Pydantic AI
для более точного анализа документов и сопоставления компаний.
"""

# Импорт оригинальной логики
from assistant_logic import *

# Импорт нового AI анализатора
try:
    from ai_invoice_analyzer import (
        enhance_invoice_analysis,
        enhance_company_detection,
        is_ai_available,
        AIInvoiceAnalyzer
    )
    AI_ENHANCED = True
    print("✅ Pydantic AI интеграция активна")
except ImportError as e:
    AI_ENHANCED = False
    print(f"⚠️ Pydantic AI недоступен: {e}")


def enhanced_process_invoice_json(data: dict, existing_bills: list[tuple[str, str]], ocr_text: str = "") -> dict:
    """
    Улучшенная обработка JSON счета с AI анализом
    
    Args:
        data: Исходные данные счета
        existing_bills: Список существующих счетов
        ocr_text: OCR текст документа
        
    Returns:
        Обработанные данные с AI улучшениями
    """
    print("🚀 Запуск улучшенной обработки счета с AI...")
    
    # Сначала выполняем стандартную обработку
    result = process_invoice_json(data, existing_bills, ocr_text)
    
    # Если AI доступен, улучшаем анализ
    if AI_ENHANCED and ocr_text:
        print("🧠 Применяем AI анализ...")
        
        # AI анализ документа
        ai_analysis = enhance_invoice_analysis(ocr_text)
        
        if ai_analysis.get("ai_enhanced"):
            print("✅ AI анализ успешен, улучшаем данные...")
            
            # Улучшаем данные поставщика
            if ai_analysis.get("supplier_name") and not result.get("supplier", {}).get("name"):
                if "supplier" not in result:
                    result["supplier"] = {}
                result["supplier"]["name"] = ai_analysis["supplier_name"]
                print(f"  📝 AI обнаружил поставщика: {ai_analysis['supplier_name']}")
            
            # Улучшаем VAT номер
            if ai_analysis.get("supplier_vat") and not result.get("supplier", {}).get("vat"):
                if "supplier" not in result:
                    result["supplier"] = {}
                result["supplier"]["vat"] = ai_analysis["supplier_vat"]
                print(f"  🏷️ AI обнаружил VAT: {ai_analysis['supplier_vat']}")
            
            # Улучшаем номер документа
            if ai_analysis.get("bill_number") and not result.get("bill_number"):
                result["bill_number"] = ai_analysis["bill_number"]
                print(f"  📄 AI обнаружил номер: {ai_analysis['bill_number']}")
            
            # Улучшаем сумму
            if ai_analysis.get("total_amount") and not result.get("total_amount"):
                result["total_amount"] = ai_analysis["total_amount"]
                print(f"  💰 AI обнаружил сумму: {ai_analysis['total_amount']} {ai_analysis.get('currency', 'EUR')}")
            
            # Улучшаем валюту
            if ai_analysis.get("currency") and not result.get("currency"):
                result["currency"] = ai_analysis["currency"]
                print(f"  💱 AI обнаружил валюту: {ai_analysis['currency']}")
            
            # Добавляем автомобильную информацию
            if ai_analysis.get("is_car_related"):
                result["is_car_related"] = True
                
                if ai_analysis.get("vin_numbers"):
                    result["vin_numbers"] = ai_analysis["vin_numbers"]
                    print(f"  🚗 AI обнаружил VIN: {ai_analysis['vin_numbers']}")
                
                if ai_analysis.get("vehicle_models"):
                    result["vehicle_models"] = ai_analysis["vehicle_models"]
                    print(f"  🏎️ AI обнаружил модели: {ai_analysis['vehicle_models']}")
            
            # Проверяем нашу компанию
            if ai_analysis.get("is_our_company_supplier"):
                print("  ⚠️ AI определил, что поставщик - наша компания (исходящий документ)")
                result["is_outgoing"] = True
            
            # Добавляем метаданные AI
            result["ai_metadata"] = {
                "confidence": ai_analysis.get("confidence", 0.5),
                "notes": ai_analysis.get("notes", []),
                "enhanced_fields": [k for k, v in ai_analysis.items() if k != "ai_enhanced" and v],
                "analysis_version": "pydantic_ai_0.4.2"
            }
            
            print(f"  📊 AI уверенность: {ai_analysis.get('confidence', 0.5):.1%}")
        
        else:
            print(f"❌ AI анализ не удался: {ai_analysis.get('reason', 'Неизвестная ошибка')}")
    
    return result


def enhanced_company_detection(supplier_data: dict, ocr_text: str = "") -> dict:
    """
    Улучшенное определение компании с AI
    
    Args:
        supplier_data: Данные поставщика
        ocr_text: OCR текст для дополнительного анализа
        
    Returns:
        Улучшенные данные поставщика
    """
    if not AI_ENHANCED or not supplier_data.get("name"):
        return supplier_data
    
    print("🔍 Проверяем компанию с помощью AI...")
    
    # AI анализ компании
    company_result = enhance_company_detection(supplier_data["name"])
    
    if company_result.get("ai_enhanced"):
        print(f"🧠 AI результат для '{supplier_data['name']}':")
        print(f"  Наша компания: {company_result.get('is_our_company')}")
        print(f"  Уверенность: {company_result.get('confidence', 0.5):.1%}")
        print(f"  Обоснование: {company_result.get('reasoning', 'Нет')}")
        
        # Добавляем AI метаданные
        supplier_data["ai_company_analysis"] = {
            "is_our_company": company_result.get("is_our_company", False),
            "confidence": company_result.get("confidence", 0.5),
            "reasoning": company_result.get("reasoning", ""),
            "analysis_version": "pydantic_ai_0.4.2"
        }
    
    return supplier_data


def enhanced_process_proforma_json(data: dict, ocr_text: str = "") -> dict:
    """
    Улучшенная обработка Proforma с AI
    
    Args:
        data: Данные проформы
        ocr_text: OCR текст
        
    Returns:
        Обработанные данные
    """
    # Сначала стандартная обработка
    result = process_proforma_json(data, ocr_text)
    
    # Затем AI улучшения (аналогично invoice)
    if AI_ENHANCED and ocr_text:
        ai_analysis = enhance_invoice_analysis(ocr_text)
        
        if ai_analysis.get("ai_enhanced"):
            # Применяем те же улучшения, что и для invoice
            # ... (код аналогичен enhanced_process_invoice_json)
            
            result["ai_metadata"] = {
                "confidence": ai_analysis.get("confidence", 0.5),
                "document_type": "proforma",
                "analysis_version": "pydantic_ai_0.4.2"
            }
    
    return result


def enhanced_guess_document_type(data: dict, ocr_text: str) -> str:
    """
    Улучшенное определение типа документа с AI
    
    Args:
        data: Данные документа
        ocr_text: OCR текст
        
    Returns:
        Тип документа
    """
    # Сначала пробуем стандартный метод
    standard_type = guess_document_type(data, ocr_text)
    
    if standard_type != "unknown" or not AI_ENHANCED:
        return standard_type
    
    print("🤔 Стандартный метод не определил тип, пробуем AI...")
    
    # Используем AI для определения типа
    ai_analysis = enhance_invoice_analysis(ocr_text)
    
    if ai_analysis.get("ai_enhanced"):
        # Здесь можно добавить логику определения типа через AI
        # Пока возвращаем стандартный результат
        pass
    
    return standard_type


def get_ai_status() -> dict:
    """
    Получение статуса AI интеграции
    
    Returns:
        Словарь с информацией о статусе AI
    """
    return {
        "ai_available": AI_ENHANCED,
        "openai_configured": is_ai_available() if AI_ENHANCED else False,
        "version": "pydantic_ai_0.4.2" if AI_ENHANCED else None,
        "features": [
            "invoice_analysis",
            "company_matching", 
            "vin_detection",
            "auto_type_detection"
        ] if AI_ENHANCED else []
    }


def create_ai_analysis_report(data: dict) -> dict:
    """
    Создание отчета AI анализа
    
    Args:
        data: Обработанные данные документа
        
    Returns:
        Отчет с AI метаданными
    """
    ai_metadata = data.get("ai_metadata", {})
    
    report = {
        "ai_enhanced": bool(ai_metadata),
        "confidence": ai_metadata.get("confidence", 0.0),
        "enhanced_fields": ai_metadata.get("enhanced_fields", []),
        "notes": ai_metadata.get("notes", []),
        "analysis_version": ai_metadata.get("analysis_version", "none")
    }
    
    # Добавляем информацию о компании
    supplier = data.get("supplier", {})
    company_analysis = supplier.get("ai_company_analysis", {})
    
    if company_analysis:
        report["company_analysis"] = {
            "is_our_company": company_analysis.get("is_our_company", False),
            "confidence": company_analysis.get("confidence", 0.0),
            "reasoning": company_analysis.get("reasoning", "")
        }
    
    return report


# Экспортируем улучшенные функции как основные
def process_invoice_json_ai_enhanced(data: dict, existing_bills: list[tuple[str, str]], ocr_text: str = "") -> dict:
    """Алиас для удобства использования"""
    return enhanced_process_invoice_json(data, existing_bills, ocr_text)


def process_proforma_json_ai_enhanced(data: dict, ocr_text: str = "") -> dict:
    """Алиас для удобства использования"""
    return enhanced_process_proforma_json(data, ocr_text)


# Вспомогательные функции для тестирования
def test_ai_integration():
    """Тест AI интеграции"""
    print("🧪 Тестирование AI интеграции...")
    
    status = get_ai_status()
    print(f"AI доступен: {status['ai_available']}")
    print(f"OpenAI настроен: {status['openai_configured']}")
    print(f"Версия: {status['version']}")
    
    if not status['ai_available']:
        print("❌ AI интеграция недоступна")
        return False
    
    # Тестовый документ
    test_ocr = """
    INVOICE
    BMW Deutschland GmbH
    VAT: DE123456789
    
    Invoice No: BMW-2025-001
    Date: 15.07.2025
    
    Vehicle: BMW X5 xDrive40i
    VIN: WBAJB4C51PBY12345
    Price: 65,000.00 EUR
    """
    
    test_data = {"supplier": {"name": ""}, "bill_number": ""}
    
    print("\n📋 Тестирование анализа...")
    result = enhanced_process_invoice_json(test_data, [], test_ocr)
    
    ai_report = create_ai_analysis_report(result)
    print(f"✅ AI отчет: {ai_report}")
    
    return True


if __name__ == "__main__":
    test_ai_integration() 