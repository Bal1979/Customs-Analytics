# Ændringslog — Customs Analytics regelkatalog & dokumentationspakke

Versionering følger regelkataloget (`customs/rules/Customs-Validation-Rules.json`,
felt `catalog_version`). Dokumentationspakken versioneres sammen med koden.

## 0.2.0 — 2026-07-01

**CUS-X01 flyttet planlagt → implementeret** (DMS-XML strukturvalidering).

- Ny `customs/xsd_validation.py`: velformetheds-tjek (RØD, XXE slået fra) +
  strukturvalidering af DMS-XML mod de officielle **H1 V2.5 / I1 V2.3**-skemaer
  (valgt på ProcedureCategory). Skemaafvigelser rapporteres **rådgivende (GUL)** —
  ikke som afvisning.
- **Fund:** Toldstyrelsens egne eksempel-XML'er afviger i elementrækkefølge fra de
  vendrede V2.5/V2.3-skemaer (versions-mismatch). Derfor er skema-laget bevidst
  rådgivende, ikke en hård port — så reelt brugbare angivelser ikke fejl-afvises.
- Valideringssuiten udvidet med CUS-X01-scenarie (**14 scenarier**, alle bestået);
  unit-tests i `tests/test_xsd_validation.py` (inkl. XXE-guard). 53 tests i alt.
- Regelkataloget nu **13 implementerede + 3 planlagte** kontroller. Matrix,
  valideringsrapport og de fire docx regenereret.

## 0.1.0 — 2026-06-18

Første version af governance-rammen (samme skabelon som SAF-T/VIES/VAT Analytics/
Data Extract). Etablerer fundamentet; flere områder står ærligt som Udkast/Åbent.

**Regelkatalog (nyt):**
- 12 implementerede kontroller i 5 lag:
  - Lag 1 (struktur): CUS-H01 (varekode 10 cifre), CUS-C01 (CPC 7 tegn).
  - Lag 2 (konsistens): CUS-W01 (brutto-total), CUS-W02 (netto≤brutto), CUS-V01 (toldværdi).
  - Lag 3 (oprindelse): CUS-O01 (oprindelse), CUS-P01 (præference-oprindelse).
  - Lag 4 (tarifering): CUS-P02 (manglende FTA), CUS-P03 (ugyldig præference), CUS-E01 (EDR).
  - Lag 5 (klassifikation): CUS-K01 (eksakt), CUS-K02 (fuzzy).
- 4 planlagte kontroller (status `planned`): CUS-V02 (statistisk værdi vs. faktura),
  CUS-X01 (XSD-strukturvalidering), CUS-AD01 (anti-dumping), CUS-E02 (strammet RØD EDR).

**Valideringssuite (nyt):**
- `validation/` med plantet defekt pr. implementeret kontrol + ren baseline.
- Kører kontrollerne via deres rigtige indgange; gated i `tests/test_validation_suite.py`.
- Auto-genereret `docs/Customs-Analytics_Valideringsrapport.md` (13 scenarier, alle bestået).

**Dokumentationspakke (nyt):**
- Godkendelses-overblik, Solution Architecture, Sikkerhed og databehandling (Udkast),
  Hosting og drift (Udkast) — genereret af `tools/build_approval_docs.js`.
- Regel-sporbarhedsmatrix (xlsx) genereret af `tools/build_traceability.py`.
- README (pakke-indeks) + denne CHANGELOG.

**Åbent (listet i Godkendelses-overblikket §4):** CI-pipeline, central balai_auth-
migrering, EU data-residency, fuld TARIC-sync (anti-dumping/suspension/kvote →
stram EDR til RØD), stress-test på rigtige klientdata, ekstern penetrationstest,
samt jura-review af sikkerheds-/databehandlingsdokumentet.
