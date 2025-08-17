"""
FastAPI Application Main
========================

Main FastAPI application with all routers and middleware.
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
import time

from .routers import health_router, documents_router, companies_router, admin_router
from ..infrastructure.config import get_config

# Логи настраиваются центрально; используем модульный логгер
logger = logging.getLogger(__name__)

# Load configuration
config = get_config()

# Create FastAPI app
app = FastAPI(
    title="Invoice Processing API",
    description="Modern API for automated invoice processing with AI-powered categorization",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure properly for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add timing middleware
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """Add processing time to response headers"""
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error": str(exc)}
    )

# Include routers
app.include_router(health_router)
app.include_router(documents_router)
app.include_router(companies_router)
app.include_router(admin_router)

@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "message": "Invoice Processing API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }

@app.on_event("startup")
async def startup_event():
    """Application startup event"""
    logger.info("Starting Invoice Processing API")
    logger.info(f"Environment: {config.environment}")
    logger.info(f"Debug mode: {config.debug}")

@app.on_event("shutdown") 
async def shutdown_event():
    """Application shutdown event"""
    logger.info("Shutting down Invoice Processing API")

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host=config.api.host,
        port=config.api.port,
        reload=config.api.reload,
        workers=config.api.workers
    ) 