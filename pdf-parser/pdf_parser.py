"""
pdf_parser.py

Handles PDF ingestion, advanced table extraction, robust multi-page header detection, 
data normalization, Debit/Credit merging, and acts as the entry point.
"""

import pdfplumber
import pandas as pd
import unicodedata
import os
import re
from typing import List
from rapidfuzz import fuzz

from schema_mapper import (
    detect_dataset_type, 
    map_columns, 
    ensure_schema, 
    save_csv,
    SCHEMAS,
    ALIASES
)

def _normalize_text(text: str) -> str:
    """Removes strange unicode characters, newlines, and trims whitespace."""
    if pd.isna(text):
        return text
    text = str(text)
    text = unicodedata.normalize("NFKD", text)
    text = " ".join(text.replace("\n", " ").split())
    return text.strip()

def extract_tables_from_pdf(pdf_path: str) -> pd.DataFrame:
    """
    Extracts tables across all pages using pdfplumber.
    Falls back to single extract_table if extract_tables fails.
    """
    all_rows = []
    
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            if not tables:
                table = page.extract_table()
                if table:
                    tables = [table]
                    
            for table in tables:
                for row in table:
                    cleaned_row = [_normalize_text(cell) for cell in row]
                    all_rows.append(cleaned_row)
                    
    if not all_rows:
        raise ValueError("No tabular data found in the provided PDF.")

    return pd.DataFrame(all_rows)

def _detect_and_apply_header(df: pd.DataFrame) -> pd.DataFrame:
    """
    Scans the first 20 rows. Scores each based on canonical schemas and aliases.
    The highest-scoring row becomes the header, and rows above it are dropped.
    """
    valid_terms = set()
    for d_type, schema in SCHEMAS.items():
        valid_terms.update(col.lower() for col in schema)
        for alias_list in ALIASES[d_type].values():
            valid_terms.update(alias.lower() for alias in alias_list)

    best_idx = 0
    max_score = -1
    limit = min(20, len(df))

    for i in range(limit):
        row = df.iloc[i].dropna().astype(str).str.lower().str.strip()
        score = sum(1 for cell in row if cell in valid_terms)
        
        if score > max_score:
            max_score = score
            best_idx = i

    if max_score < 2:
        raise ValueError("Failed to detect a valid table header row in the document.")

    df.columns = df.iloc[best_idx].astype(str).str.strip()
    df = df.iloc[best_idx+1:].reset_index(drop=True)
    return df

def _remove_repeated_headers(df: pd.DataFrame) -> pd.DataFrame:
    """Fuzzy removes header rows that repeat on subsequent pages."""
    header_str = " ".join([str(c) for c in df.columns]).lower()
    
    def is_repeated_header(row):
        row_str = " ".join(row.dropna().astype(str)).lower()
        return fuzz.WRatio(header_str, row_str) > 90

    mask = df.apply(is_repeated_header, axis=1)
    return df[~mask].reset_index(drop=True)

def _merge_debit_credit(df: pd.DataFrame) -> pd.DataFrame:
    """
    If a Bank statement contains separate Debit and Credit columns instead of an Amount,
    this merges them into a single column so the schema mapper doesn't drop values.
    """
    cols = [str(c).lower().strip() for c in df.columns]
    
    debit_col, credit_col = None, None
    debit_aliases = ['debit', 'withdrawal', 'dr']
    credit_aliases = ['credit', 'deposit', 'cr']

    for original_col, lower_col in zip(df.columns, cols):
        if lower_col in debit_aliases or any(fuzz.WRatio(a, lower_col) > 90 for a in debit_aliases):
            debit_col = original_col
        elif lower_col in credit_aliases or any(fuzz.WRatio(a, lower_col) > 90 for a in credit_aliases):
            credit_col = original_col

    if debit_col and credit_col:
        s_debit = df[debit_col].replace(r'^\s*$', pd.NA, regex=True)
        s_credit = df[credit_col].replace(r'^\s*$', pd.NA, regex=True)
        # Prioritize Credit, fallback to Debit
        df['Transaction_Amount_Merged'] = s_credit.combine_first(s_debit)

    return df

def _clean_raw_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Applies pre-mapping structure normalizations."""
    df = _detect_and_apply_header(df)
    df = _remove_repeated_headers(df)
    df = df.replace(r'^\s*$', pd.NA, regex=True)
    df = df.dropna(how='all')
    df = df.drop_duplicates()
    df = _merge_debit_credit(df)
    return df.reset_index(drop=True)

def _clean_mapped_dataframe(df: pd.DataFrame, dataset_type: str) -> pd.DataFrame:
    """
    Cleans mapped values. STRICTLY avoids modifying Identifiers (Account, IMEI, Phone).
    Only applies numeric cleaning to known amounts and durations. Validates dates.
    """
    numeric_columns = {
        "bank": ["Transaction_Amount"],
        "cdr": ["Call_Duration_Seconds"],
        "ipdr": ["Session_Duration_Seconds"]
    }
    date_columns = {
        "bank": ["Date"],
        "cdr": ["Call_Date"],
        "ipdr": ["Session_Date"]
    }
    
    # 1. Clean monetary/duration fields
    for col in numeric_columns.get(dataset_type, []):
        if col in df.columns:
            # Strip commas and currency symbols (₹, $, Cr, Dr)
            df[col] = df[col].astype(str).str.replace(r'[,\₹\$\sCrDr]+', '', regex=True)
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # 2. Normalize canonical date formats
    for col in date_columns.get(dataset_type, []):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce', dayfirst=True).dt.strftime('%Y-%m-%d')

    return df

def _validate_schema(df: pd.DataFrame, dataset_type: str):
    """Raises a validation error if critical foundational data is completely missing."""
    critical_fields = {
        "bank": ["Date", "Transaction_Amount"],
        "cdr": ["Call_Date", "A_Party_Number"],
        "ipdr": ["Session_Date", "Source_IP_Address"]
    }
    
    if df.empty:
        raise ValueError("Schema validation failed: The extracted output is completely empty.")

    for col in critical_fields.get(dataset_type, []):
        if col in df.columns and df[col].isna().all():
            raise ValueError(f"Schema validation failed: Critical column '{col}' is missing or entirely empty.")

def parse_pdf(pdf_path: str, output_dir: str = ".") -> pd.DataFrame:
    """
    Main PDF Parsing Pipeline. Converts an unstructured PDF directly 
    into a mathematically rigorous, structurally sound canonical CSV.
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"The PDF file at '{pdf_path}' was not found.")
        
    try:
        # 1. Extract raw tabular blocks
        raw_df = extract_tables_from_pdf(pdf_path)
        
        # 2. Structural & Header Normalization
        cleaned_df = _clean_raw_dataframe(raw_df)
        
        # 3. Intelligent Classification
        dataset_type = detect_dataset_type(list(cleaned_df.columns))
        
        # 4. Canonical Projection (4-Tier matching)
        mapped_df = map_columns(cleaned_df, dataset_type)
        
        # 5. Semantic Value Normalization (e.g. Comma stripping, Date parsing)
        clean_mapped_df = _clean_mapped_dataframe(mapped_df, dataset_type)
        
        # 6. Schema Enforcement & Strict Ordering
        final_df = ensure_schema(clean_mapped_df, dataset_type)
        
        # 7. Final Sanity Validation
        _validate_schema(final_df, dataset_type)
        
        # 8. Dispatch to Disk
        save_csv(final_df, dataset_type, output_dir)
        
        return final_df

    except Exception as e:
        raise RuntimeError(f"Failed to parse PDF '{pdf_path}': {str(e)}") from e