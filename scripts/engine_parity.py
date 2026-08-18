"""Engine parity check: the Python fight engine and the TS port must resolve
identical stats for identical inputs, or the advisor argues from different
numbers than the site displays. Runs both sides over the battery in
scripts/engine_parity_battery.json and diffs field-by-field.

Usage:  python -m scripts.engine_parity
Add a case to the battery whenever an itemFx key gains an engine channel.
"""
import io
import json
import subprocess
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent

FIELDS = ["ap", "bonusAd", "hp", "bonusHp", "mana", "haste", "crit", "critMult",
          "onHitPhys", "onHitMagic", "onHitPctMaxHp", "onHitPctCurrentHp",
          "mrShred", "mrShredFlat", "spellbladeApPct", "spellbladeMagic",
          "cleaveFlat", "cleavePctBonusHp", "healShieldAmp", "shieldPctMaxHp", "apAmp"]


def main() -> int:
    import web.fight_engine as fe
    battery = json.loads((ROOT / "scripts" / "engine_parity_battery.json").read_text("utf-8"))
    py = {}
    for champ, items, runes in battery:
        st = fe.resolve_stats(champ, 15, items, runes)
        py[f"{champ}|{'+'.join(items)}"] = {f: round(float(st.get(f, 0)), 4) for f in FIELDS}

    ts_out = ROOT / "scratch_ts_stats.json"
    subprocess.run(["npx", "tsx", "scripts/engine_parity.ts"],
                   cwd=ROOT / "web-next", check=True, shell=True)
    ts = json.loads(ts_out.read_text("utf-8"))

    mismatches = 0
    for key, a in py.items():
        b = ts.get(key, {})
        for f, va in a.items():
            vb = b.get(f, 0)
            tol = max(0.01, abs(va) * 0.005)
            if abs(va - vb) > tol:
                print(f"MISMATCH {key} .{f}: py={va} ts={vb}")
                mismatches += 1
    ts_out.unlink(missing_ok=True)
    print(f"parity: {len(py)} cases, {mismatches} mismatches")
    return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
