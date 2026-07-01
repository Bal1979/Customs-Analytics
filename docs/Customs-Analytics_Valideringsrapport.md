# Valideringsrapport — Customs Analytics

> **Auto-genereret** af `validation/run_validation.py`. Regenerér med `python -m validation.run_validation`. Rediger ikke i hånden.

- **Regelkatalog:** v0.2.0 (2026-07-01)
- **Scenarier:** 14 (14/14 bestået)
- **Metode:** Hvert scenarie planter præcis ÉN defekt i en ren baseline og kører kontrollen via dens rigtige indgang; det bekræftes, at netop den tilsigtede kontrol fyrer. En ren angivelse udløser ingen fund.

## Resultater

| Scenarie | Lag | Kontrol | Defekt | Forventet | Faktisk | Resultat |
|----------|-----|---------|--------|-----------|---------|----------|
| CUS-000 | — | Ren angivelse | Ingen defekt — gyldig 1-linjes angivelse | Ingen fund | ingen | ✓ Bestået |
| CUS-H01 | 1 · Struktur & format | Varekode er 10 cifre | TARIC-led afkortet → 9-cifret varekode | CUS-H01 fyrer | CUS-H01 | ✓ Bestået |
| CUS-C01 | 1 · Struktur & format | Procedurekode (CPC) er 7 tegn | Supplerende procedurekode 2 tegn → CPC bliver 6 tegn | CUS-C01 fyrer | CUS-C01 | ✓ Bestået |
| CUS-W01 | 2 · Intern konsistens (vægt & værdi) | Samlet bruttovægt ≥ Σ linje-brutto | Samlet bruttovægt (50) < linjesum (100) | CUS-W01 fyrer | CUS-W01 | ✓ Bestået |
| CUS-W02 | 2 · Intern konsistens (vægt & værdi) | Nettovægt ≤ bruttovægt pr. linje | Nettovægt (150) > bruttovægt (100) | CUS-W02 fyrer | CUS-W02 | ✓ Bestået |
| CUS-V01 | 2 · Intern konsistens (vægt & værdi) | Toldværdi udfyldt og positiv | Toldværdi sat til 0 | CUS-V01 fyrer | CUS-V01 | ✓ Bestået |
| CUS-O01 | 3 · Oprindelse & præference-krav | Oprindelsesland udfyldt | Oprindelsesland fjernet | CUS-O01 fyrer | CUS-O01 | ✓ Bestået |
| CUS-P01 | 3 · Oprindelse & præference-krav | Præference påberåbt → præference-oprindelse påkrævet | Præference påberåbt (300) uden præference-oprindelsesland | CUS-P01 fyrer | CUS-P01 | ✓ Bestået |
| CUS-P02 | 4 · Tarifering & told (TARIC/FTA) | Manglende FTA-mulighed | VN-oprindelse med præference, men ingen præference påberåbt (told betalt MFN) | CUS-P02 fyrer | CUS-P02 | ✓ Bestået |
| CUS-P03 | 4 · Tarifering & told (TARIC/FTA) | Ugyldig præference | Præference påberåbt (300) for CN, der ingen aftale har med EU | CUS-P03 fyrer | CUS-P03 | ✓ Bestået |
| CUS-E01 | 4 · Tarifering & told (TARIC/FTA) | EDR-rimelighed | CN-gardin (MFN 12 %), men told betalt 0 → effektiv sats 0 % | CUS-E01 fyrer | CUS-E01 | ✓ Bestået |
| CUS-X01 | 1 · Struktur & format | DMS-XML velformethed + skemavalidering | Ikke-velformet DMS-XML (uafsluttet tag) → kan ikke behandles | CUS-X01 fyrer | CUS-X01 | ✓ Bestået |
| CUS-K01 | 5 · Klassifikation | Eksakt klassifikationskonsistens | Samme beskrivelse 'Gardin' på to forskellige HS-koder | CUS-K01 flagger ≥1 gruppe | 1 gruppe(r) | ✓ Bestået |
| CUS-K02 | 5 · Klassifikation | Fuzzy klassifikationsklynger | Varianter 'Gardin syntetisk grå' og '... sort' på to HS-koder | CUS-K02 flagger ≥1 gruppe | 1 gruppe(r) | ✓ Bestået |

## Dækning

- **Implementerede kontroller:** 13
- **Dækket af et scenarie:** 13 / 13
- **Udækkede:** ingen ✓

Planlagte kontroller (status `planned` i kataloget) er bevidst ikke dækket, da de endnu ikke er implementeret.
