"""Generér en syntetisk, JYSK-lignende importdatafixture (CSV).

Bruges til at udvikle/demo'e dashboards og teste analyselaget på realistiske
datamængder, indtil rigtige data (AEO-eksport e.l.) foreligger. ALT er fiktivt og
deterministisk (fast seed), så testene er reproducerbare.

Fordelingen efterligner JYSK-forlægget: CN dominerer, møbler (HS 9401/9403) toldfri,
tekstiler (HS 6302/6303/9404) med 6,5–12 % told, overvejende søtransport, CPC 4000000.

Kør: python tools/generate_sample.py
"""

from __future__ import annotations

import csv
import random
from pathlib import Path

SEED = 20260616
N_ROWS = 4000
OUT = Path(__file__).resolve().parent.parent / "sample_data" / "jysk_like_imports.csv"

# Land -> relativ vægt (CN dominerer, jf. forlægget).
COUNTRIES = {
    "CN": 55, "VN": 12, "IN": 8, "PK": 7, "TR": 4, "UA": 3,
    "MY": 2, "TW": 2, "ID": 2, "BD": 2, "IL": 1, "EG": 1, "MA": 1,
}

# (HS, varebeskrivelse, told-sats, alt-HS). alt-HS = den kode varen LEJLIGHEDSVIS
# fejlkvalificeres under (samme vare, anden kvalificering). Dyne-eksemplet er klassisk:
# 9404 (3,7 %) vs. sengelinned 6302 (12 %) — stor toldforskel.
PRODUCTS = [
    ("9401790000", "Recliner chair STOUBY", 0.0, "9401710000"),
    ("9403208000", "Lounge set FJELLERUP", 0.0, None),
    ("9401710000", "Dining chair JONSTRUP", 0.0, None),
    ("9404909000", "Duvet 200g HIMMELBJERG", 0.037, "6302310000"),
    ("9401610000", "Lounge set VONGE", 0.0, None),
    ("9404219000", "Mattress GULDAGER", 0.037, None),
    ("6303929090", "Curtain SILKEBORG", 0.12, None),
    ("9403601000", "Bookshelf TAMBOHUSE", 0.0, None),
    ("9401300000", "Office chair GUDHJEM", 0.0, None),
    ("6302310000", "Bed linen NEXO", 0.12, None),
    ("6301401000", "Blanket SKAGEN", 0.12, "6301901000"),
    ("3926909290", "Air bed VELOUR DURABEAM", 0.065, "9404909000"),
    ("9404219000", "Pillow KRONBORG", 0.037, None),
    ("7013990090", "Glass vase ROMO", 0.11, None),
]

# Beskrivelsesvarianter (størrelse/farve/forkortelse) — driver fuzzy matching.
VARIANTS = ["", "", "", " grå", " 60x63cm", " W152xL203", " (B-kval.)", " sort"]

# MFN-sats pr. HS6 (spejler reference/tariff/seed_mfn_rates.csv) — bruges til at
# sætte korrekt told når en vare fejlkvalificeres under alt-HS.
SEED_RATES = {
    "940130": 0.0, "940161": 0.0, "940171": 0.0, "940179": 0.0, "940320": 0.0,
    "940360": 0.0, "940490": 0.037, "940421": 0.037, "940429": 0.037,
    "630231": 0.12, "630239": 0.12, "630260": 0.12, "630292": 0.12, "630392": 0.12,
    "630140": 0.12, "630190": 0.12, "392690": 0.065, "701399": 0.11,
}

CURRENCIES = ["DKK", "DKK", "DKK", "EUR", "EUR", "NOK", "USD"]
MOT = ["1", "1", "1", "1", "3", "3", "4"]  # overvejende søtransport, lidt vej/luft
CONSIGNORS = [
    "JYSK A/S", "2-Connect ApS", "Actona Company A/S", "LetRight Industrial Corp., LTD",
    "Trade Point A/S", "SourceByNet Pte. Ltd.", "ScanCom International A/S",
    "Healthcare Co., LTD", "Schou", "X-Mile ApS", "Intex Development Company Ltd",
    "Multi Lines International Co. Ltd.", "Zolo", "Unique Furniture A/S",
]


def _weighted(rng: random.Random, weights: dict[str, int]) -> str:
    keys = list(weights)
    return rng.choices(keys, weights=[weights[k] for k in keys], k=1)[0]


def generate() -> list[dict]:
    rng = random.Random(SEED)
    rows = []
    for i in range(N_ROWS):
        country = _weighted(rng, COUNTRIES)
        hs, base_desc, rate, alt_hs = rng.choice(PRODUCTS)
        # ~8 % fejlkvalificeres under alt-HS (samme vare, anden kode) når der findes en.
        if alt_hs and rng.random() < 0.08:
            hs = alt_hs
            rate = SEED_RATES.get(hs[:6], rate)
        # ~25 % får en beskrivelsesvariant → kræver fuzzy matching at klynge.
        desc = base_desc + (rng.choice(VARIANTS) if rng.random() < 0.25 else "")
        # Lognormal-agtig værdifordeling: mange små, få meget store.
        value = round(rng.lognormvariate(10.5, 1.4), 2)
        # Præference påberåbt (300) i ~15 % af tilfældene → told 0 (præference givet);
        # ellers betales MFN-satsen. Gør demodata sammenhængende med told-tjekkene.
        regime = "100" if rng.random() > 0.15 else "300"
        duty = 0.0 if regime == "300" else round(value * rate, 2)
        month = rng.randint(1, 12)
        day = rng.randint(1, 28)
        net = round(value / rng.uniform(40, 120), 1)  # kr/kg -> kg
        rows.append(
            {
                "date": f"2025-{month:02d}-{day:02d}",
                "consignor_name": rng.choice(CONSIGNORS),
                "origin_country": country,
                "commodity_code": hs,
                "description": desc,
                "customs_value_dkk": value,
                "customs_duty": duty,
                "invoice_currency": rng.choice(CURRENCIES),
                "net_mass": net,
                "border_mot": rng.choice(MOT),
                # Indland: oftest vejtransport (varer kører videre fra havn/grænse).
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
