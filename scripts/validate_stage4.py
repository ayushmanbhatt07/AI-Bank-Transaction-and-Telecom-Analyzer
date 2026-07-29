import time
import json
import pandas as pd
from collections import Counter
from src.canonical.loader import load_bank, load_cdr, load_ipdr
from src.resolution.registry import IdentityRegistry
from src.resolution.extractor import extract_bank_identities, extract_cdr_identities, extract_ipdr_identities
from src.correlation.config import CorrelationConfig
from src.correlation.bank_cdr import correlate_bank_to_cdr
from src.correlation.cdr_ipdr import correlate_cdr_to_ipdr
from src.correlation.evaluator import evaluate_predictions
from src.correlation.models import MatchStrength

def run_stage4_pipeline(bank_path, cdr_path, ipdr_path, truth_bank_cdr, truth_cdr_ipdr):
    t0 = time.time()
    
    # 1. Load Canonical
    bank_df = pd.read_csv(bank_path)
    cdr_df = pd.read_csv(cdr_path)
    ipdr_df = pd.read_csv(ipdr_path)
    
    bank_txns, _, _ = load_bank(bank_df, bank_path)
    cdr_events, _, _ = load_cdr(cdr_df, cdr_path)
    ipdr_sessions, _, _ = load_ipdr(ipdr_df, ipdr_path)
    
    t1 = time.time()
    
    # 2. Extract and Register (Stage 3)
    registry = IdentityRegistry()
    for txn in bank_txns:
        for obs in extract_bank_identities(txn):
            registry.register(obs)
            
    cdr_dict = {}
    for event in cdr_events:
        cdr_dict[event.cdr_id] = event
        for obs in extract_cdr_identities(event):
            registry.register(obs)
            
    ipdr_dict = {}
    for session in ipdr_sessions:
        ipdr_dict[session.ipdr_id] = session
        for obs in extract_ipdr_identities(session):
            registry.register(obs)
            
    t2 = time.time()
    
    # 3. Correlate (Stage 4)
    config = CorrelationConfig()
    bank_cdr_preds = correlate_bank_to_cdr(bank_txns, cdr_dict, registry, config)
    t3 = time.time()
    
    cdr_ipdr_preds = correlate_cdr_to_ipdr(cdr_events, ipdr_dict, registry, config)
    t4 = time.time()
    
    # 4. Evaluate
    bank_cdr_eval = evaluate_predictions(bank_cdr_preds, truth_bank_cdr, "Transaction_ID", "CDR_ID")
    cdr_ipdr_eval = evaluate_predictions(cdr_ipdr_preds, truth_cdr_ipdr, "CDR_ID", "IPDR_ID")
    t5 = time.time()
    
    # Extra stats
    bc_accepted = [p for p in bank_cdr_preds if p.accepted]
    ci_accepted = [p for p in cdr_ipdr_preds if p.accepted]
    
    report = {
        "timing": {
            "load_canonical": round(t1 - t0, 2),
            "registry_build": round(t2 - t1, 2),
            "correlate_bank_cdr": round(t3 - t2, 2),
            "correlate_cdr_ipdr": round(t4 - t3, 2),
            "evaluation": round(t5 - t4, 2),
            "total": round(t5 - t0, 2)
        },
        "bank_cdr": {
            "transactions_processed": len(bank_txns),
            "predicted_links": len(bc_accepted),
            "unique_cdrs_linked": len({p.target_event_id for p in bc_accepted}),
            "evaluation": bank_cdr_eval
        },
        "cdr_ipdr": {
            "cdrs_processed": len(cdr_events),
            "predicted_links": len(ci_accepted),
            "unique_ipdrs_linked": len({p.target_event_id for p in ci_accepted}),
            "strength_breakdown": dict(Counter(p.match_strength.value for p in ci_accepted)),
            "evaluation": cdr_ipdr_eval
        }
    }
    return report

def main():
    print("Running Clean Dataset...")
    clean = run_stage4_pipeline(
        "data/clean/bank_final.csv",
        "data/clean/cdr_final.csv",
        "data/clean/ipdr_final.csv",
        "data/ground_truth/bank_cdr_ground_truth.csv",
        "data/ground_truth/cdr_ipdr_ground_truth.csv"
    )
    
    with open("scripts/stage4_report_clean.json", "w") as f:
        json.dump(clean, f, indent=2)
        
    print("Clean dataset saved to scripts/stage4_report_clean.json")
    
    print("Running Anomalous Dataset...")
    anomalous = run_stage4_pipeline(
        "data/anomalous/bank_anomaly.csv",
        "data/anomalous/cdr_anomaly.csv",
        "data/anomalous/ipdr_anomaly.csv",
        "data/ground_truth/bank_cdr_ground_truth.csv", 
        "data/ground_truth/bank_cdr_ground_truth.csv_NONEXISTENT"
    )
    
    with open("scripts/stage4_report_anomaly.json", "w") as f:
        json.dump(anomalous, f, indent=2)
    
    final = {"clean": clean, "anomalous": anomalous}
    with open("scripts/stage4_report.json", "w") as f:
        json.dump(final, f, indent=2)
    print("Done")

if __name__ == "__main__":
    main()
