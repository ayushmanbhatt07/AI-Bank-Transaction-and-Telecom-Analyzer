import pytest
from src.canonical.cdr_mapper import map_cdr_row
from src.models.cdr import CDREvent

def test_cdr_mapper_success():
    row_dict = {
        "CDR_ID": "CDR202600000001",
        "Call_Date": "2025-07-30",
        "Call_Start_Time": "05:10:18",
        "A_Party_Number": 919688378412,
        "B_Party_Number": 918571552449,
        "Call_Type": "VOICE",
        "Call_Duration_Seconds": 19,
        "IMSI": 404668358296730,
        "IMEI": 358452418469620,
        "First_BTS_Location": "WestBengal_BTS_008",
        "First_Cell_Global_ID": "404-45-979-482",
        "Roaming_Network_Circle": "West Bengal"
    }
    
    event, warnings = map_cdr_row(row_dict, "test_cdr.csv", 0)
    assert isinstance(event, CDREvent)
    assert event.cdr_id == "CDR202600000001"
    assert event.a_party_phone == "919688378412"
    assert event.b_party_phone == "918571552449"
    assert event.imsi == "404668358296730"
    assert event.imei == "358452418469620"
    assert event.cell_id == "404-45-979-482"
    assert event.duration_seconds == 19
    assert event.provenance.source_record_id == "CDR202600000001"
    assert len(warnings) == 0

def test_cdr_mapper_missing_core():
    row_dict = {
        "Call_Date": "2025-07-30",
        "Call_Start_Time": "05:10:18",
        "A_Party_Number": 919688378412
    }
    with pytest.raises(ValueError, match="Missing CORE_REQUIRED field: cdr_id"):
        map_cdr_row(row_dict, "test_cdr.csv", 0)

def test_cdr_mapper_missing_fusion():
    row_dict = {
        "CDR_ID": "CDR1",
        "Call_Date": "2025-07-30",
        "Call_Start_Time": "05:10:18",
        "A_Party_Number": 919688378412,
        "B_Party_Number": 918571552449
    }
    event, warnings = map_cdr_row(row_dict, "test_cdr.csv", 0)
    assert len(warnings) == 3 # missing imsi, imei, cell_id
