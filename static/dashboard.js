/* Customs Analytics — dashboard-rendering med ECharts.
   Henter den fulde kerne-rapport fra API'et og tegner KPI'er, grafer og tabeller
   i Bal AI-paletten. Faner skifter mellem analysesiderne. */

const NAVY = "#1B365D";
const NAVY_LIGHT = "#2E5C8A";
const GREEN = "#16A34A";
const MUTED = "#4B5563";
const GRID = "#E5E7EB";
const CPC_COLORS = [NAVY, NAVY_LIGHT, GREEN, "#7C9CBF", "#B45309", "#9CA3AF"];

const charts = {};

// ISO 3166-1 alpha-2 -> navn i verdens-GeoJSON'en (keyed by 'name').
const ISO2_NAME = {
    CN: "China", VN: "Vietnam", IN: "India", PK: "Pakistan", TR: "Turkey",
    UA: "Ukraine", MY: "Malaysia", TW: "Taiwan", ID: "Indonesia", BD: "Bangladesh",
    IL: "Israel", EG: "Egypt", MA: "Morocco", NO: "Norway", GB: "United Kingdom",
    DK: "Denmark", DE: "Germany", FR: "France", IT: "Italy", ES: "Spain",
    NL: "Netherlands", BE: "Belgium", PL: "Poland", SE: "Sweden", FI: "Finland",
    US: "United States", CA: "Canada", MX: "Mexico", BR: "Brazil", JP: "Japan",
    KR: "Korea", TH: "Thailand", KH: "Cambodia", LK: "Sri Lanka", RU: "Russia",
    CH: "Switzerland", AT: "Austria", PT: "Portugal", GR: "Greece", CZ: "Czech Rep.",
    RO: "Romania", HU: "Hungary", BG: "Bulgaria", HR: "Croatia", AE: "United Arab Emirates",
    TN: "Tunisia", ZA: "South Africa", AU: "Australia", NZ: "New Zealand", HK: "Hong Kong",
};

// Hent og registrér verdenskortet én gang (offline, vendret i static/).
const mapReady = fetch("/static/world.json")
    .then((r) => r.json())
    .then((geo) => echarts.registerMap("world", geo))
    .catch((e) => console.error("Kunne ikke indlæse verdenskort:", e));

const kr = (v) => {
    if (v >= 1e9) return (v / 1e9).toFixed(2) + " mia.";
    if (v >= 1e6) return (v / 1e6).toFixed(1) + " mio.";
    if (v >= 1e3) return (v / 1e3).toFixed(0) + "k";
    return Math.round(v || 0).toString();
};
const krFull = (v) => Math.round(v || 0).toLocaleString("da-DK") + " kr.";
const kg = (v) => Math.round(v || 0).toLocaleString("da-DK") + " kg";
const num = (v) => (v || 0).toLocaleString("da-DK");
const pct = (v) => (v == null ? "–" : (v * 100).toFixed(2) + " %");

let lastData = null;

function chart(id) {
    if (!charts[id]) charts[id] = echarts.init(document.getElementById(id));
    return charts[id];
}

const baseSplit = { lineStyle: { color: GRID, type: "dashed" } };

function renderKpis(k) {
    const cards = [
        { value: kr(k.customs_value) + " kr.", label: "Toldværdi" },
        { value: kr(k.import_duty) + " kr.", label: "Importtold" },
        { value: num(k.shipments), label: "Forsendelser" },
        { value: pct(k.effective_duty_rate), label: "Effektiv toldsats" },
    ];
    document.getElementById("kpis").innerHTML = cards
        .map((c) => `<div class="kpi"><div class="kpi-value">${c.value}</div><div class="kpi-label">${c.label}</div></div>`)
        .join("");
}

function renderTime(series) {
    chart("chart-time").setOption({
        grid: { left: 56, right: 24, top: 30, bottom: 30 },
        legend: { data: ["Toldværdi", "Told"], textStyle: { color: MUTED }, top: 0 },
        tooltip: { trigger: "axis", valueFormatter: krFull },
        xAxis: { type: "category", data: series.map((p) => p.month), axisLabel: { color: MUTED }, axisLine: { lineStyle: { color: GRID } } },
        yAxis: { type: "value", axisLabel: { color: MUTED, formatter: kr }, splitLine: baseSplit },
        series: [
            { name: "Toldværdi", type: "line", smooth: true, areaStyle: { opacity: 0.12 }, itemStyle: { color: NAVY }, data: series.map((p) => p.customs_value) },
            { name: "Told", type: "line", smooth: true, itemStyle: { color: GREEN }, data: series.map((p) => p.import_duty) },
        ],
    });
}

function barH(id, rows, labelKey, valueKey, color, fmt = kr, full = krFull) {
    const ordered = [...rows].reverse();
    chart(id).setOption({
        grid: { left: 8, right: 70, top: 12, bottom: 24, containLabel: true },
        tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: full },
        xAxis: { type: "value", axisLabel: { color: MUTED, formatter: fmt }, splitLine: baseSplit },
        yAxis: { type: "category", data: ordered.map((r) => r[labelKey]), axisLabel: { color: MUTED }, axisLine: { lineStyle: { color: GRID } } },
        series: [{
            type: "bar", itemStyle: { color, borderRadius: [0, 3, 3, 0] },
            data: ordered.map((r) => r[valueKey]),
            label: { show: true, position: "right", color: MUTED, formatter: (p) => fmt(p.value) },
        }],
    });
}

function table(id, columns, rows) {
    const head = columns.map((c) => `<th>${c.label}</th>`).join("");
    const body = rows.map((r) =>
        "<tr>" + columns.map((c) => {
            const v = c.value(r);
            const cls = c.num === false ? "" : ' class="num"';
            return `<td${cls}>${v}</td>`;
        }).join("") + "</tr>"
    ).join("");
    document.getElementById(id).innerHTML =
        `<table class="data"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

function renderMap(byOrigin) {
    const data = byOrigin.map((r) => ({
        name: ISO2_NAME[r.country] || r.country,
        value: Math.round(r.customs_value),
        code: r.country,
    }));
    const max = Math.max(1, ...data.map((d) => d.value));
    mapReady.then(() => {
        chart("chart-map").setOption({
            tooltip: {
                trigger: "item",
                formatter: (p) => (p.value ? `${p.name}<br>${krFull(p.value)}` : p.name),
            },
            visualMap: {
                left: 16, bottom: 20, min: 0, max,
                text: ["Høj", "Lav"], calculable: true,
                inRange: { color: ["#E5EAF1", "#7C9CBF", NAVY] },
                textStyle: { color: MUTED }, formatter: (v) => kr(v),
            },
            series: [{
                type: "map", map: "world", roam: false,
                emphasis: { label: { show: false }, itemStyle: { areaColor: GREEN } },
                itemStyle: { borderColor: "#FFFFFF", borderWidth: 0.5, areaColor: "#F0F2F5" },
                data,
            }],
        });
        if (charts["chart-map"]) charts["chart-map"].resize();
    });
}

function renderOverview(s) {
    renderKpis(s.kpis);
    renderMap(s.by_origin);
    renderTime(s.time_series);
    barH("chart-origin", s.by_origin, "country", "customs_value", NAVY);
    barH("chart-hs", s.by_hs_code, "hs_code", "customs_value", NAVY_LIGHT);
    barH("chart-desc", s.by_description, "description", "customs_value", NAVY_LIGHT);
}

function renderSuppliers(suppliers) {
    barH("chart-suppliers", suppliers.slice(0, 12), "consignor", "customs_value", NAVY);
    table("table-suppliers", [
        { label: "Leverandør", value: (r) => r.consignor, num: false },
        { label: "Lande", value: (r) => num(r.countries_count) },
        { label: "Forsend.", value: (r) => num(r.shipments) },
        { label: "Toldværdi", value: (r) => kr(r.customs_value) },
        { label: "Told", value: (r) => kr(r.import_duty) },
        { label: "EDR", value: (r) => pct(r.effective_duty_rate) },
    ], suppliers.slice(0, 20));
}

function renderSourcing(src) {
    const cols = (labelHead, key) => [
        { label: labelHead, value: (r) => r[key], num: false },
        { label: "Toldværdi", value: (r) => kr(r.customs_value) },
        { label: "Told", value: (r) => kr(r.import_duty) },
        { label: "EDR", value: (r) => pct(r.effective_duty_rate) },
        { label: "Forsend.", value: (r) => num(r.shipments) },
    ];
    table("table-sourcing-country", cols("Oprindelsesland", "country"), src.by_country);
    table("table-sourcing-hs", cols("HS-kode", "hs_code"), src.by_hs_code);
}

function renderCpc(cpc) {
    chart("chart-cpc").setOption({
        tooltip: { trigger: "item", formatter: (p) => `${p.name}<br>${krFull(p.value)} (${p.percent}%)` },
        legend: { bottom: 0, textStyle: { color: MUTED } },
        series: [{
            type: "pie", radius: ["42%", "68%"], center: ["50%", "44%"],
            data: cpc.map((r, i) => ({ name: r.cpc, value: r.customs_value, itemStyle: { color: CPC_COLORS[i % CPC_COLORS.length] } })),
            label: { color: MUTED, formatter: (p) => `${p.name}\n${(p.percent).toFixed(1)}%` },
        }],
    });
    table("table-cpc", [
        { label: "CPC", value: (r) => r.cpc, num: false },
        { label: "Andel", value: (r) => pct(r.share) },
        { label: "Toldværdi", value: (r) => kr(r.customs_value) },
        { label: "Told", value: (r) => kr(r.import_duty) },
        { label: "EDR", value: (r) => pct(r.effective_duty_rate) },
    ], cpc);
}

function renderTransport(t) {
    barH("chart-border", t.by_border, "mot_label", "customs_value", NAVY);
    barH("chart-inland", t.by_inland, "mot_label", "customs_value", NAVY_LIGHT);
    barH("chart-weight", t.by_border, "mot_label", "net_mass", GREEN, kg, kg);
}

function renderFta(fta) {
    const cards = [
        { value: kr(fta.total_potential_saving) + " kr.", label: "Samlet mulig FTA-besparelse" },
        { value: num(fta.invalid_preference_claims), label: "Ugyldige præference-krav (toldrisiko)" },
        { value: num(fta.by_country.length), label: "Lande med uudnyttet præference" },
        { value: num(fta.lines.length), label: "Vareposter med mulighed" },
    ];
    document.getElementById("fta-kpis").innerHTML = cards
        .map((c) => `<div class="kpi"><div class="kpi-value">${c.value}</div><div class="kpi-label">${c.label}</div></div>`)
        .join("");
    barH("chart-fta-country", fta.by_country.slice(0, 10), "country", "saving", GREEN);
    barH("chart-fta-hs", fta.by_hs_code.slice(0, 10), "hs_code", "saving", GREEN);
    table("table-fta", [
        { label: "HS-kode", value: (r) => r.hs_code, num: false },
        { label: "Oprindelse", value: (r) => r.origin, num: false },
        { label: "Aftale", value: (r) => (r.arrangement || "–") + (r.is_quota ? " ⚠ kvote" : ""), num: false },
        { label: "Toldværdi", value: (r) => kr(r.customs_value) },
        { label: "MFN", value: (r) => pct(r.mfn_rate) },
        { label: "Præf.", value: (r) => pct(r.preferential_rate) },
        { label: "Mulig besparelse", value: (r) => krFull(r.potential_saving) },
    ], fta.lines.slice(0, 25));
}

function codesList(codes) {
    return codes.map((c) => `${c.hs_code} (${pct(c.mfn_rate)})`).join(", ");
}

function renderClassification(cls) {
    const cards = [
        { value: num(cls.exact.length), label: "Oplagte inkonsistenser" },
        { value: kr(cls.exact_saving) + " kr.", label: "Indikativ besparelse (oplagte)" },
        { value: num(cls.fuzzy.length), label: "Fuzzy-klynger m. flere koder" },
        { value: kr(cls.fuzzy_saving) + " kr.", label: "Indikativ besparelse (fuzzy)" },
    ];
    document.getElementById("cls-kpis").innerHTML = cards
        .map((c) => `<div class="kpi"><div class="kpi-value">${c.value}</div><div class="kpi-label">${c.label}</div></div>`)
        .join("");
    table("table-cls-exact", [
        { label: "Vare", value: (r) => r.product, num: false },
        { label: "Antal koder", value: (r) => num(r.distinct_codes) },
        { label: "HS-koder (MFN)", value: (r) => codesList(r.codes), num: false },
        { label: "Toldværdi", value: (r) => kr(r.total_value) },
        { label: "Indikativ besparelse", value: (r) => krFull(r.potential_saving) },
    ], cls.exact.slice(0, 25));
    table("table-cls-fuzzy", [
        { label: "Vare (repr.)", value: (r) => r.product, num: false },
        { label: "Varianter", value: (r) => num(r.variants.length) },
        { label: "HS-koder (MFN)", value: (r) => codesList(r.codes), num: false },
        { label: "Toldværdi", value: (r) => kr(r.total_value) },
        { label: "Indikativ besparelse", value: (r) => krFull(r.potential_saving) },
    ], cls.fuzzy.slice(0, 25));
}

function showReport(show) {
    document.getElementById("empty-state").hidden = show;
    document.getElementById("dataset-note").hidden = !show;
    document.getElementById("tabs").hidden = !show;
    document.querySelectorAll(".panel").forEach((p) => { p.style.display = show ? "" : "none"; });
}

function render(data) {
    lastData = data;
    showReport(true);
    document.getElementById("dataset-note").innerHTML =
        `Viser <strong>${data.dataset}</strong> · ${num(data.rows)} linjer.`;

    renderOverview(data.summary);
    renderSuppliers(data.suppliers);
    renderSourcing(data.sourcing);
    renderCpc(data.cpc);
    renderTransport(data.transport);
    renderFta(data.fta);
    renderClassification(data.classification);
    // Resize charts i den aktive fane (ECharts måler 0 i skjulte paneler).
    requestAnimationFrame(() => resizeActive());
}

function resizeActive() {
    const active = document.querySelector(".panel.active");
    if (!active) return;
    active.querySelectorAll(".chart").forEach((el) => {
        const c = charts[el.id];
        if (c) c.resize();
    });
}

document.getElementById("tabs").addEventListener("click", (e) => {
    const btn = e.target.closest(".tab");
    if (!btn) return;
    const tab = btn.dataset.tab;
    document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t === btn));
    document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("active", p.dataset.panel === tab));
    resizeActive();
});

async function uploadFile(file) {
    const btn = document.getElementById("empty-upload-btn");
    const err = document.getElementById("upload-error");
    err.hidden = true;
    if (btn) { btn.textContent = "Analyserer …"; btn.disabled = true; }
    try {
        const fd = new FormData();
        fd.append("file", file);
        const csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";
        const res = await fetch("/api/upload", { method: "POST", body: fd, headers: { "X-CSRF-Token": csrf } });
        const data = await res.json();
        if (!res.ok) { err.textContent = data.error || "Kunne ikke læse filen."; err.hidden = false; return; }
        render(data);
    } catch (e) {
        err.textContent = "Netværksfejl — prøv igen."; err.hidden = false;
    } finally {
        if (btn) { btn.textContent = "Upload importdata"; btn.disabled = false; }
    }
}

const fileInput = document.getElementById("file-input");
fileInput.addEventListener("change", (e) => { if (e.target.files[0]) uploadFile(e.target.files[0]); });
document.getElementById("empty-upload-btn").addEventListener("click", () => fileInput.click());

showReport(false);  // start rent — ingen demo-data, klar til import
window.addEventListener("resize", () => Object.values(charts).forEach((c) => c.resize()));
