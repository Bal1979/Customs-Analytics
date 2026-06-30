# Dokumentation — Customs Analytics

Denne mappe indeholder produkt-/værktøjsdokumentationen for Customs Analytics
(told- og importanalyse af danske DMS/WCO-importdata). Dokumenterne versioneres
bevidst **sammen med koden**, så de altid matcher den version af produktet, de
beskriver (samme commit, samme git-historik).

Rammen er **identisk med søsterværktøjernes** (SAF-T, VIES, VAT Analytics, Data
Extract). Customs Analytics er det yngste værktøj i porteføljen, så flere områder
står ærligt som **Udkast** eller **Åbent** — se Godkendelses-overblikket §3–§4.

## Indhold

| Fil | Indhold |
|-----|---------|
| `Customs-Analytics_Godkendelses-overblik.docx` | **Start her.** Forside- og statusdokument: samler hele pakken, viser parathed pr. område (Dækket/Udkast/Åbent) og lister de åbne punkter med næste skridt og ejer. Tag dette med til EY's tool-governance. |
| `Customs-Analytics_Solution_Architecture.docx` | Løsnings- og arkitekturbeskrivelse: formål, afgrænsning, teknologistack, arkitektur, dataflow, den 5-lags kontrol-/analysemodel, told-/tariferingsmotor, referencedata-provenance, kvalitetssikring, ændringsstyring, hosting, begrænsninger og åbne punkter. Inkl. appendikser (modulinventar, ordliste). |
| `Customs-Analytics_Regel-sporbarhedsmatrix.xlsx` | Sporbarhedsmatrix: hver kontrol mappet til autoritativ kilde (Toldstyrelsen/DMS, TARIC, EU-FTA) → modul → test. Plus fane for referencedata-provenance. Genereret fra regelkataloget med `python tools/build_traceability.py`. |
| `Customs-Analytics_Sikkerhed_og_databehandling.docx` | Sikkerheds- og databehandlingsbeskrivelse: datakategorier, dataflow/dataminimering (in-memory, intet gemmes), GDPR/behandlingsgrundlag, adgangskontrol, trusselsmodel, underdatabehandlere, logning. (Udkast — skal review'es af jura/databeskyttelse og sikkerhed.) |
| `Customs-Analytics_Hosting_og_drift.docx` | Hosting, drift, roller og support: nuværende (Railway) vs. mål (EY-platform), migrationsplan, miljø-/konfig-inventar, backup/BCDR, roller/ansvar og support-/vedligeholdelsesmodel. (Udkast.) |
| `Customs-Analytics_Valideringsrapport.md` | Auto-genereret valideringsrapport fra den uafhængige valideringssuite (`validation/`): for hver implementeret kontrol bekræftes, at netop den rigtige kontrol fyrer på sit defekt-scenarie, og at en ren angivelse ikke udløser fund. Regenereres med `python -m validation.run_validation`. |
| `CHANGELOG.md` | Ændringslog pr. katalogversion — understøtter ændringsstyring og reproducerbarhed. |

Det maskinlæsbare regelkatalog ligger i `customs/rules/Customs-Validation-Rules.json`
(versioneret med `catalog_version`) og er kilden, som matrix og valideringsrapport
genereres fra.

## Sådan regenereres pakken

```
python -m validation.run_validation
python tools/build_traceability.py
npm install docx && node tools/build_approval_docs.js
```

(Node-artefakterne `package.json`, `package-lock.json` og `node_modules/` er
gitignored, så deploy-platformen ikke fejldetekterer en Node-app.)

## Status og brug

- **Kilde (source of truth):** Denne mappe + regelkataloget. Her redigeres og
  versioneres dokumentationen.
- **Officiel kopi (record of record):** Ved formel godkendelse lægges en kopi i
  EY's dokument-/governance-system. Repoet forbliver den levende kilde.
- **Klassifikation:** Fortroligt — internt. Dokumenterne må kun ligge i et
  **privat** repo og i EY-godkendte systemer.

## Vedligehold

Opdatér dokumenterne, når noget væsentligt ændres — især:

- Ny/ændret kontrol → opdatér `customs/rules/Customs-Validation-Rules.json`, bump
  `catalog_version`, opdatér valideringssuite + matrix + CHANGELOG.
- Ændret hosting/sikkerhed/datapolitik → opdatér de relevante afsnit.
- Ændret referencedata-kilde/-mekanisme → opdatér Solution Architecture §7 +
  referencedata-fanen i matrixen.

Dokumenterne er genereret med versionsnummer og dato på forsiden; hæv versionen
ved hver væsentlig revision.
