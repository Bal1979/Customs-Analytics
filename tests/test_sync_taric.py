"""Tests for TARIC-ingest-pipelinen (tools/sync_taric.py) mod et repræsentativt ekstrakt."""

import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import sync_taric  # noqa: E402
from customs.tariff import TariffDatabase  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures" / "taric_sample"


def test_parse_rate_variants():
    assert sync_taric.parse_rate("12.0 %") == Decimal("0.12")
    assert sync_taric.parse_rate("3.7 %") == Decimal("0.037")
    assert sync_taric.parse_rate("12") == Decimal("0.12")
    assert sync_taric.parse_rate("0.12") == Decimal("0.12")
    assert sync_taric.parse_rate("0.0") == Decimal("0")
    assert sync_taric.parse_rate("12 EUR / 100 kg") is None  # specifik told
    assert sync_taric.parse_rate("") is None


def test_build_reference_extracts_mfn_and_preferences():
    ref = sync_taric.build_reference(
        FIX / "nomenclature.csv", FIX / "measures.csv", FIX / "geo_groups.csv"
    )
    assert ref["mfn"]["6303929090"] == Decimal("0.12")
    assert ref["mfn"]["9404909000"] == Decimal("0.037")
    # Præference fra grupper expanderet til medlemslande.
    assert ref["arrangements"]["VN"]["name"] == "EU–Vietnam (EVFTA)"
    assert ref["arrangements"]["PK"]["type"] == "gsp_plus"
    assert "LK" in ref["arrangements"]


def test_write_reference_only_leaf_codes(tmp_path):
    ref = sync_taric.build_reference(
        FIX / "nomenclature.csv", FIX / "measures.csv", FIX / "geo_groups.csv"
    )
    codes, arrs = sync_taric.write_reference(ref, tmp_path)
    assert codes == 3  # 6303000000 er ikke-leaf og udelades
    assert arrs == 3   # VN, PK, LK
    assert (tmp_path / "mfn_rates.csv").exists()
    assert (tmp_path / "arrangements.json").exists()


def test_tariff_database_consumes_synced_output(tmp_path):
    # End-to-end: synket output kan indlæses af tariferingslaget og bruges til opslag.
    ref = sync_taric.build_reference(
        FIX / "nomenclature.csv", FIX / "measures.csv", FIX / "geo_groups.csv"
    )
    sync_taric.write_reference(ref, tmp_path)
    db = TariffDatabase(reference_dir=tmp_path)
    assert db.source == "mfn_rates.csv"  # foretrækker synket frem for seed
    look = db.lookup("6303929090", "VN")
    assert look.mfn_rate == Decimal("0.12")
    assert look.has_preference and look.preferential_rate == Decimal("0.0")
    assert look.potential_saving_rate == Decimal("0.12")
