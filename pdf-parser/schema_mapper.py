"""
schema_mapper.py

Handles canonical schema definitions, refined alias dictionaries, 
hierarchical dataset detection (deterministic markers → fuzzy scoring → semantic),
and a production-grade 5-tier semantic mapping system with cached embeddings.
"""

import re
import pandas as pd
import logging
from typing import Dict, List, Optional, Set, Tuple
from rapidfuzz import process, fuzz

logger = logging.getLogger(__name__)

# ==========================================
# CENTRALIZED CONFIGURATION
# ==========================================

PARSER_CONFIG = {
    # Header detection
    "header_scan_limit": 30,
    "header_fuzzy_threshold": 78,
    "header_min_matched_cells": 2,
    "header_min_match_ratio": 0.3,

    # Dataset detection
    "dataset_fuzzy_threshold": 78,
    "dataset_min_score": 100,
    "dataset_ambiguity_margin": 50,

    # Column mapping
    "mapping_fuzzy_threshold": 82,
    "mapping_alias_fuzzy_threshold": 80,
    "mapping_semantic_threshold": 0.62,

    # Table extraction
    "scanned_pdf_char_threshold": 50,
    "repeated_header_fuzzy_threshold": 85,
    "repeated_header_match_ratio": 0.7,
    "min_row_col_count": 2,
}


class UnknownDatasetError(Exception):
    pass


class AmbiguousDatasetError(Exception):
    pass


# ==========================================
# CANONICAL SCHEMAS
# ==========================================

BANK_SCHEMA = [
    "Transaction_ID", "Date", "Timestamp", "Txn_Ref_Number", "Transaction_Mode", 
    "Currency", "Transaction_Amount", "Balance", "Sender_Customer_ID", "Sender_Customer_Name", 
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
# EXPANDED AND REFINED ALIAS DICTIONARIES
# (Duplicates removed, collisions resolved)
# ==========================================

BANK_ALIASES = {
    "Date": [
        "Txn Date", "Transaction Date", "Posting Date", "Date",
        "Booking Date", "Tran Date", "Value Dt", "Tran Dt", "Txn Dt", "Dt",
        "Entry Date", "Post Date", "Effective Date"
    ],
    "Txn_Ref_Number": [
        "UTR Number", "Reference", "Ref No", "Reference Number", "Reference No.",
        "Cheque/Ref No.", "Transaction Reference", "UTR",
        "Cheque Number", "Chq No", "Chq No.", "Cheque No", "Cheque No.",
        "Ref. No.", "Ref No.", "Txn Ref", "Transaction Ref", "Chq.No",
        "Chq/Ref No", "Chq / Ref No", "Reference No", "Cheque/Ref.No.",
        "Chq.No.", "Chq/Ref", "Chq/Ref.", "UTR No", "UTRNo"
    ],
    "Transaction_Amount": [
        "Amount", "Txn Amount", "Transaction Amount", "Transfer Amount",
        "Transaction_Amount_Merged", "Amount(INR)", "Amount (INR)",
        "Amt", "Amt (INR)", "Amount INR", "Txn Amt",
        "Amount (Rs.)", "Amount(Rs.)", "Amt.", "Txn Amt.",
        "Amt(INR)", "Amount in INR", "INR Amount",
        "Amount (Rs)", "Amt (Rs)", "Amt(Rs)",
        "Dr Amount", "Cr Amount", "Debit Amount", "Credit Amount",
        "Withdrawal Amt", "Deposit Amt"
    ],
    "Balance": [
        "Balance", "Balance(INR)", "Balance (INR)", "Closing Balance", 
        "Running Balance", "Bal", "Available Balance", "Book Balance",
        "Balance Amount", "Balance Amt", "Bal(INR)", "Bal (INR)",
        "Balance (Rs.)", "Balance(Rs.)"
    ],
    "Sender_Account_Number": [
        "Account No", "A/C No", "Sender A/C", "Account Number", "Account",
        "Debit Account", "Source Account", "A/c No.", "Acct No", "Acct Number",
        "A/C Number", "Acc No", "Acc Number", "Account No.", "Acct No.",
        "Sender Account", "Sender Account Number", "From Account"
    ],
    "Receiver_Account_Number": [
        "Beneficiary Account", "Receiver Account", "Destination Account",
        "Credit Account", "Beneficiary A/C", "Receiver A/C",
        "Beneficiary A/C No", "Receiver Account Number", "To Account",
        "Credit A/C", "Beneficiary Account Number", "Receiver Acc No"
    ],
    "Transaction_Mode": [
        "Mode", "Particulars", "Description", "Remarks", "Narration",
        "Transaction Details", "Details", "Transaction Particulars",
        "Txn Particulars", "Transaction Description", "Txn Description",
        "Txn Details", "Transaction Narration", "Txn Narration",
        "Transaction Type", "Txn Type", "Mode of Transaction", "Payment Mode"
    ],
    "Sender_Phone_Number": [
        "Mobile", "Phone", "Contact", "Phone Number", "Mobile No", "Mobile Number",
        "Contact Number", "Phone No.", "Sender Mobile", "Sender Phone",
        "Sender Contact", "From Mobile", "From Phone"
    ],
    "Sender_IFSC": [
        "IFSC", "IFSC Code", "Sender IFSC", "IFSC_Code", "Ifsc Code",
        "Sender IFSC Code", "From IFSC"
    ],
    "Transaction_ID": [
        "Transaction ID", "Txn ID", "Transaction No", "Txn No", "Txn Number",
        "Transaction Number", "Voucher No", "Voucher Number",
        "Transaction Ref No", "Ref ID", "Reference ID",
        "Transaction Reference Number", "Txn Ref No"
    ],
    "Timestamp": [
        "Time", "Txn Time", "Transaction Time", "Time Stamp", "Timestamp",
        "Entry Time", "Posting Time", "Transaction Timestamp", "Txn Timestamp",
        "Value Time", "Tran Time"
    ],
    "Currency": [
        "Curr", "Currency", "CCY", "Cur", "Currency Code", "Currency Type",
        "Txn Currency", "Transaction Currency"
    ],
    "Sender_Customer_Name": [
        "Customer Name", "Sender Name", "Account Holder", "Holder Name",
        "Customer", "Sender", "From Name", "Remitter Name", "Account Holder Name",
        "Sender's Name", "Remitter", "Drawer"
    ],
    "Sender_Bank_Name": [
        "Bank", "Bank Name", "Sender Bank", "From Bank", "Remitter Bank",
        "Bank/Branch", "Sender Bank Name",
        "Remitting Bank", "Drawee Bank", "Bank/Branch Name"
    ],
    "Sender_Account_Type": [
        "Account Type", "A/C Type", "Acct Type", "Type of Account", "Scheme",
        "Sender Account Type", "From Account Type", "Account Category"
    ],
    "Receiver_Customer_Name": [
        "Beneficiary Name", "Receiver Name", "To Name", "Beneficiary",
        "Payee Name", "Payee", "Receiver's Name", "Beneficiary's Name",
        "Creditor Name", "Recipient Name"
    ],
    "Receiver_Bank_Name": [
        "Beneficiary Bank", "To Bank", "Receiver Bank", "Payee Bank",
        "Beneficiary Bank Name", "Receiving Bank", "Credit Bank",
        "Recipient Bank", "Destination Bank"
    ],
    "Receiver_Account_Type": [
        "Beneficiary Account Type", "Receiver A/C Type", "To Account Type",
        "Receiver Account Type", "Beneficiary A/C Type", "Credit Account Type"
    ],
    "Receiver_IFSC": [
        "Beneficiary IFSC", "Receiver IFSC", "To IFSC", "Beneficiary IFSC Code",
        "Receiver IFSC Code", "Payee IFSC", "Credit IFSC", "Destination IFSC"
    ],
    "Receiver_Phone_Number": [
        "Beneficiary Mobile", "Receiver Mobile", "To Mobile", "Beneficiary Phone",
        "Receiver Phone", "Payee Phone", "Receiver Phone Number",
        "Beneficiary Phone Number", "Payee Mobile", "Recipient Phone"
    ],
    "Sender_Customer_ID": [
        "Customer ID", "Cust ID", "Sender ID", "Client ID", "CIF", "CIF No",
        "Customer Identification", "Sender Customer ID", "From Customer ID",
        "CIF Number", "Cust ID No"
    ],
    "Receiver_Customer_ID": [
        "Beneficiary ID", "Receiver ID", "To Customer ID", "Beneficiary Cust ID",
        "Receiver Customer ID", "Payee ID", "Beneficiary Customer ID",
        "Recipient ID", "Creditor ID"
    ],
}

CDR_ALIASES = {
    "Call_Date": [
        "Date", "Call Date", "Start Date", "Call Dt", "Date of Call",
        "Record Date", "CDR Date"
    ],
    "Call_Start_Time": [
        "Time", "Start Time", "Call Time", "Call Start Time", "Time of Call",
        "Record Time", "CDR Time"
    ],
    "A_Party_Number": [
        "Calling Number", "Originating Number", "Caller", "A Party", "Calling No",
        "A Number", "Calling Party", "Origin Number", "From Number", "A-Party",
        "Calling No.", "A Party Number", "Origin No", "Caller Number",
        "Originator", "Source Number"
    ],
    "B_Party_Number": [
        "Called Number", "Destination Number", "Receiver", "B Party", "Called No",
        "B Number", "Called Party", "Destination Party", "To Number", "B-Party",
        "Called No.", "B Party Number", "Destination No", "Recipient Number",
        "Dialed Number", "Target Number"
    ],
    "Call_Duration_Seconds": [
        "Duration", "Call Duration", "Time (sec)", "Duration (s)", "Secs",
        "Total Duration", "Call Duration (sec)", "Duration Sec", "Dur (sec)",
        "Duration in Sec", "Call Duration (s)", "Duration (Seconds)", "Duration Seconds",
        "Call Length", "Talk Time"
    ],
    "First_BTS_Location": [
        "Location", "Tower Location", "BTS", "Site ID", "Cell Site", "Address",
        "BTS Location", "Tower Address", "Site Address", "BTS Address",
        "Cell Tower Location", "First BTS Location", "Tower ID"
    ],
    "Call_Type": [
        "Call Type", "Voice/SMS", "Service Type", "Call Nature",
        "Communication Type", "Direction", "Call Direction", "Service",
        "Call Service Type", "Communication Mode"
    ],
    "IMSI": ["IMSI", "IMSI Number", "Subscriber IMSI", "IMSI No", "IMSI Code", "IMSI ID"],
    "IMEI": ["IMEI", "IMEI Number", "Handset IMEI", "Device IMEI", "IMEI No", "IMEI Code", "IMEI ID"],
    "First_Cell_Global_ID": [
        "Cell ID", "CGI", "Cell Global ID", "Global Cell ID", "Cell Identifier",
        "Cell Global Identifier", "First Cell ID", "CGI Code", "Cell ID Code"
    ],
    "Roaming_Network_Circle": [
        "Roaming Circle", "Network Circle", "Circle", "Roaming Network", "Network",
        "Roaming Zone", "Network Zone", "Circle Name", "Roaming Area"
    ],
    "CDR_ID": [
        "CDR ID", "Record ID", "Call Record ID", "Record Number", "CDR Number",
        "Call Record Number", "CDR Record ID", "Record ID Number"
    ],
}

IPDR_ALIASES = {
    "Session_Date": [
        "Date", "Session Date", "Start Date", "Session Dt", "Date of Session",
        "Session Start Date", "IPDR Date", "Record Date"
    ],
    "Session_Start_Time": [
        "Time", "Start Time", "Session Time", "Session Start Time", "Time of Session",
        "Session Timestamp", "IPDR Time", "Session Start Timestamp"
    ],
    "Source_IP_Address": [
        "Src IP", "Source IP", "Origin IP", "Private IP", "Framed IP",
        "Source IP Address", "Client IP", "User IP", "Originating IP",
        "Source IP Addr", "Src IP Address", "Local IP", "NAT IP",
        "Private IP Address", "Framed IP Address"
    ],
    "Destination_IP_Address": [
        "Dest IP", "Destination IP", "Target IP", "Server IP", "Destination IP Address",
        "Dst IP", "Remote IP", "Destination IP Addr", "Dest IP Address",
        "Target IP Address", "External IP", "Server IP Address", "Public IP"
    ],
    "Destination_Port": [
        "Dest Port", "Target Port", "Port", "Server Port", "Destination Port",
        "Dst Port", "Service Port", "Target Port Number", "Destination Port Number",
        "Port Number", "Server Port Number"
    ],
    "Session_Duration_Seconds": [
        "Duration", "Time (sec)", "Uptime", "Session Duration", "Session Duration (sec)",
        "Duration Sec", "Dur (sec)", "Session Duration (s)", "Duration Seconds",
        "Connection Duration", "Session Length"
    ],
    "Subscriber_MSISDN": [
        "MSISDN", "Mobile Number", "Phone Number", "Subscriber Number", "Mobile No",
        "Cellular Number", "MSISDN Number", "Subscriber Mobile", "Subscriber Phone",
        "MSISDN No", "Cell Number"
    ],
    "Subscriber_IMSI": [
        "IMSI", "Subscriber IMSI", "IMSI Number", "IMSI No", "Subscriber IMSI Number",
        "IMSI Code", "IMSI ID", "Subscriber IMSI Code"
    ],
    "Device_IMEI": [
        "IMEI", "Device IMEI", "IMEI Number", "Handset IMEI", "IMEI No",
        "Device IMEI Number", "IMEI Code", "IMEI ID", "Handset IMEI Number"
    ],
    "Cell_Global_ID": [
        "Cell ID", "CGI", "Cell Global ID", "Global Cell ID", "Cell Identifier",
        "Cell Global Identifier", "CGI Code", "Cell ID Code", "Location ID",
        "Cell Location ID", "Global Cell Identifier"
    ],
    "IPDR_ID": [
        "IPDR ID", "Record ID", "Session Record ID", "Record Number", "IPDR Number",
        "IPDR Record ID", "Session ID", "Record ID Number", "IPDR Record Number"
    ],
}

ALIASES = {
    "bank": BANK_ALIASES,
    "cdr": CDR_ALIASES,
    "ipdr": IPDR_ALIASES
}

# ==========================================
# DEBIT/CREDIT COLUMN NAMES
# (Used by merge logic in pdf_parser, NOT mapped to Transaction_Amount)
# ==========================================

DEBIT_CREDIT_COLUMN_NAMES = {
    "debit", "credit", "withdrawal", "deposit", "dr", "cr",
    "debit amount", "credit amount", "withdrawal amount", "deposit amount",
}

# ==========================================
# DETERMINISTIC DATASET MARKERS
# ==========================================

DATASET_MARKERS = {
    "bank": {
        "unique_headers": [
            "utr", "ifsc", "account no", "a/c no", "cheque", "chq",
            "narration", "particulars", "beneficiary", "sender",
            "receiver", "payee", "remitter", "account number",
            "voucher", "balance", "deposit", "withdrawal",
            "transaction amount", "txn amount", "debit", "credit",
        ],
        "patterns": [
            re.compile(r'\b[A-Z]{4}0[A-Z0-9]{6}\b'),  # IFSC code pattern
        ],
    },
    "cdr": {
        "unique_headers": [
            "a party", "b party", "calling number", "called number",
            "a-party", "b-party", "caller", "bts", "cell site",
            "tower location", "roaming", "call duration",
            "call type", "voice/sms", "calling no", "called no",
            "a number", "b number", "origin number", "cdr",
        ],
        "patterns": [
            re.compile(r'\bimsi\b', re.IGNORECASE),
            re.compile(r'\bimei\b', re.IGNORECASE),
        ],
    },
    "ipdr": {
        "unique_headers": [
            "source ip", "dest ip", "destination ip", "src ip", "dst ip",
            "msisdn", "framed ip", "session duration", "destination port",
            "dest port", "server port", "private ip", "nat ip",
            "ipdr", "session date", "subscriber imsi", "device imei",
        ],
        "patterns": [
            re.compile(r'\bip\s*addr', re.IGNORECASE),
        ],
    },
}

# ==========================================
# STATIC CACHE & WEIGHTS
# ==========================================

HIGH_WEIGHT_TERMS = {
    "txn_ref_number", "transaction_id", "sender_account_number", "sender_ifsc", "receiver_account_number",
    "utr number", "reference", "utr", "ifsc code",
    "a_party_number", "b_party_number", "imsi", "imei", "first_cell_global_id",
    "source_ip_address", "destination_ip_address", "destination_port", "subscriber_msisdn"
}

_dataset_terms_cache = {}
_all_valid_terms = set()
_semantic_model = None
_schema_embeddings_cache = {}


def _build_caches():
    """Builds static lookup dictionaries exactly once."""
    if _dataset_terms_cache:
        return
        
    for d_type, schema in SCHEMAS.items():
        terms_map = {}
        for col in schema:
            terms_map[col.lower()] = 3.0 if col.lower() in HIGH_WEIGHT_TERMS else 1.0
            _all_valid_terms.add(col.lower())
            
        for canonical, alias_list in ALIASES[d_type].items():
            weight = 3.0 if canonical.lower() in HIGH_WEIGHT_TERMS else 1.0
            for alias in alias_list:
                terms_map[alias.lower()] = weight
                _all_valid_terms.add(alias.lower())
                
        _dataset_terms_cache[d_type] = terms_map

_build_caches()


def _get_semantic_model():
    """Lazily loads SentenceTransformer model. Returns None if unavailable."""
    global _semantic_model
    if _semantic_model is None:
        try:
            from sentence_transformers import SentenceTransformer
            logger.info("Loading SentenceTransformer model for semantic matching...")
            _semantic_model = SentenceTransformer('all-MiniLM-L6-v2')
        except Exception as e:
            logger.warning(f"SentenceTransformer unavailable, semantic matching disabled: {e}")
            _semantic_model = False  # Sentinel: tried and failed
    return _semantic_model if _semantic_model is not False else None


def get_all_valid_terms() -> Set[str]:
    """Returns the globally cached set of valid canonical and alias terms."""
    return _all_valid_terms


def get_dataset_terms(dataset_type: str) -> Dict[str, float]:
    """Returns the cached mapping of terms to weights for a given dataset type."""
    return _dataset_terms_cache.get(dataset_type, {})


# ==========================================
# HIERARCHICAL DATASET DETECTION
# ==========================================

def _detect_via_deterministic_markers(headers: List[str]) -> Optional[str]:
    """
    Tier 1: Deterministic marker detection.
    Scans headers for unique identifying keywords and regex patterns.
    Returns dataset type if confident, None otherwise.
    """
    clean_headers = [str(h).lower().strip() for h in headers if pd.notna(h) and str(h).strip()]
    header_blob = " ".join(clean_headers)
    
    marker_hits = {}
    
    for dataset, markers in DATASET_MARKERS.items():
        hits = set()
        
        # Check unique header keywords
        for keyword in markers["unique_headers"]:
            for header in clean_headers:
                if keyword in header:
                    hits.add(keyword)
                    break
        
        # Check regex patterns against the blob
        for pattern in markers.get("patterns", []):
            if pattern.search(header_blob):
                hits.add(f"pattern:{pattern.pattern}")
        
        marker_hits[dataset] = hits
        if hits:
            logger.info(f"  Deterministic markers for '{dataset}': {hits}")
    
    # Evaluate: if one type has ≥ 2 hits and others have 0, it's deterministic
    sorted_types = sorted(marker_hits.items(), key=lambda x: len(x[1]), reverse=True)
    best_type, best_hits = sorted_types[0]
    runner_up_type, runner_up_hits = sorted_types[1]
    
    if len(best_hits) >= 2 and len(runner_up_hits) == 0:
        logger.info(f"Deterministic detection: '{best_type}' with {len(best_hits)} unique markers.")
        return best_type
    
    # If best has ≥ 3 and runner-up has ≤ 1, still confident
    if len(best_hits) >= 3 and len(runner_up_hits) <= 1:
        logger.info(
            f"Deterministic detection (strong): '{best_type}' with {len(best_hits)} markers "
            f"vs runner-up '{runner_up_type}' with {len(runner_up_hits)}."
        )
        return best_type
    
    if best_hits:
        logger.info(f"Deterministic detection inconclusive: {dict((k, len(v)) for k, v in marker_hits.items())}")
    
    return None


def _detect_via_fuzzy_scoring(headers: List[str]) -> Tuple[str, float, Dict[str, float]]:
    """
    Tier 2: Weighted fuzzy scoring (improved).
    Returns (best_dataset, best_score, all_scores).
    """
    threshold = PARSER_CONFIG["dataset_fuzzy_threshold"]
    scores = {"bank": 0.0, "cdr": 0.0, "ipdr": 0.0}
    clean_headers = [str(h).lower().strip() for h in headers if pd.notna(h) and str(h).strip()]
    
    for dataset in SCHEMAS.keys():
        terms_dict = _dataset_terms_cache[dataset]
        valid_terms = list(terms_dict.keys())
        
        for header in clean_headers:
            match = process.extractOne(header, valid_terms, scorer=fuzz.WRatio)
            if match and match[1] >= threshold:
                matched_term = match[0]
                confidence_score = match[1]
                weight = terms_dict[matched_term]
                scores[dataset] += (confidence_score * weight)

    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    best_dataset, best_score = sorted_scores[0]
    
    logger.info(f"Fuzzy scoring results: {dict(sorted_scores)}")
    
    return best_dataset, best_score, scores


def detect_dataset_type(headers: List[str]) -> str:
    """
    Hierarchical dataset detection pipeline.
    Tier 1: Deterministic unique markers → Tier 2: Fuzzy scoring → Tier 3: Best guess with warning.
    
    Prioritizes robustness: returns best guess instead of crashing when possible.
    """
    logger.info(f"Detecting dataset type from {len(headers)} headers...")
    
    # Tier 1: Deterministic markers
    det_result = _detect_via_deterministic_markers(headers)
    if det_result:
        return det_result
    
    # Tier 2: Fuzzy scoring
    best_dataset, best_score, scores = _detect_via_fuzzy_scoring(headers)
    
    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    runner_up_dataset, runner_up_score = sorted_scores[1]
    
    min_score = PARSER_CONFIG["dataset_min_score"]
    margin = PARSER_CONFIG["dataset_ambiguity_margin"]
    
    if best_score < min_score:
        raise UnknownDatasetError(
            f"Cannot identify dataset type. All fuzzy scores below minimum threshold ({min_score}). "
            f"Scores: bank={scores['bank']:.0f}, cdr={scores['cdr']:.0f}, ipdr={scores['ipdr']:.0f}. "
            f"Headers seen: {headers[:10]}"
        )
    
    if runner_up_score > 0 and (best_score - runner_up_score) <= margin:
        # Ambiguous, but return best guess with warning instead of crashing
        logger.warning(
            f"Dataset detection is ambiguous: '{best_dataset}' ({best_score:.0f}) vs "
            f"'{runner_up_dataset}' ({runner_up_score:.0f}). Margin={best_score - runner_up_score:.0f} "
            f"< threshold={margin}. Proceeding with '{best_dataset}' as best guess."
        )
    
    logger.info(f"Detected dataset type '{best_dataset.upper()}' with score {best_score:.1f}")
    return best_dataset


# ==========================================
# SEMANTIC MATCHING
# ==========================================

def semantic_match(header: str, candidates: List[str], threshold: float = None) -> Optional[str]:
    """
    Uses cached Sentence-Transformers embeddings to find the most semantically similar field.
    Returns None if model is unavailable or no match exceeds threshold.
    """
    if threshold is None:
        threshold = PARSER_CONFIG["mapping_semantic_threshold"]
    
    if not candidates:
        return None
    
    model = _get_semantic_model()
    if model is None:
        return None
    
    try:
        from sentence_transformers import util
        
        cache_key = tuple(candidates)
        
        if cache_key not in _schema_embeddings_cache:
            _schema_embeddings_cache[cache_key] = model.encode(candidates, convert_to_tensor=True)
            
        candidate_embs = _schema_embeddings_cache[cache_key]
        header_emb = model.encode(header, convert_to_tensor=True)
        
        cos_scores = util.cos_sim(header_emb, candidate_embs)[0]
        best_idx = int(pd.Series(cos_scores.cpu().numpy()).idxmax())
        best_score = cos_scores[best_idx].item()
        
        if best_score >= threshold:
            logger.info(f"  Semantic match: '{header}' → '{candidates[best_idx]}' (score={best_score:.3f})")
            return candidates[best_idx]
        else:
            logger.debug(
                f"  Semantic match below threshold for '{header}': "
                f"best='{candidates[best_idx]}' (score={best_score:.3f} < {threshold})"
            )
    except Exception as e:
        logger.warning(f"Semantic matching failed for '{header}': {e}")
    
    return None


# ==========================================
# 5-TIER COLUMN MAPPING PIPELINE
# ==========================================

def find_best_match(header: str, dataset_type: str, used_canonical: Set[str]) -> Optional[Tuple[str, str]]:
    """
    Executes the production-grade 5-tier matching pipeline for a single header.
    Returns (canonical_field, tier_used) or None.
    
    Tier 1: Exact canonical match
    Tier 2: Exact alias match
    Tier 3: Fuzzy alias match (new)
    Tier 4: Fuzzy canonical match
    Tier 5: Semantic match (last resort)
    """
    header_clean = str(header).strip().lower()
    schema = SCHEMAS[dataset_type]
    aliases = ALIASES.get(dataset_type, {})
    
    available_schema = [c for c in schema if c not in used_canonical]
    if not available_schema:
        return None

    # Tier 1: Exact canonical name match
    for canonical in available_schema:
        if canonical.lower() == header_clean:
            return (canonical, "exact_canonical")

    # Tier 2: Exact alias match
    for canonical, alias_list in aliases.items():
        if canonical in available_schema:
            for alias in alias_list:
                if alias.lower() == header_clean:
                    return (canonical, "exact_alias")

    # Tier 3: Fuzzy alias match (matches misspellings in alias strings)
    alias_fuzzy_threshold = PARSER_CONFIG["mapping_alias_fuzzy_threshold"]
    best_alias_match = None
    best_alias_score = 0
    
    for canonical, alias_list in aliases.items():
        if canonical not in available_schema:
            continue
        alias_lower = [a.lower() for a in alias_list]
        match = process.extractOne(header_clean, alias_lower, scorer=fuzz.WRatio)
        if match and match[1] >= alias_fuzzy_threshold and match[1] > best_alias_score:
            best_alias_score = match[1]
            best_alias_match = canonical
    
    if best_alias_match:
        return (best_alias_match, f"fuzzy_alias(score={best_alias_score:.0f})")

    # Tier 4: Fuzzy canonical name match
    mapping_threshold = PARSER_CONFIG["mapping_fuzzy_threshold"]
    match_result = process.extractOne(header_clean, available_schema, scorer=fuzz.WRatio)
    if match_result:
        matched_str, score, _ = match_result
        if score >= mapping_threshold:
            return (matched_str, f"fuzzy_canonical(score={score:.0f})")

    # Tier 5: Semantic match (contextual similarity — last resort)
    semantic_result = semantic_match(header_clean, available_schema)
    if semantic_result:
        return (semantic_result, "semantic")

    return None


def map_columns(df: pd.DataFrame, dataset_type: str) -> pd.DataFrame:
    """
    Maps the extracted DataFrame columns to the canonical schema.
    Logs every mapping decision with the tier that produced it.
    """
    mapping = {}
    used_canonical = set()
    unmapped = []
    
    logger.info(f"Mapping {len(df.columns)} columns to '{dataset_type}' schema...")
    
    for col in df.columns:
        if pd.isna(col) or 'unnamed' in str(col).lower():
            continue
        
        # Skip standalone debit/credit columns — they should be preserved for merge logic
        col_clean = str(col).strip().lower()
        if col_clean in DEBIT_CREDIT_COLUMN_NAMES:
            logger.info(f"  Preserving debit/credit column '{col}' for merge logic (not mapping to Transaction_Amount)")
            continue
            
        result = find_best_match(col, dataset_type, used_canonical)
        if result:
            canonical, tier = result
            mapping[col] = canonical
            used_canonical.add(canonical)
            logger.info(f"  Column '{col}' → '{canonical}' via {tier}")
        else:
            unmapped.append(col)
            logger.warning(f"  Column '{col}' could not be matched to any canonical field — unmapped")
    
    if unmapped:
        logger.info(f"Unmapped columns ({len(unmapped)}): {unmapped}")
    
    mapped_count = len(mapping)
    total_schema = len(SCHEMAS[dataset_type])
    logger.info(f"Column mapping complete: {mapped_count}/{total_schema} canonical fields populated.")
    
    df_mapped = df.rename(columns=mapping)
    columns_to_keep = [col for col in df_mapped.columns if col in SCHEMAS[dataset_type]]
    return df_mapped[columns_to_keep]


def ensure_schema(df: pd.DataFrame, dataset_type: str) -> pd.DataFrame:
    """Ensures exact canonical schema layout. Fills missing with pd.NA."""
    canonical_schema = SCHEMAS[dataset_type]
    return df.reindex(columns=canonical_schema, fill_value=pd.NA)


def save_csv(df: pd.DataFrame, dataset_type: str, output_dir: str = ".") -> str:
    """Saves DataFrame complying with the strict CSV contract (UTF-8, No Index)."""
    import os
    filename = f"{dataset_type}_parsed.csv"
    output_path = os.path.join(output_dir, filename)
    df.to_csv(output_path, index=False, encoding="utf-8")
    logger.info(f"Successfully saved structured CSV to: {output_path}")
    return output_path