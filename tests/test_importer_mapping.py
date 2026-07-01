"""Tests for robust column mapping — alias normalization + content-based fallback."""

from fw_obd.import_.csv_importer import parse_csv_text


def test_underscore_headers_map_like_solarwinds():
    # SolarWinds export uses IP_Address / Caption / Location_Country (underscores).
    csv_text = """Caption,IP_Address,SysName,City,Location_Country
FW-DC,10.77.1.4,WAN-SW,Petach Tikva,Israel
FW-IN,14.142.155.110,MUMBAI-FW,Mumbai,India
"""
    preview = parse_csv_text(csv_text)
    assert preview.column_map["management_ip"] == "IP_Address"
    assert preview.column_map["name"] == "Caption"
    assert preview.column_map["location"] == "City"
    assert preview.column_map["region"] == "Location_Country"
    assert len(preview.rows) == 2
    assert preview.rows[0].management_ip == "10.77.1.4"
    assert preview.rows[1].region == "India"


def test_content_fallback_for_unknown_headers():
    # No header matches any alias — resolver must sniff IP + name from the data.
    csv_text = """Firewall Label,Mgmt Endpoint,Notes
Edge-FW-01,203.0.113.9,primary
Core-FW-02,10.20.30.40,standby
,,skipme
"""
    preview = parse_csv_text(csv_text)
    assert preview.column_map["management_ip"] == "Mgmt Endpoint"
    assert preview.column_map["name"] == "Firewall Label"
    assert len(preview.rows) == 2
    assert preview.skipped == 1


def test_hyphenated_headers_normalize():
    csv_text = """Node-Name,Node-IP
core,192.0.2.1
"""
    preview = parse_csv_text(csv_text)
    assert preview.rows[0].name == "core"
    assert preview.rows[0].management_ip == "192.0.2.1"


def test_still_raises_when_no_ip_anywhere():
    csv_text = """Label,Notes
just text,more text
"""
    try:
        parse_csv_text(csv_text)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "management IP" in str(exc)
