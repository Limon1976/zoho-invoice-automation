"""
Асинхронная версия AI анализатора для FastAPI
===========================================

Версия без использования asyncio.run() для работы в FastAPI event loop.
"""

import os
from typing import Optional, Dict, Any
from decimal import Decimal

# Импорты Pydantic AI
try:
    from pydantic_ai import Agent, RunContext
    from pydantic import BaseModel, Field
    PYDANTIC_AI_AVAILABLE = True
except ImportError:
    PYDANTIC_AI_AVAILABLE = False

class AIAnalysisContext(BaseModel):
    """Контекст для AI анализа"""
    our_companies: list[str] = Field(
        default=["TaVie Europe OÜ", "Parkentertainment Sp. z o.o."],
        description="Наши компании"
    )
    car_brands: list[str] = Field(
        default=["BMW", "Mercedes", "Audi", "Porsche", "Ferrari", "Lamborghini"],
        description="Автомобильные бренды"
    )

class InvoiceAnalysisResult(BaseModel):
    """Результат AI анализа счета"""
    supplier_name: str = Field(..., description="Название поставщика")
    supplier_vat: Optional[str] = Field(None, description="VAT номер поставщика")
    bill_number: Optional[str] = Field(None, description="Номер документа")
    document_date: Optional[str] = Field(None, description="Дата документа")
    total_amount: Decimal = Field(..., description="Общая сумма")
    currency: str = Field("EUR", description="Валюта")
    our_company_name: Optional[str] = Field(None, description="Название нашей компании")
    is_our_company_supplier: bool = Field(False, description="Поставщик - это наша компания")
    is_car_related: bool = Field(False, description="Связан ли счет с автомобилями")
    vin_numbers: list[str] = Field(default_factory=list, description="VIN номера")
    vehicle_models: list[str] = Field(default_factory=list, description="Модели автомобилей")
    confidence_score: float = Field(0.5, ge=0.0, le=1.0, description="Уверенность анализа")
    processing_notes: list[str] = Field(default_factory=list, description="Заметки")

class CompanyMatchResult(BaseModel):
    """Результат сопоставления компании"""
    is_our_company: bool = Field(False, description="Является ли компания нашей")
    confidence: float = Field(0.5, ge=0.0, le=1.0, description="Уверенность")
    reasoning: str = Field("", description="Обоснование")

class AsyncAIInvoiceAnalyzer:
    """Асинхронный AI анализатор для FastAPI"""
    
    def __init__(self):
        self.available = PYDANTIC_AI_AVAILABLE and bool(os.getenv('OPENAI_API_KEY'))
        
        if self.available:
            try:
                # Создаем агентов
                self.invoice_agent = Agent(
                    'openai:gpt-4o-mini',
                    deps_type=AIAnalysisContext,
                    output_type=InvoiceAnalysisResult,
                    system_prompt=self._get_invoice_prompt(),
                    retries=2
                )
                
                self.company_agent = Agent(
                    'openai:gpt-4o-mini',
                    deps_type=AIAnalysisContext,
                    output_type=CompanyMatchResult,
                    system_prompt=self._get_company_prompt(),
                    retries=2
                )
                
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
    
    async def analyze_invoice_text(self, text: str) -> Optional[InvoiceAnalysisResult]:
        """
        Асинхронный анализ текста счета
        
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
        Асинхронное сопоставление компании
        
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

# Глобальный экземпляр анализатора
_async_analyzer = None

def get_async_analyzer() -> AsyncAIInvoiceAnalyzer:
    """Получение глобального экземпляра анализатора"""
    global _async_analyzer
    if _async_analyzer is None:
        _async_analyzer = AsyncAIInvoiceAnalyzer()
    return _async_analyzer

async def async_enhance_invoice_analysis(text: str) -> Dict[str, Any]:
    """
    Асинхронное улучшение анализа счета
    
    Args:
        text: Текст счета
        
    Returns:
        Словарь с результатом анализа
    """
    analyzer = get_async_analyzer()
    
    if not analyzer.available:
        return {"ai_enhanced": False, "reason": "Pydantic AI недоступен"}
    
    try:
        result = await analyzer.analyze_invoice_text(text)
        
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

async def async_enhance_company_detection(company_name: str) -> Dict[str, Any]:
    """
    Асинхронное улучшение определения компании
    
    Args:
        company_name: Название компании
        
    Returns:
        Словарь с результатом сопоставления
    """
    analyzer = get_async_analyzer()
    
    if not analyzer.available:
        return {"ai_enhanced": False, "reason": "AI недоступен"}
    
    try:
        result = await analyzer.match_company(company_name)
        
        if result:
            return {
                "ai_enhanced": True,
                "is_our_company": result.is_our_company,
                "confidence": result.confidence,
                "reasoning": result.reasoning
            }
        else:
            return {"ai_enhanced": False, "reason": "Сопоставление не удалось"}
            
    except Exception as e:
        return {"ai_enhanced": False, "reason": f"Ошибка: {e}"}

def is_async_ai_available() -> bool:
    """Проверка доступности асинхронного AI"""
    return PYDANTIC_AI_AVAILABLE and bool(os.getenv('OPENAI_API_KEY')) 