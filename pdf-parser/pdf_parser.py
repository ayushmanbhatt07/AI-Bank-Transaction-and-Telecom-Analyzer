"""
pdf_parser.py

Handles PDF ingestion, tabular data extraction, data cleaning, and acts as 
the main entry point for the independent PDF parsing module.
"""

import pdfplumber
import pandas as pd
import unicodedata
import os
from typing import List

from schema_mapper import (
    detect_dataset_type, 
    map_columns, 
    ensure_schema, 
    save_csv,
    SCHEMAS
)

def _normalize_text(text: str) -> str:
    """Removes weird unicode characters, newlines, and trims whitespace."""
    if pd.isna(text):
        return text
    text = str(text)
    # Normalize unicode
    text = unicodedata.normalize("NFKD", text)
    # Remove newlines and extra spaces
    text = " ".join(text.replace("\n", " ").split())
    return text.strip()

def _clean_numeric_amounts(df: pd.DataFrame, dataset_type: str) -> pd.DataFrame:
    """
    Removes commas and standardizes numeric fields depending on canonical mappings.
    Must be called AFTER columns have been mapped to canonical schemas.
    """
    numeric_columns = {
        "bank": ["Transaction_Amount", "Sender_Account_Number", "Receiver_Account_Number"],
        "cdr": ["Call_Duration_Seconds", "A_Party_Number", "B_Party_Number", "IMEI", "IMSI"],
        "ipdr": ["Session_Duration_Seconds", "Device_IMEI", "Subscriber_IMSI"]
    }
    
    target_cols = numeric_columns.get(dataset_type, [])
    
    for col in target_cols:
        if col in df.columns:
            # Remove commas from amounts and numbers, but ignore NaNs
            df[col] = df[col].astype(str).str.replace(",", "", regex=False)
            df[col] = df[col].replace({"nan": pd.NA, "<NA>": pd.NA, "None": pd.NA})
            
    return df

def extract_tables_from_pdf(pdf_path: str) -> pd.DataFrame:
    """
    Extracts all tables from a multi-page PDF using pdfplumber and merges them.
    Handles duplicated header rows logically.
    """
    all_rows = []
    
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    # Clean strings immediately
                    cleaned_row = [_normalize_text(cell) for cell in row]
                    all_rows.append(cleaned_row)
                    
    if not all_rows:
        raise ValueError("No tabular data found in the provided PDF.")

    # Convert to DataFrame
    df = pd.DataFrame(all_rows)
    
    # Assume the first row containing valid text is the header
    df.columns = df.iloc[0]
    df = df[1:].reset_index(drop=True)
    
    return df

def _clean_raw_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    General data cleaning prior to schema mapping.
    """
    # Replace empty strings with NA
    df = df.replace(r'^\s*$', pd.NA, regex=True)
    
    # Drop rows where ALL elements are NaN
    df = df.dropna(how='all')
    
    # Drop repeating headers (where row values perfectly match column names)
    if not df.empty:
        header_row = list(df.columns)
        # Create a boolean mask where rows match the header exactly
        mask = df.apply(lambda row: list(row) == header_row, axis=1)
        df = df[~mask]
        
    return df.reset_index(drop=True)

def parse_pdf(pdf_path: str, output_dir: str = ".") -> pd.DataFrame:
    """
    Main pipeline function to process a PDF.
    
    1. Extracts tables
    2. Cleans basic text/whitespace
    3. Detects dataset type
    4. Maps columns semantically to canonical schema
    5. Cleans mapped specific numeric fields
    6. Ensures strict schema enforcement
    7. Saves CSV & returns dataframe
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"The PDF file at {pdf_path} was not found.")
        
    try:
        # 1. Extraction
        raw_df = extract_tables_from_pdf(pdf_path)
        
        # 2. Base Cleaning
        cleaned_df = _clean_raw_dataframe(raw_df)
        
        # 3. Detection
        dataset_type = detect_dataset_type(list(cleaned_df.columns))
        print(f"Detected Dataset Type: {dataset_type.upper()}")
        
        # 4. Semantic Schema Mapping
        mapped_df = map_columns(cleaned_df, dataset_type)
        
        # 5. Targeted Data Cleaning (removing commas from numeric amounts)
        clean_mapped_df = _clean_numeric_amounts(mapped_df, dataset_type)
        
        # 6. Schema Enforcement (Populate missing, strict order)
        final_df = ensure_schema(clean_mapped_df, dataset_type)
        
        # 7. Save to CSV
        output_csv = save_csv(final_df, dataset_type, output_dir)
        print(f"Successfully saved structured data to {output_csv}")
        
        return final_df

    except Exception as e:
        raise RuntimeError(f"Error parsing PDF '{pdf_path}': {str(e)}") from e