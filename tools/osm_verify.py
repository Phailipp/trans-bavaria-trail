"""Third check: every unpaved run of the final route against LIVE OpenStreetMap data.

BRouter works on a periodic data snapshot and ignores conditional restrictions.
For each unpaved run in tools/stages.json this script loads the current OSM
data around sampled points (official API, small boxes, ~1 request/s) and checks
every way the run uses: it must still be legal for motorcycles under the same
rules as route_check, have no prohibiting *:conditional tag, and still be
unpaved. Result: tools/osm_verify.json; exit code 1 on any problem.
"""
import json
import math
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import route_check  # noqa: E402

BOX = 0.0025          # ~250 m half-size of each API box
SAMPLE_M = 400        # one sample every ~400 m along a run
UA = "TransBavariaTrail-verify/1.0 (route legality check)"
BAD_COND = ("no", "private", "agricultural", "forestry", "destination", "permit", "delivery", "customers")


def load(bbox, cache):
    key = ",".join(f"{v:.4f}" for v in bbox)
    if key in cache:
        return cache[key]
    url = "https://api.openstreetmap.org/api/0.6/map?bbox=" + key
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        root = ET.fromstring(r.read())
    nodes = {n.get("id"): (float(n.get("lon")), float(n.get("lat"))) for n in root.iter("node")}
    ways = []
    for w in root.iter("way"):
        tags = {t.get("k"): t.get("v") for t in w.iter("tag")}
        if "highway" not in tags:
            continue
        pts = [nodes[nd.get("ref")] for nd in w.iter("nd") if nd.get("ref") in nodes]
        if len(pts) >= 2:
            ways.append({"id": w.get("id"), "tags": tags, "pts": pts})
    cache[key] = ways
    time.sleep(1.1)
    return ways


def seg_dist_m(p, a, b):
    kx = 111320 * math.cos(math.radians(p[1]))
    ky = 110540
    ax, ay = (a[0] - p[0]) * kx, (a[1] - p[1]) * ky
    bx, by = (b[0] - p[0]) * kx, (b[1] - p[1]) * ky
    dx, dy = bx - ax, by - ay
    t = max(0, min(1, -(ax * dx + ay * dy) / (dx * dx + dy * dy or 1e-9)))
    return math.hypot(ax + t * dx, ay + t * dy)


def point_dist_m(a, b):
    kx = 111320 * math.cos(math.radians(a[1]))
    return math.hypot((b[0] - a[0]) * kx, (b[1] - a[1]) * 110540)


def nearest_way(p, ways):
    best = None
    for w in ways:
        d = min(seg_dist_m(p, a, b) for a, b in zip(w["pts"], w["pts"][1:]))
        if best is None or d < best[0]:
            best = (d, w)
    return best


def check_way(tags):
    ok, why = route_check.legal(tags)
    if not ok:
        return f"nicht legal: {why}"
    for k, v in tags.items():
        if k.endswith(":conditional") and k.split(":")[0] in ("access", "vehicle", "motor_vehicle", "motorcycle"):
            if any(v.strip().startswith(b) for b in BAD_COND):
                return f"zeitliche Sperre {k}={v}"
    return None


def near_ways(p, ways, max_m):
    out = []
    for w in ways:
        d = min(seg_dist_m(p, a, b) for a, b in zip(w["pts"], w["pts"][1:]))
        if d <= max_m:
            out.append((d, w))
    return sorted(out, key=lambda x: x[0])


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else TOOLS / "stages.json"
    stages = json.loads(src.read_text(encoding="utf-8"))["etappen"]
    cache, problems, report = {}, [], []
    live_unpaved = {}
    for s in stages:
        live_km = 0.0
        for run in s.get("schotter_abschnitte", []):
            pts = run["pts"]
            classes = {route_check.parse_tags(t).get("highway") for t in run.get("tags", [])}
            # interior samples only (run ends sit on junctions with the paved road)
            samples, acc = [], 0.0
            for a, b in zip(pts, pts[1:]):
                acc += point_dist_m(a, b)
                if acc >= SAMPLE_M:
                    samples.append(b)
                    acc = 0.0
            if not samples and len(pts) >= 3:
                samples = [pts[len(pts) // 2]]
            if not samples:
                continue
            unpaved_hits = 0
            for p in samples:
                bbox = (p[0] - BOX, p[1] - BOX, p[0] + BOX, p[1] + BOX)
                try:
                    ways = load(bbox, cache)
                except Exception as e:  # noqa: BLE001
                    problems.append({"etappe": s["nr"], "lon": p[0], "lat": p[1], "grund": f"OSM-API-Fehler: {e}"})
                    continue
                cands = near_ways(p, ways, 20)
                match = [c for c in cands if c[1]["tags"].get("highway") in classes]
                if not match:
                    got = ", ".join(sorted({c[1]["tags"].get("highway", "?") for c in cands})) or "nichts"
                    problems.append({"etappe": s["nr"], "lon": p[0], "lat": p[1],
                                     "grund": f"kein Weg der Klasse {sorted(classes)} im Umkreis 20 m (gefunden: {got})"})
                    continue
                w = match[0][1]
                err = check_way(w["tags"])
                if err:
                    problems.append({"etappe": s["nr"], "lon": p[0], "lat": p[1], "grund": f"way/{w['id']}: {err}"})
                elif route_check.unpaved(w["tags"]):
                    unpaved_hits += 1
            share = unpaved_hits / len(samples)
            live_km += run["km"] * share
            report.append({"etappe": s["nr"], "km": run["km"], "stichproben": len(samples), "aktuell_unbefestigt": unpaved_hits})
            print(f"E{s['nr']} {run['km']} km: {unpaved_hits}/{len(samples)} Stichproben legal und aktuell unbefestigt")
        live_unpaved[s["nr"]] = round(live_km, 1)
    (TOOLS / "osm_verify.json").write_text(json.dumps(
        {"probleme": problems, "unbefestigt_live_km": live_unpaved, "abschnitte": report}, ensure_ascii=False, indent=1))
    for p in problems:
        print(f"PROBLEM E{p['etappe']} {p['lon']:.5f},{p['lat']:.5f}: {p['grund']}")
    print(f"{len(report)} Abschnitte geprüft, {len(problems)} Probleme; unbefestigt laut Live-Daten: "
          f"{sum(live_unpaved.values()):.0f} km")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
