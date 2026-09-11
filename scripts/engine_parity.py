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
          "cleaveFlat", "cleavePctBonusHp", "healShieldAmp", "shieldPctMaxHp", "apAmp",
          "armor", "mr", "dotPctMaxHp", "extraOnHitApplications", "as", "baseAs",
          # Penetration, vamp and tenacity. Added after the two engines were found
          # to disagree on every one of them with nothing here to catch it: the
          # item stat line and the extracted itemFx both carried the same effect,
          # Python applied both and the TS port applied neither (or, for
          # physicalPen, ignored the percent flag and charged 36% as 36 flat).
          "flatPen", "pctPen", "flatMagicPen", "pctMagicPen",
          "vamp", "lifestealPct", "omnivampPct", "tenacity",
          "dr", "giant", "execute", "armorShred",
          # Target-side, crowd-control and clone channels, all added at once
          # and all previously unreadable by either engine.
          "grievousWounds", "shieldCut", "basicAttackDr", "targetAsSlow",
          "ccRemoval", "stasisSec"]


def main() -> int:
    import web.fight_engine as fe
    battery = json.loads((ROOT / "scripts" / "engine_parity_battery.json").read_text("utf-8"))
    py = {}
    for champ, items, runes in battery:
        st = fe.resolve_stats(champ, 15, items, runes)
        pen = 1.0
        for factor in st.get("pctPenFactors") or []:
            pen *= 1 - factor
        st = dict(st, pctPen=1 - pen)
        key = f"{champ}|{'+'.join(items)}|{'+'.join(runes)}"
        py[key] = {f: round(float(st.get(f, 0)), 4) for f in FIELDS}

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
