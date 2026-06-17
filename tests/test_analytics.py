"""Tests for analyselaget (Imports Summary) og Excel/CSV-adapteren."""

from decimal import Decimal
from pathlib import Path

from customs.analytics import imports_summary
from customs.parsers.tabular import parse_tabular

SAMPLE = Path(__file__).resolve().parent.parent / "sample_data" / "jysk_like_imports.csv"


def _rows():
    return [
        {"origin_country": "CN", "commodity_code": "9401790000", "description": "Chair",
         "customs_value_dkk": Decimal("1000"), "customs_duty": Decimal("0"),
         "issue_datetime": "2025-01-15", "border_mot": "1", "cpc": "4000000"},
        {"origin_country": "CN", "commodity_code": "6303929090", "description": "Curtain",
         "customs_value_dkk": Decimal("500"), "customs_duty": Decimal("60"),
         "issue_datetime": "2025-02-10", "border_mot": "3", "cpc": "4000000"},
        {"origin_country": "VN", "commodity_code": "9401790000", "description": "Chair",
         "customs_value_dkk": Decimal("300"), "customs_duty": Decimal("0"),
         "issue_datetime": "2025-02-20", "border_mot": "1", "cpc": "4071000"},
    ]


def test_kpis_aggregate_correctly():
    s = imports_summary(_rows())
    k = s["kpis"]
    assert k["customs_value"] == Decimal("1800")
    assert k["import_duty"] == Decimal("60")
    assert k["shipments"] == 3
    assert k["lines"] == 3
    assert k["effective_duty_rate"] == Decimal("60") / Decimal("1800")


def test_by_origin_sorted_desc():
    s = imports_summary(_rows())
    origins = s["by_origin"]
    assert origins[0]["country"] == "CN"
    assert origins[0]["customs_value"] == Decimal("1500")
    assert origins[1]["country"] == "VN"


def test_by_hs_aggregates_same_code():
    s = imports_summary(_rows())
    chair = next(b for b in s["by_hs_code"] if b["hs_code"] == "9401790000")
    assert chair["customs_value"] == Decimal("1300")  # 1000 + 300


def test_time_series_grouped_by_month():
    s = imports_summary(_rows())
    months = {p["month"]: p for p in s["time_series"]}
    assert set(months) == {"2025-01", "2025-02"}
    assert months["2025-02"]["customs_value"] == Decimal("800")  # 500 + 300


def test_tabular_csv_roundtrip_on_sample():
    rows = parse_tabular(SAMPLE)
    assert len(rows) == 4000
    s = imports_summary(rows)
    assert s["kpis"]["customs_value"] > 0
    assert len(s["time_series"]) == 12
    # CN skal være største oprindelsesland i den syntetiske fordeling.
    assert s["by_origin"][0]["country"] == "CN"


def test_tabular_maps_both_transport_modes():
    # Regression: inland_mot skal mappes, ikke kun border_mot (ellers bliver
    # indenlandsk transport "(ukendt)" i transportanalysen).
    rows = parse_tabular(SAMPLE)
    assert any(r.get("border_mot") for r in rows)
    assert any(r.get("inland_mot") for r in rows)


def test_tabular_handles_danish_number_format():
    csv_text = (
        "oprindelsesland;varekode;toldværdi;told;dato\n"
        "CN;9401790000;1.234.567,89;0,00;2025-03-01\n"
    )
    rows = parse_tabular(csv_text.encode(), filename="x.csv")
    assert rows[0]["customs_value_dkk"] == Decimal("1234567.89")
    assert rows[0]["origin_country"] == "CN"
