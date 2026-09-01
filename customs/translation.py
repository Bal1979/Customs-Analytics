"""Oversættelseslag: én angivelse → parret SAD-/DMS-visning (Oversæt-fanen).

Ren PRÆSENTATIONSLOGIK — ingen kontrol, ingen dom. Modulet tager én uploadet
angivelse (DMS-XML, gammel-system-PDF eller struktureret udtræk), registrerer
selv formatet og bygger et felt-katalog, hvor hvert felt er parret på tværs af
de to formater: gammel SAD-rubrik ↔ nyt DMS-dataelement, med værdi, status og
en pædagogisk note. Manglende værdier markeres eksplicit (aldrig stiltiende
tomme), og der beregnes en dækningsgrad, så brugeren kan se, hvor komplet
oversættelsen er — særligt vigtigt for PDF-input, som er tabsgivende.

Feltmapping følger EUTK's datamodel (DF (EU) 2015/2446, bilag B), Toldstyrelsens
DMS-materiale og det gamle importsystems felthjælp til enhedsdokumentet — samme
grundlag som den offentlige Told-oversætter på balai.dk.

Output er JSON-serialiserbart (kun str/int/lists/dicts) og modificerer aldrig
inputtet.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from customs.schema import Declaration
from customs.parsers.legacy_sad import parse_legacy_sad
from customs.parsers.tabular import parse_tabular
from customs.parsers.wco_xml import parse_wco_xml

# Status pr. felt-par — samme kategorier som den offentlige Told-oversætter:
# ok = 1:1 · warn = opdelt · move = flyttet · gone = udgået · newde = nyt i DMS.
_STATUS_LABELS = {
    "ok": "1:1",
    "warn": "Opdelt",
    "move": "Flyttet",
    "gone": "Udgået",
    "newde": "Nyt i DMS",
}


def detect_format(data: bytes, filename: Optional[str] = None) -> str:
    """Identificér angivelsens format: filendelse først, derefter magiske bytes.

    Returnerer "wco_xml" (DMS), "legacy_sad" (gammelt system, PDF) eller
    "tabular" (struktureret Excel/CSV-udtræk).
    """
    name = (filename or "").lower()
    if name.endswith(".xml"):
        return "wco_xml"
    if name.endswith(".pdf"):
        return "legacy_sad"
    if name.endswith((".csv", ".xlsx", ".xlsm")):
        return "tabular"
    head = data[:256].lstrip()
    if head.startswith(b"%PDF"):
        return "legacy_sad"
    if head.startswith(b"<"):
        return "wco_xml"
    return "tabular"


# ── Formatering (præsentation — beløb forbliver Decimal indtil her) ──────────


def _fmt(value) -> Optional[str]:
    """Værdi → visningsstreng (dansk talformat for Decimal); None forbliver None."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        v = value.normalize()
        s = f"{v:,f}"
        return s.replace(",", "§").replace(".", ",").replace("§", ".")
    s = str(value).strip()
    return s or None


def _join(*parts: Optional[str], sep: str = " · ") -> Optional[str]:
    kept = [p for p in (_fmt(p) for p in parts) if p]
    return sep.join(kept) if kept else None


# ── Normalisering: begge kilder → {"header": {...}, "items": [...]} ─────────


def _split_commodity(code: Optional[str]) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """10-cifret varekode → (HS6, KN2, TARIC2). Kortere koder fyldes forfra."""
    if not code:
        return None, None, None
    c = str(code).strip()
    return c[:6] or None, c[6:8] or None, c[8:10] or None


def _split_cpc(cpc: Optional[str]) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """7-tegns procedurekode → (anmodet 2, forudgående 2, supplerende 3)."""
    if not cpc:
        return None, None, None
    c = str(cpc).strip()
    return c[:2] or None, c[2:4] or None, c[4:7] or None


def _normalize_declaration(decl: Declaration) -> dict:
    """WCO/DMS-``Declaration`` → normaliseret hoved + vareposter."""
    exporter = decl.party("exporter") or decl.party("consignor")
    importer = decl.party("importer")
    declarant = decl.party("declarant")

    header = {
        "procedure_category": decl.procedure_category,
        "type_code": decl.type_code,
        "lrn": decl.lrn,
        "mrn": decl.mrn,
        "declaration_office": decl.declaration_office,
        "invoice_amount": decl.invoice_amount,
        "invoice_currency": decl.invoice_currency,
        "exchange_rate": decl.exchange_rate,
        "exporter": _join(
            exporter.name if exporter else None,
            exporter.city if exporter else None,
            exporter.country if exporter else None,
            sep=", ",
        ),
        "importer_id": importer.eori if importer else None,
        "declarant_id": declarant.eori if declarant else None,
        "dispatch_country": decl.dispatch_country,
        "destination_country": decl.destination_country,
        "border_mot": decl.border_transport_mode,
        "inland_mot": decl.inland_transport_mode,
        "transport_nationality": decl.transport_nationality,
        "incoterm": decl.incoterm,
        "delivery_location": _join(decl.delivery_location, decl.delivery_country, sep=", "),
        "gross_mass_total": decl.gross_mass_total,
    }

    items = []
    for it in decl.goods_items:
        supp = it.supplementary_procedures
        items.append(
            {
                "item_number": it.item_number,
                "description": it.description,
                "hs_code": it.hs_code,
                "cn_code": it.cn_code,
                "taric_code": it.taric_code,
                "origin_country": it.origin_country,
                "preferential_origin_country": it.preferential_origin_country,
                "procedure_current": it.procedure_current,
                "procedure_previous": it.procedure_previous,
                "supplementary_procedure": supp[0] if supp else None,
                "duty_regime_code": it.duty_regime_code,
                "statistical_value": it.statistical_value,
                "item_invoice_amount": it.item_invoice_amount,
                "valuation_method": it.valuation_method,
                "gross_mass": it.gross_mass,
                "net_mass": it.net_mass,
                "supplementary_units": it.supplementary_units,
                "customs_duty": it.customs_duty,
                "documents": [
                    _join(d.get("type_code"), d.get("id"))
                    for d in it.supporting_documents
                    if d.get("type_code") or d.get("id")
                ],
            }
        )
    return {"header": header, "items": items}


# Række-nøgler (legacy SAD/tabular), der hører til hoveddelen.
_ROW_HEADER_KEYS = (
    "lrn", "mrn", "procedure_category", "declaration_office", "invoice_currency",
    "exchange_rate", "importer_eori", "consignor_name", "dispatch_country",
    "destination_country", "border_mot", "inland_mot", "incoterm",
)


def _normalize_rows(rows: list[dict]) -> dict:
    """Analyseklare rækker (legacy SAD-PDF eller Excel/CSV) → normaliseret form."""
    first = rows[0] if rows else {}
    header = {
        "procedure_category": first.get("procedure_category"),
        "type_code": None,
        "lrn": first.get("lrn"),
        "mrn": first.get("mrn"),
        "declaration_office": first.get("declaration_office"),
        "invoice_amount": None,  # gamle udtræk bærer kun pris pr. varepost
        "invoice_currency": first.get("invoice_currency"),
        "exchange_rate": first.get("exchange_rate"),
        "exporter": first.get("consignor_name"),
        "importer_id": first.get("importer_eori"),
        "declarant_id": None,
        "dispatch_country": first.get("dispatch_country"),
        "destination_country": first.get("destination_country"),
        "border_mot": first.get("border_mot"),
        "inland_mot": first.get("inland_mot"),
        "transport_nationality": None,
        "incoterm": first.get("incoterm"),
        "delivery_location": None,
        "gross_mass_total": None,
    }
    items = []
    for i, r in enumerate(rows, start=1):
        hs, cn, taric = _split_commodity(r.get("commodity_code") or r.get("hs_code"))
        cur, prev, supp = _split_cpc(r.get("cpc"))
        items.append(
            {
                "item_number": r.get("item_number") or i,
                "description": r.get("description"),
                "hs_code": r.get("hs_code") or hs,
                "cn_code": cn,
                "taric_code": taric,
                "origin_country": r.get("origin_country"),
                "preferential_origin_country": r.get("preferential_origin_country"),
                "procedure_current": cur,
                "procedure_previous": prev,
                "supplementary_procedure": supp,
                "duty_regime_code": r.get("duty_regime_code"),
                "statistical_value": r.get("customs_value_dkk"),
                "item_invoice_amount": r.get("item_invoice_amount"),
                "valuation_method": None,
                "gross_mass": r.get("gross_mass"),
                "net_mass": r.get("net_mass"),
                "supplementary_units": None,
                "customs_duty": r.get("customs_duty"),
                "documents": [],
            }
        )
    return {"header": header, "items": items}


# ── Felt-kataloget: (nøgle, niveau, SAD-side, DMS-side, status, note, getter) ─
# Getter modtager hoveddelen hhv. vareposten og returnerer visningsværdien.

_HEADER_FIELDS = [
    ("decltype", "Boks 1", "Angivelse",
     "11 01 001 + 11 02 001", "Angivelsestype + supplerende type", "warn",
     "H1/H7/I1 er nu navnet på datasættet — ikke en kode i et felt.",
     lambda h: _join(h["type_code"], h["procedure_category"])),
    ("lrn", None, "Ingen rubrik",
     "12 09 001", "LRN", "newde",
     "Klarererens eget entydige nummer — identificerer angivelsen indtil MRN.",
     lambda h: _fmt(h["lrn"])),
    ("mrn", None, "MRN (påtegning)",
     "Nøgledata", "Angivelsens nummer (MRN)", "newde",
     "MRN følger angivelsen i alle statusser.",
     lambda h: _fmt(h["mrn"])),
    ("office", "Boks A/29", "Toldsted",
     "17 09/17 10", "Frembydelses-/tilsynstoldsted", "ok", None,
     lambda h: _fmt(h["declaration_office"])),
    ("exporter", "Boks 2", "Afsender/Eksportør",
     "13 01", "Eksportør", "ok",
     "Adressen er strukturerede underelementer (016/018-serien).",
     lambda h: _fmt(h["exporter"])),
    ("importer", "Boks 8", "Modtager / nr.",
     "13 04 017", "EORI-nr. — Importør", "ok",
     "Før CVR/SE-nummer — nu EORI-nummer.",
     lambda h: _fmt(h["importer_id"])),
    ("declarant", "Boks 14", "Klarerer / repræsentant",
     "13 05/13 06", "Klarerer + repræsentant", "warn",
     "Nu to adskilte parter med hver sin datagruppe.",
     lambda h: _fmt(h["declarant_id"])),
    ("invoice", "Boks 22", "Møntsort og fakturabeløb",
     "14 05/14 06 001", "Fakturavaluta + samlet beløb", "ok", None,
     lambda h: _join(h["invoice_currency"], h["invoice_amount"])),
    ("rate", "Boks 23", "Vekselkurs",
     "14 09 001", "Vekselkurs", "ok",
     "Udfyldes kun ved forud aftalt kurs — ellers bruger DMS dagskursen.",
     lambda h: _fmt(h["exchange_rate"])),
    ("dispatch", "Boks 15", "Afsendelsesland",
     "16 06 001", "Afsendelsesland", "ok", None,
     lambda h: _fmt(h["dispatch_country"])),
    ("destination", "Boks 17", "Bestemmelsesland",
     "16 03 001", "Bestemmelsesland", "ok", None,
     lambda h: _fmt(h["destination_country"])),
    ("motborder", "Boks 25", "Transportmåde ved grænsen",
     "19 03 001", "Transportmåde ved grænsen", "ok", None,
     lambda h: _fmt(h["border_mot"])),
    ("motinland", "Boks 26", "Indenlandsk transportmåde",
     "19 04 001", "Transportmåde indenfor EU", "ok", None,
     lambda h: _fmt(h["inland_mot"])),
    ("transportnat", "Boks 21", "Aktivt transportmiddels nationalitet",
     "19 08 062", "Nationalitet, aktivt transportmiddel", "ok", None,
     lambda h: _fmt(h["transport_nationality"])),
    ("delivery", "Boks 20", "Leveringsbetingelser",
     "14 01 035/037/020", "Incoterm + lokalitet + land", "ok", None,
     lambda h: _join(h["incoterm"], h["delivery_location"])),
    ("grosstotal", "Boks 35", "Bruttomasse i alt (kg)",
     "18 04 001", "Bruttovægt (hoveddel)", "ok", None,
     lambda h: _fmt(h["gross_mass_total"])),
]

_ITEM_FIELDS = [
    ("itemno", "Boks 32", "Varepost nr.",
     "11 03 001", "Varepostnummer", "ok", None,
     lambda it: _fmt(it["item_number"])),
    ("description", "Boks 31", "Varebeskrivelse (del af samleboksen)",
     "18 05 001", "Varebeskrivelse", "warn",
     "Boks 31 er splittet: beskrivelse (18 05), kolli (18 06), containere (19 07).",
     lambda it: _fmt(it["description"])),
    ("commodity", "Boks 33", "Varekode",
     "18 09 056/057/058", "HS + KN + TARIC", "warn",
     "Samme 10 cifre — maskinlæsbart adskilt i DMS.",
     lambda it: _join(it["hs_code"], it["cn_code"], it["taric_code"])),
    ("origin", "Boks 34", "Oprindelsesland",
     "16 08 001", "Oprindelsesland", "warn",
     "Præferenceoprindelse (16 09) er sit eget felt i DMS.",
     lambda it: _fmt(it["origin_country"])),
    ("preforigin", "Boks 34 (implicit)", "Præference-oprindelse",
     "16 09 001", "Præferenceoprindelsesland", "newde",
     "Udfyldes når præference påberåbes (14 11 ≠ 100).",
     lambda it: _fmt(it["preferential_origin_country"])),
    ("preference", "Boks 36", "Præference",
     "14 11 001", "Præference", "ok",
     "Samme trecifrede koder (100 = ingen).",
     lambda it: _fmt(it["duty_regime_code"])),
    ("procedure", "Boks 37", "Procedure",
     "11 09 001/002 + 11 10 001", "Anmodet + forudgående + supplerende", "warn",
     "Samme 7 cifre — formaliseret som separate elementer i DMS.",
     lambda it: _join(it["procedure_current"], it["procedure_previous"],
                      it["supplementary_procedure"])),
    ("net", "Boks 38", "Nettomasse (kg)",
     "18 01 001", "Nettovægt", "ok", None,
     lambda it: _fmt(it["net_mass"])),
    ("gross", "Boks 35", "Bruttomasse (kg)",
     "18 04 001", "Bruttovægt", "ok", None,
     lambda it: _fmt(it["gross_mass"])),
    ("suppunits", "Boks 41", "Supplerende enheder",
     "18 02", "Supplerende enheder", "ok", None,
     lambda it: _fmt(it["supplementary_units"])),
    ("itemprice", "Boks 42", "Varens pris",
     "14 08 001", "Varepost fakturaværdi", "ok", None,
     lambda it: _fmt(it["item_invoice_amount"])),
    ("valuation", "Boks 43", "Værdiansættelsesmetode",
     "14 10 001", "Værdiansættelsesmetode", "ok", None,
     lambda it: _fmt(it["valuation_method"])),
    ("statvalue", "Boks 46", "Statistisk værdi (DKK)",
     "99 06 001", "Statistisk værdi", "move",
     "Flyttet til gruppe 99 — fortsat grundlaget for toldværdi/EDR.",
     lambda it: _fmt(it["statistical_value"])),
    ("duty", "Boks 47", "Beregnet told (A-serien)",
     "14 03", "Beregning af told og afgifter", "ok",
     "A00 = told, B00 = importmoms; beregnes af DMS.",
     lambda it: _fmt(it["customs_duty"])),
    ("documents", "Boks 40/44", "Forudgående dokument / dokumenter",
     "12 01/12 02/12 03", "Henvisninger (gruppe 12)", "warn",
     "Én rubrik → fem strukturerede lister i gruppe 12.",
     lambda it: _join(*it["documents"], sep=" · ") if it["documents"] else None),
]


def _build_fields(specs, data) -> list[dict]:
    out = []
    for key, sad_box, sad_label, dms_de, dms_label, status, note, getter in specs:
        value = getter(data)
        out.append(
            {
                "key": key,
                "status": status,
                "status_label": _STATUS_LABELS[status],
                "note": note,
                "value": value,  # None = kunne ikke udlæses af kilden
                "sad": {"box": sad_box, "label": sad_label},
                "dms": {"de": dms_de, "label": dms_label},
            }
        )
    return out


def build_translation(norm: dict, source_format: str) -> dict:
    """Normaliseret angivelse → felt-par, dækning og retning (JSON-klar)."""
    header_fields = _build_fields(_HEADER_FIELDS, norm["header"])
    item_sections = [
        {"item_number": it["item_number"], "fields": _build_fields(_ITEM_FIELDS, it)}
        for it in norm["items"]
    ]

    all_fields = header_fields + [f for sec in item_sections for f in sec["fields"]]
    filled = [f for f in all_fields if f["value"] is not None]
    missing = [f for f in all_fields if f["value"] is None]

    direction = "ny_til_gammel" if source_format == "wco_xml" else "gammel_til_ny"
    return {
        "source_format": source_format,
        "direction": direction,
        "items_count": len(item_sections),
        "header_fields": header_fields,
        "item_sections": item_sections,
        "coverage": {
            "filled": len(filled),
            "total": len(all_fields),
            "missing_keys": sorted({f["key"] for f in missing}),
        },
        "lossy_source": source_format == "legacy_sad",
    }


def translate_upload(data: bytes, filename: Optional[str] = None) -> dict:
    """Én uploadet fil → format-detektion → parsning → parret oversættelse.

    Filen behandles kun i hukommelsen og modificeres aldrig (datapolitik).
    """
    fmt = detect_format(data, filename)
    if fmt == "wco_xml":
        norm = _normalize_declaration(parse_wco_xml(data))
    elif fmt == "legacy_sad":
        norm = _normalize_rows(parse_legacy_sad(data))
    else:
        norm = _normalize_rows(parse_tabular(data, filename=filename))
    if not norm["items"]:
        raise ValueError("Angivelsen indeholder ingen vareposter.")
    return build_translation(norm, fmt)
