import pytest
from decimal import Decimal
from src.canonical.bank_mapper import map_bank_row
from src.models.bank import BankTransaction

def test_bank_mapper_success():
    row_dict = {
        "Transaction_ID": "ATM250101XAJI0Y",
        "Date": "2025-01-01",
        "Timestamp": "00:01:21",
        "Txn_Ref_Number": "6DPBHSAHXTHV",
        "Transaction_Mode": "ATM",
        "Currency": "INR",
        "Transaction_Amount": 12259.13,
        "Sender_Customer_ID": 100005319,
        "Sender_Customer_Name": "Niraj Rathod",
        "Sender_Bank_Name": "IndusInd Bank",
        "Sender_Account_Number": "716477905315",
        "Sender_Account_Type": "Savings",
        "Sender_IFSC": "INDB7033599",
        "Sender_Phone_Number": 918978249018,
        "Receiver_Customer_ID": 100004520,
        "Receiver_Customer_Name": "Sarthak Agarwal",
        "Receiver_Bank_Name": "Punjab National Bank",
        "Receiver_Account_Number": "101629319198",
        "Receiver_Account_Type": "Savings",
        "Receiver_IFSC": "PUNB8143143",
        "Receiver_Phone_Number": 916547825570
    }
    
    txn, warnings = map_bank_row(row_dict, "test.csv", 0)
    assert isinstance(txn, BankTransaction)
    assert txn.transaction_id == "ATM250101XAJI0Y"
    assert txn.amount == Decimal("12259.13")
    assert txn.sender.phone == "918978249018"
    assert txn.receiver.phone == "916547825570"
    assert txn.sender.account_number == "716477905315"
    assert txn.receiver.account_number == "101629319198"
    assert txn.provenance.source_record_id == "ATM250101XAJI0Y"
    assert len(warnings) == 0

def test_bank_mapper_missing_core():
    row_dict = {
        "Date": "2025-01-01",
        "Timestamp": "00:01:21",
        "Transaction_Amount": 100
    }
    with pytest.raises(ValueError, match="Missing CORE_REQUIRED field: transaction_id"):
        map_bank_row(row_dict, "test.csv", 0)

def test_bank_mapper_missing_fusion():
    row_dict = {
        "Transaction_ID": "T1",
        "Date": "2025-01-01",
        "Timestamp": "00:01:21",
        "Transaction_Amount": 100
    }
    txn, warnings = map_bank_row(row_dict, "test.csv", 0)
    assert len(warnings) == 2 # Sender and Receiver phone missing
