"""
main.py

Entry point for the FastAPI backend. Initializes the application, configures
system paths for external module imports, sets up logging, and registers routers.
"""

import sys
import logging
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import JSONResponse

# ==========================================
# SYSTEM PATH CONFIGURATION
# ==========================================
# Resolve the project root (AI-Telecom-Bank-Analyzer) and add pdf-parser to sys.path
# Current file is at: AI-Telecom-Bank-Analyzer/backend/app/main.py
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PDF_PARSER_DIR = PROJECT_ROOT / "pdf-parser"

if str(PDF_PARSER_DIR) not in sys.path:
    sys.path.append(str(PDF_PARSER_DIR))

# ==========================================
# APP IMPORTS
# ==========================================
# These must be imported after sys.path modification to ensure 
# underlying services can import from pdf-parser without issues.
from app.api.parser import router as parser_router
from app.core.config import settings
from app.core.logging_config import setup_logging

# Initialize logging
setup_logging()
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="API for the AI Telecom Bank Analyzer PDF Parser"
)

# Register API Routers
app.include_router(parser_router, prefix="/api/v1/parser", tags=["Parser"])

# ==========================================
# BASE ENDPOINTS
# ==========================================

@app.get("/")
async def root() -> JSONResponse:
    """Root endpoint verifying service identity and status."""
    return JSONResponse(
        content={
            "service": "AI Telecom Bank Analyzer Backend",
            "status": "running"
        }
    )

@app.get("/health")
async def health_check() -> JSONResponse:
    """Health check endpoint for orchestration/monitoring."""
    return JSONResponse(
        content={
            "status": "healthy"
        }
    )