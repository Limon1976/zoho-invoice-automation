"""
VAT Validator Service
====================

Advanced VAT number validation service supporting multiple countries
with pattern matching, checksum validation, and country detection.
"""

import re
import logging
from typing import Optional, Dict, List, Tuple, Set
from dataclasses import dataclass

from ..value_objects import VATNumber
from ..exceptions import InvalidVATFormat, VATCountryMismatch

logger = logging.getLogger(__name__)

@dataclass
class VATValidationResult:
    """Result of VAT validation"""
    is_valid: bool
    vat_number: Optional[VATNumber] = None
    country_code: Optional[str] = None
    formatted_number: Optional[str] = None
    validation_errors: Optional[List[str]] = None
    confidence_score: float = 0.0
    
    def __post_init__(self):
        if self.validation_errors is None:
            self.validation_errors = []

class VATValidatorService:
    """Advanced VAT number validation service"""
    
    def __init__(self):
        # EU country VAT patterns with detailed regex
        self.vat_patterns = {
            # EU Countries
            "AT": r"^ATU\d{8}$",           # Austria
            "BE": r"^BE0\d{9}$",           # Belgium  
            "BG": r"^BG\d{9,10}$",         # Bulgaria
            "CY": r"^CY\d{8}[A-Z]$",       # Cyprus
            "CZ": r"^CZ\d{8,10}$",         # Czech Republic
            "DE": r"^DE\d{9}$",            # Germany
            "DK": r"^DK\d{8}$",            # Denmark
            "EE": r"^EE\d{9}$",            # Estonia
            "ES": r"^ES[A-Z0-9]\d{7}[A-Z0-9]$",  # Spain
            "FI": r"^FI\d{8}$",            # Finland
            "FR": r"^FR[A-Z0-9]{2}\d{9}$", # France
            "GB": r"^GB\d{9}$|^GB\d{12}$|^GBGD\d{3}$|^GBHA\d{3}$",  # United Kingdom
            "GR": r"^GR\d{9}$",            # Greece (EL also used)
            "HR": r"^HR\d{11}$",           # Croatia
            "HU": r"^HU\d{8}$",            # Hungary
            "IE": r"^IE\d[A-Z0-9]\d{5}[A-Z]$", # Ireland
            "IT": r"^IT\d{11}$",           # Italy
            "LT": r"^LT\d{9}$|^LT\d{12}$", # Lithuania
            "LU": r"^LU\d{8}$",            # Luxembourg
            "LV": r"^LV\d{11}$",           # Latvia
            "MT": r"^MT\d{8}$",            # Malta
            "NL": r"^NL\d{9}B\d{2}$",      # Netherlands
            "PL": r"^PL\d{10}$",           # Poland
            "PT": r"^PT\d{9}$",            # Portugal
            "RO": r"^RO\d{2,10}$",         # Romania
            "SE": r"^SE\d{12}$",           # Sweden
            "SI": r"^SI\d{8}$",            # Slovenia
            "SK": r"^SK\d{10}$",           # Slovakia
            
            # Non-EU Countries
            "US": r"^\d{2}-\d{7}$",        # United States (EIN)
            "CA": r"^\d{9}RT\d{4}$",       # Canada (GST/HST)
            "AU": r"^\d{11}$",             # Australia (ABN)
            "CH": r"^CHE-\d{9}$",          # Switzerland
            "NO": r"^NO\d{9}MVA$",         # Norway
            "IS": r"^IS\d{5,6}$",          # Iceland
        }
        
        # Common business entity suffixes by country
        self.business_suffixes = {
            "PL": ["SP. Z O.O.", "SP Z OO", "SPÓŁKA Z O.O.", "SP ZOO", "S.A.", "SA"],
            "EE": ["OÜ", "OU", "AS", "SA"],
            "DE": ["GMBH", "GMBH & CO KG", "AG", "E.V."],
            "FR": ["SARL", "SA", "SAS", "EURL"],
            "GB": ["LTD", "LIMITED", "PLC"],
            "US": ["INC", "CORP", "LLC", "LLP"],
            "NL": ["B.V.", "BV", "N.V.", "NV"],
            "IT": ["S.R.L.", "SRL", "S.P.A.", "SPA"],
        }
        
        # Countries that use alternative codes
        self.country_aliases = {
            "EL": "GR",  # Greece uses both EL and GR
            "UK": "GB",  # UK is often used instead of GB
        }

    def validate_vat(self, vat_input: str, expected_country: Optional[str] = None) -> VATValidationResult:
        """
        Comprehensive VAT validation
        
        Args:
            vat_input: VAT number string (with or without country prefix)
            expected_country: Expected country code for validation
            
        Returns:
            VATValidationResult with validation details
        """
        try:
            # Normalize input
            normalized_vat = self._normalize_vat(vat_input)
            
            if not normalized_vat:
                return VATValidationResult(
                    is_valid=False,
                    validation_errors=["Empty or invalid VAT input"]
                )
            
            # Detect country
            detected_country = self._detect_country(normalized_vat)
            
            # Validate format
            format_valid, format_errors = self._validate_format(normalized_vat, detected_country)
            
            # Check country match
            country_match = True
            country_errors = []
            
            if expected_country and detected_country:
                expected_normalized = self._normalize_country_code(expected_country)
                detected_normalized = self._normalize_country_code(detected_country)
                
                if expected_normalized != detected_normalized:
                    country_match = False
                    country_errors.append(
                        f"Country mismatch: expected {expected_normalized}, detected {detected_normalized}"
                    )
            
            # Calculate confidence score
            confidence = self._calculate_confidence(
                format_valid, country_match, normalized_vat, detected_country
            )
            
            # Create VAT number object if valid
            vat_number = None
            if format_valid and country_match:
                try:
                    vat_number = VATNumber(
                        value=normalized_vat,
                        country_code=detected_country
                    )
                except Exception as e:
                    format_valid = False
                    format_errors.append(f"VAT object creation failed: {str(e)}")
            
            # Combine all errors
            all_errors = format_errors + country_errors
            
            return VATValidationResult(
                is_valid=format_valid and country_match,
                vat_number=vat_number,
                country_code=detected_country,
                formatted_number=self._format_vat_display(normalized_vat, detected_country),
                validation_errors=all_errors,
                confidence_score=confidence
            )
            
        except Exception as e:
            logger.error(f"VAT validation error: {e}")
            return VATValidationResult(
                is_valid=False,
                validation_errors=[f"Validation error: {str(e)}"]
            )

    def _normalize_vat(self, vat_input: str) -> str:
        """Normalize VAT input by removing spaces, dashes, dots"""
        if not vat_input:
            return ""
            
        # Remove common separators and convert to uppercase
        normalized = re.sub(r'[\s\-\.\,]', '', vat_input.upper())
        
        # Remove common prefixes that are not country codes
        prefixes_to_remove = ['VAT', 'VATNR', 'VATNUMBER', 'BTWNR', 'BTW', 'NIP', 'EIN']
        for prefix in prefixes_to_remove:
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix):]
                break
        
        return normalized.strip()

    def _detect_country(self, vat_number: str) -> Optional[str]:
        """Detect country from VAT number pattern"""
        if len(vat_number) < 2:
            return None
            
        # Check for explicit country prefix (2 letters at start)
        prefix = vat_number[:2]
        if prefix.isalpha() and prefix in self.vat_patterns:
            return prefix
            
        # Check aliases
        if prefix in self.country_aliases:
            return self.country_aliases[prefix]
            
        # Try to match against all patterns (for numbers without country prefix)
        for country, pattern in self.vat_patterns.items():
            # Try with country prefix
            test_vat = f"{country}{vat_number}"
            if re.match(pattern, test_vat):
                return country
                
        return None

    def _validate_format(self, vat_number: str, country: Optional[str]) -> Tuple[bool, List[str]]:
        """Validate VAT format against country-specific patterns"""
        errors = []
        
        if not country:
            errors.append("Cannot determine country for VAT validation")
            return False, errors
            
        if country not in self.vat_patterns:
            errors.append(f"VAT validation not supported for country: {country}")
            return False, errors
            
        pattern = self.vat_patterns[country]
        
        # Ensure country prefix is present
        if not vat_number.startswith(country):
            vat_number = f"{country}{vat_number}"
            
        if not re.match(pattern, vat_number):
            errors.append(f"VAT format invalid for {country}: {vat_number}")
            return False, errors
            
        # Additional validations for specific countries
        if country == "PL" and not self._validate_polish_nip(vat_number[2:]):
            errors.append("Polish NIP checksum validation failed")
            return False, errors
            
        return True, errors

    def _validate_polish_nip(self, nip: str) -> bool:
        """Validate Polish NIP checksum"""
        if len(nip) != 10 or not nip.isdigit():
            return False
            
        weights = [6, 5, 7, 2, 3, 4, 5, 6, 7]
        checksum = sum(int(nip[i]) * weights[i] for i in range(9)) % 11
        
        return checksum == int(nip[9])

    def _normalize_country_code(self, country: str) -> str:
        """Normalize country code handling aliases"""
        normalized = country.upper().strip()
        return self.country_aliases.get(normalized, normalized)

    def _calculate_confidence(self, format_valid: bool, country_match: bool, 
                            vat_number: str, country: Optional[str]) -> float:
        """Calculate confidence score for VAT validation"""
        score = 0.0
        
        if format_valid:
            score += 0.6
            
        if country_match:
            score += 0.2
            
        if country and country in self.vat_patterns:
            score += 0.1
            
        # Bonus for well-known patterns
        if len(vat_number) >= 8:  # Reasonable length
            score += 0.1
            
        return min(score, 1.0)

    def _format_vat_display(self, vat_number: str, country: Optional[str]) -> str:
        """Format VAT for display with proper spacing"""
        if not country:
            return vat_number
            
        # Ensure country prefix
        if not vat_number.startswith(country):
            vat_number = f"{country}{vat_number}"
            
        # Add formatting for common countries
        if country == "PL" and len(vat_number) == 12:  # PL + 10 digits
            return f"{vat_number[:2]} {vat_number[2:5]}-{vat_number[5:8]}-{vat_number[8:10]}-{vat_number[10:]}"
        elif country == "EE" and len(vat_number) == 11:  # EE + 9 digits
            return f"{vat_number[:2]} {vat_number[2:5]} {vat_number[5:8]} {vat_number[8:]}"
        elif country == "DE" and len(vat_number) == 11:  # DE + 9 digits
            return f"{vat_number[:2]} {vat_number[2:5]} {vat_number[5:8]} {vat_number[8:]}"
            
        return vat_number

    def extract_vat_numbers_from_text(self, text: str) -> List[VATValidationResult]:
        """Extract and validate all VAT numbers found in text"""
        if not text:
            return []
            
        results = []
        
        # Patterns to find VAT numbers in text
        vat_patterns = [
            r'\b(?:VAT|NIP|EIN|BTW|MOMS|MVA|TAX)\s*[:#]?\s*([A-Z]{0,2}\d{8,15}[A-Z0-9]*)\b',
            r'\b([A-Z]{2}\d{8,15}[A-Z0-9]*)\b',  # EU VAT format
            r'\b(\d{2}-\d{7})\b',  # US EIN format
        ]
        
        found_vats = set()
        
        for pattern in vat_patterns:
            matches = re.finditer(pattern, text.upper())
            for match in matches:
                vat_candidate = match.group(1)
                if vat_candidate not in found_vats:
                    found_vats.add(vat_candidate)
                    result = self.validate_vat(vat_candidate)
                    if result.confidence_score > 0.3:  # Only include reasonable matches
                        results.append(result)
        
        # Sort by confidence score (highest first)
        results.sort(key=lambda x: x.confidence_score, reverse=True)
        
        return results

    def add_country_prefix(self, vat_number: str, country: Optional[str] = None) -> str:
        """Add country prefix to VAT number if missing"""
        normalized = self._normalize_vat(vat_number)
        
        if not normalized:
            return vat_number
            
        # If already has country prefix, return as is
        if len(normalized) >= 2 and normalized[:2].isalpha():
            return normalized
            
        # If country is provided, add prefix
        if country:
            country_normalized = self._normalize_country_code(country)
            return f"{country_normalized}{normalized}"
            
        # Try to detect country and add prefix
        detected_country = self._detect_country(normalized)
        if detected_country:
            return f"{detected_country}{normalized}"
            
        return normalized

    def get_supported_countries(self) -> List[str]:
        """Get list of supported country codes"""
        return list(self.vat_patterns.keys())

    def is_country_supported(self, country: str) -> bool:
        """Check if country is supported for VAT validation"""
        normalized = self._normalize_country_code(country)
        return normalized in self.vat_patterns


# Utility functions for backward compatibility
def normalize_vat_number(vat_input: str) -> str:
    """Normalize VAT number (utility function)"""
    validator = VATValidatorService()
    return validator._normalize_vat(vat_input)

def format_vat_display(vat_number: str, country: Optional[str] = None) -> str:
    """Format VAT for display (utility function)"""
    validator = VATValidatorService()
    return validator._format_vat_display(vat_number, country) 