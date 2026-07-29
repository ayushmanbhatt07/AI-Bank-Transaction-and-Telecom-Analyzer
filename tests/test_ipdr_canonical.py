import pytest
from src.canonical.ipdr_mapper import map_ipdr_row
from src.models.ipdr import IPDRSession

def test_ipdr_mapper_success():
    row_dict = {
        "IPDR_ID": "IPDR202600000001",
        "Session_Date": "2025-11-12",
        "Session_Start_Time": "19:16:30",
        "Subscriber_IMSI": 404957538096376,
        "Subscriber_MSISDN": 916126482756,
        "Device_IMEI": 350825372787856,
        "Source_IP_Address": "10.240.105.232",
        "Destination_IP_Address": "198.51.100.21",
        "Destination_Port": 5228,
        "Cell_Global_ID": "404-45-779-107",
        "Session_Duration_Seconds": 7
    }
    
    session, warnings = map_ipdr_row(row_dict, "test_ipdr.csv", 0)
    assert isinstance(session, IPDRSession)
    assert session.ipdr_id == "IPDR202600000001"
    assert session.subscriber_msisdn == "916126482756"
    assert session.subscriber_imsi == "404957538096376"
    assert session.device_imei == "350825372787856"
    assert session.source_ip == "10.240.105.232"
    assert session.destination_ip == "198.51.100.21"
    assert session.cell_id == "404-45-779-107"
    assert session.duration_seconds == 7
    assert session.destination_port == 5228
    assert len(warnings) == 0

def test_ipdr_mapper_missing_core():
    row_dict = {
        "IPDR_ID": "IPDR1",
        "Session_Date": "2025-11-12",
        "Session_Start_Time": "19:16:30"
    }
    with pytest.raises(ValueError, match="Missing CORE_REQUIRED field: subscriber_msisdn"):
        map_ipdr_row(row_dict, "test_ipdr.csv", 0)

def test_ipdr_mapper_missing_fusion():
    row_dict = {
        "IPDR_ID": "IPDR1",
        "Session_Date": "2025-11-12",
        "Session_Start_Time": "19:16:30",
        "Subscriber_MSISDN": 916126482756
    }
    session, warnings = map_ipdr_row(row_dict, "test_ipdr.csv", 0)
    assert len(warnings) == 3 # missing imsi, imei, cell_id
