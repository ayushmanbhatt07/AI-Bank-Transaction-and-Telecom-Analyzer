import pandas as pd
from typing import Set

class IPDRFilter:
    def __init__(self, config):
        self.config = config

    def reduce_ipdr_dataset(self, ipdr_df: pd.DataFrame, cdr_ipdr_gt_df: pd.DataFrame, retained_cdrs: Set[str]) -> pd.DataFrame:
        """
        Reduces the IPDR dataset by keeping only records that are linked to the retained CDRs.
        """
        # Find IPDRs mapped to retained CDRs
        mapped_df = cdr_ipdr_gt_df[cdr_ipdr_gt_df["CDR_ID"].isin(retained_cdrs)]
        
        # Extract unique IPDR_IDs (ignoring nulls, e.g., NO_MATCH)
        retained_ipdrs = set(mapped_df["IPDR_ID"].dropna().unique())
        
        # Filter ipdr_df
        reduced_ipdr_df = ipdr_df[ipdr_df["IPDR_ID"].isin(retained_ipdrs)].copy()
        
        print(f"Final IPDR Records               : {len(reduced_ipdr_df)}")
        return reduced_ipdr_df
