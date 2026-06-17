# Customs Analytics — projektkontekst (agent hand-off)

Kontinuitets-note: hvor projektet er, hvorfor valgene blev truffet, og hvad der er
åbent. Hold den opdateret ved væsentlige ændringer.

## Hvad er det

Bal AI-værktøj til **told- og importanalyse** af danske importdata. Femte produkt i
porteføljen (saft/vat/vies/vat-extract). Modelleret på **VAT Analytics**-mønstret:
Flask-web-lag tyndt, al forretningslogik i den testbare `customs/`-pakke, genbrugt
auth/datapolitik. Fagligt forlæg: en told-importanalyse-rapport (9 analysesider, anonymiseret forlæg).
Mål: EY-godkendelse, som søsterprojekterne. Front-end vægtes højt (rigtige
dashboards) men i **Bal AI's lyse navy-identitet** (#1B365D på hvid, IBM Plex Sans),
ikke EY's mørke/gule look.

## Status (pr. 2026-06-16) — Fase 0 færdig, Fase 1 påbegyndt

- **Fase 0:** kanonisk datamodel (`customs/schema.py`), **WCO DMS-XML-parser**
  (`customs/parsers/wco_xml.py`), **sanity-tjek** (`customs/sanity.py`), officiel
  referencedata i `reference/` (H1/I1-XSD'er + codelists), kilde-commit i
  `reference/SOURCE_COMMIT.txt`.
- **Fase 1 (i gang):** analyselag (`customs/analytics.py`) med **hele analyse-kernen** —
  Imports Summary, Supplier Overview, Sourcing, CPC-analyse, Transport (grænse+indland,
  nettovægt); samlet via `build_report()`. **Excel/CSV-adapter**
  (`customs/parsers/tabular.py`), syntetisk demodata (`tools/generate_sample.py` →
  `tests/fixtures/sample_imports.csv`) og **faneopdelt dashboard** (`app.py` +
  `templates/dashboard.html` + `static/`) i Bal AI-identitet (ECharts: choropleth-verdenskort,
  linje, bar, donut, tabeller). Verdenskort-GeoJSON vendret i `static/world.json`
  (apache/echarts testdata, keyed by `name`; ISO2→navn-map i `dashboard.js`).
- **Fase 2 (i gang) — told-motoren:** tariferingslag (`customs/tariff.py`) med opslag
  HS×oprindelse → MFN/præferencesats/aftale; told-faglige tjek (`customs/duty_checks.py`):
  CUS-P02 manglende FTA-mulighed, CUS-P03 ugyldig præference (rød), CUS-E01 EDR-rimelighed;
  **FTA Opportunities**-rapport + UI-fane. Kører p.t. på **kurateret seed** (`reference/tariff/`,
  relevante kapitler + EU's aftaledækning); produktionskilde = officiel TARIC bulk
  (DG TAXUD), sync scaffoldet i `tools/sync_taric.py`. Demodata: told = 0 når præference
  påberåbt (kode 300), ellers MFN.
- **Fase 3 (delvist) — klassifikation:** `customs/classification.py` med **eksakt
  konsistens** (samme beskrivelse → flere HS-koder = oplagte fejl) og **fuzzy matching**
  (token-Jaccard m. blokning på sjældent token, dependency-frit) der klynger varianter;
  begge med indikativ besparelse ved tilpasning til laveste anvendte MFN i gruppen.
  UI-fane "Klassifikation". Demodata injicerer nu fejlkvalificeringer (alt-HS) + beskrivelsesvarianter.
- **TARIC-ingest-pipeline** (`tools/sync_taric.py`) — **auto-download virker uden login**:
  DDS-mekanik fundet (`daily_publications.jsp` → `taric_management.jsp?...&message=extract`
  returnerer ZIP'en direkte). `--fetch-latest` (urllib) eller `tools/fetch_taric.sh` (curl,
  til sandkasse hvor Python-net er blokeret). Parser det **rigtige** DDS-ekstraktformat
  (Goods_Nomenclature: GOODS CODE/LANG_COD/DESCR_TEXT, flersproget → vælger DA/EN;
  Measures: GOODS CODE/MEAS_TYP_ID/GEOGR_AREA/DUTY) → `mfn_rates.csv` + `arrangements.json`,
  som `customs/tariff.py` foretrækker frem for seed (`seed_*`). Kolonne-mapping + MFN-udtræk
  (type 103/ERGA OMNES) verificeret mod ægte data. Også fixtur-format understøttet
  (`tests/fixtures/taric_sample/`).
  **FULD MFN-tarif integreret (via Skattestyrelsen):** `info.skat.dk/download/told/toldtarif_ext.zip`
  (gratis, ingen login) = hele den danske toldtarif (eVita-XML, 140 MB). `sync_taric.py --evita`
  streamer den (lxml iterparse, XXE fra) → `reference/tariff/mfn_rates.csv` med **15.767 deklarérbare
  koder + rigtige MFN-satser + officielle danske beskrivelser** (verificeret: gardiner 12 %, møbler
  0 %, sengeudstyr 3,7 %). `tariff.py` bruger den nu. `tools/fetch_taric.sh evita|dds` henter kilden.
- **Per-HS præferencer integreret (Trader Export Total):** `info.skat.dk/download/told/tot/`
  (gratis, ingen login) — `Measure_<dato>.xml` (~1,2 GB) + `GeographicalArea_<dato>.xml`.
  `tools/sync_preferences.py` streamer dem (lxml iterparse) → `reference/tariff/preferential_rates.csv`
  (**90.182 (hs×område)-satser på 12.248 koder**) + `geo_areas.json` (land→grupper + danske områdenavne).
  `tariff.py` slår nu HS-specifikt op med **kode-arv** (measures hænger på forælderkoden 8-cif →
  deklarérbare børn arver: prøv 10→8→6→4→2 cif.) og **gruppe-opløsning** (land → geografiske grupper).
  Verificeret: gardiner fra VN → præference 0 % (arvet fra 6303929000), aftale "Vietnam"; PK → "GSP+";
  BD → "GSP-EBA"; CN → ingen. Ægte data korrigerede seed-antagelser (fx Indien HAR GSP). Per-land-seed
  (`seed_arrangements.json`) er nu kun fallback. `tools/fetch_taric.sh trader` henter kilden.
- **FTA-grundlag dobbelttjekket (2026-06-17) mod EU Access2Markets' officielle FTA-liste:** alle EU's
  FTA'er/GSP/EPA'er er dækket. Krydstjek afslørede ét hul — **toldunioner** (Tyrkiet/San Marino/Andorra,
  measureType 106) lå ikke i de oprindelige præference-typer. Rettet: præference-typerne er nu
  **142 (toldpræference) + 145 (end-use) + 141 (præf. ifm. suspension) + 106 (toldunionsafgift)**;
  **143/146/147 (præferencetoldkontingenter)** medtages men **markeres som kvote** (`is_quota` i
  `preferential_rates.csv` + DutyLookup) → FTA-tjek/UI flagger "kvote — verificér åbning". 91.427 satser.
  Tyrkiet er nu korrekt med (industrivarer 0 % via toldunion). Suspensioner (112/115, erga omnes 0 %)
  bevidst udeladt af præferencer — relevant for EDR-tjek senere, ikke FTA.
- **TEMPORAL korrekthed (2026-06-17):** `preferential_rates.csv` bærer nu `date_start`/`date_end`
  pr. measure (211.285 rækker, alle gyldighedsperioder bevaret — ikke laveste-på-tværs-af-tid).
  `tariff.lookup(hs, origin, date)` matcher **kun præferencer der var i kraft på importdatoen** →
  en ny FTA lægges ikke ned over en gammel transaktion (verificeret: VN-gardin før EVFTA 2020-08-01
  → ingen præference; efter → 0 %). Importdatoen tages fra angivelsen (`issue_datetime`/`date`,
  både ISO og DMS-kompakt format normaliseres). `date=None` → kun aktuelt gældende. Told-tjekket
  bruger desuden **faktisk betalt told** fra angivelsen.
- **Temporal MFN + autonome suspensioner (2026-06-17):** `third_country_rates.csv` (38.396 rækker,
  13.309 koder) fra Trader Export — measureType **103 (MFN) + 112 (autonom toldsuspension, alle lande,
  ubetinget)**, erga omnes, med gyldighedsperioder. `tariff.mfn_rate(hs, date)` returnerer laveste
  gældende sats på datoen → en **suspenderet kode giver 0 %** (EDR-tjekket fejl-flagger den ikke længere),
  og MFN er nu dato-bevidst. Fallback til eVita-nutidssnapshot når temporal ikke dækker. Type 115
  (end-use-suspension, betinget) udeladt bevidst. Temporal gruppemedlemskab (GSP-graduering) er
  nu også løst (se nedenfor).
- **Temporal gruppemedlemskab (2026-06-17):** `geo_areas.json` country_groups bærer nu
  medlemskabsperioder ({land: [[gruppe, ds, de], ...]}); `tariff` opløser gruppemedlemskab
  PÅ importdatoen → GSP-graduering respekteres (verificeret: Kina i GSP-gruppen til 2014-12-31
  → 2013-import får GSP-sats 9,6 %, 2016-import ingen). Sidste temporale afgrænsning lukket;
  oprindelsesvurdering forbliver bevidst uden for scope (leverandørens ansvar).
- **41 tests** grønne. Kør appen via preview-config `customs-analytics` (port 5005)
  eller `venv/bin/python app.py`. Verificeret visuelt: alle 7 faner renderer korrekt.
  Repo: github.com/Bal1979/Customs-Analytics (månedlig TARIC-Action verificeret).

## Deploy (Railway → customs.balai.dk)

- Deploy-filer: `Procfile` + `railway.json` (gunicorn, 2 workers, gthread, `--preload` deler
  ~123 MB referencedata via COW, bind til `$PORT`), `.python-version` 3.13.
- **Env-variabler i prod (påkrævet):** `SECRET_KEY` (ellers tilfældig nøgle → sessions
  nulstilles ved genstart), `AUTH_DB_PATH=/data/auth.db`, `AUDIT_DB_PATH=/data/audit.db` på et
  **Railway persistent volume** mountet på `/data` (så brugere/login overlever genstarts/deploys).
- **Login (auth.py, porteret):** første kørsel → `/setup` opretter admin; derefter `/login` +
  invitationer (`/admin/invites`). CSRF på upload. data/*.db gitignored.
- Auto-deploy på `main` → den månedlige TARIC-Action holder produktionen frisk.

## Genoptag hurtigt

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
```

(Bal kører pytest lokalt og pusher — SSH ligger kun på hans Mac.)

## Arkitektur

- **DMS-format = WCO Data Model XML** (`urn:wco:datamodel:WCO:DEC-DMS:2`). Det er
  parserens primære target — PDF er kun en rendering. Legacy SAD (gl. toldsystem)
  og generisk Excel/CSV bliver sekundære adaptere i `customs/parsers/`.
- **Analyse-enhed = varepost** (`GovernmentAgencyGoodsItem`). Hoveddata arves ned;
  `Declaration.to_rows()` folder ud til én analyseklar række pr. varepost.
- **Toldværdi = statistisk værdi i DKK** (`StatisticalValueAmount` / 99 06 001).
  Told (afgiftsart A00) ≠ moms (B00). EDR = told ÷ toldværdi.
- **Præference:** `DutyRegimeCode` (14 11 001), 100 = ingen; ≠100 = påberåbt.
  `Origin TypeCode` 1 = oprindelsesland, 2 = præference-oprindelsesland.
- **Referencedata** (`reference/`) er forankret på Toldstyrelsens **skat/dms-public**
  (XSD'er til struktur-validering + codelists + forretningsregler). Synkroniseres
  versioneret med kildedato — samme princip som ERST-data i SAF-T.

## Vedligeholdelse af tarif-motoren (automatisk)

Referencedata (MFN + præferencer) holdes friske **automatisk**:
- `tools/update_tariff.sh` henter begge officielle kilder (toldtarif_ext = MFN; Trader
  Export Total = præferencer, nyeste dato findes dynamisk), regenererer
  `reference/tariff/{mfn_rates.csv,preferential_rates.csv,geo_areas.json}` og kører
  pytest som **selvtjek** (fanger format-ændringer). Kører lokalt på ~15 sek.
- `.github/workflows/update-tariff.yml` kører scriptet **den 2. i hver måned** (+ manuelt),
  committer de friske data, og fejler synligt hvis selvtjekket knækker (= alarm). Samme
  mønster som SAF-T's ERST-sync. Kræver at repoet er på GitHub m. Actions + push-ret
  (ved branch protection: skift `git push` til en PR).

## Konventioner

- Ny logik → tests først/samtidig; brug de officielle test-XML'er som fixtures.
- Beløb som `Decimal` (ingen float på toldværdier).
- Skriv dansk, klart og konkret. **Slet aldrig filer uden tilladelse; modificér
  aldrig den uploadede angivelse** — kun analysér/rapportér.

## Faseplan

- **Fase 0 (nu):** skelet + kanonisk skema + WCO-XML-parser + struktur-sanity-tjek.
- **Fase 1:** kerne-dashboards (Imports Summary, Supplier, Sourcing, CPC, Transport)
  i Bal AI-identitet; Flask-web-lag + JSON-API + ECharts.
- **Fase 2:** FTA-database (scrape præferencesatser pr. HS×land×aftale) +
  Taric MFN-satser → FTA Opportunities + EDR-rimelighed.
- **Fase 3:** Classification Analysis, Fuzzy Match, Import Supply Path (flowkort).
- **Fase 4:** godkendelsespakke (regelkatalog, valideringssuite, docx, CI, pip-audit).

## Åbne tråde

- **Fuld TARIC-data** (sidste brik): skaf den autoritative månedlige XLSX fra DG TAXUD/
  CIRCABC (interaktiv/registrering — ikke auto-fetchbar) og kør `tools/sync_taric.py` på den.
  Pipelinen er bygget+testet; verificér kolonnenavne mod det rigtige ekstrakt + tilføj
  anti-dumping/suspensioner/kvoter, så EDR-tjek kan strammes til RØD.
- ✅ Legacy SAD løst (2026-06-17): `customs/parsers/legacy_sad.py` parser rapportservlet-PDF'en
  fra det gamle toldsystem (SAD-bokse 33/34/36/37/38/42/46 + Beregninger A-serie=told, B=moms),
  med tekstudtræk (PyMuPDF, koordinat-parring) adskilt fra felt-logik (`_rows_from_lines`, testbar
  uden rigtige data). Struktureret Excel/CSV fra gl. system dækkes af tabular-adapterens SAD-aliaser.
  `app.py` dispatcher upload: .xml→WCO, .pdf→legacy SAD, .csv/.xlsx→tabular. 44 tests grønne.
- Klassifikation: forbedr fuzzy (rigtig string-similarity/embeddings) + brug en
  produkt-/varereference frem for beskrivelse når DMS-data har den; samkør med
  TARIC-beskrivelser for at foreslå den *korrekte* kode (ikke kun laveste sats).
- Indlæsning af de officielle codelists (openpyxl) til kode-opslag i sanity-tjek.
- XSD-struktur-validering wired mod `reference/xsds/` (lukning H1+I1 er vendret).
- Sanity-katalog udvides med Toldstyrelsens forretningsregler
  (`reference/codelists/Validation rules and Error codes.xlsx`).
- Bulk-input fra AEO-fuldeksport (Toldstyrelsen) — eksempelangivelserne er p.t.
  enkeltlinjer; syntetisk fler-linjes fixture mangler til dashboard-demo.
