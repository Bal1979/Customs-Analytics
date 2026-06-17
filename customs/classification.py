"""Klassifikationsanalyse — finder fejlkvalificering (samme vare, forskellig HS-kode).

To niveauer, i to niveauer:
- **Eksakt konsistens** (`classification_consistency`): samme varebeskrivelse →
  flere forskellige HS-koder = oplagte fejl (høj konfidens).
- **Fuzzy matching** (`fuzzy_clusters`): klynger *lignende* beskrivelser (varianter,
  størrelser, forkortelser) sammen og flagger klynger med flere HS-koder. Bredere,
  lavere konfidens — fanger det den eksakte gruppering misser.

Begge beregner en *indikativ* besparelse ved at tilpasse til den laveste anvendte
MFN-sats i gruppen (kræver klassifikationsfaglig vurdering før brug). Ingen eksterne
afhængigheder — fuzzy-lighed er token-Jaccard med blokning på sjældent token.
"""

from __future__ import annotations

import re
from collections import defaultdict
from decimal import Decimal
from typing import Iterable, Optional

from customs.tariff import TariffDatabase

# Tokens uden klassifikationsværdi (farve/kvalitet/enheder) — fjernes så varianter
# af samme vare klynger sammen.
_STOPWORDS = {
    "grå", "graa", "sort", "hvid", "blå", "blaa", "rød", "roed", "grøn", "groen",
    "kval", "bkval", "cm", "stk", "sæt", "saet", "med", "uden", "til", "og",
}
_DIM = re.compile(r"\d")  # tokens med cifre (størrelser/mål) droppes


def _tokens(description: str) -> frozenset[str]:
    raw = re.split(r"[^0-9a-zA-ZæøåÆØÅ]+", (description or "").lower())
    return frozenset(
        t for t in raw
        if len(t) >= 3 and not _DIM.search(t) and t not in _STOPWORDS
    )


def _dec(value) -> Decimal:
    if value in (None, ""):
        return Decimal(0)
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _code(row: dict) -> Optional[str]:
    return row.get("commodity_code") or row.get("hs_code")


def _group_summary(rows: list[dict], tariff: TariffDatabase, label: str) -> dict:
    """Opsummér en gruppe rækker med >1 HS-kode: koder, værdi og indikativ besparelse."""
    codes: dict[str, dict] = {}
    for r in rows:
        code = _code(r)
        b = codes.setdefault(code, {"hs_code": code, "lines": 0, "customs_value": Decimal(0),
                                    "mfn_rate": tariff.mfn_rate(code)})
        b["lines"] += 1
        b["customs_value"] += _dec(r.get("customs_value_dkk"))
    rates = [c["mfn_rate"] for c in codes.values() if c["mfn_rate"] is not None]
    min_rate = min(rates) if rates else None
    saving = Decimal(0)
    if min_rate is not None:
        for c in codes.values():
            if c["mfn_rate"] is not None and c["mfn_rate"] > min_rate:
                saving += (c["mfn_rate"] - min_rate) * c["customs_value"]
    return {
        "product": label,
        "distinct_codes": len(codes),
        "codes": sorted(codes.values(), key=lambda c: c["customs_value"], reverse=True),
        "total_value": sum((c["customs_value"] for c in codes.values()), Decimal(0)),
        "mfn_min": min_rate,
        "mfn_max": max(rates) if rates else None,
        "potential_saving": saving,
    }


def classification_consistency(rows: Iterable[dict], tariff: TariffDatabase) -> list[dict]:
    """Eksakt: samme (normaliserede) beskrivelse → flere HS-koder = oplagt inkonsistens."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        desc = (r.get("description") or "").strip()
        if desc and _code(r):
            groups[" ".join(desc.lower().split())].append(r)
    out = []
    for items in groups.values():
        if len({_code(r) for r in items}) > 1:
            out.append(_group_summary(items, tariff, items[0]["description"]))
    out.sort(key=lambda g: g["potential_saving"], reverse=True)
    return out


def fuzzy_clusters(rows: Iterable[dict], tariff: TariffDatabase, threshold: float = 0.5) -> list[dict]:
    """Fuzzy: klynger lignende beskrivelser (token-Jaccard) og flag klynger m. flere HS-koder."""
    items = [r for r in rows if (r.get("description") and _code(r))]
    toks = {id(r): _tokens(r["description"]) for r in items}

    # Dokumentfrekvens pr. token → blok på det sjældneste (mest distinktive) token.
    df: dict[str, int] = defaultdict(int)
    for r in items:
        for t in toks[id(r)]:
            df[t] += 1

    def block_key(r) -> str:
        ts = toks[id(r)]
        return min(ts, key=lambda t: (df[t], t)) if ts else ""

    blocks: dict[str, list] = defaultdict(list)
    for r in items:
        blocks[block_key(r)].append(r)

    clusters: list[list[dict]] = []
    for block in blocks.values():
        reps: list[tuple[frozenset, list]] = []  # (repræsentativt token-sæt, medlemmer)
        for r in block:
            ts = toks[id(r)]
            placed = False
            for rep_ts, members in reps:
                union = ts | rep_ts
                jac = len(ts & rep_ts) / len(union) if union else 0
                if jac >= threshold:
                    members.append(r)
                    placed = True
                    break
            if not placed:
                reps.append((ts, [r]))
        clusters.extend(m for _, m in reps)

    out = []
    for members in clusters:
        if len({_code(r) for r in members}) > 1:
            descs = sorted({r["description"] for r in members})
            summary = _group_summary(members, tariff, descs[0])
            summary["variants"] = descs
            summary["lines_total"] = len(members)
            out.append(summary)
    out.sort(key=lambda g: g["potential_saving"], reverse=True)
    return out


def classification_report(rows: Iterable[dict], tariff: TariffDatabase) -> dict:
    """Saml begge analyser til UI-siden."""
    rows = list(rows)
    exact = classification_consistency(rows, tariff)
    fuzzy = fuzzy_clusters(rows, tariff)
    return {
        "exact": exact,
        "fuzzy": fuzzy,
        "exact_saving": sum((g["potential_saving"] for g in exact), Decimal(0)),
        "fuzzy_saving": sum((g["potential_saving"] for g in fuzzy), Decimal(0)),
    }
