import pytest
import pandas as pd
from datetime import datetime
from src.canonical.normalizers import (
    normalize_phone, normalize_imsi, normalize_imei,
    parse_datetime, normalize_ip, normalize_cell_id, normalize_account
)

def test_normalize_phone():
    assert normalize_phone("+91 98123 45678") == "919812345678"
    assert normalize_phone("+919812345678") == "919812345678"
    assert normalize_phone("91-98123-45678") == "919812345678"
    assert normalize_phone("9812345678") == "9812345678"
    assert normalize_phone(919812345678) == "919812345678"
    assert normalize_phone(None) == ""
    assert normalize_phone("") == ""
    assert normalize_phone(pd.NA) == ""

def test_cross_source_normalisation():
    """
    Test demonstrating that equivalent formatting becomes comparable.
    Bank phone: +91 98123 45678
    CDR phone: 919812345678
    IPDR MSISDN: 91-98123-45678
    """
    bank_phone = normalize_phone("+91 98123 45678")
    cdr_phone = normalize_phone("919812345678")
    ipdr_msisdn = normalize_phone("91-98123-45678")
    
    assert bank_phone == "919812345678"
    assert bank_phone == cdr_phone
    assert cdr_phone == ipdr_msisdn

def test_normalize_imsi():
    assert normalize_imsi(" 123 456 789 ") == "123456789"
    assert normalize_imsi("001234567890123") == "001234567890123"
    assert normalize_imsi(None) == ""

def test_normalize_imei():
    assert normalize_imei(" 123 456 789 ") == "123456789"
    assert normalize_imei("001234567890123") == "001234567890123"
    assert normalize_imei(None) == ""

def test_parse_datetime():
    dt = parse_datetime("2025-01-01", "00:01:21")
    assert isinstance(dt, datetime)
    
    # Missing Date
    with pytest.raises(ValueError):
        parse_datetime(None, "00:01:21")
        
    # Missing Time
    with pytest.raises(ValueError):
        parse_datetime("2025-01-01", None)
        
    # Explicit 00:00:00 is fine
    dt2 = parse_datetime("2025-01-01", "00:00:00")
    assert dt2.hour == 0

def test_normalize_ip():
    assert normalize_ip("192.168.1.1 ") == "192.168.1.1"
    assert normalize_ip("2001:0db8:85a3:0000:0000:8a2e:0370:7334") == "2001:0db8:85a3:0000:0000:8a2e:0370:7334"
    assert normalize_ip(None) == ""
    assert normalize_ip("NaN") == ""
    
    with pytest.raises(ValueError):
        normalize_ip("999.999.999.999")

def test_normalize_cell_id():
    assert normalize_cell_id(" 404-45-979-482 ") == "404-45-979-482"
