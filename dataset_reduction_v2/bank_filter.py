import pandas as pd
from typing import Set

class BankFilter:
    def __init__(self, config):
        self.config = config

    def filter_bank_data(self, bank_df: pd.DataFrame, selected_customers: Set[str]) -> pd.DataFrame:
        """
        Retains only transactions where BOTH Sender and Receiver belong to the selected customers.
        """
        print("Filtering Bank dataset enforcing strict closed-universe rule...")
        
        mask = bank_df["Sender_Customer_ID"].isin(selected_customers) & bank_df["Receiver_Customer_ID"].isin(selected_customers)
        reduced_bank_df = bank_df[mask].copy()
        
        # Save
        reduced_bank_df.to_csv(self.config.BANK_REDUCED_FILE, index=False)
        print(f"Saved reduced bank dataset to {self.config.BANK_REDUCED_FILE}")
        
        return reduced_bank_df
