"""
AI Document Analyzer Service
============================

Доменный сервис для интеллектуального анализа документов с использованием Pydantic AI.
Интегрируется с существующей архитектурой проекта.
"""

import asyncio
from typing import Optional, List, Dict, Any
from decimal import Decimal
from datetime import datetime
import re

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext

from ..entities import Invoice, Company, DocumentItem, Proforma, Contract
from ..value_objects import Money, Currency, VATNumber, BillNumber, Address
from ..exceptions import DocumentParsingError, ValidationError


class DocumentAnalysisContext(BaseModel):
    """Контекст для AI анализа документов"""
    our_companies: List[Dict[str, str]] = Field(
        default=[
            {"name": "TaVie Europe OÜ", "vat": "EE102288270", "country": "Estonia"},
            {"name": "Parkentertainment Sp. z o.o.", "vat": "PL5272956146", "country": "Poland"},
        ],
        description="Список наших компаний"
    )
    
    known_suppliers: List[str] = Field(
        default=["BMW", "Mercedes-Benz", "Audi", "Porsche", "Volkswagen", "Ferrari", "Lamborghini"],
        description="Известные поставщики автомобилей"
    )
    
    supported_currencies: List[str] = Field(
        default=["EUR", "USD", "PLN", "SEK", "GBP"],
        description="Поддерживаемые валюты"
    )


class AIDocumentAnalysisResult(BaseModel):
    """Результат AI анализа документа"""
    # Основная информация
    document_type: str = Field(..., description="Тип документа: invoice, proforma, contract")
    supplier_name: str = Field(..., description="Название поставщика")
    supplier_vat: Optional[str] = Field(None, description="VAT номер поставщика")
    supplier_address: Optional[str] = Field(None, description="Адрес поставщика")
    
    # Номер и дата документа
    bill_number: Optional[str] = Field(None, description="Номер документа")
    document_date: Optional[str] = Field(None, description="Дата документа в формате YYYY-MM-DD")
    due_date: Optional[str] = Field(None, description="Срок оплаты в формате YYYY-MM-DD")
    
    # Финансовая информация
    total_amount: Decimal = Field(..., description="Общая сумма")
    currency: str = Field(..., description="Валюта")
    tax_amount: Optional[Decimal] = Field(None, description="Сумма налога")
    
    # Наша компания
    our_company_name: Optional[str] = Field(None, description="Название нашей компании из документа")
    our_company_vat: Optional[str] = Field(None, description="VAT нашей компании")
    
    # Специализированная информация
    is_car_related: bool = Field(..., description="Связан ли документ с автомобилями")
    vin_numbers: List[str] = Field(default_factory=list, description="Найденные VIN номера")
    vehicle_models: List[str] = Field(default_factory=list, description="Модели автомобилей")
    
    # Позиции документа
    items: List[Dict[str, Any]] = Field(
        default_factory=list, 
        description="Позиции документа с описанием, количеством и ценой"
    )
    
    # Метаданные анализа
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Уверенность в анализе")
    processing_notes: List[str] = Field(default_factory=list, description="Заметки по обработке")


class CompanyMatchingResult(BaseModel):
    """Результат сопоставления компании"""
    is_our_company: bool = Field(..., description="Является ли компания нашей")
    matched_company: Optional[Dict[str, str]] = Field(None, description="Найденная компания")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Уверенность сопоставления")
    reasoning: str = Field(..., description="Обоснование решения")


class AIDocumentAnalyzer:
    """Сервис для AI анализа документов"""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Инициализация AI анализатора
        
        Args:
            api_key: OpenAI API ключ (если не передан, берется из переменной окружения)
        """
        try:
            # Основной агент для анализа документов
            self.document_analyzer = Agent(
                'openai:gpt-4o-mini',
                deps_type=DocumentAnalysisContext,
                output_type=AIDocumentAnalysisResult,
                system_prompt=self._get_document_analysis_prompt(),
                retries=2
            )
            
            # Агент для сопоставления компаний
            self.company_matcher = Agent(
                'openai:gpt-4o-mini', 
                deps_type=DocumentAnalysisContext,
                output_type=CompanyMatchingResult,
                system_prompt=self._get_company_matching_prompt(),
                retries=2
            )
            
            # Добавляем инструменты
            self._register_tools()
            
        except Exception as e:
            raise DocumentParsingError("ai_analyzer", f"Ошибка инициализации AI анализатора: {e}")
    
    def _get_document_analysis_prompt(self) -> str:
        """Промпт для анализа документов"""
        return """
        Ты эксперт по анализу финансовых документов и счетов.
        Анализируй предоставленный текст документа и извлекай ключевую информацию.
        
        ОСОБОЕ ВНИМАНИЕ:
        1. Автомобильная тематика - ищи VIN номера (17 символов), модели автомобилей
        2. VAT номера - форматы: PL1234567890, EE123456789, DE123456789 и т.д.
        3. Даты - различные форматы: DD.MM.YYYY, DD/MM/YYYY, YYYY-MM-DD
        4. Суммы - с разными разделителями: 50,000.00, 50.000,00, 50 000.00
        5. Наши компании - TaVie Europe OÜ, Parkentertainment Sp. z o.o.
        
        ТИПЫ ДОКУМЕНТОВ:
        - invoice: обычный счет к оплате
        - proforma: проформа-счет
        - contract: договор или контракт
        
        Будь точным и внимательным к деталям. Указывай высокую уверенность только при четких данных.
        """
    
    def _get_company_matching_prompt(self) -> str:
        """Промпт для сопоставления компаний"""
        return """
        Ты эксперт по сопоставлению компаний.
        Определи, принадлежит ли указанная компания к нашим компаниям.
        
        НАШИ КОМПАНИИ:
        - TaVie Europe OÜ (VAT: EE102288270, Эстония)
        - Parkentertainment Sp. z o.o. (VAT: PL5272956146, Польша)
        
        УЧИТЫВАЙ:
        - Различные варианты написания и сокращения
        - Возможные опечатки и форматирование
        - Контекст документа
        
        Объясни свое решение подробно.
        """
    
    def _register_tools(self):
        """Регистрация инструментов для AI агентов"""
        
        @self.document_analyzer.tool
        async def extract_vin_numbers(ctx: RunContext[DocumentAnalysisContext], text: str) -> List[str]:
            """Извлечение VIN номеров из текста"""
            vin_pattern = r'\b[A-HJ-NPR-Z0-9]{17}\b'
            vins = re.findall(vin_pattern, text.upper())
            return list(set(vins))  # Убираем дубликаты
        
        @self.document_analyzer.tool
        async def validate_vat_number(ctx: RunContext[DocumentAnalysisContext], vat: str) -> Dict[str, Any]:
            """Валидация VAT номера"""
            vat_patterns = {
                'PL': r'^PL\d{10}$',
                'EE': r'^EE\d{9}$',
                'DE': r'^DE\d{9}$',
                'FR': r'^FR[A-Z0-9]{2}\d{9}$',
                'GB': r'^GB\d{9}$|^GB\d{12}$',
            }
            
            vat_clean = vat.replace(' ', '').replace('-', '').upper()
            
            for country, pattern in vat_patterns.items():
                if re.match(pattern, vat_clean):
                    return {
                        "valid": True,
                        "country": country,
                        "formatted": vat_clean
                    }
            
            return {"valid": False, "country": None, "formatted": vat_clean}
        
        @self.document_analyzer.tool
        async def detect_car_models(ctx: RunContext[DocumentAnalysisContext], text: str) -> List[str]:
            """Обнаружение моделей автомобилей в тексте"""
            car_models = [
                "BMW X1", "BMW X3", "BMW X5", "BMW X6", "BMW X7",
                "Mercedes-Benz C-Class", "Mercedes-Benz E-Class", "Mercedes-Benz S-Class",
                "Audi A3", "Audi A4", "Audi A6", "Audi A8", "Audi Q3", "Audi Q5", "Audi Q7",
                "Range Rover", "Range Rover Sport", "Range Rover Evoque",
                "Porsche 911", "Porsche Cayenne", "Porsche Macan",
                "Ferrari", "Lamborghini"
            ]
            
            found_models = []
            text_upper = text.upper()
            
            for model in car_models:
                if model.upper() in text_upper:
                    found_models.append(model)
            
            return found_models
        
        @self.company_matcher.tool
        async def fuzzy_match_company(ctx: RunContext[DocumentAnalysisContext], company_name: str) -> Dict[str, Any]:
            """Нечеткое сопоставление названия компании"""
            from difflib import SequenceMatcher
            
            best_match = None
            best_score = 0.0
            
            for our_company in ctx.deps.our_companies:
                our_name = our_company["name"]
                score = SequenceMatcher(None, company_name.lower(), our_name.lower()).ratio()
                
                if score > best_score:
                    best_score = score
                    best_match = our_company
            
            return {
                "best_match": best_match,
                "similarity_score": best_score,
                "is_likely_match": best_score > 0.7
            }
    
    async def analyze_document(self, text: str) -> AIDocumentAnalysisResult:
        """
        Анализ документа с помощью AI
        
        Args:
            text: Текст документа для анализа
            
        Returns:
            Результат анализа документа
            
        Raises:
            DocumentProcessingError: При ошибке анализа
        """
        try:
            context = DocumentAnalysisContext()
            
            result = await self.document_analyzer.run(
                f"Проанализируй этот документ и извлеки всю ключевую информацию:\n\n{text}",
                deps=context
            )
            
            return result.output
            
        except Exception as e:
            raise DocumentProcessingError(f"Ошибка AI анализа документа: {e}")
    
    async def match_company(self, company_name: str) -> CompanyMatchingResult:
        """
        Сопоставление компании с нашими компаниями
        
        Args:
            company_name: Название компании для проверки
            
        Returns:
            Результат сопоставления
        """
        try:
            context = DocumentAnalysisContext()
            
            result = await self.company_matcher.run(
                f"Определи, является ли компания '{company_name}' одной из наших компаний",
                deps=context
            )
            
            return result.output
            
        except Exception as e:
            raise DocumentProcessingError(f"Ошибка сопоставления компании: {e}")
    
    async def create_invoice_from_analysis(
        self, 
        analysis: AIDocumentAnalysisResult, 
        raw_text: str = ""
    ) -> Invoice:
        """
        Создание объекта Invoice из результата AI анализа
        
        Args:
            analysis: Результат AI анализа
            raw_text: Исходный текст документа
            
        Returns:
            Готовый объект Invoice
            
        Raises:
            ValidationError: При ошибке валидации данных
        """
        try:
            # Создаем поставщика
            supplier_vat = None
            if analysis.supplier_vat:
                try:
                    country_code = analysis.supplier_vat[:2] if len(analysis.supplier_vat) >= 2 else None
                    supplier_vat = VATNumber(value=analysis.supplier_vat, country_code=country_code)
                except Exception:
                    pass
            
            supplier_address = None
            if analysis.supplier_address:
                supplier_address = Address(full_address=analysis.supplier_address)
            
            supplier = Company(
                name=analysis.supplier_name,
                vat_number=supplier_vat,
                address=supplier_address,
                country=supplier_vat.country_code if supplier_vat else None,
                is_our_company=False
            )
            
            # Определяем нашу компанию
            our_company = await self._determine_our_company(analysis)
            
            # Создаем финансовые объекты
            try:
                currency = Currency(analysis.currency)
            except ValueError:
                currency = Currency.EUR
            
            total_money = Money(amount=analysis.total_amount, currency=currency)
            
            tax_money = None
            if analysis.tax_amount:
                tax_money = Money(amount=analysis.tax_amount, currency=currency)
            
            # Создаем позиции документа
            items = []
            for item_data in analysis.items:
                try:
                    item = DocumentItem(
                        description=item_data.get("description", ""),
                        quantity=Decimal(str(item_data.get("quantity", 1))),
                        unit_price=Money(
                            amount=Decimal(str(item_data.get("unit_price", 0))),
                            currency=currency
                        ) if item_data.get("unit_price") else None,
                        total_price=Money(
                            amount=Decimal(str(item_data.get("total_price", 0))),
                            currency=currency
                        ) if item_data.get("total_price") else None,
                        vin=item_data.get("vin"),
                        vehicle_model=item_data.get("vehicle_model")
                    )
                    items.append(item)
                except Exception:
                    # Пропускаем некорректные позиции
                    continue
            
            # Создаем номер документа
            bill_number = None
            if analysis.bill_number:
                try:
                    bill_number = BillNumber(value=analysis.bill_number)
                except Exception:
                    pass
            
            # Обрабатываем дату
            doc_date = None
            if analysis.document_date:
                try:
                    from datetime import date
                    doc_date = date.fromisoformat(analysis.document_date)
                except Exception:
                    pass
            
            # Создаем соответствующий тип документа
            if analysis.document_type.lower() == "proforma":
                return Proforma(
                    supplier=supplier,
                    our_company=our_company,
                    currency=currency,
                    total_amount=total_money,
                    tax_amount=tax_money,
                    bill_number=bill_number,
                    date=doc_date,
                    items=items,
                    raw_text=raw_text
                )
            elif analysis.document_type.lower() == "contract":
                return Contract(
                    supplier=supplier,
                    our_company=our_company, 
                    currency=currency,
                    total_amount=total_money,
                    bill_number=bill_number,
                    date=doc_date,
                    items=items,
                    raw_text=raw_text
                )
            else:
                # По умолчанию создаем Invoice
                return Invoice(
                    supplier=supplier,
                    our_company=our_company,
                    currency=currency,
                    total_amount=total_money,
                    tax_amount=tax_money,
                    bill_number=bill_number,
                    date=doc_date,
                    items=items,
                    raw_text=raw_text
                )
                
        except Exception as e:
            raise ValidationError(f"Ошибка создания Invoice из AI анализа: {e}")
    
    async def _determine_our_company(self, analysis: AIDocumentAnalysisResult) -> Company:
        """Определение нашей компании из анализа"""
        context = DocumentAnalysisContext()
        
        # Пытаемся найти по названию или VAT
        for our_company_data in context.our_companies:
            if analysis.our_company_name and our_company_data["name"] in analysis.our_company_name:
                return Company(
                    name=our_company_data["name"],
                    vat_number=VATNumber(
                        value=our_company_data["vat"],
                        country_code=our_company_data["vat"][:2]
                    ),
                    country=our_company_data["country"],
                    is_our_company=True
                )
            
            if analysis.our_company_vat and our_company_data["vat"] in analysis.our_company_vat:
                return Company(
                    name=our_company_data["name"],
                    vat_number=VATNumber(
                        value=our_company_data["vat"],
                        country_code=our_company_data["vat"][:2]
                    ),
                    country=our_company_data["country"],
                    is_our_company=True
                )
        
        # По умолчанию возвращаем первую компанию
        default_company = context.our_companies[0]
        return Company(
            name=default_company["name"],
            vat_number=VATNumber(
                value=default_company["vat"],
                country_code=default_company["vat"][:2]
            ),
            country=default_company["country"],
            is_our_company=True
        ) 