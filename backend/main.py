"""Main FastAPI application for the AI Telecom Bank Analyzer backend."""

import logging
import sys
from pathlib import Path

# Ensure the backend directory is on sys.path so that `pdf` resolves correctly
_backend_dir = Path(__file__).resolve().parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

# Ensure pdf-parser/ is on sys.path so that `from pdf_parser import parse_pdf` works
_project_root = _backend_dir.parent
_pdf_parser_path = _project_root / "pdf-parser"
if str(_pdf_parser_path) not in sys.path:
    sys.path.insert(0, str(_pdf_parser_path))
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from fastapi import FastAPI
from pdf.config import PROJECT_NAME, VERSION
from pdf.logging_config import get_logger
from pdf.router import router as pdf_router
from investigative_copilot.router import router as copilot_router

# Configure root logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = get_logger(__name__)

app = FastAPI(
    title=PROJECT_NAME,
    version=VERSION,
    description="Backend API for AI Telecom Bank Analyzer and LLM Investigative Co-Pilot.",
)

app.include_router(pdf_router)
app.include_router(copilot_router)



@app.get("/")
def root() -> dict[str, str]:
    """Root endpoint."""
    return {
        "name": PROJECT_NAME,
        "version": VERSION,
        "status": "running",
    }


@app.get("/health")
def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}