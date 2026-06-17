"""Tests for legacy SAD-parserens felt-logik (syntetiske data — ingen rigtige angivelser)."""

from decimal import Decimal

from customs.parsers.legacy_sad import _rows_from_lines


HEADER = [
    "2 Afsenders ...",
    "Møntsort: EUR",
    "25 Transportmåde ved grænsen: 1",
    "26 Indenlandsk transportmåde: 3",
    "Forventet ankomstdato: 20230615 kl.0800",
]


def test_single_varepost_maps_sad_boxes():
    lines = HEADER + [
        "32 Varepost nummer: 1",
        "Varebeskrivelse: Testgardin",
        "33 Varekode: 6303929090",
        "34 Oprindelsesland: VN",
        "36 Præference: 300",
        "37 Procedurekode: 4000000",
        "38 Nettomasse: 1000",
        "42 Varens pris: 50000",
        "46 Statistisk værdi: 60000",
        "44.4b Præference dokumentationsnummer: ABC-123",   # må IKKE overskrive boks 36
        "1 A00 60000 0 0 1 142 1001",        # told (A-serie) = 0
        "2 B00 60000 2500 15000.00 2 900 1159",  # moms (B-serie) — tæller ikke som told
    ]
    rows = _rows_from_lines(lines)
    assert len(rows) == 1
    r = rows[0]
    assert r["commodity_code"] == "6303929090"
    assert r["origin_country"] == "VN"
    assert r["duty_regime_code"] == "300"          # boks 36, ikke dokumentationsnummeret
    assert r["customs_value_dkk"] == Decimal("60000")
    assert r["item_invoice_amount"] == Decimal("50000")
    assert r["invoice_currency"] == "EUR"          # hoveddel arvet ned
    assert r["border_mot"] == "1" and r["inland_mot"] == "3"
    assert r["date"] == "2023-06-15"               # normaliseret til ISO (temporal-klar)
    assert r["customs_duty"] == Decimal("0")       # kun A-serien
    assert r["source_format"] == "legacy_sad"


def test_customs_duty_sums_a_series_excludes_vat():
    lines = HEADER + [
        "32 Varepost nummer: 1",
        "33 Varekode: 6302310000",
        "34 Oprindelsesland: IN",
        "46 Statistisk værdi: 100000",
        "1 A00 100000 1200 12000.00 1 142 1001",   # told 12.000
        "2 A20 100000 500 5000.00 1 142 1002",     # anti-dumping (A-serie) 5.000
        "3 B00 100000 2500 29250.00 2 900 1159",   # moms — ekskluderes
    ]
    r = _rows_from_lines(lines)[0]
    assert r["customs_duty"] == Decimal("17000")   # 12.000 + 5.000, ikke moms


def test_multiple_vareposter():
    lines = HEADER + [
        "32 Varepost nummer: 1",
        "33 Varekode: 6303929090",
        "34 Oprindelsesland: VN",
        "46 Statistisk værdi: 60000",
        "1 A00 60000 0 0 1 142 1001",
        "32 Varepost nummer: 2",
        "33 Varekode: 9401790000",
        "34 Oprindelsesland: CN",
        "46 Statistisk værdi: 80000",
        "1 A00 80000 0 0 1 142 1001",
    ]
    rows = _rows_from_lines(lines)
    assert len(rows) == 2
    assert rows[0]["commodity_code"] == "6303929090" and rows[0]["origin_country"] == "VN"
    assert rows[1]["commodity_code"] == "9401790000" and rows[1]["origin_country"] == "CN"
    assert all(r["invoice_currency"] == "EUR" for r in rows)  # hoveddel arvet til begge
