"""Tests for den konsoliderede risiko-/mulighedsanalyse (customs/risk_analysis.py)."""

from decimal import Decimal

from customs.tariff import TariffDatabase
from customs.duty_checks import fta_opportunities
from customs.classification import classification_report
from customs.risk_analysis import risk_opportunity_report, _line_signals

TAR = TariffDatabase()
CURTAIN = "6303929090"  # gardin syntetisk — MFN 12 %


def _row(**kw):
    base = {
        "item_number": 1, "commodity_code": CURTAIN, "description": "Gardin",
        "origin_country": "CN", "date": "2025-06-01", "duty_regime_code": "100",
        "customs_value_dkk": Decimal("10000"), "customs_duty": Decimal("1200"),
    }
    base.update(kw)
    return base


def test_edr_anomaly_detected_and_weighted():
    # CN-gardin (MFN 12 %) men told betalt 0 → faktisk 0 % vs. forventet 12 % → anomali.
    anomalies, _ = _line_signals([_row(customs_duty=Decimal("0"))], TAR)
    assert len(anomalies) == 1
    assert anomalies[0]["hs_code"] == CURTAIN
    assert anomalies[0]["impact"] > 0  # beløbsvægtet


def test_invalid_preference_claim_is_risk():
    # CN påberåber præference (300) uden kendt aftale → toldrisiko med told i risiko.
    _, invalid = _line_signals([_row(duty_regime_code="300")], TAR)
    assert len(invalid) == 1
    assert invalid[0]["duty_at_risk"] > 0


def test_clean_line_yields_no_signals():
    # CN-gardin med korrekt MFN-told (12 %) → hverken anomali eller risiko.
    anomalies, invalid = _line_signals([_row()], TAR)
    assert anomalies == [] and invalid == []


def test_report_structure_and_amount_sorted():
    rows = [_row(customs_duty=Decimal("0")), _row(item_number=2)]
    fta = fta_opportunities(rows, TAR)
    cls = classification_report(rows, TAR)
    rep = risk_opportunity_report(rows, TAR, fta, cls)
    assert set(rep) == {"kpis", "opportunities", "edr_anomalies"}
    assert "fta_saving" in rep["kpis"] and "edr_impact" in rep["kpis"]
    amounts = [o["amount"] for o in rep["opportunities"]]
    assert amounts == sorted(amounts, reverse=True)  # prioriteret, beløbssorteret
