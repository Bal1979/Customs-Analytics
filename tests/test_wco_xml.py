"""Parser-tests mod Toldstyrelsens officielle DMS test-XML'er (skat/dms-public)."""

from decimal import Decimal
from pathlib import Path

from customs.parsers.wco_xml import parse_wco_xml

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_h1_standard_header():
    decl = parse_wco_xml(FIXTURES / "official_h1_standard.xml")
    assert decl.source_format == "wco_xml"
    assert decl.procedure_category == "H1"
    assert decl.type_code == "IMD"
    assert decl.lrn == "test124589"
    assert decl.declaration_office == "DK005607"
    assert decl.invoice_amount == Decimal("30000")
    assert decl.invoice_currency == "GBP"
    assert decl.border_transport_mode == "1"  # søtransport
    assert decl.transport_nationality == "DK"
    assert decl.destination_country == "DK"
    assert decl.dispatch_country == "GB"
    assert decl.incoterm == "FOB"
    assert decl.party("importer").eori == "DK12345678"
    assert decl.party("consignor").name == "Test Company"
    assert decl.party("consignor").country == "GB"


def test_h1_standard_goods_item():
    decl = parse_wco_xml(FIXTURES / "official_h1_standard.xml")
    assert len(decl.goods_items) == 1
    it = decl.goods_items[0]
    assert it.description == "Tørret frugt"
    assert it.hs_code == "080430" and it.cn_code == "00" and it.taric_code == "90"
    assert it.commodity_code == "0804300090"
    assert it.statistical_value == Decimal("268138")
    assert it.item_invoice_amount == Decimal("30000")
    assert it.gross_mass == Decimal("2000") and it.net_mass == Decimal("1800")
    assert it.valuation_method == "1"
    # CPC sammensat: anmodet 40 + forudgående 00 + supplerende 000.
    assert it.procedure_current == "40" and it.procedure_previous == "00"
    assert it.supplementary_procedures == ["000"]
    assert it.cpc == "4000000"
    assert it.origin_country == "GB"
    assert it.duty_regime_code == "100"
    assert it.claims_preference is False


def test_i1_preference_uk():
    decl = parse_wco_xml(FIXTURES / "official_i1_preference_uk.xml")
    assert decl.procedure_category == "I1"
    assert decl.invoice_currency == "EUR"
    it = decl.goods_items[0]
    assert it.commodity_code == "9405990090"
    assert it.duty_regime_code == "300"
    assert it.claims_preference is True
    # Præference-oprindelse (Origin TypeCode 2) skal fanges separat.
    assert it.origin_country == "GB"
    assert it.preferential_origin_country == "GB"
    assert it.cpc == "4000000"


def test_to_rows_flattens_per_item():
    decl = parse_wco_xml(FIXTURES / "official_h1_standard.xml")
    rows = decl.to_rows()
    assert len(rows) == 1
    row = rows[0]
    assert row["procedure_category"] == "H1"
    assert row["commodity_code"] == "0804300090"
    assert row["customs_value_dkk"] == Decimal("268138")
    assert row["origin_country"] == "GB"
    assert row["importer_eori"] == "DK12345678"
    assert row["border_mot"] == "1"
