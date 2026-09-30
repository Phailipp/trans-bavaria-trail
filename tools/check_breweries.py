"""Machine checks for tools/breweries.json (zero error tolerance).

- coordinates must lie inside the stated Regierungsbezirk (real borders)
- website URLs must answer with HTTP < 400
- no duplicate names / near-identical coordinates
Run: python3 tools/check_breweries.py   (exit code 1 on any problem)
"""
import json
import math
import subprocess
import time
import urllib.parse
import urllib.request
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
geo = json.loads((TOOLS / "regierungsbezirke.geo.json").read_text())
polys = {}
for f in geo["features"]:
    g = f["geometry"]
    polys[f["properties"]["name"]] = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]


def inside(lon, lat, rings):
    hit = False
    for ring in rings:
        n = len(ring)
        for i in range(n):
            x1, y1 = ring[i][:2]
            x2, y2 = ring[(i + 1) % n][:2]
            if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
                hit = not hit
    return hit


def in_district(lon, lat, name):
    return any(inside(lon, lat, poly) for poly in polys[name])


def district_of(lon, lat):
    return next((n for n in polys if in_district(lon, lat, n)), None)


CACHE = TOOLS / ".geocache.json"


def geocode(query):
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    if query not in cache:
        url = "https://photon.komoot.io/api/?" + urllib.parse.urlencode(
            {"q": query, "limit": 5, "bbox": "8.9,47.2,13.9,50.6", "lang": "de"})
        with urllib.request.urlopen(url, timeout=20) as r:
            cache[query] = [
                {"lat": f["geometry"]["coordinates"][1], "lon": f["geometry"]["coordinates"][0],
                 "name": f["properties"].get("name"), "county": f["properties"].get("county", ""),
                 "state": f["properties"].get("state", ""), "key": f["properties"].get("osm_key")}
                for f in json.load(r)["features"]
            ]
        CACHE.write_text(json.dumps(cache, ensure_ascii=False))
        time.sleep(1)
    return cache[query]


def km(a_lat, a_lon, b_lat, b_lon):
    return math.dist((a_lat * 111.2, a_lon * 111.2 * math.cos(math.radians(a_lat))),
                     (b_lat * 111.2, b_lon * 111.2 * math.cos(math.radians(b_lat))))


def place_check(b):
    """Returns an error string or None. The coordinate must be within 3 km of the named place."""
    lk = b["landkreis"].replace("Landkreis ", "").split(" (")[0].strip()
    ort = b["ort"].split(" (")[0]
    queries = [f'{ort} {b.get("gemeinde", "")}'.strip(), ort]
    hits = []
    for q in queries:
        hits = [h for h in geocode(q) if h["state"] == "Bayern" and h["key"] in ("place", "boundary")]
        if hits:
            break
    if not hits:
        return f"Ort '{ort}' nicht in OSM gefunden"
    best = min(hits, key=lambda h: km(b["lat"], b["lon"], h["lat"], h["lon"]))
    d = km(b["lat"], b["lon"], best["lat"], best["lon"])
    lk_ok = lk.lower() in best["county"].lower() or best["county"].lower().replace("landkreis ", "") in lk.lower()
    if d > 3:
        return f"Koordinate {d:.1f} km von OSM-Ort {best['name']} ({best['county']}) entfernt"
    if best["county"] and not lk_ok:
        return f"Landkreis '{lk}' passt nicht zu OSM '{best['county']}'"
    return None


def url_ok(url):
    for method in (["-I"], []):
        r = subprocess.run(
            ["curl", "-sL", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "20", "-A",
             "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36", *method, url],
            capture_output=True, text=True)
        code = r.stdout.strip()
        if code.isdigit() and 200 <= int(code) < 400:
            return True, code
    return False, code


def main(check_urls=True):
    data = json.loads((TOOLS / "breweries.json").read_text(encoding="utf-8"))
    problems = []
    seen = {}
    brews = data["brauereien"]
    for b in brews:
        tag = f'{b["name"]} ({b["ort"]})'
        actual = district_of(b["lon"], b["lat"])
        if actual != b["bezirk"]:
            problems.append(f"{tag}: Koordinate liegt in {actual}, angegeben {b['bezirk']}")
        if "--no-geo" not in sys.argv:
            err = place_check(b)
            if err:
                problems.append(f"{tag}: {err}")
        key = b["name"].lower().strip()
        if key in seen:
            problems.append(f"{tag}: doppelter Name")
        seen[key] = b
    for i, a in enumerate(brews):
        for c in brews[i + 1:]:
            if math.dist((a["lat"], a["lon"]), (c["lat"], c["lon"])) < 0.0015 and a["ort"] != c["ort"]:
                problems.append(f'{a["name"]} / {c["name"]}: fast identische Koordinaten, verschiedene Orte')
    if check_urls:
        for b in brews:
            if b.get("website"):
                ok, code = url_ok(b["website"])
                if not ok:
                    problems.append(f'{b["name"]}: Website {b["website"]} nicht erreichbar ({code})')
    for p in problems:
        print("FEHLER:", p)
    print(f"{len(brews)} Brauereien geprüft, {len(problems)} Probleme")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main("--no-urls" not in sys.argv))
