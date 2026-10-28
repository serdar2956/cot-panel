"use strict";

// ------------------------------------------------------------------ yardımcılar
const $ = (sel, el = document) => el.querySelector(sel);
const DATA = {};
const charts = {};
const state = { inst: "eurusd", range: "5", lookback: "52", tab: "overview", corr: "c60", statInst: "eurusd" };

const C = {
  blue: "#2459d6", green: "#12805c", red: "#c4372f", orange: "#d97706", purple: "#7a3fc2",
  teal: "#0f8b8d", gray: "#8a94a6", pink: "#c2417a", ink: "#1c2430",
};
const GROUP_COLORS = {
  dealer: C.gray, asset_mgr: C.blue, lev_funds: C.orange, other: C.teal, nonrept: C.pink,
  prod_merc: C.gray, swap: C.teal, managed_money: C.orange,
};

async function load(name) {
  if (DATA[name]) return DATA[name];
  const r = await fetch(`data/${name}.json?v=${Date.now() / 3.6e6 | 0}`);
  if (!r.ok) throw new Error(`${name}: ${r.status}`);
  DATA[name] = await r.json();
  return DATA[name];
}

const nf = (v, d = 0) => v == null || Number.isNaN(v) ? "–" :
  Number(v).toLocaleString("tr-TR", { minimumFractionDigits: d, maximumFractionDigits: d });
const sgn = (v, d = 0) => v == null ? "–" : (v > 0 ? "+" : "") + nf(v, d);
const pn = v => v == null ? "" : v > 0 ? "pos" : v < 0 ? "neg" : "";
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const fmtDate = d => d ? new Date(d + "T00:00:00").toLocaleDateString("tr-TR", { day: "2-digit", month: "short", year: "numeric" }) : "–";

// 0-100 endeks rengi: kırmızı (aşırı short) → nötr → yeşil (aşırı long)
function idxColor(v) {
  if (v == null) return { bg: "#f1f3f6", fg: C.gray };
  if (v >= 80) return { bg: "#cdebdc", fg: "#0b5e43" };
  if (v >= 60) return { bg: "#e6f4ed", fg: "#12805c" };
  if (v > 40) return { bg: "#f1f3f6", fg: "#3b4656" };
  if (v > 20) return { bg: "#fbeceb", fg: "#b03a32" };
  return { bg: "#f6d3cf", fg: "#962b24" };
}
function scoreColor(v) {
  if (v == null) return idxColor(null);
  return idxColor(50 + v / 2);
}
const idxCell = v => { const c = idxColor(v); return `<span class="cell" style="background:${c.bg};color:${c.fg}">${nf(v)}</span>`; };
const scoreCell = v => { const c = scoreColor(v); return `<span class="cell" style="background:${c.bg};color:${c.fg}">${sgn(v)}</span>`; };
const statusDot = s => `<span class="dot ${s === "ok" ? "ok" : s === "red" ? "red" : "yellow"}"></span>`;

function sliceFrom(dates, years) {
  if (years === "all" || !dates.length) return 0;
  const last = new Date(dates[dates.length - 1]);
  last.setFullYear(last.getFullYear() - Number(years));
  const iso = last.toISOString().slice(0, 10);
  const i = dates.findIndex(d => d >= iso);
  return i < 0 ? 0 : i;
}

function chart(id, cfg) {
  if (charts[id]) charts[id].destroy();
  const el = document.getElementById(id);
  if (!el) return;
  charts[id] = new Chart(el, cfg);
}

function lineCfg(labels, datasets, opts = {}) {
  const scales = {
    x: { ticks: { maxTicksLimit: 8, maxRotation: 0, color: C.gray }, grid: { display: false } },
    y: { position: "left", ticks: { color: C.gray }, grid: { color: "#eef1f5" }, ...(opts.y || {}) },
  };
  if (opts.y1) scales.y1 = { position: "right", ticks: { color: C.gray }, grid: { display: false }, ...opts.y1 };
  return {
    type: opts.type || "line",
    data: {
      labels,
      datasets: datasets.map(d => ({
        borderWidth: 1.6, pointRadius: 0, pointHitRadius: 6, tension: 0, spanGaps: true, fill: false, ...d,
      })),
    },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false, normalized: true,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { labels: { boxWidth: 12, boxHeight: 2, color: C.ink, font: { size: 12 } } },
        tooltip: { callbacks: { label: ctx => `${ctx.dataset.label}: ${nf(ctx.parsed.y, opts.decimals ?? 2)}` } },
      },
      scales,
    },
  };
}

const constLine = (labels, v, color, label) => ({
  label, data: labels.map(() => v), borderColor: color, borderDash: [5, 4], borderWidth: 1, pointRadius: 0,
});

function seg(name, options, current) {
  return `<div class="seg" data-seg="${name}">${options.map(([v, l]) =>
    `<button data-v="${v}" class="${v === current ? "active" : ""}">${l}</button>`).join("")}</div>`;
}
const RANGE_OPTS = [["1", "1Y"], ["3", "3Y"], ["5", "5Y"], ["10", "10Y"], ["all", "Tümü"]];

// ------------------------------------------------------------------ Özet
async function renderOverview() {
  const s = await load("summary");
  const el = $("#tab-overview");
  const rows = s.instruments.map(i => `
    <tr class="click" data-inst="${i.key}">
      <td><b>${esc(i.name)}</b>${i.main ? "" : ' <span class="muted small">(ek)</span>'}</td>
      <td>${nf(i.price_now, i.decimals)}<div class="muted small">${i.price_basis === "spot" ? "" : "vadeli proxy"}</div></td>
      <td>${scoreCell(i.score)}<div class="muted small">${esc(i.score_label)}</div></td>
      <td>${idxCell(i.spec_idx)}<div class="muted small">${esc(i.spec_name)}</div></td>
      <td>${idxCell(i.slow_idx)}<div class="muted small">${esc(i.slow_name)}</div></td>
      <td>${idxCell(i.small_idx)}</td>
      <td>${idxCell(i.spec_willco)}</td>
      <td>${idxCell(i.oi_idx)}</td>
      <td class="left small wrap">${esc(i.price_oi ? i.price_oi.text.split(" — ")[0] : "–")}<div class="muted">${esc(i.price_oi ? i.price_oi.text.split(" — ")[1] : "")}</div></td>
      <td class="${pn(-(i.fv_z ?? 0))}">${sgn(i.fv_z, 2)}</td>
      <td>${statusDot(i.validation.cot === "ok" ? "ok" : "yellow")}COT ${statusDot(i.validation.price)}Fiyat</td>
    </tr>`).join("");

  const alerts = s.alerts.length ? s.alerts.map(a => `
      <li><span class="tag ${a.level}">${{ extreme: "Aşırı uç", divergence: "Ayrışma", score: "Skor", validation: "Doğrulama", vol: "Volatilite", sentiment: "Sentiment", corr: "Korelasyon" }[a.level] || a.level}</span>
      <div><b>${esc(a.name)}</b> — ${esc(a.text)}</div></li>`).join("") : '<li class="muted">Şu an aktif uyarı yok.</li>';

  el.innerHTML = `
    <div class="card">
      <h2>Özet Panosu</h2>
      <p class="muted small">COT verisi: ${fmtDate(s.instruments[0]?.date)} (salı) pozisyonları. Endeksler 52 haftalık COT Index (0–100).
      Yeşil = aşırı long (≥${s.thresholds.high}), kırmızı = aşırı short (≤${s.thresholds.low}). Satıra tıklayınca detay açılır.</p>
      <div class="table-wrap"><table>
        <thead><tr><th>Enstrüman</th><th>Fiyat</th><th>Bileşik Skor</th><th>Spekülatif Grup</th><th>Yavaş Para / Ticari</th>
        <th>Küçük Spek.</th><th>Willco (Spek.)</th><th>OI Endeksi</th><th class="left">Fiyat–OI (1 hafta)</th><th>Adil Değer z</th><th>Doğrulama</th></tr></thead>
        <tbody>${rows}</tbody></table></div>
    </div>
    <div class="card"><h2>Uyarılar</h2><ul class="alerts">${alerts}</ul></div>
    <div class="note-box">
      <b>Nasıl okunur?</b> Spekülatif grup (Leveraged Funds / Managed Money) aşırı uçlarda genelde ters sinyal verir.
      Yavaş para (Asset Manager) trendi gösterir. Altın ve gümüşte Üretici/Tüccar hedge yapan ticari gruptur ve spekülatörlerin tersine hareket eder.
      Bileşik skor (−100…+100) tüm bileşenlerin geçmişte işe yarama derecesine göre ağırlıklandırılmış toplamıdır, ayrıntısı Enstrümanlar sekmesinde.
      Adil değer z: fiyatın makro modele göre ne kadar sapmış olduğu (+ pahalı, − ucuz).
    </div>`;
  el.querySelectorAll("tr[data-inst]").forEach(tr => tr.addEventListener("click", () => {
    state.inst = tr.dataset.inst; showTab("instruments");
  }));
}

// ------------------------------------------------------------------ Enstrümanlar
async function renderInstruments() {
  const s = await load("summary");
  const d = await load(`inst_${state.inst}`);
  const el = $("#tab-instruments");
  const S = d.series;
  const lb = state.lookback;
  const st = await load("stats");

  const instBtns = s.instruments.map(i => [i.key, i.name.split(" (")[0]]);
  const groupRows = d.groups.map(g => `
    <tr><td><span class="dot" style="background:${GROUP_COLORS[g.key]}"></span>${esc(g.name)}
      ${g.role === "spec" ? '<span class="muted small">(spekülatif)</span>' : g.role === "slow" ? '<span class="muted small">(yavaş para / ticari)</span>' : ""}</td>
      <td>${nf(g.long)}</td><td>${nf(g.short)}</td><td class="${pn(g.net)}"><b>${sgn(g.net)}</b></td>
      <td class="${pn(g.chg)}">${sgn(g.chg)}</td><td>${nf(g.pct, 1)}%</td>
      <td>${idxCell(g.idx26)}</td><td>${idxCell(g.idx52)}</td><td>${idxCell(g.idx156)}</td><td>${idxCell(g.willco)}</td></tr>`).join("");

  const comps = d.components.map(c => `
    <tr><td class="left">${esc(c.label)}</td><td>${sgn(c.signal, 2)}</td><td>${sgn(c.weight, 3)}</td>
      <td class="${pn(c.contribution)}"><b>${sgn(c.contribution, 1)}</b></td></tr>`).join("");
  const perf = d.score_perf || {};
  const ex = (st.extremes[state.inst] || {}).stats || [];

  const divs = d.divergences.length ? d.divergences.map(x => `<li>${esc(x.text)}</li>`).join("") : "<li class='muted'>Belirgin ayrışma yok.</li>";
  const fv = d.fair_value;

  el.innerHTML = `
    <div class="controls">
      ${seg("inst", instBtns, state.inst)}
    </div>
    <div class="controls">
      <span class="seg-label">Dönem</span>${seg("range", RANGE_OPTS, state.range)}
      <span class="seg-label">COT Index periyodu</span>${seg("lookback", [["26", "26 hafta"], ["52", "52 hafta"], ["156", "3 yıl"]], lb)}
    </div>

    <div class="grid kpis">
      <div class="kpi"><div class="label">Fiyat (${fmtDate(d.date)})</div><div class="value">${nf(d.price, d.decimals)}</div>
        <div class="note">${esc(d.contract)} · ${d.price_basis === "spot" ? "spot" : "vadeli proxy"}</div></div>
      <div class="kpi"><div class="label">Bileşik Skor</div><div class="value">${scoreCell(d.score)}</div><div class="note">${esc(d.score_label)}</div></div>
      <div class="kpi"><div class="label">${esc(d.group_names[d.spec])} endeksi (${lb}h)</div><div class="value">${idxCell(d.groups.find(g => g.key === d.spec)["idx" + lb])}</div><div class="note">spekülatif grup</div></div>
      <div class="kpi"><div class="label">${esc(d.group_names[d.slow])} endeksi (${lb}h)</div><div class="value">${idxCell(d.groups.find(g => g.key === d.slow)["idx" + lb])}</div><div class="note">yavaş para / ticari</div></div>
      <div class="kpi"><div class="label">Open Interest</div><div class="value">${nf(d.oi)}</div><div class="note ${pn(d.oi_chg)}">haftalık ${sgn(d.oi_chg)} · endeks ${nf(d.oi_idx52)}</div></div>
      <div class="kpi"><div class="label">Fiyat–OI</div><div class="value small" style="font-size:13.5px">${esc(d.price_oi_1w?.text.split(" — ")[1] || "–")}</div>
        <div class="note">4 hafta: ${esc(d.price_oi_4w?.text.split(" — ")[1] || "–")}</div></div>
    </div>

    <div class="card">
      <h2>${esc(d.name)} — Grup Pozisyonları</h2>
      <p class="muted small">${esc(d.report_name)} raporu, Futures Only. Endeksler son N haftanın en düşük (0) ve en yüksek (100) net pozisyonuna göre konumdur. Willco: net pozisyonun OI'ye oranının 26 haftalık endeksi.</p>
      <div class="table-wrap"><table>
        <thead><tr><th>Grup</th><th>Long</th><th>Short</th><th>Net</th><th>Haftalık Δ</th><th>Net / OI</th><th>Endeks 26h</th><th>Endeks 52h</th><th>Endeks 3y</th><th>Willco</th></tr></thead>
        <tbody>${groupRows}</tbody></table></div>
      <h3 style="margin-top:14px">Ayrışmalar</h3><ul class="small">${divs}</ul>
    </div>

    <div class="grid two">
      <div class="card"><h3>Fiyat</h3><div class="chart"><canvas id="cPrice"></canvas></div></div>
      <div class="card"><h3>COT Endeksi (${lb} hafta)</h3><div class="chart"><canvas id="cIdx"></canvas></div></div>
      <div class="card"><h3>Net Pozisyonlar</h3><div class="chart"><canvas id="cNet"></canvas></div></div>
      <div class="card"><h3>Open Interest</h3><div class="chart"><canvas id="cOI"></canvas></div></div>
      <div class="card"><h3>Willco (OI'ye göre normalize, 26h)</h3><div class="chart"><canvas id="cWillco"></canvas></div></div>
      <div class="card"><h3>Bileşik Skor Geçmişi</h3><div class="chart"><canvas id="cScore"></canvas></div></div>
    </div>

    <div class="card">
      <h2>Bileşik Skor: ${scoreCell(d.score)} <span class="muted small">${esc(d.score_label)}</span></h2>
      <p class="muted small">Her bileşen −1…+1 arası sinyal üretir. Ağırlık, o bileşenin 2006'dan bu yana sonraki 4 haftalık fiyat değişimiyle sıralı korelasyonudur (yalnızca o tarihe kadar bilinen veriyle, ileriye bakmadan hesaplanır).
      Negatif ağırlık, sinyalin ters çalıştığını gösterir (ör. aşırı spekülatif long → düşüş).</p>
      <div class="table-wrap"><table><thead><tr><th class="left">Bileşen</th><th>Sinyal</th><th>Ağırlık</th><th>Katkı</th></tr></thead><tbody>${comps}</tbody></table></div>
      <div class="note-box" style="margin-top:12px">
        <b>Skorun geçmiş başarısı (örneklem dışı, ${nf(perf.n)} hafta):</b>
        Skor ile sonraki 4 hafta arasındaki sıralı korelasyon ${sgn(perf.ic, 3)}.
        Skor ≥ +25 iken fiyat 4 hafta sonra %${nf(perf.hit_up)} oranında yükseldi (${nf(perf.n_up)} hafta),
        skor ≤ −25 iken %${nf(perf.hit_down)} oranında düştü (${nf(perf.n_down)} hafta). Karşılaştırma: tüm haftalarda yükseliş oranı %${nf(perf.base_up)}.
        ${Math.abs(perf.ic || 0) < 0.03 ? "<br><b>Not:</b> Bu enstrümanda skorun tahmin gücü zayıf, tek başına kullanılmamalı." : ""}
      </div>
    </div>

    ${fv ? `<div class="card"><h2>Makro Adil Değer</h2>
      <p class="muted small">Fiyatın logaritması ${fv.factors.map(esc).join(" ve ")} ile son 2 yıllık kayan regresyonla modellenir. z = fiyatın modelden sapması (standart sapma cinsinden). Son pencere R² = ${nf(fv.r2, 2)}, güncel z = <b>${sgn(fv.last_z, 2)}</b>.</p>
      <div class="grid two"><div class="chart"><canvas id="cFair"></canvas></div><div class="chart"><canvas id="cFairZ"></canvas></div></div></div>` : ""}

    <div class="card"><h2>Aşırı Uç İstatistikleri</h2>
      <p class="muted small">52 haftalık endeks ilk kez ≥80 veya ≤20 olduğunda, sonraki 1, 4 ve 12 haftada fiyat ne yaptı? (Fiyat değişimi %, "Yükseliş %" = pozitif sonuçlanan olayların oranı)</p>
      ${extremeTable(ex)}
    </div>`;

  bindSeg(el, "inst", v => { state.inst = v; renderInstruments(); });
  bindSeg(el, "range", v => { state.range = v; renderInstruments(); });
  bindSeg(el, "lookback", v => { state.lookback = v; renderInstruments(); });

  const i0 = sliceFrom(S.dates, state.range);
  const L = S.dates.slice(i0);
  const sl = a => a.slice(i0);
  const groups = d.groups.map(g => g.key);

  chart("cPrice", lineCfg(L, [{ label: d.name, data: sl(S.price), borderColor: C.ink }], { decimals: d.decimals }));
  chart("cIdx", lineCfg(L, [
    { label: d.group_names[d.spec], data: sl(S[`${d.spec}_idx${lb}`]), borderColor: GROUP_COLORS[d.spec] },
    { label: d.group_names[d.slow], data: sl(S[`${d.slow}_idx${lb}`]), borderColor: GROUP_COLORS[d.slow] },
    { label: d.group_names.nonrept, data: sl(S[`nonrept_idx${lb}`]), borderColor: GROUP_COLORS.nonrept, borderWidth: 1.1 },
    constLine(L, 80, C.green, "80"), constLine(L, 20, C.red, "20"),
  ], { y: { min: 0, max: 100 }, decimals: 0 }));
  chart("cNet", lineCfg(L, groups.map(g => ({ label: d.group_names[g], data: sl(S[`${g}_net`]), borderColor: GROUP_COLORS[g],
    borderWidth: g === d.spec || g === d.slow ? 1.8 : 1.1 })), { decimals: 0 }));
  chart("cOI", lineCfg(L, [
    { type: "bar", label: "Haftalık OI değişimi", data: sl(S.oi_chg), backgroundColor: sl(S.oi_chg).map(v => v >= 0 ? "#3fae86" : "#df6a62"), yAxisID: "y1" },
    { label: "Open Interest", data: sl(S.oi), borderColor: C.blue },
  ], { y1: {}, decimals: 0 }));
  chart("cWillco", lineCfg(L, [
    { label: d.group_names[d.spec], data: sl(S[`${d.spec}_willco`]), borderColor: GROUP_COLORS[d.spec] },
    { label: d.group_names[d.slow], data: sl(S[`${d.slow}_willco`]), borderColor: GROUP_COLORS[d.slow] },
    constLine(L, 80, C.green, "80"), constLine(L, 20, C.red, "20"),
  ], { y: { min: 0, max: 100 }, decimals: 0 }));
  chart("cScore", lineCfg(L, [
    { label: "Bileşik skor", data: sl(S.score), borderColor: C.purple, fill: { target: "origin", above: "rgba(18,128,92,.12)", below: "rgba(196,55,47,.12)" } },
    { label: "Fiyat", data: sl(S.price), borderColor: "#b9c1cd", borderWidth: 1, yAxisID: "y1" },
  ], { y: { min: -100, max: 100 }, y1: {}, decimals: 1 }));

  if (fv) {
    const j0 = sliceFrom(fv.dates, state.range);
    const FL = fv.dates.slice(j0);
    chart("cFair", lineCfg(FL, [
      { label: "Fiyat", data: fv.price.slice(j0), borderColor: C.ink },
      { label: "Adil değer", data: fv.fair.slice(j0), borderColor: C.orange, borderDash: [4, 3] },
    ], { decimals: d.decimals }));
    chart("cFairZ", lineCfg(FL, [
      { type: "bar", label: "Sapma (z)", data: fv.z.slice(j0), backgroundColor: fv.z.slice(j0).map(v => v >= 0 ? "#df6a62" : "#3fae86") },
    ], { decimals: 2 }));
  }
}

function extremeTable(ex) {
  if (!ex.length) return "<p class='muted'>Veri yok.</p>";
  const rows = [];
  ex.forEach(g => {
    g.zones.forEach(z => {
      const f = k => z.fwd[k] || {};
      rows.push(`<tr><td class="left">${esc(g.name)}</td><td class="left">${z.zone === "high" ? "≥80 (aşırı long)" : "≤20 (aşırı short)"}</td><td>${z.count}</td>
        ${["1", "4", "12"].map(k => `<td class="${pn(f(k).mean)}">${sgn(f(k).mean, 2)}%</td><td>${nf(f(k).pos)}%</td>`).join("")}
        <td class="left small muted">${z.last_events.slice(-3).map(fmtDate).join(", ") || "–"}</td></tr>`);
    });
    rows.push(`<tr><td class="left muted small">${esc(g.name)}</td><td class="left muted small">Tüm haftalar (karşılaştırma)</td><td></td>
      ${["1", "4", "12"].map(k => `<td class="muted small">${sgn(g.baseline[k].mean, 2)}%</td><td class="muted small">${nf(g.baseline[k].pos)}%</td>`).join("")}<td></td></tr>`);
  });
  return `<div class="table-wrap"><table><thead><tr><th class="left">Grup</th><th class="left">Bölge</th><th>Olay</th>
    <th>1h ort.</th><th>Yükseliş %</th><th>4h ort.</th><th>Yükseliş %</th><th>12h ort.</th><th>Yükseliş %</th><th class="left">Son olaylar</th></tr></thead>
    <tbody>${rows.join("")}</tbody></table></div>`;
}

function bindSeg(root, name, fn) {
  root.querySelectorAll(`[data-seg="${name}"] button`).forEach(b => b.addEventListener("click", () => fn(b.dataset.v)));
}

// ------------------------------------------------------------------ Makro
async function renderMacro() {
  const m = await load("macro");
  const s = await load("summary");
  const el = $("#tab-macro");
  const latest = m.latest.map(r => `<tr><td>${esc(r.name)}</td><td>${nf(r.value, Math.abs(r.value) >= 1000 ? 0 : 3)} <span class="muted small">${esc(r.unit)}</span></td>
    <td class="${pn(r.chg4w)}">${sgn(r.chg4w, Math.abs(r.value) >= 1000 ? 0 : 3)}</td><td class="muted">${fmtDate(r.date)}</td></tr>`).join("");
  const fvRows = s.instruments.map(i => `<tr><td>${esc(i.name)}</td><td class="${pn(-(i.fv_z ?? 0))}">${sgn(i.fv_z, 2)}</td>
    <td class="left small">${i.fv_z == null ? "–" : i.fv_z > 1.5 ? "Modele göre pahalı" : i.fv_z < -1.5 ? "Modele göre ucuz" : "Model aralığında"}</td></tr>`).join("");

  el.innerHTML = `
    <div class="controls"><span class="seg-label">Dönem</span>${seg("range", RANGE_OPTS, state.range)}</div>
    <div class="grid two">
      <div class="card"><h2>Son Değerler</h2><div class="table-wrap"><table><thead><tr><th>Seri</th><th>Değer</th><th>4 hafta Δ</th><th>Tarih</th></tr></thead><tbody>${latest}</tbody></table></div></div>
      <div class="card"><h2>Makro Adil Değer Özeti</h2><p class="muted small">Fiyatın makro modelden sapması. ±1.5'in ötesi belirgin sapmadır. Modeller Enstrümanlar sekmesinde.</p>
        <div class="table-wrap"><table><thead><tr><th>Enstrüman</th><th>z</th><th class="left">Yorum</th></tr></thead><tbody>${fvRows}</tbody></table></div></div>
    </div>
    <div class="grid two">
      ${m.eur_rates ? `<div class="card"><h3>EUR/USD ve 2 Yıllık Faiz Farkı (EU − US)</h3><div class="chart"><canvas id="mEur"></canvas></div></div>` : ""}
      ${m.gbp_rates ? `<div class="card"><h3>GBP/USD ve 10 Yıllık Faiz Farkı (UK − US, aylık)</h3><div class="chart"><canvas id="mGbp"></canvas></div>
        <p class="muted small">İngiltere günlük 2Y verisine ücretsiz erişilemediği için aylık 10Y farkı kullanılıyor.</p></div>` : ""}
      <div class="card"><h3>Altın ve 10Y Reel Faiz (ters eksen)</h3><div class="chart"><canvas id="mGold"></canvas></div></div>
      <div class="card"><h3>Getiri Eğrisi</h3><div class="chart"><canvas id="mCurve"></canvas></div></div>
      <div class="card"><h3>Kredi Spread'i ve Finansal Koşullar</h3><div class="chart"><canvas id="mCredit"></canvas></div></div>
      <div class="card"><h3>Atlanta Fed GDPNow</h3><div class="chart"><canvas id="mGdp"></canvas></div></div>
      <div class="card"><h3>Altın / Gümüş Oranı</h3><div class="chart"><canvas id="mGsr"></canvas></div></div>
      <div class="card"><h3>Bakır / Altın Oranı ve ABD 10Y</h3><div class="chart"><canvas id="mCg"></canvas></div></div>
      <div class="card"><h3>Nasdaq-100 / S&P 500 Oranı</h3><div class="chart"><canvas id="mNs"></canvas></div></div>
    </div>`;
  bindSeg(el, "range", v => { state.range = v; renderMacro(); });

  const cut = o => { const i = sliceFrom(o.dates, state.range); const r = { L: o.dates.slice(i) }; for (const k in o) if (k !== "dates") r[k] = o[k].slice(i); return r; };
  if (m.eur_rates) {
    const e = cut(m.eur_rates);
    chart("mEur", lineCfg(e.L, [
      { label: "EU2Y − US2Y", data: e.eu2y.map((v, i) => v != null && e.us2y[i] != null ? v - e.us2y[i] : null), borderColor: C.blue },
      { label: "EUR/USD", data: e.eurusd, borderColor: C.ink, yAxisID: "y1" },
    ], { y1: {}, decimals: 3 }));
  }
  if (m.gbp_rates) {
    const g = cut(m.gbp_rates);
    chart("mGbp", lineCfg(g.L, [
      { label: "UK10Y − US10Y", data: g.uk10y.map((v, i) => v != null && g.us10y[i] != null ? v - g.us10y[i] : null), borderColor: C.blue },
      { label: "GBP/USD", data: g.gbpusd, borderColor: C.ink, yAxisID: "y1" },
    ], { y1: {}, decimals: 3 }));
  }
  const g = cut(m.gold_real);
  chart("mGold", lineCfg(g.L, [
    { label: "10Y Reel Faiz (%)", data: g.real10y, borderColor: C.blue },
    { label: "Altın", data: g.xauusd, borderColor: C.orange, yAxisID: "y1" },
  ], { y: { reverse: true }, y1: {}, decimals: 2 }));
  const c = cut(m.curve);
  chart("mCurve", lineCfg(c.L, [
    { label: "10Y − 2Y", data: c.curve, borderColor: C.purple, fill: { target: "origin", above: "rgba(18,128,92,.10)", below: "rgba(196,55,47,.12)" } },
    { label: "ABD 10Y", data: c.us10y, borderColor: C.gray, borderWidth: 1, yAxisID: "y1" },
    { label: "ABD 2Y", data: c.us2y, borderColor: C.teal, borderWidth: 1, yAxisID: "y1" },
  ], { y1: {}, decimals: 2 }));
  const k = cut(m.credit);
  chart("mCredit", lineCfg(k.L, [
    { label: "HY spread (%)", data: k.hy_spread, borderColor: C.red },
    { label: "NFCI", data: k.nfci, borderColor: C.blue, yAxisID: "y1" },
  ], { y1: {}, decimals: 2 }));
  const gd = cut(m.gdpnow);
  chart("mGdp", lineCfg(gd.L, [{ label: "GDPNow (%)", data: gd.gdpnow, borderColor: C.green }], { decimals: 2 }));
  const r = cut(m.ratios);
  if (r.gold_silver) chart("mGsr", lineCfg(r.L, [{ label: "Altın/Gümüş", data: r.gold_silver, borderColor: C.orange }], { decimals: 1 }));
  if (r.copper_gold) chart("mCg", lineCfg(r.L, [
    { label: "Bakır/Altın ×1000", data: r.copper_gold, borderColor: C.teal },
    { label: "ABD 10Y", data: r.us10y, borderColor: C.gray, yAxisID: "y1" },
  ], { y1: {}, decimals: 3 }));
  if (r.ndx_spx) chart("mNs", lineCfg(r.L, [{ label: "NDX/SPX", data: r.ndx_spx, borderColor: C.blue }], { decimals: 3 }));
}

// ------------------------------------------------------------------ Volatilite
async function renderVol() {
  const v = await load("vol");
  const el = $("#tab-vol");
  const regimes = v.regimes.map(r => `<tr><td>${esc(r.name)}</td><td>${nf(r.rv, 1)}%</td><td>${nf(r.pct)}</td>
    <td><span class="cell" style="background:${r.regime === "Yüksek" ? "#fbe7e5" : r.regime === "Düşük" ? "#e8eefc" : "#f1f3f6"}">${r.regime}</span></td>
    <td class="left small">${esc(r.hint)}</td></tr>`).join("");
  const pairs = v.pairs.map(p => `<div class="card"><h3>${esc(p.label)}: Implied vs Realized</h3>
    <p class="muted small">Implied ${nf(p.last_iv, 1)} · Realized (20g) ${nf(p.last_rv, 1)} · Fark ${sgn(p.last_spread, 1)} (son 3 yılın %${nf(p.spread_pct)} yüzdeliği).
    Fark yüksekse opsiyonlar pahalı (korku primi), negatifse piyasa hareketi hafife alıyor.</p>
    <div class="chart"><canvas id="v_${p.key}"></canvas></div></div>`).join("");
  el.innerHTML = `
    <div class="controls"><span class="seg-label">Dönem</span>${seg("range", RANGE_OPTS, state.range)}</div>
    <div class="card"><h2>Volatilite Rejimi</h2><p class="muted small">20 günlük gerçekleşen volatilitenin son 3 yıldaki yüzdeliği.</p>
      <div class="table-wrap"><table><thead><tr><th>Enstrüman</th><th>Realized Vol</th><th>Yüzdelik</th><th>Rejim</th><th class="left">Strateji ipucu</th></tr></thead><tbody>${regimes}</tbody></table></div></div>
    <div class="grid two">
      ${v.term ? `<div class="card"><h3>VIX Vade Yapısı (VIX / VIX3M) — son ${nf(v.term.last, 2)}</h3>
        <p class="muted small">1'in üstü: kısa vadeli korku uzun vadeliden yüksek (backwardation). Tarihsel olarak panik ve dip bölgeleri.</p>
        <div class="chart"><canvas id="vTerm"></canvas></div></div>` : ""}
      ${v.move ? `<div class="card"><h3>MOVE (Tahvil Volatilitesi)</h3><p class="muted small">Tahvil piyasasındaki belirsizlik; yükselişi genelde tüm varlıklarda riski artırır.</p><div class="chart"><canvas id="vMove"></canvas></div></div>` : ""}
      ${pairs}
    </div>`;
  bindSeg(el, "range", x => { state.range = x; renderVol(); });
  v.pairs.forEach(p => {
    const i = sliceFrom(p.dates, state.range);
    chart(`v_${p.key}`, lineCfg(p.dates.slice(i), [
      { label: "Implied", data: p.iv.slice(i), borderColor: C.purple },
      { label: "Realized (20g)", data: p.rv.slice(i), borderColor: C.orange },
    ], { decimals: 1 }));
  });
  if (v.term) {
    const i = sliceFrom(v.term.dates, state.range); const L = v.term.dates.slice(i);
    chart("vTerm", lineCfg(L, [{ label: "VIX/VIX3M", data: v.term.ratio.slice(i), borderColor: C.blue }, constLine(L, 1, C.red, "1.0")], { decimals: 3 }));
  }
  if (v.move) {
    const i = sliceFrom(v.move.dates, state.range);
    chart("vMove", lineCfg(v.move.dates.slice(i), [{ label: "MOVE", data: v.move.move.slice(i), borderColor: C.teal }], { decimals: 1 }));
  }
}

// ------------------------------------------------------------------ Likidite
async function renderLiquidity() {
  const q = await load("liquidity");
  const el = $("#tab-liquidity");
  if (!q.dates) { el.innerHTML = "<div class='card'>Likidite verisi yok.</div>"; return; }
  el.innerHTML = `
    <div class="controls"><span class="seg-label">Dönem</span>${seg("range", RANGE_OPTS, state.range)}</div>
    <div class="grid kpis">
      <div class="kpi"><div class="label">Net Likidite</div><div class="value">${nf(q.last, 2)} trn $</div><div class="note">Fed bilançosu − TGA − Ters Repo</div></div>
      <div class="kpi"><div class="label">13 haftalık değişim</div><div class="value ${pn(q.chg13)}">${sgn(q.chg13, 2)}%</div></div>
      <div class="kpi"><div class="label">S&P 500 ile korelasyon</div><div class="value">${sgn(q.corr13.sp500, 2)}</div><div class="note">13 haftalık değişimler, son 3 yıl</div></div>
      <div class="kpi"><div class="label">Nasdaq-100 ile korelasyon</div><div class="value">${sgn(q.corr13.nasdaq, 2)}</div><div class="note">13 haftalık değişimler, son 3 yıl</div></div>
    </div>
    <div class="card"><h3>Net Likidite ve Endeksler</h3><div class="chart tall"><canvas id="lMain"></canvas></div></div>
    <div class="card"><h3>Bileşenler (trilyon $)</h3><div class="chart"><canvas id="lComp"></canvas></div>
      <p class="muted small">Fed bilançosu büyüdüğünde, TGA veya ters repo azaldığında piyasaya likidite girer. Kaynak: FRED (haftalık).</p></div>`;
  bindSeg(el, "range", x => { state.range = x; renderLiquidity(); });
  const i = sliceFrom(q.dates, state.range); const L = q.dates.slice(i);
  chart("lMain", lineCfg(L, [
    { label: "Net likidite (trn $)", data: q.netliq.slice(i), borderColor: C.blue, borderWidth: 2 },
    { label: "S&P 500", data: q.sp500.slice(i), borderColor: C.ink, yAxisID: "y1" },
    { label: "Nasdaq-100", data: q.nasdaq.slice(i), borderColor: C.orange, yAxisID: "y1", hidden: true },
  ], { y1: {}, decimals: 2 }));
  chart("lComp", lineCfg(L, [
    { label: "Fed bilançosu", data: q.walcl.slice(i), borderColor: C.blue },
    { label: "TGA", data: q.tga.slice(i), borderColor: C.orange },
    { label: "Ters repo", data: q.rrp.slice(i), borderColor: C.purple },
  ], { decimals: 2 }));
}

// ------------------------------------------------------------------ Sentiment
async function renderSentiment() {
  const se = await load("sentiment");
  const s = await load("summary");
  const el = $("#tab-sentiment");
  const a = se.aaii;
  const small = s.instruments.map(i => `<tr class="click" data-inst="${i.key}"><td>${esc(i.name)}</td><td>${idxCell(i.small_idx)}</td>
    <td class="left small">${i.small_idx == null ? "–" : i.small_idx >= 80 ? "Küçük yatırımcı aşırı long — ters sinyal: dikkat" : i.small_idx <= 20 ? "Küçük yatırımcı aşırı short — ters sinyal: fırsat olabilir" : "Nötr"}</td></tr>`).join("");
  el.innerHTML = `
    <div class="controls"><span class="seg-label">Dönem</span>${seg("range", RANGE_OPTS, state.range)}</div>
    <div class="grid two">
      <div class="card"><h2>Küçük Spekülatör Endeksi (COT)</h2>
        <p class="muted small">CFTC'nin "non-reportable" grubu, yani küçük ve çoğunlukla perakende oyuncular. Aşırı uçlarda ters (contrarian) sinyal olarak kullanılır. 52 haftalık endeks.</p>
        <div class="table-wrap"><table><thead><tr><th>Enstrüman</th><th>Endeks</th><th class="left">Yorum</th></tr></thead><tbody>${small}</tbody></table></div></div>
      ${a ? `<div class="card"><h2>AAII Yatırımcı Anketi</h2>
        <p class="muted small">${fmtDate(a.date)} · Boğa − Ayı farkı: <b class="${pn(a.last_spread)}">${sgn(a.last_spread, 1)}</b> puan (z = ${sgn(a.last_z, 2)}).
        Bireysel yatırımcıların 6 aylık beklentisi. Aşırı iyimserlik (z > 1.5) ve aşırı kötümserlik (z < −1.5) tarihsel olarak ters sinyal verir.</p>
        <div class="chart"><canvas id="sAaii"></canvas></div></div>` : ""}
    </div>
    ${a ? `<div class="card"><h3>AAII Boğa / Ayı Oranları</h3><div class="chart"><canvas id="sAaii2"></canvas></div></div>` : ""}`;
  bindSeg(el, "range", x => { state.range = x; renderSentiment(); });
  el.querySelectorAll("tr[data-inst]").forEach(tr => tr.addEventListener("click", () => { state.inst = tr.dataset.inst; showTab("instruments"); }));
  if (a) {
    const i = sliceFrom(a.dates, state.range); const L = a.dates.slice(i);
    chart("sAaii", lineCfg(L, [
      { type: "bar", label: "Boğa − Ayı", data: a.spread.slice(i), backgroundColor: a.spread.slice(i).map(v => v >= 0 ? "#9fd3bd" : "#efb1ab") },
      { label: "8 haftalık ortalama", data: a.spread8.slice(i), borderColor: C.ink },
    ], { decimals: 1 }));
    chart("sAaii2", lineCfg(L, [
      { label: "Boğa %", data: a.bullish.slice(i), borderColor: C.green },
      { label: "Ayı %", data: a.bearish.slice(i), borderColor: C.red },
      { label: "Nötr %", data: a.neutral.slice(i), borderColor: C.gray, borderWidth: 1 },
    ], { decimals: 1 }));
  }
}

// ------------------------------------------------------------------ İstatistik
async function renderStats() {
  const st = await load("stats");
  const s = await load("summary");
  const el = $("#tab-stats");
  const months = st.seasonality[Object.keys(st.seasonality)[0]].rows.map(r => r.month);
  const curMonth = new Date().getMonth();
  const seasonRows = Object.entries(st.seasonality).map(([k, o]) => `<tr><td>${esc(o.name)}<div class="muted small">${o.years}</div></td>
    ${o.rows.map((r, i) => {
      const c = r.mean == null ? "#f1f3f6" : r.mean > 0 ? `rgba(18,128,92,${Math.min(Math.abs(r.mean) / 3, 1) * .35 + .05})` : `rgba(196,55,47,${Math.min(Math.abs(r.mean) / 3, 1) * .35 + .05})`;
      return `<td style="background:${c};${i === curMonth ? "outline:2px solid #2459d6;outline-offset:-2px" : ""}" title="Medyan ${nf(r.median, 2)}%, ${r.n} yıl">${sgn(r.mean, 1)}%<div class="muted small">%${nf(r.pos)}</div></td>`;
    }).join("")}</tr>`).join("");

  const cm = st.corr;
  const M = cm[state.corr];
  const corrRows = cm.names.map((a, i) => `<tr><td>${esc(a)}</td>${cm.names.map((b, j) => {
    const v = M[i][j];
    const bg = v == null ? "#fff" : v > 0 ? `rgba(18,128,92,${Math.abs(v) * .5})` : `rgba(196,55,47,${Math.abs(v) * .5})`;
    return `<td style="background:${i === j ? "#f1f3f6" : bg}">${i === j ? "" : nf(v, 2)}</td>`;
  }).join("")}</tr>`).join("");
  const breaks = cm.breaks.length ? cm.breaks.map(b => `<li>${esc(b.a)} – ${esc(b.b)}: 60 gün ${sgn(b.c60, 2)}, 1 yıl ${sgn(b.c252, 2)}</li>`).join("") : "<li class='muted'>Belirgin korelasyon bozulması yok.</li>";
  const ex = (st.extremes[state.statInst] || {}).stats || [];
  const instOpts = s.instruments.map(i => [i.key, i.name.split(" (")[0]]);

  el.innerHTML = `
    <div class="card"><h2>Aşırı Uç Sonrası Fiyat Hareketi</h2>
      <div class="controls">${seg("statInst", instOpts, state.statInst)}</div>
      ${extremeTable(ex)}
      <p class="muted small">COT verisi 2006'dan beri. Olay sayısı az olan satırlarda sonuçlar güvenilir değildir. Ortalama ile "Tüm haftalar" satırını karşılaştır: fark yoksa sinyalin ek değeri yoktur.</p>
    </div>
    <div class="card"><h2>Sezonsallık</h2>
      <p class="muted small">Her ayın ortalama getirisi ve pozitif kapanan yılların oranı. Mavi çerçeve = içinde bulunulan ay.</p>
      <div class="table-wrap"><table><thead><tr><th>Enstrüman</th>${months.map(m => `<th>${m}</th>`).join("")}</tr></thead><tbody>${seasonRows}</tbody></table></div>
    </div>
    <div class="card"><h2>Korelasyon Matrisi</h2>
      <div class="controls">${seg("corr", [["c60", "60 gün"], ["c252", "1 yıl"]], state.corr)}</div>
      <p class="muted small">Günlük getiriler (faizlerde günlük değişim). Yeşil pozitif, kırmızı negatif korelasyon.</p>
      <div class="table-wrap"><table><thead><tr><th></th>${cm.names.map(n => `<th>${esc(n)}</th>`).join("")}</tr></thead><tbody>${corrRows}</tbody></table></div>
      <h3 style="margin-top:14px">Korelasyon Bozulmaları</h3><ul class="small">${breaks}</ul>
    </div>`;
  bindSeg(el, "statInst", v => { state.statInst = v; renderStats(); });
  bindSeg(el, "corr", v => { state.corr = v; renderStats(); });
}

// ------------------------------------------------------------------ Veri Doğrulama
async function renderValidation() {
  const v = await load("validation");
  const el = $("#tab-validation");
  const notes = v.notes || {};
  const names = v.names || {};
  const lvl = s => s === "ok" ? "ok" : (s === "red" ? "red" : "yellow");
  const statusText = s => ({ ok: "Doğrulandı", hold: "Bekletiliyor", yellow: "Uyarı", single: "Tek kaynak", red: "Uyuşmazlık" }[s] || s);

  const cot = Object.entries(v.cot).map(([k, e]) => `
    <details ${e.status !== "ok" ? "open" : ""}><summary>${statusDot(lvl(e.status === "hold" ? "yellow" : e.status))}${esc(names[k] || k)} — ${statusText(e.status)}
      <span class="muted small">(${esc(e.contract || "")}, doğrulanan son rapor ${fmtDate(e.validated_through)})</span></summary>
      <ul class="checks">${(e.checks || []).map(c => `<li>${statusDot(c.level === "ok" ? "ok" : c.level)}<b>${esc(c.name)}</b> — <span class="muted">${esc(c.detail)}</span></li>`).join("")}</ul>
    </details>`).join("");

  const px = Object.entries(v.prices).map(([k, e]) => {
    const srcs = Object.entries(e.sources).map(([sn, si]) => `<li>${statusDot(si.ok ? "ok" : "red")}<b>${esc(sn)}</b> <span class="muted">(${esc(si.symbol)})</span> —
      ${si.ok ? `son veri ${fmtDate(si.last_date)}: ${nf(si.last, 4)}` : `<span class="neg">${esc(si.error)}</span>`}
      <div class="muted small" style="margin-left:15px">${esc(notes[sn] || "")}</div></li>`).join("");
    const l30 = e.last30 || {};
    const live = e.live ? `<li>${statusDot(e.live.agree ? "ok" : "yellow")}<b>Canlı spot kontrolü</b> — ${Object.entries(e.live.values).map(([a, b]) => `${esc(a)}: ${nf(b, 3)}`).join(" · ")}
      ${e.live.agree ? "(iki kaynak uyuşuyor)" : "(uyuşmuyor veya eksik)"}</li>` : "";
    return `<details ${e.status === "red" ? "open" : ""}><summary>${statusDot(lvl(e.status))}${esc(names[k] || k)} — ${statusText(e.status)}
      <span class="muted small">(son 30 gün: ${l30.ok ?? 0} doğrulandı, ${l30.single ?? 0} tek kaynak, ${l30.conflict ?? 0} uyuşmazlık · ${e.basis || ""})</span></summary>
      <ul class="checks">${srcs}${live}
      ${e.note ? `<li class="muted">${esc(e.note)}</li>` : ""}
      ${e.latest ? `<li class="muted">Son gün ${fmtDate(e.latest.date)}: ${Object.entries(e.latest.values).map(([a, b]) => `${esc(a)} ${nf(b, 4)}`).join(" · ")} → kullanılan ${nf(e.latest.used, 4)} (${statusText(e.latest.status)})</li>` : ""}
      </ul></details>`;
  }).join("");

  const mac = Object.entries(v.macro).map(([k, e]) => `<tr><td>${statusDot(lvl(e.status === "single" ? "ok" : e.status))}${esc(e.name)}</td>
    <td class="left">${Object.entries(e.sources || {}).map(([sn, si]) => `${esc(sn)}${si.ok ? "" : ' <span class="neg">(hata)</span>'}`).join(", ")}</td>
    <td>${statusText(e.status)}</td><td>${fmtDate(e.last_date)}</td><td class="left small muted">${esc(e.detail || "")}</td></tr>`).join("");

  el.innerHTML = `
    <div class="card"><h2>Veri Doğrulama</h2>
      <p class="muted small">Son çalıştırma: ${new Date(v.generated).toLocaleString("tr-TR")}.
      COT verisi CFTC API'si ve CFTC haftalık metin dosyası olmak üzere iki ayrı kanaldan birebir karşılaştırılır; uyuşmazlıkta yeni hafta bekletilir ve sonraki çalıştırmada tekrar denenir.
      Fiyatlarda en az iki kaynağın tolerans içinde (döviz %${(v.tolerances?.fx ?? 0.003) * 100}, diğerleri %${(v.tolerances?.other ?? 0.01) * 100}) uyuşması gerekir.</p>
    </div>
    <div class="card"><h2>COT</h2>${cot}</div>
    <div class="card"><h2>Fiyatlar</h2>${px}</div>
    <div class="card"><h2>Makro ve Sentiment Serileri</h2>
      <p class="muted small">Resmi kaynaklarda (FRED, ECB) ikinci bağımsız kaynak olmadığından mantık kontrolleri yapılır. Volatilite endeksleri Yahoo ve CBOE arasında çapraz kontrol edilir.</p>
      <div class="table-wrap"><table><thead><tr><th>Seri</th><th class="left">Kaynak</th><th>Durum</th><th>Son veri</th><th class="left">Not</th></tr></thead><tbody>${mac}</tbody></table></div></div>`;
}

// ------------------------------------------------------------------ genel
const RENDER = {
  overview: renderOverview, instruments: renderInstruments, macro: renderMacro, vol: renderVol,
  liquidity: renderLiquidity, sentiment: renderSentiment, stats: renderStats, validation: renderValidation,
};

async function showTab(name) {
  state.tab = name;
  document.querySelectorAll("#tabs button").forEach(b => b.classList.toggle("active", b.dataset.tab === name));
  document.querySelectorAll(".tab").forEach(t => t.classList.toggle("active", t.id === `tab-${name}`));
  history.replaceState(null, "", `#${name}${name === "instruments" ? "/" + state.inst : ""}`);
  try { await RENDER[name](); }
  catch (e) { $(`#tab-${name}`).innerHTML = `<div class="card neg">Veri yüklenemedi: ${esc(e.message)}</div>`; console.error(e); }
  window.scrollTo({ top: 0 });
}

async function init() {
  document.querySelectorAll("[data-tab]").forEach(b => b.addEventListener("click", () => showTab(b.dataset.tab)));
  try {
    const [s, v] = await Promise.all([load("summary"), load("validation")]);
    const cotDate = s.instruments[0]?.date;
    $("#lastUpdate").textContent = `COT raporu: ${fmtDate(cotDate)} · Son güncelleme: ${new Date(s.generated).toLocaleString("tr-TR")}`;
    const all = [...Object.values(v.cot).map(e => e.status === "ok" ? "ok" : "yellow"), ...Object.values(v.prices).map(e => e.status)];
    const worst = all.includes("red") ? "red" : all.includes("yellow") ? "yellow" : "ok";
    const b = $("#validationBadge");
    b.className = `badge ${worst}`;
    b.textContent = worst === "ok" ? "✓ Veriler doğrulandı" : worst === "yellow" ? "! Kısmi doğrulama" : "✕ Uyuşmazlık var";
  } catch (e) { $("#lastUpdate").textContent = "Veri yüklenemedi"; }
  const [tab, inst] = location.hash.slice(1).split("/");
  if (inst) state.inst = inst;
  showTab(RENDER[tab] ? tab : "overview");
}
init();
