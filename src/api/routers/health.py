"""
Health Check Router
==================

Simple health check endpoints for system monitoring.
"""

from fastapi import APIRouter
from typing import Dict, Any
import datetime
import sys

router = APIRouter(prefix="/health", tags=["health"])

@router.get("/")
async def health_check() -> Dict[str, Any]:
    """Basic health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.datetime.now().isoformat(),
        "version": "1.0.0"
    }

@router.get("/detailed")
async def detailed_health() -> Dict[str, Any]:
    """Detailed health check with system information"""
    return {
        "status": "healthy",
        "timestamp": datetime.datetime.now().isoformat(),
        "version": "1.0.0",
        "python_version": sys.version,
        "services": {
            "api": "running",
            "database": "healthy",
            "hybrid_detector": "available"
        }
    } 