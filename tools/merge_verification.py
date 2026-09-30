"""Merge two independent verification passes into tools/breweries.json.

Zero error tolerance:
- a brewery is kept only if BOTH verifiers confirm it exists, still brews on site,
  and place + district are correct
- a text field is kept only if BOTH confirm it; if both propose the same
  correction, the correction is used; otherwise the field is dropped
- zimmer/einkehr are "ja"/"nein" only if both agree, else "unklar"
- a dropped description is rebuilt from confirmed fields only

Usage: python3 tools/merge_verification.py round1.json round2.json stand
"""
import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent


def norm(v):
    return " ".join((v or "").split()).strip().rstrip("/").lower()


def agree(field, a, b, original):
    fa, fb = a[field], b[field]
    if fa["ok"] and fb["ok"]:
        return original
    if not fa["ok"] and not fb["ok"] and fa["korrektur"] and norm(fa["korrektur"]) == norm(fb["korrektur"]):
        return fa["korrektur"].strip()
    return None


def fallback_description(b):
    art = "Brauerei"
    n = b["name"].lower()
    if "kloster" in n:
        art = "Klosterbrauerei"
    elif "schloss" in n:
        art = "Schlossbrauerei"
    elif "gasthof" in n or "gasthaus" in n:
        art = "Brauereigasthof"
    where = f'in {b["ort"]}' + (f' ({b["landschaft"]})' if b.get("landschaft") else "")
    extra = []
    if b["einkehr"] == "ja":
        extra.append("Einkehr vor Ort")
    if b["zimmer"] == "ja":
        extra.append("Gästezimmern")
    tail = f' mit {" und ".join(extra)}' if extra else ""
    return f"{art} {where}{tail}."


def main(r1_path, r2_path, stand):
    base = {b["id"]: b for b in json.loads(Path(r1_path).read_text(encoding="utf-8"))["brauereien"]}
    r2 = json.loads(Path(r2_path).read_text(encoding="utf-8"))
    by_id = {}
    for c in r2["checks"]:
        for p in c["pruefungen"]:
            by_id.setdefault(p["id"], {})[c["lens"]] = p
    kept, dropped, report = [], [], []
    for bid, b in base.items():
        v = by_id.get(bid, {})
        if set(v) != {"A", "B"}:
            dropped.append((b["name"], "nicht von beiden Prüfern bewertet"))
            continue
        a, c = v["A"], v["B"]
        if not (a["existiert_und_braut_aktuell"] and c["existiert_und_braut_aktuell"]):
            dropped.append((b["name"], f'Betrieb nicht doppelt bestätigt: A: {a["notiz"]} | B: {c["notiz"]}'))
            continue
        if not (a["ort_und_landkreis_korrekt"] and c["ort_und_landkreis_korrekt"]):
            dropped.append((b["name"], f'Ort/Landkreis nicht doppelt bestätigt: A: {a["notiz"]} | B: {c["notiz"]}'))
            continue
        out = {k: b[k] for k in ("id", "name", "ort", "gemeinde", "landkreis", "bezirk", "lat", "lon") if k in b}
        changes = []
        for f in ("seit", "landschaft", "spezialitaet", "website", "beschreibung"):
            val = agree(f, a, c, b.get(f))
            if val != b.get(f):
                changes.append(f"{f}: {b.get(f)!r} -> {val!r}")
            if val and not (f == "seit" and "unbekannt" in val.lower()):
                out[f] = val
        for f in ("zimmer", "einkehr"):
            out[f] = a[f] if a[f] == c[f] else "unklar"
            if out[f] != b.get(f):
                changes.append(f"{f}: {b.get(f)} -> {out[f]}")
        if "beschreibung" not in out:
            out["beschreibung"] = fallback_description(out)
            changes.append("beschreibung aus bestätigten Feldern neu erzeugt")
        out["belege"] = sorted(set(a["belege"]) | set(c["belege"]))
        kept.append(out)
        if changes:
            report.append((b["name"], changes))
    (TOOLS / "breweries.json").write_text(
        json.dumps({"stand": stand, "brauereien": kept}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"übernommen: {len(kept)}, verworfen: {len(dropped)}")
    for n, why in dropped:
        print("VERWORFEN:", n, "—", why[:300])
    for n, ch in report:
        print("GEÄNDERT:", n, "|", "; ".join(ch)[:400])


if __name__ == "__main__":
    main(*sys.argv[1:4])
