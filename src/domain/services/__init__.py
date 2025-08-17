"""
Domain Services
===============

Domain services encapsulate business logic that doesn't naturally belong to a single entity.
They orchestrate complex business operations and maintain business rules consistency.

Available Services:
- VATValidatorService: VAT number validation and country detection
- CompanyMatcherService: Company identification and matching
- AccountDetectorService: Accounting category detection
"""

from .vat_validator import VATValidatorService, normalize_vat_number, format_vat_display
from .company_matcher import CompanyMatcherService  
from .account_detector import AccountDetectorService

__all__ = [
    "VATValidatorService",
    "CompanyMatcherService", 
    "AccountDetectorService",
    "normalize_vat_number",
    "format_vat_display"
] 