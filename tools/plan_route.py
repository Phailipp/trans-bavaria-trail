"""Route the Trans Bavaria Trail stages with the strict-legal BRouter profile.

- overnight stops: only breweries with double-verified guest rooms (zimmer == "ja")
- every stage is audited independently (tools/route_check.py): 0 violations required
- every track point must lie inside Bavaria (real border)
- writes tools/stages.json (for the website) and gpx/trans-bavaria-trail.gpx
Run: python3 tools/plan_route.py
"""
import json
import math
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import gpxpy
import gpxpy.gpx

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))
import check_breweries  # noqa: E402
import route_check  # noqa: E402

START = {"id": "start-miltenberg", "name": "Brauerei Faust", "ort": "Miltenberg", "bezirk": "Unterfranken",
         "lat": 49.7039, "lon": 9.2644, "zimmer": "unklar"}

# overnight chain, north to south (ids from breweries.json)
CHAIN = [
    "kauzen-braeu-gasthof-kauzen-ochsenfurt",
    "gasthof-brauerei-hennemann-stublang",
    "puettner-braeu-schlammersdorf",
    "brauerei-jacob-bodenwoehr-ludwigsheide",
    "brauerei-gasthof-eck-eck",
    "schlossbraeu-mariakirchen-mariakirchen",
    "brauerei-stierberg-stierberg",
    "ayinger-privatbrauerei-aying",
    "irseer-klosterbraeu-irsee",
    "brauereigasthof-schaeffler-schaeffler-braeu-missen",
]


# via points keep a stage inside Bavaria / on the intended line (lon, lat of the town centre)
VIA = {
    # right (bavarian) bank of the Main: Großheubach, Reistenhausen, Fechenbach, Stadtprozelten,
    # then through the Spessart to Marktheidenfeld and Randersacker (coordinates geocoded via OSM/Photon)
    "kauzen-braeu-gasthof-kauzen-ochsenfurt": [(9.2275, 49.7347), (9.2951, 49.7577), (9.3383, 49.7910),
                                               (9.4053, 49.7809), (9.6036, 49.8453),
                                               (9.9829, 49.7597)],
    "gasthof-brauerei-hennemann-stublang": [(10.7220, 49.6720)],           # Uehlfeld (Aischgrund)
    "ayinger-privatbrauerei-aying": [(11.8696, 48.1875)],                          # Schweiger, Markt Schwaben
}


GRAVEL_FILE = TOOLS / "gravel_vias.json"


def gravel_vias():
    """Extra via points (start/end of legal gravel segments) chosen by tools/gravel_optimize.py."""
    return json.loads(GRAVEL_FILE.read_text())["vias"] if GRAVEL_FILE.exists() else {}


def order_vias(base_coords, pts):
    """Sort via points by their position along the base track."""
    def pos(p):
        return min(range(0, len(base_coords), 3),
                   key=lambda i: (base_coords[i][0] - p[0]) ** 2 + (base_coords[i][1] - p[1]) ** 2)
    return sorted(pts, key=pos)


def upload_profile():
    req = urllib.request.Request("https://brouter.de/brouter/profile",
                                 data=(TOOLS / "tbt-legal.brf").read_bytes(), method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        res = json.load(r)
    if res.get("error"):
        raise SystemExit(f"Profilfehler: {res['error']}")
    return res["profileid"]


NOGO_FILE = TOOLS / "nogos.json"


def nogos():
    """Small no-go circles around ways that failed the live OSM check (tools/osm_verify.py)."""
    return json.loads(NOGO_FILE.read_text()) if NOGO_FILE.exists() else {}


def route(pid, a, b, extra=None, avoid=None):
    pts = [(a["lon"], a["lat"])] + list(extra if extra is not None else VIA.get(b["id"], [])) + [(b["lon"], b["lat"])]
    params = {"lonlats": "|".join(f"{x},{y}" for x, y in pts),
              "profile": pid, "alternativeidx": 0, "format": "geojson"}
    if avoid:
        params["nogos"] = "|".join(f"{x:.6f},{y:.6f},{r}" for x, y, r in avoid)
    q = urllib.parse.urlencode(params)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(f"https://brouter.de/brouter?{q}", timeout=300) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001
            if attempt == 3:
                raise
            print("  retry:", e)
            time.sleep(5 * (attempt + 1))


_BAY = json.loads((TOOLS / "bayern-grenze-hoch.geo.json").read_text())["features"][0]["geometry"]
_BAY_POLYS = _BAY["coordinates"] if _BAY["type"] == "MultiPolygon" else [_BAY["coordinates"]]


def in_bavaria(lon, lat):
    """High-resolution state border check."""
    return any(check_breweries.inside(lon, lat, p) for p in _BAY_POLYS)


def dense_slice(coords, at_m, len_m):
    """Dense track geometry of the part of the route between at_m and at_m + len_m (metres driven)."""
    out, walked = [], 0.0
    for a, b in zip(coords, coords[1:]):
        if at_m <= walked <= at_m + len_m:
            out.append([a[0], a[1]])
        walked += check_breweries.km(a[1], a[0], b[1], b[0]) * 1000
        if walked > at_m + len_m:
            break
    return out


def nearest_dist_km(lat, lon, coords):
    return min(check_breweries.km(lat, lon, c[1], c[0]) for c in coords[::5])


def main():
    brews = {b["id"]: b for b in json.loads((TOOLS / "breweries.json").read_text(encoding="utf-8"))["brauereien"]}
    chain = [START] + [brews[i] for i in CHAIN]
    for b in chain[1:]:
        assert b["zimmer"] == "ja", f'{b["name"]}: Zimmer nicht doppelt bestätigt'
    pid = upload_profile()
    print("Profil:", pid)

    gpx = gpxpy.gpx.GPX()
    gpx.creator = "Trans Bavaria Trail (Entwurf) – BRouter + OpenStreetMap"
    gpx.name = "Trans Bavaria Trail – Etappen-Entwurf"
    stages, problems = [], []
    gv = gravel_vias()
    ng = nogos()
    for n, (a, b) in enumerate(zip(chain, chain[1:]), 1):
        geo = route(pid, a, b, gv.get(b["id"]), ng.get(str(n)))
        audit = route_check.audit(geo)
        coords = geo["features"][0]["geometry"]["coordinates"]
        outside = [c for c in coords if not in_bavaria(c[0], c[1])]
        if audit["verstoesse"]:
            problems.append(f"Etappe {n}: {len(audit['verstoesse'])} Verstöße")
        if outside:
            problems.append(f"Etappe {n}: {len(outside)} Punkte außerhalb Bayerns")
        # breweries from the atlas directly on the way (<= 1.5 km from the track)
        unterwegs = [x for x in brews.values()
                     if x["id"] not in (a["id"], b["id"]) and nearest_dist_km(x["lat"], x["lon"], coords) <= 1.5]
        bezirke = []
        for c in coords[::20]:
            d = check_breweries.district_of(c[0], c[1])
            if d and d not in bezirke:
                bezirke.append(d)
        import gravel_probe  # local import: avoids a circular import at module load
        runs = gravel_probe.segments(geo, min_km=0.1)
        stage = {
            "schotter_abschnitte": [{"km": r["km"], "tags": r["tags"],
                                     "pts": dense_slice(coords, r["at_m"], r["len_m"])} for r in runs],
            "nr": n, "von": a["ort"], "nach": b["ort"], "ziel_brauerei": b["name"], "ziel_id": b["id"],
            "km": audit["km"], "unbefestigt_km": audit["unbefestigt_km"], "unbefestigt_anteil": audit["unbefestigt_anteil"],
            "strassentypen_km": audit["nach_strassentyp_km"], "bezirke": bezirke,
            "unterwegs": [{"id": x["id"], "name": x["name"], "ort": x["ort"]} for x in unterwegs],
            "verstoesse": len(audit["verstoesse"]),
        }
        stages.append(stage)
        print(f'E{n} {a["ort"]} → {b["ort"]}: {audit["km"]} km, unbefestigt {audit["unbefestigt_anteil"]} %, '
              f'Bezirke {bezirke}, unterwegs {len(unterwegs)}, Verstöße {len(audit["verstoesse"])}, außerhalb {len(outside)}')

        trk = gpxpy.gpx.GPXTrack(name=f'Etappe {n:02d} - {a["ort"]} - {b["ort"]}')
        seg = gpxpy.gpx.GPXTrackSegment()
        for c in coords:
            seg.points.append(gpxpy.gpx.GPXTrackPoint(latitude=c[1], longitude=c[0],
                                                      elevation=c[2] if len(c) > 2 else None))
        trk.segments.append(seg)
        gpx.tracks.append(trk)
        time.sleep(2)

    for i, b in enumerate(chain):
        w = gpxpy.gpx.GPXWaypoint(latitude=b["lat"], longitude=b["lon"], name=f'{b["name"]} ({b["ort"]})',
                                  symbol="Lodging" if i else "Flag, Green",
                                  description="Start" if i == 0 else f"Übernachtung Etappe {i}")
        gpx.waypoints.append(w)

    if problems:
        print("\n".join("PROBLEM: " + p for p in problems))
        raise SystemExit(1)
    (ROOT / "gpx").mkdir(exist_ok=True)
    (ROOT / "gpx" / "trans-bavaria-trail-entwurf.gpx").write_text(gpx.to_xml(version="1.1"), encoding="utf-8")
    (TOOLS / "stages.json").write_text(json.dumps({"profil": "tbt-legal.brf", "etappen": stages},
                                                  ensure_ascii=False, indent=1), encoding="utf-8")
    tot = sum(s["km"] for s in stages)
    unp = sum(s["unbefestigt_km"] for s in stages)
    print(f"GESAMT {tot:.0f} km, unbefestigt {unp:.0f} km ({unp / tot * 100:.1f} %)")


if __name__ == "__main__":
    main()
