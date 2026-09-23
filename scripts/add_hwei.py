"""Publish the reviewed Hwei kit to source data and frontend exports.

Offline, idempotent, and limited to Hwei. Run python -m scripts.add_hwei.
The two guides disagree: numeric provenance and modeling assumptions live in
data/hwei_kit.json. No ladder rates or model-confidence scores are invented.
"""
import copy
import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def read(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def write(rel, value, indent=2):
    (ROOT / rel).write_text(json.dumps(value, ensure_ascii=False, indent=indent), encoding="utf-8")


def upsert(rel, entry, key="Hwei", nested=None, indent=2):
    data = read(rel)
    (data[nested] if nested else data)[key] = entry
    write(rel, data, indent)


def source_record():
    k = read("data/hwei_kit.json")
    stats = {name: {"base": v[0], "perLevel": v[1], "lvl15": round(v[0] + 14*v[1], 4)}
             for name, v in k["baseStats"].items()}
    descriptions = {
        "P": "Different spell hits combine into a delayed area explosion: 33–333 by level +33% AP. Marks expire after 4s; repeated hits from one cast cannot repeatedly trigger it.",
        "1": "Choose QQ: 50/90/130/170 +75% AP +4/5/6/7% target maximum health; QW: 80/110/140/170 +30% AP, amplified against isolated or immobilized targets with missing health; or QE: 20/35/50/65 +30% AP eruption and 20/40/60/80 +30% AP per second in lava for 2.5s. Lava slows 30%.",
        "2": "Choose WQ: an allied movement-speed trail; WW: a 3s allied shield, initially 60/80/100/120 +35% AP, growing toward 108/128/148/168 +71% AP (15% weaker on allies); or WE: three empowered spell/attack hits, each adding 30/40/50/60 +15% AP magic damage and restoring 45/50/55/60 mana.",
        "3": "Choose EQ (fear), EW (root and vision), or EE (pull and slow). Each deals 70/120/170/220 +70% AP magic damage. Fear lasts 1/1.125/1.25/1.375s; root lasts 1.25/1.5/1.75/2s.",
        "4": "Attach an expanding, stacking slow for 3s. Deals 10/20/30 +5% AP magic damage per second, then explodes for 250/350/450 +75% AP magic damage. Wash Brush cancels subject selection; it is not the ultimate."
    }
    names = {"P":"Signature of the Visionary", "1":"Subject: Disaster", "2":"Subject: Serenity",
             "3":"Subject: Torment", "4":"Spiraling Despair"}
    icons = {"P":"hwei-signature-of-the-visionary.png", "1":"hwei-subject-disaster.png",
             "2":"hwei-subject-serenity.png", "3":"hwei-subject-torment.png", "4":"hwei-spiraling-despair.webp"}
    abilities = [{"slot":s,"name":names[s],"text":descriptions[s],
                  "cooldowns":[str(v) for v in k["cooldowns"].get(s, [])],
                  "damageTypes":["magic"],"scales":["ap"],
                  "tags":["shield"] if s=="2" else ["cc"] if s in ("1","3","4") else [],
                  "icon":"/abilities/"+icons[s]} for s in names]
    return {"slug":"hwei","name":"Hwei","class":"Mage","role":"Mid","baseStats":stats,
            "primaryDamage":"magic","scalesWith":["ap"],"mechanics":["cc","shield"],
            "abilities":abilities,"sourceUrl":k["source"],"skillPriority":["Q","E","W"],
            "icon":"https://ddragon.leagueoflegends.com/cdn/16.11.1/img/champion/Hwei.png"}


def formulas(k):
    def part(code, alt=False):
        sp = k["spells"][code]
        c = {"name":sp["name"],"type":"magic","base":sp["base"],
             "ratios":[{"stat":"ap","pct":sp["ap"]*100}],"when":"per cast"}
        if alt: c["alt"] = True
        if code=="QQ": c["ratios"].append({"stat":"targetMaxHp","pct":[x*100 for x in sp["targetMaxHp"]]})
        if code=="WE": c["hits"] = 3
        return c
    rec = source_record()
    out = {a["slot"]:{"name":a["name"],"cooldowns":k["cooldowns"].get(a["slot"],[]),
                      "damage":[],"steroids":[],"defensive":[],"unmodeled":[]} for a in rec["abilities"]}
    out["P"]["damage"] = [{"name":out["P"]["name"],"type":"magic","base":{"lvlRange":[33,333]},
                            "ratios":[{"stat":"ap","pct":33}],"when":"two distinct spells"}]
    out["1"]["damage"] = [part("QQ"),part("QW",True),part("QE",True)]
    out["2"]["damage"] = [part("WE")]
    out["2"]["defensive"] = [{"kind":"shield","base":k["spells"]["WW"]["maxShieldBase"],
                               "ratios":[{"stat":"ap","pct":71}],"alt":True}]
    out["3"]["damage"] = [part("EQ"),part("EW",True),part("EE",True)]
    out["4"]["damage"] = [part("R"),{"name":"Despair damage over time","type":"magic",
        "base":k["spells"]["R"]["tickBase"],"ratios":[{"stat":"ap","pct":5}],"hits":3,"when":"per cast"}]
    out["1"]["unmodeled"] = ["Only one Q choice per cooldown. QW execute interpolation and QE exposure are model assumptions."]
    out["2"]["unmodeled"] = ["WE is the default. WW replaces WE: shield and three empowered hits are never granted together. WQ movement is not simulated."]
    out["4"]["unmodeled"] = ["The timeline delays the explosion until three seconds after impact; the card shows full-duration damage."]
    return {"abilities":out,"hwei":k,"combo":["2","3","1","4","auto"],
            "knowledge":{"source":"reviewed-kit","asEfficiency":0.25,"resource":"mana",
                         "abilitiesCanCrit":False,"confidence":"medium"}}


def main():
    kit, champion = read("data/hwei_kit.json"), source_record()
    champs = read("data/champions_wr.json")
    champs = [champion if c["name"]=="Hwei" else c for c in champs]
    if not any(c["name"]=="Hwei" for c in champs): champs.append(champion)
    write("data/champions_wr.json",champs)
    upsert("data/ability_formulas.json",formulas(kit))
    upsert("data/wrf_guide_meta.json",{"skillOrder":kit["skillOrder"],"situational":[]})
    wm = read("data/wrmeta_champions.json").get("Hwei",{})
    wm.update({"name":"Hwei","class":"Mage","url":kit["source"],"released":True,
               "abilities":champion["abilities"],"skillOrder":kit["skillOrder"],"skillPriority":["1","3","2"]})
    upsert("data/wrmeta_champions.json",wm)
    combo = {"combo":["2","3","1","4","auto"],"confidence":"medium",
             "why":"WE, EQ, QQ, R, then autos. One choice per subject; R explodes after its 3-second delay. This is a modeled rotation, not a claim of an optimal combo."}
    upsert("data/champion_combos.json",combo,nested="champions",indent=1)
    upsert("web-next/src/data/champion_combos.json",combo,nested="champions",indent=1)
    upsert("data/champion_archetypes.json",{"archetype":"spellcaster","reason":"AP spell damage, area control and ranged poke; WE can empower spells and does not require an attack-speed build.","autoShare":0.15})
    identity = {"roles":["Mid","Support"],"classes":["Mage"],
        "identitySummary":"Long-range control mage with subject choices, area damage and allied shielding. Immobile and vulnerable when caught.",
        "combat":{"range":"long_ranged","engagement":"medium","playstyle":["poke","teamfight","zone_control"],"power_pattern":"mid_late_game","primary_win_condition":"teamfighting"},
        "teamComp":{"needs_frontline":True,"needs_peel":True,"benefits_from_engage":True,"benefits_from_cc":True,"primary_team_role":"damage_dealer"},
        "itemizationNeeds":{"primary_damage":"magic","scaling_priority":["ability_power","penetration","ability_haste","mana"],"defensive_priority":["armor","magic_resistance"],"situational_needs":["anti_heal_vs_healing","penetration_vs_resists","defensive_item_vs_burst"]},
        "hardLimits":{"neverArchetypes":[{"path":"AD Crit On-Hit","why":"Spells scale with AP; three WE charges also trigger on spell hits."}],"avoidStats":["ad","crit","lethality","armor_pen","lifesteal"]},
        "statPriorities":["ap","magic_pen","ability_haste","mana"]}
    upsert("data/champion_identity.json",identity,nested="champions",indent=1)
    draft = read("data/draft_archetypes.json")
    for tag in ("aoeUlt", "poke"):
        if "Hwei" not in draft["tags"][tag]: draft["tags"][tag].append("Hwei")
    write("data/draft_archetypes.json", draft)
    durations = read("data/hard_cc_durations.json")
    durations["champions"]["Hwei"] = 1.38
    write("data/hard_cc_durations.json", durations, 1)
    ult_shape = read("data/ult_shape.json")
    if "Hwei" not in ult_shape["aoeUlts"]: ult_shape["aoeUlts"].append("Hwei")
    ult_shape["aoeUlts"].sort()
    write("data/ult_shape.json", ult_shape)
    draft_kit = read("data/champion_draft_kit.json")
    draft_kit["champions"]["Hwei"] = {"frontline":0.0,"peel":0.65,"engage":0.35,
        "antiDive":0.7,"antiTank":0.45,"disruption":0.85,"disengage":0.75,
        "sustained":0.55,"magic":1.0,"physical":0.0,"globalPressure":0.0}
    write("data/champion_draft_kit.json", draft_kit)
    pending = read("web-next/src/data/new_champions.json")
    existing = next(c for c in pending["champions"] if c["slug"]=="hwei")
    existing.update(champion)
    existing["guideUrl"] = kit["source"]
    write("web-next/src/data/new_champions.json",pending)
    cards = [{**a,"key":{"P":"Passive","1":"Q","2":"W","3":"E","4":"R"}[a["slot"]]} for a in champion["abilities"]]
    upsert("web-next/src/data/champion_details.json",{"name":"Hwei","baseStats":champion["baseStats"],"abilities":cards,"skillPriority":["Q","E","W"]},key="hwei")

    # Run the real exporter into a temporary directory, then merge ONLY Hwei.
    # Other engine entries may contain uncommitted work in this workspace.
    from scripts import export_engine_data as exporter
    with tempfile.TemporaryDirectory(prefix="hwei-export-", dir=ROOT) as tmp:
        for attr, filename in (("OUT","engine.json"),("ROSTER_OUT","roster.json"),
                               ("STAT_RULES_OUT","stat_rules.json"),("COMBOS_OUT","champion_combos.json")):
            setattr(exporter,attr,Path(tmp)/filename)
        exporter.main()
        engine = read("web-next/src/data/engine.json")
        generated = json.loads((Path(tmp)/"engine.json").read_text(encoding="utf-8"))
        for key in ("champions","formulas"):
            engine[key]["Hwei"] = generated[key]["Hwei"]
        write("web-next/src/data/engine.json",engine,indent=None)
        roster = json.loads((Path(tmp)/"roster.json").read_text(encoding="utf-8"))
        upsert("web-next/src/data/roster.json",roster["Hwei"],indent=None)

    # A source-backed starter build, not an invented model-confidence score.
    builds = read("web-next/src/data/builds.json")
    items = engine["items"]
    def item(slug):
        meta = items[slug]
        return {"slug":slug,"name":meta["name"],"cost":meta["cost"],"icon":meta.get("icon",f"/items/{slug}.webp")}
    runes = copy.deepcopy(builds["Ziggs"]["builds"]["standard"]["runes"])
    runes["flexMinor"] = {"name":"Bone Plating","slug":"bone-plating","tree":"Resolve","icon":"https://www.wildriftfire.com/images/runes/bone-plating.png"}
    standard = {"summary":"Guide-based AP build. Fight estimates use WE → EQ → QQ → R; spell travel, passive timing and QW execution are approximations pending in-game validation.",
        "label":"Standard","pathLabel":"Magic",
        "coreBuild":[item(s) for s in ("blackfire-torch","infinity-orb","rabadons-deathcap","void-staff","zhonyas-hourglass")],
        "boots":item("spellslingers-shoes"),"bootsEarly":item("boots-of-mana"),"bootsUpgradeAfter":2,
        "enchantment":None,"situational":[],"runes":runes,
        "summoners":[{"name":"Flash","icon":"https://ddragon.leagueoflegends.com/cdn/16.11.1/img/spell/SummonerFlash.png"},
                     {"name":"Barrier","icon":"https://ddragon.leagueoflegends.com/cdn/16.11.1/img/spell/SummonerBarrier.png"}]}
    rec = {"name":"Hwei","class":"Mage","role":"Mid","damageProfile":"ap-burst-poke","canOneshot":False,
           "source":kit["source"],"variants":["standard"],"builds":{"standard":standard},
           "synergyNotes":["AP and magic penetration scale all damage choices. Haste shortens shared subject cooldowns.",
                           "WW trades away WE damage and mana restoration; the default build metrics use WE."]}
    from web import fight_engine as fe
    slugs = [i["slug"] for i in standard["coreBuild"]]+[standard["boots"]["slug"]]
    rune_names = [runes["keystone"]["name"]]+[r["name"] for r in runes["treeMinors"]]+[runes["flexMinor"]["name"]]
    standard["analysis"] = fe.analyze_build("Hwei",slugs,rune_names,15)
    for rel in ("data/champion_builds.json","web-next/src/data/builds.json"):
        upsert(rel,rec)
    print("Hwei source, formulas, builds, roster, identity and frontend exports updated.")


if __name__ == "__main__":
    main()
