from src.correlation.config import CorrelationConfig
from src.correlation.bank_cdr import correlate_bank_to_cdr
from src.correlation.cdr_ipdr import correlate_cdr_to_ipdr
from src.resolution.registry import IdentityRegistry
from src.models.observation import IdentityObservation, RoleType
from src.models.common import EntityIdentity, IdentityType, SourceType, SourceProvenance
from tests.test_bank_cdr_correlation import make_bank
from tests.test_cdr_ipdr_correlation import make_cdr, make_ipdr
from datetime import datetime

def test_stage4_end_to_end_integration():
    # 1. Setup Canonical Objects
    b = make_bank("B1", "2026-07-01T12:00:00", sender_phone="P1")
    c = make_cdr("C1", "2026-07-01T12:05:00", a_party="P1", imsi="I1")
    i = make_ipdr("IP1", "2026-07-01T12:07:00", phone="P1", imsi="I1")
    
    # 2. Stage 3 Registry
    reg = IdentityRegistry()
    # CDR observations
    reg.register(IdentityObservation(
        identity=EntityIdentity(identity_type=IdentityType.PHONE, raw_value="P1", normalized_value="P1"),
        source_type=SourceType.CDR, source_record_id="C1", source_field="a_party", role=RoleType.A_PARTY, timestamp=c.event_timestamp
    ))
    # IPDR observations
    reg.register(IdentityObservation(
        identity=EntityIdentity(identity_type=IdentityType.PHONE, raw_value="P1", normalized_value="P1"),
        source_type=SourceType.IPDR, source_record_id="IP1", source_field="phone", role=RoleType.SUBSCRIBER, timestamp=i.session_timestamp
    ))
    reg.register(IdentityObservation(
        identity=EntityIdentity(identity_type=IdentityType.IMSI, raw_value="I1", normalized_value="I1"),
        source_type=SourceType.IPDR, source_record_id="IP1", source_field="imsi", role=RoleType.SUBSCRIBER, timestamp=i.session_timestamp
    ))
    
    # 3. Stage 4 Correlation
    config = CorrelationConfig()
    bank_correlations = correlate_bank_to_cdr([b], {"C1": c}, reg, config)
    cdr_ipdr_correlations = correlate_cdr_to_ipdr([c], {"IP1": i}, reg, config)
    
    # 4. Verify
    assert len(bank_correlations) == 1
    assert bank_correlations[0].accepted == True
    assert bank_correlations[0].time_difference_seconds == 300 # 12:05 - 12:00
    
    assert len(cdr_ipdr_correlations) == 1
    assert cdr_ipdr_correlations[0].accepted == True
    assert cdr_ipdr_correlations[0].time_difference_seconds == 120 # 12:07 - 12:05
    assert len(cdr_ipdr_correlations[0].identity_evidence) == 2 # Phone and IMSI matched
