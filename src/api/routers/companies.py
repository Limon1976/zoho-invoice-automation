"""
Companies Router
===============

API endpoints for company management and matching.
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

router = APIRouter(prefix="/companies", tags=["companies"])

class CompanySearchRequest(BaseModel):
    """Request model for company search"""
    name: Optional[str] = None
    vat_number: Optional[str] = None
    country: Optional[str] = None

class CompanyResponse(BaseModel):
    """Response model for company operations"""
    id: str
    name: str
    vat_number: Optional[str] = None
    country: Optional[str] = None
    is_our_company: bool = False

@router.post("/search", response_model=List[CompanyResponse])
async def search_companies(request: CompanySearchRequest) -> List[CompanyResponse]:
    """Search for companies by name, VAT, or country"""
    # TODO: Implement actual company search using CompanyMatcherService
    return [
        CompanyResponse(
            id="company_1",
            name="TaVie Europe OÜ",
            vat_number="EE102288270",
            country="Estonia",
            is_our_company=True
        )
    ]

@router.get("/our-companies", response_model=List[CompanyResponse])
async def get_our_companies() -> List[CompanyResponse]:
    """Get list of our companies"""
    # TODO: Implement actual our companies retrieval
    return [
        CompanyResponse(
            id="our_1",
            name="TaVie Europe OÜ", 
            vat_number="EE102288270",
            country="Estonia",
            is_our_company=True
        ),
        CompanyResponse(
            id="our_2",
            name="Parkentertainment Sp. z o.o.",
            vat_number="PL5272956146", 
            country="Poland",
            is_our_company=True
        )
    ]

@router.get("/{company_id}", response_model=CompanyResponse)
async def get_company(company_id: str) -> CompanyResponse:
    """Get company details by ID"""
    # TODO: Implement actual company retrieval
    return CompanyResponse(
        id=company_id,
        name="Example Company",
        vat_number="EE123456789",
        country="Estonia"
    ) 