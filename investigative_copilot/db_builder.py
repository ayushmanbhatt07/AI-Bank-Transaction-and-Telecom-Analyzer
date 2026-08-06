import sqlite3
import pandas as pd
from pathlib import Path
from typing import Optional, Union, Tuple
import logging

logger = logging.getLogger(__name__)

class CopilotDBBuilder:
    """SQLite Database Builder for TRI-NETRA Investigative Co-Pilot.
    Reads reduced datasets from data/new_reduced/ and indexes them into SQLite tables.
    """

    def __init__(self, data_dir: Optional[Union[str, Path]] = None, db_path: str = ":memory:"):
        if data_dir is None:
            # Default to project_root / data / new_reduced
            project_root = Path(__file__).resolve().parent.parent
            data_dir = project_root / "data" / "new_reduced"
        self.data_dir = Path(data_dir)
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None

    def build_database(self) -> sqlite3.Connection:
        """Loads all reduced datasets and creates indexed SQLite tables."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        
        # Load datasets
        bank_csv = self.data_dir / "bank_reduced.csv"
        cdr_csv = self.data_dir / "cdr_reduced.csv"
        ipdr_csv = self.data_dir / "ipdr_reduced.csv"
        bank_cdr_gt_csv = self.data_dir / "bank_cdr_ground_truth_reduced.csv"
        cdr_ipdr_gt_csv = self.data_dir / "cdr_ipdr_ground_truth_reduced.csv"
        anomaly_gt_csv = self.data_dir / "anomaly_ground_truth_reduced.csv"

        if bank_csv.exists():
            df_bank = pd.read_csv(bank_csv)
            # Standardize column names for SQL convenience
            df_bank.columns = [c.lower() for c in df_bank.columns]
            df_bank.to_sql("bank_transactions", conn, if_exists="replace", index=False)
            
        if cdr_csv.exists():
            df_cdr = pd.read_csv(cdr_csv)
            df_cdr.columns = [c.lower() for c in df_cdr.columns]
            df_cdr.to_sql("cdr_records", conn, if_exists="replace", index=False)
            
        if ipdr_csv.exists():
            df_ipdr = pd.read_csv(ipdr_csv)
            df_ipdr.columns = [c.lower() for c in df_ipdr.columns]
            df_ipdr.to_sql("ipdr_records", conn, if_exists="replace", index=False)

        if bank_cdr_gt_csv.exists():
            df_b_cdr = pd.read_csv(bank_cdr_gt_csv)
            df_b_cdr.columns = [c.lower() for c in df_b_cdr.columns]
            df_b_cdr.to_sql("bank_cdr_links", conn, if_exists="replace", index=False)

        if cdr_ipdr_gt_csv.exists():
            df_c_ipdr = pd.read_csv(cdr_ipdr_gt_csv)
            df_c_ipdr.columns = [c.lower() for c in df_c_ipdr.columns]
            df_c_ipdr.to_sql("cdr_ipdr_links", conn, if_exists="replace", index=False)

        if anomaly_gt_csv.exists():
            df_anomaly = pd.read_csv(anomaly_gt_csv)
            df_anomaly.columns = [c.lower() for c in df_anomaly.columns]
            df_anomaly.to_sql("anomaly_records", conn, if_exists="replace", index=False)

        self._create_indices(conn)
        self.conn = conn
        logger.info(f"Copilot SQLite database initialized successfully at {self.db_path}")
        return conn

    def _create_indices(self, conn: sqlite3.Connection) -> None:
        """Creates indices to ensure real-time query execution."""
        cursor = conn.cursor()
        
        # Bank indices
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_bank_tx_id ON bank_transactions(transaction_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_bank_sender_acc ON bank_transactions(sender_account_number);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_bank_receiver_acc ON bank_transactions(receiver_account_number);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_bank_sender_phone ON bank_transactions(sender_phone_number);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_bank_receiver_phone ON bank_transactions(receiver_phone_number);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_bank_ts ON bank_transactions(timestamp);")
        
        # CDR indices
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cdr_id ON cdr_records(cdr_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cdr_a_party ON cdr_records(a_party_number);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cdr_b_party ON cdr_records(b_party_number);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cdr_bts ON cdr_records(first_bts_location);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cdr_imsi ON cdr_records(imsi);")
        
        # IPDR indices
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ipdr_id ON ipdr_records(ipdr_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ipdr_msisdn ON ipdr_records(subscriber_msisdn);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ipdr_imsi ON ipdr_records(subscriber_imsi);")
        
        # Link indices
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_b_cdr_tx ON bank_cdr_links(transaction_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_b_cdr_cdr ON bank_cdr_links(cdr_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_c_ipdr_cdr ON cdr_ipdr_links(cdr_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_c_ipdr_ipdr ON cdr_ipdr_links(ipdr_id);")
        
        conn.commit()


_global_db_conn: Optional[sqlite3.Connection] = None

def get_copilot_db() -> sqlite3.Connection:
    """Returns a singleton SQLite connection for the Copilot module."""
    global _global_db_conn
    if _global_db_conn is None:
        builder = CopilotDBBuilder()
        _global_db_conn = builder.build_database()
    return _global_db_conn
