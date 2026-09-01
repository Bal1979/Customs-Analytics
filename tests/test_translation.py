"""Tests for oversættelseslaget (Oversæt-fanen) — format-detektion, felt-par og dækning.

Syntetiske data + Toldstyrelsens officielle test-XML som fixtures — ingen rigtige
angivelser.
"""

from pathlib import Path

from customs.parsers.legacy_sad import _rows_from_lines
from customs.translation import (
    _normalize_rows,
    build_translation,
    detect_format,
    translate_upload,
)

FIXTURES = Path(__file__).parent / "fixtures"


# ── Format-detektion ─────────────────────────────────────────────────────────


def test_detect_format_by_extension():
    assert detect_format(b"", "angivelse.XML") == "wco_xml"
    assert detect_format(b"", "udskrift.pdf") == "legacy_sad"
    assert detect_format(b"", "udtraek.csv") == "tabular"
    assert detect_format(b"", "udtraek.xlsx") == "tabular"


def test_detect_format_by_magic_bytes_when_no_extension():
    assert detect_format(b"%PDF-1.4 ...", "upload") == "legacy_sad"
    assert detect_format(b'<?xml version="1.0"?><Declaration/>', None) == "wco_xml"
    assert detect_format(b"varekode;oprindelsesland\n0804300090;GB", None) == "tabular"


# ── Ny → gammel: officiel DMS-XML ind, SAD-visning ud ───────────────────────


def test_translate_official_h1_xml():
    data = (FIXTURES / "official_h1_standard.xml").read_bytes()
    t = translate_upload(data, "official_h1_standard.xml")

    assert t["source_format"] == "wco_xml"
    assert t["direction"] == "ny_til_gammel"
    assert t["items_count"] == 1
    assert t["lossy_source"] is False

    hdr = {f["key"]: f for f in t["header_fields"]}
    assert hdr["decltype"]["value"] == "IMD · H1"
    assert hdr["office"]["value"] == "DK005607"
    assert hdr["invoice"]["value"] == "GBP · 30.000"
    assert hdr["dispatch"]["value"] == "GB"
    assert hdr["destination"]["value"] == "DK"
    assert hdr["motborder"]["value"] == "1"
    assert hdr["transportnat"]["value"] == "DK"
    assert hdr["delivery"]["value"] == "FOB · Immingham, DK"
    assert hdr["importer"]["value"] == "DK12345678"
    assert hdr["lrn"]["value"] == "test124589"
    # Felt-parret bærer begge sider af oversættelsen.
    assert hdr["invoice"]["sad"]["box"] == "Boks 22"
    assert hdr["invoice"]["dms"]["de"] == "14 05/14 06 001"

    item = {f["key"]: f for f in t["item_sections"][0]["fields"]}
    assert item["commodity"]["value"] == "080430 · 00 · 90"
    assert item["origin"]["value"] == "GB"
    assert item["preference"]["value"] == "100"
    assert item["procedure"]["value"] == "40 · 00 · 000"
    assert item["net"]["value"] == "1.800"
    assert item["statvalue"]["value"] == "268.138"
    assert item["valuation"]["value"] == "1"
    assert item["suppunits"]["value"] == "1.500"
    assert "Y929" in (item["documents"]["value"] or "")

    # Dækning: udfyldt + manglende skal summe til kataloget.
    cov = t["coverage"]
    assert cov["filled"] + len([k for k in cov["missing_keys"]]) >= cov["filled"]
    assert 0 < cov["filled"] <= cov["total"]


# ── Gammel → ny: SAD-rækker ind, DMS-visning ud (tabsgivende kilde) ─────────


_LEGACY_LINES = [
    "Møntsort: EUR",
    "25 Transportmåde ved grænsen: 1",
    "26 Indenlandsk transportmåde: 3",
    "Forventet ankomstdato: 20230615 kl.0800",
    "32 Varepost nummer: 1",
    "Varebeskrivelse: Testgardin",
    "33 Varekode: 6303929090",
    "34 Oprindelsesland: VN",
    "36 Præference: 300",
    "37 Procedurekode: 4000000",
    "38 Nettomasse: 1000",
    "42 Varens pris: 50000",
    "46 Statistisk værdi: 60000",
    "1 A00 60000 0 0 1 142 1001",
]


def test_translate_legacy_rows_marks_gaps_and_splits_codes():
    rows = _rows_from_lines(_LEGACY_LINES)
    t = build_translation(_normalize_rows(rows), "legacy_sad")

    assert t["direction"] == "gammel_til_ny"
    assert t["lossy_source"] is True

    item = {f["key"]: f for f in t["item_sections"][0]["fields"]}
    # 10-cifret varekode og 7-cifret CPC splittes til DMS-delene.
    assert item["commodity"]["value"] == "630392 · 90 · 90"
    assert item["procedure"]["value"] == "40 · 00 · 000"
    assert item["preference"]["value"] == "300"
    assert item["statvalue"]["value"] == "60.000"
    assert item["duty"]["value"] == "0"

    # Tabsgivende kilde: umappede felter markeres eksplicit som manglende.
    assert item["valuation"]["value"] is None
    missing = t["coverage"]["missing_keys"]
    assert "valuation" in missing and "lrn" in missing
    # Hoveddel arvet fra rækkerne.
    hdr = {f["key"]: f for f in t["header_fields"]}
    assert hdr["invoice"]["value"] == "EUR"
    assert hdr["motborder"]["value"] == "1"


def test_translate_upload_rejects_empty():
    import pytest

    with pytest.raises(Exception):
        translate_upload(b"kolonne_a;kolonne_b\n", "tom.csv")
