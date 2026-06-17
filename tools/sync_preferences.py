"""Bygger per-HS præferencedata fra Skattestyrelsens Trader Export Total-filer.

Input (gratis, ingen login — info.skat.dk/download/told/tot/):
- `Measure_<dato>.xml` (~1,2 GB): alle measures. measureType 142/143/145/146 = præference/GSP,
  med `goodsNomenclatureCode`, `geographicalAreaId` (land ELLER gruppe) og
  `measureComponent`/`dutyAmount` (ad valorem).
- `GeographicalArea_<dato>.xml`: lande/grupper + memberships (land → gruppe-SID).

Output (til `reference/tariff/`):
- `preferential_rates.csv`: hs_code, area, rate — bedste (laveste) ad valorem-præferencesats
  pr. (varekode, geografisk område).
- `geo_areas.json`: {country_groups: {land: [gruppe-id'er]}, area_name: {id: navn}} så
  tariferingslaget kan opløse land → grupper og slå (hs, område) op.

Streames med lxml iterparse (hukommelsesbundet, XXE fra). Begrænsning: udelukkelser
(`measureExcludedGeographicalArea`) og oprindelsesregler ignoreres p.t. — præferencen er
"potentiel" (kræver oprindelsesvurdering), hvilket matcher FTA-mulighed-tjekkets formål.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from decimal import Decimal
from pathlib import Path

NS = "{http://www.arcticgroup.se/tariff/arctictariff/export}"
# Ubetingede præferencer/toldunion: 142 toldpræference, 145 præf. efter særl. anv.,
# 141 præf. ifm. suspension, 106 toldunionsafgift (TR/SM/AD industrivarer).
PREFERENCE_TYPES = {"142", "145", "141", "106"}
# Kvote-baserede præferencer: kun gyldige mens kontingentet er åbent → markeres.
QUOTA_TYPES = {"143", "146", "147"}
ALL_PREF_TYPES = PREFERENCE_TYPES | QUOTA_TYPES
REFERENCE = Path(__file__).resolve().parent.parent / "reference" / "tariff"


def _code10(raw) -> str:
    digits = "".join(ch for ch in str(raw or "") if ch.isdigit())
    return digits[:10]


def parse_geographical_areas(geo_xml: Path) -> tuple[dict[str, list[str]], dict[str, str]]:
    """→ (country_groups: land → [gruppe-id'er], area_name: id → dansk navn)."""
    from lxml import etree

    sid_to_id: dict[str, str] = {}
    area_name: dict[str, str] = {}
    memberships: list[tuple[str, str]] = []  # (medlems-id, gruppe-SID)

    ctx = etree.iterparse(str(geo_xml), events=("end",), tag=NS + "geographicalArea",
                          resolve_entities=False, no_network=True)
    for _, ga in ctx:
        aid = ga.get(NS + "geographicalAreaId")
        sid = ga.get(NS + "SID")
        if sid:
            sid_to_id[sid] = aid
        for desc_el in ga.iter(NS + "geographicalAreaDescription"):
            # Beskrivelsen er et attribut (at:description), med at:languageId.
            if desc_el.get(NS + "languageId") == "DA":
                d = desc_el.get(NS + "description")
                if d:
                    area_name[aid] = d.strip()
        for mem in ga.iter(NS + "geographicalAreaMembership"):
            if mem.get(NS + "dateEnd"):  # kun aktive memberships
                continue
            grp_sid = mem.get(NS + "SIDGeographicalAreaGroup")
            if grp_sid:
                memberships.append((aid, grp_sid))
        ga.clear()
        while ga.getprevious() is not None:
            del ga.getparent()[0]

    country_groups: dict[str, set] = {}
    for member_id, grp_sid in memberships:
        grp_id = sid_to_id.get(grp_sid)
        if grp_id and member_id:
            country_groups.setdefault(member_id, set()).add(grp_id)
    return {k: sorted(v) for k, v in country_groups.items()}, area_name


def build_preferences(measure_xml: Path, geo_xml: Path) -> dict:
    """Stream Measure-filen → bedste præferencesats pr. (hs, område)."""
    from lxml import etree

    country_groups, area_name = parse_geographical_areas(geo_xml)
    # rows: (hs, area, date_start, date_end, rate, is_quota) — ALLE gyldighedsperioder
    # bevares (ikke længere laveste-sats-på-tværs-af-tid), så opslag kan matche importdato.
    rows: set = set()
    ctx = etree.iterparse(str(measure_xml), events=("end",), tag=NS + "measure",
                          resolve_entities=False, no_network=True)
    for _, m in ctx:
        mt = m.get(NS + "measureType")
        if mt in ALL_PREF_TYPES:
            hs = _code10(m.get(NS + "goodsNomenclatureCode"))
            area = m.get(NS + "geographicalAreaId")
            is_quota = mt in QUOTA_TYPES
            rate = None
            for comp in m.iter(NS + "measureComponent"):
                if comp.get(NS + "dutyExpressionId") == "01":  # ad valorem %
                    da = comp.get(NS + "dutyAmount")
                    if da not in (None, ""):
                        try:
                            rate = Decimal(da) / 100
                        except Exception:
                            rate = None
                    break
            if hs and area and rate is not None:
                ds = (m.get(NS + "dateStart") or "")[:10]
                de = (m.get(NS + "dateEnd") or "")[:10]
                rows.add((hs, area, ds, de, str(rate), "1" if is_quota else "0"))
        m.clear()
        while m.getprevious() is not None:
            del m.getparent()[0]
    return {"rows": rows, "country_groups": country_groups, "area_name": area_name}


def write_preferences(data: dict, out_dir: Path) -> tuple[int, int]:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = 0
    with (out_dir / "preferential_rates.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["hs_code", "area", "date_start", "date_end", "rate", "is_quota"])
        for r in sorted(data["rows"]):
            w.writerow(r)
            rows += 1
    (out_dir / "geo_areas.json").write_text(
        json.dumps({"_note": "Genereret af tools/sync_preferences.py fra Trader Export.",
                    "country_groups": data["country_groups"], "area_name": data["area_name"]},
                   ensure_ascii=False), encoding="utf-8")
    codes = len({r[0] for r in data["rows"]})
    return rows, codes


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Synk per-HS præferencer fra Trader Export.")
    p.add_argument("--measure", required=True, help="Measure_<dato>.xml (Trader Export Total)")
    p.add_argument("--geo", required=True, help="GeographicalArea_<dato>.xml")
    p.add_argument("--out", default=str(REFERENCE))
    args = p.parse_args(argv)
    data = build_preferences(Path(args.measure), Path(args.geo))
    rows, codes = write_preferences(data, Path(args.out))
    print(f"Præferencer: {rows} (hs×område)-satser på {codes} varekoder; "
          f"{len(data['country_groups'])} lande m. gruppemedlemskab.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
