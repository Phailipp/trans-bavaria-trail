"""Plan -> live-verify -> block failures -> re-plan, until the live OSM check is clean.

Every problem point from tools/osm_verify.py becomes a 40 m no-go circle for
that stage (tools/nogos.json); BRouter then routes around it.
"""
import json
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
MAX_ROUNDS = 6
RADIUS_M = 40


def drop_suspect_gravel(probs, radius_km=1.5):
    """Remove a whole inserted gravel segment (both via points) if a live-check problem lies near it."""
    sys.path.insert(0, str(TOOLS))
    import check_breweries
    import plan_route as pr
    gv_path = TOOLS / "gravel_vias.json"
    gv = json.loads(gv_path.read_text())
    ids = list(pr.CHAIN)
    removed = 0
    for rep in gv["bericht"]:
        sid = ids[rep["etappe"] - 1]
        stage_probs = [p for p in probs if p["etappe"] == rep["etappe"]]
        keep = []
        for seg in rep["abschnitte"]:
            pts = [seg["start"], seg["end"],
                   [(seg["start"][0] + seg["end"][0]) / 2, (seg["start"][1] + seg["end"][1]) / 2]]
            bad = any(check_breweries.km(p["lat"], p["lon"], q[1], q[0]) <= radius_km for p in stage_probs for q in pts)
            if bad:
                ends = {tuple(seg["start"]), tuple(seg["end"])}
                gv["vias"][sid] = [v for v in gv["vias"][sid] if tuple(v) not in ends]
                removed += 1
            else:
                keep.append(seg)
        rep["abschnitte"] = keep
    gv_path.write_text(json.dumps(gv, ensure_ascii=False, indent=1))
    print(f"{removed} verdächtige Schotter-Abschnitte aus den Etappen entfernt")


def run(script):
    r = subprocess.run([sys.executable, str(TOOLS / script)], capture_output=True, text=True)
    print(r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-500:])
    return r.returncode


def main():
    nog_path = TOOLS / "nogos.json"
    for rnd in range(1, MAX_ROUNDS + 1):
        print(f"--- Runde {rnd}")
        if run("plan_route.py") != 0:
            raise SystemExit("plan_route fehlgeschlagen")
        rc = run("osm_verify.py")
        if rc == 0:
            print("Live-Prüfung sauber.")
            return
        if rc != 1:
            raise SystemExit("Live-Prüfung abgebrochen (API) – nichts gesperrt")
        probs = json.loads((TOOLS / "osm_verify.json").read_text())["probleme"]
        drop_suspect_gravel(probs)
        nog = json.loads(nog_path.read_text()) if nog_path.exists() else {}
        for p in probs:
            nog.setdefault(str(p["etappe"]), []).append([p["lon"], p["lat"], RADIUS_M])
        nog_path.write_text(json.dumps(nog, indent=1))
        print(f"{len(probs)} Stellen gesperrt, neu rechnen")
    raise SystemExit("nach max. Runden nicht sauber")


if __name__ == "__main__":
    main()
