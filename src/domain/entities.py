"""
Domain Entities
===============

Core business entities that represent the main concepts in our domain.
Entities have identity and can change over time while maintaining their identity.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, date
from uuid import uuid4, UUID
from decimal import Decimal
from pydantic import BaseModel, Field, computed_field
import re

from .value_objects import (
    VATNumber, Money, Address, Email, PhoneNumber, BillNumber, 
    Currency, DocumentType
)

class Company(BaseModel):
    """Company entity representing business partners"""
    
    id: UUID = Field(default_factory=uuid4, description="Unique company identifier")
    name: str = Field(..., description="Company name")
    vat_number: Optional[VATNumber] = Field(None, description="VAT number")
    address: Optional[Address] = Field(None, description="Company address")
    email: Optional[Email] = Field(None, description="Primary email")
    phone: Optional[PhoneNumber] = Field(None, description="Primary phone")
    country: Optional[str] = Field(None, description="Country code")
    
    # Business properties
    is_our_company: bool = Field(False, description="Whether this is one of our companies")
    is_active: bool = Field(True, description="Whether company is active")
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.now, description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")
    
    @computed_field
    @property
    def display_name(self) -> str:
        """Return formatted company name for display"""
        return self.name.strip()
    
    @computed_field
    @property
    def vat_display(self) -> str:
        """Return formatted VAT number for display"""
        if self.vat_number:
            return self.vat_number.with_prefix
        return "No VAT"
    
    def matches_name(self, search_name: str, fuzzy: bool = True) -> bool:
        """Check if company name matches search string"""
        if not search_name:
            return False
            
        company_clean = self._normalize_name(self.name)
        search_clean = self._normalize_name(search_name)
        
        # Exact match
        if company_clean == search_clean:
            return True
            
        if fuzzy:
            # Contains match
            if search_clean in company_clean or company_clean in search_clean:
                return True
                
            # Word overlap (at least 50% of words match)
            company_words = set(company_clean.split())
            search_words = set(search_clean.split())
            
            if len(search_words) > 0:
                overlap = len(company_words & search_words) / len(search_words)
                return overlap >= 0.5
        
        return False
    
    def matches_vat(self, search_vat: str) -> bool:
        """Check if VAT number matches"""
        if not self.vat_number or not search_vat:
            return False
            
        # Normalize both VATs for comparison
        our_vat = self.vat_number.value.replace(" ", "").replace("-", "").upper()
        search_vat_clean = search_vat.replace(" ", "").replace("-", "").upper()
        
        # Try exact match
        if our_vat == search_vat_clean:
            return True
            
        # Try with/without country prefix
        our_without_prefix = self.vat_number.without_prefix
        search_without_prefix = re.sub(r'^[A-Z]{2}', '', search_vat_clean)
        
        return our_without_prefix == search_without_prefix
    
    def _normalize_name(self, name: str) -> str:
        """Normalize company name for comparison"""
        # Remove common business suffixes and normalize
        normalized = name.upper().strip()
        
        # Remove business entity suffixes
        suffixes = [
            " SP. Z O.O.", " SP Z OO", " SPÓŁKA Z O.O.", " SP ZOO",
            " OÜ", " OU", " LLC", " LTD", " LIMITED", " INC", " CORP",
            " GMBH", " GMBH & CO KG", " AG", " SA", " SAS", " SARL",
            " B.V.", " BV", " AB", " AS"
        ]
        
        for suffix in suffixes:
            if normalized.endswith(suffix):
                normalized = normalized[:-len(suffix)].strip()
                break
        
        # Remove special characters and extra spaces
        normalized = re.sub(r'[^\w\s]', ' ', normalized)
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        
        return normalized

class DocumentItem(BaseModel):
    """Individual item within a document"""
    
    id: UUID = Field(default_factory=uuid4, description="Unique item identifier")
    description: str = Field(..., description="Item description")
    quantity: Optional[Decimal] = Field(None, description="Quantity")
    unit_price: Optional[Money] = Field(None, description="Unit price")
    total_price: Optional[Money] = Field(None, description="Total price")
    
    # Vehicle-specific fields
    vin: Optional[str] = Field(None, description="Vehicle VIN number")
    vehicle_model: Optional[str] = Field(None, description="Vehicle model")
    
    @computed_field
    @property
    def is_car_related(self) -> bool:
        """Check if this item is car-related"""
        if self.vin and len(self.vin) == 17:
            return True
            
        car_keywords = [
            "mercedes", "bmw", "audi", "volkswagen", "porsche", "ferrari",
            "lamborghini", "bentley", "rolls royce", "maserati", "aston martin",
            "car", "vehicle", "automobile", "coupe", "sedan", "suv", "cabriolet"
        ]
        
        desc_lower = self.description.lower()
        return any(keyword in desc_lower for keyword in car_keywords)
    
    @computed_field
    @property
    def is_service(self) -> bool:
        """Check if this item represents a service"""
        service_keywords = [
            "service", "repair", "maintenance", "transport", "delivery",
            "shipping", "consultation", "installation", "support"
        ]
        
        desc_lower = self.description.lower()
        return any(keyword in desc_lower for keyword in service_keywords)
    
    @computed_field
    @property
    def car_item_name(self) -> Optional[str]:
        """Generate car item name from model and VIN"""
        if self.vehicle_model and self.vin and len(self.vin) >= 5:
            last_5_digits = re.sub(r'[^0-9]', '', self.vin)[-5:]
            if len(last_5_digits) == 5:
                return f"{self.vehicle_model}_{last_5_digits}"
        return None

class ProcessingDate(BaseModel):
    """Value object for document dates with validation"""
    value: date = Field(..., description="Date value")
    
    @computed_field
    @property
    def iso_format(self) -> str:
        """Return date in ISO format"""
        return self.value.isoformat()
    
    @computed_field
    @property
    def display_format(self) -> str:
        """Return date in human-readable format"""
        return self.value.strftime("%Y-%m-%d")

class BaseDocument(BaseModel):
    """Base class for all document types"""
    
    id: UUID = Field(default_factory=uuid4, description="Unique document identifier")
    document_type: DocumentType = Field(..., description="Type of document")
    bill_number: Optional[BillNumber] = Field(None, description="Document number")
    date: Optional[ProcessingDate] = Field(None, description="Document date")
    supplier: Company = Field(..., description="Supplier company")
    our_company: Company = Field(..., description="Our company (recipient)")
    currency: Currency = Field(Currency.EUR, description="Document currency")
    total_amount: Money = Field(..., description="Total document amount")
    items: List[DocumentItem] = Field(default_factory=list, description="Document items")
    raw_text: str = Field("", description="Original OCR text")
    created_at: datetime = Field(default_factory=datetime.now, description="Processing timestamp")
    
    # Processing flags
    is_valid: bool = Field(True, description="Whether document passed validation")
    skip_processing: bool = Field(False, description="Skip further processing")
    validation_errors: List[str] = Field(default_factory=list, description="Validation error messages")
    
    @computed_field
    @property
    def display_number(self) -> str:
        """Return formatted document number for display"""
        return str(self.bill_number) if self.bill_number else "No Number"
    
    @computed_field
    @property
    def is_car_purchase(self) -> bool:
        """Check if this document represents a car purchase"""
        return any(item.is_car_related for item in self.items)
    
    @computed_field
    @property
    def is_service_invoice(self) -> bool:
        """Check if this document is for services"""
        return any(item.is_service for item in self.items)
    
    @computed_field
    @property
    def is_outgoing(self) -> bool:
        """Check if this is an outgoing document (we are the supplier)"""
        return self.supplier.is_our_company
    
    def add_validation_error(self, error: str) -> None:
        """Add a validation error"""
        if error not in self.validation_errors:
            self.validation_errors.append(error)
            self.is_valid = False
    
    def clear_validation_errors(self) -> None:
        """Clear all validation errors"""
        self.validation_errors.clear()
        self.is_valid = True

class Invoice(BaseDocument):
    """Invoice document entity"""
    
    document_type: DocumentType = Field(DocumentType.INVOICE, description="Document type")
    
    # Invoice-specific fields
    due_date: Optional[ProcessingDate] = Field(None, description="Payment due date")
    payment_terms: Optional[str] = Field(None, description="Payment terms")
    tax_amount: Optional[Money] = Field(None, description="Tax amount")
    
    @computed_field
    @property
    def is_overdue(self) -> bool:
        """Check if invoice is overdue"""
        if not self.due_date:
            return False
        return self.due_date.value < date.today()

class Proforma(BaseDocument):
    """Proforma invoice document entity"""
    
    document_type: DocumentType = Field(DocumentType.PROFORMA, description="Document type")
    
    # Proforma-specific fields
    valid_until: Optional[ProcessingDate] = Field(None, description="Proforma validity date")
    cost_price: Optional[Money] = Field(None, description="Cost price")
    is_valid_for_us: bool = Field(True, description="Whether proforma is valid for processing")
    
    @computed_field
    @property
    def is_expired(self) -> bool:
        """Check if proforma is expired"""
        if not self.valid_until:
            return False
        return self.valid_until.value < date.today()

class Contract(BaseDocument):
    """Contract document entity"""
    
    document_type: DocumentType = Field(DocumentType.CONTRACT, description="Document type")
    
    # Contract-specific fields
    contract_type: str = Field("purchase", description="Type of contract")
    start_date: Optional[ProcessingDate] = Field(None, description="Contract start date")
    end_date: Optional[ProcessingDate] = Field(None, description="Contract end date")
    payment_terms: Optional[str] = Field(None, description="Payment terms")
    
    @computed_field
    @property
    def is_active(self) -> bool:
        """Check if contract is currently active"""
        today = date.today()
        
        if self.start_date and self.start_date.value > today:
            return False
            
        if self.end_date and self.end_date.value < today:
            return False
            
        return True

class CreditNote(BaseDocument):
    """Credit note document entity"""
    
    document_type: DocumentType = Field(DocumentType.CREDIT_NOTE, description="Document type")
    
    # Credit note specific fields
    original_invoice_number: Optional[str] = Field(None, description="Original invoice number")
    reason: Optional[str] = Field(None, description="Reason for credit note") 