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
  hFilter: "All", hTag: null, hDay: null, hEvent: null, hExpand: null, calMonth: null, lot: null, lotEvent: null, perfDay: null, pin: null, chartTable: false, theme: "system"};
const S = () => (st && st.price) || 0;
const label = p => p.label;

/* ---------- theme ---------- */
function applyTheme() {
  const dark = ui.theme === "dark" || (ui.theme === "system" && !matchMedia("(prefers-color-scheme: light)").matches);
  document.documentElement.classList.toggle("light", !dark);
}
matchMedia("(prefers-color-scheme: light)").addEventListener("change", applyTheme);

/* ---------- header ---------- */
const TABS = ["Portfolio", "Chain", "History", "Performance", "Settings", "Help"];
function renderHeader() {
  const errs = st ? st.errors : 0;
  $("#tabs").innerHTML = TABS.map(t => `<button class="${ui.tab === t ? "on" : ""}" data-tab="${t}">${t}${t === "History" && errs ? `<span class=badge>${errs}</span>` : ""}</button>`).join("");
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
      <div class=row><span class=meta>Accrued interest</span><span>${mc(b.accrued_c)}</span></div>
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
function resetMarks() { ui.pfMode = null; ui.flashPos = null; ui.flashStrike = null; ui.lot = null; ui.lotEvent = null; ui.perfDay = null; ui.pin = null; ui.hExpand = null; ui.hDay = null; ui.hEvent = null; }
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
document.addEventListener("click", e => {
  const t = e.target.closest("[data-tab]");
  if (t) { ui.tab = t.dataset.tab; resetMarks(); closeDrawer(); render(); }
});
document.addEventListener("keydown", e => {
  if (!st) return;
  if (e.target.matches("input,select,textarea")) { if (e.key === "Escape") e.target.blur(); else return; }
  if ($("#splash").innerHTML) return;
  if (e.key === "Escape") { if ($("#overlay").innerHTML) closeOverlay(); else if ($("#drawer").innerHTML) { if (tk) cancelTicket(); else closeDrawer(); } else if (ui.pin != null) { ui.pin = null; render(); } else if (ui.lot) { ui.lot = null; render(); } }
  if (/^[1-6]$/.test(e.key) && !$("#overlay").innerHTML && st.run) { ui.tab = TABS[+e.key - 1]; resetMarks(); closeDrawer(); render(); }
  if (e.key === "Enter" && $("#confirmBtn") && !$("#confirmBtn").disabled) $("#confirmBtn").click();
});

/* ---------- render ---------- */
async function refreshState() { const s = await api("state"); if (!s.error) st = s; return st; }
async function render() {
  applyTheme(); renderHeader();
  const fn = {Portfolio: renderPortfolio, Chain: renderChain, History: renderHistory, Performance: renderPerf, Settings: renderSettings, Help: renderHelp}[ui.tab];
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
    <div class=meta>Account value = cash + collateral + accrued interest + shares (option buy-back prices not counted)</div>
    <h2>Open options</h2><table><thead><tr><th class=l>Contract</th><th>Contracts</th><th>${st.positions.some(p => p.side === "long") ? "Opened at" : "Sold at"}</th><th>Mark</th><th>Collateral / cover</th><th>Distance</th><th>DTE</th><th>P&L</th><th>% of premium</th><th></th></tr></thead><tbody>${rows}</tbody></table>
    <h2 id=sharesH style="display:flex;justify-content:space-between;align-items:center">Shares <button class="btn small" onclick="openShares('buy_shares')">Buy shares…</button></h2><table><thead><tr><th class=l>Holding</th><th>Qty</th><th>Avg cost</th><th>Price</th><th>Value</th><th>P&L</th><th>%</th><th></th></tr></thead><tbody>${shRow}</tbody></table>
    <div id=calendar></div>`;
  renderCalendar();
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
    return `<div class="d ${d.in_month ? "" : "out"} ${d.today ? "today" : ""} ${d.holiday ? "hol" : ""}"><div class=top><span class=num>${d.n}${d.today ? ' <span class=pill style="font-size:10px">today</span>' : ""}</span>${px}</div>${note}${evs}${items}${trd}</div>`; };
  el.innerHTML = `<div class=calbar><h2>Calendar · ${esc(c.label)}</h2>
      <button class="btn small" id=calPrev title="Previous month">‹</button>${c.month !== c.this_month ? `<button class="btn small" id=calNow>This month</button>` : ""}<button class="btn small" id=calNext title="Next month">›</button></div>
    <div class=cal>${["Mon", "Tue", "Wed", "Thu", "Fri"].map(x => `<div class=hd>${x}</div>`).join("")}${c.weeks.flat().map(cell).join("")}</div>
    <div class=meta style="margin-top:6px"><span class="it exp" style="font-size:11px;padding:0 5px;border-radius:3px;background:color-mix(in srgb,var(--warn) 22%,transparent)">$55 Put ×2</span> open expiry · <span style="opacity:.6;border:1px dashed var(--line);padding:0 5px;border-radius:3px">settled</span> resolved · <span class=ev style="font-size:11px;padding:0 5px;border-radius:3px;background:color-mix(in srgb,var(--accent) 12%,transparent)">CPI 7:30 AM</span> market event (CT; hover for details) · TQQQ close with change from the previous close · double-click anything underlined</div>${c.events_note ? `<div class=meta>${esc(c.events_note)}</div>` : ""}`;
  $("#calPrev").onclick = () => { ui.calMonth = c.prev; renderCalendar(); };
  $("#calNext").onclick = () => { ui.calMonth = c.next; renderCalendar(); };
  if ($("#calNow")) $("#calNow").onclick = () => { ui.calMonth = null; renderCalendar(); };
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
  const cell = (q, t, k, side) => { if (!hasBid(q)) { const m = `<td class="meta${ic(t, k)}">`, n = [`${m}no bid</td>`, `${m}—</td>`, `${m}—</td>`, `${m}—</td>`]; return side === "c" ? n.reverse().join("") : n.join(""); }
    const pc = `<td class="px${ic(t, k)}" data-k="${k}" data-t="${t}">`, cc = [`${pc}${f2(q.bid)}</td>`, `${pc}${f2(q.ask)}</td>`, `${pc}<b>${f2(q.mid)}</b></td>`];
    const d = `<td class="meta${ic(t, k)}">${d2(q.delta)}</td>`; return side === "c" ? d + cc.join("") : cc.reverse().join("") + d; };
  const head = view === "both" ? `<tr><th colspan=4>CALLS</th><th class=mid></th><th colspan=4>PUTS</th></tr><tr><th>Delta</th><th>Bid</th><th>Ask</th><th>Mid</th><th class=mid>Strike</th><th>Mid</th><th>Ask</th><th>Bid</th><th>Delta</th></tr>`
    : `<tr><th class=mid>Strike</th><th>Bid</th><th>Ask</th><th>Mid</th><th>Delta</th></tr>`;
  const rows = ks.map(r => { const K = r.k, hs = held[K] || [];
    const dot = hs.length ? `<span class=held data-go="pos:${hs[0].id}" data-tip="Double-click: go to your ${esc(hs[0].exp_label)} ${kTxt(K)} ${hs[0].type === "put" ? "Put" : "Call"} (${plural(hs[0].open_qty, "contract")})">●</span>` : "";
    const cls = ui.flashStrike === K ? "flash" : "";
    if (view === "both") return `<tr class="${cls}" id="k${K}">${cell(r.call, "call", K, "c")}<td class=mid>${K}${dot}</td>${cell(r.put, "put", K, "p")}</tr>`;
    const t = view === "calls" ? "call" : "put", q = r[t];
    return `<tr class="${cls}" id="k${K}"><td class=mid>${K}${dot}</td><td class="px${ic(t, K)}" data-k="${K}" data-t="${t}">${f2(q.bid)}</td><td class="px${ic(t, K)}" data-k="${K}" data-t="${t}">${f2(q.ask)}</td><td class="px${ic(t, K)}" data-k="${K}" data-t="${t}"><b>${f2(q.mid)}</b></td><td class="meta${ic(t, K)}">${d2(q.delta)}</td></tr>`; });
  const cut = ks.findIndex(r => r.k > Sx);
  const pline = `<tr class=pline>${view === "both" ? `<td colspan=4></td><td class=mid><span>TQQQ ${f2(Sx)}</span></td><td colspan=4></td>` : `<td><span>TQQQ ${f2(Sx)}</span></td><td colspan=4></td>`}</tr>`;
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
    <div class=chainbox id=chainbox><table class=both><thead>${head}</thead><tbody>${rows.join("") || `<tr><td colspan=9 class=empty>No strikes with a bid for this expiration.</td></tr>`}</tbody></table></div>`;
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
      <div class=meta style="text-align:right">Bid ${f2(q.bid)} · Ask ${f2(q.ask)} · Mid ${f2(q.mid)}${q.iv ? " · IV " + (q.iv * 100).toFixed(1) + "%" : ""}${q.delta != null ? " · Δ " + q.delta.toFixed(2) : ""}</div>
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
      <div class=row><label>Return if it expires worthless</label><span><b>${pct(d.ret, 2)}</b> · ${pct(d.ann)} annualized</span></div>`;
  else if (tk.action === "sell_to_open") effects = `<div class=row><label>Premium → Available now</label><span class=up>${mc(ef.premium_c || 0, true)}</span></div>
      <div class=row><label>Shares locked as cover</label><span>${(tk.qty || 0) * 100}</span></div>
      <div class=row><label>Return if it expires worthless</label><span><b>${pct(d.ret, 2)}</b> · ${pct(d.ann)} annualized</span></div>`;
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
}

function helpFor(t) {
  const sec = t.action.endsWith("shares") ? null : t.type === "put" ? ["cash-secured-puts", "How cash-secured puts work"] : ["covered-calls-and-the-wheel", "How covered calls work"];
  return sec ? ` <span class="lnk helplink" onclick="go('help:${sec[0]}')" data-tip="Open the manual at this section">${sec[1]} ↗</span>` : "";
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
      <tr><td class=l>TQQQ vs. strike</td><td>${f2(p.price)} vs. ${kTxt(p.strike)} · ${Math.abs(p.dist * 100).toFixed(1)}% ${p.otm ? "out of" : "in"} the money</td></tr>
      <tr><td class=l>Days to expiration</td><td>${p.dte} <span class=meta>(${esc(p.exp_label)})</span></td></tr>
      <tr><td class=l>If it expires worthless</td><td>${short ? `keep ${mc(prem)}${p.type === "put" ? ", collateral released" : ", shares unlocked"}` : `lose the ${mc(prem)} paid`}</td></tr>
      <tr><td class=l>${short ? (p.type === "put" ? "If assigned" : "If called away") : "If exercised"}</td><td>${short ? (p.type === "put" ? `buy ${p.open_qty * 100} TQQQ at ${kTxt(p.strike)} (${mc(p.collateral_c)})` : `sell ${p.open_qty * 100} shares at ${kTxt(p.strike)}`) : (p.type === "call" ? `buy ${p.open_qty * 100} shares at ${kTxt(p.strike)}` : `sell ${p.open_qty * 100} shares at ${kTxt(p.strike)}`)}</td></tr>
    </tbody></table>
    ${p.note ? `<div style="margin-top:10px;padding:8px 10px;border-radius:6px;background:var(--panel2);font-size:13px"><span class=meta>Your note</span><br><i>“${esc(p.note)}”</i></div>` : ""}
    ${short && p.type === "put" && p.dist < 0.03 ? `<div class="alert w" style="margin-top:10px"><span class=ic>${I("warn")}</span><span>${p.dist < 0 ? "In the money." : "Within 3% of the strike."}</span></div>` : ""}
    <div class=actions style="justify-content:space-between">${short ? `<button class=btn onclick="openTicket({expiry:'${p.expiry}',strike:${p.strike},type:'${p.type}',action:'sell_to_open',from:${p.id}})">Sell more</button>` : "<span></span>"}
      <button class="btn primary" onclick="openTicket({close:${p.id},from:${p.id}})">Close position…</button></div></div>`;
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
    <div class=meta style="margin:14px 0 4px">TIMELINE</div><div class=tl>${tl}</div>
    ${p.lot_id && p.status === "assigned" ? `<div class=actions style="justify-content:flex-start"><button class=btn onclick="closeDrawer();go('history:lot:${p.lot_id}')">Open the share lot it created</button></div>` : ""}</div>`;
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
      <div class=meta style="font-size:12.5px">${esc(e.detail)}</div>${exp}</td></tr>`; }).join("") || `<tr><td class="l meta" style="padding:16px 8px">Nothing matches this filter.</td></tr>`;
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
    $("#main").innerHTML = `${cardsH}<div style="display:flex;gap:16px;flex-wrap:wrap"><div class=card style="flex:1;min-width:0"><b>Account value</b><div class=empty>The charts fill in as days go by: one point for each day the app is opened (missed days are estimated from TQQQ's daily closes).</div></div>${bars}</div>`;
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
      ${bars}</div>`;
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
    <div class=row><label>Expiration-day alerts</label><span class=meta>${s.nudges.installed ? (s.nudges.active === false ? "<span class=warn>timer installed but not running</span>" : "desktop notification " + esc(s.nudges.time)) : "not set up yet (starts after the next launch)"}${!s.nudges.notify_send ? " · <span class=warn>needs libnotify</span>" : !s.nudges.daemon ? " · <span class=warn>no notification daemon running</span>" : ""} <button class="btn small" id=testNotify>Send test</button></span></div></div>
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
    <div class=row><label>Shortcuts</label><span class=meta><span class=kbd>1</span>–<span class=kbd>6</span> tabs · <span class=kbd>Esc</span> close · <span class=kbd>Enter</span> confirm</span></div></div>
  <div class=card><h2 style="margin-top:0">Runs & app</h2>
    <div class=row><label>Current run</label><span>${s.run ? "Started " + esc(s.run.start) + " · " + mc(s.run.cash_c) : "none"}</span></div>
    <div class=row style="align-items:flex-start"><label>Past runs</label><span>${s.past.length ? s.past.map(r => `<div>${esc(r.start)} → ${esc(r.end)} · ${mc(r.final_c)} <button class="btn small" data-rexp="${r.id}">Save CSV…</button></div>`).join("") : `<span class=meta>none yet · closed runs' CSVs can be re-exported here</span>`}</span></div>
    <div class=row><label>Data folder</label><span><span style="color:var(--accent);cursor:pointer" id=openDir>${I("folder")} ${esc(s.data_dir.replace(/^\/home\/[^/]+/, "~"))}/</span> <span class=meta>opens in your file manager</span></span></div>
    <div class=row><label>Last backup</label><span class=meta>${esc(s.last_backup || "none yet")}</span></div>
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
  $("#testNotify").onclick = async () => { const r = await api("test_notify"); toast((r.ok ? I("check") + " " : I("x") + " ") + esc(r.msg), 5000); };
  $("#tagMgr").onclick = () => showTags(s.tags);
  if ($("#closeRunBtn")) $("#closeRunBtn").onclick = closeRun;
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
    <tr><td class=l><b>Final value</b></td><td><b>${mc(p.account_value_c)}</b></td></tr></tbody></table>
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
  ui.theme = boot.theme || "system"; applyTheme();
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
