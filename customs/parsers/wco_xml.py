"""Indlæser for DMS' officielle udvekslingsformat: WCO Data Model XML.

Namespace ``urn:wco:datamodel:WCO:DEC-DMS:2``. Parseren matcher på *local name*
(ignorerer præfiks/namespace), så den er robust over for ns2:/default-namespace-
variationer mellem H1, I1 osv. Struktur verificeret mod Toldstyrelsens officielle
test-XML'er (skat/dms-public) — se tests/.

XXE er slået fra (ingen ekstern entitetsopløsning), da input er kundedata.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional, Union
from xml.etree import ElementTree as ET

from customs.schema import Declaration, DutyLine, GoodsItem, Party


def _local(tag: str) -> str:
    """Strip namespace fra et ElementTree-tag: '{ns}Name' -> 'Name'."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _find(elem: Optional[ET.Element], *names: str) -> Optional[ET.Element]:
    """Følg en sti af local-names, ét niveau ad gangen. None hvis et led mangler."""
    cur = elem
    for name in names:
        if cur is None:
            return None
        cur = next((c for c in cur if _local(c.tag) == name), None)
    return cur


def _findall(elem: Optional[ET.Element], name: str) -> list[ET.Element]:
    if elem is None:
        return []
    return [c for c in elem if _local(c.tag) == name]


def _text(elem: Optional[ET.Element], *names: str) -> Optional[str]:
    node = _find(elem, *names) if names else elem
    if node is None or node.text is None:
        return None
    t = node.text.strip()
    return t or None


def _dec(value: Optional[str]) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError):
        return None


def _dec_at(elem: Optional[ET.Element], *names: str) -> Optional[Decimal]:
    return _dec(_text(elem, *names))


def parse_wco_xml(source: Union[str, bytes, Path]) -> Declaration:
    """Parse en WCO DMS-XML-angivelse til den kanoniske ``Declaration``."""
    parser = ET.XMLParser()  # ElementTree opløser ikke eksterne entiteter (ingen XXE)
    if isinstance(source, (str, Path)) and Path(str(source)).exists():
        root = ET.parse(str(source), parser=parser).getroot()
    else:
        data = source.encode() if isinstance(source, str) else source
        root = ET.fromstring(data, parser=parser)

    if _local(root.tag) != "Declaration":
        # Nogle eksporter pakker Declaration i en konvolut — find den indlejret.
        found = root.find(".//{*}Declaration")
        if found is not None:
            root = found

    decl = Declaration(source_format="wco_xml")
    decl.function_code = _text(root, "FunctionCode")
    decl.procedure_category = _text(root, "ProcedureCategory")
    decl.type_code = _text(root, "TypeCode")
    decl.lrn = _text(root, "FunctionalReferenceID")
    decl.mrn = _text(root, "ID")  # tildelt MRN, hvis til stede på rod
    decl.declaration_office = _text(root, "DeclarationOfficeID")
    decl.acceptance_datetime = _text(_find(root, "AcceptanceDateTime"), "DateTimeString")
    decl.issue_datetime = _text(_find(root, "IssueDateTime"), "DateTimeString")

    inv = _find(root, "InvoiceAmount")
    if inv is not None:
        decl.invoice_amount = _dec(inv.text)
        decl.invoice_currency = inv.get("currencyID")

    # Parter på hoveddel.
    decl.parties.extend(_parse_parties(root))

    gs = _find(root, "GoodsShipment")
    if gs is not None:
        _parse_goods_shipment_header(decl, gs)
        for item_el in _findall(gs, "GovernmentAgencyGoodsItem"):
            decl.goods_items.append(_parse_goods_item(item_el))
        # Importør/consignor kan ligge under GoodsShipment.
        decl.parties.extend(_parse_parties(gs))

    return decl


def _parse_parties(parent: ET.Element) -> list[Party]:
    role_map = {
        "Exporter": "exporter",
        "Importer": "importer",
        "Declarant": "declarant",
        "Consignor": "consignor",
        "Consignee": "consignee",
        "Buyer": "buyer",
        "Seller": "seller",
        "Submitter": "submitter",
    }
    parties = []
    for el in parent:
        role = role_map.get(_local(el.tag))
        if role is None:
            continue
        addr = _find(el, "Address")
        parties.append(
            Party(
                role=role,
                eori=_text(el, "ID"),
                name=_text(el, "Name"),
                country=_text(addr, "CountryCode"),
                city=_text(addr, "CityName"),
                address=_text(addr, "Line"),
                postcode=_text(addr, "PostcodeID"),
            )
        )
    return parties


def _parse_goods_shipment_header(decl: Declaration, gs: ET.Element) -> None:
    consignment = _find(gs, "Consignment")
    btm = _find(consignment, "BorderTransportMeans")
    decl.border_transport_mode = _text(btm, "ModeCode")
    decl.transport_nationality = _text(btm, "RegistrationNationalityCode")
    # Indenlandsk transportmåde ligger på forsendelsen, når den er udfyldt.
    decl.inland_transport_mode = _text(consignment, "TransportMeans", "ModeCode") or _text(
        consignment, "ModeCode"
    )

    decl.destination_country = _text(_find(gs, "Destination"), "CountryCode")
    decl.dispatch_country = _text(_find(gs, "DispatchCountry"), "ID")
    decl.gross_mass_total = _dec_at(_find(gs, "GoodsMeasure"), "GrossMassMeasure")

    terms = _find(gs, "TradeTerms")
    if terms is not None:
        decl.incoterm = _text(terms, "ConditionCode")
        decl.delivery_location = _text(terms, "LocationName")
        decl.delivery_country = _text(terms, "CountryCode")


def _parse_goods_item(el: ET.Element) -> GoodsItem:
    item = GoodsItem()
    seq = _text(el, "SequenceNumeric")
    item.item_number = int(seq) if seq and seq.isdigit() else None
    item.statistical_value = _dec_at(el, "StatisticalValueAmount")

    commodity = _find(el, "Commodity")
    item.description = _text(commodity, "Description")
    for cls in _findall(commodity, "Classification"):
        code = _text(cls, "ID")
        kind = _text(cls, "IdentificationTypeCode")
        if kind == "HS":
            item.hs_code = code
        elif kind == "CN":
            item.cn_code = code
        elif kind == "TRC":
            item.taric_code = code

    # Varens pris pr. linje (i angivelsens fakturavaluta).
    item.item_invoice_amount = _dec_at(commodity, "InvoiceLine", "ItemChargeAmount")

    # Vægt — varepostniveau (under Commodity) med fallback til item-niveau.
    gm = _find(commodity, "GoodsMeasure")
    if gm is None:
        gm = _find(el, "GoodsMeasure")
    item.gross_mass = _dec_at(gm, "GrossMassMeasure")
    item.net_mass = _dec_at(gm, "NetNetWeightMeasure")
    item.supplementary_units = _dec_at(gm, "TariffQuantity")

    item.valuation_method = _text(_find(el, "CustomsValuation"), "MethodCode")

    # Told/afgift + præference. DutyRegimeCode kan ligge under Commodity eller item.
    for dtf in _findall(commodity, "DutyTaxFee") + _findall(el, "DutyTaxFee"):
        regime = _text(dtf, "DutyRegimeCode")
        if regime and item.duty_regime_code is None:
            item.duty_regime_code = regime
        item.duties.append(
            DutyLine(
                type_code=_text(dtf, "TypeCode"),
                regime_code=regime,
                base_amount=_dec_at(dtf, "AdValoremTaxBaseAmount"),
                payable_amount=_dec_at(dtf, "DutyTaxFeePaymentAmount"),
            )
        )

    # Procedurekoder. To former: hoved (CurrentCode 2-cif + PreviousCode) og
    # supplerende (CurrentCode 3-cif uden PreviousCode).
    for gp in _findall(el, "GovernmentProcedure"):
        cur = _text(gp, "CurrentCode")
        prev = _text(gp, "PreviousCode")
        if prev is not None or (cur and len(cur) == 2):
            item.procedure_current = cur
            item.procedure_previous = prev
        elif cur:
            item.supplementary_procedures.append(cur)

    # Oprindelse: TypeCode 1 = oprindelsesland, 2 = præference-oprindelsesland.
    for org in _findall(el, "Origin"):
        country = _text(org, "CountryCode")
        kind = _text(org, "TypeCode")
        if kind == "2":
            item.preferential_origin_country = country
        else:
            item.origin_country = item.origin_country or country

    for doc in _findall(el, "SupportingDocument") + _findall(el, "AdditionalReference"):
        item.supporting_documents.append(
            {"id": _text(doc, "ID"), "type_code": _text(doc, "TypeCode")}
        )

    return item
