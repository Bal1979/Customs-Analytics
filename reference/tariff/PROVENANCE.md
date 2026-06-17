# Tarif-referencedata — proveniens

Driver told-motoren (MFN-satser + præference-/aftaledækning) bag opslagslaget
`customs/tariff.py` og tjekkene i `customs/duty_checks.py`.

## Status: SEED (kurateret, illustrativt)

`seed_mfn_rates.csv` og `arrangements.json` er et **kurateret seed** der dækker de
JYSK-relevante kapitler (møbler 9401/9403/9404, tekstil 6301–6303, plast 3926, glas
7013) + EU's aftale-/præferencedækning pr. oprindelsesland. Det gør motoren fuldt
funktionel og testbar nu. Satserne er realistiske, men **ikke** en autoritativ kilde.

## Produktionskilde (besluttet 2026-06-16): officiel TARIC bulk (DG TAXUD)

Erstattes 1:1 (samme schema) af fuld TARIC-data via `tools/sync_taric.py`:
- Varenomenklatur (10-cifret) + beskrivelser.
- Erga omnes / tredjelands-MFN pr. kode.
- Præference-measures pr. geografisk område (FTA/GSP/GSP+/EBA).
Versioneres med udgivelsesdato, som skat/dms-public og ERST-data i SAF-T.

## Ingest-pipeline (bygget 2026-06-16)

`tools/sync_taric.py` omsætter det officielle TARIC-ekstrakt (nomenklatur + measures +
geo-grupper) til `mfn_rates.csv` + `arrangements.json`, som tariferingslaget foretrækker
frem for seed (`seed_*`). Testet mod `tests/fixtures/taric_sample/`.

**Sidste brik:** den fulde TARIC-bulk er gated bag CIRCABC/DDS og kan ikke auto-hentes.
Hent månedlig XLSX fra DG TAXUD/CIRCABC og kør:
    python tools/sync_taric.py --nomenclature <nom>.xlsx --measures <mea>.xlsx --geo-groups <grp>.csv
Verificér kolonnenavne mod det faktiske ekstrakt (parseren matcher gængse aliaser).

## FULD MFN-tarif integreret (2026-06-17)

`reference/tariff/mfn_rates.csv` er nu **rigtig, autoritativ data**: 15.767 deklarérbare
varekoder med tredjelands-MFN-satser + officielle danske beskrivelser, udtrukket fra
Skattestyrelsens fulde toldtarif (`info.skat.dk/download/told/toldtarif_ext.zip`,
eVita-XML, gratis, ingen login) via `python tools/sync_taric.py --evita <zip>`.
Genskab/opdatér: `tools/fetch_taric.sh evita` → `sync_taric.py --evita`.

Præferencer (per-land FTA/GSP) er IKKE i eVita-ekstraktet → drives fortsat af det
kuraterede `seed_arrangements.json` (22 lande). Per-HS-præferencesatser kan tilføjes
fra DDS/Trader Export Total-filerne (tot/Measure_* + tot/GeographicalArea_*).

## Per-HS præferencer integreret (2026-06-17)

`preferential_rates.csv` (90.182 hs×område-satser, 12.248 koder) + `geo_areas.json`
(land→grupper + danske områdenavne) er udtrukket fra Skattestyrelsens Trader Export
Total-filer (`info.skat.dk/download/told/tot/Measure_<dato>.xml` ~1,2 GB +
`GeographicalArea_<dato>.xml`, gratis, ingen login) via `tools/sync_preferences.py`.

Opslag i `tariff.py`: HS-specifikt med kode-arv (10→8→6→4→2 cif., da measures hænger på
forælderkoden) + gruppe-opløsning (land → geografiske grupper). Begrænsning: udelukkelser
(`measureExcludedGeographicalArea`) og oprindelsesregler ignoreres → præferencen er
"potentiel" (matcher FTA-mulighed-tjekkets formål). Opdatér med nyere Trader Export-dato.

## Temporal korrekthed (2026-06-17)

`preferential_rates.csv` har nu kolonnerne `date_start`/`date_end` pr. measure (alle
gyldighedsperioder bevaret). `tariff.lookup(hs, origin, date)` matcher kun præferencer
i kraft på importdatoen — en ny FTA anvendes ikke på en ældre transaktion.

Kendte næste-trin (dokumenteret): (1) temporal MFN (eVita er nutidssnapshot; historisk
MFN ligger i Trader Export type-103 m. datoer — men told-tjek bruger faktisk betalt told,
så lav prioritet); (2) temporal gruppemedlemskab (GSP-graduering), p.t. nuværende medlemskab.

## Temporal MFN + autonome suspensioner (2026-06-17)

`third_country_rates.csv` (fra Trader Export Measure) bærer den temporale tredjelandssats:
measureType 103 (MFN) + 112 (autonom toldsuspension, alle lande, ubetinget), erga omnes,
med date_start/date_end. `tariff.mfn_rate(hs, date)` = laveste gældende på datoen → suspenderet
kode giver 0 %, og MFN er dato-bevidst. Type 115 (end-use, betinget) udeladt. Fallback til
eVita-snapshot. Tilbage: temporal gruppemedlemskab (GSP-graduering).

## Temporal gruppemedlemskab (2026-06-17)

geo_areas.json' country_groups bærer nu medlemskabsperioder: {land: [[gruppe, ds, de], ...]}.
tariff opløser et lands grupper PÅ importdatoen, så GSP-graduering respekteres (fx Kina i
GSP-gruppen til 2014-12-31 → 2013-import får GSP, 2016-import ikke). Sidste dokumenterede
afgrænsning er hermed lukket; oprindelsesvurdering forbliver bevidst uden for scope.
