from datetime import datetime, timedelta
from decimal import Decimal
from src.models.bank import BankTransaction, BankParty
from src.models.cdr import CDREvent
from src.models.observation import IdentityObservation, RoleType
from src.models.common import EntityIdentity, IdentityType, SourceType, SourceProvenance
from src.resolution.registry import IdentityRegistry
from src.correlation.config import CorrelationConfig
from src.correlation.bank_cdr import correlate_bank_to_cdr

def make_bank(id_str, time_str, sender_phone=None, receiver_phone=None):
    return BankTransaction(
        transaction_id=id_str,
        transaction_timestamp=datetime.fromisoformat(time_str),
        amount=Decimal("10.0"),
        sender=BankParty(phone=sender_phone),
        receiver=BankParty(phone=receiver_phone),
        provenance=SourceProvenance(source_type=SourceType.BANK, source_file="b.csv", source_record_id=id_str)
    )

def make_cdr(id_str, time_str, a_party, b_party):
    return CDREvent(
        cdr_id=id_str,
        event_timestamp=datetime.fromisoformat(time_str),
        a_party_phone=a_party,
        b_party_phone=b_party,
        provenance=SourceProvenance(source_type=SourceType.CDR, source_file="c.csv", source_record_id=id_str)
    )

def test_bank_cdr_exact_boundary():
    # 1800s window
    b = make_bank("B1", "2026-07-01T12:30:00", sender_phone="919800000001")
    
    reg = IdentityRegistry()
    
    c_before = make_cdr("C1", "2026-07-01T12:00:00", a_party="919800000001", b_party="")
    c_after = make_cdr("C2", "2026-07-01T13:00:00", a_party="919800000001", b_party="")
    c_outside_before = make_cdr("C3", "2026-07-01T11:59:59", a_party="919800000001", b_party="")
    c_outside_after = make_cdr("C4", "2026-07-01T13:00:01", a_party="919800000001", b_party="")
    
    cdrs = {"C1": c_before, "C2": c_after, "C3": c_outside_before, "C4": c_outside_after}
    
    for c in cdrs.values():
        reg.register(IdentityObservation(
            identity=EntityIdentity(identity_type=IdentityType.PHONE, raw_value=c.a_party_phone, normalized_value=c.a_party_phone),
            source_type=SourceType.CDR,
            source_record_id=c.cdr_id,
            source_field="a_party",
            role=RoleType.A_PARTY,
            timestamp=c.event_timestamp
        ))
        
    config = CorrelationConfig(bank_cdr_window_seconds=1800)
    res = correlate_bank_to_cdr([b], cdrs, reg, config)
    
    assert len(res) == 2
    accepted_ids = {r.target_event_id for r in res}
    assert "C1" in accepted_ids
    assert "C2" in accepted_ids
    
    for r in res:
        assert r.time_difference_seconds in (-1800, 1800)
        assert len(r.identity_evidence) == 1
        assert r.identity_evidence[0].source_role == "BANK_SENDER"

def test_bank_cdr_duplicate_paths():
    # Sender and Receiver both match A/B party in the same CDR (loop scenario)
    b = make_bank("B1", "2026-07-01T12:30:00", sender_phone="P1", receiver_phone="P2")
    c = make_cdr("C1", "2026-07-01T12:30:00", a_party="P1", b_party="P2")
    
    reg = IdentityRegistry()
    reg.register(IdentityObservation(
        identity=EntityIdentity(identity_type=IdentityType.PHONE, raw_value="P1", normalized_value="P1"),
        source_type=SourceType.CDR, source_record_id="C1", source_field="a_party", role=RoleType.A_PARTY, timestamp=c.event_timestamp
    ))
    reg.register(IdentityObservation(
        identity=EntityIdentity(identity_type=IdentityType.PHONE, raw_value="P2", normalized_value="P2"),
        source_type=SourceType.CDR, source_record_id="C1", source_field="b_party", role=RoleType.B_PARTY, timestamp=c.event_timestamp
    ))
    
    res = correlate_bank_to_cdr([b], {"C1": c}, reg, CorrelationConfig())
    assert len(res) == 1 # Deduplicated by CDR ID!
    assert res[0].time_difference_seconds == 0
    assert len(res[0].identity_evidence) == 2 # Evidence preserves both matches

def test_bank_cdr_cross_midnight():
    b = make_bank("B1", "2026-07-01T00:10:00", sender_phone="P1")
    c = make_cdr("C1", "2026-06-30T23:55:00", a_party="P1", b_party="")
    
    reg = IdentityRegistry()
    reg.register(IdentityObservation(
        identity=EntityIdentity(identity_type=IdentityType.PHONE, raw_value="P1", normalized_value="P1"),
        source_type=SourceType.CDR, source_record_id="C1", source_field="a_party", role=RoleType.A_PARTY, timestamp=c.event_timestamp
    ))
    
    res = correlate_bank_to_cdr([b], {"C1": c}, reg, CorrelationConfig())
    assert len(res) == 1
    assert res[0].time_difference_seconds == -15 * 60
