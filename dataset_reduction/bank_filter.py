import pandas as pd
from typing import Set

class BankFilter:
    def __init__(self, config):
        self.config = config

    def reduce_bank_dataset(self, bank_df: pd.DataFrame, selected_customers: Set[str]) -> pd.DataFrame:
        """
        Reduces the bank dataset by keeping only transactions where the Sender
        or Receiver is in the selected customers set.
        """
        mask = bank_df["Sender_Customer_ID"].isin(selected_customers) | bank_df["Receiver_Customer_ID"].isin(selected_customers)
        reduced_bank_df = bank_df[mask].copy()
        
        print(f"Final Bank Transactions          : {len(reduced_bank_df)}")
        return reduced_bank_df
