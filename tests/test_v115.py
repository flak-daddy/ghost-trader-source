"""v1.21.0: chain heat map (strike x expiration)."""
from tests.test_v114 import _open
from tests.test_v18 import ready


def test_chain_map_shape_and_values(home):
    a = ready(home)
    p = _open(a, "put")
    m = a.api_chain_map()
    assert not m.get("error") and 1 <= len(m["cols"]) <= a.MAP_EXPIRIES
    assert [c["expiry"] for c in m["cols"]] == sorted(c["expiry"] for c in m["cols"])
    S = m["price"]
    assert m["strikes"] and all(S * 0.85 - 1e-9 <= k <= S * 1.15 + 1e-9 for k in m["strikes"])
    n = 0
    for typ in ("put", "call"):
        for e, by_k in m["cells"][typ].items():
            for ks, x in by_k.items():
                n += 1
                k = float(ks)
                assert k in m["strikes"] and x["bid"] > 0 and x["mid"] > 0 and x["ann"] > 0
                assert x["worthless"] is None or 0 <= x["worthless"] <= 1
    assert n > 10
    # a put held at that strike and expiry is flagged
    held = m["cells"]["put"].get(p["expiry"], {}).get(f"{p['strike']:g}")
    assert held and held["held"] == p["id"]
    # puts: annualized return grows with strike for a fixed expiry (more premium per dollar of collateral near the money)
    e0 = m["cols"][0]["expiry"]
    ks = sorted(float(k) for k in m["cells"]["put"].get(e0, {}))
    if len(ks) > 3:
        assert m["cells"]["put"][e0][f"{ks[-1]:g}"]["ann"] > m["cells"]["put"][e0][f"{ks[0]:g}"]["ann"]


def test_chain_map_needs_a_run(home):
    from ghost_trader.api import App
    from ghost_trader.market import DemoProvider
    a = App(demo=True, provider=DemoProvider())
    assert a.api_chain_map()["error"]
