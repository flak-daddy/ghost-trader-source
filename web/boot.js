/* Ghost Trader Lite: start the real Python app in the browser (Pyodide), then load the normal UI.
   The UI's calls to POST /api/<name> are answered by gt_web.dispatch() instead of a local server. */
"use strict";
(async () => {
  const PYODIDE = "https://cdn.jsdelivr.net/pyodide/v0.27.2/full/";
  const box = document.getElementById("gtboot");
  const say = (msg, sub) => { box.querySelector("b").textContent = msg; box.querySelector("small").textContent = sub || ""; };
  const fail = (e) => {
    say("Ghost Trader Lite couldn't start", String(e && e.message || e) + (problems.length ? " | " + problems.join(" | ") : ""));
    box.classList.add("err");
    console.error(e);
  };
  // Show why loading stalls instead of spinning forever: blocked requests, script errors, timeouts.
  const problems = [];
  document.addEventListener("securitypolicyviolation", e =>
    problems.push(`Blocked by the page's security policy: ${e.violatedDirective} ${e.blockedURI}`));
  window.addEventListener("error", e => problems.push("Script error: " + (e.message || e.filename)));
  window.addEventListener("unhandledrejection", e => problems.push("Error: " + (e.reason && e.reason.message || e.reason)));
  const step = (p, what, secs = 60) => Promise.race([p, new Promise((_, no) => setTimeout(() =>
    no(new Error(`${what} didn't finish in ${secs}s. ${problems.join(" | ") || "No error was reported."}`)), secs * 1000))]);
  try {
    say("Starting Ghost Trader…", "Loading Python (one-time download, about 10 MB)");
    await step(new Promise((ok, no) => { const s = document.createElement("script"); s.src = PYODIDE + "pyodide.js"; s.onload = ok; s.onerror = () => no(new Error("Couldn't load Python from the CDN.")); document.head.appendChild(s); }), "Downloading Python");
    say("Starting Ghost Trader…", "Starting Python");
    const py = await step(loadPyodide({indexURL: PYODIDE}), "Starting Python");
    say("Starting Ghost Trader…", "Loading the database engine");
    await step(py.loadPackage(["sqlite3", "tzdata"]), "Loading the database engine");
    say("Starting Ghost Trader…", "Unpacking the app");
    const files = await (await fetch("gt-web.json")).json();
    for (const [path, text] of Object.entries(files)) {
      const full = "/gtapp/" + path;
      py.FS.mkdirTree(full.slice(0, full.lastIndexOf("/")));
      py.FS.writeFile(full, text);
    }

    // Keep each visitor's run in their own browser between visits (falls back to memory only).
    const FS = py.FS;
    FS.mkdirTree("/gtdata");
    let persist = false;
    const sync = (load) => new Promise(ok => { try { FS.syncfs(load, () => ok()); } catch (e) { ok(); } });
    try { FS.mount(FS.filesystems.IDBFS, {}, "/gtdata"); await sync(true); persist = true; } catch (e) { /* memory only */ }

    py.runPython("import sys, os; sys.path[:0] = ['/gtapp']; os.environ['GHOST_TRADER_HOME'] = '/gtdata'");
    const gt = py.pyimport("gt_web");
    say("Starting Ghost Trader…", "Setting up the demo run");
    const mode = gt.start();
    if (persist) await sync(false);

    let saveTimer = null;
    const READS = /^(state|boot|startup_status|heartbeat|history|performance|chain|position|indicators|market|manual|cone|vol_now|outcomes|expirations|chain_map|roll_map|check)/;
    const realFetch = window.fetch.bind(window);
    window.fetch = async (url, opts = {}) => {
      const u = typeof url === "string" ? url : url.url;
      if (!u.startsWith("/api/")) return realFetch(url, opts);
      const name = u.slice(5);
      await new Promise(r => setTimeout(r, 0));          // let the page paint before Python runs
      const res = gt.dispatch(name, opts.body || "{}").toJs();
      const [code, body] = res;
      if (persist && !READS.test(name)) { clearTimeout(saveTimer); saveTimer = setTimeout(() => sync(false), 400); }
      return new Response(body, {status: code, headers: {"Content-Type": "application/json"}});
    };

    window.GT_LITE = {
      mode, persist,
      async reset() {
        gt.reset();
        if (persist) await sync(false);
        location.reload();
      }
    };
    box.remove();
    const s = document.createElement("script");
    s.src = "app.js";
    document.body.appendChild(s);
  } catch (e) { fail(e); }
})();
