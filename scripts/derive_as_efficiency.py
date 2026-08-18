"""Measure attackSpeedEfficiency instead of estimating it.

The knob's own definition is "1.0 = a normal marksman, lower means attack
speed converts poorly on this kit", and today's values are LLM guesses -- the
prompt prints "ESTIMATED, not measured" next to them. They do not track the
engine's own behaviour: Ekko is discounted to 0.3 while 54% of his damage
flows through basic attacks, more than Gwen at 0.6.

So measure the thing the definition describes:

    lift(champion) = (damage with +45% attack speed) / (damage without) - 1
    asEfficiency   = lift(champion) / lift(reference marksman)

Method notes that matter:
  * every champion is measured with asEfficiency forced to 1.0 IN MEMORY,
    otherwise the measurement reads back the value it is trying to replace.
  * each champion gets a NEUTRAL two-item package of its own damage type,
    chosen to contain no attack speed of any kind, so the lift measures the
    KIT and not the items around it.
  * the reference is the mean lift of several marksmen, which is what "a
    normal marksman" means, rather than one champion's quirks.

RESULT, 2026-08-19: THE OUTPUT OF THIS SCRIPT SHOULD NOT BE ADOPTED. It fails
its own sanity check -- by the knob's definition a marksman should sit at the
top, yet marksmen measure 10-14% while Ekko measures 24% and Master Yi 28%.

The confound is base attack speed. A fixed +45% item is a smaller RELATIVE
increase for a champion who already attacks fast: Jinx goes 1.95 -> 2.32
(+19%) where Ekko goes 0.80 -> 1.16 (+45%). So this measures marginal damage
per attack-speed point, which is a real quantity but not the one the knob
holds.

What asEfficiency actually encodes is the fraction of a fight a champion
spends auto-attacking at all -- the rotation assumes continuous attacking at
st.as, and the knob compensates for a caster who is casting and repositioning
instead. That is a behavioural fact about how the champion is played. It is
not present in the item or ability data, so the engine cannot derive it, and
no amount of simulation will produce it. It stays a judgement parameter.

Kept as the record of a measurement that was worth making and did not work,
and as the harness if a better formulation appears.

    python -m scripts.derive_as_efficiency
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent

import web.fight_engine as fe  # noqa: E402

LEVEL = 15
WINDOW = 8.0
AS_PROBE = 45.0          # one Nashor's worth of attack speed
TARGET = {"name": "dummy", "hp": 3000.0, "armor": 60.0, "mr": 45.0, "bonusHp": 1200.0}

REFERENCE_MARKSMEN = ["Jinx", "Caitlyn", "Miss Fortune", "Ashe"]
SUBJECTS = ["Veigar", "Lux", "Diana", "Gwen", "Ekko", "Kayle", "Ashe",
            "Jinx", "Katarina", "Ahri", "Riven", "Jax", "Master Yi", "Kai'Sa"]


def neutral_package(champ: str) -> list[str]:
    """Two offensive items of this champion's damage type carrying NO attack
    speed, so the probe measures the kit rather than the package."""
    magic = (fe.CHAMPS.get(champ) or {}).get("primaryDamage") == "magic"
    wanted = "Magic" if magic else "Physical"
    out = []
    for slug, item in fe.ITEMS.items():
        if len(out) == 2:
            break
        if item.get("category") != wanted:
            continue
        if set(item.get("categories") or []) & {"Basic", "MidTier"}:
            continue
        stats = item.get("stats") or {}
        fx = fe.ENGINE_FX.get(slug) or {}
        if "attackSpeed" in stats or fx.get("asPctPassive") or fx.get("everyNthAttack"):
            continue
        if fx.get("extraOnHitOnSpellblade") or any(k.startswith("onHit") for k in fx):
            continue          # on-hit items amplify AS; that is the item, not the kit
        out.append(slug)
    return out


def lift(champ: str) -> tuple[float, list[str]]:
    """Fractional damage gain from +45% attack speed on a neutral package."""
    items = neutral_package(champ)
    base_st = fe.resolve_stats(champ, LEVEL, items, [])
    fast_st = fe.resolve_stats(champ, LEVEL, items, [], bonus={"attackSpeed": AS_PROBE})
    base = fe.rotation(champ, base_st, TARGET, WINDOW, LEVEL)["total"]
    fast = fe.rotation(champ, fast_st, TARGET, WINDOW, LEVEL)["total"]
    return ((fast - base) / base if base else 0.0), items


def main() -> int:
    # Neutralise the knob everywhere first: measuring through the current
    # values would just recover the current values.
    original = {}
    for name, rec in fe.FORMULAS.items():
        know = rec.setdefault("knowledge", {})
        original[name] = know.get("asEfficiency")
        know["asEfficiency"] = 1.0

    ref_lifts = {c: lift(c)[0] for c in REFERENCE_MARKSMEN if c in fe.CHAMPS}
    reference = sum(ref_lifts.values()) / len(ref_lifts)
    print(f"reference 'normal marksman' lift from +{AS_PROBE:.0f}% attack speed: "
          f"{reference * 100:.1f}%")
    print("  " + ", ".join(f"{c} {v * 100:.0f}%" for c, v in ref_lifts.items()))
    print()
    print(f"{'champion':<12} {'current':>8} {'measured lift':>14} {'proposed':>9} {'change':>8}   package")
    rows = []
    for champ in SUBJECTS:
        if champ not in fe.CHAMPS:
            print(f"{champ:<12} (not in roster)")
            continue
        value, items = lift(champ)
        proposed = max(0.1, min(1.0, value / reference)) if reference else 1.0
        current = original.get(champ)
        delta = ("" if current is None else f"{proposed - current:+.2f}")
        rows.append((champ, current, value, proposed))
        print(f"{champ:<12} {str(current):>8} {value * 100:>13.1f}% {proposed:>9.2f} {delta:>8}   "
              f"{','.join(s.split('-')[0] for s in items)}")

    for name, value in original.items():       # restore, this script writes nothing
        if value is None:
            fe.FORMULAS[name].get("knowledge", {}).pop("asEfficiency", None)
        else:
            fe.FORMULAS[name]["knowledge"]["asEfficiency"] = value
    print("\n(in-memory only; no file was modified)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
