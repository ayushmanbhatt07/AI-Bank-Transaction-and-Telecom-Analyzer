"""
pdf_parser.py

Handles PDF ingestion, advanced table & text extraction fallback, robust multi-strategy
header detection, amount parsing, and data normalization. Primary entry point for the 
parsing pipeline.
"""

import pdfplumber
import pandas as pd
import unicodedata
import os
import re
import numpy as np
import logging
from typing import List, Optional, Tuple, Dict, Any

from rapidfuzz import fuzz, process

from schema_mapper import (
    detect_dataset_type, 
    map_columns, 
    ensure_schema, 
    save_csv,
    get_all_valid_terms,
    get_dataset_terms,
    semantic_match,
    SCHEMAS,
    PARSER_CONFIG,
    DEBIT_CREDIT_COLUMN_NAMES,
)

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# ==========================================
# CUSTOM EXCEPTIONS
# ==========================================

class ScannedPDFError(Exception):
    """Raised when PDF contains almost no extractable text (likely scanned image)."""
    pass


class PDFExtractionError(Exception):
    """Raised when no tabular data can be extracted from the PDF after all strategies."""
    pass


# ==========================================
# MINIMUM REQUIRED FIELDS (relaxed validation)
# ==========================================

MINIMUM_REQUIRED_FIELDS = {
    "bank": {
        "required": ["Date"],
        "any_of": [
            ["Transaction_Amount", "Transaction_Amount_Merged"],
        ],
    },
    "cdr": {
        "required": ["Call_Date"],
        "any_of": [
            ["A_Party_Number", "B_Party_Number"],
        ],
    },
    "ipdr": {
        "required": ["Session_Date"],
        "any_of": [
            ["Source_IP_Address", "Subscriber_IMSI", "Subscriber_MSISDN", "Device_IMEI"],
        ],
    },
}


# ==========================================
# TEXT NORMALIZATION
# ==========================================

def _normalize_text(text: str) -> str:
    """Removes strange unicode characters, newlines, tabs, and trims whitespace."""
    if pd.isna(text):
        return text
    text = str(text)
    text = unicodedata.normalize("NFKD", text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# ==========================================
# AMOUNT PARSING
# ==========================================

def _parse_amount(val) -> Optional[float]:
    """
    Production-grade amount parser. Handles:
    - Currency symbols: ₹, $, Rs., Rs, INR
    - Thousands separators: 1,234.56 and Indian 1,23,456.78
    - Parenthesized negatives: (1,234.56) → -1234.56
    - Trailing minus: 1,234.56- → -1234.56
    - Leading minus with commas: -1,234.56 → -1234.56
    - DR/CR suffixes: 1234.56 DR → -1234.56, 1234.56 CR → 1234.56
    - Plain numbers
    """
    if pd.isna(val):
        return None
    
    s = str(val).strip()
    if not s:
        return None
    
    # Remove currency symbols
    s = re.sub(r'[₹$]', '', s)
    s = re.sub(r'\bRs\.?\s*', '', s, flags=re.IGNORECASE)
    s = re.sub(r'\bINR\s*', '', s, flags=re.IGNORECASE)
    s = s.strip()
    
    if not s:
        return None
    
    is_negative = False
    
    # Check for parenthesized negatives: (1,234.56)
    paren_match = re.match(r'^\(([\d,. ]+)\)$', s)
    if paren_match:
        s = paren_match.group(1)
        is_negative = True
    
    # Check for DR/CR suffix
    dr_match = re.match(r'^([\d,.\- ]+)\s*(DR|DEBIT|D)\s*$', s, re.IGNORECASE)
    cr_match = re.match(r'^([\d,.\- ]+)\s*(CR|CREDIT|C)\s*$', s, re.IGNORECASE)
    
    if dr_match:
        s = dr_match.group(1)
        is_negative = True
    elif cr_match:
        s = cr_match.group(1)
        is_negative = False
    
    # Check for DR/CR prefix
    dr_prefix = re.match(r'^(DR|DEBIT|D)\s+([\d,.\- ]+)$', s, re.IGNORECASE)
    cr_prefix = re.match(r'^(CR|CREDIT|C)\s+([\d,.\- ]+)$', s, re.IGNORECASE)
    
    if dr_prefix:
        s = dr_prefix.group(2)
        is_negative = True
    elif cr_prefix:
        s = cr_prefix.group(2)
        is_negative = False
    
    # Check for trailing minus: 1234.56-
    if s.endswith('-'):
        s = s[:-1]
        is_negative = True
    
    # Check for leading minus
    if s.startswith('-'):
        s = s[1:]
        is_negative = not is_negative  # Double negative = positive
    
    # Remove remaining non-numeric characters except dots
    s = s.replace(',', '').replace(' ', '')
    
    # Handle multiple dots (Indian format edge case): keep only the last dot
    dot_count = s.count('.')
    if dot_count > 1:
        parts = s.split('.')
        s = ''.join(parts[:-1]) + '.' + parts[-1]
    
    try:
        result = float(s)
        return -abs(result) if is_negative else result
    except (ValueError, TypeError):
        return None


# ==========================================
# PROVIDER DETECTION
# ==========================================

def _detect_provider_metadata(df: pd.DataFrame) -> Optional[str]:
    """Internal mechanism to log potential data providers, zero impact on schema."""
    providers = ["SBI", "HDFC", "ICICI", "Axis", "PNB", "BOB", "Airtel", "Jio", "Vi", "BSNL",
                 "Kotak", "IndusInd", "Yes Bank", "Federal", "Canara", "Union", "IOB", "RBL"]
    text_dump = " ".join(df.head(20).fillna("").astype(str).values.flatten()).upper()
    found = [p for p in providers if p.upper() in text_dump]
    if found:
        provider_str = ', '.join(set(found))
        logger.info(f"Detected Provider Context: {provider_str}")
        return provider_str
    return None


# ==========================================
# TABLE EXTRACTION
# ==========================================

def _extract_via_text_fallback(pdf) -> pd.DataFrame:
    """Fallback mechanism: extracts text, splits by lines, then by delimiters."""
    all_rows = []
    
    for page in pdf.pages:
        text = page.extract_text()
        if not text:
            continue
        for line in text.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            # Skip likely page numbers, footers, headers
            if re.match(r'^\d{1,3}\s*$', line):  # Bare page numbers
                continue
            if re.match(r'^page\s+\d+', line, re.IGNORECASE):
                continue
            
            # Try tab-delimited first
            if '\t' in line:
                row = [cell.strip() for cell in line.split('\t')]
            else:
                # Split by 2 or more spaces
                row = re.split(r'\s{2,}', line)
            
            if len(row) > 1:
                all_rows.append(row)
                
    if not all_rows:
        return pd.DataFrame()
        
    # Pad rows to consistent length
    max_cols = max(len(r) for r in all_rows)
    padded = [r + [pd.NA] * (max_cols - len(r)) for r in all_rows]
    return pd.DataFrame(padded)


def _filter_junk_rows(rows: list, min_cols: int = None) -> list:
    """
    Filters out rows that are likely junk:
    - Too few cells (below min_cols)
    - All cells are empty/whitespace
    """
    if min_cols is None:
        min_cols = PARSER_CONFIG["min_row_col_count"]
    
    filtered = []
    for row in rows:
        # Skip rows that are too short
        non_empty = [cell for cell in row if cell is not None and str(cell).strip()]
        if len(non_empty) < min_cols:
            continue
        filtered.append(row)
    
    return filtered


def extract_tables_from_pdf(pdf_path: str) -> pd.DataFrame:
    """
    Extracts tables across all pages using multiple pdfplumber strategies.
    Falls back to regex-based text extraction if tabular bounds fail.
    Raises ScannedPDFError if the PDF appears to lack textual content.
    """
    all_rows = []
    total_chars = 0
    char_threshold = PARSER_CONFIG["scanned_pdf_char_threshold"]
    
    with pdfplumber.open(pdf_path) as pdf:
        # Pre-check for scanned PDFs
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                total_chars += len(t)
        
        if total_chars < char_threshold:
            raise ScannedPDFError(
                f"PDF contains almost no extractable text ({total_chars} chars). "
                "It is likely a scanned image requiring OCR."
            )
            
        # Strategy 1: Default table extraction
        for page in pdf.pages:
            tables = page.extract_tables()
            if tables:
                for table in tables:
                    for row in table:
                        all_rows.append(row)
        
        if all_rows:
            logger.info(f"Strategy 1 (default tables): extracted {len(all_rows)} rows")
        
        # Strategy 2: lines_strict strategy
        if not all_rows:
            logger.info("Strategy 1 failed. Trying Strategy 2 (lines_strict)...")
            table_settings = {"vertical_strategy": "lines_strict", "horizontal_strategy": "lines_strict"}
            for page in pdf.pages:
                tables = page.extract_tables(table_settings)
                if tables:
                    for table in tables:
                        for row in table:
                            all_rows.append(row)
            if all_rows:
                logger.info(f"Strategy 2 (lines_strict): extracted {len(all_rows)} rows")
        
        # Strategy 3: Text-based strategy
        if not all_rows:
            logger.info("Strategy 2 failed. Trying Strategy 3 (text strategy)...")
            table_settings = {"vertical_strategy": "text", "horizontal_strategy": "text"}
            for page in pdf.pages:
                tables = page.extract_tables(table_settings)
                if tables:
                    for table in tables:
                        for row in table:
                            all_rows.append(row)
            if all_rows:
                logger.info(f"Strategy 3 (text strategy): extracted {len(all_rows)} rows")

        # Strategy 4: Pure text extraction splitting
        if not all_rows:
            logger.info("Strategy 3 failed. Trying Strategy 4 (spatial text fallback)...")
            df = _extract_via_text_fallback(pdf)
            if not df.empty:
                logger.info(f"Strategy 4 (text fallback): extracted {len(df)} rows")
                return df
                
    if not all_rows:
        raise PDFExtractionError("No tabular data could be extracted from the provided PDF after all strategies.")

    # Filter junk rows and pad to uniform width
    all_rows = _filter_junk_rows(all_rows)
    
    if not all_rows:
        raise PDFExtractionError("All extracted rows were filtered as junk (too few cells or empty).")
    
    # Pad rows to uniform width
    max_cols = max(len(r) for r in all_rows)
    padded = [r + [None] * (max_cols - len(r)) for r in all_rows]
    
    return pd.DataFrame(padded)


# ==========================================
# HEADER DETECTION (multi-strategy)
# ==========================================

def _score_row_as_header(row_values: list, all_valid_terms: set) -> Tuple[int, int, float]:
    """
    Scores a candidate row for header-likelihood.
    Returns (matched_cells, total_non_empty_cells, match_ratio).
    """
    fuzzy_threshold = PARSER_CONFIG["header_fuzzy_threshold"]
    matched = 0
    total_non_empty = 0
    
    for cell in row_values:
        if not cell:
            continue
        total_non_empty += 1
        
        clean_cell = re.sub(r'[\[\]\(\)\{\}\:\;]', '', str(cell).lower().strip()).strip()
        if not clean_cell or len(clean_cell) < 2:
            continue
        
        # Check exact match first
        if clean_cell in all_valid_terms:
            matched += 1
            continue
        
        # Check fuzzy match
        match = process.extractOne(clean_cell, list(all_valid_terms), scorer=fuzz.WRatio)
        if match and match[1] >= fuzzy_threshold:
            matched += 1
    
    ratio = matched / total_non_empty if total_non_empty > 0 else 0.0
    return matched, total_non_empty, ratio


def _detect_and_apply_header(df: pd.DataFrame) -> pd.DataFrame:
    """
    Multi-strategy header detection pipeline:
    
    Strategy 1: Ratio-based row scanning — scores each candidate row by the fraction
                of cells that match known schema terms (exact + fuzzy).
    Strategy 2: Check if df.columns (auto-extracted by pdfplumber) are already headers.
    Strategy 3: Semantic fallback on top candidates (last resort, expensive).
    
    Never crashes silently. Falls back to row 0 with a warning if all strategies fail.
    """
    all_valid_terms = get_all_valid_terms()
    limit = min(PARSER_CONFIG["header_scan_limit"], len(df))
    min_matched = PARSER_CONFIG["header_min_matched_cells"]
    min_ratio = PARSER_CONFIG["header_min_match_ratio"]
    
    # Strategy 1: Row-level ratio matching
    candidates = []
    
    for i in range(limit):
        row = df.iloc[i].dropna().astype(str).str.lower().str.strip().tolist()
        matched, total, ratio = _score_row_as_header(row, all_valid_terms)
        candidates.append((i, matched, total, ratio))
    
    # Sort by (ratio DESC, matched DESC)
    candidates.sort(key=lambda x: (x[3], x[1]), reverse=True)
    
    best = candidates[0] if candidates else None
    
    if best and best[1] >= min_matched and best[3] >= min_ratio:
        best_idx = best[0]
        logger.info(
            f"Header detected at row {best_idx} via Strategy 1 (ratio matching): "
            f"{best[1]}/{best[2]} cells matched (ratio={best[3]:.2f})"
        )
        df.columns = df.iloc[best_idx].astype(str).apply(_normalize_text)
        return df.iloc[best_idx + 1:].reset_index(drop=True)
    
    # Strategy 2: Check existing column names
    col_values = [str(c).lower().strip() for c in df.columns if pd.notna(c) and str(c).strip()]
    if col_values:
        col_matched, col_total, col_ratio = _score_row_as_header(col_values, all_valid_terms)
        if col_matched >= min_matched and col_ratio >= min_ratio:
            logger.info(
                f"Header detected in existing column names via Strategy 2: "
                f"{col_matched}/{col_total} matched (ratio={col_ratio:.2f})"
            )
            # Columns are already set, just normalize them
            df.columns = [_normalize_text(str(c)) for c in df.columns]
            return df.reset_index(drop=True)
    
    # Strategy 3: Semantic fallback on top 3 candidates
    logger.info("Strategies 1-2 failed. Attempting Strategy 3 (semantic fallback on top candidates)...")
    
    for candidate in candidates[:3]:
        idx, matched, total, ratio = candidate
        row = df.iloc[idx].dropna().astype(str).str.lower().str.strip().tolist()
        
        sem_matched = matched  # Start with what we already counted
        for cell in row:
            clean_cell = re.sub(r'[\[\]\(\)\{\}\:\;]', '', str(cell).strip()).strip()
            if not clean_cell or len(clean_cell) < 3:
                continue
            # Only check cells not already matched by fuzzy
            if clean_cell not in all_valid_terms:
                sem_result = semantic_match(clean_cell, list(all_valid_terms))
                if sem_result:
                    sem_matched += 1
        
        sem_ratio = sem_matched / total if total > 0 else 0.0
        if sem_matched >= min_matched and sem_ratio >= min_ratio:
            logger.info(
                f"Header detected at row {idx} via Strategy 3 (semantic): "
                f"{sem_matched}/{total} cells matched (ratio={sem_ratio:.2f})"
            )
            df.columns = df.iloc[idx].astype(str).apply(_normalize_text)
            return df.iloc[idx + 1:].reset_index(drop=True)
    
    # Last resort: use row 0 as header with a warning
    logger.warning(
        f"All header detection strategies failed. Best candidate was row {best[0]} "
        f"with {best[1]}/{best[2]} matches (ratio={best[3]:.2f}). "
        f"Falling back to row 0 as header."
    )
    df.columns = df.iloc[0].astype(str).apply(_normalize_text)
    return df.iloc[1:].reset_index(drop=True)


# ==========================================
# REPEATED HEADER REMOVAL
# ==========================================

def _remove_repeated_headers(df: pd.DataFrame) -> pd.DataFrame:
    """
    Removes header rows that repeat on subsequent pages by comparing individual cells 
    against the detected header to avoid monolithic string concatenation flaws.
    """
    header_cells = [str(c).strip().lower() for c in df.columns]
    fuzzy_threshold = PARSER_CONFIG["repeated_header_fuzzy_threshold"]
    match_ratio = PARSER_CONFIG["repeated_header_match_ratio"]
    
    def is_repeated_header(row):
        matches = 0
        valid_cells = 0
        for h_str, r_cell in zip(header_cells, row):
            r_str = str(r_cell).strip().lower()
            if h_str and h_str != 'nan':
                valid_cells += 1
                h_clean = re.sub(r'\W+', '', h_str)
                r_clean = re.sub(r'\W+', '', r_str)
                if r_clean and fuzz.WRatio(h_clean, r_clean) > fuzzy_threshold:
                    matches += 1
                    
        if valid_cells == 0:
            return False
        return (matches / valid_cells) >= match_ratio

    mask = df.apply(is_repeated_header, axis=1)
    removed = mask.sum()
    if removed > 0:
        logger.info(f"Removed {removed} repeated header rows from subsequent pages.")
    return df[~mask].reset_index(drop=True)


# ==========================================
# DEBIT/CREDIT MERGE
# ==========================================

def _merge_debit_credit(df: pd.DataFrame) -> pd.DataFrame:
    """
    Merges isolated Debit/Credit columns or Amount+DR/CR into signed Transaction_Amount.
    Uses the production-grade _parse_amount() for all numeric conversions.
    """
    cols_lower = {str(c).lower().strip(): c for c in df.columns}
    
    # Strategy 1: Separate debit and credit columns
    debit_col, credit_col = None, None
    debit_aliases = ['debit', 'withdrawal', 'dr', 'debit amount', 'withdrawal amt', 'debit amt']
    credit_aliases = ['credit', 'deposit', 'cr', 'credit amount', 'deposit amt', 'credit amt']

    for lower_col, original_col in cols_lower.items():
        if lower_col in debit_aliases or any(fuzz.WRatio(a, lower_col) > 90 for a in debit_aliases):
            debit_col = original_col
        elif lower_col in credit_aliases or any(fuzz.WRatio(a, lower_col) > 90 for a in credit_aliases):
            credit_col = original_col

    if debit_col and credit_col:
        s_debit = df[debit_col].apply(_parse_amount).apply(lambda x: abs(x) if x is not None else None)
        s_credit = df[credit_col].apply(_parse_amount).apply(lambda x: abs(x) if x is not None else None)
        
        s_debit_series = pd.to_numeric(s_debit, errors='coerce')
        s_credit_series = pd.to_numeric(s_credit, errors='coerce')
        
        df['Transaction_Amount_Merged'] = s_credit_series.fillna(0) - s_debit_series.fillna(0)
        # Remove zero amounts (both empty)
        df.loc[(s_debit_series.isna()) & (s_credit_series.isna()), 'Transaction_Amount_Merged'] = pd.NA
        logger.info(f"Merged Debit ('{debit_col}') and Credit ('{credit_col}') columns into signed amount.")
        return df

    # Strategy 2: Single Amount column + DR/CR flag column
    amount_col = None
    drcr_col = None
    for lower_col, original_col in cols_lower.items():
        lower_clean = re.sub(r'[\s\(\)]', '', lower_col)
        if "amount" in lower_clean or "amt" in lower_clean:
            amount_col = original_col
            
        drcr_clean = re.sub(r'[\s\.\(\)\/_-]', '', lower_col)
        if drcr_clean in {"drcr", "crdr"}:
            drcr_col = original_col
        elif fuzz.ratio(lower_col, "dr/cr") > 80 or fuzz.ratio(lower_col, "cr/dr") > 80:
            drcr_col = original_col

    if amount_col and drcr_col:
        def to_signed(row):
            val = _parse_amount(row[amount_col])
            if val is None:
                return pd.NA
            flag = str(row[drcr_col]).strip().upper()
            if flag in {"DR", "D", "DEBIT", "DR."}:
                return -abs(val)
            if flag in {"CR", "C", "CREDIT", "CR."}:
                return abs(val)
            return val

        df['Transaction_Amount_Merged'] = df.apply(to_signed, axis=1)
        logger.info(f"Merged Amount ('{amount_col}') and DR/CR flag ('{drcr_col}') into signed amount.")
        return df
    
    # Strategy 3: Single Amount column with DR/CR embedded in the same cell
    if amount_col:
        df['Transaction_Amount_Merged'] = df[amount_col].apply(_parse_amount)
        logger.info(f"Extracted signed amount from single column ('{amount_col}') using embedded DR/CR detection.")
        return df
    
    # Strategy 4: Check for any column with "amount" in the name
    for lower_col, original_col in cols_lower.items():
        if "amount" in lower_col and original_col not in (debit_col, credit_col):
            df['Transaction_Amount_Merged'] = df[original_col].apply(_parse_amount)
            logger.info(f"Extracted amount from column '{original_col}' (generic amount match).")
            return df

    return df


# ==========================================
# TRANSACTION PARTICULARS PARSING
# ==========================================

def _parse_transaction_particulars(df: pd.DataFrame) -> pd.DataFrame:
    """Parse Transaction Particulars to extract mode, ID, beneficiary, and bank."""
    if "Transaction_Mode" not in df.columns:
        return df
    
    def parse_particulars(text):
        if pd.isna(text):
            return pd.Series([pd.NA, pd.NA, pd.NA, pd.NA])
        
        s = str(text).strip()
        parts = [p.strip() for p in s.split('/') if p.strip()]
        
        mode = pd.NA
        txn_id = pd.NA
        beneficiary = pd.NA
        bank = pd.NA
        
        if not parts:
            return pd.Series([s, pd.NA, pd.NA, pd.NA])
        
        # Detect mode from first part
        mode_keywords = {
            'IMPS': 'IMPS', 'NEFT': 'NEFT', 'RTGS': 'RTGS', 'UPI': 'UPI',
            'POS': 'POS', 'EDC': 'EDC', 'ATM': 'ATM', 'CASH': 'CASH',
            'CHQ': 'CHEQUE', 'CHEQUE': 'CHEQUE', 'DR': 'DEBIT_CARD',
            'CASHBACK': 'CASHBACK', 'INITIAL': 'INITIAL_FUNDING',
            'OPENING': 'OPENING_BALANCE', 'CLOSING': 'CLOSING_BALANCE'
        }
        
        first = parts[0].upper()
        for keyword, canonical in mode_keywords.items():
            if keyword in first:
                mode = canonical
                break
        
        if mode == 'IMPS' and len(parts) >= 2:
            mode = f"IMPS_{parts[1]}" if parts[1] in ('P2A', 'P2P', 'P2M') else 'IMPS'
        
        if mode in ['POS', 'EDC'] and len(parts) >= 2:
            txn_id = parts[-1] if parts[-1].isdigit() else pd.NA
        
        if mode == 'IMPS' and len(parts) >= 3:
            txn_id = parts[2] if parts[2].isdigit() else pd.NA
            for part in parts[3:]:
                if any(b in part.upper() for b in ['BANK', 'IDFC', 'HDFC', 'SBI', 'ICICI', 'AXIS', 'PNB']):
                    bank = part
                    break
            if len(parts) >= 4 and not any(b in parts[3].upper() for b in ['BANK', 'X0']):
                beneficiary = parts[3]
        
        # If no mode detected, keep original as mode
        if pd.isna(mode):
            mode = s
        
        return pd.Series([mode, txn_id, beneficiary, bank])
    
    parsed = df["Transaction_Mode"].apply(parse_particulars)
    parsed.columns = ["Transaction_Mode_Clean", "Transaction_ID_Parsed", "Receiver_Customer_Name_Parsed", "Receiver_Bank_Name_Parsed"]
    
    # We DO NOT overwrite Transaction_Mode, we keep the raw narration
    # df["Transaction_Mode"] = parsed["Transaction_Mode_Clean"]
    
    # Safely set Transaction_ID — create if missing
    if "Transaction_ID" not in df.columns:
        df["Transaction_ID"] = parsed["Transaction_ID_Parsed"]
    else:
        df["Transaction_ID"] = df["Transaction_ID"].fillna(parsed["Transaction_ID_Parsed"])
    
    # Safely set Receiver_Customer_Name — create if missing
    if "Receiver_Customer_Name" not in df.columns:
        df["Receiver_Customer_Name"] = parsed["Receiver_Customer_Name_Parsed"]
    else:
        df["Receiver_Customer_Name"] = df["Receiver_Customer_Name"].fillna(parsed["Receiver_Customer_Name_Parsed"])
    
    # Safely set Receiver_Bank_Name — create if missing
    if "Receiver_Bank_Name" not in df.columns:
        df["Receiver_Bank_Name"] = parsed["Receiver_Bank_Name_Parsed"]
    else:
        df["Receiver_Bank_Name"] = df["Receiver_Bank_Name"].fillna(parsed["Receiver_Bank_Name_Parsed"])
    
    return df


# ==========================================
# SUMMARY ROW REMOVAL
# ==========================================

def _remove_summary_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Remove opening balance, closing balance, and total rows."""
    if "Transaction_Mode" not in df.columns:
        return df
    
    summary_patterns = [
        r'.*OPENING\s+BALANCE.*',
        r'.*CLOSING\s+BALANCE.*',
        r'.*TRANSACTION\s+TOTAL.*',
        r'.*BROUGHT\s+FORWARD.*',
        r'.*CARRIED\s+FORWARD.*',
        r'^\s*TOTAL\s*$',
        r'^\s*GRAND\s+TOTAL\s*$',
        r'^\s*SUB\s*TOTAL\s*$',
        r'^\s*STATEMENT\s+SUMMARY\s*$'
    ]
    
    mask = df["Transaction_Mode"].astype(str).str.strip().str.upper().apply(
        lambda x: not any(re.match(p, x, re.IGNORECASE) for p in summary_patterns)
    )
    
    removed = len(df) - mask.sum()
    if removed > 0:
        logger.info(f"Removed {removed} summary rows (opening/closing balance, totals).")
    
    return df[mask].reset_index(drop=True)


def _remove_secondary_tables(df: pd.DataFrame) -> pd.DataFrame:
    """
    Detects when a new table (like a Charges Summary or Tax Summary) 
    starts at the end of the statement, and drops all rows from that point onward.
    """
    # Keywords that often indicate a secondary table header
    secondary_keywords = {"charge type", "tax amount", "period", "recover date", "sgst", "cgst", "igst"}
    
    drop_index = None
    for idx, row in df.iterrows():
        # Check if the row contains multiple secondary keywords
        row_str = " ".join([str(x).lower() for x in row if pd.notna(x)])
        matches = sum(1 for kw in secondary_keywords if kw in row_str)
        if matches >= 2:
            drop_index = idx
            break
            
    if drop_index is not None:
        logger.info(f"Detected secondary table starting at row {drop_index}. Dropping {len(df) - drop_index} rows.")
        return df.iloc[:drop_index].reset_index(drop=True)
        
    return df


# ==========================================
# DATA CLEANING PIPELINE
# ==========================================

def _clean_raw_dataframe(df: pd.DataFrame) -> Tuple[pd.DataFrame, Optional[str]]:
    """Applies robust, pre-mapping structural normalizations safely."""
    provider = _detect_provider_metadata(df)
    df = _detect_and_apply_header(df)
    df = _remove_repeated_headers(df)
    df = _remove_secondary_tables(df)
    
    # Normalize string format correctly depending on pandas version
    try:
        df = df.map(lambda x: _normalize_text(x) if isinstance(x, str) else x)
    except AttributeError:
        df = df.applymap(lambda x: _normalize_text(x) if isinstance(x, str) else x)
        
    df = df.replace(r'^\s*$', pd.NA, regex=True)
    df = df.dropna(how='all')
    df = df.drop_duplicates()
    df = _merge_debit_credit(df)
    
    return df.reset_index(drop=True), provider


def _clean_mapped_dataframe(df: pd.DataFrame, dataset_type: str) -> pd.DataFrame:
    """
    Cleans mapped numeric and date values securely.
    STRICTLY avoids modifying Identifiers.
    Uses _parse_amount for all monetary/numeric cleaning.
    """
    numeric_columns = {
        "bank": ["Transaction_Amount", "Transaction_Amount_Merged", "Balance"],
        "cdr": ["Call_Duration_Seconds"],
        "ipdr": ["Session_Duration_Seconds"]
    }
    date_columns = {
        "bank": ["Date"],
        "cdr": ["Call_Date"],
        "ipdr": ["Session_Date"]
    }
    
    # Clean monetary/duration fields using _parse_amount
    for col in numeric_columns.get(dataset_type, []):
        if col in df.columns:
            df[col] = df[col].apply(_parse_amount)
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # Normalize canonical date formats consistently
    for col in date_columns.get(dataset_type, []):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce', dayfirst=True).dt.strftime('%Y-%m-%d')
            df[col] = df[col].replace({np.nan: pd.NA, 'NaT': pd.NA})

    # Bank-specific post-processing
    if dataset_type == "bank":
        # Fallback: copy merged amount to Transaction_Amount if latter is empty/missing
        if "Transaction_Amount_Merged" in df.columns:
            if "Transaction_Amount" not in df.columns:
                df["Transaction_Amount"] = df["Transaction_Amount_Merged"]
            else:
                df["Transaction_Amount"] = df["Transaction_Amount"].combine_first(df["Transaction_Amount_Merged"])
        
        df = _parse_transaction_particulars(df)
        df = _remove_summary_rows(df)

    return df


# ==========================================
# FLEXIBLE VALIDATION
# ==========================================

def _validate_schema(df: pd.DataFrame, dataset_type: str) -> List[str]:
    """
    Validates output against minimum required fields.
    Returns a list of warnings (never crashes for optional missing fields).
    Raises ValueError ONLY if the absolute minimum requirements are not met.
    """
    warnings = []
    requirements = MINIMUM_REQUIRED_FIELDS.get(dataset_type)
    
    if requirements is None:
        warnings.append(f"No validation rules defined for dataset type '{dataset_type}'")
        return warnings
    
    if df.empty or df.isna().all(axis=None):
        raise ValueError("Validation Failed: Extracted DataFrame is entirely empty or null.")
    
    # Check required fields (ALL must be present and not fully null)
    for col in requirements.get("required", []):
        if col not in df.columns:
            # Special fallback for Transaction_Amount
            if col == "Transaction_Amount" and "Transaction_Amount_Merged" in df.columns:
                df["Transaction_Amount"] = df["Transaction_Amount_Merged"]
                logger.info("Validation: used Transaction_Amount_Merged as fallback for Transaction_Amount.")
                continue
            raise ValueError(
                f"Validation Failed: Required column '{col}' is missing from output. "
                f"Available columns: {list(df.columns)}"
            )
        if df[col].isna().all():
            raise ValueError(
                f"Validation Failed: Required column '{col}' is present but entirely empty/null."
            )
    
    # Check any_of groups (at least ONE must be present and not fully null)
    for group in requirements.get("any_of", []):
        found_valid = False
        for col in group:
            if col in df.columns and not df[col].isna().all():
                found_valid = True
                break
        
        if not found_valid:
            raise ValueError(
                f"Validation Failed: At least one of {group} must be present and non-empty. "
                f"None found in output columns."
            )
    
    # Log warnings for optional missing fields from the full schema
    full_schema = SCHEMAS.get(dataset_type, [])
    present = [c for c in full_schema if c in df.columns and not df[c].isna().all()]
    missing = [c for c in full_schema if c not in present]
    
    if missing:
        warnings.append(f"Optional columns missing or empty: {missing}")
        logger.info(f"Validation passed with warnings: {len(present)}/{len(full_schema)} columns populated.")
        logger.info(f"Missing optional columns: {missing}")
    else:
        logger.info(f"Validation passed: all {len(full_schema)} canonical columns are populated.")
    
    return warnings


# ==========================================
# PARSING SUMMARY
# ==========================================

def _print_parsing_summary(original_rows: int, retained_rows: int, 
                           dataset_type: str, provider: Optional[str], 
                           mapped_df: pd.DataFrame, final_csv_path: str,
                           warnings: List[str]):
    """Logs an operational summary of the parsing execution."""
    canonical = SCHEMAS[dataset_type]
    present = [c for c in canonical if c in mapped_df.columns and not mapped_df[c].isna().all()]
    missing = [c for c in canonical if c not in present]
    
    logger.info("=== PARSING SUMMARY ===")
    logger.info(f"Dataset Type     : {dataset_type.upper()}")
    logger.info(f"Provider Context : {provider if provider else 'Unknown'}")
    logger.info(f"Rows Extracted   : {original_rows}")
    logger.info(f"Rows Retained    : {retained_rows}")
    logger.info(f"Columns Mapped   : {len(present)}/{len(canonical)}")
    if missing:
        logger.info(f"Missing Columns  : {', '.join(missing)}")
    if warnings:
        logger.info(f"Warnings         : {len(warnings)}")
        for w in warnings:
            logger.info(f"  - {w}")
    logger.info(f"Output Pathway   : {final_csv_path}")
    logger.info("=======================")


# ==========================================
# MAIN PARSING PIPELINE
# ==========================================

def parse_pdf(pdf_path: str, output_dir: str = ".") -> pd.DataFrame:
    """
    Main PDF Parsing Pipeline. Converts unstructured PDFs directly 
    into validated canonical CSVs suitable for downstream logic.
    
    Each stage has individual error handling and recovery attempts.
    Attaches metadata (dataset_type, warnings) via df.attrs for the router.
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"The PDF file at '{pdf_path}' was not found.")
        
    logger.info(f"Initiating parsing for: {os.path.basename(pdf_path)}")
    all_warnings = []
    
    # 1. Block Extraction
    try:
        raw_df = extract_tables_from_pdf(pdf_path)
        original_rows = len(raw_df)
        logger.info(f"Stage 1 (extraction): {original_rows} raw rows extracted.")
    except (ScannedPDFError, PDFExtractionError):
        raise  # These are unrecoverable — propagate with their descriptive messages
    except Exception as e:
        raise PDFExtractionError(f"Unexpected error during table extraction: {e}") from e
    
    # 2. Structural & Header Normalization
    try:
        cleaned_df, provider = _clean_raw_dataframe(raw_df)
        retained_rows = len(cleaned_df)
        logger.info(f"Stage 2 (cleaning): {retained_rows} rows after normalization.")
    except ValueError as e:
        # Header detection failed — try to recover using row 0
        logger.warning(f"Stage 2 header detection error: {e}. Attempting recovery with row 0 as header.")
        all_warnings.append(f"Header detection failed: {e}")
        try:
            raw_df.columns = raw_df.iloc[0].astype(str).apply(_normalize_text)
            cleaned_df = raw_df.iloc[1:].reset_index(drop=True)
            cleaned_df = cleaned_df.replace(r'^\s*$', pd.NA, regex=True)
            cleaned_df = cleaned_df.dropna(how='all')
            cleaned_df = _merge_debit_credit(cleaned_df)
            provider = None
            retained_rows = len(cleaned_df)
        except Exception as recovery_e:
            raise ValueError(f"Header detection and recovery both failed: {e} / {recovery_e}") from e
    except Exception as e:
        raise PDFExtractionError(f"Unexpected error during data cleaning: {e}") from e
    
    # 3. Intelligent Classification
    try:
        dataset_type = detect_dataset_type(list(cleaned_df.columns))
    except Exception as e:
        # Try to classify from data patterns as a fallback
        logger.warning(f"Stage 3 dataset detection error: {e}. Attempting data-pattern fallback...")
        all_warnings.append(f"Dataset detection from headers failed: {e}")
        dataset_type = _detect_dataset_from_data_patterns(cleaned_df)
        if dataset_type is None:
            raise type(e)(
                f"Dataset type could not be determined from headers or data patterns. "
                f"Headers: {list(cleaned_df.columns)[:10]}. Original error: {e}"
            ) from e
        logger.info(f"Data-pattern fallback classified dataset as: {dataset_type}")
    
    # 4. Canonical Projection
    try:
        mapped_df = map_columns(cleaned_df, dataset_type)
    except Exception as e:
        raise ValueError(f"Column mapping failed for dataset type '{dataset_type}': {e}") from e
    
    # 5. Semantic Value Normalization
    try:
        clean_mapped_df = _clean_mapped_dataframe(mapped_df, dataset_type)
    except Exception as e:
        logger.warning(f"Stage 5 value normalization encountered errors: {e}")
        all_warnings.append(f"Value normalization warning: {e}")
        clean_mapped_df = mapped_df  # Use unmapped data if normalization fails
    
    # 6. Schema Enforcement
    try:
        final_df = ensure_schema(clean_mapped_df, dataset_type)
    except Exception as e:
        logger.warning(f"Schema enforcement error: {e}")
        all_warnings.append(f"Schema enforcement warning: {e}")
        final_df = clean_mapped_df
    
    # 7. Flexible Validation
    try:
        validation_warnings = _validate_schema(final_df, dataset_type)
        all_warnings.extend(validation_warnings)
    except ValueError as e:
        logger.error(f"Validation failed: {e}")
        raise
    
    # 8. Dispatch & Summarize
    try:
        out_path = save_csv(final_df, dataset_type, output_dir)
    except Exception as e:
        logger.warning(f"CSV save failed: {e}")
        out_path = "(not saved)"
        all_warnings.append(f"CSV save failed: {e}")
    
    _print_parsing_summary(original_rows, retained_rows, dataset_type, provider, final_df, out_path, all_warnings)
    
    # Attach metadata via df.attrs for the router
    final_df.attrs["dataset_type"] = dataset_type
    final_df.attrs["warnings"] = all_warnings
    final_df.attrs["provider"] = provider
    
    return final_df


# ==========================================
# DATA-PATTERN FALLBACK DETECTOR
# ==========================================

def _detect_dataset_from_data_patterns(df: pd.DataFrame) -> Optional[str]:
    """
    Fallback dataset detection by scanning data values (not headers) for characteristic patterns.
    Used when header-based detection fails entirely.
    """
    text_sample = df.head(50).fillna("").astype(str).values.flatten()
    text_blob = " ".join(text_sample)
    
    scores = {"bank": 0, "cdr": 0, "ipdr": 0}
    
    # Bank patterns: dates + monetary values
    if re.search(r'\d{2}[/-]\d{2}[/-]\d{4}', text_blob):
        scores["bank"] += 1
        scores["cdr"] += 1
        scores["ipdr"] += 1
    
    # Bank-specific: IFSC codes, account numbers, UTR patterns
    if re.search(r'\b[A-Z]{4}0[A-Z0-9]{6}\b', text_blob):
        scores["bank"] += 3
    if re.search(r'\b\d{9,18}\b', text_blob):  # Account number-like
        scores["bank"] += 1
    if re.search(r'₹|Rs\.?|INR', text_blob):
        scores["bank"] += 2
    if re.search(r'\b(NEFT|RTGS|IMPS|UPI|ATM|CHEQUE)\b', text_blob, re.IGNORECASE):
        scores["bank"] += 3
    
    # CDR patterns: phone numbers (10+ digits), IMSI (15 digits), IMEI (15 digits)
    phone_pattern = re.findall(r'\b\d{10,15}\b', text_blob)
    if len(phone_pattern) > 5:
        scores["cdr"] += 2
    if re.search(r'\b\d{15}\b', text_blob):  # IMSI/IMEI-like
        scores["cdr"] += 2
    if re.search(r'\b(voice|sms|incoming|outgoing|call)\b', text_blob, re.IGNORECASE):
        scores["cdr"] += 2
    
    # IPDR patterns: IP addresses
    ip_count = len(re.findall(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', text_blob))
    if ip_count >= 2:
        scores["ipdr"] += 3
    if re.search(r'\b\d{1,5}\b', text_blob) and ip_count > 0:  # Port-like numbers + IPs
        scores["ipdr"] += 1
    
    logger.info(f"Data-pattern detection scores: {scores}")
    
    if max(scores.values()) == 0:
        return None
    
    best = max(scores, key=scores.get)
    if scores[best] >= 2:
        return best
    
    return None