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
        if run("osm_verify.py") == 0:
            print("Live-Prüfung sauber.")
            return
        probs = json.loads((TOOLS / "osm_verify.json").read_text())["probleme"]
        nog = json.loads(nog_path.read_text()) if nog_path.exists() else {}
        for p in probs:
            nog.setdefault(str(p["etappe"]), []).append([p["lon"], p["lat"], RADIUS_M])
        nog_path.write_text(json.dumps(nog, indent=1))
        print(f"{len(probs)} Stellen gesperrt, neu rechnen")
    raise SystemExit("nach max. Runden nicht sauber")


if __name__ == "__main__":
    main()
