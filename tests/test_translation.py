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


# ── Ny → gammel: DMS-print (PDF-rendering af det nye format) ────────────────

_DMS_PRINT_LINES = [
    "26DKTESTPRINT00A1B2",
    "Overgang til fri",
    "H1",
    "omsætning",
    "Oversigt",
    "Nøgledata",
    "Angivelses nummer: 26DKTESTPRINT00A1B2 Suppl. angivelsestype: IM/A",
    "Klarerens navn: Angivelsestype: H1",
    "Toldsteds ID: DK004700 Angivelse Status: Varerne er frigivet",
    "Hoveddel",
    "Gruppe 11 Meddelelsesoplysninger",
    # Værdi indskudt i elementnummeret pga. linjeombrydning (observeret mønster).
    "Angivelsestype (11 01 001 000) IM Supplerende angivelsestype (11 02 001 A",
    "000)",
    "LRN (12 09 001 000): TESTLRN-2026",
    "Gruppe 13 Parter",
    "Navn (13 01 016 000): Testfirma GmbH Landekode (13 01 018 020): DE",
    "By (13 01 018 022): Hamburg",
    "EORI nr. - Importør (13 04 017 000): DK11223344 By (13 04 018 022):",
    "Gruppe 14 Beregningsoplysninger",
    "UN/LOCODE (14 01 036 000) Lokalitet (14 01 037 000) Aarhus",
    "INCOTERM kode (14 01 035 000) CIF Land (14 01 020 000) DK",
    "Samlet fakturebeløb (14 06 001 000) 12345 Fakturavaluta (14 05 001 000) EUR",
    "Gruppe 16 Steder-Lande-Regioner",
    "Bestemmelsesland (16 03 001 000): DK Afsendelsesregion (16 04 001 000):",
    "Afsendelsesland (16 06 001 000): DE",
    "Gruppe 18 Vareoplysninger",
    "Bruttovægt (18 04 001 000): 2.500",
    "Varepost 1",
    "Gruppe 11 Meddelelsesoplysninger",
    "Anmodet procedure (11 09 001 000): 40 Forudgående procedure (11 09 002 000): 00",
    "Supplerende procedurer (11 10 000 000)",
    "Løbenummer Supplerende procedure (11 10 001 000)",
    "1 000",
    "Gruppe 14 Beregningsoplysninger",
    "Værdiansættelsesindikator (14 Varepost fakturaværdi (14 08 001 000): 12345",
    "07 001 000):",
    "Præference (14 11 001 000): 400",
    "Gruppe 16 Steder-Lande-Regioner",
    "Afsendelsesland (16 06 001 000) Oprindelsesland (16 08 001 000) TR",
    "Præference oprindelsesland (16 09 001 TR",
    "000)",
    "Gruppe 18 Vareoplysninger",
    "Nettovægt (18 01 001 000) 2.400",
    "Bruttovægt (18 04 001 000) 2.500",
    "Varebeskrivelse (18 05 001 000) NATRIUMKARBONAT CUS kode (18 08 001 000)",
    "HS-kode (18 09 056 000) 283620 KN-kode (18 09 057 000) 00",
    "TARIC-kode (18 09 058 000) 00",
    "Gruppe 99 Andre dataelementer (statistiske data, garantier, tarifrelaterede data)",
    "Transaktionsart (99 05 001 000) 11 Statistisk værdi (99 06 001 000) 92100",
    "Versioner",
]


def test_dms_print_lines_parse_and_translate():
    from customs.parsers.dms_pdf import looks_like_dms_print, parse_dms_lines

    assert looks_like_dms_print(_DMS_PRINT_LINES) is True
    norm = parse_dms_lines(_DMS_PRINT_LINES)
    t = build_translation(norm, "dms_pdf")

    assert t["direction"] == "ny_til_gammel"
    assert t["lossy_source"] is True

    hdr = {f["key"]: f["value"] for f in t["header_fields"]}
    assert hdr["decltype"] == "IM · H1"
    assert hdr["mrn"] == "26DKTESTPRINT00A1B2"
    assert hdr["lrn"] == "TESTLRN-2026"
    assert hdr["office"] == "DK004700"
    assert hdr["exporter"] == "Testfirma GmbH, Hamburg, DE"
    assert hdr["importer"] == "DK11223344"
    assert hdr["invoice"] == "EUR · 12.345"
    assert hdr["delivery"] == "CIF · Aarhus, DK"
    assert hdr["dispatch"] == "DE" and hdr["destination"] == "DK"
    assert hdr["grosstotal"] == "2.500"

    item = {f["key"]: f["value"] for f in t["item_sections"][0]["fields"]}
    assert item["description"] == "NATRIUMKARBONAT"
    assert item["commodity"] == "283620 · 00 · 00"
    # Indskudte værdier (linjeombrudte elementnumre) fanges korrekt.
    assert item["preforigin"] == "TR"
    assert item["preference"] == "400"
    assert item["procedure"] == "40 · 00 · 000"
    assert item["statvalue"] == "92.100"
    assert item["net"] == "2.400"


def test_legacy_sad_pdf_lines_still_detected_as_legacy():
    from customs.parsers.dms_pdf import looks_like_dms_print

    legacy = ["2 Afsenders navn: X", "32 Varepost nummer: 1", "33 Varekode: 6303929090"]
    assert looks_like_dms_print(legacy) is False
