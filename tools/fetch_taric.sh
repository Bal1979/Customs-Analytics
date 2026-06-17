#!/usr/bin/env bash
# Henter officiel toldsatsdata. To kilder (begge gratis, ingen login):
#   ./tools/fetch_taric.sh evita   → Skattestyrelsens fulde danske tarif (toldtarif_ext.zip)
#                                     → kør derefter: python tools/sync_taric.py --evita <zip>
#   ./tools/fetch_taric.sh dds     → DG TAXUD DDS dagsekstrakt (delta)
set -euo pipefail
MODE="${1:-evita}"
UA="Mozilla/5.0 (Macintosh) AppleWebKit/537.36"
OUTDIR="reference/tariff/taric_raw"; mkdir -p "$OUTDIR"
if [ "$MODE" = "evita" ]; then
  OUT="$OUTDIR/toldtarif_ext.zip"
  echo "Henter Skattestyrelsens fulde toldtarif (eVita) ..."
  curl -sL -A "$UA" "https://info.skat.dk/download/told/toldtarif_ext.zip" -o "$OUT"
  echo "Gemt: $OUT ($(wc -c < "$OUT") bytes). Kør: python tools/sync_taric.py --evita $OUT"
else
  BASE="https://ec.europa.eu/taxation_customs/dds2/taric"
  html=$(curl -sL -A "$UA" "$BASE/daily_publications.jsp?Lang=en&Domain=TARIC")
  pub=$(printf '%s' "$html" | grep -oE 'publicationDate=[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}&message=extract' | head -1 | sed 's/publicationDate=//; s/&message=extract//')
  enc=$(printf '%s' "$pub" | sed 's/ /%20/')
  OUT="$OUTDIR/dds_latest.zip"
  curl -sL -A "$UA" "$BASE/taric_management.jsp?publicationDate=$enc&message=extract" -o "$OUT"
  echo "Gemt: $OUT (DDS delta $pub)"
fi

# Per-HS præferencer: Trader Export Total-filer (Measure + GeographicalArea).
#   ./tools/fetch_taric.sh trader  → henter de to filer; kør derefter:
#   python tools/sync_preferences.py --measure <Measure>.xml --geo <GeographicalArea>.xml
fetch_trader() {
  local UA="Mozilla/5.0 (Macintosh) AppleWebKit/537.36"
  local OUTDIR="reference/tariff/taric_raw"; mkdir -p "$OUTDIR"
  local d; d=$(date +%Y-%m-%d)
  echo "Hent nyeste dato fra info.skat.dk/data.aspx?oid=2247456 og indsæt i URLerne:"
  echo "  https://info.skat.dk/download/told/tot/Measure_<dato>.xml.zip"
  echo "  https://info.skat.dk/download/told/tot/GeographicalArea_<dato>.xml.zip"
}
[ "${1:-}" = "trader" ] && fetch_trader
