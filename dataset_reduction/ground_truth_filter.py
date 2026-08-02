import pandas as pd
from typing import Set

class GroundTruthFilter:
    def __init__(self, config):
        self.config = config

    def reduce_ground_truth(self, anomaly_gt_df: pd.DataFrame, bank_cdr_gt_df: pd.DataFrame, cdr_ipdr_gt_df: pd.DataFrame,
                            retained_txns: Set[str], retained_cdrs: Set[str], retained_ipdrs: Set[str]):
        """
        Reduces ground truth files to contain only references that exist in the reduced datasets.
        """
        # Anomaly Ground Truth: keep only rows where Transaction_ID is retained.
        reduced_anomaly_gt = anomaly_gt_df[anomaly_gt_df["Transaction_ID"].isin(retained_txns)].copy()
        
        # Bank-CDR Ground Truth:
        # Keep if Transaction_ID is retained.
        reduced_bank_cdr_gt = bank_cdr_gt_df[bank_cdr_gt_df["Transaction_ID"].isin(retained_txns)].copy()
        
        # If CDR_ID is populated, it MUST be in retained_cdrs (to avoid dangling mappings).
        # We can drop rows that have a CDR_ID but it's not in retained_cdrs, although by definition 
        # our cdr_filter.py retains ALL CDR_IDs linked to retained_txns. So this should just be an integrity check.
        # But to be completely safe:
        mask = reduced_bank_cdr_gt["CDR_ID"].isna() | reduced_bank_cdr_gt["CDR_ID"].isin(retained_cdrs)
        reduced_bank_cdr_gt = reduced_bank_cdr_gt[mask].copy()

        # CDR-IPDR Ground Truth:
        # Keep if CDR_ID is retained.
        reduced_cdr_ipdr_gt = cdr_ipdr_gt_df[cdr_ipdr_gt_df["CDR_ID"].isin(retained_cdrs)].copy()
        
        # If IPDR_ID is populated, it MUST be in retained_ipdrs.
        mask2 = reduced_cdr_ipdr_gt["IPDR_ID"].isna() | reduced_cdr_ipdr_gt["IPDR_ID"].isin(retained_ipdrs)
        reduced_cdr_ipdr_gt = reduced_cdr_ipdr_gt[mask2].copy()
        
        return reduced_anomaly_gt, reduced_bank_cdr_gt, reduced_cdr_ipdr_gt
