import pandas as pd
from typing import Set

class CDRFilter:
    def __init__(self, config):
        self.config = config

    def reduce_cdr_dataset(self, cdr_df: pd.DataFrame, bank_cdr_gt_df: pd.DataFrame, retained_txns: Set[str]) -> pd.DataFrame:
        """
        Reduces the CDR dataset by keeping only records that are linked to the retained bank transactions.
        """
        # Find CDRs mapped to retained transactions
        mapped_df = bank_cdr_gt_df[bank_cdr_gt_df["Transaction_ID"].isin(retained_txns)]
        
        # Extract unique CDR_IDs (ignoring nulls, e.g., NO_MATCH)
        retained_cdrs = set(mapped_df["CDR_ID"].dropna().unique())
        
        # Filter cdr_df
        reduced_cdr_df = cdr_df[cdr_df["CDR_ID"].isin(retained_cdrs)].copy()
        
        print(f"Final CDR Records                : {len(reduced_cdr_df)}")
        return reduced_cdr_df
