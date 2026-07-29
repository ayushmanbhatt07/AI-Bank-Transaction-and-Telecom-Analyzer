import pytest
from datetime import datetime
from decimal import Decimal
from src.models.common import SourceProvenance, SourceType, EntityIdentity, IdentityType
from src.models.bank import BankTransaction, BankParty
from src.models.cdr import CDREvent
from src.models.ipdr import IPDRSession
from src.models.observation import RoleType, IdentityObservation
from src.resolution.extractor import extract_bank_identities, extract_cdr_identities, extract_ipdr_identities
from src.resolution.registry import IdentityRegistry

def _mock_bank_txn() -> BankTransaction:
    return BankTransaction(
        transaction_id="TXN1",
        transaction_timestamp=datetime(2025, 1, 1, 14, 30),
        amount=Decimal("100.00"),
        sender=BankParty(customer_id="C1", account_number="A1", phone="919876543210"),
        receiver=BankParty(customer_id="C2", account_number="A2", phone="919876543211"),
        provenance=SourceProvenance(source_type=SourceType.BANK, source_file="dummy", source_record_id="TXN1")
    )

def _mock_cdr_event() -> CDREvent:
    return CDREvent(
        cdr_id="CDR1",
        event_timestamp=datetime(2025, 1, 1, 14, 24),
        a_party_phone="919876543210",
        b_party_phone="919876543212",
        imsi="404010123456789",
        imei="351234567890123",
        cell_id="CELL1",
        provenance=SourceProvenance(source_type=SourceType.CDR, source_file="dummy", source_record_id="CDR1")
    )

def _mock_ipdr_session() -> IPDRSession:
    return IPDRSession(
        ipdr_id="IPDR1",
        session_timestamp=datetime(2025, 1, 1, 14, 50),
        subscriber_msisdn="919876543210",
        subscriber_imsi="404010123456789",
        device_imei="351234567890123",
        cell_id="CELL1",
        provenance=SourceProvenance(source_type=SourceType.IPDR, source_file="dummy", source_record_id="IPDR1")
    )

def test_bank_extraction():
    txn = _mock_bank_txn()
    obs = extract_bank_identities(txn)
    
    assert len(obs) == 6
    types = [o.identity.identity_type for o in obs]
    assert types.count(IdentityType.PHONE) == 2
    assert types.count(IdentityType.BANK_ACCOUNT) == 2
    assert types.count(IdentityType.CUSTOMER_ID) == 2

def test_cdr_extraction():
    event = _mock_cdr_event()
    obs = extract_cdr_identities(event)
    
    assert len(obs) == 5
    assert obs[0].identity.identity_type == IdentityType.PHONE
    assert obs[1].identity.identity_type == IdentityType.PHONE
    assert obs[2].identity.identity_type == IdentityType.IMSI
    assert obs[3].identity.identity_type == IdentityType.IMEI
    assert obs[4].identity.identity_type == IdentityType.CELL_ID

def test_ipdr_extraction():
    session = _mock_ipdr_session()
    obs = extract_ipdr_identities(session)
    
    assert len(obs) == 4
    # Check MSISDN mapped to PHONE
    assert obs[0].identity.identity_type == IdentityType.PHONE
    assert obs[0].identity.normalized_value == "919876543210"

def test_typed_identity_safety():
    # PHONE:"12345" vs IMSI:"12345"
    registry = IdentityRegistry()
    
    obs1 = IdentityObservation(
        identity=EntityIdentity(identity_type=IdentityType.PHONE, raw_value="12345", normalized_value="12345"),
        source_type=SourceType.BANK, source_record_id="1", source_field="p", role=RoleType.SENDER, timestamp=datetime.now()
    )
    obs2 = IdentityObservation(
        identity=EntityIdentity(identity_type=IdentityType.IMSI, raw_value="12345", normalized_value="12345"),
        source_type=SourceType.CDR, source_record_id="2", source_field="i", role=RoleType.SUBSCRIBER, timestamp=datetime.now()
    )
    
    registry.register(obs1)
    registry.register(obs2)
    
    assert len(registry.get_observations(IdentityType.PHONE, "12345")) == 1
    assert len(registry.get_observations(IdentityType.IMSI, "12345")) == 1

def test_cross_source_phone_bridge():
    registry = IdentityRegistry()
    for o in extract_bank_identities(_mock_bank_txn()): registry.register(o)
    for o in extract_cdr_identities(_mock_cdr_event()): registry.register(o)
    for o in extract_ipdr_identities(_mock_ipdr_session()): registry.register(o)
    
    # 919876543210 is in Bank(sender), CDR(a_party), IPDR(msisdn)
    obs = registry.get_observations(IdentityType.PHONE, "919876543210")
    assert len(obs) == 3
    sources = {o.source_type for o in obs}
    assert sources == {SourceType.BANK, SourceType.CDR, SourceType.IPDR}
    assert registry.is_cross_source(IdentityType.PHONE, "919876543210")

def test_missing_identity():
    # CDR missing imei and cell_id
    event = _mock_cdr_event()
    event.imei = None
    event.cell_id = None
    
    obs = extract_cdr_identities(event)
    assert len(obs) == 3 # A, B, IMSI
    types = [o.identity.identity_type for o in obs]
    assert IdentityType.IMEI not in types
    assert IdentityType.CELL_ID not in types

def test_duplicate_handling():
    registry = IdentityRegistry()
    event = _mock_cdr_event()
    obs_list = extract_cdr_identities(event)
    
    # register same exact observation twice
    registry.register(obs_list[0])
    registry.register(obs_list[0])
    
    assert len(registry.get_observations(obs_list[0].identity.identity_type, obs_list[0].identity.normalized_value)) == 1

def test_one_to_many_safety():
    registry = IdentityRegistry()
    
    # Two different customers, same phone
    txn1 = _mock_bank_txn()
    txn1.transaction_id = "T1"
    txn1.sender.customer_id = "C1"
    txn1.sender.phone = "P1"
    
    txn2 = _mock_bank_txn()
    txn2.transaction_id = "T2"
    txn2.sender.customer_id = "C2"
    txn2.sender.phone = "P1"
    
    for o in extract_bank_identities(txn1): registry.register(o)
    for o in extract_bank_identities(txn2): registry.register(o)
    
    assert registry.has_identity(IdentityType.CUSTOMER_ID, "C1")
    assert registry.has_identity(IdentityType.CUSTOMER_ID, "C2")
    # P1 has 2 observations
    assert len(registry.get_observations(IdentityType.PHONE, "P1")) == 2
