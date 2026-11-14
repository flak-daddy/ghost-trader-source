/* Ghost Trader UI. Talks to the local backend at POST /api/<name>. */
"use strict";

/* ---------- helpers ---------- */
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const money = (v, sign) => (v < 0 ? "−" : (sign && v > 0 ? "+" : "")) + "$" + Math.abs(v).toLocaleString("en-US", {minimumFractionDigits: 2, maximumFractionDigits: 2});
const mc = (c, sign) => money((c || 0) / 100, sign);
const f2 = v => (v == null || isNaN(v)) ? "—" : Number(v).toFixed(2);
const pct = (v, d = 1) => (v == null || isNaN(v)) ? "—" : (v * 100).toFixed(d) + "%";
const kTxt = k => "$" + (Number.isInteger(+k) ? (+k).toString() : (+k).toFixed(2).replace(/0$/, ""));
const plural = (n, w) => `${n} ${w}${n === 1 ? "" : "s"}`;
const TOKEN = new URLSearchParams(location.search).get("t");
const P = {
  check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>', x: '<path d="M6 6l12 12M18 6L6 18"/>',
  alert: '<circle cx="12" cy="12" r="9"/><path d="M12 7.5v5.5"/><circle cx="12" cy="16.6" r=".9" fill="currentColor" stroke="none"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.2 2"/>',
  warn: '<path d="M12 3.6L2.9 19.4h18.2z"/><path d="M12 9.5v4.5"/><circle cx="12" cy="16.7" r=".9" fill="currentColor" stroke="none"/>',
  star: '<path d="M12 3.8l2.5 5.3 5.7.7-4.2 3.9 1.1 5.7L12 16.6l-5.1 2.8 1.1-5.7-4.2-3.9 5.7-.7z" fill="currentColor"/>',
  spin: '<path d="M12 3a9 9 0 1 1-9 9"/>', ring: '<circle cx="12" cy="12" r="6"/>',
  dot: '<circle cx="12" cy="12" r="5" fill="currentColor" stroke="none"/>',
  pin: '<path d="M9 4h6l-1 5 3 3H7l3-3zM12 12v8"/>', folder: '<path d="M3 6h7l2 2h9v11H3z"/>',
  chart: '<path d="M4 19h16M6 16l4-5 4 3 5-7"/>', diamond: '<path d="M12 4l7 8-7 8-7-8z" fill="currentColor" stroke="none"/>',
  refresh: '<path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7"/>', down: '<path d="M12 4v12M6 11l6 6 6-6M5 20h14"/>'
};
const I = n => `<svg class="i" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">${P[n]}</svg>`;
const LOGO = `<svg class="i" style="width:1.3em;height:1.3em;color:var(--accent)" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linejoin="round"><path d="M12 3a7 7 0 0 0-7 7v10.5l2.4-1.7 2.3 1.7 2.3-1.7 2.3 1.7 2.3-1.7 2.4 1.7V10a7 7 0 0 0-7-7z" fill="color-mix(in srgb,currentColor 18%,transparent)"/><circle cx="9.5" cy="10.5" r="1.3" fill="currentColor" stroke="none"/><circle cx="14.5" cy="10.5" r="1.3" fill="currentColor" stroke="none"/></svg>`;
$("#logo").innerHTML = LOGO;

function toast(msg, ms = 3600) { const t = $("#toast"); t.innerHTML = msg; t.style.display = "block"; clearTimeout(toast.h); toast.h = setTimeout(() => t.style.display = "none", ms); }

async function api(name, args = {}) {
  try {
    const r = await fetch("/api/" + name, {method: "POST", headers: {"Content-Type": "application/json", "X-GT-Token": TOKEN}, body: JSON.stringify(args)});
    return await r.json();
  } catch (e) { return {error: "Lost contact with the app (" + e.message + ")."}; }
}

/* ---------- state ---------- */
let st = null, boot = {};
let ui = {tab: "Portfolio", pfMode: null, flashPos: null, chainExp: null, chainView: "both", flashStrike: null,
  hFilter: "All", hTag: null, hDay: null, hEvent: null, hExpand: null, calMonth: null, lot: null, lotEvent: null, perfDay: null, pin: null, chartTable: false, theme: "system", indN: "14", indRanges: {px: "3M", st: "3M", mood: "3M", vol: "3M"}, indTrades: false, outRange: "3M", indTable: false};
const S = () => (st && st.price) || 0;
const label = p => p.label;

/* ---------- theme ---------- */
function applyTheme() {
  const dark = ui.theme === "dark" || (ui.theme === "system" && !matchMedia("(prefers-color-scheme: light)").matches);
  document.documentElement.classList.toggle("light", !dark);
}
matchMedia("(prefers-color-scheme: light)").addEventListener("change", applyTheme);

/* ---------- header ---------- */
const TABS = ["Portfolio", "Chain", "Indicators", "Market", "History", "Performance", "Settings", "Help"];
function renderHeader() {
  const errs = st ? st.errors : 0;
  $("#tabs").innerHTML = TABS.map(t => `<button class="${ui.tab === t ? "on" : ""}" data-tab="${t}"${t === "History" && errs ? ` data-tip="Right-click: mark all as read"` : ""}>${t}${t === "History" && errs ? `<span class=badge>${errs}</span>` : ""}</button>`).join("");
  if (!st || !st.run) { $("#acct").innerHTML = st ? `<div><small>Data as of</small><span>${esc(st.data_asof || "—")}</span> <span class=pill>${esc(st.market.label)}</span></div>` : ""; return; }
  const b = st.bal;
  $("#acct").innerHTML = `
    <div><small>Account value</small><span class=lnk id="acctv" data-go="portfolio" data-tip="Double-click: go to Portfolio">${mc(b.account_value_c)}</span></div>
    <div><small>Collateral</small><span class=lnk data-go="portfolio:puts" data-tip="Double-click: show your open puts">${mc(b.collateral_c)}</span></div>
    <div><small>Shares</small><span class=lnk data-go="portfolio:shares" data-tip="Double-click: go to your shares">${b.shares ? b.shares + " × $" + f2(S()) : "none"}</span></div>
    <div><small>Data as of</small><span class=lnk data-go="report" data-tip="Double-click: startup report">${esc(st.data_asof || "—")}</span> <span class=pill>${esc(st.market.label)}</span></div>`;
}
const hov = $("#hovbox");
document.addEventListener("mousemove", e => {
  const onAcct = e.target.closest && e.target.closest("#acctv");
  if (onAcct && st && st.bal) {
    const b = st.bal;
    hov.innerHTML = `<div class="row tot"><span>Total account value</span><span>${mc(b.account_value_c)}</span></div>
      <div class=row><span class=meta>Available</span><span>${mc(b.available_c)}</span></div>
      <div class=row><span class=meta>Collateral</span><span>${mc(b.collateral_c)}</span></div>
      <div class=row><span class=meta>Shares value <span style="opacity:.8">(${b.shares} × $${f2(S())})</span></span><span>${mc(b.shares_value_c)}</span></div>`;
    hov.style.display = "block";
    hov.style.left = Math.min(e.clientX + 14, innerWidth - 310) + "px"; hov.style.top = (e.clientY + 18) + "px";
  } else hov.style.display = "none";
});
let tipT; const tipEl = $("#tip");
document.addEventListener("mouseover", e => {
  const el = e.target.closest && e.target.closest("[data-tip]");
  clearTimeout(tipT); tipEl.style.display = "none";
  if (!el || el.id === "acctv") return;
  tipT = setTimeout(() => { const r = el.getBoundingClientRect(); tipEl.textContent = el.dataset.tip;
    tipEl.style.display = "block"; tipEl.style.left = Math.max(4, Math.min(r.left, innerWidth - tipEl.offsetWidth - 8)) + "px"; tipEl.style.top = Math.max(4, r.top - 30) + "px"; }, 550);
});

/* ---------- navigation ---------- */
function resetMarks() { ui.indPin = null; ui.indFlash = false; ui.pfMode = null; ui.flashPos = null; ui.flashStrike = null; ui.lot = null; ui.lotEvent = null; ui.perfDay = null; ui.pin = null; ui.hExpand = null; ui.hDay = null; ui.hEvent = null; }
async function go(target) {
  const [a, b, c, d] = target.split(":");
  const hKeep = {f: ui.hFilter, t: ui.hTag, d: ui.hDay};
  resetMarks();
  if (a === "poshist") { ui.hDay = hKeep.d; }
  if (a === "portfolio") { ui.tab = "Portfolio"; ui.pfMode = b || null; }
  else if (a === "pos") { ui.tab = "Portfolio"; ui.flashPos = +b; }
  else if (a === "chain") { ui.tab = "Chain"; ui.chainExp = b; ui.flashStrike = +c; }
  else if (a === "chainpos") { const p = st.positions.find(x => x.id === +b); if (!p) return;
    ui.tab = "Chain"; ui.chainExp = p.expiry; ui.flashStrike = p.strike; closeOverlay(); closeDrawer(); await render(); openPosPanel(p.id); return; }
  else if (a === "history") { ui.tab = "History"; ui.hFilter = "All"; ui.hTag = null;
    if (b === "errors") { ui.hFilter = "Errors"; ui.hExpand = "all"; }
    if (b === "tag") ui.hTag = c;
    if (b === "lot") { ui.lot = +c; ui.lotEvent = d ? +d : null; }
    if (b === "day") ui.hDay = c;
    if (b === "event") ui.hEvent = +c; }
  else if (a === "perf") { ui.tab = "Performance"; ui.perfDay = b; }
  else if (a === "report") { showReport(); return; }
  else if (a === "help") { ui.tab = "Help"; ui.helpAt = b || null; }
  else if (a === "ind") { ui.tab = "Indicators"; if (b) { ui.indPin = b; ui.indFlash = true; const need = rangeFor(b);
    ui.indRanges = Object.fromEntries(Object.entries(ui.indRanges).map(([g, r]) => [g, RDAYS[need] > RDAYS[r] ? need : r])); } }
  else if (a === "poshist") { ui.tab = "History"; ui.hFilter = hKeep.f; ui.hTag = hKeep.t; ui.hEvent = null;
    closeOverlay(); closeDrawer(); await render(); openPosPanel(+b); return; }
  closeOverlay(); closeDrawer(); await render(); scrollTo(0, 0);
  setTimeout(() => { const f = document.querySelector(".flash"); if (f && !f.closest(".chainbox")) f.scrollIntoView({block: "center", behavior: "smooth"}); }, 60);
}
let pinT;
document.addEventListener("dblclick", e => {
  clearTimeout(pinT);
  const el = e.target.closest("[data-go]"); if (!el) return;
  e.preventDefault(); getSelection().removeAllRanges(); go(el.dataset.go);
});
document.addEventListener("contextmenu", e => {
  const t = e.target.closest('[data-tab="History"]');
  closeCtx(); if (!t) return;
  e.preventDefault();
  const m = document.createElement("div"); m.className = "ctxmenu"; m.id = "ctxmenu";
  m.innerHTML = `<button id=ctxRead>${I("check")} Mark all as read</button>`;
  m.style.left = e.clientX + "px"; m.style.top = e.clientY + "px"; document.body.appendChild(m);
  $("#ctxRead").onclick = async () => { closeCtx(); await api("mark_read"); await refreshState(); renderHeader(); if (ui.tab === "Portfolio") render(); toast(`${I("check")} Marked as read`, 1500); };
});
function closeCtx() { const m = $("#ctxmenu"); if (m) m.remove(); }
document.addEventListener("click", e => {
  if (!e.target.closest("#ctxmenu")) closeCtx();
  const t = e.target.closest("[data-tab]");
  if (t) { ui.tab = t.dataset.tab; resetMarks(); closeDrawer(); render(); }
});
document.addEventListener("keydown", e => {
  if (!st) return;
  if (e.target.matches("input,select,textarea")) { if (e.key === "Escape") e.target.blur(); else return; }
  if ($("#splash").innerHTML) return;
  if (e.key === "Escape" && $("#ctxmenu")) { closeCtx(); return; }
  if (e.key === "Escape") { if ($("#overlay").innerHTML) closeOverlay(); else if ($("#drawer").innerHTML) { if (tk) cancelTicket(); else closeDrawer(); } else if (ui.pin != null) { ui.pin = null; render(); } else if (ui.indPin && ui.tab === "Indicators") { ui.indPin = null; render(); } else if (ui.lot) { ui.lot = null; render(); } }
  if (/^[1-8]$/.test(e.key) && !$("#overlay").innerHTML && st.run) { ui.tab = TABS[+e.key - 1]; resetMarks(); closeDrawer(); render(); }
  if (e.key === "Enter" && $("#confirmBtn") && !$("#confirmBtn").disabled) $("#confirmBtn").click();
});

/* ---------- render ---------- */
async function refreshState() { const s = await api("state"); if (!s.error) st = s; return st; }
async function render() {
  applyTheme(); renderHeader();
  const fn = {Portfolio: renderPortfolio, Chain: renderChain, History: renderHistory, Indicators: renderIndicators, Market: renderMarket, Performance: renderPerf, Settings: renderSettings, Help: renderHelp}[ui.tab];
  await fn();
  renderHeader();
}
async function reload() { await refreshState(); await render(); }

/* ---------- PORTFOLIO ---------- */
const posLink = p => `<span class=lnk data-go="chainpos:${p.id}" data-tip="Double-click: open in the Chain with details">${esc(p.label)}</span>`;
const tagHtml = (t, tip) => `<span class="tag lnk" data-go="history:tag:${esc(t)}" data-tip="${tip || "Double-click: History tagged " + esc(t)}">${esc(t)}</span>`;
async function renderPortfolio() {
  await refreshState();
  if (!st.run) { $("#main").innerHTML = `<div class=empty>No run yet.</div>`; return; }
  const b = st.bal, av = b.account_value_c, start = st.run.start_cash_c, ret = start ? (av - start) / start : 0;
  let alerts = "";
  if (!ui.pfMode && !ui.flashPos) {
    if (st.warnings.length) alerts += `<div class="alert e"><span class=ic>${I("alert")}</span><span><b>${plural(st.warnings.length, "startup warning")}:</b> ${esc(st.warnings[0])}</span><span class="meta lnk" style="margin-left:auto" data-go="history:errors" data-tip="Double-click: open in History">Double-click to open in History</span></div>`;
    for (const a of st.alerts) { const p = a.pos;
      if (a.kind === "expiring") alerts += `<div class="alert w"><span class=ic>${I("clock")}</span><span><b>Expires this week:</b> ${posLink(p)} (${plural(p.open_qty, "contract")}), ${plural(p.dte, "day")}. ${st.price ? `${"TQQQ"} is ${Math.abs(p.dist * 100).toFixed(1)}% ${S() > p.strike ? "above" : "below"} the strike.` : ""}</span></div>`;
      if (a.kind === "near") alerts += `<div class="alert w"><span class=ic>${I("warn")}</span><span><b>${S() < p.strike ? "In the money" : "Near the money"}:</b> ${posLink(p)} (${plural(p.open_qty, "contract")}). TQQQ ${f2(S())} is ${Math.abs(p.dist * 100).toFixed(1)}% ${S() >= p.strike ? "above" : "below"} the strike (alert within 3%).</span></div>`;
      if (a.kind === "exdiv") alerts += `<div class="alert w"><span class=ic>${I("warn")}</span><span><b>Early assignment risk:</b> ${posLink(p)} is in the money ahead of the ${esc(a.ex)} ex-dividend date.</span></div>`;
    }
  }
  const puts = st.positions.filter(p => p.type === "put" && p.side === "short");
  const bar = ui.pfMode === "puts" ? `<div class=arrive><span><b>Showing open puts</b> <span class=meta>· ${plural(puts.length, "position")}, ${plural(puts.reduce((a, p) => a + p.open_qty, 0), "contract")} securing ${mc(b.collateral_c)}</span></span><button class=chip style="margin-left:auto" onclick="ui.pfMode=null;render()">Clear ${I("x")}</button></div>` : "";
  const cards = [["Account value", mc(av), `${mc(av - start, true)} (${(ret * 100).toFixed(2)}%)`], ["Available", mc(b.available_c), "spendable"],
    ["Collateral", mc(b.collateral_c), `${(b.collateral_c / av * 100 || 0).toFixed(1)}% of account · ${plural(puts.length, "put")}`],
    ["Shares", mc(b.shares_value_c), b.shares ? `${b.shares} TQQQ · ${st.locked >= b.shares ? "all covering" : (b.shares - st.locked) + " free"}` : "none"],
    ["Premium collected", mc(st.premium_c), "this run"], ["Interest earned", mc(st.interest_c), `+${mc(b.accrued_c)} accrued${st.next_pay ? " · pays " + esc(st.next_pay) : ""}`]]
    .map(([a, b2, c]) => `<div class=card><small>${a}</small><span class=big>${b2}</span><div class=meta>${c}</div></div>`).join("");
  const rows = st.positions.map(p => {
    const cls = ui.pfMode === "puts" ? (p.type === "put" && p.side === "short" ? "flash" : "dim") : (ui.flashPos === p.id ? "flash" : "");
    const cover = p.type === "put" && p.side === "short" ? mc(p.collateral_c) : p.side === "short" ? p.open_qty * 100 + " sh" : "—";
    const pn = p.pnl_c;
    return `<tr class="${cls}"><td class=l>${posLink(p)}<div class=meta>${p.kind} ${p.tags.map(t => tagHtml(t)).join("")}${p.quote_stale ? ` <span class=pill>stale quote</span>` : ""}</div></td>
      <td>${p.open_qty}</td><td>${f2(p.open_price)}</td><td>${f2(p.mark)}</td><td>${cover}</td>
      <td>${p.dist == null ? "—" : Math.abs(p.dist * 100).toFixed(1) + "% " + (p.otm ? "OTM" : "ITM")}</td><td>${p.dte}</td>
      <td class="${pn >= 0 ? "up" : "down"}">${pn == null ? "—" : mc(pn, true)}</td><td class="${pn >= 0 ? "up" : "down"}">${p.pnl_pct == null ? "—" : pct(p.pnl_pct)}</td>
      <td><button class="btn small" onclick="openTicket({close:${p.id}})">Close</button></td></tr>`; }).join("") || `<tr><td colspan=10 class="l meta" style="padding:16px 8px">No open options. Click any price on the Chain to open a ticket.</td></tr>`;
  const sh = st.bal.shares;
  const covering = st.positions.filter(p => p.type === "call" && p.side === "short").map(p => p.exp_label + " " + kTxt(p.strike) + " Call");
  const lots = st.lots.map(l => `${l.open_qty} ${l.source === "assigned" ? "assigned" : l.source} ${esc(l.acquired)} @ ${f2(l.cost)}`).join(" · ");
  const shRow = sh ? `<tr class="${ui.pfMode === "shares" ? "flash" : ""}"><td class=l>TQQQ shares<div class=meta>${lots}${covering.length ? ` · <span class=pill>${st.locked} covering ${esc(covering.join(", "))}</span>` : ""} · ${Math.max(0, sh - st.locked)} free</div></td><td>${sh}</td><td>${f2(st.avg_cost)}</td><td>${f2(S())}</td><td>${mc(b.shares_value_c)}</td><td class="${S() >= st.avg_cost ? "up" : "down"}">${money((S() - st.avg_cost) * sh, true)}</td><td class="${S() >= st.avg_cost ? "up" : "down"}">${pct((S() - st.avg_cost) / st.avg_cost)}</td><td><button class="btn small" onclick="openShares('sell_shares')">Sell</button></td></tr>`
    : `<tr><td colspan=8 class="l meta" style="padding:16px 8px">No shares.</td></tr>`;
  $("#main").innerHTML = `${bar}${alerts}<div class=cards style="margin-top:10px">${cards}</div>
    <div class=meta>Account value = cash + collateral + shares · interest counts once it's paid on the 15th · option buy-back prices not counted</div>
    <h2>Open options</h2><table><thead><tr><th class=l>Contract</th><th>Contracts</th><th>${st.positions.some(p => p.side === "long") ? "Opened at" : "Sold at"}</th><th>Mark</th><th>Collateral / cover</th><th>Distance</th><th>DTE</th><th>P&L</th><th>% of premium</th><th></th></tr></thead><tbody>${rows}</tbody></table>
    <h2 id=sharesH style="display:flex;justify-content:space-between;align-items:center">Shares <button class="btn small" onclick="openShares('buy_shares')">Buy shares…</button></h2><table><thead><tr><th class=l>Holding</th><th>Qty</th><th>Avg cost</th><th>Price</th><th>Value</th><th>P&L</th><th>%</th><th></th></tr></thead><tbody>${shRow}</tbody></table>
    <h2>Where TQQQ could go</h2><div id=pfCone class=card style="padding:12px 14px"><span class=meta><span class=spin>${I("spin")}</span> Drawing…</span></div>
    <div class=meta style="margin-top:10px">The calendar is on the <span class="lnk helplink" style="margin:0" onclick="ui.tab='Market';render()">Market</span> tab.</div>`;
  api("cone", {days_back: 90}).then(d => drawCone($("#pfCone"), d, false));
}
async function renderCalendar() {
  const c = await api("calendar", {month: ui.calMonth});
  const el = $("#calendar"); if (!el || c.error) return;
  ui.calMonth = c.month;
  const cell = d => {
    const chg = d.chg == null ? "" : `<small class="${d.chg >= 0 ? "up" : "down"}">${d.chg >= 0 ? "+" : "−"}${Math.abs(d.chg * 100).toFixed(2)}%</small>`;
    const px = d.close != null ? `<span class=px>$${f2(d.close)}${chg}</span>` : "";
    const items = d.items.map(it => {
      const cls = it.kind === "interest" ? "int" : "exp" + (it.active ? "" : " done");
      const go = it.go ? ` data-go="${esc(it.go)}"` : "";
      return `<div class="it ${cls}${it.go ? " lnk" : ""}"${go} data-tip="${esc(it.tip)}">${esc(it.text)}</div>`; }).join("");
    const evs = (d.events || []).length ? `<div class=evs>${d.events.map(e => `<span class="ev ${e.kind}" data-tip="${esc(e.tip)}">${esc(e.text)}</span>`).join("")}</div>` : "";
    const note = d.holiday ? `<div class=note>Market closed · ${esc(d.holiday)}</div>` : d.early ? `<div class=note>${esc(d.early)}</div>` : "";
    const trd = d.trades ? `<div class="trd lnk" data-go="history:day:${d.day}" data-tip="Double-click: History for this day">${I("dot")} ${plural(d.trades, "trade")}</div>` : "";
    const mine = (d.notes || []).map(n => `<div class="mynote ${n.kind}" data-note="${n.id}" data-tip="${esc((n.body ? n.body + " · " : "") + (n.remind !== "none" ? (n.remind === "morning" ? "reminder that morning" : "reminder the afternoon before") + " · " : "") + "click to edit")}">${n.kind === "note" ? "✎ " : (n.time_txt ? esc(n.time_txt) + " " : "")}${esc(n.title)}${n.remind !== "none" ? " " + I("clock") : ""}</div>`).join("");
    return `<div class="d ${d.in_month ? "" : "out"} ${d.today ? "today" : ""} ${d.holiday ? "hol" : ""}" data-day="${d.day}"><div class=top><span class=num>${d.n}${d.today ? ' <span class=pill style="font-size:10px">today</span>' : ""}</span>${px}</div>${note}${evs}${items}${mine}${trd}<button class=addnote data-add="${d.day}" title="Add a note, event or reminder">+</button></div>`; };
  el.innerHTML = `<div class=calbar><h2>Calendar · ${esc(c.label)}</h2>
      <button class="btn small" id=calPrev title="Previous month">‹</button>${c.month !== c.this_month ? `<button class="btn small" id=calNow>This month</button>` : ""}<button class="btn small" id=calNext title="Next month">›</button></div>
    <div class=cal>${["Mon", "Tue", "Wed", "Thu", "Fri"].map(x => `<div class=hd>${x}</div>`).join("")}${c.weeks.flat().map(cell).join("")}</div>
    <div class=meta style="margin-top:6px"><span class="it exp" style="font-size:11px;padding:0 5px;border-radius:3px;background:color-mix(in srgb,var(--warn) 22%,transparent)">$55 Put ×2</span> open expiry · <span style="opacity:.6;border:1px dashed var(--line);padding:0 5px;border-radius:3px">settled</span> resolved · <span class=ev style="font-size:11px;padding:0 5px;border-radius:3px;background:color-mix(in srgb,var(--accent) 12%,transparent)">CPI 7:30 AM</span> market event (CT; hover for details) · <span class=mynote style="font-size:11px;padding:0 5px;border-radius:3px;background:color-mix(in srgb,var(--accent) 14%,transparent)">✎ note</span> your notes and events (hover a day and click + to add; click one to edit) · TQQQ close with change from the previous close · double-click anything underlined</div>${c.events_note ? `<div class=meta>${esc(c.events_note)}</div>` : ""}`;
  const all = c.weeks.flat();
  $$("[data-add]").forEach(b => b.onclick = e => { e.stopPropagation(); noteEditor({day: b.dataset.add, kind: "note", remind: "none"}); });
  $$("[data-note]").forEach(x => x.onclick = e => { e.stopPropagation(); const n = all.flatMap(d => (d.notes || []).map(m => ({...m, day: d.day}))).find(m => m.id === +x.dataset.note); if (n) noteEditor(n); });
  $("#calPrev").onclick = () => { ui.calMonth = c.prev; renderCalendar(); };
  $("#calNext").onclick = () => { ui.calMonth = c.next; renderCalendar(); };
  if ($("#calNow")) $("#calNow").onclick = () => { ui.calMonth = null; renderCalendar(); };
}

/* ---------- CALENDAR NOTES (v1.12.0) ---------- */
function noteEditor(n) {
  const isNew = !n.id, dayTxt = new Date(n.day + "T12:00:00").toLocaleDateString("en-US", {weekday: "long", month: "long", day: "numeric"});
  $("#overlay").innerHTML = `<div class=scrim><div class=modal style="width:480px"><h3>${isNew ? "Add to" : "Edit"} ${esc(dayTxt)}</h3>
    <div class=row><label>Type</label><span class=seg><button class="btn small ${n.kind === "note" ? "on" : ""}" data-nk=note>Note</button><button class="btn small ${n.kind === "event" ? "on" : ""}" data-nk=event>Event</button></span></div>
    <div class=row><label id=ntLab>${n.kind === "note" ? "Note" : "Title"}</label><input id=ntTitle value="${esc(n.title || "")}" style="width:300px" placeholder="${n.kind === "note" ? "e.g. watch NVDA after the close" : "e.g. Review my Dec puts"}"></div>
    <div class=row id=ntTimeRow style="${n.kind === "event" ? "" : "display:none"}"><label>Time (CT, optional)</label><input id=ntTime value="${esc(n.time_txt || "")}" style="width:110px" placeholder="2:30 PM"></div>
    <div class=row style="align-items:flex-start"><label>Details (optional)</label><textarea id=ntBody rows=3 style="width:300px">${esc(n.body || "")}</textarea></div>
    <div class=row><label>Reminder</label><select id=ntRem>${[["none", "None"], ["morning", "That morning (7:45 AM CT)"], ["daybefore", "The afternoon before (3:30 PM CT)"]].map(([v, t]) => `<option value="${v}" ${n.remind === v ? "selected" : ""}>${t}</option>`).join("")}</select></div>
    <div class=meta>Reminders are desktop notifications from Ghost Trader's timer, which also runs when the app is closed. Notes and events are logged in History and the run CSV.</div>
    <div id=ntErr></div>
    <div class=actions style="justify-content:space-between">${isNew ? "<span></span>" : `<button class="btn danger" id=ntDel>Delete</button>`}<span style="display:flex;gap:8px"><button class=btn onclick="closeOverlay()">Cancel</button><button class="btn primary" id=ntSave>${isNew ? "Add" : "Save"}</button></span></div></div></div>`;
  let kind = n.kind;
  $$("[data-nk]").forEach(b => b.onclick = () => { kind = b.dataset.nk; $$("[data-nk]").forEach(x => x.classList.toggle("on", x === b));
    $("#ntTimeRow").style.display = kind === "event" ? "" : "none"; $("#ntLab").textContent = kind === "note" ? "Note" : "Title"; });
  $("#ntTitle").focus();
  $("#ntSave").onclick = async () => {
    const r = await api("note_save", {id: n.id || null, day: n.day, kind, title: $("#ntTitle").value, body: $("#ntBody").value, time: kind === "event" ? $("#ntTime").value : null, remind: $("#ntRem").value});
    if (r.error) { $("#ntErr").innerHTML = `<div class="alert e" style="margin-top:8px"><span class=ic>${I("warn")}</span><span>${esc(r.error)}</span></div>`; return; }
    closeOverlay(); toast(`${I("check")} ${isNew ? "Added" : "Saved"}`, 1500); renderCalendar(); };
  if ($("#ntDel")) $("#ntDel").onclick = async () => { const r = await api("note_delete", {id: n.id}); if (r.error) return toast(esc(r.error)); closeOverlay(); toast(`${I("check")} Deleted`, 1500); renderCalendar(); };
}

/* ---------- MARKET (v1.12.0) ---------- */
async function renderMarket(refresh) {
  if (!ui.mkt || refresh || Date.now() - ui.mkt._t > 180e3) {
    if (!ui.mkt) $("#main").innerHTML = `<div class=meta style="padding:20px 0"><span class=spin>${I("spin")}</span> Getting the Nasdaq heavyweights…</div>`;
    const m = await api("market", {refresh: !!refresh});
    if (m.error && !m.heavy) { $("#main").innerHTML = `<div class="alert e"><span class=ic>${I("alert")}</span><span>${esc(m.error)}</span></div>`; return; }
    ui.mkt = {...m, _t: Date.now()};
  }
  if (ui.tab !== "Market") return;
  const m = ui.mkt, sg = v => v == null ? "" : `<span class="${v >= 0 ? "up" : "down"}">${v >= 0 ? "+" : "−"}${Math.abs(v * 100).toFixed(2)}%</span>`;
  const tile = (r, sub) => r.missing ? `<div class=card><small>${r.symbol}</small><span class=big>—</span><div class=meta>no quote</div></div>`
    : `<div class=card><small>${r.symbol}</small><span class=big>$${f2(r.price)}</span><div class=meta>${sg(r.chg)} today${sub ? " · " + sub : ""}</div></div>`;
  const q = m.qqq, t = m.tqqq, lev = q.chg != null && t.chg != null ? `3× QQQ would be ${sg(3 * q.chg)}` : "";
  const soon = m.soon.length ? m.soon.map(s => `<div class=row><span class=meta>${esc(s.day_txt)}</span><span><span class="ev ${s.kind}" style="padding:1px 6px;border-radius:4px">${esc(s.text)}</span></span></div>`).join("") : `<div class=meta>Nothing scheduled in the next week.</div>`;
  $("#main").innerHTML = `<div class=bar style="margin-bottom:10px;justify-content:flex-end"><span class=meta>${m.asof ? "quotes " + esc(m.asof) + " · Yahoo, ~15 min delayed" : ""}</span><button class="btn small" id=mktRef>${I("refresh")} Refresh</button></div>
    ${m.error ? `<div class="alert w"><span class=ic>${I("warn")}</span><span>${esc(m.error)}. Showing the last quotes fetched.</span></div>` : ""}
    <div class=cards style="grid-template-columns:1fr 1fr 2fr">${tile(q, "the Nasdaq-100")}${tile(t, lev)}<div class="card mktsoon"><small>Coming up · next 7 days</small>${soon}</div></div>
    <h2>Nasdaq heavyweights today</h2><div class=card style="padding:10px"><div id=heat></div><div class=meta style="margin-top:6px">Sized by market value · color by today's change (green up, red down, stronger = bigger move) · hover for details. These eight make up a large share of the Nasdaq-100, so they drive QQQ, and TQQQ moves about 3× QQQ each day.</div></div>
    <h2>Earnings and TQQQ</h2><div class=card style="padding:10px 12px">${earnTable(m.earnings)}</div>
    <div id=calendar></div>`;
  drawHeat($("#heat"), m.heavy);
  $("#mktRef").onclick = async () => { $("#mktRef").innerHTML = `<span class=spin>${I("spin")}</span> Refreshing…`; await renderMarket(true); };
  renderCalendar();
}
function earnTable(rows) {
  const W = 180, H = 34;
  const bars = ms => { if (!ms.length) return `<span class=meta>no history yet</span>`; const mx = Math.max(.02, ...ms.map(x => Math.abs(x.move)));
    return `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}"><line x1="0" x2="${W}" y1="${H / 2}" y2="${H / 2}" stroke="var(--line)"/>${ms.map((x, i) => { const w = W / 8 - 4, h = Math.abs(x.move) / mx * (H / 2 - 2), xx = i * W / 8 + 2;
      return `<rect x="${xx}" y="${x.move >= 0 ? H / 2 - h : H / 2}" width="${w}" height="${Math.max(h, 1)}" rx="1.5" fill="${x.move >= 0 ? "var(--up)" : "var(--down)"}" data-tip="${esc(x.label)} report: TQQQ ${x.move >= 0 ? "+" : "−"}${Math.abs(x.move * 100).toFixed(1)}% (close before → close the day after)"/>`; }).join("")}</svg>`; };
  const pc = v => v == null ? "—" : `<span class="${v >= 0 ? "up" : "down"}">${v >= 0 ? "+" : "−"}${Math.abs(v * 100).toFixed(1)}%</span>`;
  return `<table class=mini><thead><tr><th class=l>Company</th><th class=l>Next report</th><th class=l>TQQQ around its last 8 reports</th><th>Typical move</th><th>Worst</th><th>Best</th></tr></thead><tbody>
    ${rows.map(r => `<tr><td class=l><b>${r.symbol}</b></td><td class=l>${r.next_txt ? esc(r.next_txt) + (r.days_to != null ? ` <span class=meta>· in ${plural(r.days_to, "day")}</span>` : "") : "<span class=meta>not announced</span>"}</td><td class=l>${bars(r.moves)}</td>
      <td data-tip="Average size of TQQQ's move, up or down, from the close before the report date to the close the day after">${r.avg_abs == null ? "—" : "±" + (r.avg_abs * 100).toFixed(1) + "%"}</td><td>${pc(r.worst)}</td><td>${pc(r.best)}</td></tr>`).join("")}</tbody></table>
    <div class=meta style="margin-top:6px">Each bar is TQQQ's move from the close before a report date to the close the trading day after, so it covers reports before the open and after the close. Report dates from Yahoo; TQQQ moves for other reasons on those days too.</div>`;
}
function drawHeat(el, rows) {
  const W = 1100, H = 220, ok = rows.filter(r => !r.missing);
  if (!ok.length) { el.innerHTML = `<div class=meta>No quotes for the heavyweights.</div>`; return; }
  const tot = ok.reduce((a, r) => a + (r.cap || 1), 0);
  // slice-and-dice in two rows: biggest first, split where the running total passes about 55%
  const sorted = ok.slice().sort((a, b) => (b.cap || 1) - (a.cap || 1)); let run = 0, cut = sorted.length;
  sorted.forEach((r, i) => { run += r.cap || 1; if (cut === sorted.length && run / tot >= .55) cut = i + 1; });
  const rowsOf = [sorted.slice(0, cut), sorted.slice(cut)].filter(x => x.length);
  const rowTot = rowsOf.map(rw => rw.reduce((a, r) => a + (r.cap || 1), 0));
  let y = 0, out = "";
  rowsOf.forEach((rw, j) => { const h = H * rowTot[j] / tot; let x = 0;
    rw.forEach(r => { const w = W * (r.cap || 1) / rowTot[j], k = Math.min(Math.abs(r.chg || 0) / .03, 1), col = (r.chg || 0) >= 0 ? "var(--up)" : "var(--down)";
      out += `<g data-tip="${esc(`${r.symbol} $${f2(r.price)} · ${r.chg >= 0 ? "+" : "−"}${Math.abs(r.chg * 100).toFixed(2)}% today${r.cap ? " · market value $" + (r.cap / 1e12).toFixed(2) + "T" : ""}${r.next_earn ? " · next earnings " + r.next_earn : ""}`)}">
        <rect x="${x + 2}" y="${y + 2}" width="${w - 4}" height="${h - 4}" rx="6" fill="${col}" fill-opacity="${(.12 + k * .5).toFixed(2)}" stroke="${col}" stroke-opacity=".5"/>
        <text x="${x + 12}" y="${y + 26}" fill="var(--text)" font-size="17" font-weight="600">${r.symbol}</text>
        <text x="${x + 12}" y="${y + 46}" fill="var(--text)" font-size="14">${r.chg >= 0 ? "+" : "−"}${Math.abs(r.chg * 100).toFixed(2)}%</text></g>`;
      x += w; });
    y += h; });
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" width="100%">${out}</svg>`;
}

/* ---------- CHAIN ---------- */
let chainData = null;
async function renderChain() {
  const c = await api("chain", {expiry: ui.chainExp, view: ui.chainView});
  if (c.error && !c.strikes) { $("#main").innerHTML = `<div class="alert e"><span class=ic>${I("alert")}</span><span>${esc(c.error)}</span></div>`; return; }
  chainData = c; ui.chainExp = c.expiry; ui.chainView = c.view || ui.chainView;
  const e = c.expiry, Sx = c.price, held = {};
  c.held.forEach(p => (held[p.strike] = held[p.strike] || []).push(p));
  const view = ui.chainView;
  const hasBid = q => q && q.bid > 0;
  const ks = c.strikes.filter(r => view === "both" ? (hasBid(r.call) || hasBid(r.put)) : hasBid(view === "calls" ? r.call : r.put));
  const atm = ks.reduce((a, r) => Math.abs(r.k - Sx) < Math.abs(a - Sx) ? r.k : a, ks.length ? ks[0].k : 0);
  const itm = (t, k) => t === "call" ? k < Sx : k > Sx, ic = (t, k) => itm(t, k) ? " itm" : "";
  const d2 = v => v == null ? "—" : v.toFixed(2);
  const vol = v => v == null ? "—" : v >= 10000 ? (v / 1000).toFixed(0) + "k" : v >= 1000 ? (v / 1000).toFixed(1) + "k" : String(v);
  const cell = (q, t, k, side) => { if (!hasBid(q)) { const m = `<td class="meta${ic(t, k)}">`, n = [`${m}no bid</td>`, `${m}—</td>`, `${m}—</td>`, `${m}—</td>`, `${m}—</td>`]; return side === "c" ? n.reverse().join("") : n.join(""); }
    const pc = `<td class="px${ic(t, k)}" data-k="${k}" data-t="${t}">`, cc = [`${pc}${f2(q.bid)}</td>`, `${pc}${f2(q.ask)}</td>`, `${pc}<b>${f2(q.mid)}</b></td>`];
    const d = `<td class="meta${ic(t, k)}">${d2(q.delta)}</td>`, v = `<td class="meta${ic(t, k)}">${vol(q.volume)}</td>`;
    return side === "c" ? v + d + cc.join("") : cc.reverse().join("") + d + v; };
  const head = view === "both" ? `<tr><th colspan=5>CALLS</th><th class=mid></th><th colspan=5>PUTS</th></tr><tr><th>Vol</th><th>Delta</th><th>Bid</th><th>Ask</th><th>Mid</th><th class=mid>Strike</th><th>Mid</th><th>Ask</th><th>Bid</th><th>Delta</th><th>Vol</th></tr>`
    : `<tr><th class=mid>Strike</th><th>Bid</th><th>Ask</th><th>Mid</th><th>Delta</th><th>Vol</th></tr>`;
  const rows = ks.map(r => { const K = r.k, hs = held[K] || [];
    const dot = hs.length ? `<span class=held data-go="chainpos:${hs[0].id}" data-tip="Double-click: details for your ${esc(hs[0].exp_label)} ${kTxt(K)} ${hs[0].type === "put" ? "Put" : "Call"} (${plural(hs[0].open_qty, "contract")})">●</span>` : "";
    const cls = ui.flashStrike === K ? "flash" : "";
    if (view === "both") return `<tr class="${cls}" id="k${K}">${cell(r.call, "call", K, "c")}<td class=mid>${K}${dot}</td>${cell(r.put, "put", K, "p")}</tr>`;
    const t = view === "calls" ? "call" : "put", q = r[t];
    return `<tr class="${cls}" id="k${K}"><td class=mid>${K}${dot}</td><td class="px${ic(t, K)}" data-k="${K}" data-t="${t}">${f2(q.bid)}</td><td class="px${ic(t, K)}" data-k="${K}" data-t="${t}">${f2(q.ask)}</td><td class="px${ic(t, K)}" data-k="${K}" data-t="${t}"><b>${f2(q.mid)}</b></td><td class="meta${ic(t, K)}">${d2(q.delta)}</td><td class="meta${ic(t, K)}">${vol(q.volume)}</td></tr>`; });
  const cut = ks.findIndex(r => r.k > Sx);
  const pline = `<tr class=pline>${view === "both" ? `<td colspan=5></td><td class=mid><span>TQQQ ${f2(Sx)}</span></td><td colspan=5></td>` : `<td><span>TQQQ ${f2(Sx)}</span></td><td colspan=5></td>`}</tr>`;
  if (cut >= 0) rows.splice(cut, 0, pline); else rows.push(pline);
  const opts = c.groups.map(([g, list]) => `<optgroup label="${g}">${list.map(x => `<option value="${x.exp}" ${x.exp === e ? "selected" : ""}>${esc(x.label)} · ${x.dte} days</option>`).join("")}</optgroup>`).join("");
  const chg = c.prev_close ? Sx - c.prev_close : null;
  $("#main").innerHTML = `<div class=bar><input value="TQQQ" size=6 disabled title="TQQQ only for now">
    <select id=expSel style="width:220px">${opts}</select>
    <div class=seg>${["calls", "both", "puts"].map(v => `<button class="btn ${view === v ? "on" : ""}" data-view="${v}">${v[0].toUpperCase() + v.slice(1)}</button>`).join("")}</div>
    <span class=meta>Every strike with a bid · ${c.market.open && !c.stale ? "quotes as of " + esc(c.asof) + " (Yahoo, ~15 min delayed)" : "quotes from the " + esc(c.market.close_txt) + " close"} ${c.stale ? `<span class=pill>stale${c.market.open ? "" : " · market closed"}</span>` : ""}</span>
    <button class="btn small" style="margin-left:auto" id=chainRef title="Fetch this chain again">${I("refresh")} Refresh</button></div>
    ${c.error ? `<div class="alert w"><span class=ic>${I("warn")}</span><span>Couldn't refresh this chain (${esc(c.error)}); showing the last good quotes.</span></div>` : ""}
    <div class=bar><span class=big>TQQQ ${f2(Sx)}</span>${chg == null ? "" : `<span class="${chg >= 0 ? "up" : "down"}">${chg >= 0 ? "+" : "−"}${Math.abs(chg).toFixed(2)} (${chg >= 0 ? "+" : "−"}${Math.abs(chg / c.prev_close * 100).toFixed(2)}%)</span>`}<span class=meta>· <span class=itmkey></span> in the money · <span class=warn>●</span> = you hold this strike · click any price to open a ticket</span></div>
    <div class=chainbox id=chainbox><table class=both><thead>${head}</thead><tbody>${rows.join("") || `<tr><td colspan=11 class=empty>No strikes with a bid for this expiration.</td></tr>`}</tbody></table></div>`;
  $("#expSel").onchange = ev => { ui.chainExp = ev.target.value; ui.flashStrike = null; render(); };
  $$("[data-view]").forEach(b => b.onclick = () => { ui.chainView = b.dataset.view; render(); });
  $("#chainRef").onclick = async () => { await api("refresh_quote", {expiry: e, type: "put", strike: atm}); render(); };
  $$("td.px").forEach(td => td.onclick = () => openTicket({expiry: e, strike: +td.dataset.k, type: td.dataset.t, action: "sell_to_open"}));
  setTimeout(() => { const t = document.getElementById("k" + (ui.flashStrike || atm)), box = $("#chainbox"); if (!box) return; if (t) box.scrollTop = t.offsetTop - box.clientHeight / 2; const hr = box.querySelectorAll("thead tr"); if (hr.length > 1) hr[1].querySelectorAll("th").forEach(th => th.style.top = hr[0].offsetHeight + "px"); }, 0);
}

/* ---------- TICKET ---------- */
let tk = null, tkData = null, tkSeq = 0;
function openTicket(o) {
  if (o.close) { const p = st.positions.find(x => x.id === o.close);
    tk = {action: p.side === "short" ? "buy_to_close" : "sell_to_close", position_id: p.id, type: p.type, expiry: p.expiry, strike: p.strike, qty: p.open_qty, price: null, note: "", tags: [], close_note: ""}; }
  else tk = {action: o.action || "sell_to_open", type: o.type, expiry: o.expiry, strike: o.strike, qty: 1, price: null, note: "", tags: [], compare: "dates"};
  tk.from = o.from || null;
  loadTicket(true);
}
function openShares(action) { tk = {action, qty: action === "sell_shares" ? Math.max(0, st.bal.shares - st.locked) || 100 : 100, price: null, note: "", tags: []}; tk.from = null; loadTicket(true); }
async function loadTicket(fresh) {
  const seq = ++tkSeq;
  document.body.classList.add("withDrawer");
  if (fresh) $("#drawer").innerHTML = `<div class=drawer><div class=meta><span class=spin>${I("spin")}</span> Getting a fresh quote…</div></div>`;
  const d = await api("ticket", {order: tk, fresh: !!fresh});
  if (seq !== tkSeq || !tk) return;
  if (d.error) { $("#drawer").innerHTML = `<div class=drawer><div style="display:flex;justify-content:space-between"><b>Ticket</b><button class="btn small" onclick="cancelTicket()">Close <span class=kbd>Esc</span></button></div><div class="alert e" style="margin-top:10px"><span class=ic>${I("alert")}</span><span>${esc(d.error)}</span></div></div>`; return; }
  tkData = d;
  if (tk.price == null && d.default_fill != null) tk.price = d.default_fill;
  renderTicket();
}
function cancelTicket() { const f = tk && tk.from; tk = null; if (f && st.positions.some(p => p.id === f)) openPosPanel(f); else closeDrawer(); }
function closeDrawer() { $("#drawer").innerHTML = ""; tk = null; document.body.classList.remove("withDrawer"); }
function renderTicket() {
  const d = tkData, q = d.quote || {}, c = d.check, ef = d.effects || {}, isShares = tk.action.endsWith("shares"), isClose = !!tk.position_id;
  const titles = {sell_to_open: "Sell to open", buy_to_open: "Buy to open", buy_to_close: "Buy to close", sell_to_close: "Sell to close", buy_shares: "Buy TQQQ shares", sell_shares: "Sell TQQQ shares"};
  const qtxt = d.market.open && !q.stale ? `quotes as of ${esc(d.quote_txt || "")}` : `quotes from the ${esc((d.market.close_txt || "").replace(/ \(.*\)/, ""))} close (stale${d.market.open ? "" : ", market closed"})`;
  let contract = "", cmp = "", effects = "";
  if (!isShares) {
    const expOpts = (d.groups || []).map(([g, l]) => `<optgroup label="${g}">${l.map(x => `<option value="${x.exp}" ${x.exp === tk.expiry ? "selected" : ""}>${esc(x.label)} · ${x.dte}d</option>`).join("")}</optgroup>`).join("");
    const kOpts = (d.strikes || [tk.strike]).map(K => `<option ${K === +tk.strike ? "selected" : ""} value="${K}">${K}</option>`).join("");
    contract = `<div class=row><label>Contract</label><span style="display:flex;gap:6px"><select id=tkExp ${isClose ? "disabled" : ""}>${expOpts}</select><select id=tkK ${isClose ? "disabled" : ""}>${kOpts}</select>
      <span class=seg><button class="btn small ${tk.type === "call" ? "on" : ""}" data-tt="call" ${isClose ? "disabled" : ""}>Call</button><button class="btn small ${tk.type === "put" ? "on" : ""}" data-tt="put" ${isClose ? "disabled" : ""}>Put</button></span></span></div>
      <div class=meta style="text-align:right">Bid ${f2(q.bid)} · Ask ${f2(q.ask)} · Mid ${f2(q.mid)}${q.iv ? " · IV " + (q.iv * 100).toFixed(1) + "%" + ivSrcShort(q.iv_src) : ""}${q.delta != null ? " · Δ " + q.delta.toFixed(2) : ""}</div>
      ${isClose ? "" : `<div class=row><label>Action</label><span class=seg><button class="btn small ${tk.action === "sell_to_open" ? "on" : ""}" data-sd="sell_to_open">Sell to open</button><button class="btn small ${tk.action === "buy_to_open" ? "on" : ""}" data-sd="buy_to_open">Buy to open</button></span></div>`}`;
    if (d.compare) { const cm = d.compare;
      const rowsH = cm.rows.map(r => { const sel = cm.mode === "dates" ? r.exp === tk.expiry : r.strike === +tk.strike;
        const key = cm.mode === "dates" ? `data-cx="${r.exp}"` : `data-ck="${r.strike}"`;
        if (r.fill == null) return `<tr class="${sel ? "cur" : ""}"><td class=l>${esc(r.label)}</td>${cm.mode === "dates" ? `<td>${r.dte}</td>` : `<td>${r.delta == null ? "—" : r.delta.toFixed(2)}</td>`}<td colspan=4 class=meta>no bid</td></tr>`;
        return `<tr class="click ${sel ? "cur" : ""}" ${key}><td class=l>${esc(r.label)}</td>${cm.mode === "dates" ? `<td>${r.dte}</td>` : `<td>${r.delta == null ? "—" : r.delta.toFixed(2)}</td>`}<td>${f2(r.bid)}/${f2(r.ask)}</td><td>${f2(r.fill)}</td><td>${pct(r.ret, 2)}</td><td class="${r.best ? "up" : ""}">${(r.ann * 100).toFixed(0)}%${r.best ? " " + I("star") : ""}</td></tr>`; }).join("");
      cmp = `<div style="display:flex;justify-content:space-between;align-items:center;margin:10px 0 4px"><span class=meta>COMPARE</span>
        <span class=seg><button class="btn small ${cm.mode === "dates" ? "on" : ""}" data-cm="dates">Dates</button><button class="btn small ${cm.mode === "strikes" ? "on" : ""}" data-cm="strikes">Strikes</button></span></div>
        <table class=mini><thead><tr><th class=l>${cm.mode === "dates" ? "Expiry" : "Strike"}</th><th>${cm.mode === "dates" ? "DTE" : "Delta"}</th><th>Bid/Ask</th><th>Fill</th><th>Return</th><th>Ann.</th></tr></thead><tbody>${rowsH}</tbody></table>
        <div class=meta style="margin:4px 0 8px">Click a row to switch the ticket to that contract.</div>`; }
  }
  const avBefore = ef.available_before_c, avAfter = ef.available_after_c;
  // When a rule blocks the trade the backend sends no effects; still show what the trade would be worth.
  const grossC = Math.round((parseInt(tk.qty) || 0) * (parseFloat(tk.price) || 0) * (isShares ? 1 : 100) * 100);
  if (ef.premium_c == null && tk.action === "sell_to_open") { ef.premium_c = grossC; if (tk.type === "put") ef.collateral_c = Math.round(+tk.strike * 100 * (parseInt(tk.qty) || 0) * 100); }
  if (ef.cost_c == null && /buy/.test(tk.action)) ef.cost_c = grossC;
  if (ef.proceeds_c == null && /sell_to_close|sell_shares/.test(tk.action)) ef.proceeds_c = grossC;
  if (tk.action === "sell_to_open" && tk.type === "put") effects = `<div class=row><label>Premium → Available now</label><span class=up>${mc(ef.premium_c || 0, true)}</span></div>
      <div class=row><label>Collateral set aside</label><span>${mc(ef.collateral_c || 0)}</span></div>
      <div class=row><label>Interest on collateral to expiry @ ${f2(d.rate)}%</label><span class=up>${mc(d.interest_c || 0, true)}</span></div>
      <div class=row data-tip="${pct(d.ret, 2)} over ${plural(d.dte, "day")} (premium + interest on the collateral, against the collateral) ≈ ${pct(d.ann)} a year if repeated back-to-back for a year. A comparison yardstick, not a forecast."><label>Return if it expires worthless</label><span><b>${pct(d.ret, 2)}</b></span></div>${chancesRows(d.chances, tk.type)}<div id=tkPayoff></div>`;
  else if (tk.action === "sell_to_open") effects = `<div class=row><label>Premium → Available now</label><span class=up>${mc(ef.premium_c || 0, true)}</span></div>
      <div class=row><label>Shares locked as cover</label><span>${(tk.qty || 0) * 100}</span></div>
      <div class=row data-tip="${pct(d.ret, 2)} over ${plural(d.dte, "day")} (premium against the value of the 100 shares per contract covering it) ≈ ${pct(d.ann)} a year if repeated back-to-back for a year. A comparison yardstick, not a forecast."><label>Return if it expires worthless</label><span><b>${pct(d.ret, 2)}</b></span></div>${chancesRows(d.chances, tk.type)}<div id=tkPayoff></div>`;
  else if (tk.action === "buy_to_close") effects = `<div class=row><label>Cost out${tk.type === "put" ? " (from this position's collateral)" : ""}</label><span class=down>${mc(-(ef.cost_c || 0))}</span></div>
      ${tk.type === "put" ? `<div class=row><label>Collateral released</label><span>${mc((ef.collateral_released_c || 0) - (ef.cost_c || 0))}</span></div>` : `<div class=row><label>Shares unlocked</label><span>${(tk.qty || 0) * 100}</span></div>`}
      ${ef.result_c != null ? `<div class=row><label>Result on these contracts</label><span class="${ef.result_c >= 0 ? "up" : "down"}">${mc(ef.result_c, true)}</span></div>` : ""}`;
  else if (tk.action === "sell_to_close" || tk.action === "sell_shares") effects = `<div class=row><label>Proceeds → Available</label><span class=up>${mc(ef.proceeds_c || 0, true)}</span></div>`;
  else effects = `<div class=row><label>Cost</label><span class=down>${mc(-(ef.cost_c || 0))}</span></div>`;
  if (avBefore != null && avAfter != null) effects += `<div class=row><label>Available after</label><span>${mc(avBefore)} → <b>${mc(avAfter)}</b></span></div>`;
  const priceBad = !c.ok && /price|bid|ask/.test(c.msg);
  document.body.classList.add("withDrawer");
  $("#drawer").innerHTML = `<div class=drawer>
    <div style="display:flex;justify-content:space-between"><span><b style="font-size:15px">${titles[tk.action]}</b>${helpFor(tk)}</span><button class="btn small" onclick="cancelTicket()">${tk.from ? "Back" : "Close"} <span class=kbd>Esc</span></button></div>
    <div class=meta>TQQQ ${f2(d.price)} · ${qtxt} <span class=lnk style="color:var(--accent)" id=tkRef>${I("refresh")} Refresh quote</span></div>
    ${isClose ? `<div style="margin:8px 0 2px;font-weight:600">${esc(st.positions.find(p => p.id === tk.position_id)?.label || "")}</div>` : ""}
    ${contract}
    ${isShares ? `<div class=meta style="text-align:right">Bid ${f2(q.bid)} · Ask ${f2(q.ask)}${!d.market.open ? " · market closed: the last price" : ""}</div>` : ""}
    <div class=row><label>${isShares ? "Shares" : "Contracts"}</label><input id=tkQ value="${esc(tk.qty)}" style="width:80px" inputmode=numeric><label>Fill price</label><input id=tkPx value="${esc(tk.price ?? "")}" style="width:80px" class="${priceBad ? "bad" : ""}"></div>
    <div class=meta style="text-align:right">Allowed: ${f2(q.bid)} (bid) – ${f2(q.ask)} (ask)</div>
    ${effects}
    ${isClose ? "" : `<div class=row><label>Note</label><input id=tkNote value="${esc(tk.note)}" placeholder="why this trade?" style="width:300px"></div>
    <div class=row><label>Tags</label><span style="flex:1;text-align:right">${tk.tags.map(t => `<span class=tag>${esc(t)} <span style="cursor:pointer" data-rmtag="${esc(t)}">${I("x")}</span></span>`).join("")}
      <input id=tkTag list=taglist placeholder="+ tag" style="width:110px;padding:2px 6px"><datalist id=taglist>${(st.tags || []).map(t => `<option value="${esc(t)}">`).join("")}</datalist></span></div>`}
    ${cmp}
    ${c.warn ? `<div class="alert w" style="margin:8px 0"><span class=ic>${I("warn")}</span><span>${esc(c.warn)}</span></div>` : ""}
    <div class="${c.ok ? "ok" : "err"}">${c.ok ? I("check") : I("x")} ${esc(c.msg)}</div>
    <div class=actions><button class=btn onclick="cancelTicket()">Cancel</button><button class="btn primary" id=reviewBtn ${c.ok ? "" : "disabled"}>Review trade</button></div></div>`;
  const re = () => { tk.price = null; loadTicket(false); };
  const ex = $("#tkExp"); if (ex) ex.onchange = e => { tk.expiry = e.target.value; re(); };
  const kk = $("#tkK"); if (kk) kk.onchange = e => { tk.strike = +e.target.value; re(); };
  $$("[data-tt]").forEach(b => b.onclick = () => { tk.type = b.dataset.tt; re(); });
  $$("[data-sd]").forEach(b => b.onclick = () => { tk.action = b.dataset.sd; re(); });
  $$("[data-cm]").forEach(b => b.onclick = () => { tk.compare = b.dataset.cm; loadTicket(false); });
  $$("[data-cx]").forEach(r => r.onclick = () => { tk.expiry = r.dataset.cx; re(); });
  $$("[data-ck]").forEach(r => r.onclick = () => { tk.strike = +r.dataset.ck; re(); });
  $$("[data-rmtag]").forEach(x => x.onclick = () => { tk.tags = tk.tags.filter(t => t !== x.dataset.rmtag); renderTicket(); });
  $("#tkQ").onchange = e => { tk.qty = e.target.value; loadTicket(false); };
  $("#tkPx").onchange = e => { tk.price = e.target.value; loadTicket(false); };
  $("#tkRef").onclick = () => { tk.price = null; loadTicket(true); };
  const n = $("#tkNote"); if (n) n.oninput = () => tk.note = n.value;
  const tg = $("#tkTag"); if (tg) tg.onkeydown = e => { if (e.key === "Enter" && tg.value.trim()) { let v = tg.value.trim().toLowerCase().replace(/\s+/g, "-"); if (!v.startsWith("#")) v = "#" + v; if (!tk.tags.includes(v)) tk.tags.push(v); renderTicket(); setTimeout(() => $("#tkTag") && $("#tkTag").focus(), 0); } };
  $("#reviewBtn").onclick = showConfirm;
  if (tk.action === "sell_to_open") drawPayoff($("#tkPayoff"), d.payoff);
}

/* Chances as text: never a flat 0% or 100%, which reads as "certain" when it's only very unlikely / very likely. */
const touchTxt = (c, type, K) => c.touch >= 1 && (type === "put" ? c.S <= K : c.S >= K) ? "already there" : chPct(c.touch);
function chPct(v) { return v == null ? "—" : v >= 0.995 ? ">99%" : v < 0.005 ? "<1%" : (v * 100).toFixed(0) + "%"; }
const IV_SRC = {quote: "from Yahoo's quote", price: "worked out from the option's price (Yahoo's reading was implausible)",
  nearby: "borrowed from the nearest strike (this contract's reading was implausible)"};
function ivSrcShort(s) { return s === "price" ? " (from price)" : s === "nearby" ? " (nearest strike)" : ""; }
function chBasis(c) {
  const iv = (c.iv * 100).toFixed(0) + "%", src = IV_SRC[c.iv_src] || "from the quote";
  const parts = [`IV ${iv}${ivSrcShort(c.iv_src)}`];
  if (c.S != null) parts.push(`TQQQ $${f2(c.S)}`);
  if (c.dte != null) parts.push(plural(Math.max(c.dte, 0), "day") + " left");
  const tip = `Implied volatility ${iv}, ${src}: the market's own guess at how much TQQQ will move. The chances assume that guess is right and say nothing about direction. Days are calendar days.`;
  return `<div class=meta style="text-align:right;font-size:11px" data-tip="${esc(tip)}">Using ${parts.join(" · ")} · estimates, not predictions</div>`;
}
function chancesRows(c, type) {
  if (!c) return "";
  const k = kTxt(tk.strike), be = "$" + f2(c.breakeven), pc = v => `<b>${chPct(v)}</b>`;
  const rows = type === "put" ? [
    ["Chance of expiring worthless", c.worthless, `% chance TQQQ closes above ${k} at expiration: the put expires and you keep the whole premium`],
    ["Chance of assignment", 1 - c.worthless, `% chance TQQQ closes below ${k} and you buy 100 shares per contract at ${k}`],
    [`Chance of touching ${k}`, c.touch, `% chance TQQQ trades at or below ${k} at some point before expiration, even if it finishes above. Touching isn't assignment (that depends on the close), but it's when the position looks worst`],
    ["Chance of profit at expiration", c.profit, `% chance TQQQ closes above ${be}, the breakeven (${k} strike − premium): either expiring worthless, or assigned with the drop smaller than the premium`],
  ] : [
    ["Chance of expiring worthless", c.worthless, `% chance TQQQ closes below ${k} at expiration: the call expires, your shares stay, you keep the whole premium`],
    ["Chance of being called away", 1 - c.worthless, `% chance TQQQ closes above ${k} and your 100 shares per contract are sold at ${k}`],
    [`Chance of touching ${k}`, c.touch, `% chance TQQQ trades at or above ${k} at some point before expiration, even if it finishes below. Touching isn't being called away (that depends on the close), but it's when your shares look most likely to go`],
    ["Chance of profit at expiration", c.profit, `% chance TQQQ closes below ${be} (${k} strike + premium), where the premium outweighs what selling at ${k} gives up`],
  ];
  return `<div class=chances>
    ${rows.filter(r => r[1] != null).map(([lab, v, tip]) => `<div class=row data-tip="${esc(tip)}"><label>${lab}</label><span>${/touching/.test(lab) ? `<b>${touchTxt(c, type, +tk.strike)}</b>` : pc(v)}</span></div>`).join("")}
    ${chBasis(c)}</div>`;
}
function helpFor(t) {
  const sec = t.action.endsWith("shares") ? null : t.type === "put" ? ["cash-secured-puts", "How cash-secured puts work"] : ["covered-calls-and-the-wheel", "How covered calls work"];
  return sec ? ` <span class="lnk helplink" onclick="go('help:${sec[0]}')" data-tip="Open the manual at this section">${sec[1]} ↗</span>` : "";
}

/* ---------- AUTO-REFRESH (market hours) ---------- */
let autoT = null;
function setAutoRefresh() {
  clearInterval(autoT); autoT = null;
  const m = ui.autoMin ?? 10; if (!m) return;
  autoT = setInterval(async () => {
    if (!st || !st.run || !st.market || !st.market.open) return;
    const r = await api("refresh_open"); if (r.closed) return;
    await refreshState(); indData = null;
    const busy = $("#overlay").innerHTML || $("#drawer").innerHTML || document.activeElement.matches("input,select,textarea");
    if (busy || ui.tab === "Settings" || ui.tab === "Help") renderHeader(); else render();
  }, m * 60000);
}

/* ---------- INDICATORS ---------- */
let indData = null;
const FG_BANDS = [[0, 25, "Extreme fear"], [25, 45, "Fear"], [45, 55, "Neutral"], [55, 75, "Greed"], [75, 100, "Extreme greed"]];
const fgName = v => v == null ? "" : (FG_BANDS.find(([a, b]) => Math.round(v) < b) || FG_BANDS[4])[2];
const zone = v => v == null ? "" : v >= 80 ? "overbought zone" : v <= 20 ? "oversold zone" : "";
const chg = (a, b, d = 2) => (a == null || b == null) ? "" : `<span class="${a >= b ? "up" : "down"}">${a >= b ? "+" : "−"}${Math.abs(a - b).toFixed(d)}</span>`;
const fmtDay = d => { const t = new Date(d + "T12:00:00"); return t.toLocaleDateString("en-US", {month: "short", day: "numeric", year: "2-digit"}); };
const IW = 900, IL = 56, IR = 96;
function ichart(c, N, xlab) {
  const H = c.h, T = 14, B = xlab ? 26 : 10, pw = IW - IL - IR;
  const X = i => IL + (N > 1 ? pw * i / (N - 1) : pw / 2), Y = v => T + (H - T - B) * (c.hi - v) / (c.hi - c.lo);
  let g = "";
  for (const t of c.ticks) g += `<line x1=${IL} x2=${IW - IR} y1=${Y(t)} y2=${Y(t)} stroke="var(--line)"/><text x=${IL - 8} y=${Y(t) + 4} fill="var(--dim)" font-size=11 text-anchor=end>${c.tfmt ? c.tfmt(t) : t}</text>`;
  for (const r of c.refs || []) g += `<line x1=${IL} x2=${IW - IR} y1=${Y(r.y)} y2=${Y(r.y)} stroke="var(--dim)" stroke-dasharray="4 4" opacity=".7" />`;
  for (const b of c.bands || []) g += `<text x=${IW - IR + 8} y=${Y((b[0] + b[1]) / 2) + 4} fill="var(--dim)" font-size=10.5>${b[2]}</text>`;
  const path = v => { let s = "", pen = false; v.forEach((x, i) => { if (x == null) { pen = false; return; } s += (pen ? " L" : " M") + X(i).toFixed(1) + "," + Y(x).toFixed(1); pen = true; }); return s; };
  const lines = c.series.map(s => `<path d="${path(s.v)}" fill=none stroke="${s.color}" stroke-width=2 ${s.dash ? 'stroke-dasharray="5 4"' : ""} stroke-linejoin=round stroke-linecap=round />`).join("");
  let endl = "";
  if (!c.bands) c.series.forEach((s, j) => { const i = s.v.map((x, k) => x == null ? -1 : k).filter(k => k >= 0).pop(); if (i == null) return;
    endl += `<text x=${IW - IR + 8} y=${Y(s.v[i]) + 4 + (c.series.length > 1 ? (j ? 9 : -5) * (Math.abs(Y(s.v[i]) - Y(c.series[1 - j].v[i] ?? s.v[i])) < 14 ? 1 : 0) : 0)} fill="var(--text)" font-size=11.5 font-weight=600>${c.efmt ? c.efmt(s.v[i]) : s.v[i].toFixed(1)}${c.series.length > 1 ? " " + s.name : ""}</text>`; });
  let xl = "";
  if (xlab && N > 1) { const tk = [...new Set([0, Math.round((N - 1) / 4), Math.round((N - 1) / 2), Math.round(3 * (N - 1) / 4), N - 1])];
    xl = tk.map(i => `<text x=${X(i)} y=${H - 6} fill="var(--dim)" font-size=11 text-anchor=${i === 0 ? "start" : i === N - 1 ? "end" : "middle"}>${fmtDay(xlab[i])}</text>`).join(""); }
  let mk = "";
  for (const m of c.marks || []) { const x = X(m.i);
    if (m.diamond && c.series[0].v[m.i] != null) { const y = Y(c.series[0].v[m.i]);
      mk += `<line x1="${x}" x2="${x}" y1="${T}" y2="${H - B}" stroke="${m.color}" stroke-width="1" opacity=".22"/><path d="M${x},${y - 6}L${x + 6},${y}L${x},${y + 6}L${x - 6},${y}Z" fill="${m.color}" stroke="var(--panel)" stroke-width="1.5"/>`; }
    else mk += `<line x1="${x}" x2="${x}" y1="${T}" y2="${H - B}" stroke="${m.color}" stroke-width="1" opacity=".28"/>`; }
  return `<div class=ichart><div class=ihead><b>${c.title}</b>${c.ctl || ""}${c.legend || ""}<span class=meta>${c.sub || ""}</span></div>
    <svg viewBox="0 0 ${IW} ${H}" width="100%" data-g="${c.g || ""}" data-t="${T}" data-b="${H - B}">${g}${mk}${lines}${endl}${xl}<line class=xh x1=0 x2=0 y1=${T} y2=${H - B} stroke="var(--dim)" stroke-width=1 style="display:none"/></svg></div>`;
}
function niceTicks(lo, hi, n) { const st = niceStep(hi - lo, n), out = []; const a = Math.floor(lo / st + 1e-9) * st, b = Math.ceil(hi / st - 1e-9) * st; for (let v = a; v <= b + 1e-9; v += st) out.push(+v.toFixed(6)); return out; }
const RANGES = ["14D", "1M", "3M", "6M", "1Y", "5Y"], RDAYS = {"14D": 14, "1M": 31, "3M": 92, "6M": 183, "1Y": 366, "5Y": 1827};
const isoMinus = n => { const t = new Date(); t.setDate(t.getDate() - n); return t.toISOString().slice(0, 10); };
function fgTint(sc) {
  if (sc == null) return null;
  const t = (sc - 50) / 50, k = Math.pow(Math.abs(t), 1.3), c = t < 0 ? "#7a3fe0" : "#a8c93a";
  return {bg: `color-mix(in srgb, ${c} ${Math.round(k * 11)}%, var(--panel))`, bd: `color-mix(in srgb, ${c} ${Math.round(k * 40)}%, var(--line))`};
}
const rangeFor = day => { const back = (Date.now() - new Date(day + "T12:00:00")) / 864e5; return RANGES.find(r => RDAYS[r] >= back + 1) || "5Y"; };
function ivTile(v) {
  if (!v) return `<div class=card><div class=thead>IV = —</div><div class=meta>TQQQ's 30-day at-the-money IV shows here once Ghost Trader has saved a reading (after the next quote refresh).</div></div>`;
  const few = v.n < 60;
  const tip = `IV rank: where today's IV sits between the lowest (0) and highest (100) reading of the past year. IV percentile: the share of past-year days with lower IV. Both use the readings Ghost Trader has saved (${plural(v.n, "day")} so far${few ? "; a full year is about 252" : ""}). High = options are expensive relative to TQQQ's own history, which favors selling premium.`;
  return `<div class=card data-tip="${esc(tip)}"><div class=thead>IV = ${(v.iv * 100).toFixed(0)}%</div>
    <div class=meta>rank <b>${v.rank ?? "—"}</b> · percentile <b>${v.pct ?? "—"}</b>${v.hv != null ? ` · 30-day realized ${(v.hv * 100).toFixed(0)}%` : ""}</div>
    <div class=meta>${few ? `based on ${plural(v.n, "day")} of saved IV so far` : `past-year range ${(v.lo * 100).toFixed(0)}–${(v.hi * 100).toFixed(0)}%`}</div></div>`;
}
let volNowCache = null;
async function loadVolNow() {
  const el = $("#volNow"); if (!el) return;
  const v = volNowCache && Date.now() - volNowCache.t < 5 * 60e3 ? volNowCache.v : await api("vol_now");
  volNowCache = {v, t: Date.now()};
  const el2 = $("#volNow"); if (!el2) return;
  if (v.error) { el2.innerHTML = `<div class=meta>${esc(v.error)}</div>`; return; }
  el2.innerHTML = `<div class=volcharts><div>${miniChart({title: "IV by expiration", sub: "at the money · today", pts: v.term.map(t => ({x: t.dte, y: t.iv * 100, lab: t.label, tip: `${t.label} · ${t.dte} days · IV ${(t.iv * 100).toFixed(1)}%`})), xfmt: x => x + "d", yfmt: y => y.toFixed(0) + "%"})}</div>
    <div>${miniChart({title: "IV by strike", sub: v.skew_expiry ? `${esc(v.skew_expiry)} (${v.skew_dte} days) · puts below TQQQ, calls above` : "", pts: v.skew.map(s => ({x: s.strike, y: s.iv * 100, color: s.type === "put" ? "var(--warn)" : "var(--up)", tip: `${kTxt(s.strike)} ${s.type} · IV ${(s.iv * 100).toFixed(1)}%`})), xfmt: x => "$" + x, yfmt: y => y.toFixed(0) + "%", vline: v.price, vlab: "TQQQ $" + f2(v.price)})}</div></div>
    <div class=meta style="margin-top:4px">Upward-sloping IV by expiration is normal; when near-term IV is above longer-term IV, the market expects a bumpy few weeks. Puts usually carry more IV than calls the same distance away (the skew).</div>`;
}
function miniChart(c) {
  const W = 430, H = 170, L = 44, R = 12, T = 12, B = 22, p = c.pts;
  if (p.length < 2) return `<div class=ihead><b>${c.title}</b></div><div class=meta>Not enough quotes yet.</div>`;
  const xs = p.map(q => q.x), ys = p.map(q => q.y), x0 = Math.min(...xs, c.vline ?? Infinity), x1 = Math.max(...xs, c.vline ?? -Infinity);
  const yt = niceTicks(Math.min(...ys) - 2, Math.max(...ys) + 2, 4);
  const X = x => L + (x - x0) / (x1 - x0 || 1) * (W - L - R), Y = y => T + (yt[yt.length - 1] - y) / (yt[yt.length - 1] - yt[0] || 1) * (H - T - B);
  const xt = niceTicks(x0, x1, 4).filter(x => x >= x0 && x <= x1);
  return `<div class=ihead><b>${c.title}</b><span class=meta>${c.sub || ""}</span></div><svg viewBox="0 0 ${W} ${H}" width="100%">
    ${yt.map(y => `<line x1="${L}" x2="${W - R}" y1="${Y(y)}" y2="${Y(y)}" stroke="var(--line)"/><text x="${L - 6}" y="${Y(y) + 4}" fill="var(--dim)" font-size="11" text-anchor="end">${c.yfmt(y)}</text>`).join("")}
    ${xt.map(x => `<text x="${X(x)}" y="${H - 6}" fill="var(--dim)" font-size="11" text-anchor="middle">${c.xfmt(x)}</text>`).join("")}
    ${c.vline != null ? `<line x1="${X(c.vline)}" x2="${X(c.vline)}" y1="${T}" y2="${H - B}" stroke="var(--dim)" stroke-dasharray="3 3"/><text x="${X(c.vline) + 4}" y="${T + 10}" fill="var(--dim)" font-size="10.5">${c.vlab}</text>` : ""}
    <path d="M${p.map(q => `${X(q.x).toFixed(1)},${Y(q.y).toFixed(1)}`).join("L")}" fill="none" stroke="var(--s1)" stroke-width="1.6" opacity=".7"/>
    ${p.map(q => `<circle cx="${X(q.x).toFixed(1)}" cy="${Y(q.y).toFixed(1)}" r="4" fill="${q.color || "var(--s1)"}" stroke="var(--panel)" stroke-width="1.5" data-tip="${esc(q.tip)}"/>`).join("")}</svg>`;
}
async function renderIndicators(refresh) {
  if (!indData || refresh) {
    if (!indData) $("#main").innerHTML = `<div class=meta style="padding:20px 0"><span class=spin>${I("spin")}</span> Getting TQQQ, the VIX and Fear & Greed…</div>`;
    const dd = await api("indicators", {refresh: !!refresh});
    if (dd.error) { $("#main").innerHTML = `<div class="alert e"><span class=ic>${I("alert")}</span><span>${esc(dd.error)}</span></div>`; return; }
    indData = dd;
  }
  if (ui.tab !== "Indicators") return;
  const d = indData, nw = d.now, n = ui.indN, NN = d.days.length, sel = d.stoch[n] || {k: [], d: null};
  const R = ui.indRanges;
  const startIdx = r => { const cut = isoMinus(RDAYS[r]); const i = d.days.findIndex(x => x >= cut); return i < 0 ? NN : i; };
  const G = {px: startIdx(R.px), st: startIdx(R.st), mood: startIdx(R.mood), vol: startIdx(R.vol || "3M")};
  // your trades as a layer (v1.11.0): diamonds on the price chart, faint lines on the others
  const TCOL = {open: "var(--accent)", close: "var(--dim)", assign: "var(--warn)", expire: "var(--up)"};
  const tradeMarks = (g, diamond) => !ui.indTrades ? [] : d.days.map((day, i) => [day, i]).filter(([day, i]) => i >= G[g] && d.trades[day])
    .map(([day, i]) => { const ks = d.trades[day].map(t => t.kind); const k = ["assign", "open", "close", "expire"].find(x => ks.includes(x)); return {i: i - G[g], color: TCOL[k], diamond}; });
  const cnt = g => NN - G[g], sl = (a, g) => a ? a.slice(G[g]) : null;
  const names = {tqqq: "TQQQ prices (Yahoo)", vix: "the VIX (Yahoo)", fg: "Fear & Greed (CNN)"};
  const alerts = Object.entries(d.status).filter(([, s]) => !s.ok).map(([k, s]) => `<div class="alert w"><span class=ic>${I("warn")}</span><span><b>Couldn't get ${names[k]}:</b> ${esc(s.error || "no data")}. ${s.at ? `Showing what was fetched ${esc(s.at_txt)}.` : "It'll show here once it's available."}${k === "fg" ? " CNN has no official feed, so its site changing can break this." : ""}</span></div>`).join("");
  const label = k => k === "14" ? "14,3,3" : k + "-day";
  const srows = d.lookbacks.map(String).map(k => { const c = nw.stoch[k] || {};
    return `<tr><td class=l>${label(k)}</td><td><b>${r0(c.k)}</b>${c.d != null ? `<span class=meta> / ${r0(c.d)}</span>` : ""}</td><td>${c.k != null && c.k_prev != null ? `<span class="${c.k >= c.k_prev ? "up" : "down"}">${c.k >= c.k_prev ? "▲" : "▼"}</span>` : ""}</td><td class="l meta">${zone(c.k)}</td></tr>`; }).join("");
  const fg = nw.fg || {}, tint = fgTint(fg.score);
  const cards = `<div class="cards itiles" style="grid-template-columns:repeat(auto-fit,minmax(220px,1fr))">
    <div class=card><small>TQQQ</small><span class=big>${nw.price == null ? "—" : "$" + f2(nw.price)}</span><div class=meta>${chg(nw.price, nw.prev)} vs. prior day · bars through ${nw.bars_through ? esc(fmtDay(nw.bars_through)) : "—"}</div></div>
    <div class="card stile"><small>Stochastic (%K${nw.stoch["14"] && nw.stoch["14"].d != null ? " / %D" : ""})</small><table class="mini istoch"><tbody>${srows}</tbody></table></div>
    ${ivTile(d.ivnow)}
    <div class=card><div class=thead>VIX = ${nw.vix == null ? "—" : f2(nw.vix)}</div><div class=meta>${chg(nw.vix, nw.vix_prev)} vs. prior close${nw.vix_lo != null ? ` · 1-year range ${f2(nw.vix_lo)}–${f2(nw.vix_hi)}` : ""}</div></div>
    <div class=card ${tint ? `style="background:${tint.bg};border-color:${tint.bd}"` : ""}><div class=thead>Fear &amp; Greed ${fg.score == null ? "unavailable" : `is at ${Math.round(fg.score)} <span class=pill>${esc(fg.rating || fgName(fg.score))}</span>`}</div>
      <div class=meta>${[["prior close", fg.previous_close], ["1 week", fg.week_ago], ["1 month", fg.month_ago], ["1 year", fg.year_ago]].filter(x => x[1] != null).map(([a, v]) => `${a} ${Math.round(v)}`).join(" · ")}</div></div></div>`;
  const seg = (items, cur, attr) => `<span class=seg>${items.map(([v, t]) => `<button class="btn small ${v === cur ? "on" : ""}" ${attr}="${v}">${t}</button>`).join("")}</span>`;
  const rseg = g => `<span class="seg irng">${RANGES.map(r => `<button class="btn small ${R[g] === r ? "on" : ""}" data-rg="${g}:${r}">${r}</button>`).join("")}</span>`;
  const stochTabs = `<div class=stabs role=tablist>${d.lookbacks.map(String).map(k => `<button role=tab class="${k === n ? "on" : ""}" data-in="${k}">${label(k)}</button>`).join("")}<span class=srng>${rseg(ui.indTable ? "px" : "st")}</span></div>`;
  const nTr = Object.keys(d.trades || {}).length;
  const bar = `<div class=bar style="margin-bottom:10px;justify-content:flex-end">
    <span class=meta data-tip="Your trades this run, drawn on the charts: ◆ on the price chart, a faint line on the others (blue opened, gray closed, amber assigned or called away, green expired worthless). Hover a day to see them.">Your trades</span>${seg([["0", "Off"], ["1", "On"]], ui.indTrades ? "1" : "0", "data-itr")}
    ${seg([["chart", "Chart"], ["table", "Table"]], ui.indTable ? "table" : "chart", "data-iv")}
    <button class="btn small" id=indRef>${I("refresh")} Refresh</button></div>`;
  const pctv = a => a ? a.map(x => x == null ? null : x * 100) : a;
  const volGroup = () => {
    const iv = pctv(sl(d.iv, "vol")), hv = pctv(sl(d.hv, "vol")), vals = [...iv, ...hv].filter(x => x != null);
    const ivn = iv.filter(x => x != null).length;
    const lo = vals.length ? Math.min(...vals) : 30, hi = vals.length ? Math.max(...vals) : 100, pd = Math.max((hi - lo) * .1, 3);
    const tk = niceTicks(Math.max(0, lo - pd), hi + pd, 4);
    const leg = `<span class=ileg><svg width=22 height=8><line x1=0 x2=22 y1=4 y2=4 stroke="var(--s1)" stroke-width=2 /></svg>Implied <svg width=22 height=8><line x1=0 x2=22 y1=4 y2=4 stroke="var(--s2)" stroke-width=2 stroke-dasharray="5 4"/></svg>Realized</span>`;
    return `<div class="card igroup" style="margin-top:12px"><div class="gtitle gflex">Volatility${rseg("vol")}</div>
      ${ichart({g: "vol", title: "Implied vs. realized", legend: leg, sub: "TQQQ 30-day at-the-money IV (saved daily since v1.9.0) · realized = last 30 trading days, annualized", h: 170, lo: tk[0], hi: tk[tk.length - 1], ticks: tk, tfmt: t => t + "%", efmt: v => v.toFixed(0) + "%",
        series: [{v: iv, color: "var(--s1)", name: "IV"}, {v: hv, color: "var(--s2)", dash: true, name: "real."}], marks: tradeMarks("vol")}, cnt("vol"), sl(d.days, "vol"))}
      ${ivn < 20 ? `<div class=meta style="margin:-2px 0 6px">The implied line is still short: Ghost Trader has saved ${plural(ivn, "day")} of IV in this range so far (one a day from v1.9.0 on).</div>` : ""}
      <div class=volnow id=volNow><div class=meta style="padding:10px 0"><span class=spin>${I("spin")}</span> Reading IV across expirations and strikes…</div></div></div>`;
  };
  let body;
  if (!NN) body = `<div class=empty>No TQQQ price history yet.</div>`;
  else if (ui.indTable) {
    const i0 = G.px;
    const rows = d.days.slice(i0).map((day, j) => { const i = i0 + j; return `<tr><td class=l>${esc(fmtDay(day))}</td><td>${f2(d.close[i])}</td><td>${r0(sel.k[i])}</td>${sel.d ? `<td>${r0(sel.d[i])}</td>` : ""}<td>${d.vix[i] == null ? "—" : f2(d.vix[i])}</td><td>${r0(d.fg[i])}</td><td class="l meta">${d.fg[i] == null ? "" : fgName(d.fg[i])}</td><td>${d.iv[i] == null ? "—" : (d.iv[i] * 100).toFixed(0) + "%"}</td><td>${d.hv[i] == null ? "—" : (d.hv[i] * 100).toFixed(0) + "%"}</td>${ui.indTrades ? `<td class="l meta">${(d.trades[day] || []).map(t => esc(t.text)).join("<br>")}</td>` : ""}</tr>`; }).reverse().join("");
    body = `<div class="stochpanel tblmode" style="margin-top:12px">${stochTabs}</div><div class=meta style="margin:6px 2px">The tabs pick the stochastic column; the range picks the dates.</div><div class=chainbox style="max-height:60vh"><table class=both><thead><tr><th class=l>Date</th><th>TQQQ close</th><th>Stoch ${label(n)} %K</th>${sel.d ? "<th>%D</th>" : ""}<th>VIX</th><th>Fear &amp; Greed</th><th></th><th>IV</th><th>Realized</th>${ui.indTrades ? "<th class=l>Your trades</th>" : ""}</tr></thead><tbody>${rows}</tbody></table></div>`;
  } else {
    const cl = sl(d.close, "px").filter(x => x != null), clo = Math.min(...cl), chi = Math.max(...cl), cp = Math.max((chi - clo) * .06, .3);
    const vx = sl(d.vix, "mood").filter(x => x != null), vlo = vx.length ? Math.min(...vx) : 10, vhi = vx.length ? Math.max(...vx) : 30, vp = Math.max((vhi - vlo) * .08, .5);
    const ct = niceTicks(clo - cp, chi + cp, 4), vt = niceTicks(Math.max(0, vlo - vp), vhi + vp, 4);
    const leg = sel.d ? `<span class=ileg><svg width=22 height=8><line x1=0 x2=22 y1=4 y2=4 stroke="var(--s1)" stroke-width=2 /></svg>%K <svg width=22 height=8><line x1=0 x2=22 y1=4 y2=4 stroke="var(--s2)" stroke-width=2 stroke-dasharray="5 4"/></svg>%D</span>` : "";
    const sk = sl(sel.k, "st"), sd = sl(sel.d, "st");
    body = `<div class=ichartbox id=ichartbox style="position:relative;margin-top:12px">
      <div class="card igroup"><div class=gtitle>TQQQ</div>
      ${ichart({g: "px", title: "Price", ctl: rseg("px"), sub: "daily close", h: 190, lo: ct[0], hi: ct[ct.length - 1], ticks: ct, tfmt: t => "$" + t, efmt: v => "$" + v.toFixed(2), series: [{v: sl(d.close, "px"), color: "var(--s1)"}], marks: tradeMarks("px", true)}, cnt("px"), sl(d.days, "px"))}
      <div class=stochpanel>${stochTabs}
      ${ichart({g: "st", title: "Stochastic", legend: leg, sub: sel.d ? "%K smoothed 3 · %D = 3-day average of %K · 80 / 20 lines" : `raw %K over ${n} trading days · 80 / 20 lines`, h: 170, lo: 0, hi: 100, ticks: [0, 20, 50, 80, 100], refs: [{y: 80}, {y: 20}], efmt: v => Math.round(v), series: sel.d ? [{v: sk, color: "var(--s1)", name: "%K"}, {v: sd, color: "var(--s2)", dash: true, name: "%D"}] : [{v: sk, color: "var(--s1)"}], marks: tradeMarks("st")}, cnt("st"), sl(d.days, "st"))}</div></div>
      <div class="card igroup" style="margin-top:12px"><div class="gtitle gflex">Market mood${rseg("mood")}</div>
      ${ichart({g: "mood", title: "VIX", sub: "S&P 500 expected volatility, daily close", h: 150, lo: vt[0], hi: vt[vt.length - 1], ticks: vt, efmt: v => v.toFixed(2), series: [{v: sl(d.vix, "mood"), color: "var(--s1)"}], marks: tradeMarks("mood")}, cnt("mood"))}
      ${ichart({g: "mood", title: "Fear & Greed", sub: "CNN, 0–100", h: 170, lo: 0, hi: 100, ticks: [0, 25, 45, 55, 75, 100], bands: FG_BANDS, series: [{v: sl(d.fg, "mood"), color: "var(--s1)"}], marks: tradeMarks("mood")}, cnt("mood"), sl(d.days, "mood"))}</div>
      ${volGroup()}
      <div class=itip id=itip></div></div>`;
  }
  $("#main").innerHTML = `${alerts}${bar}${cards}${body}
    <div class=meta style="margin-top:8px">TQQQ and the VIX from Yahoo (~15 min delayed) · Fear &amp; Greed from CNN's site (unofficial) · readings are saved with each trade you place · <span class="lnk helplink" style="margin:0" onclick="go('help:indicators')">How these work ↗</span></div>`;
  $$("[data-in]").forEach(b => b.onclick = () => { ui.indN = b.dataset.in; renderIndicators(); });
  $$("[data-rg]").forEach(b => b.onclick = () => { const [g, r] = b.dataset.rg.split(":"); ui.indRanges = {...ui.indRanges, [g]: r};
    api("settings_set", {ind_ranges: {[g]: r}}); renderIndicators(); });
  $$("[data-iv]").forEach(b => b.onclick = () => { ui.indTable = b.dataset.iv === "table"; renderIndicators(); });
  $$("[data-itr]").forEach(b => b.onclick = () => { ui.indTrades = b.dataset.itr === "1"; api("settings_set", {ind_trades: ui.indTrades}); renderIndicators(); });
  if ($("#volNow")) loadVolNow();
  $("#indRef").onclick = async () => { $("#indRef").innerHTML = `<span class=spin>${I("spin")}</span> Refreshing…`; await renderIndicators(true); };
  const box = $("#ichartbox"); if (!box) return;
  const tip = $("#itip");
  const gidx = day => { let j = -1; d.days.forEach((x, i) => { if (x <= day) j = i; }); return j; };
  const xAt = (i, m) => IL + (m > 1 ? (IW - IL - IR) * i / (m - 1) : 0);
  const svgs = () => [...box.querySelectorAll(".ichart > svg")];
  const hit = e => { const svg = e.target.closest && e.target.closest(".ichart > svg"); if (!svg) return null;
    const g = svg.dataset.g, m = cnt(g), r = svg.getBoundingClientRect(), x = (e.clientX - r.left) * IW / r.width;
    const li = Math.max(0, Math.min(m - 1, Math.round((x - IL) / (IW - IL - IR) * (m - 1))));
    return {gi: G[g] + li, svg}; };
  const hide = () => { tip.style.display = "none"; $$(".xh").forEach(l => l.style.display = "none"); };
  const showAt = (gi, y, pinned, from) => {
    svgs().forEach(sv => { const g = sv.dataset.g, li = gi - G[g], l = sv.querySelector(".xh");
      if (li < 0 || li >= cnt(g)) { l.style.display = "none"; return; }
      const X = xAt(li, cnt(g)); l.setAttribute("x1", X); l.setAttribute("x2", X); l.style.display = "";
      l.setAttribute("stroke", pinned ? "var(--warn)" : "var(--dim)"); l.setAttribute("stroke-dasharray", pinned ? "3 3" : ""); });
    tip.innerHTML = `<div style="display:flex;justify-content:space-between;align-items:center"><b>${esc(fmtDay(d.days[gi]))}</b>${pinned ? `<span class=ipx id=iUnpin title="Unpin (Esc)">${I("x")}</span>` : ""}</div>
      <div class=row><span class=meta>TQQQ</span><span>$${f2(d.close[gi])}</span></div>
      <div class=row><span class=meta>Stoch ${label(n)}</span><span>${r0(sel.k[gi])}${sel.d ? " / " + r0(sel.d[gi]) : ""}</span></div>
      <div class=row><span class=meta>VIX</span><span>${d.vix[gi] == null ? "—" : f2(d.vix[gi])}</span></div>
      <div class=row><span class=meta>Fear &amp; Greed</span><span>${d.fg[gi] == null ? "—" : Math.round(d.fg[gi]) + " · " + fgName(d.fg[gi])}</span></div>
      ${d.iv[gi] != null || d.hv[gi] != null ? `<div class=row><span class=meta>IV / realized</span><span>${d.iv[gi] == null ? "—" : (d.iv[gi] * 100).toFixed(0) + "%"} / ${d.hv[gi] == null ? "—" : (d.hv[gi] * 100).toFixed(0) + "%"}</span></div>` : ""}
      ${ui.indTrades && d.trades[d.days[gi]] ? `<div class=itrades>${d.trades[d.days[gi]].map(t => `<div><span style="color:${TCOL[t.kind]}">◆</span> ${esc(t.text)}</div>`).join("")}</div>` : ""}
      <div class="meta ifoot">${pinned ? "PINNED · " : "CLICK TO PIN · "}DOUBLE-CLICK: HISTORY FOR THIS DAY</div>`;
    tip.style.display = "block"; tip.classList.toggle("pinned", !!pinned);
    const ref = from || svgs().find(sv => { const li = gi - G[sv.dataset.g]; return li >= 0 && li < cnt(sv.dataset.g); }) || svgs()[0];
    const rr = ref.getBoundingClientRect(), br = box.getBoundingClientRect(), li = gi - G[ref.dataset.g];
    const px = (xAt(li, cnt(ref.dataset.g)) / IW) * rr.width + rr.left - br.left;
    tip.style.left = (px > br.width - 230 ? px - tip.offsetWidth - 14 : px + 14) + "px";
    tip.style.top = Math.max(8, y ?? (rr.top - br.top + 30)) + "px";
    const u = $("#iUnpin"); if (u) u.onclick = ev => { ev.stopPropagation(); ui.indPin = null; hide(); };
  };
  const pinned = () => ui.indPin ? gidx(ui.indPin) : -1;
  if (pinned() >= 0) {
    const gi = pinned();
    if (ui.indFlash) { ui.indFlash = false; svgs().forEach(sv => { const g = sv.dataset.g, li = gi - G[g]; if (li < 0 || li >= cnt(g)) return;
      sv.insertAdjacentHTML("afterbegin", `<rect class=iflash x=${xAt(li, cnt(g)) - 7} y=${+sv.dataset.t} width=14 height=${+sv.dataset.b - +sv.dataset.t} fill="var(--warn)" opacity=.22 />`); }); }
    showAt(gi, null, true);
  } else if (ui.indPin) ui.indPin = null;
  box.addEventListener("mouseleave", () => { if (pinned() < 0) hide(); });
  box.addEventListener("mousemove", e => { if (pinned() >= 0) return; const h = hit(e); if (!h) { hide(); return; }
    showAt(h.gi, e.clientY - box.getBoundingClientRect().top - 40, false, h.svg); });
  let clickT;
  box.addEventListener("click", e => {
    if (e.target.closest("#iUnpin") || e.target.closest("button")) return;
    const h = hit(e); if (!h) return;
    clearTimeout(clickT);
    if (e.detail !== 1) return;
    clickT = setTimeout(() => { ui.indPin = d.days[h.gi]; showAt(h.gi, e.clientY - box.getBoundingClientRect().top - 40, true, h.svg); }, 260);
  });
  box.addEventListener("dblclick", e => { if (e.target.closest("button")) return; clearTimeout(clickT); const h = hit(e); if (!h) return; getSelection().removeAllRanges(); go("history:day:" + d.days[h.gi]); });
}

/* ---------- HELP ---------- */
let manualData = null;
async function renderHelp() {
  if (!manualData) { const m = await api("manual"); if (m.error) { $("#main").innerHTML = `<div class="alert e"><span class=ic>${I("alert")}</span><span>${esc(m.error)}</span></div>`; return; } manualData = m; }
  const m = manualData;
  const toc = m.toc.filter(t => t.id !== "contents").map(t => `<a class="t${t.level}" href="#${t.id}" data-h="${t.id}">${esc(t.text)}</a>`).join("");
  $("#main").innerHTML = `<div class=help><nav class=helptoc><div class=meta style="margin-bottom:6px">MANUAL · v${esc(m.version)}</div>
      <input id=helpQ placeholder="Find in the manual…" style="width:100%;margin-bottom:8px">${toc}</nav>
    <article class=manual id=manual>${m.html}</article></div>`;
  const art = $("#manual"), q = $("#helpQ");
  const jump = id => { const t = document.getElementById(id); if (!t) return; const y = t.getBoundingClientRect().top + scrollY - $("header").offsetHeight - 10; scrollTo({top: y}); t.classList.add("flashh"); setTimeout(() => t.classList.remove("flashh"), 1400); };
  $("#main").querySelectorAll("a[href]").forEach(a => a.onclick = e => {
    const h = a.getAttribute("href"); e.preventDefault();
    if (h.startsWith("#")) jump(h.slice(1));
    else api("open_manual_link", {url: h}).then(r => r.error ? toast(esc(r.error)) : toast("Opened in your browser."));
  });
  q.onkeydown = e => {
    if (e.key !== "Enter" || !q.value.trim()) return;
    const needle = q.value.trim().toLowerCase(), els = [...art.querySelectorAll("h2,h3,h4,p,li,td")];
    const start = (renderHelp.lastHit != null && renderHelp.lastQ === needle) ? renderHelp.lastHit + 1 : 0;
    let k = els.findIndex((el, i) => i >= start && el.textContent.toLowerCase().includes(needle));
    if (k < 0) k = els.findIndex(el => el.textContent.toLowerCase().includes(needle));
    if (k < 0) { toast("Not found in the manual."); return; }
    renderHelp.lastHit = k; renderHelp.lastQ = needle;
    const el = els[k]; scrollTo({top: el.getBoundingClientRect().top + scrollY - $("header").offsetHeight - 40});
    el.classList.add("flashh"); setTimeout(() => el.classList.remove("flashh"), 1400);
  };
  const at = ui.helpAt; ui.helpAt = null;
  if (at) setTimeout(() => jump(at), 0); else scrollTo(0, 0);
}

/* ---------- POSITION DETAILS ---------- */
async function openPosPanel(id) {
  const p = await api("position", {id});
  if (p.error) return toast(esc(p.error));
  if (p.finished) return storyPanel(p);
  const q = p.quote, prem = p.premium_c, short = p.side === "short";
  tk = null; document.body.classList.add("withDrawer");
  const tgs = p.tags.map(t => tagHtml(t)).join("");
  $("#drawer").innerHTML = `<div class=drawer>
    <div style="display:flex;justify-content:space-between"><b style="font-size:15px">Your position</b><button class="btn small" onclick="closeDrawer()">Close <span class=kbd>Esc</span></button></div>
    <h3 style="margin:6px 0 2px;font-size:17px">${esc(p.label)}</h3>
    <div class=meta>${p.kind} · ${plural(p.open_qty, "contract")} · opened ${esc(p.opened)}${tgs ? " · " + tgs : ""}</div>
    <table class=mini style="margin-top:10px"><tbody>
      <tr><td class=l>${short ? "Sold at" : "Bought at"}</td><td>${f2(p.open_price)} · <span class="${short ? "up" : "down"}">${mc(short ? prem : -prem, true)}</span> ${short ? "premium" : "cost"}</td></tr>
      <tr><td class=l>Now</td><td>${q ? `bid ${f2(q.bid)} · ask ${f2(q.ask)} · mark ${f2(q.mid)}${q.stale ? " <span class=pill>stale</span>" : ""}` : "no quote"}</td></tr>
      <tr><td class=l>P&L if closed at the mark</td><td class="${p.pnl_c >= 0 ? "up" : "down"}">${p.pnl_c == null ? "—" : `${mc(p.pnl_c, true)} (${pct(p.pnl_pct)} of ${short ? "premium" : "cost"})`}</td></tr>
      ${short ? `<tr><td class=l>${p.type === "put" ? "Collateral" : "Covering"}</td><td>${p.type === "put" ? mc(p.collateral_c) : p.open_qty * 100 + " TQQQ shares"}</td></tr>` : ""}
      ${short && p.type === "put" ? `<tr><td class=l>Interest on collateral to expiry</td><td class=up>${mc(p.interest_c, true)}</td></tr>` : ""}
      ${short && p.ret != null ? `<tr data-tip="${pct(p.ret, 2)} over the ${plural(p.days_total, "day")} from open to expiration (${p.type === "put" ? "premium + interest on the collateral, against the collateral" : "premium against the value of the shares covering it"}) ≈ ${pct(p.ann)} a year if repeated back-to-back. A comparison yardstick, not a forecast."><td class=l>Return if it expires worthless</td><td><b>${pct(p.ret, 2)}</b></td></tr>` : ""}
      <tr><td class=l>TQQQ vs. strike</td><td>${f2(p.price)} vs. ${kTxt(p.strike)} · ${Math.abs(p.dist * 100).toFixed(1)}% ${p.otm ? "out of" : "in"} the money</td></tr>
      <tr><td class=l>Days to expiration</td><td>${p.dte} <span class=meta>(${esc(p.exp_label)})</span></td></tr>
      <tr><td class=l>If it expires worthless</td><td>${short ? `keep ${mc(prem)}${p.type === "put" ? ", collateral released" : ", shares unlocked"}` : `lose the ${mc(prem)} paid`}</td></tr>
      <tr><td class=l>${short ? (p.type === "put" ? "If assigned" : "If called away") : "If exercised"}</td><td>${short ? (p.type === "put" ? `buy ${p.open_qty * 100} TQQQ at ${kTxt(p.strike)} (${mc(p.collateral_c)})` : `sell ${p.open_qty * 100} shares at ${kTxt(p.strike)}`) : (p.type === "call" ? `buy ${p.open_qty * 100} shares at ${kTxt(p.strike)}` : `sell ${p.open_qty * 100} shares at ${kTxt(p.strike)}`)}</td></tr>
    </tbody></table>
    ${p.note ? `<div style="margin-top:10px;padding:8px 10px;border-radius:6px;background:var(--panel2);font-size:13px"><span class=meta>Your note</span><br><i>“${esc(p.note)}”</i></div>` : ""}
    ${short && p.type === "put" && p.dist < 0.03 ? `<div class="alert w" style="margin-top:10px"><span class=ic>${I("warn")}</span><span>${p.dist < 0 ? "In the money." : "Within 3% of the strike."}</span></div>` : ""}
    ${short ? posChances(p) : ""}
    <div id=posCone></div>
    ${readingsTable(p.readings)}
    <div class=actions style="justify-content:space-between"><button class=btn onclick="closeDrawer();go('pos:${p.id}')" data-tip="Portfolio, with this position highlighted">Show in Portfolio</button>
      <span style="display:flex;gap:8px">${short ? `<button class=btn onclick="openTicket({expiry:'${p.expiry}',strike:${p.strike},type:'${p.type}',action:'sell_to_open',from:${p.id}})">Sell more</button>` : ""}
      <button class="btn primary" onclick="openTicket({close:${p.id},from:${p.id}})">Close position…</button></span></div></div>`;
  api("cone", {id: p.id, days_back: 30}).then(d => { if ($("#posCone") && !tk) drawCone($("#posCone"), d, true); });
}

function storyPanel(p) {
  tk = null; document.body.classList.add("withDrawer");
  const short = p.side === "short", prem = p.premium_c, res = p.result_c;
  const tgs = p.tags.map(t => tagHtml(t)).join("");
  const back = p.bought_back.map(([q, px]) => `${q} @ ${f2(px)}`).join(", ");
  const tl = p.events.map(e => `<div><b>${esc(e.when)}</b> · ${esc(e.title)}<div class=meta>${esc(e.detail)}</div></div>`).join("");
  $("#drawer").innerHTML = `<div class=drawer>
    <div style="display:flex;justify-content:space-between"><b style="font-size:15px">Trade details</b><button class="btn small" onclick="closeDrawer()">Close <span class=kbd>Esc</span></button></div>
    <h3 style="margin:6px 0 2px;font-size:17px">${esc(p.label)}</h3>
    <div class=meta>${p.kind} · ${plural(p.qty, "contract")} · <span class=pill>${esc(p.outcome)}</span>${tgs ? " · " + tgs : ""}</div>
    <table class="mini story" style="margin-top:10px"><tbody>
      <tr><td class=l>Opened</td><td>${esc(p.opened_day)} · ${short ? "sold" : "bought"} at ${f2(p.open_price)} · <span class="${short ? "up" : "down"}">${mc(short ? prem : -prem, true)}</span></td></tr>
      ${back ? `<tr><td class=l>${short ? "Bought back" : "Sold"}</td><td>${esc(back)}</td></tr>` : ""}
      <tr><td class=l>Ended</td><td>${esc(p.ended_day || "—")} · ${esc(p.outcome.toLowerCase())}${p.settle_close ? ` · TQQQ closed ${f2(p.settle_close)}` : ""}</td></tr>
      <tr><td class=l>Days held</td><td>${p.days_held ?? "—"}</td></tr>
      <tr><td class=l>Result on the option</td><td class="${res >= 0 ? "up" : "down"}"><b>${mc(res, true)}</b>${prem && short ? ` <span class=meta>(${pct(res / prem, 0)} of premium kept)</span>` : ""}</td></tr>
      ${short && p.type === "put" ? `<tr><td class=l>Interest on its collateral (est.)</td><td class=up>${mc(p.interest_c, true)}</td></tr>` : ""}
    </tbody></table>
    ${p.note ? `<div style="margin-top:10px;padding:8px 10px;border-radius:6px;background:var(--panel2);font-size:13px"><span class=meta>Your note</span><br><i>“${esc(p.note)}”</i></div>` : ""}
    ${p.close_notes.length ? `<div style="margin-top:8px;padding:8px 10px;border-radius:6px;background:var(--panel2);font-size:13px"><span class=meta>Why you closed</span><br><i>${p.close_notes.map(n => "“" + esc(n) + "”").join("<br>")}</i></div>` : ""}
    ${readingsTable(p.readings)}
    <div class=meta style="margin:14px 0 4px">TIMELINE</div><div class=tl>${tl}</div>
    ${p.lot_id && p.status === "assigned" ? `<div class=actions style="justify-content:flex-start"><button class=btn onclick="closeDrawer();go('history:lot:${p.lot_id}')">Open the share lot it created</button></div>` : ""}</div>`;
}

/* ---------- indicator readings saved on trades ---------- */
const r0 = v => v == null ? "—" : Math.round(v);
const hasReadings = r => r && ["stoch14_k", "stoch30_k", "stoch60_k", "stoch180_k", "vix", "fg"].some(k => r[k] != null);
function posChances(p) {
  const c = p.chances, o = p.chances_open;
  if (!c) return "";
  const k = kTxt(p.strike), be = "$" + f2(c.breakeven), was = v => v == null ? "" : ` <span class=meta>· was ${chPct(v)}</span>`;
  const rows = p.type === "put" ? [
    ["Chance of expiring worthless", c.worthless, o && o.worthless, `% chance TQQQ closes above ${k} at expiration: the put expires and you keep the whole premium`],
    ["Chance of assignment", 1 - c.worthless, o && 1 - o.worthless, `% chance TQQQ closes below ${k} and you buy 100 shares per contract at ${k}`],
    [`Chance of touching ${k}`, c.touch, o && o.touch, `% chance TQQQ trades at or below ${k} at some point before expiration, even if it finishes above. Touching isn't assignment (that depends on the close), but it's when the position looks worst`],
    ["Chance of profit at expiration", c.profit, o && o.profit, `% chance TQQQ closes above ${be}, the breakeven (${k} strike − premium): either expiring worthless, or assigned with the drop smaller than the premium`],
  ] : [
    ["Chance of expiring worthless", c.worthless, o && o.worthless, `% chance TQQQ closes below ${k} at expiration: the call expires, your shares stay, you keep the whole premium`],
    ["Chance of being called away", 1 - c.worthless, o && 1 - o.worthless, `% chance TQQQ closes above ${k} and your 100 shares per contract are sold at ${k}`],
    [`Chance of touching ${k}`, c.touch, o && o.touch, `% chance TQQQ trades at or above ${k} at some point before expiration, even if it finishes below. Touching isn't being called away (that depends on the close), but it's when your shares look most likely to go`],
    ["Chance of profit at expiration", c.profit, o && o.profit, `% chance TQQQ closes below ${be} (${k} strike + premium), where the premium outweighs what selling at ${k} gives up`],
  ];
  return `<div class=meta style="margin:14px 0 4px">CHANCES NOW${o ? ` <span style="opacity:.8">· and when you opened it</span>` : ""}</div>
    <table class=mini><tbody>${rows.filter(r => r[1] != null).map(([lab, v, w, tip]) => `<tr data-tip="${esc(tip)}"><td class=l>${lab}</td><td><b>${/touching/.test(lab) ? touchTxt(c, p.type, p.strike) : chPct(v)}</b>${o ? was(w) : ""}</td></tr>`).join("")}</tbody></table>
    ${chBasis(c)}`;
}
function readingsLine(r, day) {
  if (!hasReadings(r)) return "";
  return `<div class="meta rd lnk" data-go="ind:${day}" data-tip="Double-click: Indicators on this date">${I("chart")} Stoch 14,3,3 ${r0(r.stoch14_k)}/${r0(r.stoch14_d)} · 30: ${r0(r.stoch30_k)} · 60: ${r0(r.stoch60_k)} · 180: ${r0(r.stoch180_k)} · VIX ${r.vix == null ? "—" : f2(r.vix)} · Fear & Greed ${r0(r.fg)}${r.fg_rating ? " " + esc(r.fg_rating) : ""}</div>`;
}
function readingsTable(list) {
  list = (list || []).filter(hasReadings);
  if (!list.length) return "";
  const rows = list.map(r => `<tr class=lnk data-go="ind:${r.day}" data-tip="Double-click: Indicators on this date"><td class=l>${esc(r.label)}<div class=meta>${esc(r.when)}</div></td><td>${r0(r.stoch14_k)}/${r0(r.stoch14_d)}</td><td>${r0(r.stoch30_k)}</td><td>${r0(r.stoch60_k)}</td><td>${r0(r.stoch180_k)}</td><td>${r.vix == null ? "—" : f2(r.vix)}</td><td>${r0(r.fg)}<div class=meta>${esc(r.fg_rating || "")}</div></td></tr>`).join("");
  return `<div class=meta style="margin:14px 0 4px">MARKET AT EACH TRADE <span class="lnk helplink" onclick="go('ind')" style="margin-left:6px">Indicators ↗</span></div>
    <table class="mini rdt"><thead><tr><th class=l></th><th>Stoch 14,3,3</th><th>30</th><th>60</th><th>180</th><th>VIX</th><th>F&amp;G</th></tr></thead><tbody>${rows}</tbody></table>`;
}

/* ---------- PAYOFF CHART + PROBABILITY CONES (v1.10.0) ---------- */
const jsN = x => { const t = 1 / (1 + 0.2316419 * Math.abs(x)), d = 0.3989423 * Math.exp(-x * x / 2),
  p = d * t * (0.3193815 + t * (-0.3565638 + t * (1.781478 + t * (-1.821256 + t * 1.330274)))); return x > 0 ? 1 - p : p; };
function bsVal(type, S, K, T, r, v) {
  if (T <= 0 || v <= 0) return Math.max(0, type === "call" ? S - K : K - S);
  const d1 = (Math.log(S / K) + (r + v * v / 2) * T) / (v * Math.sqrt(T)), d2 = d1 - v * Math.sqrt(T);
  return type === "call" ? S * jsN(d1) - K * Math.exp(-r * T) * jsN(d2) : K * Math.exp(-r * T) * jsN(-d2) - S * jsN(-d1);
}
const usd0 = v => (v < 0 ? "−" : v > 0 ? "+" : "") + "$" + Math.abs(Math.round(v)).toLocaleString("en-US");

/* P&L at expiration, halfway and today across a range of TQQQ prices. Covered calls include the covering shares,
   valued from today's price, so the curve is the position you actually hold. */
function drawPayoff(el, pf) {
  if (!el || !pf) return;
  const {type, strike: K, premium: P, qty, S: S0, iv, dte, rate: r} = pf, m = 100 * (qty || 1), T = Math.max(dte, 0.5) / 365;
  const sd = iv * Math.sqrt(T), lo = Math.max(0.01, Math.min(S0 * Math.exp(-2.4 * sd), K * 0.92)), hi = Math.max(S0 * Math.exp(1.4 * sd), K * 1.08);
  const opt = (s, t) => bsVal(type, s, K, t, r, iv);
  const pnl = (s, t) => (P - opt(s, t)) * m + (pf.covered ? (s - S0) * m : 0);
  const N = 120, xs = Array.from({length: N + 1}, (_, i) => lo + (hi - lo) * i / N);
  const cur = [[0, "exp", "at expiration"], [T / 2, "mid", `in ${plural(Math.round(dte / 2), "day")}`], [T, "now", "today"]]
    .map(([t, k, l]) => ({k, l, y: xs.map(s => pnl(s, t))}));
  const all = cur.flatMap(c => c.y), y0 = Math.min(...all), y1 = Math.max(...all), pad = (y1 - y0) * 0.08 || 50;
  const W = 420, H = 210, L = 52, R = 10, Tp = 16, B = 26;
  const X = s => L + (s - lo) / (hi - lo) * (W - L - R), Y = v => Tp + (y1 + pad - v) / (y1 - y0 + 2 * pad) * (H - Tp - B);
  const be = pf.covered ? S0 - P : type === "put" ? K - P : K + P, maxP = pf.covered ? (K - S0 + P) * m : P * m;
  const path = ys => "M" + ys.map((v, i) => `${X(xs[i]).toFixed(1)},${Y(v).toFixed(1)}`).join("L");
  const ticks = niceTicks(y0 - pad, y1 + pad, 4).filter(v => Y(v) > Tp - 2 && Y(v) < H - B + 2);
  const xt = niceTicks(lo, hi, 5).filter(v => v >= lo && v <= hi);
  const vline = (x, c, lab, yy, anchor = "start") => `<line x1=${X(x)} x2=${X(x)} y1=${Tp} y2=${H - B} stroke="${c}" stroke-width=1 stroke-dasharray="3 3"/>` +
    `<text x=${X(x) + (anchor === "end" ? -4 : 4)} y=${yy} fill="${c}" font-size=10.5 text-anchor=${anchor}>${lab}</text>`;
  const svg = `<svg viewBox="0 0 ${W} ${H}" width="100%" class=pfsvg>
    ${ticks.map(v => `<line x1=${L} x2=${W - R} y1=${Y(v)} y2=${Y(v)} stroke="var(--line)" stroke-width="${v === 0 ? 1.2 : 0.6}"/><text x=${L - 6} y=${Y(v) + 3.5} fill="var(--dim)" font-size=10 text-anchor=end>${usd0(v)}</text>`).join("")}
    ${xt.map(v => `<text x=${X(v)} y=${H - 8} fill="var(--dim)" font-size=10 text-anchor=middle>$${v}</text>`).join("")}
    <path d="${path(cur[2].y)}" fill=none stroke="var(--dim)" stroke-width=1.3 stroke-dasharray="4 3"/>
    <path d="${path(cur[1].y)}" fill=none stroke="var(--accent)" stroke-width=1.3 stroke-dasharray="1.5 2.5"/>
    <path d="${path(cur[0].y)}" fill=none stroke="var(--up)" stroke-width="2"/>
    ${vline(be, "var(--warn)", `breakeven $${f2(be)}`, Tp + 10, be > S0 ? "start" : "end")}
    ${vline(S0, "var(--text)", `TQQQ $${f2(S0)}`, Tp + 24, S0 >= be ? "start" : "end")}
    ${Math.abs(X(K) - X(S0)) > 4 ? `<line x1=${X(K)} x2=${X(K)} y1=${Tp} y2=${H - B} stroke="var(--dim)" stroke-width=".7"/>` : ""}
    <text x=${W - R} y=${Y(maxP) - 5} fill="var(--up)" font-size=10.5 text-anchor=end>max ${usd0(maxP)}</text>
    <line class=pfx x1=0 x2=0 y1=${Tp} y2=${H - B} stroke="var(--dim)" style="display:none"/></svg>`;
  el.innerHTML = `<div class=meta style="margin:12px 0 4px">PAYOFF${pf.covered ? ` <span style="opacity:.8">· your shares (from today's $${f2(S0)}) + this call</span>` : ""}</div>${svg}
    <div class=pfread>${pfLegend()}</div>`;
  const s = el.querySelector("svg"), read = el.querySelector(".pfread"), xh = el.querySelector(".pfx");
  s.addEventListener("mousemove", e => { const b = s.getBoundingClientRect(), px = (e.clientX - b.left) * W / b.width;
    if (px < L || px > W - R) return; const sx = lo + (px - L) / (W - L - R) * (hi - lo);
    xh.setAttribute("x1", px); xh.setAttribute("x2", px); xh.style.display = "";
    read.innerHTML = `TQQQ at <b>$${f2(sx)}</b> · at expiration <b class="${pnl(sx, 0) >= 0 ? "up" : "down"}">${usd0(pnl(sx, 0))}</b> · today <b class="${pnl(sx, T) >= 0 ? "up" : "down"}">${usd0(pnl(sx, T))}</b>`; });
  s.addEventListener("mouseleave", () => { xh.style.display = "none"; read.innerHTML = pfLegend(); });
  function pfLegend() { return `<span class=up>━</span> at expiration · <span style="color:var(--accent)">┈</span> in ${plural(Math.round(dte / 2), "day")} · <span style="color:var(--dim)">╌</span> today · hover for values · IV ${(iv * 100).toFixed(0)}%`; }
}

/* A cone of where TQQQ could be, from today out to the latest expiration: the inner band holds about 68% of the
   outcomes its IV implies, the outer about 95%. Open options are drawn as their strike, from today to expiry. */
function drawCone(el, d, mini) {
  if (!el || !d || d.error) { if (el) el.innerHTML = ""; return; }
  const day = s => new Date(s + "T12:00:00").getTime() / 864e5, t0 = day(d.today);
  const hist = d.closes.map(([dd, c]) => [day(dd), c]);
  const end = t0 + Math.max(d.horizon, mini ? 2 : 7), x0 = hist.length ? hist[0][0] : t0 - 30;
  const v = d.iv, mu = d.rate - v * v / 2, S0 = d.price;
  const band = (t, k) => { const yr = Math.max(t - t0, 0) / 365; return S0 * Math.exp(mu * yr + k * v * Math.sqrt(yr)); };
  const tsF = Array.from({length: 41}, (_, i) => t0 + (end - t0) * i / 40);
  const ys = [...hist.map(h => h[1]), band(end, -2), band(end, 2), ...d.positions.map(p => p.strike)];
  let ylo = Math.min(...ys), yhi = Math.max(...ys); const pd = (yhi - ylo) * 0.06; ylo -= pd; yhi += pd;
  const W = mini ? 420 : 1100, H = mini ? 190 : 300, L = 44, R = mini ? 96 : 190, Tp = 12, B = 24;
  // the past gets a fixed share of the width, so a short horizon isn't squeezed by months of history
  const fp = mini ? 0.42 : 0.5, xm = L + fp * (W - L - R);
  const X = t => t <= t0 ? L + (t - x0) / Math.max(t0 - x0, 1) * (xm - L) : xm + (t - t0) / Math.max(end - t0, 1) * (W - R - xm);
  const Xinv = px => px <= xm ? x0 + (px - L) / (xm - L) * (t0 - x0) : t0 + (px - xm) / (W - R - xm) * (end - t0);
  const Y = p => Tp + (yhi - p) / (yhi - ylo) * (H - Tp - B);
  const area = k => `M${tsF.map(t => `${X(t).toFixed(1)},${Y(band(t, k)).toFixed(1)}`).join("L")}L${tsF.slice().reverse().map(t => `${X(t).toFixed(1)},${Y(band(t, -k)).toFixed(1)}`).join("L")}Z`;
  const yt = niceTicks(ylo, yhi, mini ? 4 : 6).filter(p => p >= ylo && p <= yhi);
  const lbl = t => new Date(t * 864e5).toLocaleDateString("en-US", {month: "short", day: "numeric"});
  const xt = mini ? [x0, t0, end] : [x0, (x0 + t0) / 2, t0, (t0 + end) / 2, end];
  let strikes = "", used = [];
  d.positions.slice().sort((a, b) => a.strike - b.strike).forEach(p => {
    const c = p.type === "put" ? "var(--warn)" : "var(--up)", xe = X(day(p.expiry)), y = Y(p.strike);
    let ly = y + 3.5; while (used.some(u => Math.abs(u - ly) < 12)) ly -= 12; used.push(ly);
    strikes += `<line x1=${mini ? L : X(t0)} x2=${xe} y1=${y} y2=${y} stroke="${c}" stroke-width=1.4 stroke-dasharray="${mini ? "4 3" : ""}"/>
      <circle cx=${xe} cy=${y} r=3 fill="${c}"/><text x=${xe + 6} y=${ly} fill="${c}" font-size=10.5>${mini ? kTxt(p.strike) + " strike" : esc(p.label) + " ×" + p.qty}</text>`;
  });
  const svg = `<svg viewBox="0 0 ${W} ${H}" width="100%">
    ${yt.map(p => `<line x1=${L} x2=${W - R} y1=${Y(p)} y2=${Y(p)} stroke="var(--line)" stroke-width=".6"/><text x=${L - 6} y=${Y(p) + 3.5} fill="var(--dim)" font-size=10 text-anchor=end>$${p}</text>`).join("")}
    ${xt.map(t => `<text x=${X(t)} y=${H - 7} fill="var(--dim)" font-size=10 text-anchor=${t === x0 ? "start" : t === end ? "end" : "middle"}>${t === t0 ? "today" : lbl(t)}</text>`).join("")}
    <path d="${area(2)}" fill="var(--accent)" fill-opacity=".10"/><path d="${area(1)}" fill="var(--accent)" fill-opacity=".18"/>
    <line x1=${X(t0)} x2=${X(t0)} y1=${Tp} y2=${H - B} stroke="var(--line)"/>
    <path d="M${hist.map(([t, c]) => `${X(t).toFixed(1)},${Y(c).toFixed(1)}`).join("L")}" fill=none stroke="var(--text)" stroke-width="1.5"/>
    ${strikes}
    <line class=cnx x1=0 x2=0 y1=${Tp} y2=${H - B} stroke="var(--dim)" style="display:none"/></svg>`;
  const foot = `Shaded: where TQQQ would be about 68% (inner) and 95% (outer) of the time if it moves as its implied volatility says (IV ${(v * 100).toFixed(0)}%, ${esc(d.iv_src)}). Says nothing about direction; not a forecast.`;
  el.innerHTML = `${mini ? `<div class=meta style="margin:14px 0 4px">WHERE TQQQ COULD BE BY EXPIRATION</div>` : ""}${svg}<div class="meta cnread" style="min-height:17px">${coneSum()}</div><div class=meta style="font-size:11px">${foot}</div>`;
  const s = el.querySelector("svg"), read = el.querySelector(".cnread"), xh = el.querySelector(".cnx");
  function coneSum() { if (!d.positions.length) return "No open options: the cone shows TQQQ's likely range over the next month.";
    const p = d.positions.reduce((a, b) => b.dte > a.dte ? b : a); const t = day(p.expiry);
    return `By ${lbl(t)}: ${"$" + f2(band(t, -1))}–${"$" + f2(band(t, 1))} (68%) · ${"$" + f2(band(t, -2))}–${"$" + f2(band(t, 2))} (95%)`; }
  s.addEventListener("mousemove", e => { const b = s.getBoundingClientRect(), px = (e.clientX - b.left) * W / b.width;
    if (px < L || px > W - R) return; const t = Xinv(px);
    xh.setAttribute("x1", px); xh.setAttribute("x2", px); xh.style.display = "";
    if (t <= t0) { const h = hist.reduce((a, b) => Math.abs(b[0] - t) < Math.abs(a[0] - t) ? b : a, hist[0] || [t0, S0]);
      read.innerHTML = `${lbl(h[0])} · TQQQ closed <b>$${f2(h[1])}</b>`; }
    else read.innerHTML = `${lbl(t)} · 68%: <b>$${f2(band(t, -1))}–$${f2(band(t, 1))}</b> · 95%: $${f2(band(t, -2))}–$${f2(band(t, 2))}`; });
  s.addEventListener("mouseleave", () => { xh.style.display = "none"; read.innerHTML = coneSum(); });
}

/* ---------- CONFIRM ---------- */
function closeOverlay() { $("#overlay").innerHTML = ""; }
async function showConfirm() {
  const shown = tkData.quote ? {bid: tkData.quote.bid, ask: tkData.quote.ask} : null;
  $("#reviewBtn").disabled = true; $("#reviewBtn").innerHTML = `<span class=spin>${I("spin")}</span> Re-quoting…`;
  const r = await api("review", {order: tk, shown});
  if (r.error) { toast(esc(r.error)); renderTicket(); return; }
  const q = r.quote, ef = r.effects || {}, o = r.order, isShares = o.action.endsWith("shares");
  let lines = `<div class=row><label>Quantity</label><span>${isShares ? plural(o.qty, "share") : plural(o.qty, "contract")}</span></div>
    <div class=row><label>Fill price</label><span><b>${f2(o.price)}</b> <span class=meta>(bid ${f2(q.bid)} / ask ${f2(q.ask)}${r.stale ? " · close quote, stale" : " · " + esc(r.quote_txt)})</span></span></div>`;
  if (r.moved) lines += `<div class="alert w" style="margin:8px 0"><span class=ic>${I("warn")}</span><span>The quote moved since the ticket opened (was ${f2(shown.bid)} / ${f2(shown.ask)}).${r.ok ? "" : " Your fill price is outside the new range; go back and adjust it."}</span></div>`;
  if (o.action === "sell_to_open") {
    lines += `<div class=row><label>Premium in</label><span><span class=up>${mc(ef.premium_c, true)}</span> → Available</span></div>`;
    if (ef.collateral_c) lines += `<div class=row><label>Collateral set aside</label><span>${mc(ef.collateral_c)} from Available</span></div>`;
    if (ef.locks_shares) lines += `<div class=row><label>Shares locked</label><span>${ef.locks_shares} TQQQ as cover</span></div>`;
  } else if (o.action === "buy_to_close") {
    lines += `<div class=row><label>Cost out</label><span><span class=down>${mc(-ef.cost_c)}</span>${ef.collateral_released_c ? " from this position's collateral" : " from Available"}</span></div>`;
    if (ef.collateral_released_c) lines += `<div class=row><label>Collateral released</label><span>${mc(ef.collateral_released_c)} − ${mc(ef.cost_c)} = <b>${mc(ef.collateral_released_c - ef.cost_c)}</b> → Available</span></div>`;
    if (ef.unlocks_shares) lines += `<div class=row><label>Shares unlocked</label><span>${ef.unlocks_shares}</span></div>`;
  } else if (ef.proceeds_c != null) lines += `<div class=row><label>Proceeds</label><span class=up>${mc(ef.proceeds_c, true)} → Available</span></div>`;
  else if (ef.cost_c != null) lines += `<div class=row><label>Cost</label><span class=down>${mc(-ef.cost_c)} from Available</span></div>`;
  if (ef.result_c != null && r.position) lines += `<div class=row><label>Result on these contracts</label><span>Opened ${f2(r.position.open_price)}, closing ${f2(o.price)} · <span class="${ef.result_c >= 0 ? "up" : "down"}">${mc(ef.result_c, true)}</span></span></div>`;
  if (ef.available_before_c != null && ef.available_after_c != null) lines += `<div class=row><label>Available</label><span>${mc(ef.available_before_c)} → <b>${mc(ef.available_after_c)}</b></span></div>`;
  if (!o.position_id && (o.note || o.tags.length)) lines += `<div class=row><label>Journal</label><span>${esc(o.note)} ${o.tags.map(t => `<span class=tag>${esc(t)}</span>`).join("")}</span></div>`;
  if (r.warn) lines += `<div class="alert w" style="margin:8px 0"><span class=ic>${I("warn")}</span><span>${esc(r.warn)}</span></div>`;
  if (o.position_id) lines += `<div class=meta style="margin:10px 0 4px">Why I closed (optional)</div><input id=whyClosed style="width:100%" placeholder="e.g. took 70% of max profit">`;
  $("#overlay").innerHTML = `<div class=scrim><div class=modal><div class=meta>CONFIRM TRADE · re-quoted just now</div>
    <h3>${esc(r.title)}</h3>${lines}
    <div class="${r.ok ? "ok" : "err"}">${r.ok ? I("check") : I("x")} ${esc(r.msg)}</div>
    <div class=actions><button class=btn onclick="closeOverlay();loadTicket(false)">Cancel <span class=kbd>Esc</span></button><button class="btn primary" id=confirmBtn ${r.ok ? "" : "disabled"}>Confirm <span class=kbd style="color:#fff">Enter</span></button></div></div></div>`;
  renderTicket();
  $("#confirmBtn").onclick = async () => {
    $("#confirmBtn").disabled = true;
    const why = ($("#whyClosed") || {}).value || "";
    const res = await api("place", {order: {...tk, close_note: why}});
    if (res.error) { closeOverlay(); toast(`${I("x")} ${esc(res.error)}`, 6000); loadTicket(true); return; }
    closeOverlay(); closeDrawer(); toast(`${I("check")} Paper trade placed. It's in Portfolio and History.`); reload();
  };
}

/* ---------- HISTORY ---------- */
async function renderHistory() {
  const h = await api("history", {filter: ui.hFilter, tag: ui.hTag, day: ui.hDay});
  const list = h.events;
  const colors = {Error: "var(--down)", Warning: "var(--warn)", Trade: "var(--s1)", Shares: "var(--s1)", Expired: "var(--warn)", Assigned: "var(--warn)", "Called away": "var(--warn)", Exercised: "var(--warn)", Interest: "var(--up)", Dividend: "var(--up)"};
  const rows = list.map(e => {
    const isErr = e.err || e.warn, open = isErr && (ui.hExpand === "all" || ui.hExpand === e.id);
    const flash = (ui.lot && e.lot_id === ui.lot && (ui.lotEvent ? e.id === ui.lotEvent : e.share_event)) || (ui.hExpand === "all" && isErr) || ui.hEvent === e.id ? "flash" : "";
    const exp = open && e.data.what ? `<div class=errbox><b>What happened:</b> ${esc(e.data.what)}<br><b>What the app did:</b> ${esc(e.data.did)}<br><b>What you can do:</b> ${esc(e.data.todo)}${e.data.log ? ` Technical details: ${esc(e.data.log)}` : ""}</div>` : "";
    return `<tr class="${flash} ${isErr ? "click" : ""}" ${isErr ? `data-exp="${e.id}"` : ""} ${e.share_event ? `data-go="history:lot:${e.lot_id}:${e.id}" data-tip="Double-click: open the share lot"` : e.position_id ? `data-go="poshist:${e.position_id}" data-tip="Double-click: trade details"` : ""}><td class=l style="width:190px">${esc(e.d)} CT<div class=meta>(${esc(e.et)} ET)</div></td>
      <td class=l style="width:105px"><span class=pill style="color:${colors[e.kind] || "var(--dim)"};border-color:${colors[e.kind] || "var(--line)"}">${esc(e.kind)}</span></td>
      <td class=l style="white-space:normal"><b>${esc(e.title)}</b> ${e.tags.map(t => tagHtml(t, "Double-click: filter to " + esc(t))).join("")}
      ${e.share_event ? `<button class="chip" style="margin-left:4px" data-chart="${e.day}">${I("chart")} Show on chart</button>` : ""}
      <div class=meta style="font-size:12.5px">${esc(e.detail)}</div>${readingsLine(e.readings, e.day)}${exp}</td></tr>`; }).join("") || `<tr><td class="l meta" style="padding:16px 8px">Nothing matches this filter.</td></tr>`;
  const dayLbl = ui.hDay ? new Date(ui.hDay + "T12:00:00").toLocaleDateString("en-US", {weekday: "short", month: "short", day: "numeric"}) : "";
  const bar = ui.hDay ? `<div class=arrive><span><b>Showing ${esc(dayLbl)}</b> <span class=meta>· ${plural(list.length, "event")}</span></span><button class=chip style="margin-left:auto" id=clrDay>Clear ${I("x")}</button></div>` : ui.hTag ? `<div class=arrive><span><b>Showing events tagged ${esc(ui.hTag)}</b> <span class=meta>· ${list.length} of ${h.total} events</span></span><button class=chip style="margin-left:auto" id=clrTag>Clear ${I("x")}</button></div>`
    : ui.hFilter === "Errors" ? `<div class=arrive><span><b>Showing errors and warnings</b> <span class=meta>· ${plural(list.length, "event")}</span></span><button class=chip style="margin-left:auto" id=clrErr>Clear ${I("x")}</button></div>` : "";
  const segs = ["All", "Trades", "Expirations & Assignments", "Interest", "Errors"].map(x => `<button class="btn ${ui.hFilter === x ? "on" : ""}" data-hf="${x}">${x}${x === "Errors" && st.errors ? ` <span style="color:var(--down)">${I("dot")}</span>` : ""}</button>`).join("");
  const lot = ui.lot ? await lotPanel(ui.lot) : "";
  $("#main").innerHTML = `<div style="${ui.lot ? "margin-right:440px" : ""}">${bar}<div class=bar><span class=seg>${segs}</span>
    <select id=tagSel><option value="">Any tag</option>${h.tags.map(t => `<option ${t === ui.hTag ? "selected" : ""}>${esc(t)}</option>`).join("")}</select>
    <button class=btn style="margin-left:auto" id=csvBtn>${I("down")} Export CSV</button></div>
    <div class=meta style="margin:-4px 0 8px">Click an error to expand it · double-click a trade for its details, or a share event for the lot's story</div>
    <table><tbody>${rows}</tbody></table></div>${lot}`;
  $$("[data-hf]").forEach(b => b.onclick = () => { ui.hFilter = b.dataset.hf; ui.hExpand = b.dataset.hf === "Errors" ? "all" : null; if (b.dataset.hf === "Errors") ui.hTag = null; render(); });
  $$("[data-exp]").forEach(r => r.onclick = () => { const id = +r.dataset.exp; ui.hExpand = ui.hExpand === id || ui.hExpand === "all" ? null : id; render(); });
  $$("[data-chart]").forEach(b => b.onclick = e => { e.stopPropagation(); go("perf:" + b.dataset.chart); });
  $("#tagSel").onchange = e => { ui.hTag = e.target.value || null; render(); };
  if ($("#clrTag")) $("#clrTag").onclick = () => { ui.hTag = null; render(); };
  if ($("#clrDay")) $("#clrDay").onclick = () => { ui.hDay = null; render(); };
  if ($("#clrErr")) $("#clrErr").onclick = () => { ui.hFilter = "All"; ui.hExpand = null; render(); };
  $("#csvBtn").onclick = async () => { const r = await api("history_csv"); if (r.ok) toast(`${I("check")} Saved ${esc(r.path)}`); else if (r.error) toast(esc(r.error)); };
}
async function lotPanel(id) {
  const s = await api("lot", {id});
  if (s.error) return "";
  const L = s.lot;
  const tl = s.timeline.map(t => `<div><b>${esc(t.when)}</b> · ${esc(t.text)} ${t.amt_c ? `<span class=up>${mc(t.amt_c, true)}</span>` : ""}${t.note ? `<div class=meta>“${esc(t.note)}”</div>` : ""}</div>`).join("");
  const now = s.held ? `<div><b>Now</b> · Still held at $${f2(s.today.price)}<div class=meta>${s.open_calls.length ? esc(s.open_calls.join(", ")) + " open" : "not covered"}</div></div>` : "";
  return `<div class=side><div style="display:flex;justify-content:space-between"><b style="font-size:15px">Share lot: ${L.qty} TQQQ</b><button class="btn small" onclick="ui.lot=null;render()">Close <span class=kbd>Esc</span></button></div>
  <div class=meta>${L.source === "assigned" ? "Assigned" : L.source[0].toUpperCase() + L.source.slice(1)} ${esc(L.acquired)} · ${s.held ? "still held" : "closed"}${s.tags.length ? " · tags " + s.tags.map(t => tagHtml(t)).join("") : ""}</div>
  <div class=tl>${tl}${now}</div>
  <table class=mini><tbody><tr><td class=l>Premium from this lot</td><td class="${s.premium_c >= 0 ? "up" : "down"}">${mc(s.premium_c, true)}</td></tr><tr><td class=l>Interest on its collateral (est.)</td><td class=up>${mc(s.interest_c, true)}</td></tr>
  <tr><td class=l>Shares vs. $${f2(L.cost)} cost</td><td class="${s.shares_c >= 0 ? "up" : "down"}">${mc(s.shares_c, true)}</td></tr><tr><td class=l><b>Net so far</b></td><td class="${s.net_c >= 0 ? "up" : "down"}"><b>${mc(s.net_c, true)}</b></td></tr></tbody></table>
  <div class=actions style="justify-content:flex-start"><button class=btn onclick="go('perf:${L.acquired_day}')">${I("chart")} Show on chart</button></div></div>`;
}

/* ---------- PERFORMANCE ---------- */
function niceStep(range, target) { const raw = range / target, mag = Math.pow(10, Math.floor(Math.log10(raw))); const n = raw / mag; return (n < 1.5 ? 1 : n < 3 ? 2 : n < 7 ? 5 : 10) * mag; }
async function renderPerf() {
  const p = await api("performance");
  if (p.empty || p.error) { $("#main").innerHTML = `<div class=empty>${esc(p.error || "Start a run to see performance.")}</div>`; return; }
  const sm = p.summary, N = p.days.length;
  const cardsH = `<div class=cards style="grid-template-columns:repeat(auto-fit,minmax(230px,1fr))">
    <div class=card><small>Ghost Trader (this run)</small><span class="big ${sm.ret >= 0 ? "up" : "down"}">${sm.ret >= 0 ? "+" : ""}${pct(sm.ret, 2)}</span><div class=meta>${sm.ann >= 0 ? "+" : ""}${pct(sm.ann)} annualized · ${money(sm.value)}</div></div>
    <div class=card><small>TQQQ buy & hold, same dates</small><span class="big ${sm.bh_ret >= 0 ? "up" : "down"}">${sm.bh_ret == null ? "—" : (sm.bh_ret >= 0 ? "+" : "") + pct(sm.bh_ret, 2)}</span><div class=meta>${sm.bh_value ? money(sm.bh_value) : "—"}${p.entry ? ` · bought at ${f2(p.entry)} ${esc(p.labels[0] || "")}` : ""}</div></div>
    <div class=card><small>T-bills (cash only)</small><span class="big up">+${pct(sm.tb_ret, 2)}</span><div class=meta>${money(sm.tb_value)}</div></div>
    <div class=card><small>vs. benchmarks</small><span class=big>${sm.bh_ret == null ? "—" : ((sm.ret - sm.bh_ret) * 100 >= 0 ? "+" : "") + ((sm.ret - sm.bh_ret) * 100).toFixed(2)} / ${((sm.ret - sm.tb_ret) * 100 >= 0 ? "+" : "") + ((sm.ret - sm.tb_ret) * 100).toFixed(2)} pts</span><div class=meta>vs. TQQQ / vs. T-bills</div></div></div>`;
  const bars = monthBars(p);
  if (N < 2) {
    $("#main").innerHTML = `${cardsH}<div style="display:flex;gap:16px;flex-wrap:wrap"><div class=card style="flex:1;min-width:0"><b>Account value</b><div class=empty>The charts fill in as days go by: one point for each day the app is opened (missed days are estimated from TQQQ's daily closes).</div></div>${bars}</div><div id=outcomes></div>`;
    renderOutcomes();
    return;
  }
  const {acct, bh, tb, tqqq: tq, est} = p;
  const W = 860, H = 250, H2 = 200, L = 70, T = 16, Rr = 120, B = 30;
  const all = acct.concat(bh.filter(x => x != null), tb), lo0 = Math.min(...all), hi0 = Math.max(...all), pad = Math.max((hi0 - lo0) * .08, 50);
  const lo = lo0 - pad, hi = hi0 + pad, step = niceStep(hi - lo, 5);
  const X = i => L + (W - L - Rr) * i / (N - 1), Y = v => T + (H - T - B) * (hi - v) / (hi - lo);
  const tqv = tq.filter(x => x != null), plo = Math.min(...tqv), phi = Math.max(...tqv), ppad = Math.max((phi - plo) * .1, .5), plo2 = plo - ppad, phi2 = phi + ppad, pstep = niceStep(phi2 - plo2, 4);
  const Y2 = v => T + (H2 - T - B) * (phi2 - v) / (phi2 - plo2);
  const path = (v, y) => { let s = "", pen = false; v.forEach((x, i) => { if (x == null) { pen = false; return; } s += (pen ? " L" : " M") + X(i).toFixed(1) + "," + y(x).toFixed(1); pen = true; }); return s; };
  const kfmt = v => Math.abs(hi - lo) < 20000 ? "$" + (v / 1000).toFixed(1) + "k" : "$" + Math.round(v / 1000) + "k";
  let g1 = ""; for (let v = Math.ceil(lo / step) * step; v < hi; v += step) g1 += `<line x1=${L} x2=${W - Rr} y1=${Y(v)} y2=${Y(v)} stroke="var(--line)"/><text x=${L - 8} y=${Y(v) + 4} fill="var(--dim)" font-size=11 text-anchor=end>${kfmt(v)}</text>`;
  let g2 = ""; for (let v = Math.ceil(plo2 / pstep) * pstep; v < phi2; v += pstep) g2 += `<line x1=${L} x2=${W - Rr} y1=${Y2(v)} y2=${Y2(v)} stroke="var(--line)"/><text x=${L - 8} y=${Y2(v) + 4} fill="var(--dim)" font-size=11 text-anchor=end>$${v.toFixed(pstep < 1 ? 1 : 0)}</text>`;
  const ticks = [...new Set([0, Math.round((N - 1) / 3), Math.round(2 * (N - 1) / 3), N - 1])];
  const xt = h => ticks.map(i => `<text x=${X(i)} y=${h - 8} fill="var(--dim)" font-size=11 text-anchor=middle>${esc(p.labels[i])}</text>`).join("");
  const idxOf = day => { let j = 0; p.days.forEach((d, i) => { if (d <= day) j = i; }); return j; };
  const band = h => ui.perfDay ? `<rect x=${X(idxOf(ui.perfDay)) - 7} y=${T} width=14 height=${h - T - B} fill="var(--warn)" opacity=.18 />` : "";
  const mks = p.markers.map((m, j) => ({...m, i: idxOf(m.day), j}));
  const dia = (m, y, sel) => `${sel ? `<circle cx=${X(m.i)} cy=${y} r=12 fill=none stroke="var(--warn)" stroke-width=1.5 stroke-dasharray="2 2"/>` : ""}<path class=mk data-j="${m.j}" d="M${X(m.i)},${y - 7} L${X(m.i) + 7},${y} L${X(m.i)},${y + 7} L${X(m.i) - 7},${y} Z" fill="var(--warn)" stroke="var(--panel)" stroke-width=2 style="cursor:pointer" data-go="history:lot:${m.lot_id}:${m.event_id || ""}"/>`;
  const lab = (y, c, t) => `<circle cx=${W - Rr + 12} cy=${y} r=4 fill="${c}"/><text x=${W - Rr + 20} y=${y + 4} fill="var(--text)" font-size=12>${t}</text>`;
  const pts = acct.map((a, i) => est[i] ? `<circle cx=${X(i)} cy=${Y(a)} r=3 fill="var(--panel)" stroke="var(--s1)" stroke-width=1.5 />` : "").join("");
  const ends = [[acct[N - 1], "var(--s1)", "Ghost Trader"], [tb[N - 1], "var(--s3)", "T-bills"], [bh[N - 1], "var(--s2)", "TQQQ hold"]].filter(x => x[0] != null).map(x => [Y(x[0]), x[1], x[2]]).sort((a, b) => a[0] - b[0]);
  for (let i = 1; i < ends.length; i++) if (ends[i][0] - ends[i - 1][0] < 15) ends[i][0] = ends[i - 1][0] + 15;
  const mlines = (h, y) => mks.map(m => `<line x1=${X(m.i)} x2=${X(m.i)} y1=${T} y2=${h - B} stroke="var(--warn)" stroke-dasharray="2 4"/>`).join("");
  const svg1 = `<svg id=c1 width=${W} height=${H} style="display:block;max-width:100%">${band(H)}${g1}${xt(H)}
    <path d="${path(tb, Y)}" fill=none stroke="var(--s3)" stroke-width=2 /><path d="${path(bh, Y)}" fill=none stroke="var(--s2)" stroke-width=2 /><path d="${path(acct, Y)}" fill=none stroke="var(--s1)" stroke-width=2.5 />${pts}
    ${mlines(H)}${mks.map(m => dia(m, Y(acct[m.i]), false)).join("")}
    ${ends.map(([v, c, t]) => lab(v, c, t)).join("")}<g id=x1></g>
    <rect id=hit1 x=${L} y=${T} width=${W - L - Rr} height=${H - T - B} fill=transparent style="pointer-events:none" /></svg>`;
  const svg2 = `<svg id=c2 width=${W} height=${H2} style="display:block;max-width:100%">${band(H2)}${g2}${xt(H2)}<path d="${path(tq, Y2)}" fill=none stroke="var(--s2)" stroke-width=2 />
    <circle cx=${X(0)} cy=${Y2(tq[0])} r=4 fill="var(--s2)"/><text x=${X(0) + 8} y=${Y2(tq[0]) - 8} font-size=12 fill="var(--text)">$${f2(tq[0])}</text>
    <circle cx=${X(N - 1)} cy=${Y2(tq[N - 1])} r=4 fill="var(--s2)"/><text x=${W - Rr + 8} y=${Y2(tq[N - 1]) + 4} font-size=12 fill="var(--text)">$${f2(tq[N - 1])} (${tq[N - 1] >= tq[0] ? "+" : "−"}${Math.abs((tq[N - 1] / tq[0] - 1) * 100).toFixed(2)}%)</text>
    ${mlines(H2)}${mks.map(m => `<text x=${X(m.i) + 10} y=${H2 - B - 6} font-size=11 fill="var(--warn)">${esc(m.label)}</text>`).join("")}<g id=x2></g>
    ${mks.map(m => dia(m, Y2(tq[m.i]), ui.pin === m.j)).join("")}</svg>`;
  let pin = "";
  if (ui.pin != null && mks[ui.pin]) { const m = mks[ui.pin], s = m.story || {};
    pin = `<div class=pin style="left:${Math.min(X(m.i) + 22, W - 390)}px;top:8px"><div style="display:flex;justify-content:space-between;align-items:center"><b>${I("pin")} ${esc(m.label)} · ${esc(m.when)}</b><span class=meta style="cursor:pointer" id=pinX>${I("x")}</span></div>
    <div class=row><span class=meta>Got in?</span><span>${esc(s.got_in || "")}</span></div>
    <div class=row><span class=meta>Got out?</span><span>${s.held ? "<b>Not yet</b> · " + esc((s.got_out || "").replace(/^Not yet · /, "")) : esc(s.got_out || "")}</span></div>
    <div class=row><span class=meta>Today</span><span>$${f2(S())}${s.held && s.today ? ` · <span class="${s.today.pnl_c >= 0 ? "up" : "down"}">${mc(s.today.pnl_c, true)} (${pct(s.today.pct)})</span>` : ""}</span></div>
    <div class=row><span class=meta>Premium from this lot</span><span class=up>${mc(s.premium_c || 0, true)}</span></div>
    <div style="margin-top:8px;padding-top:7px;border-top:1px solid var(--line);text-align:center;font-size:10.5px;letter-spacing:.7px;color:var(--dim);font-weight:600">DOUBLE-CLICK MARKER FOR FULL DETAILS</div></div>`; }
  const table = `<div style="max-height:450px;overflow:auto"><table class=mini><thead><tr><th class=l>Date</th><th>Ghost Trader</th><th>TQQQ hold</th><th>T-bills</th><th>TQQQ close</th></tr></thead><tbody>${acct.map((a, i) => `<tr><td class=l>${esc(p.labels[i])}${est[i] ? " <span class=meta>est.</span>" : ""}</td><td>${money(a)}</td><td>${bh[i] == null ? "—" : money(bh[i])}</td><td>${money(tb[i])}</td><td>$${f2(tq[i])}</td></tr>`).reverse().join("")}</tbody></table></div>`;
  const bandNote = ui.perfDay ? `<div class=arrive><span><b>Showing ${esc(p.labels[idxOf(ui.perfDay)])} on the charts</b></span><button class=chip style="margin-left:auto" id=clrBand>Clear ${I("x")}</button></div>` : "";
  $("#main").innerHTML = `${bandNote}${cardsH}
    <div style="display:flex;gap:16px;flex-wrap:wrap"><div class=card style="flex:1;min-width:0">
      <div style="display:flex;justify-content:space-between"><b>Account value since ${esc(p.labels[0])}</b><span class=seg><button class="btn small ${ui.chartTable ? "" : "on"}" id=asChart>Chart</button><button class="btn small ${ui.chartTable ? "on" : ""}" id=asTable>Table</button></span></div>
      <div class=meta style="margin:2px 0 6px"><span style="color:var(--s1)">${I("dot")}</span> Ghost Trader &nbsp; <span style="color:var(--s2)">${I("dot")}</span> TQQQ buy & hold &nbsp; <span style="color:var(--s3)">${I("dot")}</span> T-bills &nbsp; ${I("ring")} estimated day &nbsp; <span style="color:var(--warn)">${I("diamond")}</span> share in/out</div>
      ${ui.chartTable ? table : `${svg1}<div style="border-top:1px solid var(--line);margin-top:6px;padding-top:8px"><b>TQQQ price since ${esc(p.labels[0])}</b> <span class=meta>· hover either chart · click a <span style="color:var(--warn)">${I("diamond")}</span> to pin, double-click to open in History</span></div><div class=chartwrap>${svg2}${pin}</div>`}</div>
      ${bars}</div><div id=outcomes></div>`;
  renderOutcomes();
  $("#asChart").onclick = () => { ui.chartTable = false; render(); };
  $("#asTable").onclick = () => { ui.chartTable = true; render(); };
  if ($("#clrBand")) $("#clrBand").onclick = () => { ui.perfDay = null; render(); };
  if ($("#pinX")) $("#pinX").onclick = () => { ui.pin = null; render(); };
  if (ui.chartTable) return;
  const svgPt = (svg, e) => { const r = svg.getBoundingClientRect(); return (e.clientX - r.left) * (W / r.width); };
  const draw = i => {
    $("#x1").innerHTML = `<line x1=${X(i)} x2=${X(i)} y1=${T} y2=${H - B} stroke="var(--dim)" stroke-dasharray="3 3"/><circle cx=${X(i)} cy=${Y(acct[i])} r=4.5 fill="var(--s1)" stroke="var(--panel)" stroke-width=2 />${bh[i] != null ? `<circle cx=${X(i)} cy=${Y(bh[i])} r=4.5 fill="var(--s2)" stroke="var(--panel)" stroke-width=2 />` : ""}
      <g transform="translate(${X(i) > W / 2 ? X(i) - 262 : X(i) + 10},${T + 4})"><rect width=252 height=74 rx=6 fill="var(--panel2)" stroke="var(--line)"/>
      <text x=10 y=18 font-size=12 fill="var(--text)" font-weight=600>${esc(p.labels[i])}${est[i] ? " · estimated" : ""}</text>
      <circle cx=14 cy=32 r=4 fill="var(--s1)"/><text x=24 y=36 font-size=12 fill="var(--text)">Ghost Trader ${money(acct[i])}</text>
      <circle cx=14 cy=48 r=4 fill="var(--s2)"/><text x=24 y=52 font-size=12 fill="var(--text)">TQQQ buy & hold ${bh[i] == null ? "—" : money(bh[i])}</text>
      <circle cx=14 cy=64 r=4 fill="var(--s3)"/><text x=24 y=68 font-size=12 fill="var(--text)">T-bills ${money(tb[i])}</text></g>`;
    $("#x2").innerHTML = `<line x1=${X(i)} x2=${X(i)} y1=${T} y2=${H2 - B} stroke="var(--dim)" stroke-dasharray="3 3"/><circle cx=${X(i)} cy=${Y2(tq[i])} r=4.5 fill="var(--s2)" stroke="var(--panel)" stroke-width=2 />
      <g transform="translate(${X(i) > W / 2 ? X(i) - 160 : X(i) + 10},${T})"><rect width=150 height=24 rx=6 fill="var(--panel2)" stroke="var(--line)"/><text x=10 y=16 font-size=12 fill="var(--text)">${esc(p.labels[i])} · TQQQ $${f2(tq[i])}</text></g>`; };
  const clear = () => { $("#x1").innerHTML = ""; $("#x2").innerHTML = ""; };
  ["#c1", "#c2"].forEach(id => { const svg = $(id);
    svg.addEventListener("mousemove", e => { if (e.target.classList.contains("mk")) return clear(); const x = svgPt(svg, e); const i = Math.round((x - L) / (W - L - Rr) * (N - 1)); if (i >= 0 && i < N) draw(i); else clear(); });
    svg.addEventListener("mouseleave", clear); });
  $$(".mk").forEach(m => m.addEventListener("click", e => { e.stopPropagation(); clearTimeout(pinT); if (e.detail === 1) pinT = setTimeout(() => { if (ui.tab === "Performance") { ui.pin = +m.dataset.j; render(); } }, 260); }));
}
async function renderOutcomes() {
  const o = await api("outcomes", {by: ui.outBy || "stoch14", range: ui.outRange}), el = $("#outcomes");
  if (!el || o.error) return;
  const tabs = `<div class=stabs role=tablist>${o.options.map(([k, t]) => `<button role=tab class="${k === o.by ? "on" : ""}" data-ob="${k}">${t}</button>`).join("")}<span class=srng><span class="seg irng">${RANGES.map(r => `<button class="btn small ${o.range === r ? "on" : ""}" data-or="${r}">${r}</button>`).join("")}</span></span></div>`;
  const pc = v => v == null ? "—" : (v * 100).toFixed(0) + "%";
  const rows = o.groups.map(g => `<tr class="${g.n ? "" : "dim"}"><td class=l>${esc(g.label)}</td><td>${g.n}</td><td>${pc(g.win_rate)}</td><td>${pc(g.kept)}</td><td>${g.n ? g.expired : "—"}</td><td>${g.n ? g.assigned : "—"}</td><td class="${g.avg_result_c > 0 ? "up" : g.avg_result_c < 0 ? "down" : ""}">${g.avg_result_c == null ? "—" : mc(g.avg_result_c, true)}</td></tr>`).join("");
  el.innerHTML = `<h2>Readings at entry vs. outcomes</h2><div class="stochpanel" style="margin-top:0">${tabs}
    ${o.total ? `<table class=outt><thead><tr><th class=l>When opened, ${esc(o.options.find(x => x[0] === o.by)[1])} was</th><th>Trades</th><th>Win rate</th><th>Avg % of premium kept</th><th>Expired worthless</th><th>Assigned / called</th><th>Avg result</th></tr></thead><tbody>${rows}</tbody></table>
    <div class=meta style="padding:6px 12px 8px">Finished short options this run, opened in the last ${({"14D": "14 days", "1M": "month", "3M": "3 months", "6M": "6 months", "1Y": "year", "5Y": "5 years"})[o.range]}, with readings saved when opened (${o.total}${o.without ? `; ${o.without} had no reading for this one` : ""}). A win is a positive result; assigned puts count the shares at that day's close. Small groups say little.</div>`
    : `<div class=empty style="padding:18px 12px">Nothing to compare in this range. Trades placed from v1.6.0 on save their readings; once they finish (expire, get assigned or are closed) they're grouped here by when they were opened.</div>`}</div>`;
  $$("[data-ob]").forEach(b => b.onclick = () => { ui.outBy = b.dataset.ob; renderOutcomes(); });
  $$("[data-or]").forEach(b => b.onclick = () => { ui.outRange = b.dataset.or; api("settings_set", {out_range: ui.outRange}); renderOutcomes(); });
}
function monthBars(p) {
  const ms = p.monthly.slice(-6);
  const BW = Math.max(360, 70 + ms.length * 140), BH = 250;
  const mx = Math.max(100, ...ms.map(m => Math.max(m.premium_c, m.interest_c || m.accrued_c) / 100));
  const step = niceStep(mx, 4), top = Math.ceil(mx / step) * step;
  const yb = v => 20 + (BH - 50) * (1 - v / top);
  let s = "";
  for (let v = 0; v <= top; v += step) s += `<line x1=50 x2=${BW} y1=${yb(v)} y2=${yb(v)} stroke="var(--line)"/><text x=44 y=${yb(v) + 4} font-size=11 fill="var(--dim)" text-anchor=end>$${v}</text>`;
  ms.forEach((m, j) => { const x = 70 + j * 140, pv = m.premium_c / 100, iv = (m.interest_c || m.accrued_c) / 100, posted = !!m.interest_c;
    s += `<rect x=${x} y=${yb(pv)} width=40 height=${BH - 30 - yb(pv)} rx=4 fill="var(--s1)"><title>${esc(m.label)} premium ${money(pv)}</title></rect><text x=${x + 20} y=${yb(pv) - 6} font-size=12 fill="var(--text)" text-anchor=middle>$${Math.round(pv)}</text>
    <rect x=${x + 44} y=${yb(iv)} width=40 height=${BH - 30 - yb(iv)} rx=4 fill="${posted ? "var(--s3)" : "url(#hatch)"}" stroke="var(--s3)" stroke-width="${posted ? 0 : 1.5}"><title>${esc(m.label)} interest ${money(iv)}${posted ? "" : " (accrued)"}</title></rect><text x=${x + 64} y=${yb(iv) - 6} font-size=12 fill="var(--text)" text-anchor=middle>$${Math.round(iv)}</text>
    <text x=${x + 42} y=${BH - 10} font-size=11 fill="var(--dim)" text-anchor=middle>${esc(m.label)}</text>`; });
  const sm = p.summary;
  return `<div class=card style="width:${Math.min(BW + 30, 520)}px;max-width:100%"><b>Premium + interest by month</b>
    <div class=meta style="margin:2px 0 6px"><span style="color:var(--s1)">${I("dot")}</span> Premium &nbsp; <span style="color:var(--s3)">${I("dot")}</span> Interest posted &nbsp; striped = accrued, pays ${esc(p.next_pay || "")}</div>
    ${ms.length ? `<svg width=${BW} height=${BH} style="max-width:100%"><defs><pattern id=hatch width=6 height=6 patternTransform="rotate(45)" patternUnits=userSpaceOnUse><line x1=0 y1=0 x2=0 y2=6 stroke="var(--s3)" stroke-width=2 /></pattern></defs>${s}</svg>` : `<div class=empty>Nothing yet.</div>`}
    <div class=meta>Total: ${mc(sm.premium_c)} premium · ${mc(sm.interest_c)} interest + ${mc(sm.accrued_c)} accrued</div></div>`;
}

/* ---------- SETTINGS ---------- */
function renderAlertRules(a, save) {
  const el = $("#alertRules"); if (!el) return;
  let rules = a.rules.map(r => ({...r}));
  const now = a.now || {};
  const opt = (m) => Object.entries(a.metrics).map(([k, t]) => `<option value="${k}" ${k === m ? "selected" : ""}>${esc(t)}</option>`).join("");
  const draw = () => {
    el.innerHTML = (rules.length ? rules.map((r, i) => { const v = now[r.metric], hit = v != null && (r.op === "below" ? v < r.value : v > r.value);
      return `<div class=arule><input type=checkbox data-aon=${i} ${r.on ? "checked" : ""} title="On/off">
        <select data-am=${i}>${opt(r.metric)}</select>
        <select data-ao=${i}><option ${r.op === "below" ? "selected" : ""}>below</option><option ${r.op === "above" ? "selected" : ""}>above</option></select>
        <input data-av=${i} value="${r.value}" style="width:56px">
        <span class=meta style="min-width:70px">now ${v == null ? "—" : (r.metric === "vix" ? f2(v) : Math.round(v))}${hit ? ` <span class=warn>${I("dot")}</span>` : ""}</span>
        <button class="btn small" data-adel=${i} title="Remove">${I("x")}</button></div>`; }).join("") : `<div class=meta>No alerts yet.</div>`)
      + `<div style="margin-top:6px;display:flex;gap:6px;flex-wrap:wrap"><button class="btn small" id=aAdd>+ Add alert</button>${rules.length ? "" : `<button class="btn small" id=aPre>Add suggested (stoch &lt; 20, stoch &gt; 80, F&amp;G &lt; 25, VIX &gt; 30)</button>`}</div>`;
    const put = async () => { await save({ind_alerts: rules}); };
    $$("[data-aon]").forEach(x => x.onchange = () => { rules[+x.dataset.aon].on = x.checked; put(); });
    $$("[data-am]").forEach(x => x.onchange = () => { rules[+x.dataset.am].metric = x.value; rules[+x.dataset.am].id = null; put(); draw(); });
    $$("[data-ao]").forEach(x => x.onchange = () => { rules[+x.dataset.ao].op = x.value; rules[+x.dataset.ao].id = null; put(); draw(); });
    $$("[data-av]").forEach(x => x.onchange = () => { const v = parseFloat(x.value); if (isNaN(v)) { toast("Enter a number."); return; } rules[+x.dataset.av].value = v; rules[+x.dataset.av].id = null; put(); draw(); });
    $$("[data-adel]").forEach(x => x.onclick = () => { rules.splice(+x.dataset.adel, 1); put(); draw(); });
    $("#aAdd").onclick = () => { rules.push({metric: "stoch14_k", op: "below", value: 20, on: true}); put(); draw(); };
    if ($("#aPre")) $("#aPre").onclick = () => { rules = a.presets.map(p => ({...p, on: true})); put(); draw(); };
  };
  draw();
}
async function renderSettings() {
  const s = await api("settings"), cfg = s.settings;
  const fontOk = document.fonts.check('14px "GT Inter"');
  ui.theme = cfg.theme || "system";
  const rate = s.rate.rate != null ? `<b>${f2(s.rate.rate)}%</b> (${esc(s.rate.source)}, ${esc(s.rate.day)}) <span class=pill>OK</span>` : `<span class=warn>no rate yet</span>`;
  $("#main").innerHTML = `<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:16px;max-width:1150px">
  <div class=card><h2 style="margin-top:0">Data & interest</h2>
    <div class=row><label>Alpha Vantage API key</label><span><input id=key type=password value="${esc(cfg.av_key)}" style="width:200px" placeholder="paste your key"> <button class="btn small" id=keyShow>Show</button></span></div>
    <div class=row><label></label><span class=meta>${cfg.av_key ? "" : "No key yet: the rate comes from ^IRX. "}<span class=lnk style="color:var(--accent)" id=avLink>Get a free key</span> (about a minute; the key shows right on the page)</span></div>
    <div class=row><label>Rate source</label><span>3-mo Treasury · ${rate}</span></div>
    <div class=row><label>Fallbacks</label><span class=meta>^IRX (Yahoo) → manual rate</span></div>
    <div class=row><label>Manual rate (last resort)</label><input id=man value="${cfg.manual_rate == null ? "" : esc(cfg.manual_rate) + "%"}" placeholder="e.g. 4.24%" style="width:90px"></div>
    <div class=row><label>Haircut below T-bill rate</label><input id=hc value="${f2(cfg.haircut || 0)}%" style="width:90px"></div>
    <div class=row><label>Interest</label><span class=meta>all cash · accrues daily · paid on the 15th (prior business day if closed)</span></div>
    <div class=row><label>Quotes</label><span class=meta>${esc(s.provider)}</span></div>
    <div class=row><label>Auto-refresh</label><span><span class=seg>${[[0, "Off"], [5, "5 min"], [10, "10 min"], [15, "15 min"]].map(([v, t]) => `<button class="btn small ${(cfg.auto_refresh ?? 10) === v ? "on" : ""}" data-ar="${v}">${t}</button>`).join("")}</span> <span class=meta>while the market is open</span></span></div>
    <div class=row><label>Expiration-day alerts</label><span class=meta>${s.nudges.installed ? (s.nudges.active === false ? "<span class=warn>timer installed but not running</span>" : "desktop notification " + esc(s.nudges.time)) : "not set up yet (starts after the next launch)"}${!s.nudges.notify_send ? " · <span class=warn>needs libnotify</span>" : !s.nudges.daemon ? " · <span class=warn>no notification daemon running</span>" : ""} <button class="btn small" id=testNotify>Send test</button></span></div></div>
  <div class=card><h2 style="margin-top:0">Notifications</h2>
    <div class=row><label>End-of-day summary</label><span><span class=seg><button class="btn small ${cfg.eod_summary === false ? "on" : ""}" data-eod=0>Off</button><button class="btn small ${cfg.eod_summary === false ? "" : "on"}" data-eod=1>On</button></span> <button class="btn small" id=testEod>Send now</button></span></div>
    <div class=row><label></label><span class=meta>3:30 PM CT on trading days: the day's change, premium, interest, and what expires next</span></div>
    <div class=row style="align-items:flex-start"><label>Indicator alerts</label><div id=alertRules style="flex:1"></div></div>
    <div class=row><label></label><span class=meta>A notification when a reading crosses your level (once per crossing). Checked when the indicators refresh and at 7:45 AM / 3:30 PM CT.</span></div></div>
  <div class=card><h2 style="margin-top:0">Trading</h2>
    <div class=row><label>Allow buying options to open</label><span class=seg><button class="btn small ${cfg.long_options ? "" : "on"}" data-lo=0>Off</button><button class="btn small ${cfg.long_options ? "on" : ""}" data-lo=1>On</button></span></div>
    <div class=row><label>Fill price default</label><span class=meta>mid when selling · halfway between mid and ask when buying</span></div>
    <div class=row><label>Fill price limits</label><span class=meta>must be within bid–ask · no override</span></div>
    <div class=row><label>Rules</label><span class=meta>covered calls and cash-secured puts only</span></div>
    <div class=row><label>Sizing warning</label><span class=meta>collateral above 80% of account</span></div>
    <div class=row><label>Fees</label><span class=meta>none</span></div></div>
  <div class=card><h2 style="margin-top:0">Appearance</h2>
    <div class=row><label>Theme</label><span class=seg>${["light", "dark", "system"].map(t => `<button class="btn small ${ui.theme === t ? "on" : ""}" data-th="${t}">${t === "system" ? "Match system" : t[0].toUpperCase() + t.slice(1)}</button>`).join("")}</span></div>
    <div class=row><label>Times</label><span class=meta>Central, with Eastern in parentheses (Central only in tickets)</span></div>
    <div class=row style="align-items:flex-start"><label>Mouse</label><div class=rules>
      <span class=pill style="text-align:center">Hover</span><span>quick look</span>
      <span class=pill style="text-align:center">Click</span><span>pin the details</span>
      <span class=pill style="text-align:center">Double-click</span><span>jump to the related place <span class=meta>(<span class=lnk>dotted underline</span>)</span></span></div></div>
    <div class=row><label>Font</label><span class=meta>Inter, bundled with the app · ${fontOk ? "loaded " + I("check") : "using backup font"}</span></div>
    <div class=row><label>Shortcuts</label><span class=meta><span class=kbd>1</span>–<span class=kbd>8</span> tabs · <span class=kbd>Esc</span> close · <span class=kbd>Enter</span> confirm</span></div></div>
  <div class=card><h2 style="margin-top:0">Runs & app</h2>
    <div class=row><label>Current run</label><span>${s.run ? "Started " + esc(s.run.start) + " · " + mc(s.run.cash_c) : "none"}</span></div>
    <div class=row style="align-items:flex-start"><label>Past runs</label><span>${s.past.length ? s.past.map(r => `<div>${esc(r.start)} → ${esc(r.end)} · ${mc(r.final_c)} <button class="btn small" data-rexp="${r.id}">Save CSV…</button></div>`).join("") : `<span class=meta>none yet · closed runs' CSVs can be re-exported here</span>`}</span></div>
    <div class=row><label>Data folder</label><span><span style="color:var(--accent);cursor:pointer" id=openDir>${I("folder")} ${esc(s.data_dir.replace(/^\/home\/[^/]+/, "~"))}/</span> <span class=meta>opens in your file manager</span></span></div>
    <div class=row><label>Last backup</label><span class=meta>${esc(s.last_backup || "none yet")} · <span class=meta>automatic at every launch and before updates · last 30 kept</span></span></div>
    <div class=row><label>Backup & restore</label><span><button class="btn small" id=bkNow>Back up now</button> <button class="btn small" id=bkExport>Export ledger…</button> <button class="btn small" id=bkRestore>Restore…</button></span></div>
    <div class=row><label>Tags</label><span>${s.tags.map(t => `<span class=tag>${esc(t.tag)}</span>`).join("") || `<span class=meta>none yet</span>`} <button class="btn small" id=tagMgr>Manage</button></span></div>
    <div class=row><label>Version</label><span>v${esc(s.version)} <span class=meta>· ${s.install === "system" ? "installed as an Arch package · updates noted at startup" : "updates offered at startup"}</span></span></div></div></div>
  ${s.run ? `<div class=card style="max-width:1150px;margin-top:16px;border-color:color-mix(in srgb,var(--danger) 50%,var(--line))">
    <div class=row><span><b>Close run</b><div class=meta>Ends this run, pays out accrued interest, saves the run CSV, and starts a new run. Can't be undone.</div></span><button class="btn danger" id=closeRunBtn>Close run</button></div></div>` : ""}`;
  const save = async kv => { const r = await api("settings_set", kv); if (r.error) toast(esc(r.error)); else toast(`${I("check")} Saved`, 1500); };
  $("#keyShow").onclick = () => { const k = $("#key"); k.type = k.type === "password" ? "text" : "password"; };
  $("#avLink").onclick = async () => { const r = await api("open_link", {name: "av_key"}); if (r.error) toast(esc(r.error), 8000); else toast(`${I("check")} Opened alphavantage.co in your browser`); };
  $("#key").onchange = e => save({av_key: e.target.value.trim()});
  $("#man").onchange = e => save({manual_rate: e.target.value.trim()});
  $("#hc").onchange = e => save({haircut: e.target.value.trim()});
  $$("[data-lo]").forEach(b => b.onclick = async () => { await save({long_options: b.dataset.lo === "1"}); render(); });
  $$("[data-th]").forEach(b => b.onclick = async () => { ui.theme = b.dataset.th; applyTheme(); await api("settings_set", {theme: ui.theme}); render(); });
  $$("[data-rexp]").forEach(b => b.onclick = async () => { const r = await api("export_run", {id: +b.dataset.rexp}); if (r.ok) toast(`${I("check")} Saved ${esc(r.path)}`); else if (r.error) toast(esc(r.error)); });
  $("#openDir").onclick = () => api("open_folder");
  $("#bkNow").onclick = async () => { const r = await api("backup_now"); if (r.ok) { toast(`${I("check")} Backed up (${esc(r.name)})`); render(); } else toast(esc(r.error || "Backup failed")); };
  $("#bkExport").onclick = async () => { const r = await api("export_ledger"); if (r.ok) toast(`${I("check")} Saved ${esc(r.path)}`, 5000); else if (r.error) toast(esc(r.error)); };
  $("#bkRestore").onclick = showRestore;
  $$("[data-ar]").forEach(b => b.onclick = async () => { await save({auto_refresh: +b.dataset.ar}); ui.autoMin = +b.dataset.ar; setAutoRefresh(); render(); });
  $$("[data-eod]").forEach(b => b.onclick = async () => { await save({eod_summary: b.dataset.eod === "1"}); render(); });
  $("#testEod").onclick = async () => { const r = await api("test_notify", {kind: "eod"}); toast((r.ok ? I("check") + " " : I("x") + " ") + esc(r.msg), 5000); };
  renderAlertRules(s.alerts, save);
  $("#testNotify").onclick = async () => { const r = await api("test_notify"); toast((r.ok ? I("check") + " " : I("x") + " ") + esc(r.msg), 5000); };
  $("#tagMgr").onclick = () => showTags(s.tags);
  if ($("#closeRunBtn")) $("#closeRunBtn").onclick = closeRun;
}
/* ---------- BACKUP & RESTORE (v1.9.0) ---------- */
async function showRestore() {
  const b = await api("backups");
  const rows = b.backups.map((x, i) => `<tr class=click data-bk="${esc(x.name)}"><td class=l><b>${esc(x.when)}</b><div class=meta>${esc(x.why)}</div></td><td class=meta>${x.kb} KB</td></tr>`).join("");
  $("#overlay").innerHTML = `<div class=scrim><div class=modal style="width:680px"><h3>Restore the ledger</h3>
    <div class=meta>Pick a backup to see what's in it before anything changes. Your ledger as it is now is backed up first, so a restore can itself be undone.</div>
    <div style="max-height:300px;overflow:auto;margin-top:10px"><table class=mini><tbody>${rows || `<tr><td class="l meta">No backups yet.</td></tr>`}</tbody></table></div>
    <div style="margin-top:10px"><span class=meta>Or a ledger file, e.g. one you exported:</span> <input type=file id=rsFile accept=".db,application/octet-stream"></div>
    <div id=rsPrev></div>
    <div class=actions><button class=btn onclick="closeOverlay()">Cancel</button><button class="btn danger" id=rsGo disabled>Restore and restart</button></div></div></div>`;
  let source = null;
  const preview = async args => {
    $("#rsGo").disabled = true; $("#rsPrev").innerHTML = `<div class=meta style="margin-top:10px"><span class=spin>${I("spin")}</span> Reading…</div>`;
    const r = await api("restore_preview", args);
    if (r.error) { $("#rsPrev").innerHTML = `<div class="alert e" style="margin-top:10px"><span class=ic>${I("warn")}</span><span>${esc(r.error)}</span></div>`; return; }
    source = r.source;
    const col = i => [i.run_start_txt ? `Run started ${esc(i.run_start_txt)} · ${mc(i.run_cash_c)}` : "No open run", `${plural(i.trades, "trade")} · ${plural(i.events, "History event")}`,
      i.last_day_txt ? `Last snapshot ${esc(i.last_day_txt)} · ${mc(i.last_value_c)}` : "No snapshots", i.last_txt ? `Last activity ${esc(i.last_txt)}` : "—", plural(i.closed_runs, "closed run")];
    const a = col(r.backup), c = col(r.current);
    $("#rsPrev").innerHTML = `<table class=mini style="margin-top:12px;table-layout:fixed;width:100%"><colgroup><col style="width:72px"><col><col></colgroup><thead><tr><th class=l></th><th class=l>${esc(r.label)}</th><th class=l>Your ledger now</th></tr></thead><tbody>
      ${["Run", "Activity", "Account", "Latest", "History"].map((h, i) => `<tr><td class="l meta">${h}</td><td class=l style="white-space:normal">${a[i]}</td><td class=l style="white-space:normal">${c[i]}</td></tr>`).join("")}</tbody></table>
      <div class="alert w" style="margin-top:10px"><span class=ic>${I("warn")}</span><span>Everything after this backup is replaced (it stays in the safety backup made first). Ghost Trader restarts and runs its usual startup refresh.</span></div>`;
    $("#rsGo").disabled = false;
  };
  $$("[data-bk]").forEach(tr => tr.onclick = () => { $$("[data-bk]").forEach(x => x.classList.remove("cur")); tr.classList.add("cur"); $("#rsFile").value = ""; preview({name: tr.dataset.bk}); });
  $("#rsFile").onchange = e => { const f = e.target.files[0]; if (!f) return; $$("[data-bk]").forEach(x => x.classList.remove("cur"));
    const rd = new FileReader(); rd.onload = () => preview({data: rd.result, filename: f.name}); rd.readAsDataURL(f); };
  $("#rsGo").onclick = async () => {
    $("#rsGo").disabled = true; $("#rsGo").innerHTML = `<span class=spin>${I("spin")}</span> Restoring…`;
    const r = await api("restore_apply", {source});
    if (r.error) { toast(esc(r.error)); $("#rsGo").disabled = false; $("#rsGo").textContent = "Restore and restart"; return; }
    $("#overlay").innerHTML = ""; $("#splash").innerHTML = `<div class=splash><div class=modal><h3>${LOGO} Restarting…</h3><div class=meta>Ledger restored. Ghost Trader is restarting with it. If this is a browser tab, reopen Ghost Trader.</div></div></div>`;
  };
}
function showTags(tags) {
  $("#overlay").innerHTML = `<div class=scrim><div class=modal style="width:520px"><h3>Tags</h3><div class=meta>Type any new tag in a ticket; it's created on first use and autocompletes after that. Changes here apply to every trade that carries the tag.</div>
    <table class=mini style="margin-top:10px"><tbody>${tags.map(t => `<tr><td class=l><span class=tag>${esc(t.tag)}</span></td><td class=meta>${plural(t.n, "event")}</td><td><button class="btn small" data-tr="${esc(t.tag)}">Rename</button> <button class="btn small" data-tm="${esc(t.tag)}">Merge</button> <button class="btn small" data-td="${esc(t.tag)}">Delete</button></td></tr>`).join("") || `<tr><td class="l meta">No tags yet.</td></tr>`}</tbody></table>
    <div id=tagEdit></div><div class=actions><button class=btn onclick="closeOverlay();render()">Done</button></div></div></div>`;
  const edit = (op, tag) => {
    const others = tags.filter(t => t.tag !== tag).map(t => `<option>${esc(t.tag)}</option>`).join("");
    $("#tagEdit").innerHTML = `<div class=row style="margin-top:12px"><label>${op === "rename" ? "Rename" : op === "merge" ? "Merge" : "Delete"} ${esc(tag)}${op === "delete" ? " from every trade?" : " into"}</label>
      ${op === "rename" ? `<input id=tagTo placeholder="#new-name" style="width:160px">` : op === "merge" ? `<select id=tagTo>${others}</select>` : ""}<button class="btn ${op === "delete" ? "danger" : "primary"} small" id=tagGo>${op === "delete" ? "Delete" : "Apply"}</button></div>`;
    $("#tagGo").onclick = async () => { const r = await api("tag_edit", {op, tag, to: ($("#tagTo") || {}).value}); if (r.error) return toast(esc(r.error)); toast(`${I("check")} Tags updated`); showTags(r.tags); };
  };
  $$("[data-tr]").forEach(b => b.onclick = () => edit("rename", b.dataset.tr));
  $$("[data-tm]").forEach(b => b.onclick = () => edit("merge", b.dataset.tm));
  $$("[data-td]").forEach(b => b.onclick = () => edit("delete", b.dataset.td));
}
async function closeRun() {
  const p = await api("close_run_preview");
  if (p.error) return toast(esc(p.error));
  $("#overlay").innerHTML = `<div class=scrim><div class=modal><h3 style="color:var(--danger)">Close this run?</h3>
    <div class=meta>${esc(p.start)} → ${esc(p.end)} (${plural(p.days, "day")}) · started with ${mc(p.start_cash_c)}. This is permanent.</div>
    <table class=mini style="margin:10px 0"><tbody><tr><td class=l>Available</td><td>${mc(p.available_c)}</td></tr><tr><td class=l>Collateral${p.open_puts ? ` <span class=meta>(${plural(p.open_puts, "open put")}: counted at collateral only)</span>` : ""}</td><td>${mc(p.collateral_c)}</td></tr>
    <tr><td class=l>Accrued interest (paid out now)</td><td>${mc(p.accrued_c)}</td></tr><tr><td class=l>${p.shares} TQQQ @ ${f2(p.share_price)}${p.open_calls ? ` <span class=meta>(open calls ignored)</span>` : ""}</td><td>${mc(p.shares_value_c)}</td></tr>
    <tr><td class=l><b>Final value</b></td><td><b>${mc(p.final_c)}</b></td></tr></tbody></table>
    <div class=row><label>Type the final value to confirm</label><input id=crv placeholder="${p.final}" style="width:160px"></div><div id=crm class=meta style="text-align:right">&nbsp;</div>
    <div class=actions><button class=btn onclick="closeOverlay()">Cancel</button><button class="btn danger" id=crb disabled>Close run and save CSV…</button></div></div></div>`;
  const norm = v => { const n = parseFloat(v.replace(/[$,\s]/g, "")); return isNaN(n) ? null : n.toFixed(2); };
  $("#crv").oninput = e => { const ok = norm(e.target.value) === p.final && /^\$?[\d,]*\.?\d{0,2}$/.test(e.target.value.trim());
    $("#crb").disabled = !ok; e.target.style.borderColor = ok ? "var(--up)" : ""; $("#crm").innerHTML = ok ? `<span class=ok>${I("check")} Matches</span>` : "&nbsp;"; };
  $("#crb").onclick = async () => {
    $("#crb").disabled = true; $("#crb").textContent = "Choose where to save…";
    const r = await api("close_run", {typed: $("#crv").value});
    if (r.cancelled) { closeOverlay(); toast("Save cancelled. The run stays open."); return; }
    if (r.error) { toast(esc(r.error)); $("#crb").disabled = false; $("#crb").textContent = "Close run and save CSV…"; return; }
    toast(`${I("check")} Run closed · saved ${esc(r.path)}`, 6000);
    await refreshState(); newRun();
  };
}
function newRun() {
  $("#overlay").innerHTML = `<div class=scrim><div class=modal style="width:480px"><div class=meta>NEW RUN</div><h3>How much paper cash should this run start with?</h3>
    <div class=row style="margin-top:14px"><label>Starting cash</label><input id=sc value="$100,000.00" style="width:180px;font-size:16px"></div>
    <div class=meta>Rules for every run: covered calls and cash-secured puts only · all cash earns the 3-month T-bill rate, paid on the 15th · no fees.</div>
    <div class=meta style="margin-top:6px">Tip: a free Alpha Vantage key (Settings) gives the most accurate interest rate. Optional.</div>
    <div id=scErr class=err></div>
    <div class=actions><button class="btn primary" id=scb>Start run</button></div></div></div>`;
  $("#sc").select();
  $("#sc").onkeydown = e => { if (e.key === "Enter") $("#scb").click(); };
  $("#scb").onclick = async () => { const r = await api("start_run", {cash: $("#sc").value});
    if (r.error) { $("#scErr").textContent = r.error; return; }
    closeOverlay(); ui.tab = "Portfolio"; await reload(); toast("New run started. Try the Chain tab to sell a put."); };
}
async function showReport() {
  const r = await api("report");
  const icon = s => s === "ok" ? "check" : s === "warn" ? "warn" : s === "working" ? "spin" : "ring";
  $("#overlay").innerHTML = `<div class=scrim><div class=modal style="width:min(820px,94vw)"><div class=meta>STARTUP REPORT${r.when ? " · " + esc(r.when) + " · took " + esc(r.took) : ""}</div><h3>What was refreshed</h3>
    <table class=mini><tbody>${r.steps.map(s => `<tr><td class=l style="${s.status === "warn" ? "color:var(--warn)" : ""}">${I(icon(s.status))} ${esc(s.name)}</td><td class=l style="white-space:normal">${esc(s.detail)}${s.status === "warn" ? ` <span class=lnk style="color:var(--accent)" data-go="history:errors">see History</span>` : ""}</td><td>${esc(s.t || "")}</td></tr>`).join("")}</tbody></table>
    <div class=meta style="margin-top:8px">${st && st.market.open ? "Market is open; quotes are Yahoo's (~15 min delayed)." : "Market is closed; quotes are from the " + esc(st ? st.market.close_txt : "") + " close."}</div>
    <div class=actions><button class=btn onclick="closeOverlay()">Close <span class=kbd>Esc</span></button></div></div></div>`;
}

/* ---------- STARTUP ---------- */
function paintSplash(s) {
  const steps = s.steps;
  const n = steps.filter(x => x.status === "ok" || x.status === "warn").length;
  let issue = "";
  if (s.issue) { const is = s.issue;
    issue = `<div class=issue><b>${esc(is.title)}</b><pre>${esc(is.what)}</pre><div class=opts>${is.options.map(o => `<div>${o.input != null ? `<input data-in="${o.id}" placeholder="${esc(o.input)}" style="width:160px">` : ""}<button class="btn ${o.primary ? "primary" : ""}" data-opt="${o.id}">${esc(o.label)}</button></div>`).join("")}</div></div>`;
  }
  const restarting = s.state === "restarting";
  $("#splash").innerHTML = `<div class=splash><div class=modal style="width:min(640px,94vw)"><h3 style="display:flex;gap:6px;align-items:center">${LOGO} Ghost Trader <span class=meta>v${esc(s.version)}</span></h3>
    <div class=meta>${restarting ? "Restarting with the new version…" : "Updating everything before you trade"}${s.started ? " · " + esc(s.started) : ""}</div><div class=steps style="margin-top:12px">${steps.map(x => {
      const ic = x.status === "ok" ? I("check") : x.status === "warn" ? I("warn") : x.status === "working" ? `<span class=spin>${I("spin")}</span>` : I("ring");
      const col = x.status === "ok" ? "var(--up)" : x.status === "warn" ? "var(--warn)" : x.status === "working" ? "var(--accent)" : "var(--dim)";
      return `<div><span class=s style="color:${col}">${ic}</span><span style="width:250px">${esc(x.name)}</span><span class=meta>${x.status === "working" ? (s.issue ? "needs you" : "working…") : esc(x.detail)}</span></div>`; }).join("")}</div>
    <div style="height:6px;background:var(--panel2);border-radius:3px;margin-top:12px"><div style="width:${n / steps.length * 100}%;height:6px;background:var(--accent);border-radius:3px;transition:width .2s"></div></div>${issue}</div></div>`;
  $$("[data-opt]").forEach(b => b.onclick = async () => { const inp = $(`[data-in="${b.dataset.opt}"]`);
    b.disabled = true; await api("startup_resolve", {issue_id: s.issue.id, choice: b.dataset.opt, value: inp ? inp.value : null}); });
}
async function startup() {
  boot = await api("boot");
  ui.theme = boot.theme || "system"; applyTheme(); ui.autoMin = boot.auto_refresh ?? 10; setAutoRefresh(); if (boot.ind_ranges) ui.indRanges = {...ui.indRanges, ...boot.ind_ranges}; ui.indTrades = !!boot.ind_trades; ui.outRange = boot.out_range || "3M";
  if (boot.demo) { const d = document.createElement("div"); d.className = "demo"; d.textContent = "Demo mode · synthetic data · separate demo ledger"; document.body.appendChild(d); }
  await api("loaded");
  setInterval(async () => { const h = await api("heartbeat"); if (h.restarting) $("#splash").innerHTML = `<div class=splash><div class=modal><h3>${LOGO} Restarting…</h3><div class=meta>Ghost Trader is restarting. If this is a browser tab, you can close it.</div></div></div>`; }, 5000);
  let lastIssue = null;
  for (;;) {
    const s = await api("startup_status");
    if (s.error) { await new Promise(r => setTimeout(r, 800)); continue; }
    const key = JSON.stringify([s.state, s.steps.map(x => x.status + x.detail), s.issue && s.issue.id]);
    if (key !== lastIssue) { paintSplash(s); lastIssue = key; }
    if (s.state === "done") break;
    await new Promise(r => setTimeout(r, s.issue ? 600 : 250));
  }
  await refreshState();
  setTimeout(() => $("#splash").innerHTML = "", 300);
  ui.tab = "Portfolio";
  await render();
  if (!st.run) newRun();
}
startup();
