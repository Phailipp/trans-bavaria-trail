"""Pull legal gravel segments (tools/gravel_segments.json) into the stages.

For each stage, candidate segments near the base track are tried one by one
(largest first). A segment is added as two via points (its start and end, in
driving direction) and kept only if
  - the stage stays legal (0 violations) and inside Bavaria,
  - the route really drives it (unpaved km grows by >= 70 % of its length),
  - the detour is worth it (extra km <= DETOUR_PER_KM x extra gravel km),
  - the stage stays <= MAX_STAGE_KM.
Writes tools/gravel_vias.json (full ordered via list per stage).
"""
import json
import sys
import time
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import check_breweries  # noqa: E402
import plan_route as pr  # noqa: E402
import route_check  # noqa: E402

CORRIDOR_KM = 12
DETOUR_PER_KM = 4
MAX_STAGE_KM = 190
MAX_TRIES = 14


def evaluate(pid, a, b, vias):
    geo = pr.route(pid, a, b, vias)
    audit = route_check.audit(geo)
    coords = geo["features"][0]["geometry"]["coordinates"]
    ok = not audit["verstoesse"] and all(pr.in_bavaria(c[0], c[1]) for c in coords[::4])
    return ok, audit, coords


def main():
    segs = json.loads((TOOLS / "gravel_segments.json").read_text())["segmente"]
    brews = {b["id"]: b for b in json.loads((TOOLS / "breweries.json").read_text(encoding="utf-8"))["brauereien"]}
    chain = [pr.START] + [brews[i] for i in pr.CHAIN]
    pid = pr.upload_profile()
    result, report = {}, []
    for n, (a, b) in enumerate(zip(chain, chain[1:]), 1):
        vias = list(pr.VIA.get(b["id"], []))
        ok, cur, coords = evaluate(pid, a, b, vias)
        assert ok, f"Basisroute Etappe {n} ungültig"
        base_km, base_unp = cur["km"], cur["unbefestigt_km"]
        sample = coords[::8]

        def dist_to_track(p):
            return min(check_breweries.km(p[1], p[0], c[1], c[0]) for c in sample)

        cands = []
        for s in segs:
            mid = ((s["start"][0] + s["end"][0]) / 2, (s["start"][1] + s["end"][1]) / 2)
            d = dist_to_track(mid)
            if d <= CORRIDOR_KM:
                cands.append((s["km"] / (1 + d), s, d))
        cands.sort(key=lambda x: -x[0])
        used = []
        for _, s, d in cands[:MAX_TRIES]:
            ends = pr.order_vias(coords, [tuple(s["start"]), tuple(s["end"])])
            trial = pr.order_vias(coords, vias + ends)
            ok, aud, new_coords = evaluate(pid, a, b, trial)
            time.sleep(1)
            if not ok:
                continue
            gain = aud["unbefestigt_km"] - cur["unbefestigt_km"]
            extra = aud["km"] - cur["km"]
            if gain >= 0.7 * s["km"] and extra <= DETOUR_PER_KM * gain and aud["km"] <= MAX_STAGE_KM:
                vias, cur = trial, aud
                used.append({"km": s["km"], "abstand_km": round(d, 1), "start": s["start"], "end": s["end"]})
        result[b["id"]] = vias
        line = (f'E{n} {a["ort"]} → {b["ort"]}: {base_km} km/{base_unp} km unbefestigt  →  '
                f'{cur["km"]} km/{cur["unbefestigt_km"]} km unbefestigt ({len(used)} Abschnitte eingebaut)')
        print(line)
        report.append({"etappe": n, "vorher_km": base_km, "vorher_unbefestigt": base_unp,
                       "nachher_km": cur["km"], "nachher_unbefestigt": cur["unbefestigt_km"], "abschnitte": used})
    (TOOLS / "gravel_vias.json").write_text(json.dumps({"vias": result, "bericht": report}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
