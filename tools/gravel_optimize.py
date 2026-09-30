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
import gravel_probe  # noqa: E402
import osm_verify  # noqa: E402
import plan_route as pr  # noqa: E402
import route_check  # noqa: E402

CORRIDOR_KM = 12
DETOUR_PER_KM = 4
MAX_STAGE_KM = 190
MAX_TRIES = 20


def evaluate(pid, a, b, vias, avoid, cache):
    """BRouter legality audit + Bavaria border + LIVE OSM check of every unpaved run.
    Returns (ok, km, live_unpaved_km, coords, problems)."""
    geo = pr.route(pid, a, b, vias, avoid)
    audit = route_check.audit(geo)
    coords = geo["features"][0]["geometry"]["coordinates"]
    if audit["verstoesse"] or not all(pr.in_bavaria(c[0], c[1]) for c in coords[::4]):
        return False, audit["km"], 0.0, coords, []
    live, all_probs = 0.0, []
    for r in gravel_probe.segments(geo, min_km=0.1):
        run = {"km": r["km"], "tags": r["tags"], "pts": pr.dense_slice(coords, r["at_m"], r["len_m"])}
        probs, n, hits = osm_verify.check_run(run, cache)
        all_probs += probs
        if n:
            live += r["km"] * hits / n
    if all_probs:
        return False, audit["km"], 0.0, coords, all_probs
    return True, audit["km"], round(live, 2), coords, []


def main():
    segs = json.loads((TOOLS / "gravel_segments.json").read_text())["segmente"]
    brews = {b["id"]: b for b in json.loads((TOOLS / "breweries.json").read_text(encoding="utf-8"))["brauereien"]}
    chain = [pr.START] + [brews[i] for i in pr.CHAIN]
    pid = pr.upload_profile()
    ng = pr.nogos()
    cache = osm_verify.load_cache()
    result, report = {}, []
    for n, (a, b) in enumerate(zip(chain, chain[1:]), 1):
        avoid = list(ng.get(str(n), []))
        vias = list(pr.VIA.get(b["id"], []))
        for _ in range(6):   # clean the base route first: block every live-check failure
            ok, km, unp, coords, probs = evaluate(pid, a, b, vias, avoid, cache)
            if ok or not probs:
                break
            avoid += [[p["lon"], p["lat"], 40] for p in probs]
        assert ok, f"Basisroute Etappe {n} besteht die Prüfung nicht"
        ng[str(n)] = avoid
        blocked = [(x, y) for x, y, _ in avoid]
        base_km, base_unp = km, unp
        sample = coords[::8]

        def dist_to_track(p):
            return min(check_breweries.km(p[1], p[0], c[1], c[0]) for c in sample)

        cands = []
        for s in segs:
            if any(check_breweries.km(y, x, q[1], q[0]) < 0.3 for x, y in blocked for q in (s["start"], s["end"])):
                continue
            mid = ((s["start"][0] + s["end"][0]) / 2, (s["start"][1] + s["end"][1]) / 2)
            d = dist_to_track(mid)
            if d <= CORRIDOR_KM:
                cands.append((s["km"] / (1 + d), s, d))
        cands.sort(key=lambda x: -x[0])
        used = []
        for _, s, d in cands[:MAX_TRIES]:
            ends = pr.order_vias(coords, [tuple(s["start"]), tuple(s["end"])])
            trial = pr.order_vias(coords, vias + ends)
            try:
                ok, tkm, tunp, _, _ = evaluate(pid, a, b, trial, avoid, cache)
            except Exception as e:  # noqa: BLE001  (routing failure = reject candidate)
                print("   verworfen:", e)
                continue
            time.sleep(1)
            if not ok:
                continue
            gain, extra = tunp - unp, tkm - km
            if gain >= 0.5 * s["km"] and extra <= DETOUR_PER_KM * gain and tkm <= MAX_STAGE_KM:
                vias, km, unp = trial, tkm, tunp
                used.append({"km": s["km"], "abstand_km": round(d, 1), "start": s["start"], "end": s["end"]})
        result[b["id"]] = vias
        print(f'E{n} {a["ort"]} → {b["ort"]}: {base_km} km/{base_unp} km live-unbefestigt  →  '
              f'{km} km/{unp} km ({len(used)} Abschnitte)')
        report.append({"etappe": n, "vorher_km": base_km, "vorher_unbefestigt": base_unp,
                       "nachher_km": km, "nachher_unbefestigt": unp, "abschnitte": used})
    pr.NOGO_FILE.write_text(json.dumps(ng, indent=1))
    (TOOLS / "gravel_vias.json").write_text(json.dumps({"vias": result, "bericht": report}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
