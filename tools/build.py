"""Renders index.html from tools/index.src.html.

Generates the inline SVGs (Bavaria map with real district borders, route,
hero landscape, roadbook tulips, BBS seal) so the page ships as one static
file. Run: python3 tools/build.py
"""
import json
import math
import random
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"

paths = json.loads((TOOLS / "paths.json").read_text())
route = json.loads((TOOLS / "route.json").read_text(encoding="utf-8"))

DISTRICT_LABELS = {
    "Unterfranken": (150, 205),
    "Oberfranken": (500, 110),
    "Oberpfalz": (655, 370),
    "Mittelfranken": (300, 330),
    "Niederbayern": (760, 600),
    "Oberbayern": (640, 760),
    "Schwaben": (250, 640),
}


def route_fractions():
    """Fraction of the route length at which each stop is reached."""
    pts = [tuple(map(float, p.split(","))) for p in route["route"][1:].split(" ")]
    cum = [0.0]
    for a, b in zip(pts, pts[1:]):
        cum.append(cum[-1] + math.dist(a, b))
    total = cum[-1]
    out = {}
    for s in route["stops"]:
        i = min(range(len(pts)), key=lambda k: math.dist(pts[k], (s["x"], s["y"])))
        out[s["id"]] = round(cum[i] / total, 4)
    return out


def bavaria_map():
    frac = route_fractions()
    h = paths["H"]
    parts = [
        f'<svg id="bayern-map" viewBox="-20 -20 1040 {h + 40}" role="img" '
        f'aria-labelledby="map-title map-desc">',
        '<title id="map-title">Karte Bayern mit Etappen-Idee des Trans Bavaria Trail</title>',
        '<desc id="map-desc">Schematische Linie vom Main bei Miltenberg durch alle sieben '
        "Regierungsbezirke bis ins Allgäu nach Rettenberg, mit zehn Brauerei-Zielen.</desc>",
        f'<path class="land" d="{paths["bayern"]}"/>',
    ]
    for name, d in paths["rb"].items():
        parts.append(f'<path class="district" data-district="{name}" d="{d}"/>')
    for name, (x, y) in DISTRICT_LABELS.items():
        parts.append(f'<text class="district-label" x="{x}" y="{y}" text-anchor="middle">{name}</text>')
    parts.append(f'<path class="route-ghost" d="{route["route"]}"/>')
    parts.append(f'<path class="route-line" id="route-line" d="{route["route"]}"/>')
    label_side = {"kreuzberg": "end", "faust": "start", "zoigl": "start", "kuchlbauer": "start",
                  "weltenburg": "start", "spalt": "end", "rothenbach": "start", "schlenkerla": "end",
                  "andechs": "start", "zoetler": "start"}
    offsets = {"weltenburg": (0, -14), "kuchlbauer": (0, 16), "schlenkerla": (0, -12),
               "rothenbach": (0, 16), "kreuzberg": (0, 6)}
    for s in route["stops"]:
        side = label_side.get(s["id"], "start")
        dx = 18 if side == "start" else -18
        ox, oy = offsets.get(s["id"], (0, 6))
        parts.append(
            f'<g class="pin" data-stop="{s["id"]}" data-at="{frac[s["id"]]}">'
            f'<circle class="halo" cx="{s["x"]}" cy="{s["y"]}" r="9"/>'
            f'<circle class="dot" cx="{s["x"]}" cy="{s["y"]}" r="9"/>'
            f'<text x="{s["x"] + dx + ox}" y="{s["y"] + oy}" text-anchor="{side}">{s["town"].split(" ")[0]}</text>'
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


def main():
    src = (TOOLS / "index.src.html").read_text(encoding="utf-8")
    out = (
        src.replace("{{MAP}}", bavaria_map())
        .replace("{{LANDSCAPE}}", landscape())
        .replace("{{SEAL}}", bbs_seal())
        .replace("{{STAMP}}", stamp())
    )
    out = re.sub(r"\{\{TULIP_(\d)\}\}", lambda m: TULIPS[m.group(1)], out)
    assert "{{" not in out, re.findall(r"\{\{\w+\}\}", out)
    (ROOT / "index.html").write_text(out, encoding="utf-8")
    print(f"index.html: {len(out) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
