import pandas as pd
import numpy as np
from typing import Set

class CustomerSelector:
    def __init__(self, config):
        self.config = config

    def select_customers(self, bank_df: pd.DataFrame, anomalous_customers: Set[str]) -> Set[str]:
        """
        Selects all anomalous customers and randomly samples normal customers
        until the total number of bank transactions (where they are sender or receiver)
        reaches the target limit.
        """
        selected_customers = set(anomalous_customers)
        
        # Initial mask for anomalous customers
        mask = bank_df["Sender_Customer_ID"].isin(selected_customers) | bank_df["Receiver_Customer_ID"].isin(selected_customers)
        current_tx_count = mask.sum()
        
        print(f"Transactions From Fraud Customers: {current_tx_count}")
        
        if current_tx_count >= self.config.TARGET_BANK_TRANSACTIONS:
            print("Target transaction count reached with anomalous customers alone.")
            return selected_customers
            
        all_senders = set(bank_df["Sender_Customer_ID"].dropna().unique())
        all_receivers = set(bank_df["Receiver_Customer_ID"].dropna().unique())
        all_customers = all_senders.union(all_receivers)
        
        normal_customers = list(all_customers - selected_customers)
        
        # Randomize with seed
        rng = np.random.default_rng(self.config.RANDOM_SEED)
        rng.shuffle(normal_customers)
        
        added_count = 0
        
        # To avoid re-evaluating the mask on the whole dataframe on every single customer,
        # we can add customers in chunks.
        chunk_size = 50
        
        for i in range(0, len(normal_customers), chunk_size):
            chunk = normal_customers[i:i + chunk_size]
            selected_customers.update(chunk)
            added_count += len(chunk)
            
            # Re-evaluate mask
            mask = bank_df["Sender_Customer_ID"].isin(selected_customers) | bank_df["Receiver_Customer_ID"].isin(selected_customers)
            current_tx_count = mask.sum()
            
            if current_tx_count >= self.config.TARGET_BANK_TRANSACTIONS:
                break
                
        print(f"Random Customers Selected        : {added_count}")
        
        return selected_customers
