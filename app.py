"""Customs Analytics — web-lag (Flask).

Tyndt lag oven på ``customs/``-pakken: serverer Imports Summary-dashboardet og et
JSON-API. Følger datapolitikken fra søsterprojekterne: **uploadede filer parses i
hukommelsen og kasseres straks** — intet gemmes på disk, filen modificeres aldrig.
"""

from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from customs.analytics import build_report
from customs.classification import classification_report
from customs.duty_checks import fta_opportunities
from customs.parsers.tabular import parse_tabular
from customs.tariff import TariffDatabase

TARIFF = TariffDatabase()  # indlæses én gang ved opstart


def _full_report(rows):
    return {
        **build_report(rows),
        "fta": fta_opportunities(rows, TARIFF),
        "classification": classification_report(rows, TARIFF),
    }

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024  # 64 MB upload-loft

SAMPLE = Path(__file__).resolve().parent / "sample_data" / "jysk_like_imports.csv"


def _jsonable(obj):
    """Konvertér Decimal -> float rekursivt, så summary kan serialiseres til JSON."""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_jsonable(v) for v in obj]
    return obj


@app.get("/")
def index():
    return render_template("dashboard.html")


@app.get("/api/summary")
def api_summary():
    """Fuld kerne-rapport på den medfølgende demodata (syntetisk, JYSK-lignende)."""
    rows = parse_tabular(SAMPLE)
    return jsonify({"dataset": "demo", "rows": len(rows), **_jsonable(_full_report(rows))})


@app.post("/api/upload")
def api_upload():
    """Parse en uploadet CSV/XLSX i hukommelsen og returnér summary. Intet gemmes."""
    file = request.files.get("file")
    if file is None or not file.filename:
        return jsonify({"error": "Ingen fil modtaget."}), 400
    try:
        rows = parse_tabular(file.read(), filename=file.filename)
    except Exception as exc:  # robust fejlbesked til brugeren
        return jsonify({"error": f"Kunne ikke læse filen: {exc}"}), 422
    if not rows:
        return jsonify({"error": "Filen indeholder ingen rækker."}), 422
    return jsonify(
        {"dataset": file.filename, "rows": len(rows), **_jsonable(_full_report(rows))}
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5005))
    debug = os.environ.get("FLASK_ENV") != "production"
    app.run(debug=debug, host="0.0.0.0", port=port)
