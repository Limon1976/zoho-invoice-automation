#!/usr/bin/env python3
"""
Enhanced AI Invoice Analyzer with Pydantic AI
==============================================

Улучшенный AI анализатор счетов с использованием Pydantic AI
"""

import os
from typing import Optional, List, Dict, Any
from decimal import Decimal
from pydantic import BaseModel, Field

# Импорты Pydantic AI
try:
    from pydantic_ai import Agent
    PYDANTIC_AI_AVAILABLE = True
except ImportError:
    PYDANTIC_AI_AVAILABLE = False

# Address parsing теперь интегрирован в этот файл
# from agent_invoice_parser import extract_text_from_pdf  # Не нужен здесь


class ZohoAddress(BaseModel):
    """Адрес для Zoho Books с точными названиями полей"""
    country: str = Field(..., description="Country/Region - выпадающее поле в Zoho (DE, PL, EE, etc)")
    address: str = Field(..., description="Address - улица с номером дома или здание с квартирой")
    city: str = Field(..., description="City - город")
    zip_code: Optional[str] = Field(None, description="ZIP Code - почтовый индекс")
    phone: Optional[str] = Field(None, description="Phone - телефон поставщика")
    state: Optional[str] = Field(None, description="State/Province - регион (опционально)")
    
    class Config:
        """Дополнительная конфигурация"""
        schema_extra = {
            "example": {
                "country": "DE",
                "address": "Stuttgarter Strasse 116",
                "city": "Böblingen", 
                "zip_code": "71032",
                "phone": "+49 (0)7031-234178",
                "state": None
            }
        }


class ZohoItem(BaseModel):
    """Item для Zoho"""
    name: str = Field(..., description="Название товара")
    description: str = Field(..., description="Описание")
    unit_price: Decimal = Field(..., description="Цена за единицу")
    quantity: int = Field(1, description="Количество")


class CarDetails(BaseModel):
    """Детали автомобиля для Zoho"""
    brand: str = Field(..., description="Бренд (BMW, Mercedes, etc.)")
    model: str = Field(..., description="Модель (V 300 d, X6, etc.)")
    engine: str = Field(..., description="Двигатель (5.1 L, etc.)")
    vin: str = Field(..., description="VIN номер")


class EnhancedInvoiceAnalysisResult(BaseModel):
    """Улучшенный результат AI анализа счета"""
    # Основная информация
    supplier_name: str = Field(..., description="Название поставщика")
    supplier_vat: Optional[str] = Field(None, description="VAT номер поставщика")
    
    # Адреса для Zoho
    supplier_address: Optional[ZohoAddress] = Field(None, description="Адрес поставщика для Zoho")
    billing_address: Optional[ZohoAddress] = Field(None, description="Адрес для выставления счетов")
    shipping_address: Optional[ZohoAddress] = Field(None, description="Адрес доставки")
    
    # Номер и дата документа
    bill_number: Optional[str] = Field(None, description="Номер документа")
    document_date: Optional[str] = Field(None, description="Дата документа")
    
    # Финансовая информация
    total_amount: Decimal = Field(..., description="Общая сумма")
    currency: str = Field("EUR", description="Валюта")
    
    # Наша компания
    our_company_name: Optional[str] = Field(None, description="Название нашей компании")
    is_our_company_supplier: bool = Field(False, description="Поставщик - это наша компания")
    
    # Автомобильная информация
    is_car_related: bool = Field(False, description="Связан ли счет с автомобилями")
    car_details: Optional[CarDetails] = Field(None, description="Детали автомобиля")
    
    # Items для Zoho
    items: List[ZohoItem] = Field(default_factory=list, description="Товары для Zoho")
    
    # Метаданные
    confidence_score: float = Field(0.5, ge=0.0, le=1.0, description="Уверенность анализа")
    processing_notes: List[str] = Field(default_factory=list, description="Заметки")


class EnhancedAIAnalysisContext(BaseModel):
    """Контекст для улучшенного AI анализа"""
    our_companies: List[str] = Field(
        default=["TaVie Europe OÜ", "Parkentertainment Sp. z o.o."],
        description="Наши компании"
    )
    car_brands: List[str] = Field(
        default=["BMW", "Mercedes", "Audi", "Porsche", "Ferrari", "Lamborghini"],
        description="Автомобильные бренды"
    )
    zoho_countries: List[str] = Field(
        default=["DE", "EE", "PL", "SE", "NO", "DK", "FI", "NL", "BE", "FR", "IT", "ES"],
        description="Страны доступные в Zoho"
    )


class EnhancedAIInvoiceAnalyzer:
    """Улучшенный AI анализатор счетов"""
    
    def __init__(self):
        self.available = PYDANTIC_AI_AVAILABLE
        
        if self.available:
            try:
                # Агент для улучшенного анализа счетов
                self.enhanced_agent = Agent(
                    'openai:gpt-4o-mini',
                    output_type=EnhancedInvoiceAnalysisResult,
                    system_prompt=self._get_enhanced_prompt(),
                    retries=2
                )
            except Exception as e:
                print(f"⚠️ Ошибка инициализации Enhanced AI анализатора: {e}")
                self.available = False
    
    def _get_enhanced_prompt(self) -> str:
        """Промпт для улучшенного анализа счетов"""
        return """
        Ты - эксперт по анализу счетов для системы Zoho Books.
        
        ТВОЯ ЗАДАЧА:
        Проанализировать текст документа и извлечь структурированную информацию для Zoho.
        
        ОСОБОЕ ВНИМАНИЕ:
        1. Адреса должны быть разбиты на компоненты (country, city, state, zip_code, address_line1, address_line2)
        2. Для автомобилей создавай car_details с brand, model, engine, vin
        3. Определяй нашу компанию (TaVie Europe OÜ, Parkentertainment Sp. z o.o.)
        4. Валюту определяй точно (EUR, USD, PLN, etc.)
        5. Уверенность (confidence_score) от 0.0 до 1.0
        
        ПРИМЕРЫ АДРЕСОВ:
        "Stuttgarter Strasse 116, DE 71032 Böblingen" ->
        country: DE, city: Böblingen, zip_code: 71032, address_line1: Stuttgarter Strasse 116
        
        ПРИМЕРЫ АВТОМОБИЛЕЙ:
        "BMW X6 M50d" -> brand: BMW, model: X6, engine: M50d, vin: (если есть)
        """
    
    async def analyze_enhanced(self, text: str) -> Optional[EnhancedInvoiceAnalysisResult]:
        """Анализирует текст с помощью Enhanced AI"""
        if not self.available:
            return None
        
        if not os.getenv('OPENAI_API_KEY'):
            return None
        
        try:
            # Создаем контекст
            context = EnhancedAIAnalysisContext()
            
            # Запускаем анализ
            result = await self.enhanced_agent.run(text)
            return result.output
        except Exception as e:
            print(f"❌ Ошибка Enhanced AI анализа: {e}")
            return None


# Главная функция для улучшенного анализа
async def enhance_invoice_analysis_enhanced_async(text: str) -> dict:
    """
    Улучшенный AI анализ счета (асинхронная версия)
    
    Args:
        text: Текст документа
        
    Returns:
        Словарь с результатами анализа
    """
    analyzer = EnhancedAIInvoiceAnalyzer()
    
    if not analyzer.available:
        return {
            "ai_enhanced": False,
            "reason": "Enhanced AI анализатор недоступен"
        }
    
    if not os.getenv('OPENAI_API_KEY'):
        return {
            "ai_enhanced": False,
            "reason": "OPENAI_API_KEY не установлен"
        }
    
    try:
        result = await analyzer.analyze_enhanced(text)
        
        if result:
            # Обрабатываем результат
            return await process_enhanced_analysis_result(result)
        else:
            return {
                "ai_enhanced": False,
                "reason": "Enhanced AI анализ не удался"
            }
            
    except Exception as e:
        return {
            "ai_enhanced": False,
            "reason": f"Ошибка Enhanced AI анализа: {e}"
        }


# Синхронная обертка
def enhance_invoice_analysis_enhanced(text: str) -> dict:
    """
    Улучшенный AI анализ счета (синхронная версия)
    
    Args:
        text: Текст документа
        
    Returns:
        Словарь с результатами анализа
    """
    import asyncio
    # Просто возвращаем результат без asyncio.run
    return asyncio.run(enhance_invoice_analysis_enhanced_async(text))


# Функции для интеграции
async def process_enhanced_analysis_result(result: EnhancedInvoiceAnalysisResult) -> dict:
    """
    Обрабатывает результат AI анализа с дополнительной обработкой для Zoho
    
    Args:
        result: Результат AI анализа
        
    Returns:
        Словарь с обработанными данными для Zoho
    """
    if result:
        # Обрабатываем car_model и car_item_name
        car_model_zoho = ""
        car_item_name = ""
        item_details_clean = ""
        
        if result.car_details:
            # Создаем car_model для Zoho (бренд + модель + двигатель)
            brand = result.car_details.brand
            model = result.car_details.model
            engine = result.car_details.engine
            car_model_zoho = f"{brand} {model} {engine}".strip()
            
            # Создаем car_item_name (car_model + последние 5 цифр VIN)
            vin = result.car_details.vin
            vin_suffix = vin[-5:] if len(vin) >= 5 else vin
            car_item_name = f"{car_model_zoho}_{vin_suffix}"
            
            # Очищаем item_details от полной модели авто
            item_details_clean = f"VIN: {vin}, Engine: {engine}"
        
        # Парсим адрес поставщика с помощью AI
        supplier_address_parsed = None
        if result.supplier_address:
            address_text = f"{result.supplier_address.address}"
            if result.supplier_address.zip_code:
                address_text += f", {result.supplier_address.zip_code}"
            if result.supplier_address.city:
                address_text += f", {result.supplier_address.city}"
            if result.supplier_address.country:
                address_text += f", {result.supplier_address.country}"
            
            parsed_address = await parse_address_with_ai(address_text)
            if parsed_address.get("parsed"):
                supplier_address_parsed = parsed_address
        
        return {
            "ai_enhanced": True,
            "supplier_name": result.supplier_name,
            "supplier_vat": result.supplier_vat,
            "supplier_address": result.supplier_address.dict() if result.supplier_address else None,
            "supplier_address_parsed": supplier_address_parsed,
            "billing_address": result.billing_address.dict() if result.billing_address else None,
            "shipping_address": result.shipping_address.dict() if result.shipping_address else None,
            "bill_number": result.bill_number,
            "total_amount": float(result.total_amount),
            "currency": result.currency,
            "is_car_related": result.is_car_related,
            "car_details": result.car_details.dict() if result.car_details else None,
            "car_model": car_model_zoho,
            "car_item_name": car_item_name,
            "item_details": item_details_clean,
            "items": [item.dict() for item in result.items],
            "our_company_name": result.our_company_name,
            "is_our_company_supplier": result.is_our_company_supplier,
            "confidence": result.confidence_score,
            "notes": result.processing_notes
        }
    
    return {
        "ai_enhanced": False,
        "reason": "Результат анализа пустой"
    }


# Тестовая функция
async def test_enhanced_analyzer():
    """Тест улучшенного AI анализатора"""
    print("🧪 Тест улучшенного AI анализатора")
    print(f"Pydantic AI доступен: {PYDANTIC_AI_AVAILABLE}")
    print(f"OpenAI API ключ: {'✅' if os.getenv('OPENAI_API_KEY') else '❌'}")
    
    if not PYDANTIC_AI_AVAILABLE or not os.getenv('OPENAI_API_KEY'):
        print("❌ Улучшенный AI анализ недоступен")
        return
    
    sample_text = """
    Contract
    Supplier: Horrer Automobile GmbH
    Address: Stuttgarter Strasse 116, DE 71032 Böblingen
    Email: info@horrer-automobile.de
    Phone: +49 (0)7031-234178
    
    Item: MERCEDES-BENZ V 300 d LANG AVANTGARDE EDITION 4M AIRMAT AMG
    VIN: W1V44781313926375
    Engine: 5.1 L
    Amount: 55,369.75 EUR
    """
    
    print("\n📄 Тестирование улучшенного анализа...")
    result = await enhance_invoice_analysis_enhanced_async(sample_text)
    
    if result.get("ai_enhanced"):
        print("✅ Улучшенный AI анализ успешен:")
        print(f"  🏢 Поставщик: {result.get('supplier_name')}")
        print(f"  🏠 Адрес: {result.get('supplier_address')}")
        print(f"  🚗 Автомобильная тематика: {result.get('is_car_related')}")
        print(f"  📦 Items: {result.get('items')}")
        print(f"  🎯 Уверенность: {result.get('confidence', 0):.1%}")
    else:
        print(f"❌ Улучшенный AI анализ не удался: {result.get('reason')}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_enhanced_analyzer()) 

# Простой парсер адресов с помощью AI
async def parse_address_with_ai(address_text: str) -> dict:
    """
    Парсит адрес с помощью AI для Zoho
    
    Args:
        address_text: Текст адреса
        
    Returns:
        Словарь с компонентами адреса
    """
    if not PYDANTIC_AI_AVAILABLE or not os.getenv('OPENAI_API_KEY'):
        return {"parsed": False, "reason": "AI недоступен"}
    
    try:
        from pydantic_ai import Agent
        
        # Простая схема для адреса
        class SimpleAddress(BaseModel):
            country: str = Field(..., description="Страна")
            city: str = Field(..., description="Город")
            zip_code: Optional[str] = Field(None, description="Индекс")
            address_line1: str = Field(..., description="Адрес")
        
        agent = Agent(
            'openai:gpt-4o-mini',
            output_type=SimpleAddress,
            system_prompt="Разбери адрес на компоненты: улица, город, индекс, адресная строка"
        )
        
        result = await agent.run(address_text)
        address = result.output
        
        return {
            "parsed": True,
            "country": address.country,
            "city": address.city,
            "zip_code": address.zip_code,
            "address_line1": address.address_line1
        }
        
    except Exception as e:
        return {"parsed": False, "reason": f"Ошибка: {e}"} 

# Улучшенная схема для автомобильных документов
class CarDocumentAnalysisResult(BaseModel):
    """Результат анализа автомобильного документа"""
    
    # Основная информация о документе
    document_type: str = Field(description="Тип документа: invoice, contract, receipt")
    bill_number: Optional[str] = Field(None, description="Номер счета/договора")
    document_date: Optional[str] = Field(None, description="Дата документа в формате DD/MM/YYYY")
    due_date: Optional[str] = Field(None, description="Дата платежа")
    
    # Поставщик с разделенным адресом
    supplier_name: str = Field(description="Название поставщика")
    supplier_vat: Optional[str] = Field(None, description="VAT номер поставщика")
    supplier_email: Optional[str] = Field(None, description="Email поставщика")
    supplier_phone: Optional[str] = Field(None, description="Телефон поставщика")
    
    # Банковские реквизиты поставщика
    bank_name: Optional[str] = Field(None, description="Название банка")
    bank_account: Optional[str] = Field(None, description="Номер счета")
    iban: Optional[str] = Field(None, description="IBAN")
    swift_bic: Optional[str] = Field(None, description="SWIFT/BIC код")
    
    # Детальный адрес поставщика  
    supplier_street: Optional[str] = Field(None, description="Улица")
    supplier_city: Optional[str] = Field(None, description="Город") 
    supplier_zip_code: Optional[str] = Field(None, description="Почтовый индекс")
    supplier_country: Optional[str] = Field(None, description="Страна")
    
    # Финансовая информация
    total_amount: float = Field(description="Общая сумма")
    currency: str = Field(default="EUR", description="Валюта")
    date: Optional[str] = Field(None, description="Дата документа")
    
    # Автомобильная информация
    vin: Optional[str] = Field(None, description="VIN номер автомобиля (17 символов, начинается с W)")
    car_brand: Optional[str] = Field(None, description="Марка автомобиля: Mercedes-Benz, BMW, Audi, etc")
    car_model: Optional[str] = Field(None, description="ОСНОВНАЯ модель автомобиля без марки (только базовая модель, например: XC90, X7, S65 AMG)")
    car_full_name: Optional[str] = Field(None, description="Полное название автомобиля")
    engine_info: Optional[str] = Field(None, description="Информация о двигателе")
    item_details: Optional[str] = Field(None, description="Подробное описание товара/услуги из документа")
    
    # Дополнительная информация
    payment_terms: Optional[str] = Field(None, description="Условия оплаты")
    payment_method: Optional[str] = Field(None, description="Метод оплаты: Wire Transfer, Bank Transfer, etc")
    contract_type: Optional[str] = Field(None, description="Тип контракта: purchase, lease, service")
    
    # Наша компания
    our_company_name: Optional[str] = Field(None, description="Название нашей компании")
    our_company_vat: Optional[str] = Field(None, description="VAT нашей компании")
    
    def generate_car_item_name(self) -> str:
        """Генерирует название item для автомобиля в формате: Бренд + буквенное обозначение + цифра двигателя + последние 5 VIN"""
        if not self.vin:
            return "Unknown_Car"
        
        # Берем последние 5 символов VIN
        vin_suffix = self.vin[-5:] if len(self.vin) >= 5 else self.vin
        
        if self.car_brand and self.car_model:
            # Упрощаем название автомобиля для item
            brand = self.car_brand.replace("-", " ").replace("Mercedes-Benz", "Mercedes Benz")
            
            # ПРОСТАЯ ЛОГИКА: берем только первую часть до запятой
            if "," in self.car_model:
                # Разбиваем по запятой и берем только первую часть
                first_part = self.car_model.split(",")[0].strip()
                # Разбиваем на слова и берем первые 2 слова
                words = first_part.split()
                if len(words) >= 2:
                    # Берем "M440i xDrive" → "M440i"
                    clean_model = words[0] + words[1] if len(words) >= 2 else words[0]
                    # Убираем xDrive, sDrive
                    clean_model = clean_model.replace("xDrive", "").replace("sDrive", "")
                else:
                    clean_model = words[0] if words else "Unknown"
            else:
                # Если нет запятой, берем первые 2 слова
                words = self.car_model.split()
                if len(words) >= 2:
                    clean_model = words[0] + words[1]
                    clean_model = clean_model.replace("xDrive", "").replace("sDrive", "")
                else:
                    clean_model = words[0] if words else "Unknown"
            
            return f"{brand} {clean_model}__{vin_suffix}"
        elif self.car_full_name:
            # Если есть полное название, упрощаем его
            brand_model = self.car_full_name.split()[0:3]  # Берем первые 3 слова
            clean_name = " ".join(brand_model).replace("-", " ")
            return f"{clean_name}__{vin_suffix}"
        else:
            return f"Car__{vin_suffix}"

# Улучшенная функция анализа для автомобильных документов
async def enhanced_car_document_analysis(text: str) -> Dict[str, Any]:
    """
    Улучшенный AI анализ автомобильных документов
    
    Args:
        text: Текст документа
        
    Returns:
        Детальный анализ с правильно разобранными данными
    """
    if not PYDANTIC_AI_AVAILABLE:
        return {"ai_enhanced": False, "reason": "Pydantic AI недоступен"}
    
    if not os.getenv('OPENAI_API_KEY'):
        return {"ai_enhanced": False, "reason": "OpenAI API ключ не найден"}
    
    try:
        from pydantic_ai import Agent
        
        # Создаем агента для анализа автомобильных документов
        agent = Agent(
            'openai:gpt-4o',
            output_type=CarDocumentAnalysisResult,
            system_prompt=(
                f"""
                Ты - эксперт по анализу автомобильных документов для системы Zoho Books.
                
                АНАЛИЗИРУЙ ЭТОТ ТЕКСТ КАК АВТОМОБИЛЬНЫЙ ДОКУМЕНТ:
                
                КРИТИЧЕСКИ ВАЖНО - ТОЧНОСТЬ ПОЛЕЙ:
                
                1. НОМЕР ДОКУМЕНТА И ДАТА:
                   - Ищи номер документа: "Invoice No.", "Pro-forma No.", "Rechnung Nr.", номер счета
                   - Дата документа: "Date:", "Datum:", "PRO-FORMA DATE:", в формате DD/MM/YYYY
                   - Дата платежа: "Due Date:", "Fälligkeitsdatum:", "DUE DATE:"
                
                2. БАНКОВСКИЕ РЕКВИЗИТЫ поставщика:
                   - Название банка: "BANK:", "Bank:", "Банк:"
                   - Номер счета: "BANK ACCOUNT NO.:", "Account:", "Konto:"
                   - IBAN: "IBAN:" (международный номер счета)
                   - SWIFT/BIC: "SWIFT:", "BIC:", "SWIFT/BIC:"
                   
                3. КОНТАКТНАЯ ИНФОРМАЦИЯ поставщика:
                   - Email: ищи "Email:", "E-mail:", "Mail:", "@" символ
                   - ВАЖНО: Email может быть в секции "Inhaber" или "Kontakt"
                   - ВАЖНО: Ищи в секции "Inhaber" где есть "Jochen Schmitt" и "Schmittomobile"
                   - ВАЖНО: Email может быть на отдельной строке после "E-Mail:"
                   - Примеры: "Schmittomobile@mobile.de", "info@company.com"
                   - Телефон: ищи "Phone:", "Tel:", "Telefon:", номера телефонов
                   - ВАЖНО: В документе есть "E-Mail: Schmittomobile@mobile.de" - найди это!
                
                4. VAT НОМЕР ПОСТАВЩИКА - КРИТИЧЕСКИ ВАЖНО:
                   - СЕКЦИЯ ПОСТАВЩИКА: "Autohaus Prokop GmbH + Luckenwalder Berg 5 - 14913 Jüterbog + Tel.: 03372417256"
                   - В ЭТОЙ СЕКЦИИ НЕТ VAT НОМЕРА!
                   - ПОЭТОМУ supplier_vat: null
                   
                   СЕКЦИЯ ПОКУПАТЕЛЯ (ИГНОРИРОВАТЬ ДЛЯ VAT ПОСТАВЩИКА):
                   - "Bei obengenannter Firma bestellt der Käufer: TaVie Europe OÜ"
                   - "VAT: EE102288270" - ЭТО VAT ПОКУПАТЕЛЯ, НЕ ПОСТАВЩИКА!
                   
                   ПРАВИЛО: Если в секции поставщика НЕТ VAT - supplier_vat: null
                   
                5. АДРЕС - разбивай точно на компоненты:
                   "Petőfi Sándor út 118. 0314/16 HRSZ, 6200 Kiskőrös, Hungary" →
                   supplier_street: "Petőfi Sándor út 118. 0314/16 HRSZ"
                   supplier_zip_code: "6200"  
                   supplier_city: "Kiskőrös"
                   supplier_country: "Hungary"
                   
                   "Luckenwalder Berg 5 - 14913 Jüterbog" →
                   supplier_street: "Luckenwalder Berg 5"
                   supplier_zip_code: "14913"
                   supplier_city: "Jüterbog"
                   supplier_country: "Germany"
                
                6. АВТОМОБИЛЬ - точное разделение (ТОЛЬКО ОСНОВНАЯ МОДЕЛЬ):
                   "BMW X7 40D xDrive M Sport Package" →
                   car_brand: "BMW"
                   car_model: "X7" (ТОЛЬКО базовая модель, без комплектаций!)
                   
                   "Volvo XC90 B5 Diesel Ultimate Dark AWD 8-Gang Automatikgetriebe" →
                   car_brand: "Volvo"
                   car_model: "XC90" (ТОЛЬКО базовая модель!)
                   
                   "Mercedes-Benz S65 AMG Long Biturbo V12" →
                   car_brand: "Mercedes-Benz"  
                   car_model: "S65 AMG" (базовая модель с основной версией)
                   
                   ПРАВИЛО: car_model = ТОЛЬКО основная модель без двигателя, трансмиссии, комплектации! 
                   
                7. ITEM DETAILS - ОПИСАНИЕ ДЛЯ ZOHO ITEM:
                   - Для автомобилей: модель без марки + VIN
                   - НЕ включай марку в item_details
                   - Всегда включай VIN если найден
                
                8. VIN - ищи 17-символьный код (WBA21EN0009025694)
                
                9. ПЛАТЕЖНАЯ ИНФОРМАЦИЯ:
                   - Метод оплаты: "WIRE TRANSFER", "Bank Transfer", "Cash"
                   - Условия оплаты: "Payment terms", срок оплаты
                
                КОНТЕКСТ ДОКУМЕНТА:
                - SELLER = Поставщик (supplier)
                - BUYER = Покупатель (customer)
                - VAT ID = VAT номер
                - DESCRIPTION = Описание товара
                
                ПРИМЕРЫ ПРАВИЛЬНОГО АНАЛИЗА:
                ✅ bill_number: "000216" (из "PRO-FORMA 000216")
                ✅ document_date: "16/07/2025" (из "PRO-FORMA DATE : 16/07/2025")
                ✅ bank_name: "RAIFFEISEN BANK ZRT"
                ✅ iban: "HU82 1206 5006 0205 2928 0020 0000"
                ✅ swift_bic: "UBRTHUHB"
                ✅ supplier_vat: "HU25381252" (из "EU VAT ID: HU25381252")
                ✅ payment_method: "WIRE TRANSFER"
                """
            )
        )
        
        # Анализируем документ
        result = await agent.run(text)
        car_analysis = result.output
        
        # Отладочная информация
        print(f"🔍 AI извлек car_model: '{car_analysis.car_model}'")
        print(f"🔍 AI извлек car_brand: '{car_analysis.car_brand}'")
        print(f"🔍 AI извлек car_full_name: '{car_analysis.car_full_name}'")
        print(f"🔍 AI извлек supplier_email: '{car_analysis.supplier_email}'")
        print(f"🔍 AI извлек supplier_phone: '{car_analysis.supplier_phone}'")
        
        # Генерируем car_item_name
        car_item_name = car_analysis.generate_car_item_name()
        print(f"🔍 Сгенерированное название: '{car_item_name}'")
        
        # Формируем правильное описание для ITEM (без марки + VIN)
        item_description = ""
        if car_analysis.car_model and car_analysis.vin:
            item_description = f"{car_analysis.car_model}, VIN: {car_analysis.vin}"
        elif car_analysis.car_model:
            item_description = car_analysis.car_model
        elif car_analysis.item_details:
            item_description = car_analysis.item_details
            
        # SKU = VIN
        item_sku = car_analysis.vin if car_analysis.vin else ""
        
        # Формируем результат
        enhanced_result = {
            "ai_enhanced": True,
            "document_type": car_analysis.document_type,
            "bill_number": car_analysis.bill_number,
            "document_date": car_analysis.document_date,
            "due_date": car_analysis.due_date,
            
            # Поставщик
            "supplier_name": car_analysis.supplier_name,
            "supplier_vat": car_analysis.supplier_vat,
            "supplier_email": car_analysis.supplier_email,
            "supplier_phone": car_analysis.supplier_phone,
            
            # Банковские реквизиты
            "bank_name": car_analysis.bank_name,
            "bank_account": car_analysis.bank_account,
            "iban": car_analysis.iban,
            "swift_bic": car_analysis.swift_bic,
            
            # Финансы
            "total_amount": car_analysis.total_amount,
            "currency": car_analysis.currency,
            "date": car_analysis.date,
            
            # Автомобиль
            "vin": car_analysis.vin,
            "car_brand": car_analysis.car_brand,
            "car_model": car_analysis.car_model,
            "car_full_name": car_analysis.car_full_name,
            "car_item_name": car_item_name,
            "engine_info": car_analysis.engine_info,
            "item_details": item_description,  # Правильное описание для ITEM
            "item_description": item_description,  # Дублируем для совместимости
            "item_sku": item_sku,  # SKU = VIN
            
            # Дополнительно
            "contract_type": car_analysis.contract_type,
            "payment_terms": car_analysis.payment_terms,
            "payment_method": car_analysis.payment_method,
            "our_company_name": car_analysis.our_company_name,
            "our_company_vat": car_analysis.our_company_vat,
            
            # Для совместимости
            "is_car_related": bool(car_analysis.vin or car_analysis.car_brand),
            "confidence": 0.95
        }
        
        # Добавляем адрес поставщика (правильный парсинг)
        if any([car_analysis.supplier_street, car_analysis.supplier_city, 
                car_analysis.supplier_zip_code, car_analysis.supplier_country]):
            enhanced_result["supplier_address"] = {
                "country": car_analysis.supplier_country or "",
                "address": car_analysis.supplier_street or "",
                "city": car_analysis.supplier_city or "",
                "zip_code": car_analysis.supplier_zip_code or "",
                "phone": car_analysis.supplier_phone or "",
                "state": ""  # Пустое поле для state
            }
            
            enhanced_result["supplier_street"] = car_analysis.supplier_street
            enhanced_result["supplier_city"] = car_analysis.supplier_city
            enhanced_result["supplier_zip_code"] = car_analysis.supplier_zip_code
            enhanced_result["supplier_country"] = car_analysis.supplier_country
            
            # Формируем полный адрес для отображения
            address_parts = []
            if car_analysis.supplier_street:
                address_parts.append(car_analysis.supplier_street)
            if car_analysis.supplier_zip_code and car_analysis.supplier_city:
                address_parts.append(f"{car_analysis.supplier_zip_code} {car_analysis.supplier_city}")
            elif car_analysis.supplier_city:
                address_parts.append(car_analysis.supplier_city)
            if car_analysis.supplier_country:
                address_parts.append(car_analysis.supplier_country)
            
            enhanced_result["full_address"] = ", ".join(address_parts)
        
        return enhanced_result
        
    except Exception as e:
        print(f"❌ Ошибка анализа: {e}")
        return {"ai_enhanced": False, "reason": f"Ошибка анализа: {e}"} 


# ===================== СЕРВИСНЫЕ ДОКУМЕНТЫ (УСЛУГИ) =====================
class ServiceLine(BaseModel):
    description: str = Field(..., description="Описание услуги")
    quantity: float = Field(1.0, description="Количество")
    rate: float = Field(..., description="Ставка/цена за единицу (нетто)")
    tax_rate: float = Field(0.0, description="Налог в процентах: 0, 8, 23 и т.д.")


class ServiceDocumentAnalysisResult(BaseModel):
    document_type: str = Field(description="Тип: service, transport, delivery, logistics и т.п.")
    is_final_invoice: bool = Field(default=True, description="Это окончательный инвойс, не проформа")
    should_create_bill: bool = Field(default=True, description="Следует ли предлагать создать Bill")
    suggested_account: str = Field(default="transportation services", description="Рекомендуемый Account в Zoho")

    # Реквизиты документа
    bill_number: Optional[str] = Field(None, description="Номер счета")
    document_date: Optional[str] = Field(None, description="Дата счета DD/MM/YYYY")
    due_date: Optional[str] = Field(None, description="Срок оплаты DD/MM/YYYY")

    # Поставщик
    supplier_name: str = Field(..., description="Название поставщика")
    supplier_vat: Optional[str] = Field(None, description="VAT поставщика (без пробелов)")
    supplier_email: Optional[str] = None
    supplier_phone: Optional[str] = None

    # Банковские реквизиты
    bank_name: Optional[str] = None
    bank_account: Optional[str] = None
    iban: Optional[str] = None
    swift_bic: Optional[str] = None

    # Суммы
    total_amount: float = Field(..., description="Общая сумма НЕТТО")
    currency: str = Field(default="EUR")
    tax_rate: float = Field(default=0.0, description="Основная налоговая ставка документа")

    # Дополнительно
    services: List[ServiceLine] = Field(default_factory=list)
    additional_documents: List[str] = Field(default_factory=list, description="Напр. ['CMR TR2025/58']")
    notes: Optional[str] = None


async def enhanced_service_document_analysis(text: str) -> Dict[str, Any]:
    """
    AI-анализатор документов услуг (доставка/транспорт и т.д.).
    Возвращает структурированные поля для последующего создания Bill.
    Всегда извлекаем НЕТТО (total_amount) и tax_rate. Если налог не указан — tax_rate=0.
    """
    if not PYDANTIC_AI_AVAILABLE:
        return {"ai_enhanced": False, "reason": "Pydantic AI недоступен"}
    if not os.getenv('OPENAI_API_KEY'):
        return {"ai_enhanced": False, "reason": "OpenAI API ключ не найден"}

    try:
        from pydantic_ai import Agent

        agent = Agent(
            'openai:gpt-4o',
            output_type=ServiceDocumentAnalysisResult,
            system_prompt=(
                """
                Ты — эксперт по анализу документов услуг (доставка, транспортировка, логистика, CMR).
                Твоя задача — строго извлечь НЕТТО сумму (total_amount) и налоговую ставку (tax_rate).
                Если налог явно не указан — tax_rate=0. В Польше (PL) возможны 23%/8% — учитывай, если указано.

                Обязательные поля:
                - document_type: одно из 'service', 'transport', 'delivery', 'logistics' (подходящее по контексту)
                - is_final_invoice: True, если это финальный инвойс, а не проформа
                - should_create_bill: True, если это финальный инвойс и есть поставщик
                - suggested_account: строка, например 'Transportation Services' (английский)
                - bill_number, document_date (DD/MM/YYYY), due_date (если есть)
                - supplier_* (name, vat, email/phone если найдешь). VAT выводи БЕЗ пробелов.
                - bank_name, bank_account, IBAN, SWIFT/BIC, если найдешь. IBAN и счета — без пробелов.
                - total_amount: НЕТТО сумма (если в документе есть брутто и НДС — вычисли нетто; если нет НДС — сумма как есть)
                - tax_rate: число процентов (0, 8, 23 …)
                - services: массив с описаниями услуг НА АНГЛИЙСКОМ (description), quantity/rate. Если одна сумма — quantity=1, unit_price=total_amount, total_amount=total_amount
                - additional_documents: добавь записи вида 'CMR {номер}', если встречается (например "CMR Nr. TR2025/58")
                - notes: КОРОТКОЕ примечание НА АНГЛИЙСКОМ для Bill, включи CMR если найден (например: "Includes CMR TR2025/58")
                """
            ),
        )

        result = await agent.run(text)
        s = result.output

        def _clean(val: Optional[str]) -> Optional[str]:
            if not val:
                return val
            return val.replace(' ', '').replace('\n', '').strip()

        out: Dict[str, Any] = {
            "ai_enhanced": True,
            "document_type": s.document_type,
            "is_final_invoice": s.is_final_invoice,
            "should_create_bill": s.should_create_bill,
            "suggested_account": s.suggested_account,
            "bill_number": s.bill_number,
            "document_date": s.document_date,
            "due_date": s.due_date,
            "supplier_name": s.supplier_name,
            "supplier_vat": _clean(s.supplier_vat),
            "supplier_email": s.supplier_email,
            "supplier_phone": _clean(s.supplier_phone),
            "bank_name": s.bank_name,
            "bank_account": _clean(s.bank_account),
            "iban": _clean(s.iban),
            "swift_bic": s.swift_bic,
            "total_amount": float(s.total_amount),
            "currency": s.currency,
            "tax_rate": float(s.tax_rate),
            "services": [sl.dict() for sl in s.services],
            "additional_documents": s.additional_documents,
            "notes": s.notes,
            # Для совместимости
            "is_car_related": False,
            "confidence": 0.95,
        }
        # Fallback: пытаемся дополнительно извлечь CMR из сырого текста, если агент не вернул
        try:
            import re
            if text:
                cmr_matches = re.findall(r"CMR\s*(?:Nr\.|No\.|#)?\s*([A-Z0-9\/\-]+)", text, flags=re.IGNORECASE)
                if cmr_matches:
                    existing = [d for d in (out.get("additional_documents") or [])]
                    for m in cmr_matches:
                        tag = f"CMR {m}"
                        if tag not in existing:
                            existing.append(tag)
                    out["additional_documents"] = existing
                    # Готовим удобные заметки для Bill, если их нет
                    if not out.get("notes"):
                        out["notes"] = ", ".join(existing)
                    out["notes_for_bill"] = out.get("notes")
            else:
                out["notes_for_bill"] = out.get("notes")
        except Exception:
            out["notes_for_bill"] = out.get("notes")
        return out
    except Exception as e:
        return {"ai_enhanced": False, "reason": f"Ошибка анализа услуг: {e}"}