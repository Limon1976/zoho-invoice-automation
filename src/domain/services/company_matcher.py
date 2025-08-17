"""
Company Matcher Service
======================

Service for intelligent company identification and matching using VAT numbers,
names, and fuzzy matching algorithms.
"""

from typing import List, Dict, Optional, Tuple
import logging
from dataclasses import dataclass

from ..entities import Company
from ..value_objects import VATNumber
from .vat_validator import VATValidatorService
from ..exceptions import CompanyNotFound, MultipleCompaniesFound

logger = logging.getLogger(__name__)

@dataclass
class CompanyMatch:
    """Result of company matching"""
    company: Company
    confidence: float
    match_type: str  # "vat_exact", "name_exact", "name_fuzzy", "vat_fuzzy"
    details: Dict[str, str]

class CompanyMatcherService:
    """Intelligent company matching service"""
    
    def __init__(self, vat_validator: VATValidatorService, our_companies: List[Dict[str, str]]):
        self.vat_validator = vat_validator
        self.our_companies = self._create_our_companies(our_companies)
        
    def _create_our_companies(self, companies_config: List[Dict[str, str]]) -> List[Company]:
        """Convert configuration to Company entities"""
        companies = []
        for config in companies_config:
            try:
                vat = None
                if config.get("vat"):
                    vat_result = self.vat_validator.validate_vat(config["vat"])
                    if vat_result.is_valid:
                        vat = vat_result.vat_number
                
                company = Company(
                    name=config["name"],
                    vat_number=vat,
                    country=config.get("country"),
                    is_our_company=True
                )
                companies.append(company)
            except Exception as e:
                logger.warning(f"Failed to create company from config {config}: {e}")
        
        return companies
    
    def find_our_company(self, search_name: str = "", search_vat: str = "") -> Optional[CompanyMatch]:
        """Find our company by name or VAT"""
        matches = self.match_companies(search_name, search_vat, our_companies_only=True)
        return matches[0] if matches else None
    
    def match_companies(self, search_name: str = "", search_vat: str = "", 
                       our_companies_only: bool = False) -> List[CompanyMatch]:
        """Match companies using name and VAT with confidence scoring"""
        companies_to_search = self.our_companies if our_companies_only else self.our_companies
        matches = []
        
        for company in companies_to_search:
            confidence = 0.0
            match_type = "none"
            details = {}
            
            # VAT matching (highest priority)
            if search_vat and company.vat_number:
                if company.matches_vat(search_vat):
                    confidence = 1.0
                    match_type = "vat_exact"
                    details["vat_match"] = "exact"
            
            # Name matching
            if search_name:
                if company.matches_name(search_name, fuzzy=False):
                    if confidence < 0.9:
                        confidence = 0.9
                        match_type = "name_exact"
                        details["name_match"] = "exact"
                elif company.matches_name(search_name, fuzzy=True):
                    if confidence < 0.7:
                        confidence = 0.7
                        match_type = "name_fuzzy"
                        details["name_match"] = "fuzzy"
            
            if confidence > 0.5:  # Minimum threshold
                matches.append(CompanyMatch(
                    company=company,
                    confidence=confidence,
                    match_type=match_type,
                    details=details
                ))
        
        # Sort by confidence (highest first)
        matches.sort(key=lambda x: x.confidence, reverse=True)
        return matches
    
    def extract_companies_from_text(self, text: str) -> List[Company]:
        """Extract company information from OCR text"""
        companies = []
        
        # Extract VAT numbers
        vat_results = self.vat_validator.extract_vat_numbers_from_text(text)
        
        for vat_result in vat_results:
            if vat_result.is_valid and vat_result.vat_number:
                # Try to find company name near VAT
                company_name = self._extract_company_name_near_vat(text, vat_result.formatted_number or "")
                
                company = Company(
                    name=company_name or "Unknown Company",
                    vat_number=vat_result.vat_number,
                    country=vat_result.country_code
                )
                companies.append(company)
        
        return companies
    
    def _extract_company_name_near_vat(self, text: str, vat_number: str) -> Optional[str]:
        """Extract company name from text near VAT number"""
        # Simplified implementation - would be more sophisticated in production
        lines = text.split('\n')
        
        for i, line in enumerate(lines):
            if vat_number in line:
                # Look for company name in previous lines
                for j in range(max(0, i-3), i):
                    potential_name = lines[j].strip()
                    if len(potential_name) > 3 and not any(char.isdigit() for char in potential_name[:5]):
                        return potential_name
                break
        
        return None 