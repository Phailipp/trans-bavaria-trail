"""Renders index.html from tools/index.src.html.

Generates the inline SVGs (Bavaria map with real district borders, route,
hero landscape, roadbook tulips, BBS seal) so the page ships as one static
file. Run: python3 tools/build.py
"""
import json
import math
import random
import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"

paths = json.loads((TOOLS / "paths.json").read_text())

DISTRICT_LABELS = {
    "Unterfranken": (150, 205),
    "Oberfranken": (500, 110),
    "Oberpfalz": (655, 370),
    "Mittelfranken": (300, 330),
    "Niederbayern": (760, 600),
    "Oberbayern": (640, 760),
    "Schwaben": (250, 640),
}


def _dp(pts, eps):
    """Douglas-Peucker simplification in map units."""
    if len(pts) < 3:
        return pts
    (x1, y1), (x2, y2) = pts[0], pts[-1]
    length = math.hypot(x2 - x1, y2 - y1) or 1e-9
    dmax, idx = 0, 0
    for i in range(1, len(pts) - 1):
        x, y = pts[i]
        d = abs((y2 - y1) * x - (x2 - x1) * y + x2 * y1 - y2 * x1) / length
        if d > dmax:
            dmax, idx = d, i
    if dmax > eps:
        return _dp(pts[: idx + 1], eps)[:-1] + _dp(pts[idx:], eps)
    return [pts[0], pts[-1]]


def load_route():
    """Computed route: stages.json (audited) + GPX tracks -> projected map path and pins."""
    import gpxpy

    stages = json.loads((TOOLS / "stages.json").read_text(encoding="utf-8"))["etappen"]
    gpx = gpxpy.parse((ROOT / "gpx" / "trans-bavaria-trail-entwurf.gpx").read_text(encoding="utf-8"))
    assert len(gpx.tracks) == len(stages)
    pts = []
    for trk in gpx.tracks:
        seg = [project(p.longitude, p.latitude) for p in trk.segments[0].points]
        pts.extend(_dp(seg, 0.6) if not pts else _dp(seg, 0.6)[1:])
    d = "M" + " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    total = sum(s["km"] for s in stages)
    wps = gpx.waypoints
    pins, cum = [], 0.0
    for i, w in enumerate(wps):
        x, y = project(w.longitude, w.latitude)
        if i:
            cum += stages[i - 1]["km"]
        ort = stages[i - 1]["nach"] if i else stages[0]["von"]
        pins.append({"id": "start" if i == 0 else stages[i - 1]["ziel_id"], "x": x, "y": y,
                     "at": round(cum / total, 4), "ort": ort.split(" (")[0], "lat": w.latitude, "lon": w.longitude})
    return {"d": d, "stages": stages, "pins": pins, "total": total}


ROUTE = None


def bavaria_map():
    r = ROUTE
    h = paths["H"]
    parts = [
        f'<svg id="bayern-map" viewBox="-20 -20 1040 {h + 40}" role="img" '
        f'aria-labelledby="map-title map-desc">',
        '<title id="map-title">Karte Bayern mit dem berechneten Etappen-Entwurf des Trans Bavaria Trail</title>',
        f'<desc id="map-desc">Route von {r["pins"][0]["ort"]} durch alle sieben Regierungsbezirke bis '
        f'{r["pins"][-1]["ort"]}, {len(r["stages"])} Etappen mit Übernachtung an Brauereien.</desc>',
        f'<path class="land" d="{paths["bayern"]}"/>',
    ]
    for name, d in paths["rb"].items():
        parts.append(f'<path class="district" data-district="{name}" d="{d}"/>')
    for name, (x, y) in DISTRICT_LABELS.items():
        parts.append(f'<text class="district-label" x="{x}" y="{y}" text-anchor="middle">{name}</text>')
    parts.append(f'<path class="route-ghost" d="{r["d"]}"/>')
    parts.append(f'<path class="route-line" id="route-line" d="{r["d"]}"/>')
    for i, p in enumerate(r["pins"]):
        # labels on the side with more room: west half -> right of pin, east half -> left
        side = "start" if p["x"] < 560 else "end"
        dx = 16 if side == "start" else -16
        dy = 6
        parts.append(
            f'<g class="pin" data-stop="{p["id"]}" data-at="{p["at"]}">'
            f'<circle class="halo" cx="{p["x"]:.1f}" cy="{p["y"]:.1f}" r="8"/>'
            f'<circle class="dot" cx="{p["x"]:.1f}" cy="{p["y"]:.1f}" r="8"/>'
            f'<text x="{p["x"] + dx:.1f}" y="{p["y"] + dy:.1f}" text-anchor="{side}">{html.escape(p["ort"])}</text>'
            "</g>"
        )
    parts.append(
        '<g class="compass" transform="translate(930 60)">'
        '<circle r="26" fill="none" stroke="rgba(201,160,78,.5)" stroke-dasharray="2 4"/>'
        '<path d="M0 -20 L6 0 L0 20 L-6 0Z" fill="rgba(201,160,78,.25)" stroke="#c9a04e"/>'
        '<path d="M0 -20 L6 0 L-6 0Z" fill="#c9a04e"/>'
        '<text y="-34" text-anchor="middle">N</text></g>'
    )
    parts.append("</svg>")
    return "".join(parts)


def fmt_km(v):
    return f"{v:.0f}" if v >= 10 else f"{v:.1f}".replace(".", ",")


def stages_html(brews):
    r = ROUTE
    by_id = {b["id"]: b for b in brews}
    e = html.escape
    out = []
    turns = [(-35, 60), (70, None), (0, -90), (-120, None), (45, -45), (-80, 30), (110, None),
             (-20, 90), (60, -60), (-100, None), (30, None), (-60, 45)]
    for s in r["stages"]:
        ziel = by_id[s["ziel_id"]]
        t = turns[(s["nr"] - 1) % len(turns)]
        chips = "".join(
            f'<span class="chip"><svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="5" fill="currentColor"/></svg>'
            f'{e(u["name"])} <small>{e(u["ort"])}</small></span>'
            for u in s["unterwegs"]
        )
        unterwegs = (f'<p class="stage-sub mono">Einkehr unterwegs</p><div class="brewery-chips">{chips}</div>'
                     if chips else "")
        region = f' · {e(ziel["landschaft"])}' if ziel.get("landschaft") else ""
        out.append(
            f'<li class="stage" data-district="{e(ziel["bezirk"])}" data-until="{s["ziel_id"]}">'
            f'<div class="stage-top">{tulip(*t)}<span class="mono">Etappe {s["nr"]:02d}'
            f'<span>{e(" · ".join(s["bezirke"]))}</span></span></div>'
            f'<h3>{e(s["von"].split(" (")[0])} → {e(s["nach"].split(" (")[0])}</h3>'
            f'<dl class="stage-facts"><div><dt class="mono">Strecke</dt><dd>{fmt_km(s["km"])} km</dd></div>'
            f'<div><dt class="mono">Unbefestigt (legal)</dt><dd>{fmt_km(s["unbefestigt_km"])} km</dd></div></dl>'
            f'<p><b>Übernachtung:</b> {e(ziel["name"])} in {e(ziel["ort"])}{region} – mit Gästezimmern.</p>'
            f"{unterwegs}"
            "</li>"
        )
    return "".join(out)


def pine(x, base, h, rnd):
    w = h * rnd.uniform(0.32, 0.42)
    tiers = 4
    pts = [(x, base - h)]
    for i in range(1, tiers + 1):
        y = base - h + h * i / (tiers + 0.6)
        ww = w * i / tiers
        pts += [(x + ww * 0.55, y - h * 0.05), (x + ww, y)]
    pts += [(x + w * 0.12, base - h * 0.08), (x + w * 0.12, base), (x - w * 0.12, base), (x - w * 0.12, base - h * 0.08)]
    for i in range(tiers, 0, -1):
        y = base - h + h * i / (tiers + 0.6)
        ww = w * i / tiers
        pts += [(x - ww, y), (x - ww * 0.55, y - h * 0.05)]
    return "M" + " ".join(f"{a:.1f},{b:.1f}" for a, b in pts) + "Z"


def ridge(rnd, y0, amp, n, W=1600):
    pts = []
    for i in range(n + 1):
        x = W * i / n
        y = y0 - amp * (0.5 + 0.5 * math.sin(i * 1.3 + rnd.random() * 2)) * rnd.uniform(0.6, 1.1)
        pts.append((x, y))
    return pts


def landscape():
    rnd = random.Random(2022)
    W, H = 1600, 400
    # far alps: sharp peaks
    alps = [(0, 260)]
    x = 0
    while x < W:
        x += rnd.uniform(60, 140)
        peak = rnd.uniform(70, 190)
        alps.append((x - rnd.uniform(20, 50), 260 - peak))
        alps.append((x, 260 - peak * rnd.uniform(0.3, 0.6)))
    alps += [(W, 260), (W, H), (0, H)]
    alps_d = "M" + " ".join(f"{a:.0f},{b:.0f}" for a, b in alps) + "Z"
    # snow caps: small highlights on peaks
    snow = []
    for (px, py) in alps[1:-3:2]:
        if py < 150:
            snow.append(f"M{px:.0f},{py:.0f} l-14,26 l8,-4 l6,8 l6,-10 l8,6Z")
    # mid forest line
    mid_base = 300
    mid = "".join(
        f'<path d="{pine(x, mid_base + rnd.uniform(-6, 6), rnd.uniform(46, 80), rnd)}"/>'
        for x in range(-10, W + 20, 22)
    )
    # front hill with track
    hill = "M0,350 C260,300 460,330 700,318 S1150,280 1600,330 L1600,400 L0,400Z"
    track = "M-20,352 C260,304 460,334 700,322 S1150,284 1620,334"
    front = "".join(
        f'<path d="{pine(x, 360 + rnd.uniform(-4, 10), rnd.uniform(70, 120), rnd)}"/>'
        for x in list(range(-20, 180, 34)) + list(range(1390, 1640, 30))
    )
    return (
        f'<svg viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMax slice" aria-hidden="true">'
        f'<g class="layer" data-depth="0.08"><path d="{alps_d}" fill="#1a2c44"/>'
        f'<path d="{"".join(snow)}" fill="rgba(216,230,243,.35)"/></g>'
        f'<g class="layer" data-depth="0.16" fill="#132236">{mid}<rect y="{mid_base}" width="{W}" height="120"/></g>'
        f'<g class="layer" data-depth="0.26"><path d="{hill}" fill="#0f1b2b"/>'
        f'<path id="hero-track" d="{track}" fill="none" stroke="rgba(224,154,45,.55)" stroke-width="2" stroke-dasharray="6 8"/>'
        f'<g fill="#0b1422">{front}</g>'
        f'<g id="rider" transform="translate(-100 0)">{rider()}</g></g>'
        "</svg>"
    )


def rider():
    # small dirt bike silhouette, origin at ground contact between wheels
    return (
        '<g transform="translate(-30 -40) scale(0.9)" fill="#0b1422" stroke="#e09a2d" stroke-width="1.2">'
        '<circle cx="12" cy="36" r="9" fill="none" stroke-width="3"/>'
        '<circle cx="54" cy="36" r="9" fill="none" stroke-width="3"/>'
        '<path d="M12 36 L26 22 L44 22 L54 36 M26 22 L34 32 L44 22 M44 22 L50 12 L56 12" fill="none" stroke-width="3"/>'
        '<path d="M28 20 L34 4 L42 4 L44 14 Z" fill="#e09a2d" stroke="none"/>'
        '<circle cx="39" cy="-2" r="5" fill="#e09a2d" stroke="none"/>'
        '<path d="M42 8 L52 13" stroke-width="3" fill="none"/>'
        '</g>'
    )


def tulip(turn, extra=None):
    """Roadbook tulip: dot = entry, arrow = exit direction (degrees, 0 = straight)."""
    a = math.radians(turn)
    cx, cy = 32, 30
    ex, ey = cx + 20 * math.sin(a), cy - 20 * math.cos(a)
    hx1, hy1 = ex - 7 * math.sin(a - 0.5), ey + 7 * math.cos(a - 0.5)
    hx2, hy2 = ex - 7 * math.sin(a + 0.5), ey + 7 * math.cos(a + 0.5)
    side = ""
    if extra is not None:
        b = math.radians(extra)
        side = f'<path d="M{cx} {cy} L{cx + 18 * math.sin(b):.1f} {cy - 18 * math.cos(b):.1f}" stroke="currentColor" stroke-width="2" opacity=".35"/>'
    return (
        '<svg class="tulip" viewBox="0 0 64 64" aria-hidden="true">'
        f"{side}"
        f'<circle cx="32" cy="54" r="4" fill="currentColor"/>'
        f'<path d="M32 54 L{cx} {cy} L{ex:.1f} {ey:.1f}" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>'
        f'<path d="M{ex:.1f} {ey:.1f} L{hx1:.1f} {hy1:.1f} L{hx2:.1f} {hy2:.1f}Z" fill="#e09a2d"/>'
        "</svg>"
    )


def text_ring(r, cx=300, cy=300, top=True):
    if top:
        return f"M{cx - r},{cy} a{r},{r} 0 1,1 {2 * r},0"
    return f"M{cx - r},{cy} a{r},{r} 0 0,0 {2 * r},0"


def bbs_seal():
    rauten = (
        '<pattern id="rauten" width="44" height="76" patternUnits="userSpaceOnUse" patternTransform="rotate(0)">'
        '<rect width="44" height="76" fill="#f3f1ea"/>'
        '<path d="M22 0 L44 38 L22 76 L0 38Z" fill="#2f7fc8"/></pattern>'
    )
    stitch = 'stroke-dasharray="7 4" stroke-linecap="round"'
    return f"""<svg viewBox="0 0 600 600" role="img" aria-labelledby="seal-title">
<title id="seal-title">Bavarian Beer Seekers MC. Nomads – Est. 2022</title>
<defs>{rauten}
<radialGradient id="felt" cx="50%" cy="45%" r="60%"><stop offset="0" stop-color="#18263a"/><stop offset="1" stop-color="#0a121e"/></radialGradient>
<clipPath id="inner"><circle cx="300" cy="300" r="178"/></clipPath>
<path id="ring-top" d="{text_ring(222)}"/>
<path id="ring-bottom" d="{text_ring(250, top=False)}"/>
</defs>
<circle cx="300" cy="300" r="292" fill="#0a121e"/>
<circle cx="300" cy="300" r="286" fill="none" stroke="#c9a04e" stroke-width="10"/>
<circle cx="300" cy="300" r="286" fill="none" stroke="#e7c47a" stroke-width="2" {stitch}/>
<circle cx="300" cy="300" r="272" fill="url(#felt)"/>
<circle cx="300" cy="300" r="186" fill="none" stroke="#c9a04e" stroke-width="7"/>
<circle cx="300" cy="300" r="186" fill="none" stroke="#e7c47a" stroke-width="1.5" {stitch}/>
<g clip-path="url(#inner)">
  <rect x="100" y="100" width="400" height="400" fill="#0f1a28"/>
  <path d="M300 100 L500 100 L500 500 L240 500 C300 420 330 300 300 100Z" fill="url(#rauten)"/>
  <image href="assets/bbs-skull.webp" x="102" y="150" width="372" height="360"/>
</g>
<g font-family="Big Shoulders Display, Impact, sans-serif" font-weight="900" fill="#d8b366" stroke="#5a4418" stroke-width="1" letter-spacing="3">
  <text font-size="54"><textPath href="#ring-top" startOffset="50%" text-anchor="middle">BAVARIAN BEER SEEKERS</textPath></text>
  <text font-size="58" letter-spacing="10"><textPath href="#ring-bottom" startOffset="50%" text-anchor="middle" dominant-baseline="hanging">NOMADS</textPath></text>
  <text x="70" y="316" font-size="34" text-anchor="middle">EST</text>
  <text x="70" y="352" font-size="34" text-anchor="middle">2022</text>
  <text x="532" y="334" font-size="36" text-anchor="middle">MC.</text>
  <text x="70" y="268" font-size="30" text-anchor="middle">+</text>
  <text x="532" y="268" font-size="30" text-anchor="middle">+</text>
</g>
</svg>"""


def stamp():
    return f"""<svg class="stamp" viewBox="0 0 200 200" aria-hidden="true">
<defs><path id="stamp-ring" d="M100,100 m-74,0 a74,74 0 1,1 148,0 a74,74 0 1,1 -148,0"/></defs>
<circle cx="100" cy="100" r="94" fill="none" stroke="currentColor" stroke-width="3"/>
<circle cx="100" cy="100" r="56" fill="none" stroke="currentColor" stroke-width="1.5" stroke-dasharray="3 4"/>
<text font-family="JetBrains Mono, monospace" font-size="13.5" font-weight="600" fill="currentColor" letter-spacing="3.2">
<textPath href="#stamp-ring">RIDE LEGAL · DRINK AFTER PARKING · EST. 2022 ·</textPath></text>
<text x="100" y="96" text-anchor="middle" font-family="Big Shoulders Display, Impact, sans-serif" font-weight="900" font-size="34" fill="currentColor">BBS</text>
<text x="100" y="122" text-anchor="middle" font-family="JetBrains Mono, monospace" font-size="11" fill="currentColor" letter-spacing="2">APPROVED</text>
</svg>"""


TULIPS = {
    "1": tulip(-35, 60),
    "2": tulip(70),
    "3": tulip(0, -90),
    "4": tulip(-120),
    "5": tulip(45, -45),
    "6": tulip(-80, 30),
    "7": tulip(110),
}


# same projection as the map data (see paths.json)
LON0, LON1, LAT0, LAT1 = 8.95, 13.87, 47.25, 50.58
K = math.cos(math.radians(48.9))
SCALE = 1000 / ((LON1 - LON0) * K)
BEZIRKE = ["Unterfranken", "Oberfranken", "Oberpfalz", "Mittelfranken", "Niederbayern", "Oberbayern", "Schwaben"]


def project(lon, lat):
    return (lon - LON0) * K * SCALE, (LAT1 - lat) * SCALE


def slug(text):
    t = text.lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        t = t.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


def load_breweries():
    f = TOOLS / "breweries.json"
    if not f.exists():
        return {"stand": "", "brauereien": []}
    data = json.loads(f.read_text(encoding="utf-8"))
    order = {b: i for i, b in enumerate(BEZIRKE)}
    data["brauereien"].sort(key=lambda b: (order.get(b["bezirk"], 9), -b["lat"]))
    return data


def atlas_map(brews):
    h = paths["H"]
    e = html.escape
    parts = [
        f'<svg id="atlas-map" viewBox="-20 -20 1040 {h + 40}" role="img" aria-label="Karte Bayern mit allen Brauereien des Atlas">',
        f'<path class="land" d="{paths["bayern"]}"/>',
    ]
    for name, d in paths["rb"].items():
        parts.append(f'<path class="district" data-district="{name}" d="{d}"/>')
    parts.append(f'<path class="route-ghost" d="{ROUTE["d"]}"/>')
    for b in brews:
        x, y = project(b["lon"], b["lat"])
        cls = "bdot room" if b.get("zimmer") == "ja" else "bdot"
        parts.append(
            f'<g class="{cls}" data-id="{b["id"]}" data-bezirk="{b["bezirk"]}" tabindex="0" role="button" '
            f'aria-label="{e(b["name"])}, {e(b["ort"])}"><circle cx="{x:.1f}" cy="{y:.1f}" r="7"/>'
            f'<title>{e(b["name"])} · {e(b["ort"])}</title></g>'
        )
    parts.append("</svg>")
    return "".join(parts)


def atlas_cards(brews):
    e = html.escape
    out = []
    for b in brews:
        badges = []
        if b.get("zimmer") == "ja":
            badges.append('<span class="badge room">Zimmer</span>')
        if b.get("einkehr") == "ja":
            badges.append('<span class="badge">Einkehr</span>')
        if b.get("seit") and b["seit"].lower() != "unbekannt":
            badges.append(f'<span class="badge">seit {e(b["seit"])}</span>')
        link = ""
        if b.get("website"):
            link = f'<a class="blink mono" href="{e(b["website"])}" target="_blank" rel="noopener">Website ↗</a>'
        out.append(
            f'<li class="bcard" id="b-{b["id"]}" data-id="{b["id"]}" data-bezirk="{b["bezirk"]}" data-zimmer="{b.get("zimmer", "unklar")}">'
            f'<div class="bcard-top mono"><span>{e(b["bezirk"])}</span><span>{e(b.get("landschaft", ""))}</span></div>'
            f'<h3>{e(b["name"])}</h3>'
            f'<p class="bplace">{e(b["ort"])} · Lkr. {e(b["landkreis"].replace("Landkreis ", ""))}</p>'
            f'<p class="bdesc">{e(b["beschreibung"])}</p>'
            + (f'<p class="bspec"><b class="mono">Im Glas</b> {e(b["spezialitaet"])}</p>' if b.get("spezialitaet") else "")
            + f'<div class="bfoot"><div class="badges">{"".join(badges)}</div>{link}</div>'
            "</li>"
        )
    return "".join(out)


def main():
    global ROUTE
    src = (TOOLS / "index.src.html").read_text(encoding="utf-8")
    ROUTE = load_route()
    atlas = load_breweries()
    brews = atlas["brauereien"]
    chips = "".join(
        f'<button type="button" class="fchip" data-bezirk="{b}">{b} <small>{sum(1 for x in brews if x["bezirk"] == b)}</small></button>'
        for b in BEZIRKE
    )
    out = (
        src.replace("{{ATLAS_MAP}}", atlas_map(brews))
        .replace("{{ATLAS_CARDS}}", atlas_cards(brews))
        .replace("{{ATLAS_CHIPS}}", chips)
        .replace("{{ATLAS_COUNT}}", str(len(brews)))
        .replace("{{ATLAS_STAND}}", atlas["stand"])
        .replace("{{MAP}}", bavaria_map())
        .replace("{{STAGES}}", stages_html(brews))
        .replace("{{ROUTE_KM}}", f"{ROUTE['total']:.0f}")
        .replace("{{ROUTE_N2}}", f"{len(ROUTE['stages']):02d}")
        .replace("{{ROUTE_N}}", str(len(ROUTE['stages'])))
        .replace("{{ROUTE_FIRST_DISTRICT}}", ROUTE["stages"][0]["bezirke"][0])
        .replace("{{ROUTE_UNPAVED_KM}}", f"{sum(x['unbefestigt_km'] for x in ROUTE['stages']):.0f}")
        .replace("{{ROUTE_UNPAVED_PCT}}", f"{sum(x['unbefestigt_km'] for x in ROUTE['stages']) / ROUTE['total'] * 100:.1f}".replace(".", ","))
        .replace("{{ZIEL_COORD}}", f"N {ROUTE['pins'][-1]['lat']:.2f}° · E {ROUTE['pins'][-1]['lon']:.2f}°")
        .replace("{{ZIEL_ORT}}", ROUTE["pins"][-1]["ort"])
        .replace("{{LANDSCAPE}}", landscape())
        .replace("{{SEAL}}", bbs_seal())
        .replace("{{STAMP}}", stamp())
    )
    out = re.sub(r"\{\{TULIP_(\d)\}\}", lambda m: TULIPS[m.group(1)], out)
    if not brews:
        # no researched data yet: ship the page without the atlas
        out = re.sub(r"<!--ATLAS-START-->.*?<!--ATLAS-END-->", "", out, flags=re.S)
        out = re.sub(r"\s*<!--ATLAS-NAV--><a href=\"#atlas\">Atlas</a>", "", out)
        out = out.replace('\n              <li><a href="#atlas">Brauerei-Atlas</a></li>', "")
        out = re.sub(r'<strong data-count="0">0</strong>\s*<span class="mono">Landbrauereien</span>\s*<p>[^<]*</p>',
                     '<strong data-count="10">10</strong>\n            <span class="mono">Brauerei-Ziele</span>\n            <p>Auf der Ideenliste. Tendenz: durstig.</p>', out)
    out = out.replace("<!--ATLAS-NAV-->", "").replace("<!--ATLAS-START-->", "").replace("<!--ATLAS-END-->", "")
    for b in brews:
        assert 47.2 < b["lat"] < 50.6 and 8.9 < b["lon"] < 13.9, b["name"]
    assert "{{" not in out, re.findall(r"\{\{\w+\}\}", out)
    (ROOT / "index.html").write_text(out, encoding="utf-8")
    print(f"index.html: {len(out) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
