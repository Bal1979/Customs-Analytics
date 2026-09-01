"""Indlæser for DMS' egen PDF-udskrift af en angivelse ("DMS-print").

DMS Import kan udskrive angivelsen som PDF med dataelement-numre i parentes,
fx ``Varebeskrivelse (18 05 001 000) DINATRIUMKARBONAT``. Det er en RENDERING
af det nye format — ikke det gamle systems SAD-udskrift — og skal derfor ikke
gennem ``legacy_sad``-parseren.

PDF-tekstudtræk er tabsgivende og layout-følsomt: celler i to kolonner flettes
til én linje, og lange labels ombrydes, så værdien kan lande MIDT i element-
nummeret (fx ``(11 02 001 A`` + næste linje ``000)``). Parseren er derfor
tolerant: hvert dataelement matches med valgfrie, indskudte værditokens mellem
nummerets segmenter, og manglende felter udelades (kalderen markerer dem som
"kunne ikke udlæses"). XXE er irrelevant (ingen XML), og filen modificeres aldrig.

Output er samme normaliserede form som ``translation``-laget bruger:
``{"header": {...}, "items": [...]}``.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Optional, Union

from customs.parsers.legacy_sad import _lines_from_pdf

# Et dataelementnummer i parentes, fx "(18 09 056 000)" — evt. med indskudte
# værditokens pga. linjeombrydning. Bruges også til format-detektion.
_DE_PAREN = re.compile(r"\(\s*\d{2}\s+\d{2}\s+\d{3}\b")

# Ord der starter en NY label (bruges til at afgrænse tekstværdier).
_STOP_WORDS = {
    "Landekode", "Land", "By", "Adresse", "Postnummer", "Navn", "Status",
    "Telefonnummer", "E-mail", "Løbenummer", "Kode", "Tekst", "Filnavn",
    "Filstørrelse", "Gruppe", "Varepost", "Varepostnummer", "CUS", "KN-kode",
    "HS-kode", "TARIC-kode", "Supplerende", "Måleenhed", "Kolliart", "Kolli",
    "Mængde", "Toldsted", "Oplagstype", "Referencenummer/UCR", "Vekselkurs",
    "Fakturavaluta", "Præference", "Transportmåde", "Transport", "Nationalitet",
    "ID", "EORI", "Anmodet", "Forudgående", "Bestemmelsesland", "Afsendelsesland",
    "Afsendelsesregion", "Oprindelsesland", "Lokalitetstype", "Placeringstype",
    "UN/LOCODE", "Lokalitet", "INCOTERM", "Bruttovægt", "Nettovægt",
    "Værdiansættelsesindikator", "Værdiansættelsesmetode", "Statistisk",
    "Transaktionsart", "Kontingentnummer", "Antagelsesdato", "Breddegrad",
    "Længdegrad", "Husnummer", "Bevillingsnummer", "Garantitype", "Sikkerhedsstillelse",
}

_TITLECASE = re.compile(r"^[A-ZÆØÅ][a-zæøå]+$")


def _num(value: Optional[str]) -> Optional[Decimal]:
    """Dansk talformat ('1.235.345' / '12,5') → Decimal."""
    if not value:
        return None
    try:
        return Decimal(value.replace(".", "").replace(",", "."))
    except InvalidOperation:
        return None


def looks_like_dms_print(lines: list[str]) -> bool:
    """Er PDF'en en DMS-udskrift (dataelement-numre) frem for en gammel SAD-udskrift?"""
    hits = sum(1 for line in lines if _DE_PAREN.search(line))
    return hits >= 3


def _element_pattern(de: str) -> re.Pattern:
    """Tolerant regex for ét dataelement '(g1 g2 g3 g4)' med evt. indskudte værdier."""
    g = de.split()
    tok = r"(?:\s+[^\s()]+?)*?"  # indskudte værditokens (aldrig parenteser)
    return re.compile(
        r"\(\s*" + g[0] + "(" + tok + r")\s+" + g[1] + "(" + tok + r")\s+"
        + g[2] + "(" + tok + r")\s+" + g[3] + r"\s*\)\s*:?\s*"
    )


def _value_after(text: str, end: int, kind: str) -> Optional[str]:
    """Værdien EFTER parentesen: første token (koder/tal) eller frem til næste label."""
    rest = text[end:]
    stop = rest.find("(")
    seg = rest[: stop if stop != -1 else len(rest)]
    tokens = seg.split()
    if not tokens:
        return None
    if kind == "text":
        out = []
        for t in tokens:
            if t in _STOP_WORDS:
                break
            out.append(t)
        return " ".join(out) or None
    first = tokens[0]
    # Et TitleCase-ord efter et kode-/talfelt er starten på næste label — ikke en værdi.
    if _TITLECASE.match(first) or first in _STOP_WORDS:
        return None
    return first


def _extract(text: str, de: str, kind: str = "code") -> Optional[str]:
    """Find værdien for ét dataelement — indskudt i nummeret eller efter parentesen."""
    m = _element_pattern(de).search(text)
    if m is None:
        return None
    interleaved = [t for grp in m.groups() for t in (grp or "").split() if t]
    if kind == "text":
        after = _value_after(text, m.end(), "text")
        return after or (" ".join(interleaved) or None)
    if interleaved:
        return interleaved[0]
    return _value_after(text, m.end(), kind)


def _segments(lines: list[str]) -> tuple[str, list[tuple[int, str]]]:
    """Split i (hoveddel-tekst, [(varepostnr., varepost-tekst), ...])."""
    breaks: list[tuple[int, int]] = []  # (linjeindeks, varepostnr.)
    for i, line in enumerate(lines):
        m = re.match(r"^\s*Varepost\s+(\d+)\s*$", line)
        if m:
            breaks.append((i, int(m.group(1))))
    end_of_items = next(
        (i for i, line in enumerate(lines) if re.match(r"^\s*Versioner\s*$", line)),
        len(lines),
    )
    header_end = breaks[0][0] if breaks else end_of_items
    header_text = " ".join(lines[:header_end])
    items = []
    for n, (idx, no) in enumerate(breaks):
        stop = breaks[n + 1][0] if n + 1 < len(breaks) else end_of_items
        items.append((no, " ".join(lines[idx:stop])))
    return header_text, items


def parse_dms_print(source: Union[bytes, str]) -> dict:
    """Parse et DMS-print (PDF) til translation-lagets normaliserede form."""
    lines = _lines_from_pdf(source)
    return parse_dms_lines(lines)


def parse_dms_lines(lines: list[str]) -> dict:
    """Feltlogikken alene (testbar uden PDF): linjer → normaliseret hoved + vareposter."""
    header_text, item_segments = _segments(lines)

    mrn = None
    m = re.search(r"Angivelses\s*nummer:\s*(\S+)", header_text)
    if m:
        mrn = m.group(1)
    else:
        m = re.match(r"^\s*(\d{2}[A-Z]{2}\w{14})\s*$", lines[0]) if lines else None
        if m:
            mrn = m.group(1)

    category = None
    m = re.search(r"Angivelsestype:\s*([HIG]\d)\b", header_text)
    if m:
        category = m.group(1)

    office = None
    m = re.search(r"Toldsteds\s*ID:\s*(\S+)", header_text)
    if m:
        office = m.group(1)

    header = {
        "procedure_category": category,
        "type_code": _extract(header_text, "11 01 001 000"),
        "lrn": _extract(header_text, "12 09 001 000"),
        "mrn": mrn,
        "declaration_office": office,
        "invoice_amount": _num(_extract(header_text, "14 06 001 000")),
        "invoice_currency": _extract(header_text, "14 05 001 000"),
        "exchange_rate": _num(_extract(header_text, "14 09 001 000")),
        "exporter": _join_parts(
            _extract(header_text, "13 01 016 000", "text"),
            _extract(header_text, "13 01 018 022", "text"),
            _extract(header_text, "13 01 018 020"),
        ),
        "importer_id": _extract(header_text, "13 04 017 000"),
        "declarant_id": _extract(header_text, "13 05 017 000"),
        "dispatch_country": _extract(header_text, "16 06 001 000"),
        "destination_country": _extract(header_text, "16 03 001 000"),
        "border_mot": _extract(header_text, "19 03 001 000"),
        "inland_mot": _extract(header_text, "19 04 001 000"),
        "transport_nationality": _extract(header_text, "19 08 062 000"),
        "incoterm": _extract(header_text, "14 01 035 000"),
        "delivery_location": _join_parts(
            _extract(header_text, "14 01 037 000", "text"),
            _extract(header_text, "14 01 020 000"),
        ),
        "gross_mass_total": _num(_extract(header_text, "18 04 001 000")),
    }

    items = []
    for no, text in item_segments:
        supp = None
        m = re.search(r"Supplerende procedure \(11 10 001 000\)\s+\d+\s+(\w{3})", text)
        if m:
            supp = m.group(1)
        items.append(
            {
                "item_number": no,
                "description": _extract(text, "18 05 001 000", "text"),
                "hs_code": _extract(text, "18 09 056 000"),
                "cn_code": _extract(text, "18 09 057 000"),
                "taric_code": _extract(text, "18 09 058 000"),
                "origin_country": _extract(text, "16 08 001 000"),
                "preferential_origin_country": _extract(text, "16 09 001 000"),
                "procedure_current": _extract(text, "11 09 001 000"),
                "procedure_previous": _extract(text, "11 09 002 000"),
                "supplementary_procedure": supp,
                "duty_regime_code": _extract(text, "14 11 001 000"),
                "statistical_value": _num(_extract(text, "99 06 001 000")),
                "item_invoice_amount": _num(_extract(text, "14 08 001 000")),
                "valuation_method": _extract(text, "14 10 001 000"),
                "gross_mass": _num(_extract(text, "18 04 001 000")),
                "net_mass": _num(_extract(text, "18 01 001 000")),
                "supplementary_units": _num(_extract(text, "18 02 001 000")),
                "customs_duty": None,  # 14 03-tabellen udfyldes af DMS, ikke printet
                "documents": [],
            }
        )
    return {"header": header, "items": items}


def _join_parts(*parts: Optional[str]) -> Optional[str]:
    kept = [p for p in parts if p]
    return ", ".join(kept) if kept else None


def rows_from_dms_print(norm: dict) -> list[dict]:
    """Normaliseret DMS-print → analyseklare rækker (samme form som ``to_rows``).

    Bruges af dashboardets upload, så et DMS-print også kan analyseres — med de
    huller, PDF-kilden nu engang har (told/EDR kan ikke udledes af printet).
    """
    h = norm["header"]
    rows = []
    for it in norm["items"]:
        commodity = "".join(
            p for p in (it["hs_code"], it["cn_code"], it["taric_code"]) if p
        ) or None
        cpc = None
        if it["procedure_current"]:
            cpc = (
                it["procedure_current"]
                + (it["procedure_previous"] or "00")
                + (it["supplementary_procedure"] or "000")
            )
        regime = it["duty_regime_code"]
        rows.append(
            {
                "lrn": h["lrn"],
                "mrn": h["mrn"],
                "procedure_category": h["procedure_category"],
                "declaration_office": h["declaration_office"],
                "issue_datetime": None,  # antagelsesdato står tomt i printet
                "invoice_currency": h["invoice_currency"],
                "exchange_rate": h["exchange_rate"],
                "importer_eori": h["importer_id"],
                "consignor_name": h["exporter"],
                "dispatch_country": h["dispatch_country"],
                "destination_country": h["destination_country"],
                "border_mot": h["border_mot"],
                "inland_mot": h["inland_mot"],
                "incoterm": h["incoterm"],
                "item_number": it["item_number"],
                "description": it["description"],
                "commodity_code": commodity,
                "hs_code": it["hs_code"],
                "origin_country": it["origin_country"],
                "preferential_origin_country": it["preferential_origin_country"],
                "cpc": cpc,
                "duty_regime_code": regime,
                "claims_preference": bool(regime) and regime != "100",
                "customs_value_dkk": it["statistical_value"],
                "item_invoice_amount": it["item_invoice_amount"],
                "customs_duty": None,   # 14 03-tabellen udfyldes af DMS, ikke printet
                "effective_duty_rate": None,
                "gross_mass": it["gross_mass"],
                "net_mass": it["net_mass"],
                "source_format": "dms_pdf",
            }
        )
    return rows
