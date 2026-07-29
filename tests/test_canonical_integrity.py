import pytest
import pandas as pd
from src.canonical.loader import load_bank, load_cdr, load_ipdr
from src.canonical.bank_mapper import map_bank_row
from src.canonical.cdr_mapper import map_cdr_row
from src.canonical.ipdr_mapper import map_ipdr_row
from src.canonical.normalizers import normalize_phone
import os

def test_bank_integrity():
    csv_path = "data/clean/bank_final.csv"
    if not os.path.exists(csv_path):
        pytest.skip(f"Data file not found: {csv_path}")
    
    df = pd.read_csv(csv_path, nrows=100, dtype=str) # Test first 100 to save time in test suite
    successes, errors, warning_count = load_bank(df, csv_path)
    
    assert len(errors) == 0
    assert len(successes) == 100
    
    # Check information preservation for the first row
    first_row = df.iloc[0]
    txn = successes[0]
    assert txn.transaction_id == str(first_row['Transaction_ID'])
    assert str(txn.amount) == str(first_row['Transaction_Amount'])
    assert txn.sender.phone == normalize_phone(first_row['Sender_Phone_Number'])
    assert txn.sender.account_number == str(first_row['Sender_Account_Number'])
    assert txn.receiver.account_number == str(first_row['Receiver_Account_Number'])

def test_cdr_integrity():
    csv_path = "data/clean/cdr_final.csv"
    if not os.path.exists(csv_path):
        pytest.skip(f"Data file not found: {csv_path}")
    
    df = pd.read_csv(csv_path, nrows=100, dtype=str)
    successes, errors, warning_count = load_cdr(df, csv_path)
    
    assert len(errors) == 0
    assert len(successes) == 100
    
    first_row = df.iloc[0]
    event = successes[0]
    assert event.cdr_id == str(first_row['CDR_ID'])
    assert event.a_party_phone == normalize_phone(first_row['A_Party_Number'])
    assert event.imsi == str(first_row['IMSI'])
    assert event.imei == str(first_row['IMEI'])

def test_ipdr_integrity():
    csv_path = "data/clean/ipdr_final.csv"
    if not os.path.exists(csv_path):
        pytest.skip(f"Data file not found: {csv_path}")
    
    df = pd.read_csv(csv_path, nrows=100, dtype=str)
    successes, errors, warning_count = load_ipdr(df, csv_path)
    
    assert len(errors) == 0
    assert len(successes) == 100
    
    first_row = df.iloc[0]
    session = successes[0]
    assert session.ipdr_id == str(first_row['IPDR_ID'])
    assert session.subscriber_msisdn == normalize_phone(first_row['Subscriber_MSISDN'])
    assert session.subscriber_imsi == str(first_row['Subscriber_IMSI'])
    assert session.source_ip == str(first_row['Source_IP_Address'])
