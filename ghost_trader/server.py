"""Local HTTP server for the UI: static files plus a JSON API at POST /api/<name>.

Bound to 127.0.0.1 on a random port. API calls must carry the per-launch token (X-GT-Token header), so
other local programs can't drive the ledger."""
import json
import logging
import mimetypes
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from . import config

log = logging.getLogger("ghost_trader.server")
mimetypes.add_type("font/woff", ".woff")
mimetypes.add_type("text/javascript", ".js")


class Server:
    def __init__(self, app, port=0):
        self.app = app
        self.token = secrets.token_urlsafe(18)
        handler = _make_handler(app, self.token)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.thread = None

    @property
    def url(self):
        return f"http://127.0.0.1:{self.port}/?t={self.token}"

    def start(self):
        self.thread = threading.Thread(target=self.httpd.serve_forever, name="http", daemon=True)
        self.thread.start()
        return self

    def stop(self):
        try:
            self.httpd.shutdown()
            self.httpd.server_close()
        except Exception:  # noqa: BLE001
            pass


def _make_handler(app, token):
    methods = {n[4:]: getattr(app, n) for n in dir(app) if n.startswith("api_")}
    static_root = config.STATIC_DIR.resolve()

    class H(BaseHTTPRequestHandler):
        server_version = "GhostTrader"

        def log_message(self, fmt, *args):  # quiet
            log.debug("http " + fmt, *args)

        def _send(self, code, body, ctype="application/json"):
            data = body if isinstance(body, bytes) else body.encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            path = urlparse(self.path).path
            if path in ("/", ""):
                path = "/index.html"
            if path == "/gate":
                return self._send(200, _GATE, "text/html; charset=utf-8")
            f = (static_root / path.lstrip("/")).resolve()
            if static_root not in f.parents or not f.is_file():
                return self._send(404, b"not found", "text/plain")
            ctype = mimetypes.guess_type(str(f))[0] or "application/octet-stream"
            if ctype.startswith("text/"):
                ctype += "; charset=utf-8"
            self._send(200, f.read_bytes(), ctype)

        def do_POST(self):
            path = urlparse(self.path).path
            if not path.startswith("/api/"):
                return self._send(404, b"{}")
            if self.headers.get("X-GT-Token") != token:
                return self._send(403, json.dumps({"error": "bad token"}))
            name = path[5:]
            fn = methods.get(name)
            if not fn:
                return self._send(404, json.dumps({"error": f"no such call: {name}"}))
            n = int(self.headers.get("Content-Length") or 0)
            try:
                args = json.loads(self.rfile.read(n) or b"{}") if n else {}
                res = fn(**args)
                self._send(200, json.dumps(res, default=str))
            except TypeError as e:
                log.exception("bad call %s", name)
                self._send(400, json.dumps({"error": f"bad call: {e}"}))
            except Exception as e:  # noqa: BLE001
                log.exception("api %s failed", name)
                self._send(500, json.dumps({"error": f"{type(e).__name__}: {e}"}))

    return H


# Page shown in Firefox when the native window failed and no dialog could ask first.
_GATE = """<!doctype html><meta charset=utf-8><title>Ghost Trader</title>
<body style="font:15px system-ui,sans-serif;background:#0f1115;color:#e6e8ec;display:flex;align-items:center;
justify-content:center;height:100vh;margin:0"><div style="max-width:520px;padding:24px;border:1px solid #2a2f3a;
border-radius:10px;background:#171a21"><h2 style="margin-top:0">Ghost Trader window didn't start</h2>
<p>The app's own window failed to open (details are in History once you continue). Continue here in Firefox?</p>
<p><button id=c style="padding:8px 16px">Continue</button> <button id=q style="padding:8px 16px">Quit</button></p>
<script>const t=new URLSearchParams(location.search).get('t');
const go=a=>fetch('/api/gate_answer',{method:'POST',headers:{'X-GT-Token':t,'Content-Type':'application/json'},
body:JSON.stringify({answer:a})}).then(()=>{if(a==='continue')location.href='/?t='+t;else document.body.innerHTML=
'<p style="margin:auto">Ghost Trader closed. You can close this tab.</p>'});
c.onclick=()=>go('continue');q.onclick=()=>go('quit');</script></div>"""
