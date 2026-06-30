"""Scenarier til valideringssuiten — én plantet defekt pr. implementeret kontrol.

Hvert scenarie tager en REN baseline (en gyldig angivelse / række, der ikke
udløser fund) og planter præcis ÉN defekt, så netop den tilsigtede kontrol fyrer.
Kontrollerne køres via deres rigtige indgange:

- Sanity-kontroller (CUS-W/H/C/V/O/P01) → ``customs.sanity.check_declaration``
- Told-kontroller (CUS-P02/P03/E01)     → ``customs.duty_checks.duty_findings``
- Klassifikation (CUS-K01/K02)          → ``customs.classification`` (eksakt/fuzzy)

Tariferings-/klassifikationsscenarier bruger den rigtige ``TariffDatabase`` og
kendte HS×oprindelse-kombinationer (gardin 6303929090: MFN 12 %, VN-præference
0 %, CN ingen aftale).
"""

from __future__ import annotations

import copy
from decimal import Decimal

from customs.schema import Declaration, GoodsItem

# Importdato hvor EU-Vietnam-aftalen (EVFTA, 2020-08-01) er i kraft.
DATE = "2025-06-01"
CURTAIN = "6303929090"   # gardin syntetisk — MFN 12 %
SHEET = "6302310000"     # sengelinned bomuld — anden HS (til klassifikation)


# ---------------------------------------------------------------------------
# Ren baseline (alle sanity-tjek passerer)
# ---------------------------------------------------------------------------

def base_declaration() -> Declaration:
    """En gyldig 1-linjes angivelse uden fejl — udløser ingen sanity-fund."""
    item = GoodsItem(
        item_number=1,
        description="Gardin syntetisk",
        hs_code="630392", cn_code="90", taric_code="90",   # → 6303929090 (10 cifre)
        origin_country="VN",
        procedure_current="40", procedure_previous="00",
        supplementary_procedures=["000"],                    # → CPC 4000000 (7 tegn)
        duty_regime_code="100",                              # ingen præference påberåbt
        statistical_value=Decimal("10000"),
        gross_mass=Decimal("100"), net_mass=Decimal("90"),
    )
    return Declaration(
        procedure_category="H1",
        gross_mass_total=Decimal("100"),                     # ≥ Σ linje-brutto
        goods_items=[item],
    )


def base_row() -> dict:
    """En told-faglig ren række (MFN betalt, ingen præference påberåbt)."""
    return {
        "item_number": 1,
        "commodity_code": CURTAIN,
        "description": "Gardin syntetisk",
        "origin_country": "CN",            # ingen FTA → ingen P02
        "date": DATE,
        "duty_regime_code": "100",
        "customs_value_dkk": Decimal("10000"),
        "customs_duty": Decimal("1200"),   # 12 % = forventet MFN → ingen E01
    }


# ---------------------------------------------------------------------------
# Sanity-scenarier: (rule, titel, defekt-beskrivelse, mutate(decl))
# ---------------------------------------------------------------------------

def _set_item(decl: Declaration, **kw) -> None:
    for k, v in kw.items():
        setattr(decl.goods_items[0], k, v)


SANITY_SCENARIOS = [
    ("CUS-H01", "Varekode er 10 cifre",
     "TARIC-led afkortet → 9-cifret varekode",
     lambda d: _set_item(d, taric_code="9")),
    ("CUS-C01", "Procedurekode (CPC) er 7 tegn",
     "Supplerende procedurekode 2 tegn → CPC bliver 6 tegn",
     lambda d: _set_item(d, supplementary_procedures=["00"])),
    ("CUS-W01", "Samlet bruttovægt ≥ Σ linje-brutto",
     "Samlet bruttovægt (50) < linjesum (100)",
     lambda d: setattr(d, "gross_mass_total", Decimal("50"))),
    ("CUS-W02", "Nettovægt ≤ bruttovægt pr. linje",
     "Nettovægt (150) > bruttovægt (100)",
     lambda d: _set_item(d, net_mass=Decimal("150"))),
    ("CUS-V01", "Toldværdi udfyldt og positiv",
     "Toldværdi sat til 0",
     lambda d: _set_item(d, statistical_value=Decimal("0"))),
    ("CUS-O01", "Oprindelsesland udfyldt",
     "Oprindelsesland fjernet",
     lambda d: _set_item(d, origin_country=None)),
    ("CUS-P01", "Præference påberåbt → præference-oprindelse påkrævet",
     "Præference påberåbt (300) uden præference-oprindelsesland",
     lambda d: _set_item(d, duty_regime_code="300", preferential_origin_country=None)),
]


# ---------------------------------------------------------------------------
# Told-scenarier: (rule, titel, defekt, row)
# ---------------------------------------------------------------------------

def _row(**overrides) -> dict:
    r = base_row()
    r.update(overrides)
    return r


DUTY_SCENARIOS = [
    ("CUS-P02", "Manglende FTA-mulighed",
     "VN-oprindelse med præference, men ingen præference påberåbt (told betalt MFN)",
     _row(origin_country="VN", duty_regime_code="100", customs_duty=Decimal("1200"))),
    ("CUS-P03", "Ugyldig præference",
     "Præference påberåbt (300) for CN, der ingen aftale har med EU",
     _row(origin_country="CN", duty_regime_code="300", customs_duty=Decimal("1200"))),
    ("CUS-E01", "EDR-rimelighed",
     "CN-gardin (MFN 12 %), men told betalt 0 → effektiv sats 0 %",
     _row(origin_country="CN", duty_regime_code="100", customs_duty=Decimal("0"))),
]


# ---------------------------------------------------------------------------
# Klassifikations-scenarier: (rule, titel, defekt, rows, mode)
#   mode: "exact" → classification_consistency, "fuzzy" → fuzzy_clusters
# ---------------------------------------------------------------------------

CLASSIFICATION_SCENARIOS = [
    ("CUS-K01", "Eksakt klassifikationskonsistens",
     "Samme beskrivelse 'Gardin' på to forskellige HS-koder", "exact",
     [
         {"description": "Gardin", "commodity_code": CURTAIN, "customs_value_dkk": Decimal("8000")},
         {"description": "Gardin", "commodity_code": SHEET, "customs_value_dkk": Decimal("9000")},
     ]),
    ("CUS-K02", "Fuzzy klassifikationsklynger",
     "Varianter 'Gardin syntetisk grå' og '... sort' på to HS-koder",
     "fuzzy",
     [
         {"description": "Gardin syntetisk grå", "commodity_code": CURTAIN, "customs_value_dkk": Decimal("8000")},
         {"description": "Gardin syntetisk sort", "commodity_code": SHEET, "customs_value_dkk": Decimal("9000")},
     ]),
]


def all_scenario_rules() -> list[str]:
    """Alle kontrol-ID'er, suiten dækker (til kryds-tjek mod kataloget)."""
    return ([r for r, *_ in SANITY_SCENARIOS]
            + [r for r, *_ in DUTY_SCENARIOS]
            + [r for r, *_ in CLASSIFICATION_SCENARIOS])
