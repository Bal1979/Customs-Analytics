"""Tests for tariferingslaget og de told-faglige tjek."""

from decimal import Decimal
from pathlib import Path

from customs.duty_checks import duty_findings, evaluate_row, fta_opportunities
from customs.parsers.tabular import parse_tabular
from customs.tariff import TariffDatabase

SAMPLE = Path(__file__).resolve().parent.parent / "sample_data" / "jysk_like_imports.csv"


def _db():
    return TariffDatabase()


def test_mfn_lookup_by_prefix():
    db = _db()
    # 10-cifret varekode skal matche 6-cifret seed-prefix.
    assert db.mfn_rate("6303929090") == Decimal("0.12")
    assert db.mfn_rate("9401790000") == Decimal("0.0")
    assert db.mfn_rate("9404909000") == Decimal("0.037")
    assert db.mfn_rate("0000000000") is None


def test_preference_respects_import_date(tmp_path):
    # En FTA der trådte i kraft 2020-08-01 må IKKE anvendes på en import fra 2019.
    (tmp_path / "mfn_rates.csv").write_text(
        "hs_code,description,mfn_rate\n6303929090,Gardiner,0.12\n", encoding="utf-8")
    (tmp_path / "seed_arrangements.json").write_text('{"arrangements":{}}', encoding="utf-8")
    (tmp_path / "preferential_rates.csv").write_text(
        "hs_code,area,date_start,date_end,rate,is_quota\n"
        "6303929090,VN,2020-08-01,,0.0,0\n", encoding="utf-8")
    (tmp_path / "geo_areas.json").write_text(
        '{"country_groups":{},"area_name":{"VN":"Vietnam"}}', encoding="utf-8")
    db = TariffDatabase(reference_dir=tmp_path)

    before = db.lookup("6303929090", "VN", date="2019-05-01")
    assert before.preferential_rate is None and not before.has_preference  # FTA fandtes ikke endnu
    after = db.lookup("6303929090", "VN", date="2021-05-01")
    assert after.preferential_rate == Decimal("0.0") and after.has_preference
    assert db.lookup("6303929090", "VN", date="20210501120000+00").has_preference  # DMS-format


def test_lookup_preference_for_fta_country():
    db = _db()
    look = db.lookup("6303929090", "VN")  # tekstil fra Vietnam
    assert look.mfn_rate == Decimal("0.12")
    assert look.has_preference
    assert look.preferential_rate == Decimal("0.0")
    assert "Vietnam" in look.arrangement
    assert look.potential_saving_rate == Decimal("0.12")


def test_lookup_no_preference_for_china():
    db = _db()
    look = db.lookup("6303929090", "CN")
    assert look.has_preference is False
    assert db.is_no_preference("CN")


def test_missing_fta_opportunity_flagged():
    # Tekstil fra Pakistan (GSP+), ingen præference påberåbt, MFN betalt → P02.
    rows = [{
        "item_number": 1, "commodity_code": "6303929090", "origin_country": "PK",
        "customs_value_dkk": Decimal("100000"), "customs_duty": Decimal("12000"),
        "duty_regime_code": "100",
    }]
    findings = duty_findings(rows, _db())
    assert any(f.code == "CUS-P02" for f in findings)
    ev = evaluate_row(rows[0], _db())
    assert ev["potential_saving"] == Decimal("12000")  # 12% af 100.000


def test_invalid_preference_claim_flagged():
    # Præference påberåbt fra Kina (ingen aftale) → P03 (rød).
    rows = [{
        "item_number": 1, "commodity_code": "6303929090", "origin_country": "CN",
        "customs_value_dkk": Decimal("100000"), "customs_duty": Decimal("0"),
        "duty_regime_code": "300",
    }]
    findings = duty_findings(rows, _db())
    assert any(f.code == "CUS-P03" and f.severity == "red" for f in findings)


def test_no_opportunity_when_mfn_is_zero():
    # Møbler (0% MFN) fra Vietnam → ingen besparelse selv uden præference.
    rows = [{
        "item_number": 1, "commodity_code": "9401790000", "origin_country": "VN",
        "customs_value_dkk": Decimal("100000"), "customs_duty": Decimal("0"),
        "duty_regime_code": "100",
    }]
    assert not any(f.code == "CUS-P02" for f in duty_findings(rows, _db()))


def test_fta_opportunities_aggregates_on_sample():
    rows = parse_tabular(SAMPLE)
    report = fta_opportunities(rows, _db())
    assert report["total_potential_saving"] > 0
    # Mindst ét tekstil-oprindelsesland med aftale skal optræde.
    countries = {b["country"] for b in report["by_country"]}
    assert countries & {"VN", "PK", "BD", "UA", "TR"}
