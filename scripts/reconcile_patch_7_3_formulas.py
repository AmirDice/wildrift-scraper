"""Apply the 7.3 values that require structured fight-formula overrides."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "data" / "ability_formulas.json"


def component(formulas, champion, slot, name):
    return next(c for c in formulas[champion]["abilities"][slot]["damage"] if c["name"] == name)


def set_ratio(part, stat, value, *, old_stat=None):
    ratios = part.get("ratios", [])
    ratio = next((r for r in ratios if r["stat"] == (old_stat or stat)), None)
    if ratio is None and old_stat:
        ratio = next((r for r in ratios if r["stat"] == stat), None)
    if ratio is None:
        raise ValueError(f"missing {old_stat or stat} ratio in {part.get('name')}")
    ratio["stat"] = stat
    ratio["pct"] = value


def apply(formulas) -> None:
    set_ratio(component(formulas, "Draven", "1", "Spinning Axe"), "bonusAd", [80, 90, 100, 110])

    for name in ("Double Up - Primary", "Double Up - Ricochet"):
        set_ratio(component(formulas, "Miss Fortune", "1", name), "bonusAd", 110)
    component(formulas, "Miss Fortune", "4", "Bullet Time")["base"] = [20, 30, 40]

    zeri_p = component(formulas, "Zeri", "P", "Living Battery")
    set_ratio(zeri_p, "ad", [102, 104, 106, 108, 110])
    zeri_q = component(formulas, "Zeri", "1", "Electrocute!")
    zeri_q["base"] = [70, 100, 130, 160]
    set_ratio(zeri_q, "bonusAd", 80, old_stat="ad")
    set_ratio(zeri_q, "ap", [30, 35, 40, 45])
    zeri_r = component(formulas, "Zeri", "4", "Lightning Crash Nova")
    set_ratio(zeri_r, "bonusAd", 60)
    triple = component(formulas, "Zeri", "4", "Overcharged Triple Shot")
    triple["base"] = 0
    triple["ratios"] = [{"stat": "ad", "pct": 30}]

    akshan_q = component(formulas, "Akshan", "1", "Avengerang")
    set_ratio(akshan_q, "bonusAd", 70, old_stat="ad")
    akshan_r = component(formulas, "Akshan", "4", "Comeuppance")
    akshan_r["base"] = [25, 35, 45]
    set_ratio(akshan_r, "ad", 15)

    xayah_w = formulas["Xayah"]["abilities"]["2"]["steroids"]
    xayah_w[1]["pct"] = 30
    xayah_e = component(formulas, "Xayah", "3", "Bladecaller")
    xayah_e["base"] = [70, 80, 90, 100]
    set_ratio(xayah_e, "bonusAd", 50)

    trist_q = component(formulas, "Tristana", "2", "Rocket Jump")
    trist_q["ratios"] = [{"stat": "bonusAd", "pct": 80}, {"stat": "ap", "pct": 50}]
    trist_e = component(formulas, "Tristana", "3", "Explosive Charge (Active)")
    trist_e["base"] = [80, 100, 120, 140]
    trist_e["ratios"] = [{"stat": "bonusAd", "pct": 100}, {"stat": "ap", "pct": 50}]
    trist_r = component(formulas, "Tristana", "4", "Buster Shot")
    trist_r["ratios"] = [{"stat": "bonusAd", "pct": 70}, {"stat": "ap", "pct": 100}]

    sivir = formulas["Sivir"]["abilities"]
    sivir["P"]["steroids"][0]["flat"] = {"lvlRange": [55, 70]}
    sivir_q = component(formulas, "Sivir", "1", "Boomerang Blade")
    sivir_q["base"] = [70, 100, 130, 160]
    sivir_q["ratios"] = [{"stat": "bonusAd", "pct": 70}, {"stat": "ap", "pct": 60}]
    sivir_w = component(formulas, "Sivir", "2", "Ricochet Bounce")
    sivir_w["base"] = 0
    sivir_w["ratios"] = [{"stat": "ad", "pct": [37.5, 40, 42.5, 45]}]
    sivir["4"]["steroids"][0]["pct"] = [15, 20, 25]

    volley = formulas["Ashe"]["abilities"]["2"]["damage"]
    for part, base in zip(volley, [70, 110, 150, 190]):
        part["base"] = base
        set_ratio(part, "bonusAd", 100, old_stat="ad")

    senna_shield = formulas["Senna"]["abilities"]["4"]["defensive"][0]
    set_ratio(senna_shield, "ap", 50)
    senna_shield["note"] = "Shield also gains 2 per Mist stack."

    yunara_p = component(formulas, "Yunara", "P", "Vow of the First Lands")
    set_ratio(yunara_p, "ap", 8)
    formulas["Yunara"]["abilities"]["1"]["steroids"][0]["flat"] = [25, 35, 45, 55]

    set_ratio(component(formulas, "Yasuo", "4", "Last Breath"), "bonusAd", 150)
    yone = formulas["Yone"]["abilities"]
    yone["P"]["steroids"][1]["pct"] = 50
    yone_w = component(formulas, "Yone", "2", "Spirit Cleave")
    set_ratio(yone_w, "targetMaxHp", [9, 10, 11, 12])
    yone["2"]["defensive"][0]["base"] = [40, 55, 70, 85]
    set_ratio(yone["2"]["defensive"][0], "bonusAd", 60)

    kaisa_p = component(formulas, "Kai'Sa", "P", "Caustic Wounds On-Hit")
    kaisa_p["base"] = {"lvlRange": [5, 19]}
    set_ratio(kaisa_p, "ap", 12)

    cait_r = component(formulas, "Caitlyn", "4", "Ace in the Hole")
    cait_r["base"] = [250, 450, 650]
    set_ratio(cait_r, "bonusAd", 100)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    formulas = json.loads(PATH.read_text(encoding="utf-8"))
    before = json.dumps(formulas, sort_keys=True)
    apply(formulas)
    changed = before != json.dumps(formulas, sort_keys=True)
    print(f"formula corrections needed: {changed}")
    if args.write:
        PATH.write_text(json.dumps(formulas, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("wrote ability_formulas.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
