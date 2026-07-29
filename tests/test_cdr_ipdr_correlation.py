from datetime import datetime
from src.models.cdr import CDREvent
from src.models.ipdr import IPDRSession
from src.models.observation import IdentityObservation, RoleType
from src.models.common import EntityIdentity, IdentityType, SourceType, SourceProvenance
from src.resolution.registry import IdentityRegistry
from src.correlation.config import CorrelationConfig
from src.correlation.models import MatchStrength
from src.correlation.cdr_ipdr import correlate_cdr_to_ipdr

def make_cdr(id_str, time_str, a_party="", imsi="", imei="", cell=""):
    return CDREvent(
        cdr_id=id_str,
        event_timestamp=datetime.fromisoformat(time_str),
        a_party_phone=a_party, b_party_phone="",
        imsi=imsi, imei=imei, cell_id=cell,
        provenance=SourceProvenance(source_type=SourceType.CDR, source_file="c.csv", source_record_id=id_str)
    )

def make_ipdr(id_str, time_str, phone="", imsi="", imei="", cell=""):
    return IPDRSession(
        ipdr_id=id_str,
        session_timestamp=datetime.fromisoformat(time_str),
        subscriber_msisdn=phone,
        subscriber_imsi=imsi, device_imei=imei, cell_id=cell,
        provenance=SourceProvenance(source_type=SourceType.IPDR, source_file="i.csv", source_record_id=id_str)
    )

def test_cdr_ipdr_strong_identity():
    c = make_cdr("C1", "2026-07-01T12:00:00", imsi="I1")
    i = make_ipdr("I1", "2026-07-01T12:05:00", imsi="I1")
    
    reg = IdentityRegistry()
    reg.register(IdentityObservation(
        identity=EntityIdentity(identity_type=IdentityType.IMSI, raw_value="I1", normalized_value="I1"),
        source_type=SourceType.IPDR, source_record_id="I1", source_field="imsi", role=RoleType.SUBSCRIBER, timestamp=i.session_timestamp
    ))
    
    res = correlate_cdr_to_ipdr([c], {"I1": i}, reg, CorrelationConfig())
    assert len(res) == 1
    assert res[0].accepted == True
    assert res[0].match_strength == MatchStrength.STRONG
    assert len(res[0].identity_evidence) == 1
    assert res[0].identity_evidence[0].identity_type == IdentityType.IMSI

def test_cdr_ipdr_cell_only_rejected():
    c = make_cdr("C1", "2026-07-01T12:00:00", cell="CELL1")
    i = make_ipdr("I1", "2026-07-01T12:05:00", cell="CELL1")
    
    reg = IdentityRegistry()
    reg.register(IdentityObservation(
        identity=EntityIdentity(identity_type=IdentityType.CELL_ID, raw_value="CELL1", normalized_value="CELL1"),
        source_type=SourceType.IPDR, source_record_id="I1", source_field="cell", role=RoleType.CELL, timestamp=i.session_timestamp
    ))
    
    res = correlate_cdr_to_ipdr([c], {"I1": i}, reg, CorrelationConfig())
    assert len(res) == 0 # Rejected because Cell alone is insufficient

def test_cdr_ipdr_conflicts():
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
    
    # Has phone evidence
    assert len(res[0].identity_evidence) == 1
    
    # Should have two conflicts (IMSI, IMEI)
    assert len(res[0].conflicting_evidence) == 2
    conflict_types = {c.identity_type for c in res[0].conflicting_evidence}
    assert IdentityType.IMSI in conflict_types
    assert IdentityType.IMEI in conflict_types
    
    # 1 strong match, but 2 strong conflicts -> MODERATE strength (per rules)
    assert res[0].match_strength == MatchStrength.MODERATE
    assert res[0].accepted == True
