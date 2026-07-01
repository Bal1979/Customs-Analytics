"""XSD-strukturvalidering af DMS-XML mod Toldstyrelsens officielle H1/I1-skemaer.

Kontrol **CUS-X01**. To niveauer, én finding-kode:

- **Velformethed (RØD):** kan XML'en overhovedet parses sikkert (XXE slået fra)?
  Er den ikke velformet, kan den ikke behandles → RØD.
- **Skemakonformitet (GUL, rådgivende):** velformet XML valideres mod det officielle
  skema valgt på ``ProcedureCategory`` (H1 → DMS_H1_V2.5, I1 → DMS_I1_V2.3). Afvigelser
  rapporteres som en GUL finding — de **afviser ikke** angivelsen, da parseren er
  navnerum-/rækkefølge-robust og reelle DMS-eksporter kan afvige let fra en given
  skemaversion. For procedurekategorier uden vendret skema køres kun velformetheds-tjek.

Bemærk (proveniens): de vendrede skemaer er H1 V2.5 / I1 V2.3 fra skat/dms-public.
Toldstyrelsens egne eksempel-XML'er afviger i elementrækkefølge fra netop disse
versioner — derfor er skema-laget bevidst rådgivende (gul), ikke en hård port.
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from customs.sanity import Finding, RED, YELLOW

_XSD_DIR = Path(__file__).resolve().parent.parent / "reference" / "xsds"
_SCHEMAS = {
    "H1": _XSD_DIR / "H1_XSDS" / "DMS_H1_V2.5.xsd",
    "I1": _XSD_DIR / "I1_XSDS" / "DMS_I1_V2.3.xsd",
}
_DMS_NS = "urn:wco:datamodel:WCO:DEC-DMS:2"
_schema_cache: dict[str, etree.XMLSchema] = {}


def _safe_parser() -> etree.XMLParser:
    """Parser med XXE og netværk slået fra (upload er utrusted input)."""
    return etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)


def _procedure_category(root) -> str | None:
    el = root.find(f"{{{_DMS_NS}}}ProcedureCategory")
    return el.text.strip() if el is not None and el.text else None


def _schema_for(category: str | None) -> etree.XMLSchema | None:
    if category not in _SCHEMAS:
        return None
    if category not in _schema_cache:
        _schema_cache[category] = etree.XMLSchema(etree.parse(str(_SCHEMAS[category])))
    return _schema_cache[category]


def validate_dms_xml(xml_bytes: bytes) -> list[Finding]:
    """Kør CUS-X01 på rå DMS-XML-bytes. Returnér 0-1 findings."""
    try:
        root = etree.fromstring(xml_bytes, parser=_safe_parser())
    except etree.XMLSyntaxError as exc:
        return [Finding("CUS-X01", RED,
                        f"DMS-XML er ikke velformet og kan ikke behandles: {exc}", None)]

    category = _procedure_category(root)
    schema = _schema_for(category)
    if schema is None:
        # Velformet; intet vendret skema for denne kategori → ingen strukturafvigelse.
        return []
    if schema.validate(root):
        return []

    errors = list(schema.error_log)
    sample = " | ".join(e.message[:160] for e in errors[:2])
    return [Finding("CUS-X01", YELLOW,
                    f"DMS-XML afviger fra det officielle {category}-skema "
                    f"({len(errors)} strukturafvigelse(r)): {sample}", None)]
