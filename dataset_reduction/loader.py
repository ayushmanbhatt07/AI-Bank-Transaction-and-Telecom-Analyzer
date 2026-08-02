import pandas as pd
from typing import Tuple

class DataLoader:
    def __init__(self, config):
        self.config = config

    def load_all_datasets(self) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Loads Bank, CDR, and IPDR datasets."""
        print(f"Loading datasets...")
        bank_df = pd.read_csv(self.config.BANK_ANOMALOUS_FILE, dtype=str)
        cdr_df = pd.read_csv(self.config.CDR_ANOMALOUS_FILE, dtype=str)
        ipdr_df = pd.read_csv(self.config.IPDR_ANOMALOUS_FILE, dtype=str)
        
        print(f"Loaded Bank Dataset              : {len(bank_df)} rows")
        print(f"Loaded CDR Dataset               : {len(cdr_df)} rows")
        print(f"Loaded IPDR Dataset              : {len(ipdr_df)} rows")
        
        return bank_df, cdr_df, ipdr_df

    def load_ground_truth(self) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Loads all ground truth mapping files."""
        anomaly_gt_df = pd.read_csv(self.config.ANOMALY_GROUND_TRUTH_FILE, dtype=str)
        bank_cdr_gt_df = pd.read_csv(self.config.BANK_CDR_GROUND_TRUTH_FILE, dtype=str)
        cdr_ipdr_gt_df = pd.read_csv(self.config.CDR_IPDR_GROUND_TRUTH_FILE, dtype=str)
        
        return anomaly_gt_df, bank_cdr_gt_df, cdr_ipdr_gt_df
