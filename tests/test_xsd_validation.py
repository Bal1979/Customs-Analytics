"""Tests for CUS-X01 — DMS-XML velformethed + strukturvalidering (customs/xsd_validation.py)."""

from pathlib import Path

from customs.xsd_validation import validate_dms_xml

FIX = Path(__file__).resolve().parent / "fixtures"
DMS = "urn:wco:datamodel:WCO:DEC-DMS:2"


def test_malformed_xml_is_red():
    findings = validate_dms_xml(
        f"<ns2:Declaration xmlns:ns2='{DMS}'><ns2:ProcedureCategory>H1"
        "</ns2:ProcedureCategory><Uafsluttet>".encode()
    )
    assert any(f.code == "CUS-X01" and f.severity == "red" for f in findings)


def test_official_h1_deviation_is_yellow():
    findings = validate_dms_xml((FIX / "official_h1_standard.xml").read_bytes())
    assert any(f.code == "CUS-X01" and f.severity == "yellow" for f in findings)


def test_official_i1_deviation_is_yellow():
    findings = validate_dms_xml((FIX / "official_i1_preference_uk.xml").read_bytes())
    assert any(f.code == "CUS-X01" and f.severity == "yellow" for f in findings)


def test_wellformed_unknown_category_is_clean():
    xml = f"<ns2:Declaration xmlns:ns2='{DMS}'><ns2:ProcedureCategory>H7</ns2:ProcedureCategory></ns2:Declaration>".encode()
    assert validate_dms_xml(xml) == []


def test_xxe_is_disabled_no_file_disclosure():
    xxe = (
        '<?xml version="1.0"?><!DOCTYPE d [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
        f'<ns2:Declaration xmlns:ns2="{DMS}"><ns2:ProcedureCategory>&x;</ns2:ProcedureCategory></ns2:Declaration>'
    ).encode()
    findings = validate_dms_xml(xxe)
    joined = " ".join(f.message for f in findings)
    # Ekstern entity må ALDRIG opløses (intet filindhold i beskeden).
    assert "root:" not in joined and "/bin/" not in joined
