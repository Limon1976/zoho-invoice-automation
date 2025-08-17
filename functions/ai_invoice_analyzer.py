"""
AI Invoice Analyzer - Интеграция с существующим проектом
======================================================

Упрощенная версия AI анализатора для интеграции с functions/assistant_logic.py
Использует Pydantic AI для улучшения анализа счетов.
"""

import asyncio
from typing import Optional, List, Dict, Any
from decimal import Decimal
import re
import os

from pydantic import BaseModel, Field

# Импорты Pydantic AI
try:
    from pydantic_ai import Agent, RunContext
    PYDANTIC_AI_AVAILABLE = True
except ImportError:
    PYDANTIC_AI_AVAILABLE = False


class InvoiceAnalysisResult(BaseModel):
    """Результат AI анализа счета"""
    # Основная информация
    supplier_name: str = Field(..., description="Название поставщика")
    supplier_vat: Optional[str] = Field(None, description="VAT номер поставщика")
    
    # Номер и дата документа
    bill_number: Optional[str] = Field(None, description="Номер документа")
    document_date: Optional[str] = Field(None, description="Дата документа")
    
    # Финансовая информация
    total_amount: Decimal = Field(..., description="Общая сумма")
    currency: str = Field("EUR", description="Валюта")
    
    # Наша компания
    our_company_name: Optional[str] = Field(None, description="Название нашей компании")
    is_our_company_supplier: bool = Field(False, description="Поставщик - это наша компания")
    
    # Специализированная информация
    is_car_related: bool = Field(False, description="Связан ли счет с автомобилями")
    vin_numbers: List[str] = Field(default_factory=list, description="VIN номера")
    vehicle_models: List[str] = Field(default_factory=list, description="Модели автомобилей")
    
    # Метаданные
    confidence_score: float = Field(0.5, ge=0.0, le=1.0, description="Уверенность анализа")
    processing_notes: List[str] = Field(default_factory=list, description="Заметки")


class CompanyMatchResult(BaseModel):
    """Результат сопоставления компании"""
    is_our_company: bool = Field(False, description="Является ли компания нашей")
    confidence: float = Field(0.5, ge=0.0, le=1.0, description="Уверенность")
    reasoning: str = Field("", description="Обоснование")


class AIAnalysisContext(BaseModel):
    """Контекст для AI анализа"""
    our_companies: List[str] = Field(
        default=["TaVie Europe OÜ", "Parkentertainment Sp. z o.o."],
        description="Наши компании"
    )
    car_brands: List[str] = Field(
        default=["BMW", "Mercedes", "Audi", "Porsche", "Ferrari", "Lamborghini"],
        description="Автомобильные бренды"
    )


class AIInvoiceAnalyzer:
    """AI анализатор счетов для интеграции с existing кодом"""
    
    def __init__(self):
        self.available = PYDANTIC_AI_AVAILABLE
        
        if self.available:
            try:
                # Агент для анализа счетов
                self.invoice_agent = Agent(
                    'openai:gpt-4o-mini',
                    deps_type=AIAnalysisContext,
                    output_type=InvoiceAnalysisResult,
                    system_prompt=self._get_invoice_prompt(),
                    retries=2
                )
                
                # Агент для сопоставления компаний
                self.company_agent = Agent(
                    'openai:gpt-4o-mini',
                    deps_type=AIAnalysisContext,
                    output_type=CompanyMatchResult,
                    system_prompt=self._get_company_prompt(),
                    retries=2
                )
                
                self._register_tools()
                
            except Exception as e:
                print(f"Ошибка инициализации AI: {e}")
                self.available = False
    
    def _get_invoice_prompt(self) -> str:
        """Промпт для анализа счетов"""
        return """
        Ты эксперт по анализу счетов и документов.
        Извлеки ключевую информацию из предоставленного текста.
        
        ОСОБОЕ ВНИМАНИЕ:
        1. Автомобили: ищи VIN номера (17 символов), модели BMW/Mercedes/Audi
        2. VAT номера: PL1234567890, EE123456789, DE123456789
        3. Наши компании: TaVie Europe OÜ, Parkentertainment Sp. z o.o.
        4. Суммы и валюты: EUR, USD, PLN
        
        Будь точным и консервативным в оценке уверенности.
        """
    
    def _get_company_prompt(self) -> str:
        """Промпт для сопоставления компаний"""
        return """
        Определи, является ли указанная компания одной из наших:
        - TaVie Europe OÜ (Эстония)
        - Parkentertainment Sp. z o.o. (Польша)
        
        Учитывай варианты написания и сокращения.
        """
    
    def _register_tools(self):
        """Регистрация инструментов"""
        
        @self.invoice_agent.tool
        async def extract_vin_numbers(ctx: RunContext[AIAnalysisContext], text: str) -> List[str]:
            """Поиск VIN номеров"""
            vin_pattern = r'\b[A-HJ-NPR-Z0-9]{17}\b'
            return list(set(re.findall(vin_pattern, text.upper())))
        
        @self.invoice_agent.tool
        async def detect_car_brands(ctx: RunContext[AIAnalysisContext], text: str) -> List[str]:
            """Обнаружение автомобильных брендов"""
            found_brands = []
            text_upper = text.upper()
            
            for brand in ctx.deps.car_brands:
                if brand.upper() in text_upper:
                    found_brands.append(brand)
            
            return found_brands
        
        @self.company_agent.tool
        async def fuzzy_company_match(ctx: RunContext[AIAnalysisContext], company_name: str) -> Dict[str, Any]:
            """Нечеткое сопоставление компаний"""
            from difflib import SequenceMatcher
            
            best_match = ""
            best_score = 0.0
            
            for our_company in ctx.deps.our_companies:
                score = SequenceMatcher(None, company_name.lower(), our_company.lower()).ratio()
                if score > best_score:
                    best_score = score
                    best_match = our_company
            
            return {
                "best_match": best_match,
                "similarity": best_score,
                "is_match": best_score > 0.7
            }
    
    async def analyze_invoice_text(self, text: str) -> Optional[InvoiceAnalysisResult]:
        """
        Анализ текста счета с помощью AI
        
        Args:
            text: Текст счета
            
        Returns:
            Результат анализа или None при ошибке
        """
        if not self.available:
            return None
        
        try:
            context = AIAnalysisContext()
            result = await self.invoice_agent.run(
                f"Проанализируй счет:\n\n{text}",
                deps=context
            )
            return result.output
            
        except Exception as e:
            print(f"Ошибка AI анализа: {e}")
            return None
    
    async def match_company(self, company_name: str) -> Optional[CompanyMatchResult]:
        """
        Сопоставление компании
        
        Args:
            company_name: Название компании
            
        Returns:
            Результат сопоставления
        """
        if not self.available:
            return None
        
        try:
            context = AIAnalysisContext()
            result = await self.company_agent.run(
                f"Проверь компанию: {company_name}",
                deps=context
            )
            return result.output
            
        except Exception as e:
            print(f"Ошибка сопоставления: {e}")
            return None
    
    def analyze_invoice_sync(self, text: str) -> Optional[InvoiceAnalysisResult]:
        """Синхронная версия анализа для интеграции"""
        if not self.available:
            return None
        
        try:
            # Проверяем, есть ли уже запущенный event loop
            try:
                loop = asyncio.get_running_loop()
                # Если loop запущен, создаем новую задачу
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, self.analyze_invoice_text(text))
                    return future.result()
            except RuntimeError:
                # Если loop не запущен, используем asyncio.run
                return asyncio.run(self.analyze_invoice_text(text))
        except Exception as e:
            print(f"Ошибка синхронного анализа: {e}")
            return None
    
    def match_company_sync(self, company_name: str) -> Optional[CompanyMatchResult]:
        """Синхронная версия сопоставления"""
        if not self.available:
            return None
        
        try:
            # Проверяем, есть ли уже запущенный event loop
            try:
                loop = asyncio.get_running_loop()
                # Если loop запущен, создаем новую задачу
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, self.match_company(company_name))
                    return future.result()
            except RuntimeError:
                # Если loop не запущен, используем asyncio.run
                return asyncio.run(self.match_company(company_name))
        except Exception as e:
            print(f"Ошибка синхронного сопоставления: {e}")
            return None


# Функции для интеграции с assistant_logic.py
def enhance_invoice_analysis(text: str) -> Dict[str, Any]:
    """
    Улучшение анализа счета с помощью AI
    
    Args:
        text: Текст счета
        
    Returns:
        Словарь с дополнительной информацией
    """
    analyzer = AIInvoiceAnalyzer()
    
    if not analyzer.available:
        return {"ai_enhanced": False, "reason": "Pydantic AI недоступен"}
    
    # Проверяем API ключ
    if not os.getenv('OPENAI_API_KEY'):
        return {"ai_enhanced": False, "reason": "OPENAI_API_KEY не установлен"}
    
    try:
        result = analyzer.analyze_invoice_sync(text)
        
        if result:
            return {
                "ai_enhanced": True,
                "supplier_name": result.supplier_name,
                "supplier_vat": result.supplier_vat,
                "bill_number": result.bill_number,
                "total_amount": float(result.total_amount),
                "currency": result.currency,
                "is_car_related": result.is_car_related,
                "vin_numbers": result.vin_numbers,
                "vehicle_models": result.vehicle_models,
                "our_company_name": result.our_company_name,
                "is_our_company_supplier": result.is_our_company_supplier,
                "confidence": result.confidence_score,
                "notes": result.processing_notes
            }
        else:
            return {"ai_enhanced": False, "reason": "Анализ не удался"}
            
    except Exception as e:
        return {"ai_enhanced": False, "reason": f"Ошибка: {e}"}


def enhance_company_detection(company_name: str) -> Dict[str, Any]:
    """
    Улучшение определения компании с помощью AI
    
    Args:
        company_name: Название компании
        
    Returns:
        Словарь с результатом сопоставления
    """
    analyzer = AIInvoiceAnalyzer()
    
    if not analyzer.available or not os.getenv('OPENAI_API_KEY'):
        return {"ai_enhanced": False}
    
    try:
        result = analyzer.match_company_sync(company_name)
        
        if result:
            return {
                "ai_enhanced": True,
                "is_our_company": result.is_our_company,
                "confidence": result.confidence,
                "reasoning": result.reasoning
            }
        else:
            return {"ai_enhanced": False}
            
    except Exception as e:
        return {"ai_enhanced": False, "error": str(e)}


def is_ai_available() -> bool:
    """Проверка доступности AI"""
    return PYDANTIC_AI_AVAILABLE and bool(os.getenv('OPENAI_API_KEY'))


# Тестовая функция
def test_ai_analyzer():
    """Тест AI анализатора"""
    print("🧪 Тест AI анализатора")
    print(f"Pydantic AI доступен: {PYDANTIC_AI_AVAILABLE}")
    print(f"OpenAI API ключ: {'✅' if os.getenv('OPENAI_API_KEY') else '❌'}")
    
    if not is_ai_available():
        print("❌ AI анализ недоступен")
        return
    
    sample_text = """
    Invoice No: 12345
    Supplier: BMW Deutschland
    VAT: DE123456789
    Total: 50,000.00 EUR
    Vehicle: BMW X5
    VIN: WBAFG91090DD12345
    """
    
    print("\n📄 Тестирование анализа...")
    result = enhance_invoice_analysis(sample_text)
    
    if result.get("ai_enhanced"):
        print("✅ AI анализ успешен:")
        print(f"  Поставщик: {result.get('supplier_name')}")
        print(f"  VAT: {result.get('supplier_vat')}")
        print(f"  Автомобильная тематика: {result.get('is_car_related')}")
        print(f"  VIN номера: {result.get('vin_numbers')}")
        print(f"  Уверенность: {result.get('confidence'):.1%}")
    else:
        print(f"❌ AI анализ не удался: {result.get('reason')}")


if __name__ == "__main__":
    test_ai_analyzer() 