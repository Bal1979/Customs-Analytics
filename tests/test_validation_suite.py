"""CI-gate for den uafhængige valideringssuite.

Bekræfter at hver implementeret kontrol fyrer på sit defekt-scenarie, at en ren
angivelse ikke gør, og at hvert scenarie peger på en kontrol i regelkataloget.
"""

import json

from validation.run_validation import run, CATALOG_PATH
from validation import scenarios as S


def test_validation_suite_all_pass():
    assert run(quiet=True) is True


def test_every_scenario_rule_exists_in_catalog():
    ids = {r["id"] for r in json.loads(CATALOG_PATH.read_text(encoding="utf-8"))["rules"]}
    for rule in S.all_scenario_rules():
        assert rule in ids, f"Scenarie peger på ukendt kontrol: {rule}"


def test_catalog_is_valid_json_and_versioned():
    c = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    assert c["catalog_version"], "catalog_version mangler"
    implemented = [r for r in c["rules"] if r["status"] == "implemented"]
    assert len(implemented) >= 12, "forventede ≥12 implementerede kontroller"


def test_every_implemented_control_has_a_scenario():
    c = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    implemented = {r["id"] for r in c["rules"] if r["status"] == "implemented"}
    covered = set(S.all_scenario_rules())
    assert implemented <= covered, f"udækkede: {implemented - covered}"
