"""CSV exports: a closed run (summary block + full History) and History on its own."""
import csv
import io
import json

from . import timeutil


def _ev_rows(led, run_id):
    out = []
    for e in led.db.q("SELECT * FROM events WHERE run_id=? ORDER BY ts, id", (run_id,)):
        tags = " ".join(t[0] for t in led.db.q("SELECT tag FROM event_tags WHERE event_id=? ORDER BY tag", (e["id"],)))
        data = json.loads(e["data"] or "{}")
        ts = timeutil.parse(e["ts"])
        out.append([
            ts.astimezone(timeutil.CT).strftime("%Y-%m-%d"), ts.astimezone(timeutil.CT).strftime("%H:%M CT"),
            e["kind"], "error" if e["is_error"] else ("warning" if e["is_warning"] else ""),
            e["title"], e["detail"], tags, data.get("close_note", ""),
            data.get("what", ""), data.get("did", ""), data.get("todo", ""),
        ])
    return out


HEAD = ["date", "time", "kind", "level", "event", "details", "tags", "close reason", "what happened",
        "what the app did", "what you can do"]


def history_csv(led, run_id):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(HEAD)
    w.writerows(_ev_rows(led, run_id))
    return buf.getvalue()


def run_csv(led, run_id, summary):
    """summary: list of (label, value) pairs written as the block at the top."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Ghost Trader run summary"])
    for k, v in summary:
        w.writerow([k, v])
    w.writerow([])
    w.writerow(HEAD)
    w.writerows(_ev_rows(led, run_id))
    return buf.getvalue()
