#!/usr/bin/env bash
# Fuld, fokuseret vedligeholdelse af tarif-motoren: henter de officielle TARIC-kilder
# (gratis, ingen login), regenererer referencedata og kører selvtjek (pytest).
# Kan køres manuelt (på Mac) eller af den månedlige GitHub Action.
#
#   ./tools/update_tariff.sh
#
# PYTHON kan sættes (CI: PYTHON=python). Default: venv/bin/python hvis det findes.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-$([ -x venv/bin/python ] && echo venv/bin/python || echo python3)}"
UA="Mozilla/5.0 (Macintosh) AppleWebKit/537.36"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "==> Tarif-opdatering startet ($(date -u +%Y-%m-%dT%H:%MZ)). Python: $PYTHON"

# 1) MFN + hele HS-listen: Skattestyrelsens fulde danske toldtarif (stabil URL).
echo "==> [1/3] Henter MFN-tarif (toldtarif_ext.zip) ..."
curl -fsSL -A "$UA" "https://info.skat.dk/download/told/toldtarif_ext.zip" -o "$WORK/evita.zip"
"$PYTHON" tools/sync_taric.py --evita "$WORK/evita.zip"

# 2) Per-HS præferencer: Trader Export Total (nyeste dato findes dynamisk).
echo "==> [2/3] Finder nyeste Trader Export-dato ..."
PAGE="$(curl -fsSL -A "$UA" "https://info.skat.dk/data.aspx?oid=2247456")"
DATE="$(printf '%s' "$PAGE" | grep -oE 'tot/Measure_[0-9]{4}-[0-9]{2}-[0-9]{2}\.xml\.zip' \
        | grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2}' | sort -r | head -1)"
[ -n "$DATE" ] || { echo "FEJL: kunne ikke finde Trader Export-dato."; exit 1; }
echo "    nyeste totaludgivelse: $DATE"
BASE="https://info.skat.dk/download/told/tot"
curl -fsSL -A "$UA" "$BASE/Measure_$DATE.xml.zip"         -o "$WORK/measure.zip"
curl -fsSL -A "$UA" "$BASE/GeographicalArea_$DATE.xml.zip" -o "$WORK/geo.zip"
( cd "$WORK" && unzip -oq measure.zip && unzip -oq geo.zip )
"$PYTHON" tools/sync_preferences.py \
  --measure "$WORK/Measure_$DATE.xml" --geo "$WORK/GeographicalArea_$DATE.xml"

# 3) Selvtjek: motoren skal stadig bestå alle tests på de nye data.
echo "==> [3/3] Selvtjek (pytest) ..."
"$PYTHON" -m pytest -q

echo "==> Færdig. Ændrede referencedata:"
git status --short reference/tariff/ || true
echo "==> Datokilde: Trader Export $DATE; MFN: toldtarif_ext (seneste)."
