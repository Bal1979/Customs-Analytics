"""Risici & muligheder — konsolideret analytisk oversigt (INGEN compliance-dom).

Binder porteføljens optimerings- og risikohistorie sammen på tværs af de
eksisterende analyser og tilføjer én ny dimension (EDR-anomalier):

- **Besparelsespotentiale** — uudnyttet frihandelspræference (fra FTA-analysen).
- **Toldrisiko** — påberåbte præferencer uden kendt aftale; told der kan kræves,
  hvis præferencen underkendes.
- **Fejlklassificering** — samme vare på forskellige HS-koder (fra klassifikationen).
- **EDR-anomali (ny)** — vareposter hvor den faktiske effektive toldsats afviger
  væsentligt fra den forventede; en beløbsvægtet outlier-detektion, der kan pege på
  fejlklassificering eller fejlberegning.

Alt rapporteres som **porteføljetal + en prioriteret, beløbssorteret liste** — ikke
en godkendt/afvist-vurdering. Bygger oven på ``duty_checks.evaluate_row``.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from customs.duty_checks import evaluate_row, EDR_ABS_TOLERANCE, EDR_REL_TOLERANCE
from customs.tariff import TariffDatabase


def _line_signals(rows: list[dict], tariff: TariffDatabase) -> tuple[list[dict], list[dict]]:
    """Ét gennemløb → (EDR-anomalier, ugyldige præferencekrav), begge beløbsvægtede."""
    anomalies: list[dict] = []
    invalid_claims: list[dict] = []
    for i, row in enumerate(rows, start=1):
        ev = evaluate_row(row, tariff)
        look = ev["lookup"]
        n = row.get("item_number") or i
        hs = row.get("commodity_code") or row.get("hs_code")
        origin = row.get("origin_country")
        value = ev["value"]

        # Toldrisiko: præference påberåbt, men ingen kendt aftale.
        if ev["claims_preference"] and not look.has_preference:
            mfn = look.mfn_rate or Decimal(0)
            invalid_claims.append({
                "item_number": n, "hs_code": hs, "origin": origin,
                "customs_value": value, "duty_at_risk": value * mfn,
            })

        # EDR-anomali: faktisk effektiv toldsats afviger væsentligt fra forventet.
        expected = (look.preferential_rate if (ev["claims_preference"] and look.has_preference)
                    else look.mfn_rate)
        actual = ev["actual_rate"]
        if expected is not None and actual is not None:
            diff = abs(actual - expected)
            rel = diff / expected if expected > 0 else diff
            if diff > EDR_ABS_TOLERANCE and rel > EDR_REL_TOLERANCE:
                anomalies.append({
                    "item_number": n, "hs_code": hs, "origin": origin,
                    "customs_value": value, "actual_rate": actual,
                    "expected_rate": expected, "deviation": diff,
                    "impact": diff * value,  # kr-magnitude af afvigelsen
                })

    anomalies.sort(key=lambda r: r["impact"], reverse=True)
    invalid_claims.sort(key=lambda r: r["duty_at_risk"], reverse=True)
    return anomalies, invalid_claims


def risk_opportunity_report(rows: Iterable[dict], tariff: TariffDatabase,
                            fta: dict, classification: dict) -> dict:
    """Saml FTA, toldrisiko, fejlklassificering og EDR-anomalier til én analytisk oversigt."""
    rows = list(rows)
    anomalies, invalid_claims = _line_signals(rows, tariff)

    invalid_value = sum((c["duty_at_risk"] for c in invalid_claims), Decimal(0))
    edr_impact = sum((a["impact"] for a in anomalies), Decimal(0))
    exact, fuzzy = classification.get("exact", []), classification.get("fuzzy", [])
    miscls_saving = classification.get("exact_saving", Decimal(0)) + classification.get("fuzzy_saving", Decimal(0))

    kpis = {
        "fta_saving": fta.get("total_potential_saving", Decimal(0)),
        "fta_lines": len(fta.get("lines", [])),
        "invalid_pref_claims": len(invalid_claims),
        "invalid_pref_duty_at_risk": invalid_value,
        "misclassification_cases": len(exact) + len(fuzzy),
        "misclassification_saving": miscls_saving,
        "edr_anomalies": len(anomalies),
        "edr_impact": edr_impact,
    }

    # Prioriteret, beløbssorteret liste på tværs af typer.
    opps: list[dict] = []
    for l in fta.get("lines", [])[:60]:
        opps.append({"type": "FTA-besparelse", "amount": l["potential_saving"],
                     "hs_code": l["hs_code"], "origin": l["origin"],
                     "detail": f"Uudnyttet præference ({l.get('arrangement') or '–'})"
                               + (" — kvote" if l.get("is_quota") else "")})
    for c in invalid_claims[:40]:
        opps.append({"type": "Toldrisiko", "amount": c["duty_at_risk"],
                     "hs_code": c["hs_code"], "origin": c["origin"],
                     "detail": "Præference påberåbt uden kendt aftale — told kan kræves"})
    for g in exact[:30]:
        code = g["codes"][0]["hs_code"] if g.get("codes") else ""
        opps.append({"type": "Fejlklassificering", "amount": g.get("potential_saving", Decimal(0)),
                     "hs_code": code, "origin": "",
                     "detail": f"'{g['product']}' på {g['distinct_codes']} forskellige HS-koder"})
    for a in anomalies[:30]:
        opps.append({"type": "EDR-anomali", "amount": a["impact"],
                     "hs_code": a["hs_code"], "origin": a["origin"],
                     "detail": f"Faktisk {a['actual_rate'] * 100:.1f}% vs. forventet {a['expected_rate'] * 100:.1f}%"})

    opps.sort(key=lambda o: o["amount"], reverse=True)

    return {
        "kpis": kpis,
        "opportunities": opps[:50],
        "edr_anomalies": anomalies[:100],
    }
