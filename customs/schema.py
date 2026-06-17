"""Kanonisk intern datamodel for Customs Analytics.

Ét format som alle indlæsere (WCO DMS-XML, legacy SAD, Excel/CSV) oversætter til,
og som al analyse og alle sanity-tjek arbejder oven på. Modellen er bevidst flad
nok til at kunne "foldes ud" til én række pr. varepost (``Declaration.to_rows``),
hvilket er den analyseklare form (jf. JYSK-dashboardet).

Felter navngives fagligt (dansk/told-terminologi) og bærer reference til det
underliggende WCO-/DMS-dataelement i docstrings, så kortlægningen er sporbar.
Beløb holdes som ``Decimal`` for at undgå float-afrunding på toldværdier.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional


# Transportmåde-koder (WCO ModeCode / SAD boks 25-26). Kilde: DMS-vejledning.
MODE_OF_TRANSPORT = {
    "1": "Søtransport",
    "2": "Jernbanetransport",
    "3": "Vejtransport",
    "4": "Lufttransport",
    "5": "Post",
    "7": "Faste transportinstallationer",
    "8": "Indre vandveje",
    "9": "Egen fremdrift",
}

# Præference/DutyRegimeCode (DMS 14 11 001). 100 = ingen præference; øvrige =
# specifik præferencebehandling. Fuld kodeliste ligger i reference/codelists.
NO_PREFERENCE_CODE = "100"


@dataclass
class Party:
    """Aktør (gruppe 13): eksportør, importør, klarerer, repræsentant, sælger, køber."""

    role: str  # fx "exporter", "importer", "declarant", "consignor", "representative"
    eori: Optional[str] = None        # 13 0x 017 — EORI/ID
    name: Optional[str] = None        # 13 0x 016
    country: Optional[str] = None     # 13 0x 018 020
    city: Optional[str] = None        # 13 0x 018 022
    address: Optional[str] = None     # 13 0x 018 019
    postcode: Optional[str] = None    # 13 0x 018 021


@dataclass
class DutyLine:
    """Beregnet told/afgift pr. varepost (14 03). A00 = told, B00 = moms (25 %)."""

    type_code: Optional[str] = None       # afgiftsart, fx A00/B00/A20
    regime_code: Optional[str] = None     # DutyRegimeCode / præference (14 11 001)
    base_amount: Optional[Decimal] = None  # afgiftsgrundlag
    rate: Optional[Decimal] = None         # sats
    payable_amount: Optional[Decimal] = None  # skattebeløb der skal betales


@dataclass
class GoodsItem:
    """Varepost — analyse-enheden. WCO ``GovernmentAgencyGoodsItem``."""

    item_number: Optional[int] = None     # SequenceNumeric
    description: Optional[str] = None      # 18 05 — Commodity/Description

    # Varekode: HS(6) + KN/CN(2) + TARIC(2) = 10 cifre (18 09 056/057/058).
    hs_code: Optional[str] = None
    cn_code: Optional[str] = None
    taric_code: Optional[str] = None

    # Oprindelse (gruppe 16): 16 08 = oprindelsesland, 16 09 = præference-oprindelse.
    origin_country: Optional[str] = None
    preferential_origin_country: Optional[str] = None

    # Procedurekode (CPC) sammensat: anmodet(2) 11 09 001 + forudgående(2) 11 09 002
    # + supplerende(3) 11 10.
    procedure_current: Optional[str] = None
    procedure_previous: Optional[str] = None
    supplementary_procedures: list[str] = field(default_factory=list)

    duty_regime_code: Optional[str] = None  # præference (14 11 001), 100 = ingen

    # Værdier. toldværdi = statistisk værdi i DKK (99 06 001).
    statistical_value: Optional[Decimal] = None     # DKK — "Customs Value (kr)"
    item_invoice_amount: Optional[Decimal] = None    # i angivelsens fakturavaluta (14 08)
    valuation_method: Optional[str] = None           # 14 10 — 1 = transaktionsværdi

    gross_mass: Optional[Decimal] = None   # 18 04 (kg)
    net_mass: Optional[Decimal] = None     # 18 01 (kg)
    supplementary_units: Optional[Decimal] = None  # 18 02

    duties: list[DutyLine] = field(default_factory=list)
    supporting_documents: list[dict] = field(default_factory=list)  # {id, type_code}

    @property
    def commodity_code(self) -> Optional[str]:
        """Fuld 10-cifret varekode, hvis delene findes."""
        if self.hs_code is None:
            return None
        return (
            (self.hs_code or "")
            + (self.cn_code or "")
            + (self.taric_code or "")
        ) or None

    @property
    def cpc(self) -> Optional[str]:
        """Sammensat procedurekode, fx 40 + 00 + 000 = '4000000'."""
        if self.procedure_current is None:
            return None
        supp = self.supplementary_procedures[0] if self.supplementary_procedures else "000"
        return f"{self.procedure_current}{self.procedure_previous or '00'}{supp}"

    @property
    def claims_preference(self) -> bool:
        """Påberåbes der præference? (DutyRegimeCode ≠ 100 og udfyldt.)"""
        return bool(self.duty_regime_code) and self.duty_regime_code != NO_PREFERENCE_CODE

    @property
    def customs_duty(self) -> Optional[Decimal]:
        """Samlet told (afgiftsart A-serien), ekskl. moms (B00)."""
        amounts = [
            d.payable_amount
            for d in self.duties
            if d.payable_amount is not None
            and (d.type_code or "").upper().startswith("A")
        ]
        return sum(amounts) if amounts else None

    @property
    def effective_duty_rate(self) -> Optional[Decimal]:
        """EDR = told ÷ toldværdi."""
        duty = self.customs_duty
        if duty is None or not self.statistical_value:
            return None
        return duty / self.statistical_value


@dataclass
class Declaration:
    """Hele angivelsen (hoveddel + vareposter). Hoveddata arves ned ved udfoldning."""

    # Hoveddel — meddelelse (gruppe 11) og referencer.
    procedure_category: Optional[str] = None  # H1/H2/I1 ... (ProcedureCategory)
    type_code: Optional[str] = None           # IMD/IMB ... (suppl. angivelsestype)
    function_code: Optional[str] = None
    lrn: Optional[str] = None                 # FunctionalReferenceID / 12 09 001
    mrn: Optional[str] = None                 # angivelsesnummer (MRN), hvis tildelt
    declaration_office: Optional[str] = None  # DeclarationOfficeID

    # Værdi/valuta (gruppe 14).
    invoice_amount: Optional[Decimal] = None   # 14 06 — samlet fakturabeløb
    invoice_currency: Optional[str] = None     # 14 05 — fakturavaluta
    exchange_rate: Optional[Decimal] = None    # 14 09 — vekselkurs til DKK

    # Parter (gruppe 13).
    parties: list[Party] = field(default_factory=list)

    # Transport (gruppe 19).
    border_transport_mode: Optional[str] = None   # 19 03 — MOT ved grænsen
    inland_transport_mode: Optional[str] = None   # 19 04 — MOT indland
    transport_nationality: Optional[str] = None   # 19 08 062

    # Steder/lande (gruppe 16).
    destination_country: Optional[str] = None  # 16 03
    dispatch_country: Optional[str] = None     # 16 06

    # Leveringsbetingelser (14 01).
    incoterm: Optional[str] = None
    delivery_location: Optional[str] = None
    delivery_country: Optional[str] = None

    gross_mass_total: Optional[Decimal] = None  # 18 04 — samlet bruttovægt

    goods_items: list[GoodsItem] = field(default_factory=list)

    # Sporbarhed.
    source_format: Optional[str] = None  # "wco_xml" | "legacy_sad" | "excel"
    issue_datetime: Optional[str] = None
    acceptance_datetime: Optional[str] = None

    def party(self, role: str) -> Optional[Party]:
        for p in self.parties:
            if p.role == role:
                return p
        return None

    def to_rows(self) -> list[dict]:
        """Foldér ud til én analyseklar række pr. varepost (hoveddata påhæftet)."""
        importer = self.party("importer")
        consignor = self.party("consignor") or self.party("exporter")
        rows = []
        for it in self.goods_items:
            rows.append(
                {
                    "lrn": self.lrn,
                    "mrn": self.mrn,
                    "procedure_category": self.procedure_category,
                    "declaration_office": self.declaration_office,
                    "issue_datetime": self.issue_datetime,
                    "invoice_currency": self.invoice_currency,
                    "exchange_rate": self.exchange_rate,
                    "importer_eori": importer.eori if importer else None,
                    "consignor_name": consignor.name if consignor else None,
                    "dispatch_country": self.dispatch_country,
                    "destination_country": self.destination_country,
                    "border_mot": self.border_transport_mode,
                    "inland_mot": self.inland_transport_mode,
                    "incoterm": self.incoterm,
                    # Varepost
                    "item_number": it.item_number,
                    "description": it.description,
                    "commodity_code": it.commodity_code,
                    "hs_code": it.hs_code,
                    "origin_country": it.origin_country,
                    "preferential_origin_country": it.preferential_origin_country,
                    "cpc": it.cpc,
                    "duty_regime_code": it.duty_regime_code,
                    "claims_preference": it.claims_preference,
                    "customs_value_dkk": it.statistical_value,
                    "item_invoice_amount": it.item_invoice_amount,
                    "customs_duty": it.customs_duty,
                    "effective_duty_rate": it.effective_duty_rate,
                    "gross_mass": it.gross_mass,
                    "net_mass": it.net_mass,
                }
            )
        return rows
