# Customs Analytics

Bal AI-værktøj til told- og importanalyse af danske importdata (DMS/WCO Data Model).
Analyserer tolddeklarationer — varebevægelser, oprindelse, told/EDR, procedurekoder,
transport og frihandelsaftaler (FTA) — og kører sanity-tjek mod Toldstyrelsens regler.

Status: **Fase 0** (skelet + WCO-XML-parser + sanity-tjek). Se `CLAUDE.md` for
arkitektur og faseplan.

## Kom i gang

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
```

## Struktur

- `customs/` — forretningslogik (kanonisk skema, parsere, sanity-tjek)
- `reference/` — officiel DMS-referencedata (XSD'er, codelists, regler) fra
  Toldstyrelsens [skat/dms-public](https://github.com/skat/dms-public)
- `tests/` — pytest + officielle DMS test-XML'er som fixtures
