import pandas as pd

class GroundTruthFilter:
    def __init__(self, config):
        self.config = config

    def filter_and_save(self, anomaly_gt_df: pd.DataFrame, bank_cdr_gt_df: pd.DataFrame, cdr_ipdr_gt_df: pd.DataFrame, 
                        retained_bank_txns: set, retained_cdrs: set, retained_ipdrs: set):
        
        print("Filtering Ground Truth datasets...")
        
        # 1. Anomaly Ground Truth
        # A transaction is retained only if it's in the reduced bank dataset
        reduced_anomaly_gt = anomaly_gt_df[anomaly_gt_df["Transaction_ID"].isin(retained_bank_txns)].copy()
        reduced_anomaly_gt.to_csv(self.config.ANOMALY_GROUND_TRUTH_REDUCED_FILE, index=False)
        print(f"Saved {self.config.ANOMALY_GROUND_TRUTH_REDUCED_FILE}")
        
        # 2. Bank -> CDR Ground Truth
        # Retain relationship if Bank TX is in reduced bank dataset
        reduced_bank_cdr_gt = bank_cdr_gt_df[bank_cdr_gt_df["Transaction_ID"].isin(retained_bank_txns)].copy()
        reduced_bank_cdr_gt.to_csv(self.config.BANK_CDR_GROUND_TRUTH_REDUCED_FILE, index=False)
        print(f"Saved {self.config.BANK_CDR_GROUND_TRUTH_REDUCED_FILE}")
        
        # 3. CDR -> IPDR Ground Truth
        # Retain relationship if CDR is in reduced cdr dataset
        reduced_cdr_ipdr_gt = cdr_ipdr_gt_df[cdr_ipdr_gt_df["CDR_ID"].isin(retained_cdrs)].copy()
        reduced_cdr_ipdr_gt.to_csv(self.config.CDR_IPDR_GROUND_TRUTH_REDUCED_FILE, index=False)
        print(f"Saved {self.config.CDR_IPDR_GROUND_TRUTH_REDUCED_FILE}")

        return reduced_anomaly_gt, reduced_bank_cdr_gt, reduced_cdr_ipdr_gt
