"""
pdf_parser.py

Handles PDF ingestion, robust multi-page header detection, data normalization (including dates 
and numbers), Debit/Credit merging, and acts as the entry point while securely preserving identifiers.
"""

import pdfplumber
import pandas as pd
import unicodedata
import os
import re
import numpy as np
from typing import List, Optional
from rapidfuzz import process, fuzz

from schema_mapper import (
    detect_dataset_type, 
    map_columns, 
    ensure_schema, 
    save_csv,
    SCHEMAS,
    ALIASES
)

def _normalize_text(text: str) -> str:
    """Removes strange unicode characters, newlines, tabs, and trims whitespace."""
    if pd.isna(text):
        return text
    text = str(text)
    text = unicodedata.normalize("NFKD", text)
    # Strip tabs, newlines, multiple spaces
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def _detect_provider_metadata(df: pd.DataFrame):
    """Internal debugging mechanism to log potential data providers, zero impact on schema."""
    providers = ["SBI", "HDFC", "ICICI", "Axis", "PNB", "BOB", "Airtel", "Jio", "Vi", "BSNL"]
    text_dump = " ".join(df.head(20).fillna("").astype(str).values.flatten()).upper()
    found = [p for p in providers if p.upper() in text_dump]
    if found:
        print(f"[METADATA] Detected Provider Context: {', '.join(set(found))}")

def extract_tables_from_pdf(pdf_path: str) -> pd.DataFrame:
    """Extracts tables across all pages using pdfplumber."""
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
                    all_rows.append(row)
                    
    if not all_rows:
        raise ValueError("No tabular data found in the provided PDF.")

    return pd.DataFrame(all_rows)

def _detect_and_apply_header(df: pd.DataFrame) -> pd.DataFrame:
    """
    Scans candidate rows using fuzzy similarity against all known schema concepts.
    Provides robust detection for complex strings like 'Transaction Date (DD/MM/YYYY)'.
    """
    all_valid_terms = set()
    for d_type, schema in SCHEMAS.items():
        all_valid_terms.update(col.lower() for col in schema)
        for alias_list in ALIASES[d_type].values():
            all_valid_terms.update(alias.lower() for alias in alias_list)

    best_idx = 0
    max_score = 0
    limit = min(20, len(df))

    for i in range(limit):
        row = df.iloc[i].dropna().astype(str).str.lower().str.strip()
        score = 0
        for cell in row:
            if not cell:
                continue
            # Score each cell with RapidFuzz
            match = process.extractOne(cell, all_valid_terms, scorer=fuzz.WRatio)
            if match and match[1] >= 80:
                score += match[1]
                
        if score > max_score:
            max_score = score
            best_idx = i

    if max_score < 160: # Requires roughly two decent valid matches
        raise ValueError("Failed to detect a valid table header row in the document.")

    df.columns = df.iloc[best_idx].astype(str).apply(_normalize_text)
    df = df.iloc[best_idx+1:].reset_index(drop=True)
    return df

def _remove_repeated_headers(df: pd.DataFrame) -> pd.DataFrame:
    """Fuzzy removes header rows that repeat on subsequent pages. Ignores formatting differences."""
    # Strip everything except alphanumeric characters for strict structure comparison
    header_str = re.sub(r'\W+', '', "".join([str(c) for c in df.columns]).lower())
    
    def is_repeated_header(row):
        row_str = re.sub(r'\W+', '', "".join(row.dropna().astype(str)).lower())
        if not row_str:
            return False
        return fuzz.WRatio(header_str, row_str) > 90

    mask = df.apply(is_repeated_header, axis=1)
    return df[~mask].reset_index(drop=True)

def _merge_debit_credit(df: pd.DataFrame) -> pd.DataFrame:
    """Merges isolated Debit and Credit columns into a unified Transaction Amount column."""
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
        df['Transaction_Amount_Merged'] = s_credit.combine_first(s_debit)

    return df

def _clean_raw_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Applies robust, pre-mapping structural normalizations safely."""
    _detect_provider_metadata(df)
    df = _detect_and_apply_header(df)
    df = _remove_repeated_headers(df)
    
    # Normalize strings (handling pandas map function deprecation gracefully)
    df = df.applymap(lambda x: _normalize_text(x) if isinstance(x, str) else x)
    
    df = df.replace(r'^\s*$', pd.NA, regex=True)
    df = df.dropna(how='all')
    df = df.drop_duplicates()
    df = _merge_debit_credit(df)
    return df.reset_index(drop=True)

def _clean_mapped_dataframe(df: pd.DataFrame, dataset_type: str) -> pd.DataFrame:
    """
    Cleans mapped numeric and date values.
    STRICTLY avoids modifying Identifiers (Account, IMEI, Phone, Ports, IPs).
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
    
    # 1. Clean monetary/duration fields robustly (Fix Regex bug)
    for col in numeric_columns.get(dataset_type, []):
        if col in df.columns:
            def _clean_num(val):
                if pd.isna(val): return val
                s = str(val).replace(',', '').replace('₹', '').replace('$', '').replace('Rs.', '').replace('Rs', '')
                s = re.sub(r'(?i)\bcr\b|\bdr\b', '', s).strip()
                return s if s else pd.NA
                
            df[col] = df[col].apply(_clean_num)
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # 2. Normalize canonical date formats consistently
    for col in date_columns.get(dataset_type, []):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce', dayfirst=True).dt.strftime('%Y-%m-%d')
            # Retain NA structure instead of string 'NaT'
            df[col] = df[col].replace({np.nan: pd.NA, 'NaT': pd.NA})

    return df

def _validate_schema(df: pd.DataFrame, dataset_type: str):
    """Raises robust validation errors ensuring output structural integrity."""
    critical_fields = {
        "bank": ["Date", "Transaction_Amount"],
        "cdr": ["Call_Date", "A_Party_Number"],
        "ipdr": ["Session_Date", "Source_IP_Address"]
    }
    
    if df.empty or df.isna().all(axis=None):
        raise ValueError("Schema validation failed: Extracted DataFrame is entirely empty/null.")

    for col in critical_fields.get(dataset_type, []):
        if col not in df.columns:
            raise ValueError(f"Schema validation failed: Critical column '{col}' is missing.")
        if df[col].isna().all():
            raise ValueError(f"Schema validation failed: Critical column '{col}' is completely empty.")

def parse_pdf(pdf_path: str, output_dir: str = ".") -> pd.DataFrame:
    """
    Main PDF Parsing Pipeline. Converts unstructured PDFs directly 
    into rigorously validated canonical CSVs.
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"The PDF file at '{pdf_path}' was not found.")
        
    try:
        # 1. Block Extraction
        raw_df = extract_tables_from_pdf(pdf_path)
        
        # 2. Structural & Header Normalization
        cleaned_df = _clean_raw_dataframe(raw_df)
        
        # 3. Intelligent Classification
        dataset_type = detect_dataset_type(list(cleaned_df.columns))
        
        # 4. Canonical Projection (4-Tier mapping)
        mapped_df = map_columns(cleaned_df, dataset_type)
        
        # 5. Semantic Value Normalization (e.g. Dates, Floats)
        clean_mapped_df = _clean_mapped_dataframe(mapped_df, dataset_type)
        
        # 6. Strict Schema Enforcement
        final_df = ensure_schema(clean_mapped_df, dataset_type)
        
        # 7. Quality Sanity Validation
        _validate_schema(final_df, dataset_type)
        
        # 8. Dispatch to Disk
        save_csv(final_df, dataset_type, output_dir)
        
        return final_df

    except Exception as e:
        raise RuntimeError(f"Failed to parse PDF '{pdf_path}': {str(e)}") from e