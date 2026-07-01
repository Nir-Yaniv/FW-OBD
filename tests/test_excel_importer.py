"""Tests for Excel (.xlsx) device import."""

from openpyxl import Workbook

from fw_obd.import_.csv_importer import parse_excel_file, parse_import_file


def _write_xlsx(path, header, data_rows):
    wb = Workbook()
    ws = wb.active
    ws.append(header)
    for row in data_rows:
        ws.append(row)
    wb.save(path)


def test_parse_excel_with_solarwinds_headers(tmp_path):
    xlsx = tmp_path / "devices.xlsx"
    _write_xlsx(
        xlsx,
        ["Site Name", "Site IP", "Vendor", "Location", "Region"],
        [
            ["FG-NJ", "10.0.1.1", "Fortinet", "New Jersey", "US"],
            ["FG-TelAviv", "203.0.113.50", "FortiGate", "Tel Aviv", "IL"],
        ],
    )
    preview = parse_excel_file(xlsx)
    assert len(preview.rows) == 2
    assert preview.rows[0].name == "FG-NJ"
    assert preview.rows[0].management_ip == "10.0.1.1"
    # FortiGate is normalized to Fortinet
    assert preview.rows[1].vendor == "Fortinet"
    assert preview.rows[1].region == "IL"


def test_excel_coerces_numeric_cells_and_skips_blanks(tmp_path):
    xlsx = tmp_path / "devices.xlsx"
    _write_xlsx(
        xlsx,
        ["name", "ip"],
        [
            ["Valid", "1.2.3.4"],
            [None, "5.6.7.8"],   # missing name -> skipped
            ["Numbered", 42],     # numeric cell coerced to "42"
        ],
    )
    preview = parse_excel_file(xlsx)
    assert preview.skipped == 1
    assert len(preview.rows) == 2
    assert preview.rows[1].management_ip == "42"


def test_parse_import_file_dispatches_by_extension(tmp_path):
    xlsx = tmp_path / "d.xlsx"
    _write_xlsx(xlsx, ["name", "ip"], [["A", "1.1.1.1"]])
    csv = tmp_path / "d.csv"
    csv.write_text("name,ip\nB,2.2.2.2\n", encoding="utf-8")

    assert parse_import_file(xlsx).rows[0].name == "A"
    assert parse_import_file(csv).rows[0].name == "B"
