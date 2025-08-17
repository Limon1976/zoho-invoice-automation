"""
Account Detector Service
=======================

Service for intelligent accounting category detection using machine learning,
rules, and the existing hybrid account detector.
"""

from typing import Optional, Dict, Any, List
import logging
from dataclasses import dataclass

from ..value_objects import DocumentType

logger = logging.getLogger(__name__)

@dataclass
class AccountMatch:
    """Result of account category matching"""
    category: str
    confidence: float
    source: str  # "hybrid", "rules", "ml", "fallback"
    details: Dict[str, Any]

class AccountDetectorService:
    """Modern account detection service integrating with hybrid detector"""
    
    def __init__(self):
        self.hybrid_detector = None
        
        # Initialize hybrid detector if available
        try:
            from hybrid_account_detector import HybridAccountDetector
            self.hybrid_detector = HybridAccountDetector()
            logger.info("Hybrid account detector loaded successfully")
        except ImportError:
            logger.warning("Hybrid account detector not available, using fallback")
        
        # Fallback categories
        self.fallback_categories = {
            "car": "Vehicle Purchase",
            "vehicle": "Vehicle Purchase", 
            "transport": "Transportation services",
            "software": "Software/IT Services",
            "office": "Office Supplies",
            "consulting": "Consultant Expense",
            "default": "General Expense"
        }
    
    def detect_account(self, text: str, document_type: DocumentType, 
                      supplier_name: str = "", product_description: str = "") -> AccountMatch:
        """
        Detect accounting category for document item
        
        Args:
            text: Full OCR text for context
            document_type: Type of document being processed
            supplier_name: Name of supplier company
            product_description: Description of item/service
            
        Returns:
            AccountMatch with category and confidence
        """
        
        # Try hybrid detector first (best results)
        if self.hybrid_detector:
            try:
                category, confidence, source = self.hybrid_detector.detect_account_hybrid(
                    text=text or product_description,
                    supplier_name=supplier_name,
                    product_description=product_description
                )
                
                return AccountMatch(
                    category=category,
                    confidence=confidence,
                    source=f"hybrid_{source}",
                    details={
                        "hybrid_source": source,
                        "supplier": supplier_name,
                        "description": product_description
                    }
                )
            except Exception as e:
                logger.warning(f"Hybrid detector failed: {e}")
        
        # Fallback to simple keyword matching
        return self._fallback_detection(product_description or text, supplier_name)
    
    def _fallback_detection(self, text: str, supplier_name: str) -> AccountMatch:
        """Simple fallback detection using keywords"""
        if not text:
            return AccountMatch(
                category=self.fallback_categories["default"],
                confidence=0.1,
                source="fallback_empty",
                details={"reason": "no_text"}
            )
        
        text_lower = text.lower()
        
        # Check for keywords
        for keyword, category in self.fallback_categories.items():
            if keyword != "default" and keyword in text_lower:
                return AccountMatch(
                    category=category,
                    confidence=0.6,
                    source="fallback_keyword",
                    details={"matched_keyword": keyword}
                )
        
        # Default category
        return AccountMatch(
            category=self.fallback_categories["default"],
            confidence=0.3,
            source="fallback_default",
            details={"text_preview": text[:50]}
        )
    
    def get_supported_categories(self) -> List[str]:
        """Get list of supported account categories"""
        if self.hybrid_detector:
            try:
                return self.hybrid_detector.get_zoho_accounts()
            except Exception:
                pass
        
        return list(set(self.fallback_categories.values()))
    
    def add_learning_feedback(self, text: str, supplier_name: str, 
                            product_description: str, correct_category: str) -> bool:
        """Add user feedback for learning (if supported)"""
        if self.hybrid_detector:
            try:
                return self.hybrid_detector.add_learning_from_feedback(
                    text=text,
                    supplier_name=supplier_name,
                    product_description=product_description,
                    correct_category=correct_category,
                    source="api_feedback"
                )
            except Exception as e:
                logger.warning(f"Failed to add learning feedback: {e}")
        
        return False 