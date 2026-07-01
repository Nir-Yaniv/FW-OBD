"""Group devices into a Region -> City -> Site tree for the Devices page.

Grouping rules:
  * Region and City labels are normalized (see REGION_ALIASES / CITY_ALIASES) so
    variants of the same place collapse together. Normalization affects only the
    grouping labels — never the stored device record.
  * A "site" is derived from the device name (the part before Main/Backup), so a
    site's Main and Backup pair together while numbered sites stay distinct
    (Chennai-1 vs Chennai-2).
  * Within a site, Main is listed before Backup before Other.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Region label normalization (lowercased key -> canonical).
REGION_ALIASES = {
    "pk": "Pakistan",
    "rome": "Italy",  # Rome is a city; the country is Italy
}

# City label normalization: numbered/typo variants -> base city. The site number
# is preserved via the site level under the city.
CITY_ALIASES = {
    "hyderbad": "Hyderabad",
    "hyderabad3": "Hyderabad",
    "hyderabad - osman": "Hyderabad",
    "islamabad5": "Islamabad",
    "lahore2": "Lahore",
    "lahore4": "Lahore",
    "karachi2": "Karachi",
    "karachi-3": "Karachi",
    "pune2": "Pune",
}

_KIND_ORDER = {"Main": 0, "Backup": 1, "Other": 2}

# Region -> ISO 3166-1 alpha-2 code, keyed by normalized region name (lowercased).
# Used to load the bundled flag image (ui/assets/flags/<iso>.png).
REGION_ISO = {
    "israel": "il", "india": "in", "pakistan": "pk", "usa": "us", "canada": "ca",
    "uae": "ae", "ghana": "gh", "philippines": "ph", "saudi arabia": "sa",
    "kenya": "ke", "bolivia": "bo", "nepal": "np", "colombia": "co", "france": "fr",
    "uk": "gb", "romania": "ro", "italy": "it", "morocco": "ma",
}


def region_iso(region: str) -> str | None:
    """Return the ISO country code for a region label, or None if unknown."""
    return REGION_ISO.get((region or "").strip().lower())


def normalize_region(region: str) -> str:
    r = (region or "").strip()
    return REGION_ALIASES.get(r.lower(), r) or "(no region)"


def normalize_city(city: str, fallback: str = "") -> str:
    c = (city or "").strip()
    if not c:
        return fallback or "(unspecified)"
    return CITY_ALIASES.get(c.lower(), c)


def site_key(name: str) -> str:
    """Derive a site identifier from a device name (text before Main/Backup/paren)."""
    s = re.sub(r"^\s*RICU\s*[-\s]*", "", name or "", flags=re.I)
    m = re.search(r"\bmain\b|\bbackup\b|\(", s, flags=re.I)
    if m:
        s = s[: m.start()]
    return s.strip(" -") or (name or "").strip()


def classify(name: str) -> str:
    n = (name or "").lower()
    if "main" in n:
        return "Main"
    if "backup" in n:
        return "Backup"
    return "Other"


@dataclass
class SiteGroup:
    name: str | None            # None => city has a single site; render devices directly
    devices: list[dict] = field(default_factory=list)


@dataclass
class CityGroup:
    name: str
    sites: list[SiteGroup] = field(default_factory=list)

    @property
    def count(self) -> int:
        return sum(len(s.devices) for s in self.sites)


@dataclass
class RegionGroup:
    name: str
    cities: list[CityGroup] = field(default_factory=list)

    @property
    def count(self) -> int:
        return sum(c.count for c in self.cities)


def build_device_tree(devices: list[dict]) -> list[RegionGroup]:
    """Return regions (by device count desc) -> cities (alpha) -> sites -> devices."""
    # region -> city -> site -> [device]
    raw: dict[str, dict[str, dict[str, list[dict]]]] = {}
    for d in devices:
        name = (d.get("name") or "").strip()
        sk = site_key(name)
        region = normalize_region(d.get("region", ""))
        city = normalize_city(d.get("location", ""), fallback=sk)
        raw.setdefault(region, {}).setdefault(city, {}).setdefault(sk, []).append(d)

    regions: list[RegionGroup] = []
    for region_name in raw:
        rg = RegionGroup(region_name)
        for city_name in sorted(raw[region_name]):
            sites_map = raw[region_name][city_name]
            cg = CityGroup(city_name)
            multi = len(sites_map) > 1
            for sk in sorted(sites_map):
                devs = sorted(sites_map[sk], key=lambda d: _KIND_ORDER[classify(d.get("name", ""))])
                cg.sites.append(SiteGroup(name=sk if multi else None, devices=devs))
            rg.cities.append(cg)
        regions.append(rg)

    regions.sort(key=lambda r: r.count, reverse=True)
    return regions
