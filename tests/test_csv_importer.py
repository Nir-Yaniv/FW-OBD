"""Tests for CSV device import."""

from fw_obd.import_.csv_importer import parse_csv_text


def test_parse_generic_csv():
    csv_text = """Site Name,Site IP,Vendor,Location,Region
FG-NJ,10.0.1.1,Fortinet,New Jersey,US
FG-TelAviv,203.0.113.50,Fortinet,Tel Aviv,IL
"""
    preview = parse_csv_text(csv_text)
    assert len(preview.rows) == 2
    assert preview.rows[0].name == "FG-NJ"
    assert preview.rows[0].management_ip == "10.0.1.1"
    assert preview.rows[1].region == "IL"


def test_skips_empty_rows():
    csv_text = """name,ip
Valid,1.2.3.4
,5.6.7.8
AlsoValid,9.9.9.9
"""
    preview = parse_csv_text(csv_text)
    assert len(preview.rows) == 2
    assert preview.skipped == 1
