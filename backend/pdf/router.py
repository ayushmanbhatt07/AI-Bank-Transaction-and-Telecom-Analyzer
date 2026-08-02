"""API router for the PDF parser backend module."""

import traceback
import uuid
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, File, HTTPException, UploadFile

from pdf_parser import parse_pdf, ScannedPDFError, PDFExtractionError
from schema_mapper import UnknownDatasetError, AmbiguousDatasetError

from .logging_config import get_logger
from .models import ParserResponse
from .utils import delete_file, save_upload_file, validate_file_extension

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/pdf", tags=["pdf"])


@router.post("/parse", response_model=ParserResponse)
def parse_pdf_endpoint(file: UploadFile = File(...)) -> ParserResponse:
    """Parse an uploaded PDF file and return extracted data.

    The parser automatically detects whether the PDF contains
    Bank, CDR, or IPDR data. Returns structured error responses
    instead of generic HTTP 500.

    Args:
        file: The PDF file to parse.

    Returns:
        ParserResponse containing the extracted data, dataset type, and warnings.

    Raises:
        HTTPException: With appropriate status codes for different failure types:
            - 400: Invalid input (no filename, wrong extension)
            - 404: File not found
            - 422: Unprocessable (scanned PDF, no tables, unknown dataset)
            - 500: Unexpected internal error
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")

    validate_file_extension(file.filename)

    temp_filename = f"{uuid.uuid4().hex}_{file.filename}"
    temp_path: Path | None = None

    try:
        temp_path = save_upload_file(file, temp_filename)

        logger.info(f"Starting PDF parse for {file.filename}")

        # Parse the PDF — the parser now handles validation, DR/CR merge,
        # and dataset detection internally without needing monkey-patches.
        df = parse_pdf(str(temp_path))

        # Extract metadata from df.attrs (set by the parser)
        dataset_type = df.attrs.get("dataset_type", "unknown")
        warnings = df.attrs.get("warnings", [])
        provider = df.attrs.get("provider")

        rows = len(df)
        columns = df.columns.tolist()
        data = df.to_dict(orient="records")

        logger.info(
            f"Successfully parsed PDF {file.filename}: "
            f"{rows} rows, {len(columns)} columns, type={dataset_type.upper()}"
        )

        if warnings:
            logger.info(f"Parsing warnings for {file.filename}: {warnings}")

        return ParserResponse(
            status="success",
            dataset_type=dataset_type.upper(),
            rows=rows,
            columns=columns,
            data=data,
        )

    except HTTPException:
        raise

    except FileNotFoundError as exc:
        logger.error(f"File not found: {exc}")
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from None

    except ScannedPDFError as exc:
        logger.warning(f"Scanned PDF detected for {file.filename}: {exc}")
        raise HTTPException(
            status_code=422,
            detail=f"Scanned PDF: {exc}. Please provide a text-based PDF or use OCR first.",
        ) from None

    except PDFExtractionError as exc:
        logger.warning(f"PDF extraction failed for {file.filename}: {exc}")
        raise HTTPException(
            status_code=422,
            detail=f"Table extraction failed: {exc}",
        ) from None

    except UnknownDatasetError as exc:
        logger.warning(f"Unknown dataset type for {file.filename}: {exc}")
        raise HTTPException(
            status_code=422,
            detail=f"Dataset type could not be determined: {exc}",
        ) from None

    except ValueError as exc:
        logger.warning(f"Validation error for {file.filename}: {exc}")
        raise HTTPException(
            status_code=422,
            detail=f"Parsing validation failed: {exc}",
        ) from None

    except Exception as exc:
        logger.error(f"Unexpected PDF parsing error for {file.filename}: {exc}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=(
                f"An unexpected error occurred while parsing '{file.filename}'. "
                f"Error type: {type(exc).__name__}. Please check logs for details."
            ),
        ) from None

    finally:
        if temp_path:
            delete_file(temp_path)