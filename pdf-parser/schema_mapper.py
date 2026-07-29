"""
schema_mapper.py

Handles canonical schema definitions, alias dictionaries, dataset detection, 
and intelligent semantic mapping using Exact Match, Aliases, RapidFuzz, and Sentence-Transformers.
"""

import pandas as pd
import numpy as np
import os
from typing import Dict, List, Optional, Tuple, Set
from rapidfuzz import process, fuzz
from sentence_transformers import SentenceTransformer, util

# ==========================================
# CANONICAL SCHEMAS
# ==========================================

BANK_SCHEMA = [
    "Transaction_ID", "Date", "Timestamp", "Txn_Ref_Number", "Transaction_Mode", 
    "Currency", "Transaction_Amount", "Sender_Customer_ID", "Sender_Customer_Name", 
    "Sender_Bank_Name", "Sender_Account_Number", "Sender_Account_Type", "Sender_IFSC", 
    "Sender_Phone_Number", "Receiver_Customer_ID", "Receiver_Customer_Name", 
    "Receiver_Bank_Name", "Receiver_Account_Number", "Receiver_Account_Type", 
    "Receiver_IFSC", "Receiver_Phone_Number"
]

CDR_SCHEMA = [
    "CDR_ID", "Call_Date", "Call_Start_Time", "A_Party_Number", "B_Party_Number", 
    "Call_Type", "Call_Duration_Seconds", "IMSI", "IMEI", "First_BTS_Location", 
    "First_Cell_Global_ID", "Roaming_Network_Circle"
]

IPDR_SCHEMA = [
    "IPDR_ID", "Session_Date", "Session_Start_Time", "Subscriber_IMSI", "Subscriber_MSISDN", 
    "Device_IMEI", "Source_IP_Address", "Destination_IP_Address", "Destination_Port", 
    "Cell_Global_ID", "Session_Duration_Seconds"
]

SCHEMAS = {
    "bank": BANK_SCHEMA,
    "cdr": CDR_SCHEMA,
    "ipdr": IPDR_SCHEMA
}

# ==========================================
# ALIAS DICTIONARIES
# ==========================================

BANK_ALIASES = {
    "Date": ["Txn Date", "Transaction Date", "Posting Date", "Value Date", "Date"],
    "Txn_Ref_Number": ["UTR Number", "Reference", "Ref No", "Cheque/Ref No.", "Transaction ID"],
    "Transaction_Amount": ["Amount", "Txn Amount", "Withdrawal", "Deposit", "Dr/Cr", "Debit", "Credit"],
    "Sender_Account_Number": ["Account No", "A/C No", "Sender A/C"],
    "Transaction_Mode": ["Mode", "Type", "Particulars", "Description", "Remarks"],
    "Sender_Phone_Number": ["Mobile", "Phone", "Contact"],
}

CDR_ALIASES = {
    "Call_Date": ["Date", "Call Date"],
    "Call_Start_Time": ["Time", "Start Time"],
    "A_Party_Number": ["Calling Number", "Originating Number", "Caller", "A Party"],
    "B_Party_Number": ["Called Number", "Destination Number", "Receiver", "B Party"],
    "Call_Duration_Seconds": ["Duration", "Call Duration", "Time (sec)"],
    "First_BTS_Location": ["Location", "Tower Location", "BTS", "Site ID"],
}

IPDR_ALIASES = {
    "Session_Date": ["Date", "Session Date"],
    "Session_Start_Time": ["Time", "Start Time"],
    "Source_IP_Address": ["Src IP", "Source IP", "Origin IP"],
    "Destination_IP_Address": ["Dest IP", "Destination IP", "Target IP"],
    "Destination_Port": ["Dest Port", "Target Port", "Port"],
    "Session_Duration_Seconds": ["Duration", "Time (sec)", "Uptime"],
}

ALIASES = {
    "bank": BANK_ALIASES,
    "cdr": CDR_ALIASES,
    "ipdr": IPDR_ALIASES
}

# Global Semantic Model (Lazy Loaded)
_semantic_model = None

def _get_semantic_model() -> SentenceTransformer:
    """Lazy loads the Sentence-Transformer model."""
    global _semantic_model
    if _semantic_model is None:
        _semantic_model = SentenceTransformer('all-MiniLM-L6-v2')
    return _semantic_model

def detect_dataset_type(headers: List[str]) -> str:
    """
    Detects whether the dataset is Bank, CDR, or IPDR by scoring headers against aliases.
    """
    scores = {"bank": 0, "cdr": 0, "ipdr": 0}
    
    clean_headers = [str(h).lower().strip() for h in headers if pd.notna(h)]
    
    for dataset, aliases in ALIASES.items():
        for canonical, alias_list in aliases.items():
            for alias in alias_list:
                if alias.lower() in clean_headers:
                    scores[dataset] += 1
                    
    # Also check against canonical schemas directly
    for dataset, schema in SCHEMAS.items():
        for field in schema:
            if field.lower() in clean_headers:
                scores[dataset] += 1

    return max(scores, key=scores.get)

def semantic_match(header: str, candidates: List[str], threshold: float = 0.55) -> Optional[str]:
    """
    Uses Sentence-Transformers to find the most semantically similar canonical field.
    """
    if not candidates:
        return None
        
    model = _get_semantic_model()
    header_emb = model.encode(header, convert_to_tensor=True)
    candidate_embs = model.encode(candidates, convert_to_tensor=True)
    
    cos_scores = util.cos_sim(header_emb, candidate_embs)[0]
    best_idx = int(pd.Series(cos_scores.cpu().numpy()).idxmax())
    best_score = cos_scores[best_idx].item()
    
    if best_score >= threshold:
        return candidates[best_idx]
    return None

def find_best_match(header: str, dataset_type: str, used_canonical: Set[str]) -> Optional[str]:
    """
    Executes the 4-tier matching pipeline for a single header.
    """
    header_clean = str(header).strip().lower()
    schema = SCHEMAS[dataset_type]
    aliases = ALIASES.get(dataset_type, {})
    
    available_schema = [c for c in schema if c not in used_canonical]
    if not available_schema:
        return None

    # Tier 1: Exact Match (Case-Insensitive)
    for canonical in available_schema:
        if canonical.lower() == header_clean:
            return canonical

    # Tier 2: Alias Match
    for canonical, alias_list in aliases.items():
        if canonical in available_schema:
            for alias in alias_list:
                if alias.lower() == header_clean:
                    return canonical

    # Tier 3: RapidFuzz Match (Syntactic Similarity)
    match_result = process.extractOne(header_clean, available_schema, scorer=fuzz.WRatio)
    if match_result:
        matched_str, score, _ = match_result
        if score >= 85.0:
            return matched_str

    # Tier 4: Semantic Match (Contextual Similarity)
    # Using a slightly lower semantic threshold because acronyms/shorthand map poorly syntactically
    semantic_result = semantic_match(header_clean, available_schema, threshold=0.55)
    if semantic_result:
        return semantic_result

    return None

def map_columns(df: pd.DataFrame, dataset_type: str) -> pd.DataFrame:
    """
    Maps the extracted DataFrame columns to the canonical schema using the 4-tier pipeline.
    """
    mapping = {}
    used_canonical = set()
    
    for col in df.columns:
        if pd.isna(col) or 'unnamed' in str(col).lower():
            continue
            
        best_match = find_best_match(col, dataset_type, used_canonical)
        if best_match:
            mapping[col] = best_match
            used_canonical.add(best_match)
            
    # Rename columns based on mapping
    df_mapped = df.rename(columns=mapping)
    
    # Drop columns that couldn't be mapped to avoid downstream pollution
    columns_to_keep = [col for col in df_mapped.columns if col in SCHEMAS[dataset_type]]
    return df_mapped[columns_to_keep]

def ensure_schema(df: pd.DataFrame, dataset_type: str) -> pd.DataFrame:
    """
    Ensures the exact columns and column order of the canonical schema.
    Fills missing columns with pd.NA.
    """
    canonical_schema = SCHEMAS[dataset_type]
    
    # Assign NA to missing columns and ensure exact ordering
    df = df.reindex(columns=canonical_schema, fill_value=pd.NA)
    
    return df

def save_csv(df: pd.DataFrame, dataset_type: str, output_dir: str = ".") -> str:
    """
    Saves the standardized DataFrame to CSV.
    """
    filename = f"{dataset_type}_parsed.csv"
    output_path = os.path.join(output_dir, filename)
    df.to_csv(output_path, index=False, encoding="utf-8")
    return output_path