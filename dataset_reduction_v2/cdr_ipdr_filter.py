import pandas as pd

class CdrIpdrFilter:
    def __init__(self, config):
        self.config = config

    def filter_cdr(self, cdr_df: pd.DataFrame, bank_cdr_gt: pd.DataFrame, retained_bank_txns: set) -> pd.DataFrame:
        print("Filtering CDR dataset...")
        valid_bank_cdr = bank_cdr_gt[bank_cdr_gt["Transaction_ID"].isin(retained_bank_txns)]
        retained_cdrs = set(valid_bank_cdr["CDR_ID"].dropna())
        
        reduced_cdr_df = cdr_df[cdr_df["CDR_ID"].isin(retained_cdrs)].copy()
        
        # Save
        reduced_cdr_df.to_csv(self.config.CDR_REDUCED_FILE, index=False)
        print(f"Saved reduced CDR dataset to {self.config.CDR_REDUCED_FILE}")
        
        return reduced_cdr_df

    def filter_ipdr(self, ipdr_df: pd.DataFrame, cdr_ipdr_gt: pd.DataFrame, retained_cdrs: set) -> pd.DataFrame:
        print("Filtering IPDR dataset...")
        valid_cdr_ipdr = cdr_ipdr_gt[cdr_ipdr_gt["CDR_ID"].isin(retained_cdrs)]
        retained_ipdrs = set(valid_cdr_ipdr["IPDR_ID"].dropna())
        
        reduced_ipdr_df = ipdr_df[ipdr_df["IPDR_ID"].isin(retained_ipdrs)].copy()
        
        # Save
        reduced_ipdr_df.to_csv(self.config.IPDR_REDUCED_FILE, index=False)
        print(f"Saved reduced IPDR dataset to {self.config.IPDR_REDUCED_FILE}")
        
        return reduced_ipdr_df
