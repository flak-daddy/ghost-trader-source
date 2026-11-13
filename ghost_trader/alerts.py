"""Indicator alerts: desktop notifications when a reading crosses a level the user set.

Rules live in settings (`ind_alerts`): [{"id", "metric", "op": "below"|"above", "value", "on"}].
An alert fires when its condition becomes true (it was false, or unknown, the last time it was checked), so a
reading that stays below 20 for a week notifies once, not every check. State is kept in alerts-state.json.
Checked whenever the indicators refresh in the app, and by the weekday notification timer.
"""
from __future__ import annotations

import json
import logging

from . import SYMBOL, config

log = logging.getLogger(__name__)

METRICS = {
    "stoch14_k": "stochastic 14,3,3 %K",
    "stoch30_k": "30-day stochastic",
    "stoch60_k": "60-day stochastic",
    "stoch180_k": "180-day stochastic",
    "vix": "VIX",
    "fg": "Fear & Greed",
}
PRESETS = [
    {"metric": "stoch14_k", "op": "below", "value": 20},
    {"metric": "stoch14_k", "op": "above", "value": 80},
    {"metric": "fg", "op": "below", "value": 25},
    {"metric": "vix", "op": "above", "value": 30},
]


def clean_rules(rules):
    """Validate rules from the UI; drops anything malformed. Assigns ids."""
    out, seen = [], set()
    for i, r in enumerate(rules or []):
        try:
            m, op, v = r["metric"], r["op"], float(r["value"])
        except (KeyError, TypeError, ValueError):
            continue
        if m not in METRICS or op not in ("below", "above"):
            continue
        rid = str(r.get("id") or f"{m}-{op}-{v:g}")
        if rid in seen:
            rid = f"{rid}-{i}"
        seen.add(rid)
        out.append({"id": rid, "metric": m, "op": op, "value": v, "on": bool(r.get("on", True))})
    return out


def subject(rule):
    name = METRICS[rule["metric"]]
    return name if rule["metric"] in ("vix", "fg") else f"{SYMBOL} {name}"


def describe(rule):
    return f"{subject(rule)} {rule['op']} {rule['value']:g}"


def _state_path():
    return config.data_dir() / "alerts-state.json"


def _load_state():
    try:
        return json.loads(_state_path().read_text())
    except (OSError, ValueError):
        return {}


def evaluate(snapshot, rules, state):
    """Pure check. Returns (fired, new_state): fired = [(rule, value)] for rules that just became true."""
    fired, new = [], dict(state)
    for r in rules:
        if not r.get("on", True):
            new.pop(r["id"], None)
            continue
        v = (snapshot or {}).get(r["metric"])
        if v is None:
            continue  # no reading: keep the previous state
        hit = v < r["value"] if r["op"] == "below" else v > r["value"]
        if hit and not state.get(r["id"]):
            fired.append((r, v))
        new[r["id"]] = hit
    for k in list(new):
        if k not in {r["id"] for r in rules}:
            new.pop(k)
    return fired, new


def message(fired):
    lines = []
    for r, v in fired:
        val = f"{v:.2f}" if r["metric"] == "vix" else f"{v:.0f}"
        lines.append(f"{subject(r)} is {val} ({r['op']} {r['value']:g})")
    title = f"{SYMBOL} indicator alert" if len(fired) == 1 else f"{len(fired)} {SYMBOL} indicator alerts"
    return title, "\n".join(lines)


def check(snapshot, settings, send, led=None):
    """Evaluate the saved rules against a readings snapshot; notify and log what fired. Returns the fired list."""
    rules = clean_rules(settings.get("ind_alerts") or [])
    if not rules or not snapshot:
        return []
    fired, new = evaluate(snapshot, rules, _load_state())
    try:
        _state_path().write_text(json.dumps(new))
    except OSError as e:
        log.warning("alert state: %s", e)
    if fired:
        title, body = message(fired)
        ok, msg = send(title, body)
        if led is not None and led.run():
            try:
                led.event("Alert", title, body.replace("\n", " · "),
                          {"rules": [r["id"] for r, _ in fired], "sent": ok, "send_msg": msg})
            except Exception:  # noqa: BLE001
                log.exception("alert event")
    return fired
