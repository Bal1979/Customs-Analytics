"""Kør valideringssuiten og generér valideringsrapporten.

For hvert scenarie plantes én defekt, kontrollen køres via sin RIGTIGE indgang, og
det bekræftes, at netop den tilsigtede kontrol fyrer (og at en ren angivelse ikke
udløser fund). Resultatet skrives som markdown til docs/.

    python -m validation.run_validation            # kør + skriv rapport
    python -m validation.run_validation --quiet     # kun exit-kode (CI-gate)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from customs.sanity import check_declaration
from customs.duty_checks import duty_findings
from customs.classification import classification_consistency, fuzzy_clusters
from customs.tariff import TariffDatabase

from validation import scenarios as S

ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = ROOT / "customs" / "rules" / "Customs-Validation-Rules.json"
REPORT_PATH = ROOT / "docs" / "Customs-Analytics_Valideringsrapport.md"


def _load_catalog() -> dict:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def _run_all(tariff: TariffDatabase) -> tuple[list[dict], bool]:
    """Kør alle scenarier. Returnér (resultatrækker, baseline_ren)."""
    results: list[dict] = []

    # Baseline: ren angivelse må ikke udløse sanity-fund.
    baseline_findings = check_declaration(S.base_declaration())
    baseline_clean = len(baseline_findings) == 0
    results.append({
        "scenario": "CUS-000", "rule": "(baseline)", "family": "baseline",
        "title": "Ren angivelse", "defect": "Ingen defekt — gyldig 1-linjes angivelse",
        "expected": "Ingen fund", "actual": (", ".join(f.code for f in baseline_findings) or "ingen"),
        "passed": baseline_clean,
    })

    # Sanity-scenarier.
    for rule, title, defect, mutate in S.SANITY_SCENARIOS:
        decl = S.base_declaration()
        mutate(decl)
        codes = [f.code for f in check_declaration(decl)]
        results.append({
            "scenario": rule, "rule": rule, "family": "sanity", "title": title,
            "defect": defect, "expected": f"{rule} fyrer",
            "actual": (", ".join(codes) or "ingen"), "passed": rule in codes,
        })

    # Told-scenarier.
    for rule, title, defect, row in S.DUTY_SCENARIOS:
        codes = [f.code for f in duty_findings([row], tariff)]
        results.append({
            "scenario": rule, "rule": rule, "family": "duty", "title": title,
            "defect": defect, "expected": f"{rule} fyrer",
            "actual": (", ".join(codes) or "ingen"), "passed": rule in codes,
        })

    # Klassifikations-scenarier.
    for rule, title, defect, mode, rows in S.CLASSIFICATION_SCENARIOS:
        groups = (classification_consistency(rows, tariff) if mode == "exact"
                  else fuzzy_clusters(rows, tariff))
        fired = len(groups) >= 1
        results.append({
            "scenario": rule, "rule": rule, "family": "classification", "title": title,
            "defect": defect, "expected": f"{rule} flagger ≥1 gruppe",
            "actual": f"{len(groups)} gruppe(r)", "passed": fired,
        })

    return results, baseline_clean


def _report(results: list[dict], catalog: dict) -> str:
    by_id = {r["id"]: r for r in catalog["rules"]}
    layers = {l["id"]: l["label_da"] for l in catalog["layers"]}
    total = len(results)
    passed = sum(1 for r in results if r["passed"])

    def layer_of(rule_id):
        r = by_id.get(rule_id)
        return f"{r['layer']} · {layers[r['layer']]}" if r else "—"

    lines = [
        "# Valideringsrapport — Customs Analytics",
        "",
        "> **Auto-genereret** af `validation/run_validation.py`. Regenerér med "
        "`python -m validation.run_validation`. Rediger ikke i hånden.",
        "",
        f"- **Regelkatalog:** v{catalog['catalog_version']} ({catalog['catalog_released']})",
        f"- **Scenarier:** {total} ({passed}/{total} bestået)",
        "- **Metode:** Hvert scenarie planter præcis ÉN defekt i en ren baseline og "
        "kører kontrollen via dens rigtige indgang; det bekræftes, at netop den "
        "tilsigtede kontrol fyrer. En ren angivelse udløser ingen fund.",
        "",
        "## Resultater",
        "",
        "| Scenarie | Lag | Kontrol | Defekt | Forventet | Faktisk | Resultat |",
        "|----------|-----|---------|--------|-----------|---------|----------|",
    ]
    for r in results:
        lay = layer_of(r["rule"]) if r["rule"] != "(baseline)" else "—"
        verdict = "✓ Bestået" if r["passed"] else "✗ FEJLET"
        lines.append(
            f"| {r['scenario']} | {lay} | {r['title']} | {r['defect']} | "
            f"{r['expected']} | {r['actual']} | {verdict} |"
        )

    # Dækning: hvilke implementerede kontroller har et scenarie?
    implemented = [r["id"] for r in catalog["rules"] if r["status"] == "implemented"]
    covered = set(S.all_scenario_rules())
    missing = [c for c in implemented if c not in covered]
    lines += [
        "",
        "## Dækning",
        "",
        f"- **Implementerede kontroller:** {len(implemented)}",
        f"- **Dækket af et scenarie:** {len(covered & set(implemented))} / {len(implemented)}",
        ("- **Udækkede:** " + (", ".join(missing) if missing else "ingen ✓")),
        "",
        "Planlagte kontroller (status `planned` i kataloget) er bevidst ikke dækket, "
        "da de endnu ikke er implementeret.",
        "",
    ]
    return "\n".join(lines)


def run(quiet: bool = False) -> bool:
    catalog = _load_catalog()

    # Kryds-tjek: hvert scenarie peger på en kontrol, der findes i kataloget.
    ids = {r["id"] for r in catalog["rules"]}
    for rule in S.all_scenario_rules():
        if rule not in ids:
            raise AssertionError(f"Scenarie peger på ukendt kontrol: {rule}")

    tariff = TariffDatabase()
    results, baseline_clean = _run_all(tariff)
    all_pass = baseline_clean and all(r["passed"] for r in results)

    if not quiet:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(_report(results, catalog), encoding="utf-8")
        passed = sum(1 for r in results if r["passed"])
        print(f"Valideringssuite: {passed}/{len(results)} bestået → {REPORT_PATH}")
        for r in results:
            if not r["passed"]:
                print(f"  ✗ {r['scenario']}: forventet {r['expected']}, fik {r['actual']}")

    return all_pass


if __name__ == "__main__":
    ok = run(quiet="--quiet" in sys.argv)
    sys.exit(0 if ok else 1)
