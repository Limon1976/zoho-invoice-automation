"""
API Routers
===========

FastAPI routers for different API endpoints.
"""

from .health import router as health_router
from .documents import router as documents_router
from .companies import router as companies_router
from .admin import router as admin_router

__all__ = [
    "health_router",
    "documents_router", 
    "companies_router",
    "admin_router"
] 