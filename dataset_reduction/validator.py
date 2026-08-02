import pandas as pd
from typing import Set

class Validator:
    def __init__(self, config):
        self.config = config

    def validate(self, 
                 bank_df: pd.DataFrame, cdr_df: pd.DataFrame, ipdr_df: pd.DataFrame,
                 anomaly_gt_df: pd.DataFrame, bank_cdr_gt_df: pd.DataFrame, cdr_ipdr_gt_df: pd.DataFrame,
                 selected_customers: Set[str], original_anomaly_txns: Set[str]):
        """
        Validates referential integrity constraints of the reduced datasets.
        Raises AssertionError if any check fails.
        """
        print("Running validation...")
        
        retained_txns = set(bank_df["Transaction_ID"].dropna())
        retained_cdrs = set(cdr_df["CDR_ID"].dropna())
        retained_ipdrs = set(ipdr_df["IPDR_ID"].dropna())
        
        # 1. Bank Validation
        # All selected anomaly transactions exist.
        missing_anomalies = original_anomaly_txns - retained_txns
        assert len(missing_anomalies) == 0, f"Missing anomaly transactions: {missing_anomalies}"
        
        # Every anomalous customer exists (actually, every selected customer must have at least one transaction)
        retained_customers = set(bank_df["Sender_Customer_ID"].dropna()).union(set(bank_df["Receiver_Customer_ID"].dropna()))
        missing_customers = selected_customers - retained_customers
        assert len(missing_customers) == 0, f"Missing selected customers: {missing_customers}"
        
        # No duplicate Transaction IDs
        assert bank_df["Transaction_ID"].duplicated().sum() == 0, "Duplicate Transaction IDs found in reduced bank dataset"
        
        print("[OK] All anomaly transactions retained")
        print("[OK] No missing customer")
        
        # 2. CDR Validation
        # Every CDR mapping references an existing CDR record
        mapped_cdrs_in_gt = set(bank_cdr_gt_df["CDR_ID"].dropna())
        missing_cdrs = mapped_cdrs_in_gt - retained_cdrs
        assert len(missing_cdrs) == 0, f"Orphan CDR mappings (missing from CDR dataset): {missing_cdrs}"
        
        # No orphan CDR records
        orphan_cdrs = retained_cdrs - mapped_cdrs_in_gt
        assert len(orphan_cdrs) == 0, f"Orphan CDR records (not mapped to any retained transaction): {orphan_cdrs}"
        
        print("[OK] No orphan Bank-CDR mappings")
        
        # 3. IPDR Validation
        # Every IPDR mapping references an existing IPDR record
        mapped_ipdrs_in_gt = set(cdr_ipdr_gt_df["IPDR_ID"].dropna())
        missing_ipdrs = mapped_ipdrs_in_gt - retained_ipdrs
        assert len(missing_ipdrs) == 0, f"Orphan IPDR mappings (missing from IPDR dataset): {missing_ipdrs}"
        
        # No orphan IPDR sessions
        orphan_ipdrs = retained_ipdrs - mapped_ipdrs_in_gt
        assert len(orphan_ipdrs) == 0, f"Orphan IPDR records (not mapped to any retained CDR): {orphan_ipdrs}"
        
        print("[OK] No orphan CDR-IPDR mappings")
        print("[OK] Dataset synchronization successful")
