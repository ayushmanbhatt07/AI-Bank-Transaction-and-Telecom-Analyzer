import time
import json
import os
import pandas as pd
import json
import os
from collections import Counter
from src.canonical.loader import load_bank, load_cdr, load_ipdr
from src.resolution.registry import IdentityRegistry
from src.resolution.extractor import extract_bank_identities, extract_cdr_identities, extract_ipdr_identities
from src.models.common import IdentityType

def evaluate_datasets(bank_path, cdr_path, ipdr_path):
    report = {}
    
    t0 = time.time()
    # Stage 2 Loading
    bank_df = pd.read_csv(bank_path)
    cdr_df = pd.read_csv(cdr_path)
    ipdr_df = pd.read_csv(ipdr_path)
    
    bank_txns, bank_err, bank_warn = load_bank(bank_df, bank_path)
    cdr_events, cdr_err, cdr_warn = load_cdr(cdr_df, cdr_path)
    ipdr_sessions, ipdr_err, ipdr_warn = load_ipdr(ipdr_df, ipdr_path)
    t1 = time.time()
    
    report["timing"] = {"canonical_loading_time": round(t1 - t0, 2)}
    report["records"] = {
        "bank_input_rows": len(bank_df),
        "cdr_input_rows": len(cdr_df),
        "ipdr_input_rows": len(ipdr_df),
        "bank_records": len(bank_txns),
        "cdr_records": len(cdr_events),
        "ipdr_records": len(ipdr_sessions),
        "canonical_record_count": len(bank_txns) + len(cdr_events) + len(ipdr_sessions),
        "bank_failures": len(bank_err),
        "cdr_failures": len(cdr_err),
        "ipdr_failures": len(ipdr_err),
        "bank_warnings": bank_warn,
        "cdr_warnings": cdr_warn,
        "ipdr_warnings": ipdr_warn
    }
    
    t2 = time.time()
    # Stage 3 Extraction
    registry = IdentityRegistry()
    for txn in bank_txns:
        for obs in extract_bank_identities(txn):
            registry.register(obs)
    for event in cdr_events:
        for obs in extract_cdr_identities(event):
            registry.register(obs)
    for session in ipdr_sessions:
        for obs in extract_ipdr_identities(session):
            registry.register(obs)
    t3 = time.time()
    
    report["timing"]["identity_extraction_indexing_time"] = round(t3 - t2, 2)
    
    t4 = time.time()
    # Metrics
    report["identities"] = {
        "total_identity_observations": registry.get_total_observations(),
        "unique_customer_ids": registry.get_unique_identities(IdentityType.CUSTOMER_ID.value),
        "unique_bank_accounts": registry.get_unique_identities(IdentityType.BANK_ACCOUNT.value),
        "unique_phones": registry.get_unique_identities(IdentityType.PHONE.value),
        "unique_imsis": registry.get_unique_identities(IdentityType.IMSI.value),
        "unique_imeis": registry.get_unique_identities(IdentityType.IMEI.value),
        "unique_cell_ids": registry.get_unique_identities(IdentityType.CELL_ID.value),
        "unique_ips": registry.get_unique_identities(IdentityType.IP_ADDRESS.value)
    }
    
    # Bridges
    bridges = {}
    
    def calc_bridge(identity_type, source_a, source_b):
        a_count = 0
        b_count = 0
        intersection = 0
        union = 0
        
        for val in registry.get_all_identities_by_type(identity_type):
            sources = registry.get_sources(identity_type, val)
            in_a = source_a in sources
            in_b = source_b in sources
            
            if in_a: a_count += 1
            if in_b: b_count += 1
            if in_a and in_b: intersection += 1
            if in_a or in_b: union += 1
            
        return {
            "source_a_unique": a_count,
            "source_b_unique": b_count,
            "intersection": intersection,
            "union": union,
            "intersect_div_a": intersection / a_count if a_count else 0,
            "intersect_div_b": intersection / b_count if b_count else 0,
            "jaccard_overlap": intersection / union if union else 0
        }
    
    from src.models.common import SourceType
    bridges["bank_cdr_phone"] = calc_bridge(IdentityType.PHONE.value, SourceType.BANK, SourceType.CDR)
    bridges["cdr_ipdr_phone"] = calc_bridge(IdentityType.PHONE.value, SourceType.CDR, SourceType.IPDR)
    bridges["cdr_ipdr_imsi"] = calc_bridge(IdentityType.IMSI.value, SourceType.CDR, SourceType.IPDR)
    bridges["cdr_ipdr_imei"] = calc_bridge(IdentityType.IMEI.value, SourceType.CDR, SourceType.IPDR)
    bridges["cdr_ipdr_cell"] = calc_bridge(IdentityType.CELL_ID.value, SourceType.CDR, SourceType.IPDR)
    
    report["bridges"] = bridges
    
    # Distributions
    distributions = {}
    def calc_dist(identity_type):
        dist = Counter()
        for val in registry.get_all_identities_by_type(identity_type):
            sources = registry.get_sources(identity_type, val)
            key = "_".join(sorted([s.value for s in sources]))
            dist[key] += 1
        return dict(dist)
    
    distributions["PHONE"] = calc_dist(IdentityType.PHONE.value)
    distributions["IMSI"] = calc_dist(IdentityType.IMSI.value)
    distributions["IMEI"] = calc_dist(IdentityType.IMEI.value)
    distributions["CELL_ID"] = calc_dist(IdentityType.CELL_ID.value)
    
    report["distributions"] = distributions
    
    t5 = time.time()
    report["timing"]["summary_reporting_time"] = round(t5 - t4, 2)
    report["timing"]["total_runtime"] = round(t5 - t0, 2)
    
    return report

def main():
    print("Running Clean...")
    clean = evaluate_datasets(
        "data/clean/bank_final.csv",
        "data/clean/cdr_final.csv",
        "data/clean/ipdr_final.csv"
    )
    
    print("Running Anomalous...")
    anomalous = evaluate_datasets(
        "data/anomalous/bank_anomaly.csv",
        "data/anomalous/cdr_anomaly.csv",
        "data/anomalous/ipdr_anomaly.csv"
    )
    
    final = {"clean": clean, "anomalous": anomalous}
    with open("scripts/stage3_report.json", "w") as f:
        json.dump(final, f, indent=2)
    print("Done")

if __name__ == "__main__":
    main()
