"""Tests for klassifikationskonsistens og fuzzy matching."""

from decimal import Decimal
from pathlib import Path

from customs.classification import (
    classification_consistency,
    classification_report,
    fuzzy_clusters,
)
from customs.parsers.tabular import parse_tabular
from customs.tariff import TariffDatabase

SAMPLE = Path(__file__).resolve().parent.parent / "sample_data" / "jysk_like_imports.csv"


def _db():
    return TariffDatabase()


def test_exact_consistency_flags_same_desc_different_hs():
    rows = [
        {"description": "Duvet HIMMELBJERG", "commodity_code": "9404909000",
         "customs_value_dkk": Decimal("100000")},
        {"description": "Duvet HIMMELBJERG", "commodity_code": "6302310000",
         "customs_value_dkk": Decimal("100000")},
        {"description": "Recliner STOUBY", "commodity_code": "9401790000",
         "customs_value_dkk": Decimal("50000")},  # kun én kode → ikke flagget
    ]
    clusters = classification_consistency(rows, _db())
    assert len(clusters) == 1
    c = clusters[0]
    assert c["distinct_codes"] == 2
    # Indikativ besparelse = (0.12 − 0.037) × 100.000 for 6302-linjen.
    assert c["potential_saving"] == (Decimal("0.12") - Decimal("0.037")) * Decimal("100000")


def test_exact_consistency_ignores_consistent_products():
    rows = [
        {"description": "Curtain SILKEBORG", "commodity_code": "6303929090", "customs_value_dkk": Decimal("1000")},
        {"description": "Curtain SILKEBORG", "commodity_code": "6303929090", "customs_value_dkk": Decimal("2000")},
    ]
    assert classification_consistency(rows, _db()) == []


def test_fuzzy_clusters_description_variants():
    # Samme vare, varianter i beskrivelsen, men to forskellige HS-koder.
    rows = [
        {"description": "Duvet 200g HIMMELBJERG", "commodity_code": "9404909000", "customs_value_dkk": Decimal("100000")},
        {"description": "Duvet 200g HIMMELBJERG grå", "commodity_code": "9404909000", "customs_value_dkk": Decimal("100000")},
        {"description": "Duvet 200g HIMMELBJERG W152xL203", "commodity_code": "6302310000", "customs_value_dkk": Decimal("100000")},
    ]
    clusters = fuzzy_clusters(rows, _db())
    assert len(clusters) == 1
    assert clusters[0]["distinct_codes"] == 2
    assert len(clusters[0]["variants"]) == 3
    assert clusters[0]["potential_saving"] > 0


def test_fuzzy_does_not_merge_distinct_products():
    rows = [
        {"description": "Recliner chair STOUBY", "commodity_code": "9401790000", "customs_value_dkk": Decimal("1000")},
        {"description": "Glass vase ROMO", "commodity_code": "7013990090", "customs_value_dkk": Decimal("1000")},
    ]
    # Forskellige varer → ingen klynge med flere koder.
    assert fuzzy_clusters(rows, _db()) == []


def test_report_on_sample_finds_inconsistencies():
    rows = parse_tabular(SAMPLE)
    report = classification_report(rows, _db())
    assert len(report["exact"]) > 0
    assert report["fuzzy_saving"] >= report["exact_saving"] > 0
