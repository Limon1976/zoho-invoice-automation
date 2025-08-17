"""
Domain Exceptions
================

Domain-specific exceptions that represent business rule violations
and error conditions within our invoice processing domain.
"""

from typing import Optional, Dict, Any, List


class DomainException(Exception):
    """Base exception for all domain-related errors"""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.details = details or {}
        super().__init__(message)


class ValidationError(DomainException):
    """Raised when domain validation rules are violated"""
    
    def __init__(self, field: str, message: str, value: Any = None):
        self.field = field
        self.value = value
        details = {"field": field, "value": value}
        super().__init__(f"Validation error in {field}: {message}", details)


class BusinessRuleViolation(DomainException):
    """Raised when business rules are violated"""
    
    def __init__(self, rule: str, message: str, context: Optional[Dict[str, Any]] = None):
        self.rule = rule
        self.context = context or {}
        details = {"rule": rule, "context": self.context}
        super().__init__(f"Business rule violation ({rule}): {message}", details)


# VAT-related exceptions
class VATException(DomainException):
    """Base exception for VAT-related errors"""
    pass


class InvalidVATFormat(VATException):
    """Raised when VAT number format is invalid"""
    
    def __init__(self, vat_number: str, country: Optional[str] = None):
        self.vat_number = vat_number
        self.country = country
        
        message = f"Invalid VAT format: {vat_number}"
        if country:
            message += f" for country {country}"
            
        details = {"vat_number": vat_number, "country": country}
        super().__init__(message, details)


class VATCountryMismatch(VATException):
    """Raised when VAT country doesn't match expected country"""
    
    def __init__(self, vat_number: str, expected_country: str, detected_country: str):
        self.vat_number = vat_number
        self.expected_country = expected_country
        self.detected_country = detected_country
        
        message = f"VAT country mismatch: {vat_number} belongs to {detected_country}, expected {expected_country}"
        details = {
            "vat_number": vat_number,
            "expected_country": expected_country,
            "detected_country": detected_country
        }
        super().__init__(message, details)


# Company-related exceptions
class CompanyException(DomainException):
    """Base exception for company-related errors"""
    pass


class CompanyNotFound(CompanyException):
    """Raised when a company cannot be found"""
    
    def __init__(self, search_criteria: Dict[str, Any]):
        self.search_criteria = search_criteria
        
        criteria_str = ", ".join([f"{k}={v}" for k, v in search_criteria.items()])
        message = f"Company not found with criteria: {criteria_str}"
        super().__init__(message, {"search_criteria": search_criteria})


class MultipleCompaniesFound(CompanyException):
    """Raised when multiple companies match search criteria"""
    
    def __init__(self, search_criteria: Dict[str, Any], count: int):
        self.search_criteria = search_criteria
        self.count = count
        
        criteria_str = ", ".join([f"{k}={v}" for k, v in search_criteria.items()])
        message = f"Multiple companies ({count}) found with criteria: {criteria_str}"
        details = {"search_criteria": search_criteria, "count": count}
        super().__init__(message, details)


class CompanyOwnershipConflict(CompanyException):
    """Raised when there's a conflict in company ownership detection"""
    
    def __init__(self, company_name: str, conflicting_indicators: List[str]):
        self.company_name = company_name
        self.conflicting_indicators = conflicting_indicators
        
        indicators_str = ", ".join(conflicting_indicators)
        message = f"Ownership conflict for company {company_name}: {indicators_str}"
        details = {"company_name": company_name, "conflicting_indicators": conflicting_indicators}
        super().__init__(message, details)


# Document-related exceptions
class DocumentException(DomainException):
    """Base exception for document-related errors"""
    pass


class DocumentParsingError(DocumentException):
    """Raised when document cannot be parsed"""
    
    def __init__(self, document_path: str, reason: str, parse_errors: Optional[List[str]] = None):
        self.document_path = document_path
        self.reason = reason
        self.parse_errors = parse_errors or []
        
        message = f"Failed to parse document {document_path}: {reason}"
        details = {
            "document_path": document_path,
            "reason": reason,
            "parse_errors": self.parse_errors
        }
        super().__init__(message, details)


class UnsupportedDocumentType(DocumentException):
    """Raised when document type is not supported"""
    
    def __init__(self, document_type: str, supported_types: List[str]):
        self.document_type = document_type
        self.supported_types = supported_types
        
        supported_str = ", ".join(supported_types)
        message = f"Unsupported document type: {document_type}. Supported types: {supported_str}"
        details = {"document_type": document_type, "supported_types": supported_types}
        super().__init__(message, details)


class MissingRequiredField(DocumentException):
    """Raised when required document field is missing"""
    
    def __init__(self, field_name: str, document_type: str):
        self.field_name = field_name
        self.document_type = document_type
        
        message = f"Missing required field '{field_name}' for document type '{document_type}'"
        details = {"field_name": field_name, "document_type": document_type}
        super().__init__(message, details)


class DuplicateDocument(DocumentException):
    """Raised when duplicate document is detected"""
    
    def __init__(self, document_number: str, supplier: str, existing_id: Optional[str] = None):
        self.document_number = document_number
        self.supplier = supplier
        self.existing_id = existing_id
        
        message = f"Duplicate document detected: {document_number} from {supplier}"
        if existing_id:
            message += f" (existing ID: {existing_id})"
            
        details = {
            "document_number": document_number,
            "supplier": supplier,
            "existing_id": existing_id
        }
        super().__init__(message, details)


# OCR-related exceptions
class OCRException(DomainException):
    """Base exception for OCR-related errors"""
    pass


class OCRExtractionFailed(OCRException):
    """Raised when OCR fails to extract text"""
    
    def __init__(self, file_path: str, reason: str):
        self.file_path = file_path
        self.reason = reason
        
        message = f"OCR extraction failed for {file_path}: {reason}"
        details = {"file_path": file_path, "reason": reason}
        super().__init__(message, details)


class InsufficientOCRQuality(OCRException):
    """Raised when OCR quality is too low for processing"""
    
    def __init__(self, file_path: str, confidence_score: float, min_required: float):
        self.file_path = file_path
        self.confidence_score = confidence_score
        self.min_required = min_required
        
        message = f"OCR quality too low for {file_path}: {confidence_score:.2f} < {min_required:.2f}"
        details = {
            "file_path": file_path,
            "confidence_score": confidence_score,
            "min_required": min_required
        }
        super().__init__(message, details)


# Account detection exceptions
class AccountDetectionException(DomainException):
    """Base exception for account detection errors"""
    pass


class NoAccountMatch(AccountDetectionException):
    """Raised when no account category can be determined"""
    
    def __init__(self, item_description: str, supplier: str):
        self.item_description = item_description
        self.supplier = supplier
        
        message = f"No account category found for item '{item_description}' from supplier '{supplier}'"
        details = {"item_description": item_description, "supplier": supplier}
        super().__init__(message, details)


class AmbiguousAccountMatch(AccountDetectionException):
    """Raised when multiple account categories match with equal confidence"""
    
    def __init__(self, item_description: str, matches: List[Dict[str, Any]]):
        self.item_description = item_description
        self.matches = matches
        
        match_str = ", ".join([f"{m['category']} ({m['confidence']:.2f})" for m in matches])
        message = f"Ambiguous account matches for '{item_description}': {match_str}"
        details = {"item_description": item_description, "matches": matches}
        super().__init__(message, details)


# Integration exceptions
class IntegrationException(DomainException):
    """Base exception for external service integration errors"""
    pass


class ZohoAPIException(IntegrationException):
    """Raised when Zoho API operations fail"""
    
    def __init__(self, operation: str, status_code: Optional[int] = None, error_message: Optional[str] = None):
        self.operation = operation
        self.status_code = status_code
        self.error_message = error_message
        
        message = f"Zoho API error during {operation}"
        if status_code:
            message += f" (HTTP {status_code})"
        if error_message:
            message += f": {error_message}"
            
        details = {
            "operation": operation,
            "status_code": status_code,
            "error_message": error_message
        }
        super().__init__(message, details)


class OpenAIException(IntegrationException):
    """Raised when OpenAI API operations fail"""
    
    def __init__(self, operation: str, error_type: str, error_message: str):
        self.operation = operation
        self.error_type = error_type
        self.error_message = error_message
        
        message = f"OpenAI API error during {operation} ({error_type}): {error_message}"
        details = {
            "operation": operation,
            "error_type": error_type,
            "error_message": error_message
        }
        super().__init__(message, details)


class TelegramException(IntegrationException):
    """Raised when Telegram Bot operations fail"""
    
    def __init__(self, operation: str, error_message: str):
        self.operation = operation
        self.error_message = error_message
        
        message = f"Telegram Bot error during {operation}: {error_message}"
        details = {"operation": operation, "error_message": error_message}
        super().__init__(message, details)


# Configuration exceptions
class ConfigurationException(DomainException):
    """Raised when configuration is invalid or missing"""
    
    def __init__(self, config_key: str, reason: str):
        self.config_key = config_key
        self.reason = reason
        
        message = f"Configuration error for '{config_key}': {reason}"
        details = {"config_key": config_key, "reason": reason}
        super().__init__(message, details) 