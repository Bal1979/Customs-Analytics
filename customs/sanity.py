"""Sanity-tjek på en kanonisk ``Declaration``.

Hvert tjek returnerer ``Finding``-objekter med en kode, alvorlighed og besked.
Tjekkene her er dem, der kan køre *uden* ekstern referencedata (struktur, format,
intern konsistens) plus de told-faglige tjek, der kun kræver oplysninger i selve
angivelsen. Tjek der kræver Taric-satser / FTA-dækning hører til senere faser og
markeres med TODO.

Reglerne er forankret i DMS-vejledningen og Toldstyrelsens forretningsregler
(reference/codelists/Validation rules and Error codes.xlsx) — koblingen
dokumenteres pr. tjek, så kataloget er sporbart (som SAF-T's regelkatalog).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from customs.schema import Declaration, GoodsItem, NO_PREFERENCE_CODE

# Alvorlighed følger trafiklys-semantikken fra VIES: RØD = handling krævet,
# GUL = gennemse, INFO = oplysende.
RED = "red"
YELLOW = "yellow"
INFO = "info"


@dataclass
class Finding:
    code: str
    severity: str
    message: str
    item_number: int | None = None


def check_declaration(decl: Declaration) -> list[Finding]:
    """Kør alle Fase-0-sanity-tjek og returnér en samlet liste af fund."""
    findings: list[Finding] = []
    findings += _check_weight_totals(decl)
    for item in decl.goods_items:
        findings += _check_item(item)
    return findings


def _check_weight_totals(decl: Declaration) -> list[Finding]:
    """CUS-W01: samlet bruttovægt ≥ Σ varepost-bruttovægt (DMS-vejledning gr. 18)."""
    if decl.gross_mass_total is None:
        return []
    line_sum = sum(
        (it.gross_mass for it in decl.goods_items if it.gross_mass is not None),
        Decimal(0),
    )
    if line_sum and decl.gross_mass_total < line_sum:
        return [
            Finding(
                "CUS-W01",
                RED,
                f"Samlet bruttovægt ({decl.gross_mass_total}) er mindre end summen "
                f"af vareposternes bruttovægt ({line_sum}).",
            )
        ]
    return []


def _check_item(it: GoodsItem) -> list[Finding]:
    f: list[Finding] = []
    n = it.item_number

    # CUS-H01: varekode skal være 10 cifre (HS 6 + KN 2 + TARIC 2).
    code = it.commodity_code
    if code is None:
        f.append(Finding("CUS-H01", RED, "Varekode mangler.", n))
    elif not (code.isdigit() and len(code) == 10):
        f.append(
            Finding(
                "CUS-H01",
                RED,
                f"Varekode '{code}' er ikke 10 cifre (HS6+KN2+TARIC2).",
                n,
            )
        )

    # CUS-W02: nettovægt ≤ bruttovægt pr. linje.
    if it.net_mass is not None and it.gross_mass is not None and it.net_mass > it.gross_mass:
        f.append(
            Finding(
                "CUS-W02",
                RED,
                f"Nettovægt ({it.net_mass}) overstiger bruttovægt ({it.gross_mass}).",
                n,
            )
        )

    # CUS-C01: CPC skal kunne dannes som 7 tegn (2+2+3).
    cpc = it.cpc
    if cpc is None:
        f.append(Finding("CUS-C01", YELLOW, "Procedurekode (CPC) mangler.", n))
    elif len(cpc) != 7:
        f.append(
            Finding("CUS-C01", YELLOW, f"Procedurekode '{cpc}' er ikke 7 tegn.", n)
        )

    # CUS-P01: påberåbes præference (DutyRegimeCode ≠ 100), bør præference-
    # oprindelsesland være sat (Origin TypeCode 2) — ellers er kravet ufuldstændigt.
    if it.claims_preference and not it.preferential_origin_country:
        f.append(
            Finding(
                "CUS-P01",
                YELLOW,
                f"Præference påberåbt (kode {it.duty_regime_code}), men "
                "præference-oprindelsesland mangler.",
                n,
            )
        )

    # CUS-V01: toldværdi (statistisk værdi i DKK) bør være udfyldt og positiv.
    if it.statistical_value is None:
        f.append(Finding("CUS-V01", YELLOW, "Toldværdi (statistisk værdi) mangler.", n))
    elif it.statistical_value <= 0:
        f.append(
            Finding("CUS-V01", YELLOW, f"Toldværdi er ikke positiv ({it.statistical_value}).", n)
        )

    # CUS-O01: oprindelsesland skal være udfyldt.
    if not it.origin_country:
        f.append(Finding("CUS-O01", RED, "Oprindelsesland mangler.", n))

    # TODO (Fase 2, kræver referencedata):
    #   CUS-P02 manglende FTA-mulighed: DutyRegimeCode=100 men oprindelsesland har
    #           en gældende aftale med EU.
    #   CUS-E01 EDR-rimelighed: faktisk EDR vs. forventet MFN-sats for HS-koden.
    #   CUS-V02 statistisk værdi ≥ fakturaværdi omregnet til DKK via vekselkurs.
    return f
