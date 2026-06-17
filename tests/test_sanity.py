"""Tests for sanity-tjek mod de officielle angivelser + konstruerede defekter."""

from decimal import Decimal
from pathlib import Path

from customs.parsers.wco_xml import parse_wco_xml
from customs.sanity import RED, check_declaration
from customs.schema import Declaration, GoodsItem

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _codes(findings):
    return {f.code for f in findings}


def test_clean_h1_has_no_findings():
    decl = parse_wco_xml(FIXTURES / "official_h1_standard.xml")
    findings = check_declaration(decl)
    assert findings == [], f"forventede ingen fund, fik: {findings}"


def test_preference_with_origin_does_not_trigger_p01():
    # I1 påberåber præference (300) OG har præference-oprindelse → CUS-P01 må ikke udløses.
    decl = parse_wco_xml(FIXTURES / "official_i1_preference_uk.xml")
    findings = check_declaration(decl)
    assert "CUS-P01" not in _codes(findings)


def test_preference_without_origin_triggers_p01():
    decl = Declaration(
        goods_items=[
            GoodsItem(
                item_number=1,
                hs_code="940599",
                cn_code="00",
                taric_code="90",
                origin_country="VN",
                duty_regime_code="300",  # præference påberåbt
                preferential_origin_country=None,  # men ingen præference-oprindelse
                statistical_value=Decimal("1000"),
                procedure_current="40",
                procedure_previous="00",
            )
        ]
    )
    assert "CUS-P01" in _codes(check_declaration(decl))


def test_short_commodity_code_triggers_h01():
    decl = Declaration(
        goods_items=[GoodsItem(item_number=1, hs_code="8544", origin_country="NO")]
    )
    findings = check_declaration(decl)
    assert "CUS-H01" in _codes(findings)
    assert any(f.severity == RED for f in findings if f.code == "CUS-H01")


def test_net_exceeds_gross_triggers_w02():
    decl = Declaration(
        goods_items=[
            GoodsItem(
                item_number=1,
                hs_code="080430",
                cn_code="00",
                taric_code="90",
                origin_country="GB",
                statistical_value=Decimal("100"),
                procedure_current="40",
                procedure_previous="00",
                gross_mass=Decimal("100"),
                net_mass=Decimal("150"),
            )
        ]
    )
    assert "CUS-W02" in _codes(check_declaration(decl))


def test_gross_total_less_than_line_sum_triggers_w01():
    decl = Declaration(
        gross_mass_total=Decimal("50"),
        goods_items=[
            GoodsItem(
                item_number=1,
                hs_code="080430",
                cn_code="00",
                taric_code="90",
                origin_country="GB",
                statistical_value=Decimal("100"),
                procedure_current="40",
                procedure_previous="00",
                gross_mass=Decimal("100"),
            )
        ],
    )
    assert "CUS-W01" in _codes(check_declaration(decl))
