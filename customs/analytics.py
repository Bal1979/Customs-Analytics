"""Analyselag — aggregeringer oven på analyseklare rækker (``Declaration.to_rows``
eller Excel/CSV-adapterens output).

Fase 1: **Imports Summary** — de KPI'er og fordelinger analyse-dashboardet viser.
Alle beløb holdes som ``Decimal``; konvertering til JSON-venlige tal sker i web-laget.
Funktionerne er rene (ingen I/O), så de er trivielt testbare.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable, Optional

from customs.schema import MODE_OF_TRANSPORT

Row = dict


def _dec(value) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _month(value) -> Optional[str]:
    """Træk 'YYYY-MM' ud af en dato/datotid-streng."""
    if not value:
        return None
    s = str(value)
    if len(s) >= 7 and s[4] in "-/":
        return s[:7].replace("/", "-")
    if len(s) >= 6 and s[:8].isdigit():  # fx 20250822 (DMS-format)
        return f"{s[:4]}-{s[4:6]}"
    return None


def _rate(duty: Optional[Decimal], value: Optional[Decimal]) -> Optional[Decimal]:
    if duty is None or not value:
        return None
    return duty / value


def _top(buckets: dict, key: str, n: Optional[int]) -> list[dict]:
    items = sorted(buckets.values(), key=lambda b: b[key], reverse=True)
    return items[:n] if n else items


def imports_summary(rows: Iterable[Row], top_n: int = 10) -> dict:
    """Beregn Imports Summary: KPI'er + fordelinger pr. land/HS/varebeskrivelse,
    tidsserie samt fordeling pr. CPC og transportform."""
    rows = list(rows)

    total_value = Decimal(0)
    total_duty = Decimal(0)
    shipments = 0

    by_origin: dict[str, dict] = {}
    by_hs: dict[str, dict] = {}
    by_desc: dict[str, dict] = {}
    by_cpc: dict[str, dict] = {}
    by_mot: dict[str, dict] = {}
    by_month: dict[str, dict] = {}

    def bucket(store: dict, key, label_field: str):
        k = key if key not in (None, "") else "(ukendt)"
        if k not in store:
            store[k] = {label_field: k, "customs_value": Decimal(0), "import_duty": Decimal(0), "shipments": 0}
        return store[k]

    for r in rows:
        value = _dec(r.get("customs_value_dkk")) or Decimal(0)
        duty = _dec(r.get("customs_duty")) or Decimal(0)
        ships = int(r.get("shipments") or 1)

        total_value += value
        total_duty += duty
        shipments += ships

        for store, key, label in (
            (by_origin, r.get("origin_country"), "country"),
            (by_hs, r.get("commodity_code") or r.get("hs_code"), "hs_code"),
            (by_desc, r.get("description"), "description"),
            (by_cpc, r.get("cpc"), "cpc"),
            (by_mot, r.get("border_mot"), "mot"),
        ):
            b = bucket(store, key, label)
            b["customs_value"] += value
            b["import_duty"] += duty
            b["shipments"] += ships

        m = _month(r.get("issue_datetime") or r.get("date"))
        if m:
            mb = bucket(by_month, m, "month")
            mb["customs_value"] += value
            mb["import_duty"] += duty

    # Afledt effektiv toldsats pr. bucket.
    for store in (by_origin, by_hs, by_desc, by_cpc, by_mot):
        for b in store.values():
            b["effective_duty_rate"] = _rate(b["import_duty"], b["customs_value"])

    return {
        "kpis": {
            "customs_value": total_value,
            "import_duty": total_duty,
            "shipments": shipments,
            "effective_duty_rate": _rate(total_duty, total_value),
            "lines": len(rows),
        },
        "by_origin": _top(by_origin, "customs_value", top_n),
        "by_hs_code": _top(by_hs, "customs_value", top_n),
        "by_description": _top(by_desc, "customs_value", top_n),
        "by_cpc": _top(by_cpc, "customs_value", None),
        "by_transport": _top(by_mot, "customs_value", None),
        "time_series": [by_month[m] for m in sorted(by_month)],
    }


def supplier_overview(rows: Iterable[Row], top_n: int = 25) -> list[dict]:
    """Supplier Overview: pr. leverandør (consignor) — antal oprindelseslande,
    forsendelser, toldværdi, told og effektiv toldsats."""
    store: dict[str, dict] = {}
    for r in rows:
        name = r.get("consignor_name") or "(ukendt)"
        b = store.setdefault(
            name,
            {"consignor": name, "countries": set(), "shipments": 0,
             "customs_value": Decimal(0), "import_duty": Decimal(0)},
        )
        if r.get("origin_country"):
            b["countries"].add(r["origin_country"])
        b["shipments"] += int(r.get("shipments") or 1)
        b["customs_value"] += _dec(r.get("customs_value_dkk")) or Decimal(0)
        b["import_duty"] += _dec(r.get("customs_duty")) or Decimal(0)
    out = []
    for b in store.values():
        out.append({
            "consignor": b["consignor"],
            "countries_count": len(b["countries"]),
            "shipments": b["shipments"],
            "customs_value": b["customs_value"],
            "import_duty": b["import_duty"],
            "effective_duty_rate": _rate(b["import_duty"], b["customs_value"]),
        })
    out.sort(key=lambda b: b["customs_value"], reverse=True)
    return out[:top_n] if top_n else out


def cpc_analysis(rows: Iterable[Row]) -> list[dict]:
    """CPC-analyse: fordeling pr. toldprocedurekode med andel af samlet toldværdi."""
    rows = list(rows)
    store: dict[str, dict] = {}
    total = Decimal(0)
    for r in rows:
        cpc = r.get("cpc") or "(ukendt)"
        value = _dec(r.get("customs_value_dkk")) or Decimal(0)
        duty = _dec(r.get("customs_duty")) or Decimal(0)
        total += value
        b = store.setdefault(
            cpc, {"cpc": cpc, "customs_value": Decimal(0), "import_duty": Decimal(0), "shipments": 0}
        )
        b["customs_value"] += value
        b["import_duty"] += duty
        b["shipments"] += int(r.get("shipments") or 1)
    out = sorted(store.values(), key=lambda b: b["customs_value"], reverse=True)
    for b in out:
        b["effective_duty_rate"] = _rate(b["import_duty"], b["customs_value"])
        b["share"] = (b["customs_value"] / total) if total else None
    return out


def transport_analysis(rows: Iterable[Row]) -> dict:
    """Transportanalyse: fordeling pr. transportform (grænse + indland) med nettovægt."""
    def by_mode(field: str) -> list[dict]:
        store: dict[str, dict] = {}
        for r in rows_list:
            code = r.get(field) or "(ukendt)"
            b = store.setdefault(
                code,
                {"mot": code, "mot_label": MODE_OF_TRANSPORT.get(code, code),
                 "customs_value": Decimal(0), "import_duty": Decimal(0),
                 "net_mass": Decimal(0), "shipments": 0},
            )
            b["customs_value"] += _dec(r.get("customs_value_dkk")) or Decimal(0)
            b["import_duty"] += _dec(r.get("customs_duty")) or Decimal(0)
            b["net_mass"] += _dec(r.get("net_mass")) or Decimal(0)
            b["shipments"] += int(r.get("shipments") or 1)
        return sorted(store.values(), key=lambda b: b["customs_value"], reverse=True)

    rows_list = list(rows)
    return {"by_border": by_mode("border_mot"), "by_inland": by_mode("inland_mot")}


def sourcing_analysis(rows: Iterable[Row], top_n: int = 50) -> dict:
    """Sourcing: transaktionsniveau-tabeller pr. oprindelsesland og pr. HS-kode."""
    summary = imports_summary(rows, top_n=top_n)
    return {"by_country": summary["by_origin"], "by_hs_code": summary["by_hs_code"]}


def build_report(rows: Iterable[Row]) -> dict:
    """Saml alle kerne-analyser i ét svar (ét gennemløb pr. sektion)."""
    rows = list(rows)
    return {
        "summary": imports_summary(rows),
        "suppliers": supplier_overview(rows),
        "sourcing": sourcing_analysis(rows),
        "cpc": cpc_analysis(rows),
        "transport": transport_analysis(rows),
    }
