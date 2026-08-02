import os
import config
from loader import DataLoader
from scenario_filter import ScenarioFilter
from customer_selector import CustomerSelector
from bank_filter import BankFilter
from cdr_filter import CDRFilter
from ipdr_filter import IPDRFilter
from ground_truth_filter import GroundTruthFilter
from validator import Validator

def main():
    print("Starting TRI-NETRA Dataset Reduction Pipeline...")
    
    # Ensure reduced directory exists
    os.makedirs(config.REDUCED_DIR, exist_ok=True)
    
    # 1. Load Data
    loader = DataLoader(config)
    bank_df, cdr_df, ipdr_df = loader.load_all_datasets()
    anomaly_gt_df, bank_cdr_gt_df, cdr_ipdr_gt_df = loader.load_ground_truth()
    
    # 2. Extract Anomalies
    scenario_filter = ScenarioFilter(config)
    anomaly_txns, anomalous_customers = scenario_filter.get_anomalous_transactions_and_customers(anomaly_gt_df)
    
    # 3. Select Customers
    customer_selector = CustomerSelector(config)
    selected_customers = customer_selector.select_customers(bank_df, anomalous_customers)
    
    # 4. Reduce Bank Dataset
    bank_filter = BankFilter(config)
    reduced_bank_df = bank_filter.reduce_bank_dataset(bank_df, selected_customers)
    retained_txns = set(reduced_bank_df["Transaction_ID"].dropna())
    
    # 5. Reduce CDR Dataset
    cdr_filter = CDRFilter(config)
    reduced_cdr_df = cdr_filter.reduce_cdr_dataset(cdr_df, bank_cdr_gt_df, retained_txns)
    retained_cdrs = set(reduced_cdr_df["CDR_ID"].dropna())
    
    # 6. Reduce IPDR Dataset
    ipdr_filter = IPDRFilter(config)
    reduced_ipdr_df = ipdr_filter.reduce_ipdr_dataset(ipdr_df, cdr_ipdr_gt_df, retained_cdrs)
    retained_ipdrs = set(reduced_ipdr_df["IPDR_ID"].dropna())
    
    # 7. Reduce Ground Truth
    gt_filter = GroundTruthFilter(config)
    reduced_anomaly_gt, reduced_bank_cdr_gt, reduced_cdr_ipdr_gt = gt_filter.reduce_ground_truth(
        anomaly_gt_df, bank_cdr_gt_df, cdr_ipdr_gt_df,
        retained_txns, retained_cdrs, retained_ipdrs
    )
    
    # 8. Validation
    validator = Validator(config)
    validator.validate(
        reduced_bank_df, reduced_cdr_df, reduced_ipdr_df,
        reduced_anomaly_gt, reduced_bank_cdr_gt, reduced_cdr_ipdr_gt,
        selected_customers, anomaly_txns
    )
    
    # 9. Save Files
    print("Saving reduced datasets...")
    reduced_bank_df.to_csv(config.BANK_REDUCED_FILE, index=False)
    reduced_cdr_df.to_csv(config.CDR_REDUCED_FILE, index=False)
    reduced_ipdr_df.to_csv(config.IPDR_REDUCED_FILE, index=False)
    
    reduced_anomaly_gt.to_csv(config.ANOMALY_GROUND_TRUTH_REDUCED_FILE, index=False)
    reduced_bank_cdr_gt.to_csv(config.BANK_CDR_GROUND_TRUTH_REDUCED_FILE, index=False)
    reduced_cdr_ipdr_gt.to_csv(config.CDR_IPDR_GROUND_TRUTH_REDUCED_FILE, index=False)
    
    print("Reduction complete!")

if __name__ == "__main__":
    main()
