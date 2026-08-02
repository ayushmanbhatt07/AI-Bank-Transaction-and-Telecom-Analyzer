import pandas as pd
import numpy as np
from typing import Set, Tuple

class CustomerSelector:
    def __init__(self, config):
        self.config = config

    def select_customers(self, bank_df: pd.DataFrame, anomaly_gt_df: pd.DataFrame) -> Tuple[Set[str], Set[str], Set[str]]:
        scenarios = self.config.CONFIGURED_SCENARIOS
        filtered_gt = anomaly_gt_df[anomaly_gt_df["Scenario_Type"].isin(scenarios)]
        anomaly_txns = set(filtered_gt["Transaction_ID"].dropna().unique())
        
        # To preserve anomaly transactions under the closed-universe rule,
        # BOTH sender and receiver of every anomaly transaction must be in the selected set.
        anom_bank_df = bank_df[bank_df["Transaction_ID"].isin(anomaly_txns)]
        anomaly_customers = set(anom_bank_df["Sender_Customer_ID"].dropna()).union(set(anom_bank_df["Receiver_Customer_ID"].dropna()))
        
        print(f"Original number of customers     : {len(set(bank_df['Sender_Customer_ID'].dropna()).union(set(bank_df['Receiver_Customer_ID'].dropna())))}")
        print(f"Selected anomaly customers       : {len(anomaly_customers)}")
        
        all_senders = set(bank_df["Sender_Customer_ID"].dropna().unique())
        all_receivers = set(bank_df["Receiver_Customer_ID"].dropna().unique())
        all_customers = all_senders.union(all_receivers)
        
        normal_customers = list(all_customers - anomaly_customers)
        
        rng = np.random.default_rng(self.config.RANDOM_SEED)
        rng.shuffle(normal_customers)
        
        selected_customers = set(anomaly_customers)
        sampled_normal_customers = set()
        
        def count_internal(selected_set):
            mask = bank_df["Sender_Customer_ID"].isin(selected_set) & bank_df["Receiver_Customer_ID"].isin(selected_set)
            return mask.sum()

        current_internal = count_internal(selected_customers)
        
        chunk_size = 100
        for i in range(0, len(normal_customers), chunk_size):
            if current_internal >= self.config.TARGET_BANK_TRANSACTIONS:
                break
            chunk = normal_customers[i:i + chunk_size]
            selected_customers.update(chunk)
            sampled_normal_customers.update(chunk)
            current_internal = count_internal(selected_customers)
            
        print(f"Selected normal customers        : {len(sampled_normal_customers)}")
        print(f"Total selected customers         : {len(selected_customers)}")
        
        return selected_customers, anomaly_customers, sampled_normal_customers
