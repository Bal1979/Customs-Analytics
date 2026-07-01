/*
 * Generér EY-godkendelses-dokumentationspakken (4 docx) for Customs Analytics.
 *
 * Kør:  cd <repo> && npm install docx && node tools/build_approval_docs.js
 *
 * BUILD-FÆLDE: hold Node-artefakterne (package.json, package-lock.json,
 * node_modules/) gitignored, så deploy-platformen ikke fejldetekterer en Node-app.
 * Indholdet afspejler ÆRLIGT værktøjets status (Dækket / Udkast / Åbent).
 */

const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  WidthType, ShadingType, AlignmentType, PageBreak,
} = require("docx");

const NAVY = "1B365D";
const LIGHT = "2E5C8A";
const DATE = "1. juli 2026";
const VERSION = "0.2.0";
const CONTENT_W = 9360;
const DOCS = path.resolve(__dirname, "..", "docs");

// ---- byggehjælpere -------------------------------------------------------
const H1 = (t) => new Paragraph({
  spacing: { before: 280, after: 120 },
  children: [new TextRun({ text: t, bold: true, color: NAVY, size: 26 })],
});
const H2 = (t) => new Paragraph({
  spacing: { before: 180, after: 80 },
  children: [new TextRun({ text: t, bold: true, color: LIGHT, size: 22 })],
});
const P = (t) => new Paragraph({
  spacing: { after: 120 }, children: [new TextRun({ text: t, size: 20 })],
});
const bullets = (items) => items.map((t) => new Paragraph({
  bullet: { level: 0 }, spacing: { after: 40 },
  children: [new TextRun({ text: t, size: 20 })],
}));

function cell(text, opts = {}) {
  return new TableCell({
    width: { size: opts.w || 1200, type: WidthType.DXA },
    shading: opts.header ? { fill: NAVY, type: ShadingType.CLEAR, color: "auto" } : undefined,
    margins: { top: 60, bottom: 60, left: 90, right: 90 },
    children: [new Paragraph({ children: [new TextRun({
      text: String(text), bold: !!opts.header,
      color: opts.header ? "FFFFFF" : "000000", size: 18,
    })] })],
  });
}
function table(headers, rows, widths) {
  const w = widths || headers.map(() => Math.floor(CONTENT_W / headers.length));
  return new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: w,
    rows: [
      new TableRow({ tableHeader: true, children: headers.map((h, i) => cell(h, { header: true, w: w[i] })) }),
      ...rows.map((r) => new TableRow({ children: r.map((c, i) => cell(c, { w: w[i] })) })),
    ],
  });
}
function titleBlock(subtitle) {
  return [
    new Paragraph({ spacing: { before: 1200, after: 0 },
      children: [new TextRun({ text: "Customs Analytics", bold: true, color: NAVY, size: 52 })] }),
    new Paragraph({ spacing: { after: 200 },
      children: [new TextRun({ text: subtitle, color: LIGHT, size: 30 })] }),
    P("Bal AI · told- og importanalyse af danske DMS/WCO-importdata"),
    P(`Version ${VERSION} · ${DATE}`),
    new Paragraph({ spacing: { before: 200 },
      children: [new TextRun({ text: "Klassifikation: Fortroligt — internt. Kun privat repo og EY-godkendte systemer.",
        italics: true, size: 18, color: "666666" })] }),
    new Paragraph({ children: [new PageBreak()] }),
  ];
}
function makeDoc(children) {
  return new Document({
    sections: [{
      properties: { page: { margin: { top: 1134, bottom: 1134, left: 1134, right: 1134 } } },
      children,
    }],
  });
}

// ---- 1) Godkendelses-overblik -------------------------------------------
const overblik = makeDoc([
  ...titleBlock("Godkendelses-overblik"),
  H1("1. Om dette dokument"),
  P("Dette er start-her-dokumentet for Customs Analytics' godkendelsespakke. Det samler hele pakken, viser parathed pr. område (Dækket / Udkast / Åbent) og lister de åbne punkter med næste skridt og ejer. Tag det med til EY's tool-governance."),
  P("Customs Analytics er det yngste værktøj i porteføljen (efter SAF-T, VIES, VAT Analytics og Data Extract). Rammen her er bevidst identisk med søsterværktøjernes, men flere områder står ærligt som Udkast eller Åbent — det er forventet på dette stadie. Et udfyldt Åbent-felt med næste skridt er bedre end et tomt."),
  H1("2. Værktøjet kort"),
  P("Customs Analytics analyserer danske importangivelser (WCO DMS-XML, gammelt toldsystem via SAD-PDF, samt Excel/CSV). Det giver told- og importanalyse — varebevægelser, oprindelse, effektiv toldsats — plus FTA-besparelsesmuligheder og fejlklassificering, oven på Toldstyrelsens egne TARIC-/tarifdata. Samme arkitektur som SAF-T/VIES: al forretningslogik i en testbar pakke, tyndt web-lag."),
  H1("3. Parathed pr. område"),
  table(["Område", "Status", "Bemærkning"], [
    ["Kanonisk datamodel + WCO DMS-XML-parser", "Dækket", "customs/schema.py + customs/parsers/ (XXE slået fra)"],
    ["DMS-XML strukturvalidering (XSD, CUS-X01)", "Dækket", "customs/xsd_validation.py — velformethed (rød) + skema-advis (gul); H1 V2.5 / I1 V2.3 (ny)"],
    ["Analyselag (dashboards)", "Dækket", "customs/analytics.py — 7 faner, verificeret visuelt"],
    ["Told- og tariferingsmotor (TARIC/eVita, temporal)", "Dækket", "customs/tariff.py — MFN + præferencer, dato-bevidst opslag"],
    ["Klassifikationslag (eksakt + fuzzy)", "Dækket", "customs/classification.py — dependency-frit"],
    ["Versioneret regelkatalog", "Dækket", "customs/rules/Customs-Validation-Rules.json v0.1.0 (ny)"],
    ["Regel-sporbarhedsmatrix", "Dækket", "docs/...Regel-sporbarhedsmatrix.xlsx (ny, genereret)"],
    ["Uafhængig valideringssuite", "Dækket", "validation/ — 13 kontroller, plantet defekt pr. kontrol, gated i pytest (ny)"],
    ["Automatiseret testsuite", "Dækket", "tests/ — kører uden netværk"],
    ["Datapolitik (in-memory, intet gemmes)", "Dækket", "Upload parses i hukommelsen; kun auth/audit på volume"],
    ["Adgangskontrol (login/auth)", "Dækket", "Lokal auth.py (pbkdf2, CSRF, rate-limit, persistent volume)"],
    ["Sikkerheds- og databehandlingsdoc", "Udkast", "Skal review'es af jura/databeskyttelse"],
    ["Hosting- og driftsdoc", "Udkast", "Railway i dag; EY-platform er åben beslutning"],
    ["CI (pytest + pip-audit --strict)", "Dækket", ".github/workflows/ci.yml — pytest + valideringssuite-gate + pip-audit (ny)"],
    ["Central balai_auth-migrering + fælles SECRET_KEY", "Åbent", "Kører i dag eget lokalt auth.py"],
    ["EU data-residency (Railway-volume)", "Åbent", "Volume-region skal verificeres/migreres til EU"],
    ["Fuld TARIC (anti-dumping/suspension/kvote)", "Åbent", "EDR-tjek bevidst tolerant (gul) indtil da"],
    ["Stress-test på rigtige klientdata", "Åbent", "AEO-fuldeksport mangler at blive kørt igennem"],
    ["Penetrationstest", "Åbent", "Ekstern; typiske fund foregrebet (XXE, headers, CSRF)"],
  ], [44, 16, 40]),
  H1("4. Åbne punkter — næste skridt og ejer"),
  table(["Punkt", "Næste skridt", "Ejer"], [
    ["Central auth-migrering", "Portér til balai_auth-shim; fælles SECRET_KEY; login deles på *.balai.dk", "Udvikling / Platform"],
    ["EU data-residency", "Verificér Railway-volumeregion; migrér US→EU; bekræft AUTH_/AUDIT_DB_PATH", "Drift"],
    ["Fuld TARIC-sync", "Hent DG TAXUD-bulk; tilføj anti-dumping/suspension/kvote; stram EDR til RØD (CUS-E02/AD01)", "Udvikling"],
    ["Sikkerheds- & databehandlingsdoc", "Review + udfyld behandlingsgrundlag, DPA, dataplacering", "Jura / DPO"],
    ["Hosting (EY-platform)", "Beslut målplatform; udfør migrationsplan (WSGI-agnostisk)", "EY tool-governance"],
    ["Stress-test", "Kør reel AEO-fuldeksport igennem; ret driftsfund ved roden", "Udvikling + kunde"],
    ["Penetrationstest", "Ekstern test af det deployede værktøj", "EY / ekstern"],
  ], [26, 56, 18]),
  H1("5. Dokumentpakken"),
  bullets([
    "Customs-Analytics_Godkendelses-overblik.docx — dette dokument (start her).",
    "Customs-Analytics_Solution_Architecture.docx — løsning, arkitektur, kontrol-/analysemodel, referencedata.",
    "Customs-Analytics_Sikkerhed_og_databehandling.docx — datakategorier, GDPR, trusselsmodel (Udkast).",
    "Customs-Analytics_Hosting_og_drift.docx — nuværende vs. EY-platform, migrationsplan (Udkast).",
    "Customs-Analytics_Regel-sporbarhedsmatrix.xlsx — regel → kilde → modul → test (genereret).",
    "Customs-Analytics_Valideringsrapport.md — auto-genereret fra valideringssuiten.",
    "README.md + CHANGELOG.md — pakke-indeks + katalogversioner.",
  ]),
  H1("6. Ærlig modenhedsvurdering"),
  P("Kerne-funktionaliteten (parser, analyselag, told-/tariferingsmotor på rigtige TARIC-/eVita-data, klassifikation) er på plads og dækket af tests. Det nye i denne runde er governance-rammen: versioneret regelkatalog, sporbarhedsmatrix og en uafhængig valideringssuite, der beviser at hver implementeret kontrol fyrer på sit defekt-scenarie. Det resterende er primært ekstern/governance-arbejde (central auth, EU-residency, hosting, jura, pen-test, stress-test) — listet ovenfor med ejer og næste skridt."),
]);

// ---- 2) Solution Architecture -------------------------------------------
const arch = makeDoc([
  ...titleBlock("Løsnings- og arkitekturbeskrivelse"),
  H1("1. Formål og afgrænsning"),
  P("Customs Analytics analyserer danske importangivelser og giver told-/importanalyse plus told-faglige kontroller. Det er et ANALYSE- og KONTROLVÆRKTØJ, ikke et toldangivelsessystem: det indsender ikke angivelser og ændrer aldrig den uploadede angivelse — det analyserer og rapporterer. Oprindelsesvurdering (om en vare opfylder oprindelsesreglerne) ligger bevidst uden for scope; det er klarererens/leverandørens ansvar."),
  H1("2. Teknologistack"),
  bullets([
    "Python 3.13, Flask (tyndt web-lag), gunicorn (gthread, 2 workers, --preload).",
    "lxml (iterparse, XXE slået fra) til DMS-XML; openpyxl til Excel; PyMuPDF til legacy SAD-PDF.",
    "ECharts (frontend) til dashboards. Ingen tunge ML-afhængigheder — fuzzy-match er token-Jaccard.",
    "SQLite på persistent volume til auth/audit. Referencedata (TARIC/eVita) som CSV/JSON i repoet.",
  ]),
  H1("3. Arkitektur"),
  P("Al forretningslogik ligger i den testbare pakke customs/ (schema, parsers, analytics, tariff, duty_checks, classification, sanity), der kan køres uden web-lag og uden netværk. app.py er kun web-laget: ruter, upload-dispatch, JSON-API. Samme referencearkitektur som SAF-T og VIES."),
  H1("4. Dataflow"),
  bullets([
    "1. Bruger uploader en fil (DMS-XML / SAD-PDF / Excel / CSV).",
    "2. app.py dispatcher på filtype → rette parser → kanonisk Declaration.",
    "3. Declaration.to_rows() folder ud til én analyseklar række pr. varepost.",
    "4. Analyselag + told-/klassifikationskontroller kører i hukommelsen.",
    "5. Resultatet returneres som JSON og vises i dashboardet. Inputfilen gemmes ikke.",
  ]),
  H1("5. Kontrol- og analysemodel (5 lag)"),
  P("Kontrollerne er katalogiseret i 5 lag i det versionerede regelkatalog (customs/rules/Customs-Validation-Rules.json). Hver kontrol er forankret i en autoritativ kilde og mappet til modul + test (se sporbarhedsmatrixen)."),
  table(["Lag", "Fokus", "Kontroller"], [
    ["1 · Struktur & format", "Varekode, procedurekode, XML-struktur", "CUS-H01, CUS-C01, CUS-X01 (XSD)"],
    ["2 · Intern konsistens", "Vægt- og værditotaler", "CUS-W01, CUS-W02, CUS-V01 (+ planlagt CUS-V02)"],
    ["3 · Oprindelse & præference-krav", "Oprindelse, præference-fuldstændighed", "CUS-O01, CUS-P01"],
    ["4 · Tarifering & told", "FTA-mulighed, ugyldig præference, EDR", "CUS-P02, CUS-P03, CUS-E01 (+ planlagt CUS-AD01, CUS-E02)"],
    ["5 · Klassifikation", "Konsistens i HS-kodning", "CUS-K01 (eksakt), CUS-K02 (fuzzy)"],
  ], [30, 36, 34]),
  H1("6. Told- og tariferingsmotor"),
  P("customs/tariff.py slår op HS × oprindelse × dato → MFN-sats / præferencesats / aftale. Motoren er DATO-BEVIDST (temporal): en nyere frihandelsaftale lægges ikke ned over en ældre transaktion; gruppemedlemskab (fx GSP-graduering) opløses på importdatoen. Measures arver fra forælderkoden (kode-arv 10→8→6→4→2 cifre). Toldunioner (measureType 106) er medtaget; præferencetoldkontingenter (143/146/147) markeres som kvote."),
  H1("7. Referencedata og provenance"),
  table(["Kilde", "Indhold", "Mekanisme"], [
    ["Toldstyrelsen — skat/dms-public", "H1/I1-XSD'er, kodelister, datamodel", "Vendret i reference/ med kilde-commit"],
    ["TARIC eVita-toldtarif (Skattestyrelsen)", "MFN-satser + danske varebeskrivelser", "toldtarif_ext.zip → reference/tariff/mfn_rates.csv"],
    ["TARIC Trader Export Total", "Præferencesatser pr. HS×område (temporal)", "→ preferential_rates.csv + geo_areas.json"],
    ["EU Access2Markets", "FTA-/GSP-/EPA-/toldunions-dækning", "Manuelt krydstjekket (2026-06-17)"],
  ], [34, 36, 30]),
  P("Referencedata holdes friske automatisk: tools/update_tariff.sh + en månedlig GitHub Action, med pytest som selvtjek der fanger format-ændringer (samme mønster som SAF-T's ERST-sync)."),
  H1("8. Kvalitetssikring"),
  bullets([
    "Automatiseret testsuite (tests/), kører uden netværk.",
    "Versioneret regelkatalog (JSON med catalog_version) som maskinlæsbar kilde.",
    "Uafhængig valideringssuite (validation/): plantet defekt pr. implementeret kontrol, bekræfter at netop den rigtige kontrol fyrer; gated i pytest.",
    "Sporbarhedsmatrix genereret fra kataloget (regel → kilde → modul → test).",
  ]),
  H1("9. Ændringsstyring"),
  P("Ny/ændret kontrol → opdatér regelkataloget, bump catalog_version, opdatér valideringssuite + matrix + CHANGELOG. Kataloget og suiten er sporbarheds- og CI-porten."),
  H1("10. Hosting"),
  P("Deployes p.t. på Railway (customs.balai.dk). Værktøjet er platform-agnostisk (WSGI) og klar til flytning til EY-platform. Detaljer i Hosting- og driftsdokumentet."),
  H1("11. Begrænsninger"),
  bullets([
    "Anti-dumping, suspensioner, kvoter og mængdetold er ikke fuldt modelleret → EDR-tjek (CUS-E01) er bevidst tolerant (gul, ikke rød) indtil fuld TARIC-sync.",
    "Oprindelsesvurdering er uden for scope (leverandørens/klarererens ansvar).",
    "Klassifikations-fuzzy er token-baseret (indikativ) — kræver klassifikationsfaglig vurdering før brug.",
    "XSD-strukturvalidering (CUS-X01) er forberedt men ikke håndhævet i pipelinen endnu.",
  ]),
  H1("12. Åbne punkter for godkendelse"),
  bullets([
    "Central balai_auth-migrering, EU data-residency.",
    "Fuld TARIC-data → stram EDR til RØD; stress-test på rigtige klientdata; ekstern pen-test.",
    "Se Godkendelses-overblikket §4 for ejere og næste skridt.",
  ]),
  new Paragraph({ children: [new PageBreak()] }),
  H1("Appendiks A — Modulinventar"),
  table(["Modul", "Ansvar"], [
    ["customs/schema.py", "Kanonisk datamodel (Declaration, GoodsItem, DutyLine, Party)"],
    ["customs/parsers/", "WCO DMS-XML, legacy SAD-PDF, Excel/CSV → kanonisk model"],
    ["customs/analytics.py", "Imports/Supplier/Sourcing/CPC/Transport-aggregater"],
    ["customs/tariff.py", "Temporal HS×oprindelse-opslag (MFN/præference/aftale)"],
    ["customs/duty_checks.py", "CUS-P02/P03/E01 + FTA Opportunities"],
    ["customs/classification.py", "CUS-K01 (eksakt) + CUS-K02 (fuzzy)"],
    ["customs/sanity.py", "Struktur-/konsistens-kontroller (CUS-W/H/C/V/O/P01)"],
    ["validation/", "Uafhængig valideringssuite + rapportgenerator"],
  ], [34, 66]),
  H1("Appendiks B — Ordliste"),
  table(["Term", "Forklaring"], [
    ["DMS / WCO DMS-XML", "Danmarks toldangivelsessystem; WCO Data Model XML er udvekslingsformatet"],
    ["MFN", "Most Favoured Nation — tredjelandstoldsatsen uden præference"],
    ["EDR", "Effektiv toldsats = told ÷ toldværdi"],
    ["FTA / GSP / EPA", "Frihandelsaftale / præferenceordning for udviklingslande / økonomisk partnerskabsaftale"],
    ["TARIC", "EU's integrerede tarif — satser, præferencer, foranstaltninger"],
    ["DutyRegimeCode", "Præferencekode (14 11 001); 100 = ingen præference"],
  ], [26, 74]),
]);

// ---- 3) Sikkerhed og databehandling (Udkast) ----------------------------
const sec = makeDoc([
  ...titleBlock("Sikkerhed og databehandling (Udkast)"),
  P("UDKAST — skal review'es af jura/databeskyttelse og sikkerhed før formel godkendelse."),
  H1("1. Datakategorier"),
  table(["Kategori", "Eksempler", "Følsomhed"], [
    ["Importdata (forretningsdata)", "Varekoder, toldværdier, mængder, told, procedurekoder", "Forretningsfortroligt"],
    ["Mulige personoplysninger", "Klarerer-/importør-navn, EORI/CVR, adresse hvis i angivelsen", "Personoplysninger (alm.)"],
    ["Brugerkonti", "Brugernavn, hashet password (pbkdf2), rolle", "Personoplysninger (alm.)"],
    ["Revisionslog", "Kun metadata: bruger, filnavn, antal, varighed", "Metadata (ingen angivelsesindhold)"],
  ], [30, 44, 26]),
  H1("2. Dataflow og dataminimering"),
  P("Den uploadede fil analyseres UDELUKKENDE i hukommelsen og gemmes ikke på disk; intet resultat persisteres. Kun auth- og audit-databaserne ligger på det persistente volume. Revisionsloggen indeholder kun metadata — aldrig indholdet af en angivelse. Dette er strammere end et arkivværktøj og minimerer eksponeringen af forretnings-/personoplysninger."),
  H1("3. GDPR og behandlingsgrundlag"),
  P("Udkast: Angivelser kan indeholde personoplysninger (navne, EORI/CVR, adresser). Behandlingsgrundlag, evt. databehandleraftale (DPA) med kunden, og dataplacering (EU) skal fastlægges af jura/DPO. Da intet angivelsesindhold gemmes, er opbevaringsfladen minimal; brugerkonti og audit-metadata er den persisterede personoplysning."),
  H1("4. Adgangskontrol"),
  bullets([
    "Login kræves til al adgang (lokal auth.py: pbkdf2-hashede passwords, timing-sikkert login).",
    "CSRF-beskyttelse på upload; login-rate-limit (SQLite, trådsikkert) mod brute force.",
    "Roller: admin (brugerstyring/invitationer) vs. almindelig bruger.",
    "Sikkerhedsheaders sættes i web-laget; ingen tredjeparts-CDN'er for følsomme stier.",
    "Åbent: migrering til central balai_auth (delt login på *.balai.dk, fælles SECRET_KEY).",
  ]),
  H1("5. Trusselsmodel (udvalgte)"),
  table(["Trussel", "Modforanstaltning"], [
    ["XXE i XML-parsing", "lxml med ekstern entity-opløsning slået fra"],
    ["SQL-injection", "Parameteriserede forespørgsler i auth/audit"],
    ["Brute force på login", "Rate-limit + timing-sikker sammenligning"],
    ["CSRF", "CSRF-token på state-ændrende kald"],
    ["Lækage af angivelsesdata", "In-memory only; intet gemmes; audit kun metadata"],
    ["Sessionskapring", "Secure/HttpOnly/SameSite cookies; SECRET_KEY i env"],
  ], [40, 60]),
  H1("6. Underdatabehandlere"),
  table(["Leverandør", "Rolle", "Status"], [
    ["Railway", "Hosting/drift (dev/demo)", "Midlertidig; EU-region skal verificeres"],
    ["DanDomain", "DNS for balai.dk", "Kun DNS, ingen kundedata"],
  ], [28, 40, 32]),
  H1("7. Logning og hændelseshåndtering"),
  P("Append-only revisionslog med kun metadata (bruger, fil, antal, varighed) — aldrig angivelsesindhold. Hændelseshåndtering (alarmering, incident-proces) fastlægges sammen med driftsplatformen ved EY-flytning."),
  H1("8. Åbne punkter"),
  bullets([
    "Jura-/DPO-review af behandlingsgrundlag + DPA + dataplacering (EU).",
    "EU data-residency for auth/audit-volume (Railway-region).",
    "Central balai_auth-integration; ekstern penetrationstest.",
  ]),
]);

// ---- 4) Hosting og drift (Udkast) ---------------------------------------
const hosting = makeDoc([
  ...titleBlock("Hosting og drift (Udkast)"),
  P("UDKAST — den endelige driftsmodel afhænger af EY-platformsbeslutningen."),
  H1("1. Nuværende opsætning"),
  bullets([
    "Platform: Railway, tjeneste 'web' → customs.balai.dk (HTTPS).",
    "Runtime: gunicorn (gthread, 2 workers, --preload deler ~123 MB referencedata via COW).",
    "Persistens: SQLite på et persistent volume mountet på /data (auth.db + audit.db).",
    "Deploy: auto-deploy på main; månedlig GitHub Action holder TARIC-data friske.",
  ]),
  H1("2. Mål: EY-platform"),
  P("Værktøjet er platform-agnostisk (WSGI + SQLite/volumen) og kan flyttes uden ændring i kontrol-logikken. Ved produktionsbrug med klientdata flyttes det til EY's godkendte platform; SQLite kan om nødvendigt erstattes af managed PostgreSQL."),
  H1("3. Migrationsplan"),
  bullets([
    "1. Vælg EY-målplatform og region (EU).",
    "2. Provisionér runtime (WSGI) + persistent lager til auth/audit.",
    "3. Overfør miljøvariabler (se §4); sæt fælles SECRET_KEY (central login).",
    "4. Migrér til central balai_auth; verificér adgangsstyring.",
    "5. Verificér referencedata-sync (TARIC) + CI; kør stress-test på rigtige data.",
    "6. Skift DNS; afvikl Railway-instansen.",
  ]),
  H1("4. Miljø- og konfig-inventar"),
  table(["Variabel", "Formål"], [
    ["SECRET_KEY", "Session-signering (skal være sat; deles på tværs ved central login)"],
    ["AUTH_DB_PATH", "Sti til auth-db på persistent volume (/data/auth.db)"],
    ["AUDIT_DB_PATH", "Sti til audit-db på persistent volume (/data/audit.db)"],
    ["PORT", "Bind-port (sættes af platformen)"],
  ], [28, 72]),
  P("Bemærk: stierne strippes for blanktegn i koden, så en utilsigtet mellemrums-fejl i en variabel ikke lander databasen på efemer disk (driftsfund, lukket 2026-06-18)."),
  H1("5. Backup og BCDR"),
  P("Udkast: Backup af auth/audit-volumet og gendannelsesprocedure fastlægges på målplatformen. Da intet angivelsesindhold gemmes, er gendannelsesbehovet begrænset til brugerkonti og audit-metadata. Referencedata kan altid regenereres fra de officielle kilder."),
  H1("6. Roller og ansvar"),
  table(["Rolle", "Ansvar"], [
    ["Udvikling (Bal AI)", "Kode, tests, regelkatalog, referencedata-sync, deploy"],
    ["Drift / platform", "Hosting, volumen, region/EU-residency, backup"],
    ["EY tool-governance", "Godkendelse, platformsvalg, support-model"],
    ["Jura / DPO", "Behandlingsgrundlag, DPA, dataplacering"],
  ], [30, 70]),
  H1("7. Support og vedligehold"),
  P("Udkast: SLA, support-bemanding og vedligeholdelsesvinduer er en organisatorisk beslutning ved EY-flytning. Vedligehold af tarif-motoren er automatiseret (månedlig sync med selvtjek)."),
]);

// ---- skriv filerne -------------------------------------------------------
const FILES = [
  ["Customs-Analytics_Godkendelses-overblik.docx", overblik],
  ["Customs-Analytics_Solution_Architecture.docx", arch],
  ["Customs-Analytics_Sikkerhed_og_databehandling.docx", sec],
  ["Customs-Analytics_Hosting_og_drift.docx", hosting],
];

(async () => {
  fs.mkdirSync(DOCS, { recursive: true });
  for (const [name, doc] of FILES) {
    const buf = await Packer.toBuffer(doc);
    fs.writeFileSync(path.join(DOCS, name), buf);
    console.log("Skrev docs/" + name);
  }
})();
