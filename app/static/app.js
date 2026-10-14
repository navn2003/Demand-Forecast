"use strict";

const PERIODS = [
  { value: "day", label: "Day", hint: "One full day in IST." },
  { value: "week", label: "Week", hint: "Monday–Sunday · dates in IST." },
  { value: "month", label: "Month", hint: "One calendar month · dates in IST." },
  { value: "custom", label: "Custom", hint: "Up to three calendar months; both dates included." },
];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const MIN_WINDOW = 8; // smallest zoom window: 8 blocks = 2 hours

const $ = (id) => document.getElementById(id);
const state = { period: "day", meta: null, labels: {}, chart: null, rep: null, lo: 0, hi: 0 };

/* ---------- theme ---------- */
const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const colors = () => ({
  actual: cssVar("--c-actual"), DA1: cssVar("--c-da1"), DA2: cssVar("--c-da2"), ID: cssVar("--c-id"),
  ink: cssVar("--ink-2"), muted: cssVar("--muted"), grid: cssVar("--grid"), surface: cssVar("--surface"),
});
function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  document.querySelectorAll("[data-theme-set]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.themeSet === theme)));
  try { localStorage.setItem("df-theme", theme); } catch (e) { /* storage unavailable: theme still applies for this visit */ }
  if (state.rep) drawChart();
}

/* ---------- date helpers (local dates, no time zone shifts) ---------- */
const pad = (n) => String(n).padStart(2, "0");
const iso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const parseISO = (s) => { const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d); };
const addDays = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };
function addMonths(d, n) {
  const x = new Date(d.getFullYear(), d.getMonth() + n, 1);
  const last = new Date(x.getFullYear(), x.getMonth() + 1, 0).getDate();
  x.setDate(Math.min(d.getDate(), last));
  return x;
}
function isoWeekValue(d) {
  const t = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  t.setDate(t.getDate() - ((t.getDay() + 6) % 7) + 3); // Thursday of this ISO week
  const firstThu = new Date(t.getFullYear(), 0, 4);
  const week = 1 + Math.round(((t - firstThu) / 864e5 - 3 + ((firstThu.getDay() + 6) % 7)) / 7);
  return `${t.getFullYear()}-W${pad(week)}`;
}
function mondayOfIsoWeek(value) {
  const [y, w] = value.split("-W").map(Number);
  const jan4 = new Date(y, 0, 4);
  return addDays(addDays(jan4, -((jan4.getDay() + 6) % 7)), (w - 1) * 7);
}
const supports = (type) => { const i = document.createElement("input"); i.setAttribute("type", type); return i.type === type; };
const WEEK_OK = supports("week"), MONTH_OK = supports("month");
// "2025-10-01 14:15" -> parts
const tsDay = (ts) => `${ts.slice(8, 10)} ${MONTHS[Number(ts.slice(5, 7)) - 1]}`;
const tsLong = (ts) => `${tsDay(ts)} ${ts.slice(0, 4)}, ${ts.slice(11, 16)}`;

/* ---------- period ---------- */
function setPeriod(value) {
  state.period = value;
  const p = PERIODS.find((x) => x.value === value);
  $("periodBtn").textContent = p.label;
  $("periodHint").textContent = p.hint + (value === "week" && !WEEK_OK ? " Pick any day; its week is used." : "");
  $("dayInput").hidden = value !== "day";
  $("weekInput").hidden = value !== "week";
  $("monthInput").hidden = value !== "month";
  $("customInputs").hidden = value !== "custom";
  document.querySelector(".field.period").classList.toggle("is-custom", value === "custom");
  renderPeriodList("");
}

function resolvePeriod() {
  const v = state.period;
  if (v === "day") {
    if (!$("dayInput").value) throw new Error("Choose a day.");
    return { start: $("dayInput").value, end: $("dayInput").value };
  }
  if (v === "week") {
    const raw = $("weekInput").value;
    if (!raw) throw new Error("Choose a week.");
    const mon = WEEK_OK ? mondayOfIsoWeek(raw) : addDays(parseISO(raw), -((parseISO(raw).getDay() + 6) % 7));
    return { start: iso(mon), end: iso(addDays(mon, 6)) };
  }
  if (v === "month") {
    const raw = $("monthInput").value;
    if (!raw) throw new Error("Choose a month.");
    const [y, m] = raw.split("-").map(Number);
    return { start: iso(new Date(y, m - 1, 1)), end: iso(new Date(y, m, 0)) };
  }
  const a = $("fromInput").value, b = $("toInput").value;
  if (!a || !b) throw new Error("Choose both From and To dates.");
  if (b < a) throw new Error("The To date is before the From date.");
  const maxEnd = addDays(addMonths(parseISO(a), 3), -1);
  if (parseISO(b) > maxEnd) throw new Error(`Choose up to three calendar months (latest To date: ${iso(maxEnd)}).`);
  return { start: a, end: b };
}

/* ---------- searchable period dropdown ---------- */
function renderPeriodList(q) {
  const list = $("periodList");
  list.innerHTML = "";
  PERIODS.filter((p) => p.label.toLowerCase().includes(q.toLowerCase())).forEach((p, i) => {
    const li = document.createElement("li");
    li.role = "option";
    li.textContent = p.label;
    li.dataset.value = p.value;
    li.setAttribute("aria-selected", String(p.value === state.period));
    if (i === 0) li.classList.add("hl");
    li.addEventListener("click", () => { setPeriod(p.value); closeCombo(); });
    list.appendChild(li);
  });
}
function openCombo() {
  $("periodPanel").hidden = false;
  $("periodBtn").setAttribute("aria-expanded", "true");
  $("periodSearch").value = "";
  renderPeriodList("");
  $("periodSearch").focus();
}
function closeCombo() { $("periodPanel").hidden = true; $("periodBtn").setAttribute("aria-expanded", "false"); }

/* ---------- formatting ---------- */
const fmt = (v, d = 2) => (v === null || v === undefined || Number.isNaN(v) ? "–" : Number(v).toLocaleString("en-IN", { minimumFractionDigits: d, maximumFractionDigits: d }));
const fmtTable = (v) => (v === null || v === undefined ? "–" : Number(v).toLocaleString("en-IN", { maximumFractionDigits: 2 }));
function setStatus(msg, error = false) { $("status").textContent = msg; $("status").classList.toggle("error", error); }

/* ---------- API ---------- */
async function getJSON(url) {
  const r = await fetch(url);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.detail || `Request failed (${r.status})`);
  return body;
}
function query() {
  const { start, end } = resolvePeriod();
  return new URLSearchParams({ discom: $("discom").value, revision: $("revision").value, start, end });
}

function updateDiscomHint() {
  const d = (state.meta?.discoms || []).find((x) => x.value === $("discom").value);
  $("discomHint").textContent = d && d.members ? `Total = ${d.members.join(" + ")}` : "";
}

async function loadMeta() {
  const m = await getJSON("/api/meta");
  state.meta = m;
  $("discom").innerHTML = m.discoms.map((d) => `<option value="${d.value}">${d.label}</option>`).join("");
  $("revision").innerHTML = m.revisions.map((r) => `<option value="${r.value}">${r.label}</option>`).join("");
  m.revisions.forEach((r) => (state.labels[r.value] = r.label));
  updateDiscomHint();
  const a = m.available;
  const f = (s) => (s ? parseISO(s).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }) : "–");
  $("avail").innerHTML = `Actuals: ${f(a.actual_from)} – ${f(a.actual_to)}<br>Forecasts: ${f(a.forecast_from)} – ${f(a.forecast_to)}`;
  const def = parseISO(a.forecast_to || a.actual_to || iso(new Date()));
  $("dayInput").value = iso(def);
  $("weekInput").value = WEEK_OK ? isoWeekValue(def) : iso(def);
  $("monthInput").value = MONTH_OK ? iso(def).slice(0, 7) : iso(new Date(def.getFullYear(), def.getMonth(), 1));
  $("fromInput").value = iso(new Date(def.getFullYear(), def.getMonth(), 1));
  $("toInput").value = iso(def);
}

async function loadReport() {
  let q;
  try { q = query(); } catch (e) { setStatus(e.message, true); return; }
  $("loadBtn").disabled = true;
  setStatus("Loading…");
  try {
    render(await getJSON(`/api/report?${q}`));
  } catch (e) {
    setStatus(e.message, true);
  } finally {
    $("loadBtn").disabled = false;
  }
}

function downloadCsv() {
  // Excel workbook: one sheet per DISCOM + ODISHA_SUM, all three revisions, for the selected period
  try {
    const { start, end } = resolvePeriod();
    window.location.href = `/api/report.xlsx?${new URLSearchParams({ start, end })}`;
  } catch (e) { setStatus(e.message, true); }
}

/* ---------- render ---------- */
function render(rep) {
  state.rep = rep;
  const scope = rep.discom === "ALL" ? "All DISCOMs · Total" : rep.discom;
  const period = rep.start === rep.end ? rep.start : `${rep.start} to ${rep.end}`;
  const anyForecast = rep.summary.some((s) => s.matched_blocks > 0);
  setStatus(anyForecast
    ? `${scope} · ${period} · ${rep.actual_blocks} of ${rep.blocks_in_period} intervals have actuals.`
    : `No matched forecast and actual intervals for ${scope} in ${period}. Actuals found: ${rep.actual_blocks}.`, !anyForecast);

  const single = rep.revision !== "ALL";
  const c = colors();
  $("cards").hidden = !single;
  $("revCard").hidden = single;
  if (single) {
    const s = rep.summary[0];
    $("kpiActual").textContent = fmt(s.avg_actual);
    $("kpiForecast").textContent = fmt(s.avg_forecast);
    $("kpiMape").textContent = s.mape === null ? "–" : `${fmt(s.mape)}%`;
    $("kpiMatched").textContent = `${s.matched_blocks} matched intervals · ${s.label}`;
  } else {
    $("revTitle").textContent = `Accuracy by revision · ${scope}`;
    $("revBody").innerHTML = rep.summary.map((s) => `
      <tr><td><span class="swatch" style="background:${c[s.revision]}"></span>${s.label}</td>
      <td class="num">${fmt(s.avg_actual)}</td><td class="num">${fmt(s.avg_forecast)}</td>
      <td class="num">${s.mape === null ? "–" : fmt(s.mape)}</td><td class="num">${s.matched_blocks}</td></tr>`).join("");
  }

  $("chartCard").hidden = false;
  $("chartTitle").textContent = `Forecast versus Actual · ${scope}`;
  $("chartNote").textContent = rep.discom === "ALL" && rep.total_of
    ? `Total = ${rep.total_of.join(" + ")} at each block; blocks where any DISCOM is missing are left as gaps.`
    : "Missing actual or forecast blocks are shown as gaps.";
  const n = rep.series.length;
  ["rangeFrom", "rangeTo"].forEach((id) => { $(id).max = String(n - 1); });
  state.lo = 0;
  state.hi = n - 1;
  drawChart();

  $("tableCard").hidden = false;
  $("tableNote").textContent = `${n} intervals · scroll to review all intervals`;
  const revs = rep.revisions;
  const multi = revs.length > 1;
  const head = revs.map((r) => multi ? `<th>${r} forecast</th><th>${r} MAPE</th>` : "<th>Forecast</th><th>MAPE</th>").join("");
  $("dataHead").innerHTML = `<tr><th>Timestamp</th><th>Actual</th>${head}</tr>`;
  $("dataBody").innerHTML = rep.series.map((row) => {
    const a = row.actual;
    const cells = revs.map((r) => {
      const f = row[r];
      const ape = a && f !== null ? (Math.abs(a - f) / a) * 100 : null;
      const cls = ape === null ? "" : ape <= 3 ? "good" : ape <= 10 ? "warn" : "bad";
      return `<td>${fmtTable(f)}</td><td class="ape ${cls}">${ape === null ? "–" : ape.toFixed(2) + "%"}</td>`;
    }).join("");
    return `<tr><td>${tsLong(row.ts)}</td><td>${fmtTable(a)}</td>${cells}</tr>`;
  }).join("");
}

function drawChart() {
  const rep = state.rep;
  const c = colors();
  const datasets = [{
    label: "Actual", data: rep.series.map((r) => r.actual), borderColor: c.actual, backgroundColor: c.actual,
    borderWidth: 2, pointRadius: 0, pointHoverRadius: 4, spanGaps: false, tension: 0.15,
  }];
  const single = rep.revisions.length === 1;
  rep.revisions.forEach((r) => {
    const col = single ? c.DA1 : c[r]; // one revision: red forecast line; all revisions: DA1 red, DA2 green, ID violet
    datasets.push({
      label: `${state.labels[r] || r} forecast`, data: rep.series.map((x) => x[r]), borderColor: col, backgroundColor: col,
      borderWidth: 2, pointRadius: 0, pointHoverRadius: 4, spanGaps: false, tension: 0.15,
    });
  });
  if (state.chart) state.chart.destroy();
  state.chart = new Chart($("chart"), {
    type: "line",
    data: { labels: rep.series.map((r) => r.ts), datasets },
    options: {
      animation: false, maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { position: "bottom", labels: { usePointStyle: true, pointStyle: "line", color: c.ink, font: { family: "DM Sans", size: 13 }, padding: 16 } },
        tooltip: { callbacks: { title: (items) => tsLong(items[0].label) + " IST", label: (x) => `${x.dataset.label}: ${fmt(x.parsed.y)} MW` } },
      },
      scales: {
        x: {
          ticks: { color: c.muted, maxRotation: 0, autoSkip: true, maxTicksLimit: 8, callback: (v) => tickLabel(rep.series[v].ts) },
          grid: { display: false },
          title: { display: true, text: "Date / time (IST)", color: c.ink },
        },
        y: {
          ticks: { color: c.muted, callback: (v) => Number(v).toLocaleString("en-IN") }, grid: { color: c.grid },
          title: { display: true, text: "MW", color: c.ink },
        },
      },
    },
  });
  applyWindow();
}

function tickLabel(ts) {
  const span = state.hi - state.lo + 1;
  if (span <= 96) return ts.slice(11, 16);                 // a day or less: time only
  if (span <= 96 * 3) return `${tsDay(ts)} ${ts.slice(11, 16)}`;
  return tsDay(ts);
}

/* ---------- zoom + range ---------- */
function applyWindow() {
  const rep = state.rep, ch = state.chart;
  if (!rep || !ch) return;
  const n = rep.series.length;
  state.lo = Math.max(0, Math.min(state.lo, n - 1));
  state.hi = Math.max(state.lo, Math.min(state.hi, n - 1));
  ch.options.scales.x.min = state.lo;
  ch.options.scales.x.max = state.hi;

  // fit the y axis to what is visible
  let lo = Infinity, hi = -Infinity;
  ch.data.datasets.forEach((d) => {
    for (let i = state.lo; i <= state.hi; i++) {
      const v = d.data[i];
      if (v !== null && v !== undefined) { if (v < lo) lo = v; if (v > hi) hi = v; }
    }
  });
  if (Number.isFinite(lo)) {
    const pad = Math.max((hi - lo) * 0.06, 1);
    ch.options.scales.y.min = Math.max(0, Math.floor((lo - pad) / 10) * 10);
    ch.options.scales.y.max = Math.ceil((hi + pad) / 10) * 10;
  } else {
    delete ch.options.scales.y.min;
    delete ch.options.scales.y.max;
  }
  ch.update("none");

  $("rangeFrom").value = String(state.lo);
  $("rangeTo").value = String(state.hi);
  const span = state.hi - state.lo + 1;
  const level = n / span;
  $("zoomLevel").textContent = `${level < 10 ? level.toFixed(1) : Math.round(level)}×`;
  $("zoomOut").disabled = span >= n;
  $("zoomReset").disabled = span >= n;
  $("zoomIn").disabled = span <= MIN_WINDOW;
  const s = rep.series;
  $("rangeLabel").textContent = `${tsLong(s[state.lo].ts)} – ${tsLong(s[state.hi].ts)} IST · ${span} blocks`;
}

function zoom(factor) {
  const n = state.rep.series.length;
  const span = state.hi - state.lo + 1;
  const newSpan = Math.max(MIN_WINDOW, Math.min(n, Math.round(span / factor)));
  const centre = (state.lo + state.hi) / 2;
  let lo = Math.round(centre - (newSpan - 1) / 2);
  lo = Math.max(0, Math.min(lo, n - newSpan));
  state.lo = lo;
  state.hi = lo + newSpan - 1;
  applyWindow();
}

function onRange(which) {
  let a = Number($("rangeFrom").value), b = Number($("rangeTo").value);
  const n = state.rep.series.length;
  const gap = Math.min(MIN_WINDOW - 1, n - 1);
  if (b - a < gap) {
    if (which === "from") a = Math.max(0, b - gap); else b = Math.min(n - 1, a + gap);
  }
  state.lo = a;
  state.hi = b;
  applyWindow();
}

/* ---------- wire up ---------- */
document.addEventListener("DOMContentLoaded", async () => {
  applyTheme(document.documentElement.getAttribute("data-theme") || "light");
  document.querySelectorAll("[data-theme-set]").forEach((b) => b.addEventListener("click", () => applyTheme(b.dataset.themeSet)));

  if (!WEEK_OK) $("weekInput").type = "date";
  if (!MONTH_OK) $("monthInput").type = "date";
  setPeriod("day");
  $("periodBtn").addEventListener("click", () => ($("periodPanel").hidden ? openCombo() : closeCombo()));
  $("periodSearch").addEventListener("input", (e) => renderPeriodList(e.target.value));
  $("periodSearch").addEventListener("keydown", (e) => {
    if (e.key === "Enter") { const first = $("periodList").querySelector("li"); if (first) { setPeriod(first.dataset.value); closeCombo(); } }
    if (e.key === "Escape") closeCombo();
  });
  document.addEventListener("click", (e) => { if (!$("periodCombo").contains(e.target)) closeCombo(); });
  $("discom").addEventListener("change", updateDiscomHint);
  $("loadBtn").addEventListener("click", loadReport);
  $("csvBtn").addEventListener("click", downloadCsv);
  $("zoomIn").addEventListener("click", () => zoom(2));
  $("zoomOut").addEventListener("click", () => zoom(0.5));
  $("zoomReset").addEventListener("click", () => { state.lo = 0; state.hi = state.rep.series.length - 1; applyWindow(); });
  $("rangeFrom").addEventListener("input", () => onRange("from"));
  $("rangeTo").addEventListener("input", () => onRange("to"));

  try {
    await loadMeta();
    await loadReport();
  } catch (e) {
    setStatus(e.message, true);
    $("avail").textContent = "Data not available";
  }
});