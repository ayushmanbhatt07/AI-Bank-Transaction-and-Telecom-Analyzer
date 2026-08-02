import pandas as pd
from typing import Set, Tuple

class ScenarioFilter:
    def __init__(self, config):
        self.config = config

    def get_anomalous_transactions_and_customers(self, anomaly_gt_df: pd.DataFrame) -> Tuple[Set[str], Set[str]]:
        """
        Filters the anomaly ground truth to extract the anomaly transactions and
        customers associated with the configured fraud scenarios.
        """
        scenarios = self.config.CONFIGURED_SCENARIOS
        print(f"Selected Fraud Scenarios         : {len(scenarios)}")
        
        filtered_df = anomaly_gt_df[anomaly_gt_df["Scenario_Type"].isin(scenarios)]
        
        # We assume Transaction_ID exists. And Customer_ID exists.
        anomaly_txns = set(filtered_df["Transaction_ID"].dropna().unique())
        anomalous_customers = set(filtered_df["Customer_ID"].dropna().unique())
        
        print(f"Anomaly Transactions Found       : {len(anomaly_txns)}")
        print(f"Unique Anomalous Customers       : {len(anomalous_customers)}")
        
        return anomaly_txns, anomalous_customers
