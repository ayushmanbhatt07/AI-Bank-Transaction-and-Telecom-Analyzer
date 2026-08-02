import os

# Base directories
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
ANOMALOUS_DIR = os.path.join(DATA_DIR, "anomalous")
GROUND_TRUTH_DIR = os.path.join(DATA_DIR, "ground_truth")
REDUCED_DIR = os.path.join(DATA_DIR, "new_reduced")

# Input files
BANK_ANOMALOUS_FILE = os.path.join(ANOMALOUS_DIR, "bank_anomaly.csv")
CDR_ANOMALOUS_FILE = os.path.join(ANOMALOUS_DIR, "cdr_anomaly.csv")
IPDR_ANOMALOUS_FILE = os.path.join(ANOMALOUS_DIR, "ipdr_anomaly.csv")

ANOMALY_GROUND_TRUTH_FILE = os.path.join(GROUND_TRUTH_DIR, "anomaly_ground_truth.csv")
BANK_CDR_GROUND_TRUTH_FILE = os.path.join(GROUND_TRUTH_DIR, "bank_cdr_ground_truth.csv")
CDR_IPDR_GROUND_TRUTH_FILE = os.path.join(GROUND_TRUTH_DIR, "cdr_ipdr_ground_truth.csv")

# Output files
BANK_REDUCED_FILE = os.path.join(REDUCED_DIR, "bank_reduced.csv")
CDR_REDUCED_FILE = os.path.join(REDUCED_DIR, "cdr_reduced.csv")
IPDR_REDUCED_FILE = os.path.join(REDUCED_DIR, "ipdr_reduced.csv")

ANOMALY_GROUND_TRUTH_REDUCED_FILE = os.path.join(REDUCED_DIR, "anomaly_ground_truth_reduced.csv")
BANK_CDR_GROUND_TRUTH_REDUCED_FILE = os.path.join(REDUCED_DIR, "bank_cdr_ground_truth_reduced.csv")
CDR_IPDR_GROUND_TRUTH_REDUCED_FILE = os.path.join(REDUCED_DIR, "cdr_ipdr_ground_truth_reduced.csv")

# Configuration
RANDOM_SEED = 42
TARGET_BANK_TRANSACTIONS = 10000

# Scenarios to retain
CONFIGURED_SCENARIOS = [
    "CALL_THEN_NEW_BENEFICIARY",
    "CALL_THEN_HIGH_VALUE_TRANSFER",
    "NEW_DEVICE_AROUND_TRANSACTION",
    "UNUSUAL_LOCATION_CONTEXT",
    "NETWORK_SESSION_BURST_AROUND_TRANSACTION",
    "REPEATED_CALLS_BEFORE_TRANSACTION"
]
