"""
Value Objects
=============

Immutable objects that represent concepts with no identity.
They are defined by their attributes rather than identity.
"""

from typing import Optional, List
from decimal import Decimal
from enum import Enum
from pydantic import BaseModel, Field, validator
import re

class Currency(str, Enum):
    """Supported currencies"""
    EUR = "EUR"
    USD = "USD"
    PLN = "PLN"
    SEK = "SEK"
    GBP = "GBP"

class DocumentType(str, Enum):
    """Document types"""
    INVOICE = "Invoice"
    PROFORMA = "Proforma"
    CREDIT_NOTE = "Credit Note"
    CONTRACT = "Contract"
    RECEIPT = "Receipt"

class VATNumber(BaseModel):
    """Value object for VAT numbers with validation"""
    value: str = Field(..., description="VAT number")
    country_code: Optional[str] = Field(None, description="Country code (e.g., 'PL', 'EE')")
    
    @validator('value')
    def validate_vat_format(cls, v):
        """Basic VAT format validation"""
        if not v or len(v.strip()) == 0:
            raise ValueError("VAT number cannot be empty")
        
        # Remove spaces and convert to uppercase
        v = v.replace(" ", "").replace("-", "").upper()
        
        # Basic format check (letters + numbers)
        if not re.match(r'^[A-Z0-9]+$', v):
            raise ValueError("VAT number can only contain letters and numbers")
        
        return v
    
    @property
    def with_prefix(self) -> str:
        """Return VAT with country prefix if available"""
        if self.country_code and not self.value.startswith(self.country_code):
            return f"{self.country_code}{self.value}"
        return self.value
    
    @property
    def without_prefix(self) -> str:
        """Return VAT without country prefix"""
        # Remove common country prefixes
        prefixes = ['PL', 'EE', 'DE', 'FR', 'ES', 'IT', 'NL', 'BE', 'LU', 'AT', 'DK', 'FI', 'SE', 'GB', 'US']
        for prefix in prefixes:
            if self.value.startswith(prefix):
                return self.value[len(prefix):]
        return self.value

class Money(BaseModel):
    """Value object for monetary amounts"""
    amount: Decimal = Field(..., description="Amount")
    currency: Currency = Field(Currency.EUR, description="Currency")
    
    @validator('amount')
    def validate_amount(cls, v):
        """Validate monetary amount"""
        if v < 0:
            raise ValueError("Amount cannot be negative")
        return v
    
    def __str__(self):
        return f"{self.amount} {self.currency.value}"
    
    def to_eur(self, exchange_rate: Optional[Decimal] = None) -> 'Money':
        """Convert to EUR (simplified - in real app would use exchange service)"""
        if self.currency == Currency.EUR:
            return self
        
        # Simplified conversion rates
        rates = {
            Currency.USD: Decimal('0.85'),
            Currency.PLN: Decimal('0.23'),
            Currency.SEK: Decimal('0.09'),
            Currency.GBP: Decimal('1.15')
        }
        
        rate = exchange_rate or rates.get(self.currency, Decimal('1.0'))
        return Money(amount=self.amount * rate, currency=Currency.EUR)

class Address(BaseModel):
    """Value object for addresses"""
    street: Optional[str] = Field(None, description="Street address")
    city: Optional[str] = Field(None, description="City")
    postal_code: Optional[str] = Field(None, description="Postal/ZIP code")
    country: Optional[str] = Field(None, description="Country")
    
    def __str__(self):
        parts = [p for p in [self.street, self.city, self.postal_code, self.country] if p]
        return ", ".join(parts)
    
    @property
    def is_complete(self) -> bool:
        """Check if address has all essential fields"""
        return bool(self.city and self.country)

class Email(BaseModel):
    """Value object for email addresses"""
    value: str = Field(..., description="Email address")
    
    @validator('value')
    def validate_email(cls, v):
        """Basic email validation"""
        if not v or '@' not in v:
            raise ValueError("Invalid email format")
        return v.lower().strip()
    
    def __str__(self):
        return self.value

class PhoneNumber(BaseModel):
    """Value object for phone numbers"""
    value: str = Field(..., description="Phone number")
    country_code: Optional[str] = Field(None, description="Country code")
    
    @validator('value')
    def validate_phone(cls, v):
        """Basic phone validation"""
        if not v:
            raise ValueError("Phone number cannot be empty")
        
        # Remove common formatting
        cleaned = re.sub(r'[^\d+]', '', v)
        if len(cleaned) < 7:
            raise ValueError("Phone number too short")
        
        return cleaned
    
    def __str__(self):
        return self.value

class BillNumber(BaseModel):
    """Value object for bill/invoice numbers"""
    value: str = Field(..., description="Bill number")
    
    @validator('value')
    def validate_bill_number(cls, v):
        """Basic bill number validation"""
        if not v or len(v.strip()) == 0:
            raise ValueError("Bill number cannot be empty")
        return v.strip()
    
    def __str__(self):
        return self.value 