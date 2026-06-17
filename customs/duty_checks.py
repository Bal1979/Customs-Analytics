"""Told-faglige tjek oven på tariferingslaget.

Tre kerne-tjek (jf. JYSK's "FTA Opportunities" + EDR-analyse):
- **CUS-P02 manglende FTA-mulighed:** ingen præference påberåbt (DutyRegimeCode 100),
  men oprindelseslandet har en aftale med en lavere sats → potentiel besparelse.
- **CUS-P03 ugyldig præference:** præference påberåbt (≠100), men oprindelseslandet
  har ingen kendt aftale → revisions-/toldrisiko.
- **CUS-E01 EDR-rimelighed:** faktisk toldsats afviger væsentligt fra den forventede
  (MFN, eller præferencesats hvis præference er gyldigt påberåbt) → mulig
  fejlklassificering eller fejlberegning.

Begrænsning: anti-dumping, suspensioner, kvoter og mængdetold er ikke modelleret i
seed'et, så EDR-tjekket er bevidst tolerant (GUL, ikke RØD) indtil fuld TARIC-sync.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable, Optional

from customs.sanity import Finding, RED, YELLOW
from customs.schema import NO_PREFERENCE_CODE
from customs.tariff import TariffDatabase

# EDR-tolerance: absolut + relativ, så små satser ikke giver falske positive.
EDR_ABS_TOLERANCE = Decimal("0.015")
EDR_REL_TOLERANCE = Decimal("0.25")


def _dec(value) -> Optional[Decimal]:
    if value in (None, ""):
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return None


def evaluate_row(row: dict, tariff: TariffDatabase) -> dict:
    """Beregn told-faglige nøgletal for én varepost (bruges af tjek + FTA-rapport)."""
    value = _dec(row.get("customs_value_dkk")) or Decimal(0)
    duty = _dec(row.get("customs_duty"))
    regime = row.get("duty_regime_code")
    claims_pref = bool(regime) and str(regime) != NO_PREFERENCE_CODE

    # Importdato → kun præferencer der var i kraft dengang matches (ikke en nyere FTA).
    date = row.get("issue_datetime") or row.get("date")
    look = tariff.lookup(row.get("commodity_code") or row.get("hs_code"),
                         row.get("origin_country"), date=date)
    actual_rate = (duty / value) if (duty is not None and value > 0) else None

    saving = None
    if not claims_pref and look.has_preference and value > 0:
        # Hvad kunne være sparet hvis præferencen var anvendt korrekt.
        paid_rate = actual_rate if actual_rate is not None else (look.mfn_rate or Decimal(0))
        saving = max(Decimal(0), (paid_rate - (look.preferential_rate or Decimal(0)))) * value

    return {
        "value": value,
        "duty": duty,
        "actual_rate": actual_rate,
        "claims_preference": claims_pref,
        "lookup": look,
        "potential_saving": saving,
    }


def duty_findings(rows: Iterable[dict], tariff: TariffDatabase) -> list[Finding]:
    """Producér told-faglige fund (trafiklys) pr. varepost."""
    findings: list[Finding] = []
    for i, row in enumerate(rows, start=1):
        ev = evaluate_row(row, tariff)
        look = ev["lookup"]
        n = row.get("item_number") or i

        # CUS-P02 — manglende FTA-mulighed.
        if ev["potential_saving"] and ev["potential_saving"] > 0:
            quota = " (toldkontingent — verificér at det er åbent)" if look.is_quota else ""
            findings.append(Finding(
                "CUS-P02", YELLOW,
                f"Ingen præference påberåbt, men {look.origin} er omfattet af "
                f"{look.arrangement}. Mulig besparelse ~{ev['potential_saving']:.0f} kr.{quota}",
                n,
            ))

        # CUS-P03 — ugyldig/uunderstøttet præference.
        if ev["claims_preference"] and not look.has_preference:
            findings.append(Finding(
                "CUS-P03", RED,
                f"Præference påberåbt (kode {row.get('duty_regime_code')}), men "
                f"{look.origin} har ingen kendt aftale med EU — toldrisiko.",
                n,
            ))

        # CUS-E01 — EDR-rimelighed.
        expected = (look.preferential_rate if (ev["claims_preference"] and look.has_preference)
                    else look.mfn_rate)
        actual = ev["actual_rate"]
        if expected is not None and actual is not None:
            diff = abs(actual - expected)
            rel = diff / expected if expected > 0 else diff
            if diff > EDR_ABS_TOLERANCE and rel > EDR_REL_TOLERANCE:
                findings.append(Finding(
                    "CUS-E01", YELLOW,
                    f"Faktisk toldsats {actual*100:.1f}% afviger fra forventet "
                    f"{expected*100:.1f}% for varekode {row.get('commodity_code')} — "
                    "mulig fejlklassificering eller fejlberegning.",
                    n,
                ))
    return findings


def fta_opportunities(rows: Iterable[dict], tariff: TariffDatabase) -> dict:
    """Aggregér FTA-besparelsesmuligheder (til 'FTA Opportunities'-siden)."""
    rows = list(rows)
    total_saving = Decimal(0)
    by_country: dict[str, dict] = {}
    by_hs: dict[str, dict] = {}
    invalid_claims = 0
    lines = []

    for row in rows:
        ev = evaluate_row(row, tariff)
        look = ev["lookup"]
        if ev["claims_preference"] and not look.has_preference and tariff.mfn_rate(
            row.get("commodity_code") or row.get("hs_code")
        ):
            invalid_claims += 1
        saving = ev["potential_saving"]
        if not saving or saving <= 0:
            continue
        total_saving += saving
        country = look.origin or "(ukendt)"
        cb = by_country.setdefault(country, {"country": country, "arrangement": look.arrangement,
                                             "saving": Decimal(0), "lines": 0})
        cb["saving"] += saving
        cb["lines"] += 1
        hs = row.get("commodity_code") or row.get("hs_code") or "(ukendt)"
        hb = by_hs.setdefault(hs, {"hs_code": hs, "saving": Decimal(0), "lines": 0})
        hb["saving"] += saving
        hb["lines"] += 1
        lines.append({
            "hs_code": hs, "origin": country, "arrangement": look.arrangement,
            "customs_value": ev["value"], "mfn_rate": look.mfn_rate,
            "preferential_rate": look.preferential_rate, "potential_saving": saving,
            "is_quota": look.is_quota,
        })

    lines.sort(key=lambda r: r["potential_saving"], reverse=True)
    return {
        "total_potential_saving": total_saving,
        "invalid_preference_claims": invalid_claims,
        "by_country": sorted(by_country.values(), key=lambda b: b["saving"], reverse=True),
        "by_hs_code": sorted(by_hs.values(), key=lambda b: b["saving"], reverse=True),
        "lines": lines[:200],
    }
