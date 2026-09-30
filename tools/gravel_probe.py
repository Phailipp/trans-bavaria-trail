"""Schotter-Magnet: find legal unpaved segments all over Bavaria with BRouter.

A copy of the strict-legal profile is made where every legal paved way costs
8x and every legal unpaved way costs 1x. Routes between neighbouring points
of a ~15 km grid over Bavaria are then pulled onto any legal gravel nearby.
Every returned segment is re-audited with route_check (independent legality
rules); only unpaved AND legal runs of >= MIN_KM are kept.

Writes tools/gravel_segments.json. Run: python3 tools/gravel_probe.py
"""
import json
import math
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import plan_route  # noqa: E402  (in_bavaria)
import route_check  # noqa: E402

STEP_KM = 15
MIN_KM = 0.8
OUT = TOOLS / "gravel_segments.json"
CACHE = TOOLS / ".probe_cache.json"


def magnet_profile():
    src = (TOOLS / "tbt-legal.brf").read_text()
    src = src.replace("else if unpaved then multiply basecost 0.6\n       else basecost",
                      "else if unpaved then 1\n       else multiply basecost 8")
    assert "multiply basecost 8" in src
    req = urllib.request.Request("https://brouter.de/brouter/profile", data=src.encode(), method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        res = json.load(r)
    if res.get("error"):
        raise SystemExit(res["error"])
    return res["profileid"]


def grid():
    lat0, lat1, lon0, lon1 = 47.3, 50.55, 9.0, 13.8
    dlat = STEP_KM / 111.2
    pts = []
    lat = lat0
    while lat <= lat1:
        dlon = STEP_KM / (111.2 * math.cos(math.radians(lat)))
        lon = lon0
        row = []
        while lon <= lon1:
            row.append((round(lon, 4), round(lat, 4)) if plan_route.in_bavaria(lon, lat) else None)
            lon += dlon
        pts.append(row)
        lat += dlat
    pairs = []
    for i, row in enumerate(pts):
        for j, p in enumerate(row):
            if not p:
                continue
            if j + 1 < len(row) and row[j + 1]:
                pairs.append((p, row[j + 1]))
            if i + 1 < len(pts) and j < len(pts[i + 1]) and pts[i + 1][j]:
                pairs.append((p, pts[i + 1][j]))
    return pairs


def fetch(pid, a, b):
    q = urllib.parse.urlencode({"lonlats": f"{a[0]},{a[1]}|{b[0]},{b[1]}", "profile": pid,
                                "alternativeidx": 0, "format": "geojson"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(f"https://brouter.de/brouter?{q}", timeout=180) as r:
                return json.load(r)
        except Exception:  # noqa: BLE001
            time.sleep(3 * (attempt + 1))
    return None


def segments(geo, min_km=MIN_KM):
    """Consecutive rows that are legal AND unpaved, merged into runs."""
    msgs = geo["features"][0]["properties"]["messages"]
    head, rows = msgs[0], msgs[1:]
    ilon, ilat, idist, itags = head.index("Longitude"), head.index("Latitude"), head.index("Distance"), head.index("WayTags")
    runs, cur = [], None
    prev_pt = None
    walked = 0.0
    for r in rows:
        pt = (int(r[ilon]) / 1e6, int(r[ilat]) / 1e6)
        t = route_check.parse_tags(r[itags])
        ok, _ = route_check.legal(t)
        if ok and route_check.unpaved(t):
            if cur is None:
                cur = {"start": prev_pt or pt, "end": pt, "m": 0.0, "tags": set(), "pts": [prev_pt or pt],
                       "at_m": walked}
            cur["end"] = pt
            cur["pts"].append(pt)
            cur["m"] += float(r[idist])
            cur["tags"].add(r[itags])
        elif cur is not None:
            runs.append(cur)
            cur = None
        prev_pt = pt
        walked += float(r[idist])
    if cur is not None:
        runs.append(cur)
    return [{"start": s["start"], "end": s["end"], "km": round(s["m"] / 1000, 2), "tags": sorted(s["tags"]),
             "pts": s["pts"], "at_m": round(s["at_m"]), "len_m": round(s["m"])}
            for s in runs if s["m"] >= min_km * 1000]


def main():
    pid = magnet_profile()
    pairs = grid()
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    todo = [p for p in pairs if f"{p[0]}|{p[1]}" not in cache]
    print(f"Profil {pid}, {len(pairs)} Proberouten, davon {len(todo)} neu")

    def work(p):
        geo = fetch(pid, *p)
        time.sleep(1)
        return p, (segments(geo) if geo and geo.get("features") else None)

    done = 0
    with ThreadPoolExecutor(max_workers=3) as ex:
        for p, segs in ex.map(work, todo):
            cache[f"{p[0]}|{p[1]}"] = segs
            done += 1
            if done % 25 == 0:
                CACHE.write_text(json.dumps(cache))
                print(f"  {done}/{len(todo)}")
    CACHE.write_text(json.dumps(cache))

    # dedupe: same segment is found by several probes
    found = {}
    for segs in cache.values():
        for s in segs or []:
            key = (round(s["start"][0], 3), round(s["start"][1], 3), round(s["end"][0], 3), round(s["end"][1], 3))
            rkey = (key[2], key[3], key[0], key[1])
            if key in found or rkey in found:
                continue
            if not (plan_route.in_bavaria(*s["start"]) and plan_route.in_bavaria(*s["end"])):
                continue
            found[key] = s
    segs = sorted(found.values(), key=lambda s: -s["km"])
    OUT.write_text(json.dumps({"min_km": MIN_KM, "segmente": segs}, ensure_ascii=False, indent=1))
    failed = sum(1 for v in cache.values() if v is None)
    print(f"{len(segs)} legale unbefestigte Abschnitte >= {MIN_KM} km, {sum(s['km'] for s in segs):.0f} km gesamt; "
          f"{failed} Proberouten ohne Ergebnis")


if __name__ == "__main__":
    main()
