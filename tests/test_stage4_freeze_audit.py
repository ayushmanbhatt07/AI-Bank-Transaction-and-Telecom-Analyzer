from datetime import datetime
from src.correlation.config import CorrelationConfig
from src.correlation.bank_cdr import correlate_bank_to_cdr
from src.correlation.cdr_ipdr import correlate_cdr_to_ipdr
from src.correlation.models import MatchStrength
from src.resolution.registry import IdentityRegistry
from src.models.observation import IdentityObservation, RoleType
from src.models.common import EntityIdentity, IdentityType, SourceType
from tests.test_bank_cdr_correlation import make_bank
from tests.test_cdr_ipdr_correlation import make_ipdr

def make_cdr(id_str, time_str, a_party="", b_party="", imsi="", imei="", cell=""):
    from src.models.cdr import CDREvent
    from src.models.common import SourceProvenance
    return CDREvent(
        cdr_id=id_str,
        event_timestamp=datetime.fromisoformat(time_str),
        a_party_phone=a_party, b_party_phone=b_party,
        imsi=imsi, imei=imei, cell_id=cell,
        provenance=SourceProvenance(source_type=SourceType.CDR, source_file="c.csv", source_record_id=id_str)
    )

def test_bank_cdr_all_role_combinations():
    """Verify all Sender/Receiver combinations matching A-Party/B-Party."""
    b = make_bank("B1", "2026-07-01T12:00:00", sender_phone="S1", receiver_phone="R1")
    c1 = make_cdr("C1", "2026-07-01T12:00:00", a_party="S1", b_party="") # Sender -> A
    c2 = make_cdr("C2", "2026-07-01T12:00:00", a_party="", b_party="S1") # Sender -> B
    c3 = make_cdr("C3", "2026-07-01T12:00:00", a_party="R1", b_party="") # Receiver -> A
    c4 = make_cdr("C4", "2026-07-01T12:00:00", a_party="", b_party="R1") # Receiver -> B
    
    reg = IdentityRegistry()
    for idx, c in enumerate([c1, c2, c3, c4]):
        phone = "S1" if idx < 2 else "R1"
        role = RoleType.A_PARTY if idx % 2 == 0 else RoleType.B_PARTY
        field = "a_party" if idx % 2 == 0 else "b_party"
        reg.register(IdentityObservation(
            identity=EntityIdentity(identity_type=IdentityType.PHONE, raw_value=phone, normalized_value=phone),
            source_type=SourceType.CDR, source_record_id=c.cdr_id, source_field=field, role=role, timestamp=c.event_timestamp
        ))
    
    res = correlate_bank_to_cdr([b], {"C1": c1, "C2": c2, "C3": c3, "C4": c4}, reg, CorrelationConfig())
    assert len(res) == 4
    for r in res:
        assert r.accepted == True

def test_missing_values_handled_gracefully():
    b = make_bank("B1", "2026-07-01T12:00:00", sender_phone="", receiver_phone=None)
    c = make_cdr("C1", "2026-07-01T12:00:00", a_party="", b_party="")
    
    reg = IdentityRegistry()
    res = correlate_bank_to_cdr([b], {"C1": c}, reg, CorrelationConfig())
    assert len(res) == 0

def test_configurable_windows_signed_deltas():
    b = make_bank("B1", "2026-07-01T12:00:00", sender_phone="P1")
    c1 = make_cdr("C1", "2026-07-01T12:10:00", a_party="P1", b_party="") # +600s
    c2 = make_cdr("C2", "2026-07-01T11:50:00", a_party="P1", b_party="") # -600s
    
    reg = IdentityRegistry()
    for c in [c1, c2]:
        reg.register(IdentityObservation(
            identity=EntityIdentity(identity_type=IdentityType.PHONE, raw_value="P1", normalized_value="P1"),
            source_type=SourceType.CDR, source_record_id=c.cdr_id, source_field="a_party", role=RoleType.A_PARTY, timestamp=c.event_timestamp
        ))
    
    # 5-minute window should reject both
    res_tight = correlate_bank_to_cdr([b], {"C1": c1, "C2": c2}, reg, CorrelationConfig(bank_cdr_window_seconds=300))
    assert len(res_tight) == 0
    
    # 15-minute window should accept both
    res_loose = correlate_bank_to_cdr([b], {"C1": c1, "C2": c2}, reg, CorrelationConfig(bank_cdr_window_seconds=900))
    assert len(res_loose) == 2
    
    # Check signed deltas
    deltas = {r.target_event_id: r.time_difference_seconds for r in res_loose}
    assert deltas["C1"] == 600
    assert deltas["C2"] == -600

def test_zero_one_many_matches():
    # 1 Bank Txn -> 3 CDRs
    b1 = make_bank("B1", "2026-07-01T12:00:00", sender_phone="P1")
    c1 = make_cdr("C1", "2026-07-01T12:01:00", a_party="P1", b_party="")
    c2 = make_cdr("C2", "2026-07-01T12:02:00", a_party="P1", b_party="")
    c3 = make_cdr("C3", "2026-07-01T12:03:00", a_party="P1", b_party="")
    
    reg = IdentityRegistry()
    for c in [c1, c2, c3]:
        reg.register(IdentityObservation(
            identity=EntityIdentity(identity_type=IdentityType.PHONE, raw_value="P1", normalized_value="P1"),
            source_type=SourceType.CDR, source_record_id=c.cdr_id, source_field="a_party", role=RoleType.A_PARTY, timestamp=c.event_timestamp
        ))
        
    res = correlate_bank_to_cdr([b1], {"C1": c1, "C2": c2, "C3": c3}, reg, CorrelationConfig())
    assert len(res) == 3
    
    # 3 Bank Txns -> 1 CDR
    b2 = make_bank("B2", "2026-07-01T12:01:00", sender_phone="P2")
    b3 = make_bank("B3", "2026-07-01T12:02:00", sender_phone="P2")
    c4 = make_cdr("C4", "2026-07-01T12:01:30", a_party="P2", b_party="")
    
    reg2 = IdentityRegistry()
    reg2.register(IdentityObservation(
        identity=EntityIdentity(identity_type=IdentityType.PHONE, raw_value="P2", normalized_value="P2"),
        source_type=SourceType.CDR, source_record_id="C4", source_field="a_party", role=RoleType.A_PARTY, timestamp=c4.event_timestamp
    ))
    
    res2 = correlate_bank_to_cdr([b2, b3], {"C4": c4}, reg2, CorrelationConfig())
    assert len(res2) == 2

def test_cdr_ipdr_conflict_recording_is_not_rejection():
    # MODERATE strength should not implicitly mean rejected (accepted = True)
    c = make_cdr("C1", "2026-07-01T12:00:00", a_party="P1", imsi="I1", imei="D1")
    i = make_ipdr("I1", "2026-07-01T12:05:00", phone="P1", imsi="I2", imei="D2")
    
    reg = IdentityRegistry()
    # P1 matches!
    reg.register(IdentityObservation(
        identity=EntityIdentity(identity_type=IdentityType.PHONE, raw_value="P1", normalized_value="P1"),
        source_type=SourceType.IPDR, source_record_id="I1", source_field="msisdn", role=RoleType.SUBSCRIBER, timestamp=i.session_timestamp
    ))
    
    res = correlate_cdr_to_ipdr([c], {"I1": i}, reg, CorrelationConfig())
    assert len(res) == 1
    assert res[0].accepted == True
    assert res[0].match_strength == MatchStrength.MODERATE
    assert len(res[0].conflicting_evidence) == 2

def test_deterministic_execution_ordering():
    b1 = make_bank("B1", "2026-07-01T12:00:00", sender_phone="P1")
    b2 = make_bank("B2", "2026-07-01T12:00:00", sender_phone="P2")
    
    c1 = make_cdr("C1", "2026-07-01T12:01:00", a_party="P1", b_party="")
    c2 = make_cdr("C2", "2026-07-01T12:01:00", a_party="P2", b_party="")
    
    reg = IdentityRegistry()
    reg.register(IdentityObservation(
        identity=EntityIdentity(identity_type=IdentityType.PHONE, raw_value="P1", normalized_value="P1"),
        source_type=SourceType.CDR, source_record_id="C1", source_field="a_party", role=RoleType.A_PARTY, timestamp=c1.event_timestamp
    ))
    reg.register(IdentityObservation(
        identity=EntityIdentity(identity_type=IdentityType.PHONE, raw_value="P2", normalized_value="P2"),
        source_type=SourceType.CDR, source_record_id="C2", source_field="a_party", role=RoleType.A_PARTY, timestamp=c2.event_timestamp
    ))
    
    # Run once
    res1 = correlate_bank_to_cdr([b1, b2], {"C1": c1, "C2": c2}, reg, CorrelationConfig())
    
    # Run with reversed input order
    res2 = correlate_bank_to_cdr([b2, b1], {"C1": c1, "C2": c2}, reg, CorrelationConfig())
    
    # Output must be identically ordered
    assert [r.correlation_id for r in res1] == [r.correlation_id for r in res2]
