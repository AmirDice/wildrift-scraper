"""Reconcile 7.3 champion tooltip changes the generic numeric matcher missed.

The source scrape phrases ratios differently from Riot's patch notes, so the
generic patcher cannot safely match every rework. These replacements are
asserted against the exact stored prose and applied to both the canonical
champion data and the generated frontend cards.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "data" / "champions_wr.json"
FRONTEND = ROOT / "web-next" / "src" / "data" / "champion_details.json"


REWRITES = [
    ("Ezreal", "Mystic Shot", "reduces Ezreal's other ability cooldowns", "reduces all of Ezreal's ability cooldowns"),
    ("Kai'Sa", "Second Skin", "deal 5 ( +15% AP ) bonus magic damage", "deal 4 - 18 (based on level) ( +12% AP plus current Plasma stacks scaling ) bonus magic damage"),
    ("Kai'Sa", "Second Skin", "15% ( +0.025% AP ) bonus magic damage of their missing Health", "15% ( +5% AP ) bonus magic damage of their missing Health"),
    ("Kai'Sa", "Supercharge", "50% / 60% / 60% / 65% ( +50% Attack Speed ) Movement Speed", "50% / 55% / 60% / 65% Movement Speed, increased by 50% / 55% / 60% / 65% of bonus Attack Speed (maximum 100% / 110% / 120% / 130%)"),
    ("Caitlyn", "Ace in the Hole", "200 / 375 / 550 ( +100% bonus AD )", "250 / 450 / 650 ( +100% bonus AD )"),
    ("Draven", "League of Draven", "80 bonus gold + 4 per stack", "60 bonus gold + 3 per stack"),
    ("Draven", "Spinning Axe", "+100% / 110% / 120% / 130% bonus AD", "+80% / 90% / 100% / 110% bonus AD"),
    ("Draven", "Whirling Death", "Deals 5% less damage as it damages targets, minimum 60%", "Deals 5% less damage per target hit, minimum 50%"),
    ("Draven", "Whirling Death", "Upon reversal, the reduction is reset do deal full damage.", "Upon reversal, the reduction is reset to deal full damage. Enemy champions with less current Health than Draven's Adoration stacks are executed."),
    ("Miss Fortune", "Love Tap", "15 ( +70% bonus AD ) X ( 1 + 100% Critical Rate)", "( 15 +40% bonus AD ) × ( 0.6 + Critical Rate × 0.4 )"),
    ("Miss Fortune", "Double Up", "The second hit will Critically Strike for 130% / 140% / 150% / 160% damage", "The second hit deals 60% of current Critical Damage"),
    ("Miss Fortune", "Make it Rain", "slowing enemies by 30% / 40% / 50% / 60%", "slowing enemies by 40% ( +0.06% AP )"),
    ("Miss Fortune", "Bullet Time", "each deal 39 ( 60% AD +20% AP ) physical damage", "each deal 20 / 30 / 40 ( +60% AD +20% AP ) physical damage"),
    ("Miss Fortune", "Bullet Time", "Each wave can Crit for 130% damage.", "Each wave can Crit for 130% damage, increased by 30% of Critical Damage above 200%."),
    ("Samira", "Daredevil Impulse", "Each one increases her Style from \"E\" to \"S\" .", "Each one increases her Style from \"E\" to \"S\" and grants 3% - 4% Movement Speed per grade based on level."),
    ("Samira", "Blade Whirl", "+80% AD", "+50% bonus AD"),
    ("Samira", "Wild Rush", "25% / 30% / 25% / 30% attack speed", "25% / 30% / 35% / 40% Attack Speed"),
    ("Samira", "Inferno Trigger", "Each shot can critically strike.", "Each shot can critically strike and trigger 66.7% Life Steal."),
    ("Zeri", "Living Battery", "+105% / 110% / 115% / 120% / 125% AD", "+102% / 104% / 106% / 108% / 110% AD"),
    ("Zeri", "Electrocute!", "35 / 60 / 85 / 110 ( +55% / 70% / 85% / 100% AD +30% / 35% / 40% / 45% AP )", "70 / 100 / 130 / 160 ( +80% bonus AD +30% / 35% / 40% / 45% AP )"),
    ("Zeri", "Electrocute!", "decays over 2 seconds", "decays over 1.5 seconds"),
    ("Zeri", "Ultrashock Laser", "+100% AD +40% AP", "+100% AD +50% AP"),
    ("Zeri", "Ultrashock Laser", "Critically Striking champions and monsters.", "Critically Striking champions and monsters for 150% plus half of Critical Damage above 200%."),
    ("Zeri", "Lightning Crash", "deal 14 physical damage", "deal 30% AD physical damage"),
    ("Akshan", "Dirty Fighting", "gain bonus decaying movement speed", "gain 20 - 80 (based on level) Movement Speed multiplied by (1 + 100% bonus Attack Speed), decaying over time"),
    ("Akshan", "Avengerang", "+85% AD", "+70% bonus AD"),
    ("Akshan", "Heroic Swing", "Critically Strike for 0.7% damage", "Critically Strike for 70% of current Critical Damage"),
    ("Akshan", "Comeuppance", "20 / 30 / 40 ( +15% AD )", "25 / 35 / 45 ( +15% AD )"),
    ("Akshan", "Comeuppance", "80 / 120 / 160 ( +45% AD )", "75 / 105 / 135 ( +45% AD )"),
    ("Akshan", "Comeuppance", "30% of Critical Rate", "30% of Critical Rate plus 30% of Critical Damage above 200%, scaled by Critical Rate"),
    ("Xayah", "Deadly Plumage", "25% / 30% / 35% / 40% Movement Speed", "30% Movement Speed"),
    ("Xayah", "Bladecaller", "60 / 70 / 80 / 90 ( +50% bonus AD )", "( 70 / 80 / 90 / 100 +50% bonus AD ) multiplied by Critical Rate and Critical Damage scaling"),
    ("Tristana", "Explosive Charge", "50 / 75 / 100 / 125 ( +100% bonus AD +50% AP )", "( 80 / 100 / 120 / 140 +100% bonus AD +50% AP ) multiplied by Critical Rate and Critical Damage scaling"),
    ("Tristana", "Buster Shot", "300 / 350 / 400 ( +100% AP )", "300 / 350 / 400 ( +70% bonus AD +100% AP )"),
    ("Sivir", "Fleet of Foot", "Gains 31 Movement Speed", "Gains 55 - 70 Movement Speed (based on level)"),
    ("Sivir", "Boomerang Blade", "10 / 30 / 50 / 70 ( 75% / 80% / 85% / 90% AD + 60% AP )", "( 70 / 100 / 130 / 160 +70% bonus AD +60% AP ) multiplied by Critical Rate and Critical Damage scaling"),
    ("Sivir", "Boomerang Blade", "Deals 80% damage against non-champion enemies", "Deals 75% damage against non-champion enemies"),
    ("Sivir", "Ricochet", "37.5 / 40 / 42.5 / 45 ( +15% / 18% / 21% / 24% AD )", "37.5% / 40% / 42.5% / 45% AD"),
    ("Sivir", "On The Hunt", "Grants 15% bonus Movement Speed", "Grants 15% / 20% / 25% bonus Movement Speed"),
    ("Sivir", "On The Hunt", "an additional 25% bonus Movement Speed", "an additional 15% / 20% / 25% bonus Movement Speed"),
    ("Ashe", "Frost Shot", "slow targets hit by 15%", "slow targets hit by 20% - 30% (based on level)"),
    ("Ashe", "Frost Shot", "Attacks deal 1100% bonus damage , scaling with her Critical Damage.", "Attacks gain bonus damage from Critical Rate and from Critical Damage above 200%."),
    ("Jhin", "Curtain Call", "The 4th shot crits for 200% damage", "The 4th shot crits for current Critical Damage"),
    ("Senna", "Absolution", "Every 20 stacks of Mist grant 15 Attack Range and 10% Critical Chance.", "Every 20 stacks of Mist grant 15 Attack Range and 10% Critical Chance. Critical strikes from basic attacks deal 90% of normal critical strike damage."),
    ("Senna", "Dawning Shadow", "+120% AD +50% AP ) physical damage", "+120% AD +70% AP ) physical damage"),
    ("Senna", "Dawning Shadow", "+50% AP + 2.5 per Mist", "+50% AP + 2 per Mist"),
    ("Yunara", "Vow of the First Lands", "additional 10% (per 100 AP )", "additional 8% (per 100 AP )"),
    ("Yunara", "Cultivation of Spirit", "22% / 35% / 47% / 60% Attack Speed", "25% / 35% / 45% / 55% Attack Speed"),
    ("Yasuo", "Way of the Wanderer", "at a rate of 0.5 Attack Damge per 1% Critical Rate.", "at a rate of 0.5 Attack Damage per 1% Critical Rate. Yasuo's basic attacks and Steel Tempest critical strikes deal 90% of normal critical strike damage."),
    ("Yasuo", "Steel Tempest", "Critically Strike for 75% bonus damage", "Critically Strike for 90% of normal critical strike damage"),
    ("Yone", "Way of the Hunter", "at a rate of 0.5 Attack Damage per 1% Critical Rate.", "at a rate of 0.5 Attack Damage per 1% Critical Rate. Yone's basic attacks and Mortal Steel critical strikes deal 90% of normal critical strike damage."),
    ("Yone", "Spirit Cleave", "shield that absorbs 45 ( +60% bonus AD )", "shield that absorbs 40 / 55 / 70 / 85 ( +60% bonus AD )"),
    ("Viego", "Sovereign's Domination", "Heals for 7%", "Heals for 5%"),
    ("Viego", "Blade of the Ruined King", "Attacks deal bonus physical damage equal to 2% / 3% / 4% / 5% of the target's current Health", "Attacks deal bonus physical damage equal to 2% / 3% / 4% / 5% of the target's current Health, with critical damage scaled to 80%"),
    ("Viego", "Blade of the Ruined King", "strikes twice, dealing physical damage equal to 15% of AD", "strikes twice, dealing physical damage equal to 15% of AD with critical damage scaled to 80%"),
    ("Olaf", "Undertow", "+120% AD", "+105% bonus AD"),
]


def apply(champions: list[dict]) -> int:
    by_name = {c["name"]: c for c in champions}
    changed = 0
    for champion, ability_name, old, new in REWRITES:
        ability = next(a for a in by_name[champion]["abilities"] if a["name"] == ability_name)
        text = ability.get("text") or ""
        if new in text:
            continue
        if old not in text:
            raise ValueError(f"{champion} / {ability_name}: missing asserted text {old!r}")
        ability["text"] = text.replace(old, new, 1)
        changed += 1
    return changed


def sync_frontend(champions: list[dict], frontend: dict) -> None:
    for champion in champions:
        card = frontend.get(champion["slug"])
        if not card:
            continue
        by_slot = {a["slot"]: a for a in champion.get("abilities") or []}
        for ability in card.get("abilities") or []:
            source = by_slot.get(ability.get("slot"))
            if source:
                ability["text"] = source.get("text", "")
                ability["cooldowns"] = source.get("cooldowns", [])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    champions = json.loads(SOURCE.read_text(encoding="utf-8"))
    frontend = json.loads(FRONTEND.read_text(encoding="utf-8"))
    changed = apply(champions)
    sync_frontend(champions, frontend)
    print(f"{changed} patch 7.3 tooltip corrections")
    if args.write:
        SOURCE.write_text(json.dumps(champions, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        FRONTEND.write_text(json.dumps(frontend, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("wrote champions_wr.json and champion_details.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
