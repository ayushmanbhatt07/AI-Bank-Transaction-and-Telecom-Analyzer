import pandas as pd
from typing import Set

class Validator:
    def validate_closed_universe(self, reduced_bank_df: pd.DataFrame, selected_customers: Set[str]):
        print("Validating closed customer universe...")
        senders = set(reduced_bank_df["Sender_Customer_ID"].dropna())
        receivers = set(reduced_bank_df["Receiver_Customer_ID"].dropna())
        
        all_present_customers = senders.union(receivers)
        
        # 1. No accidental counterparties
        accidental = all_present_customers - selected_customers
        if accidental:
            raise AssertionError(f"Validation Failed: Found {len(accidental)} accidental counterparties!")
        
        # 2. Every transaction satisfies Sender AND Receiver in Selected
        invalid_mask = ~(reduced_bank_df["Sender_Customer_ID"].isin(selected_customers) & 
                         reduced_bank_df["Receiver_Customer_ID"].isin(selected_customers))
        if invalid_mask.sum() > 0:
            raise AssertionError(f"Validation Failed: {invalid_mask.sum()} transactions violate the AND rule!")
            
        print("[OK] Closed universe validation passed.")

    def validate_anomalies_preserved(self, original_anomaly_gt: pd.DataFrame, reduced_anomaly_gt: pd.DataFrame, scenarios: list):
        print("Validating anomalies preserved...")
        orig_filtered = original_anomaly_gt[original_anomaly_gt["Scenario_Type"].isin(scenarios)]
        orig_txns = set(orig_filtered["Transaction_ID"].dropna())
        
        reduced_txns = set(reduced_anomaly_gt["Transaction_ID"].dropna())
        
        missing = orig_txns - reduced_txns
        if missing:
            raise AssertionError(f"Validation Failed: {len(missing)} anomaly transactions were lost! Examples: {list(missing)[:5]}")
            
        print("[OK] Anomaly preservation validation passed.")

    def validate_relationships(self, reduced_bank: pd.DataFrame, reduced_cdr: pd.DataFrame, reduced_ipdr: pd.DataFrame,
                               reduced_bank_cdr_gt: pd.DataFrame, reduced_cdr_ipdr_gt: pd.DataFrame):
        print("Validating relationship integrity...")
        
        bank_txns = set(reduced_bank["Transaction_ID"].dropna())
        cdr_ids = set(reduced_cdr["CDR_ID"].dropna())
        ipdr_ids = set(reduced_ipdr["IPDR_ID"].dropna())
        
        # Bank -> CDR mapping
        orphan_bc = reduced_bank_cdr_gt[~reduced_bank_cdr_gt["Transaction_ID"].isin(bank_txns)]
        if not orphan_bc.empty:
            raise AssertionError(f"Validation Failed: {len(orphan_bc)} orphan Bank->CDR relationships.")
            
        # CDR -> IPDR mapping
        orphan_ci = reduced_cdr_ipdr_gt[~reduced_cdr_ipdr_gt["CDR_ID"].isin(cdr_ids) & reduced_cdr_ipdr_gt["CDR_ID"].notna()]
        if not orphan_ci.empty:
            raise AssertionError(f"Validation Failed: {len(orphan_ci)} orphan CDR->IPDR relationships.")
            
        print("[OK] Relationship integrity passed.")
