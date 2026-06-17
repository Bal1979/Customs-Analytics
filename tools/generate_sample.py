"""Generér en syntetisk importdata-fixture (CSV) til tests og udvikling.

ALT er fiktivt og deterministisk (fast seed) og bruges KUN som test-fixture — den
serveres ikke i selve værktøjet (dashboardet starter rent og afventer upload).
Fordelingen er realistisk for en møbel-/tekstilimportør (CN dominerer, møbler HS
9401/9403 toldfri, tekstiler 6,5-12 % told), med indlagte fejlkvalificeringer og
beskrivelsesvarianter, så klassifikations- og fuzzy-analysen har noget at finde.

Kør: python tools/generate_sample.py
"""

from __future__ import annotations

import csv
import random
from pathlib import Path

SEED = 20260616
N_ROWS = 4000
OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "sample_imports.csv"

# Land -> relativ vægt (CN dominerer, typisk for møbel-/tekstilimport).
COUNTRIES = {
    "CN": 55, "VN": 12, "IN": 8, "PK": 7, "TR": 4, "UA": 3,
    "MY": 2, "TW": 2, "ID": 2, "BD": 2, "IL": 1, "EG": 1, "MA": 1,
}

# (HS, generisk varebeskrivelse, told-sats, alt-HS). alt-HS = den kode varen
# LEJLIGHEDSVIS fejlkvalificeres under. Dyne-eksemplet er klassisk: 9404 (3,7 %)
# vs. sengelinned 6302 (12 %). Navnene er bevidst generiske (intet kundespor).
PRODUCTS = [
    ("9401790000", "Lænestol", 0.0, "9401710000"),
    ("9403208000", "Loungesæt metal", 0.0, None),
    ("9401710000", "Spisestol polstret", 0.0, None),
    ("9404909000", "Dyne 200g", 0.037, "6302310000"),
    ("9401610000", "Loungesæt træ", 0.0, None),
    ("9404219000", "Madras", 0.037, None),
    ("6303929090", "Gardin syntetisk", 0.12, None),
    ("9403601000", "Reol træ", 0.0, None),
    ("9401300000", "Kontorstol", 0.0, None),
    ("6302310000", "Sengelinned bomuld", 0.12, None),
    ("6301401000", "Tæppe syntetisk", 0.12, "6301901000"),
    ("3926909290", "Luftmadras", 0.065, "9404909000"),
    ("9404219000", "Pude", 0.037, None),
    ("7013990090", "Glasvase", 0.11, None),
]

# Beskrivelsesvarianter (størrelse/farve/forkortelse) — driver fuzzy matching.
VARIANTS = ["", "", "", " grå", " 60x63cm", " W152xL203", " (B-kval.)", " sort"]

# MFN-sats pr. HS6 (spejler reference/tariff/seed_mfn_rates.csv) — sætter korrekt
# told når en vare fejlkvalificeres under alt-HS.
SEED_RATES = {
    "940130": 0.0, "940161": 0.0, "940171": 0.0, "940179": 0.0, "940320": 0.0,
    "940360": 0.0, "940490": 0.037, "940421": 0.037, "940429": 0.037,
    "630231": 0.12, "630239": 0.12, "630260": 0.12, "630292": 0.12, "630392": 0.12,
    "630140": 0.12, "630190": 0.12, "392690": 0.065, "701399": 0.11,
}

# Fiktive importører/leverandører (ingen reelle virksomheder).
CONSIGNORS = [
    "Nordisk Import A/S", "Skandinavisk Handel ApS", "Dansk Møbelagentur A/S",
    "Continental Trading ApS", "Far East Sourcing Ltd", "Asia Pacific Imports Ltd",
    "Global Textile Co.", "Eastern Furniture Co.", "Pacific Home Ltd",
    "Euro Living ApS", "Hjem & Bolig Import A/S", "Interiør Handel ApS",
    "Møbel Direkte A/S", "Tekstil Agenturet ApS",
]


def _weighted(rng: random.Random, weights: dict[str, int]) -> str:
    keys = list(weights)
    return rng.choices(keys, weights=[weights[k] for k in keys], k=1)[0]


def generate() -> list[dict]:
    rng = random.Random(SEED)
    rows = []
    for _ in range(N_ROWS):
        country = _weighted(rng, COUNTRIES)
        hs, base_desc, rate, alt_hs = rng.choice(PRODUCTS)
        # ~8 % fejlkvalificeres under alt-HS (samme vare, anden kode) når der findes en.
        if alt_hs and rng.random() < 0.08:
            hs = alt_hs
            rate = SEED_RATES.get(hs[:6], rate)
        # ~25 % får en beskrivelsesvariant → kræver fuzzy matching at klynge.
        desc = base_desc + (rng.choice(VARIANTS) if rng.random() < 0.25 else "")
        value = round(rng.lognormvariate(10.5, 1.4), 2)
        # Præference påberåbt (300) i ~15 % → told 0 (præference givet); ellers MFN.
        regime = "100" if rng.random() > 0.15 else "300"
        duty = 0.0 if regime == "300" else round(value * rate, 2)
        month = rng.randint(1, 12)
        day = rng.randint(1, 28)
        net = round(value / rng.uniform(40, 120), 1)
        rows.append(
            {
                "date": f"2025-{month:02d}-{day:02d}",
                "consignor_name": rng.choice(CONSIGNORS),
                "origin_country": country,
                "commodity_code": hs,
                "description": desc,
                "customs_value_dkk": value,
                "customs_duty": duty,
                "invoice_currency": rng.choice(["DKK", "DKK", "DKK", "EUR", "EUR", "NOK", "USD"]),
                "net_mass": net,
                "border_mot": rng.choice(["1", "1", "1", "1", "3", "3", "4"]),
                "inland_mot": rng.choices(["3", "2", "4"], weights=[85, 10, 5])[0],
                "cpc": "4000000" if rng.random() > 0.1 else "4071000",
                "duty_regime_code": regime,
                "shipments": 1,
            }
        )
    return rows


def main() -> None:
    rows = generate()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    total = sum(r["customs_value_dkk"] for r in rows)
    print(f"Skrev {len(rows)} rækker til {OUT}")
    print(f"Samlet toldværdi: {total:,.0f} kr.")


if __name__ == "__main__":
    main()
