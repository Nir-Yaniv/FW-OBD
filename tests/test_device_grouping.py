"""Tests for device grouping, normalization, and site pairing."""

from fw_obd.services.device_grouping import (
    build_device_tree,
    classify,
    normalize_city,
    normalize_region,
    region_iso,
    site_key,
)


def test_normalization():
    assert normalize_region("PK") == "Pakistan"
    assert normalize_region("Rome") == "Italy"
    assert normalize_region("India") == "India"
    assert normalize_city("Hyderbad") == "Hyderabad"
    assert normalize_city("Islamabad5") == "Islamabad"
    assert normalize_city("", fallback="SiteX") == "SiteX"


def test_site_key_and_classify():
    assert site_key("RICU - Chennai-1 Main (ACT Business)") == "Chennai-1"
    assert site_key("RICU - Chennai-1 Backup") == "Chennai-1"
    assert site_key("RICU - Chennai-2 Backup (Jio)") == "Chennai-2"
    assert classify("RICU - Chennai-1 Main (ACT)") == "Main"
    assert classify("RICU - Chennai-1 Backup") == "Backup"
    assert classify("RICU - Switch WAN") == "Other"


def test_site_pairing_keeps_chennai1_and_chennai2_separate():
    devices = [
        {"name": "RICU - Chennai-1 Main (ACT)", "management_ip": "1.1.1.1", "region": "India", "location": "Chennai"},
        {"name": "RICU - Chennai-1 Backup", "management_ip": "1.1.1.2", "region": "India", "location": "Chennai"},
        {"name": "RICU - Chennai-2 Backup (Jio)", "management_ip": "1.1.1.3", "region": "India", "location": "Chennai"},
    ]
    regions = build_device_tree(devices)
    india = regions[0]
    assert india.name == "India"
    chennai = india.cities[0]
    assert chennai.name == "Chennai"
    # two distinct sites: Chennai-1 (paired) and Chennai-2 (separate)
    site_names = [s.name for s in chennai.sites]
    assert site_names == ["Chennai-1", "Chennai-2"]
    chennai1 = chennai.sites[0]
    assert len(chennai1.devices) == 2
    # Main is ordered before Backup within a site
    assert classify(chennai1.devices[0]["name"]) == "Main"


def test_single_site_city_has_no_site_subgroup():
    devices = [
        {"name": "RICU - Udaipur Main", "management_ip": "2.2.2.1", "region": "India", "location": "Udaipur"},
        {"name": "RICU - Udaipur Backup", "management_ip": "2.2.2.2", "region": "India", "location": "Udaipur"},
    ]
    city = build_device_tree(devices)[0].cities[0]
    assert len(city.sites) == 1
    assert city.sites[0].name is None  # single site -> devices render directly under city


def test_region_iso():
    assert region_iso("India") == "in"
    assert region_iso("Pakistan") == "pk"
    assert region_iso("PK") is None  # normalization happens before iso lookup
    assert region_iso("Nowhere") is None
