"""Indlæser for det GAMLE danske toldsystem (SAD / rapportservlet-PDF).

Det gamle Toldsystem (import.skat.dk) udfases af DMS, men historiske angivelser
findes typisk kun her. Udtrækket er en PDF-rendering med SAD-boksnumre
(boks 33 Varekode, 34 Oprindelsesland, 46 Statistisk værdi, Beregninger A00=told/B00=moms).

PDF-parsing er skrøbeligt af natur — derfor er tekstudtrækket (kræver PyMuPDF + selve
PDF'en) adskilt fra felt-parsingen (`_rows_from_lines`, ren logik), så logikken kan
testes uden at committe rigtige angivelsesdata. Filen modificeres aldrig.

Bemærk: ved struktureret Excel/CSV-eksport fra det gamle system bruges i stedet den
generiske tabular-adapter (som har SAD-boks-aliaser).
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional, Union

# SAD-boks/label-nøgleord → kanonisk felt. Matches hvis labelen *indeholder* nøgleordet.
_HEADER_FIELDS = {
    "møntsort": "invoice_currency",
    "transportmåde ved grænsen": "border_mot",
    "indenlandsk transportmåde": "inland_mot",
    "forventet ankomstdato": "date",
}
_ITEM_FIELDS = {
    "varekode": "commodity_code",
    "oprindelsesland": "origin_country",
    "præference": "duty_regime_code",
    "procedurekode": "cpc",
    "nettomasse": "net_mass",
    "bruttomasse": "gross_mass",
    "varens pris": "item_invoice_amount",
    "statistisk værdi": "customs_value_dkk",
    "varebeskrivelse": "description",
}
_NUMERIC = {"net_mass", "gross_mass", "item_invoice_amount", "customs_value_dkk", "customs_duty"}
_MOT = {"border_mot", "inland_mot"}


def _num(raw: str) -> Optional[Decimal]:
    s = re.sub(r"[^0-9,.\-]", "", str(raw or "").split("kl")[0])
    if not s:
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


def _match(label: str, table: dict) -> Optional[str]:
    # Eksakt label-match (efter strip + lower) — undgår at fx "Præference" (boks 36)
    # forveksles med "Præference dokumentationsnummer" (boks 44.4b).
    return table.get(label.strip().lower())


def _rows_from_lines(lines: list[str]) -> list[dict]:
    """Parse SAD-boks-linjer ('NN Label: value') + Beregninger til analyseklare rækker.

    Hoveddel-felter (før første 'Varepost nummer') arves ned på hver varepost.
    """
    header: dict = {}
    vps: list[tuple[dict, dict]] = []  # (varepost-felter, afgiftsart→beløb)
    cur: Optional[dict] = None
    duties: dict[str, Decimal] = {}

    for line in lines:
        s = line.strip()
        if re.match(r"^\s*32\s+Varepost\s*nummer", s, re.I):
            if cur is not None:
                vps.append((cur, duties))
            cur, duties = {}, {}
            continue

        # Beregninger-række: "<linie> A00 <grundlag> <sats> <beløb> ..." → told = A-serien.
        mb = re.match(r"^\s*\d+\s+([AB]\d\d)\s+(\S+)\s+(\S+)\s+(\S+)", s)
        if mb:
            beløb = _num(mb.group(4))
            if beløb is not None:
                duties[mb.group(1)] = beløb
            continue

        # SAD-boks: valgfrit boksnummer, label, ':', værdi.
        m = re.match(r"^\s*(?:\d+\s+)?([^:]+):\s*(.+)$", s)
        if not m:
            continue
        label, value = m.group(1).strip(), m.group(2).strip()
        target = cur if cur is not None else header
        field = _match(label, _ITEM_FIELDS if cur is not None else _HEADER_FIELDS)
        # Hoveddel-felter (valuta/transport/dato) kan også stå før vareposterne.
        if field is None and cur is not None:
            field = _match(label, _HEADER_FIELDS)
            if field:
                target = header
        if not field:
            continue
        if field == "date":
            digits = re.sub(r"\D", "", value)[:8]
            target[field] = f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}" if len(digits) == 8 else value
        elif field in _NUMERIC:
            target[field] = _num(value)
        else:
            target[field] = value

    if cur is not None:
        vps.append((cur, duties))

    rows = []
    for vp, dty in vps:
        row = {**header, **vp, "source_format": "legacy_sad"}
        a_series = [v for art, v in dty.items() if art.startswith("A")]  # A00 m.fl. = told
        if a_series:
            row["customs_duty"] = sum(a_series, Decimal(0))
        rows.append(row)
    return rows


def _lines_from_pdf(path: Union[str, bytes, Path]) -> list[str]:
    """Udtræk koordinat-grupperede 'label: value'-linjer fra rapportservlet-PDF'en."""
    import fitz  # PyMuPDF — kun krævet for PDF-input

    doc = fitz.open(stream=path, filetype="pdf") if isinstance(path, bytes) else fitz.open(path)
    lines: list[str] = []
    for page in doc:
        rows: dict = {}
        for x0, y0, x1, y1, word, *_ in page.get_text("words"):
            rows.setdefault(round(y0 / 2), []).append((x0, word))
        for key in sorted(rows):
            lines.append(" ".join(w for _, w in sorted(rows[key])))
    doc.close()
    return lines


def parse_legacy_sad(source: Union[str, bytes, Path]) -> list[dict]:
    """Parse en gammel-system-angivelse (rapportservlet-PDF) til analyseklare rækker."""
    return _rows_from_lines(_lines_from_pdf(source))
