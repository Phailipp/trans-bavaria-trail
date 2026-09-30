"""Independent legality + surface audit of a BRouter route (geojson with messages).

Re-implements the access rules separately from the routing profile, so a
mistake in one is caught by the other. Every segment must pass; otherwise the
route is rejected.
"""
import json
import sys

PROHIBITED = {"no", "private", "agricultural", "forestry", "destination", "permit", "customers",
              "delivery", "psv", "hov", "military", "emergency", "discouraged"}
EXPLICIT_YES = {"yes", "designated"}
PUBLIC = {"primary", "primary_link", "secondary", "secondary_link", "tertiary", "tertiary_link",
          "unclassified", "residential", "living_street"}
FORBIDDEN_HW = {"motorway", "motorway_link", "trunk", "trunk_link"}
UNPAVED_SURF = {"unpaved", "gravel", "fine_gravel", "compacted", "dirt", "earth", "ground", "grass",
                "pebblestone", "rock"}
UNPAVED_TT = {"grade2", "grade3", "grade4", "grade5"}


def parse_tags(s):
    out = {}
    for part in (s or "").split(" "):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k] = v
    return out


def legal(t):
    hw = t.get("highway", "")
    if hw in FORBIDDEN_HW:
        return False, f"highway={hw}"
    for k in ("motorcycle", "motor_vehicle", "vehicle", "access"):
        if t.get(k) in PROHIBITED:
            return False, f"{k}={t[k]}"
    if t.get("route") == "ferry":
        return False, "ferry"
    if hw in PUBLIC or t.get("living_street") == "yes":
        return True, ""
    if hw in ("track", "service", "road"):
        if any(t.get(k) in EXPLICIT_YES for k in ("motorcycle", "motor_vehicle", "motorcar", "vehicle", "access")):
            return True, ""
        return False, f"highway={hw} ohne Kfz-Freigabe"
    return False, f"highway={hw or '?'}"


def unpaved(t):
    return t.get("surface") in UNPAVED_SURF or t.get("tracktype") in UNPAVED_TT


def audit(geo):
    f = geo["features"][0]
    msgs = f["properties"]["messages"]
    head, rows = msgs[0], msgs[1:]
    i_dist, i_tags = head.index("Distance"), head.index("WayTags")
    total = unp = 0.0
    by_hw = {}
    violations = []
    for r in rows:
        d = float(r[i_dist])
        t = parse_tags(r[i_tags])
        ok, why = legal(t)
        if not ok:
            violations.append((why, d, r[i_tags]))
        total += d
        if unpaved(t):
            unp += d
        hw = t.get("highway", "?")
        by_hw[hw] = by_hw.get(hw, 0) + d
    return {
        "km": round(total / 1000, 1),
        "unbefestigt_km": round(unp / 1000, 1),
        "unbefestigt_anteil": round(unp / total * 100, 1) if total else 0,
        "hoehenmeter": int(f["properties"].get("filtered ascend", 0)),
        "nach_strassentyp_km": {k: round(v / 1000, 1) for k, v in sorted(by_hw.items(), key=lambda x: -x[1])},
        "verstoesse": violations,
    }


if __name__ == "__main__":
    res = audit(json.load(open(sys.argv[1])))
    v = res.pop("verstoesse")
    print(json.dumps(res, ensure_ascii=False))
    for why, d, tags in v:
        print(f"VERSTOSS {d:.0f} m: {why} | {tags}")
    sys.exit(1 if v else 0)
