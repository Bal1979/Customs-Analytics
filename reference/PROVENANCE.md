# Referencedata — proveniens

Officiel DMS-referencedata fra Toldstyrelsen, vendret fra det offentlige repo
**[skat/dms-public](https://github.com/skat/dms-public)** (kilde-commit i
`SOURCE_COMMIT.txt`). Genbruges som fundament — samme princip som ERST-data i
SAF-T Validator. Opdateres versioneret når Toldstyrelsen frigiver nyt.

## Indhold

- `xsds/` — XML-skemaer (struktur-validering). Vendret lukning for **H1** og **I1**:
  `H1_XSDS`, `I1_XSDS`, `DMS_DS` (delte WCO/UNECE/EDS-typer), `APPLICATION_XSDS`.
  Øvrige angivelsestyper (H2–H7, G-serien, eksport, transit) er udeladt indtil behov.
- `codelists/` — officielle kodelister + forretningsregler:
  - `Codelists - Import.xlsx`, `Codelists - Global.xlsx`
  - `Validation rules and Error codes.xlsx`, `Error and warning codes.xlsx`
- `docs/DMS_IMPORT v1.2.xlsx` — datamodel-specifikation (import).

## Ikke vendret (hentes ved behov)

Export/Transit-XSD'er, 22 MB officielle test-cases, onboarding-PDF'er. De officielle
test-XML'er vi bruger som fixtures ligger i `tests/fixtures/`.
