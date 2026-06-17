"""Tests for tariferingslaget og de told-faglige tjek."""

from decimal import Decimal
from pathlib import Path

from customs.duty_checks import duty_findings, evaluate_row, fta_opportunities
from customs.parsers.tabular import parse_tabular
from customs.tariff import TariffDatabase

SAMPLE = Path(__file__).resolve().parent / "fixtures" / "sample_imports.csv"


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


def test_temporal_group_membership_gsp_graduation(tmp_path):
    # Land graduereet ud af GSP-gruppen ved udgangen af 2014 (jf. Kina).
    (tmp_path / "mfn_rates.csv").write_text(
        "hs_code,description,mfn_rate\n6302310000,Linned,0.12\n", encoding="utf-8")
    (tmp_path / "seed_arrangements.json").write_text('{"arrangements":{}}', encoding="utf-8")
    (tmp_path / "preferential_rates.csv").write_text(
        "hs_code,area,date_start,date_end,rate,is_quota\n"
        "6302310000,GSP,,,0.096,0\n", encoding="utf-8")   # selve præferencen er åben
    (tmp_path / "geo_areas.json").write_text(
        '{"country_groups":{"CN":[["GSP","1984-01-01","2014-12-31"]]},'
        '"area_name":{"GSP":"GSP - Toldpræferencer"}}', encoding="utf-8")
    db = TariffDatabase(reference_dir=tmp_path)

    assert db.lookup("6302310000", "CN", date="2013-01-01").preferential_rate == Decimal("0.096")
    assert db.lookup("6302310000", "CN", date="2016-01-01").preferential_rate is None  # graduereet ud
    assert db.lookup("6302310000", "CN", date=None).preferential_rate is None           # ikke længere medlem


def test_temporal_mfn_and_suspension(tmp_path):
    # Autonom suspension (type 112) gør tredjelandssatsen 0 % mens den er i kraft.
    (tmp_path / "mfn_rates.csv").write_text(
        "hs_code,description,mfn_rate\n8541100000,Diode,0.05\n", encoding="utf-8")
    (tmp_path / "seed_arrangements.json").write_text('{"arrangements":{}}', encoding="utf-8")
    (tmp_path / "third_country_rates.csv").write_text(
        "hs_code,date_start,date_end,rate\n"
        "8541100000,,,0.05\n"                      # MFN (altid)
        "8541100000,2021-01-01,2023-12-31,0.0\n",  # suspension i en periode
        encoding="utf-8")
    db = TariffDatabase(reference_dir=tmp_path)
    assert db.mfn_rate("8541100000", "2022-06-01") == Decimal("0.0")   # suspension aktiv
    assert db.mfn_rate("8541100000", "2024-06-01") == Decimal("0.05")  # suspension udløbet

    # EDR: en import under suspensionen (betalt 0 %) må IKKE fejl-flagges som for lav.
    rows = [{
        "item_number": 1, "commodity_code": "8541100000", "origin_country": "CN",
        "customs_value_dkk": Decimal("1000"), "customs_duty": Decimal("0"),
        "duty_regime_code": "100", "date": "2022-06-01",
    }]
    assert "CUS-E01" not in {f.code for f in duty_findings(rows, db)}


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
