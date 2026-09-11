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
          "ccRemoval", "stasisSec", "drMagic", "drPhys", "ehp",
          # The damage path itself, not only the stats feeding it.
          "rot8", "rot8Autos",
          # `bonusAd` was here and `ad` was not, so a base-stat divergence was
          # invisible: Kayn resolved 112 AD in one engine and 126 in the other.
          "ad", "baseAd", "baseAs",
          # The ally model, ported to TS after shipping Python-only.
          "runeAllyHealPerSec", "allyShield", "shield", "support",
          # Area damage, which the TS engine had no channel for at all.
          "rot8Bolts",
          # THE FIGHT SURFACE, ported to Python on 2026-09-11 after living only
          # in TypeScript. duel/mutual_duel/score_vs_comp/champion_target are
          # what counter-mode ranking needs, and a port with nothing guarding it
          # would drift the same way the damage path silently did for as long as
          # Ashe's multiShot existed on one side only.
          "tgtHp", "tgtArmor", "tgtMr", "tgtBonusHp", "tgtSustain", "tgtShield",
          "tgtCcDepth", "tgtCcSeconds",
          "duelTtk", "duelDamage", "duelDps", "duelLockdown", "duelOverkill",
          "duelAutos", "duelPhys", "duelMagic",
          "compTtk", "compEhp", "compScore"]

# A plain stat block, so the two engines are compared on their own maths
# rather than on whatever championTarget currently returns.
PARITY_TARGET = {"hp": 2600, "armor": 90, "mr": 60, "bonusHp": 900}

# A FIXED opponent for the duel fields, so every battery case fights the same
# thing and a mismatch points at the attacker rather than at the target drifting.
# Enriched on purpose: sustain, shield and crowd control are exactly the
# channels the fight surface added, so a bare dummy would exercise none of them.
DUEL_FOE = {"label": "foe", "hp": 4100, "armor": 180, "mr": 70, "bonusHp": 1400,
            "sustainPerSec": 90.0, "shield": 1100.0, "ccDepth": 2,
            "ccSeconds": 1.5, "stasisSec": 0.0, "tenacity": 0.0,
            "basicAttackDr": 0.12, "asSlow": 0.15}
# The enemy carry for score_vs_comp, with a 60/40 physical split.
COMP_CARRY = {"name": "carry", "hp": 2900, "armor": 95, "mr": 60, "bonusHp": 950,
              "sustainPerSec": 40.0, "shield": 300.0, "ccDepth": 1,
              "ccSeconds": 1.5, "basicAttackDr": 0.0, "asSlow": 0.0,
              "stasisSec": 0.0}
#: ttk is None when the rotation never gets there; -1 travels through JSON.
NO_KILL = -1.0


def main() -> int:
    import web.fight_engine as fe
    battery = json.loads((ROOT / "scripts" / "engine_parity_battery.json").read_text("utf-8"))
    py = {}
    for champ, items, runes in battery:
        st = fe.resolve_stats(champ, 15, items, runes)
        pen = 1.0
        for factor in st.get("pctPenFactors") or []:
            pen *= 1 - factor
        # ROTATION DAMAGE, not just resolved stats. The harness diffed only
        # resolve_stats, so the entire damage path was unguarded in both
        # directions: Ashe's multiShot was modelled here and missing from the
        # TS port for as long as the mechanic has existed, worth 6% of her
        # output over an 8s window, and parity was green the whole time.
        # A fixed dummy target keeps this a pure engine comparison.
        rot = fe.rotation(champ, st, dict(PARITY_TARGET), 8.0, 15)
        _sh = (st["shield"] + st["shieldPctBonusHp"] * st["bonusHp"]
               + st["shieldPctMaxHp"] * st["hp"]) * (1 + st["healShieldAmp"])
        _dr = st["dr"] if st["dr"] < 1 else 0.99
        st = dict(st, ehp=round((st["hp"] + _sh) / fe._mixed_taken(st) / (1 - _dr), 2),
                  support=round(fe.support_value(champ, items, runes, 15), 2),
                  pctPen=1 - pen,
                  rot8=round(float(rot["total"]), 2),
                  rot8Bolts=round(float(rot.get("boltDmg", 0.0)), 2),
                  rot8Autos=round(float(rot.get("autoDmg", 0.0)), 2))
        # ---- the fight surface ------------------------------------------
        tgt = fe.champion_target(champ, 15, items, runes) or {}
        d = fe.duel(champ, items, runes, dict(DUEL_FOE), 15) or {}
        comp = fe.score_vs_comp(champ, items, runes, dict(COMP_CARRY), 0.6, 0.4, 15)
        st = dict(
            st,
            tgtHp=tgt.get("hp", 0), tgtArmor=tgt.get("armor", 0),
            tgtMr=tgt.get("mr", 0), tgtBonusHp=tgt.get("bonusHp", 0),
            tgtSustain=round(float(tgt.get("sustainPerSec", 0)), 2),
            tgtShield=round(float(tgt.get("shield", 0)), 2),
            tgtCcDepth=tgt.get("ccDepth", 0), tgtCcSeconds=tgt.get("ccSeconds", 0),
            duelTtk=NO_KILL if d.get("ttk") is None else d["ttk"],
            duelDamage=d.get("damage", 0), duelDps=d.get("dps", 0),
            duelLockdown=d.get("lockdown", 0), duelOverkill=d.get("overkill", 0),
            duelAutos=d.get("autos", 0),
            duelPhys=(d.get("byType") or {}).get("physical", 0),
            duelMagic=(d.get("byType") or {}).get("magic", 0),
            compTtk=NO_KILL if comp.get("ttkCarry") is None else comp["ttkCarry"],
            compEhp=comp.get("ehpVsComp", 0), compScore=comp.get("score", 0),
        )
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
