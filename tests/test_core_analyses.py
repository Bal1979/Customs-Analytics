"""Tests for de udvidede kerne-analyser: leverandør, CPC, transport, sourcing."""

from decimal import Decimal

from customs.analytics import (
    build_report,
    cpc_analysis,
    sourcing_analysis,
    supplier_overview,
    transport_analysis,
)


def _rows():
    return [
        {"consignor_name": "Nordisk Import A/S", "origin_country": "CN", "commodity_code": "9401790000",
         "customs_value_dkk": Decimal("1000"), "customs_duty": Decimal("0"),
         "border_mot": "1", "inland_mot": "3", "net_mass": Decimal("100"), "cpc": "4000000"},
        {"consignor_name": "Nordisk Import A/S", "origin_country": "VN", "commodity_code": "6303929090",
         "customs_value_dkk": Decimal("500"), "customs_duty": Decimal("60"),
         "border_mot": "1", "inland_mot": "3", "net_mass": Decimal("40"), "cpc": "4000000"},
        {"consignor_name": "Schou", "origin_country": "CN", "commodity_code": "6303929090",
         "customs_value_dkk": Decimal("300"), "customs_duty": Decimal("36"),
         "border_mot": "3", "inland_mot": "2", "net_mass": Decimal("20"), "cpc": "4071000"},
    ]


def test_supplier_overview_counts_countries_and_aggregates():
    sup = supplier_overview(_rows())
    nordisk = next(s for s in sup if s["consignor"] == "Nordisk Import A/S")
    assert nordisk["countries_count"] == 2          # CN + VN
    assert nordisk["customs_value"] == Decimal("1500")
    assert nordisk["import_duty"] == Decimal("60")
    assert sup[0]["consignor"] == "Nordisk Import A/S"      # sorteret efter toldværdi


def test_cpc_analysis_shares_sum_to_one():
    cpc = cpc_analysis(_rows())
    total_share = sum(b["share"] for b in cpc)
    assert abs(total_share - Decimal("1")) < Decimal("0.0001")
    main = next(b for b in cpc if b["cpc"] == "4000000")
    assert main["customs_value"] == Decimal("1500")


def test_transport_border_and_inland():
    t = transport_analysis(_rows())
    sea = next(b for b in t["by_border"] if b["mot"] == "1")
    assert sea["mot_label"] == "Søtransport"
    assert sea["customs_value"] == Decimal("1500")
    assert sea["net_mass"] == Decimal("140")
    road_inland = next(b for b in t["by_inland"] if b["mot"] == "3")
    assert road_inland["customs_value"] == Decimal("1500")


def test_sourcing_returns_country_and_hs_tables():
    src = sourcing_analysis(_rows())
    assert src["by_country"][0]["country"] == "CN"  # 1000 + 300 = 1300 > VN 500
    hs = {b["hs_code"]: b for b in src["by_hs_code"]}
    assert hs["6303929090"]["customs_value"] == Decimal("800")


def test_build_report_has_all_sections():
    report = build_report(_rows())
    assert set(report) == {"summary", "suppliers", "sourcing", "cpc", "transport"}
    assert report["summary"]["kpis"]["customs_value"] == Decimal("1800")
