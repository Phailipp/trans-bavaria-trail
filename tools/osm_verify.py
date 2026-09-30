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


def main():
    stages = json.loads((TOOLS / "stages.json").read_text(encoding="utf-8"))["etappen"]
    cache, problems, report = {}, [], []
    for s in stages:
        for run in s.get("schotter_abschnitte", []):
            pts = run["pts"]
            samples, acc = [pts[0]], 0.0
            for a, b in zip(pts, pts[1:]):
                acc += seg_dist_m(a, a, b)
                if acc >= SAMPLE_M:
                    samples.append(b)
                    acc = 0
            samples.append(pts[-1])
            seen, still_unpaved = {}, 0
            for p in samples:
                bbox = (p[0] - BOX, p[1] - BOX, p[0] + BOX, p[1] + BOX)
                try:
                    ways = load(bbox, cache)
                except Exception as e:  # noqa: BLE001
                    problems.append(f"E{s['nr']}: OSM-API-Fehler bei {p}: {e}")
                    continue
                hit = nearest_way(p, ways)
                if not hit or hit[0] > 25:
                    problems.append(f"E{s['nr']}: kein OSM-Weg innerhalb 25 m von {p}")
                    continue
                w = hit[1]
                seen[w["id"]] = w["tags"]
                if route_check.unpaved(w["tags"]):
                    still_unpaved += 1
            if still_unpaved < len(samples) / 2:
                problems.append(f"E{s['nr']}: Abschnitt {run['km']} km laut aktuellen OSM-Daten überwiegend befestigt")
            for wid, tags in seen.items():
                err = check_way(tags)
                if err:
                    problems.append(f"E{s['nr']}: way/{wid}: {err}")
            report.append({"etappe": s["nr"], "km": run["km"], "ways": sorted(seen), "stichproben": len(samples),
                           "davon_unbefestigt_aktuell": still_unpaved})
            print(f"E{s['nr']} {run['km']} km: {len(seen)} Wege geprüft, {still_unpaved}/{len(samples)} Stichproben aktuell unbefestigt")
    (TOOLS / "osm_verify.json").write_text(json.dumps({"probleme": problems, "abschnitte": report}, ensure_ascii=False, indent=1))
    for p in problems:
        print("PROBLEM:", p)
    print(f"{len(report)} Schotter-Abschnitte geprüft, {len(problems)} Probleme")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
