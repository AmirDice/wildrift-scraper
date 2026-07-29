"""Prompt assembly: the system message and every block of the user message.

Two principles run through this file.

The first is that the model knows nothing it is not told. Item, rune and boot
facts come only from the pools assembled here, because the supplied data IS the
current patch and the model's training data about Wild Rift items is stale.

The second is that a rule's tier has to match its truth. The previous prompt put
"you cannot equip two Spellblade items" and "prefer offensive boots" under one
heading called BUILD RULES (hard legality), which taught the model to treat a
preference as a prohibition -- and, worse, gave it no way to make a correct
unusual choice. Rules now arrive in three tiers, and only the first is absolute.
"""
from __future__ import annotations

import json
from pathlib import Path

from web.advisor import itemmeta, profiles, runemeta, threats

ROOT = Path(__file__).resolve().parent.parent.parent
DATA = ROOT / "data"

ITEMS = itemmeta.ITEMS
RULES = itemmeta.RULES


def _norm(text: str) -> str:
    return " ".join((text or "").split())


# --------------------------------------------------------------------------
# system message
# --------------------------------------------------------------------------

SYSTEM = (
    "You are a Challenger Wild Rift coach. Choose the loadout with the highest expected "
    "practical win rate under the supplied champion data, current item pool, role, "
    "playstyle, enemy context, and Wild Rift match tempo. Do not claim statistical "
    "superiority unless it is supported by supplied empirical data: you are making a "
    "strategic recommendation, not proving an optimum.\n"

    "KNOWLEDGE RULES -- two tiers:\n"
    "- GAME SENSE: use your full knowledge of this champion's mechanics, playstyle and "
    "known synergies or anti-synergies (e.g. attack-speed runes are wasted on a "
    "reload/magazine kit like Graves; energy champions ignore mana). Ground these "
    "conclusions in the supplied ability text, combat profile, scaling profile and build "
    "identity profile.\n"
    "- FACTS: item, boot and rune NAMES, stats, prices and effects come ONLY from the "
    "provided pools -- the data given IS the current patch, and your training data "
    "about items or patches is stale. Never invent or rename anything.\n"

    "READING THE PROFILES. The champion block carries a COMBAT PROFILE, a SCALING "
    "PROFILE and a BUILD IDENTITY PROFILE derived from that champion's ability text, "
    "cooldowns, parsed ratios and reviewed corrections. "
    "They exist because a coarse tag like 'this champion has on-hit effects' is true of "
    "most of the roster and tells you nothing. They are strong defaults, not measurements: "
    "derived, reviewed, and imperfect. Prefer them over your own impression of the "
    "champion, and when your reading of the SUPPLIED ability text clearly contradicts one, "
    "you may deviate -- but name the profile value you are overriding and quote the kit "
    "interaction that justifies it. An unstated deviation is an error:\n"
    "- A ratio existing does NOT make items granting that stat viable. A kit can carry a "
    "real AP ratio and still have no AP build; `buildPathViability` labels each stat core / "
    "secondary / not_viable, and that label OVERRIDES the raw ratio share. Only 'core' can "
    "anchor the normal primary path. The sole exception is an explicitly supplied, reviewed "
    "`alternativePath`, whose listed anchorStats may anchor only when that path was selected.\n"
    "- `repeatedOnHitReliance` distinguishes a champion who applies an on-hit effect ONCE "
    "from one whose damage depends on applying it over and over. 'high' is what makes "
    "attack-speed and on-hit stacking a CORE build plan. A lower value is a strong default "
    "AGAINST that plan, not a ban on the category: an individual attack-speed or on-hit "
    "item may still earn its slot when you name the specific kit interaction in the "
    "supplied ability text that repays it (an ability that counts attack hits, an "
    "empowered-attack window, a passive that procs per attack). On a caster kit with no "
    "such interaction that case does not exist -- do not invent one.\n"
    "- `spellbladeProcReliability` is about cast-then-attack rhythm, not about damage type.\n"
    "- BUILD IDENTITY IS AUTHORITATIVE for itemisation. `primaryCombatEngine` and "
    "`mainDamageSource` identify what contributes repeatedly across a real fight; "
    "`approvedBuildPaths` and `coreStats` define the trusted paths. Optimise that repeated "
    "source, not whichever isolated ability prints the largest ratio. An ultimate or a "
    "defensive/utility spell with one large AP ratio cannot redefine an AD auto-attacker, "
    "and a magic-damage tank may still build Armor/Health rather than AP. Stay inside "
    "approvedBuildPaths unless the user explicitly selected a supplied alternativePath.\n"

    "WILD RIFT TEMPO: an average match lasts roughly 15-20 minutes, and teamfights "
    "are short and rarely approach one minute. Early and mid-game power spikes, "
    "immediate combat value, and killing priority targets quickly are highly rewarded. "
    "Do not overvalue slow-ramping scaling that comes online after the game is usually "
    "decided.\n"

    "Method, in order: 1) read the kit, combat profile, scaling profile and build identity profile; "
    "2) read the enemy team's damage mix and threats, if one was supplied; "
    "3) SCORE 15-18 genuinely COMPETITIVE items into `candidateItemScores`, each 0-100 "
    "with a short reason; 4) separately, score EVERY item named in the MANDATORY ITEM "
    "AUDIT into `mandatoryAuditScores`. These are items whose text matches this kit "
    "closely enough to need an explicit verdict. They do NOT count toward the 15-18 "
    "competitive candidates, and most of them should be rejected with a low score -- "
    "that is the point of auditing them. An item may appear in both lists only when it "
    "is genuinely competitive; 5) choose the best FIVE items from your candidate list, "
    "maximising synergy, respecting the scaling profile, and optimising PURCHASE ORDER; "
    "6) pick tier-2 boots and note the tier-3 they become; 7) build a LEGAL rune page "
    "(1 keystone + 3 minors from ONE tree, one per slot, + 1 flex FROM A DIFFERENT TREE) -- cross-check the "
    "keystone against the supplied ability text and combat profile: a keystone scaling a "
    "stat the kit cannot use is a wasted keystone; 8) score the COMPLETE loadout; "
    "9) only after deciding, explain -- and the explanation must cover the RUNES and "
    "the BOOTS as well as the items: give a one-line reason for the keystone, each minor, "
    "the flex, and the boots (bootsReason, runeReasons), not only the item choices. "
    "(Counter mode skips this, see below.)\n"

    "WRITE A PLAY GUIDE for the build you just chose (`playGuide`). This is the part the "
    "player reads before a game, so it has to be about THIS BUILD on THIS CHAMPION, not "
    "about the champion in general. The test for every sentence: could it be copied onto "
    "a different build for the same champion without changing? If yes, it is filler -- "
    "delete it and write the version that names what you actually chose.\n"
    "THE WHOLE LOADOUT WORKS TOGETHER, so write about it that way. The items, the runes "
    "and the summoner spells were picked to do ONE thing between them, and the guide is "
    "where that plan gets said out loud: a keystone that needs a target reached explains "
    "why the boots were bought, a rune that rewards a takedown explains which fight to "
    "look for, a summoner explains how the engage starts. Name runes and summoners "
    "alongside items wherever they are part of the same play -- a guide that only "
    "discusses items is describing a third of the build.\n"
    "- earlyGame: how to play until the first item completes, given what that item and "
    "the rune page give you. Say what the early game lets the champion do that it could "
    "not do without them.\n"
    "- powerSpike: the moment this build turns on, named by ITEM COUNT or item, and what "
    "changes at that point -- what to look for on the map once it lands.\n"
    "- teamfight: how to actually fight with this loadout. Who to look for, from where, "
    "and in what order the abilities, items and summoners come out. Reference the combo "
    "if one was supplied.\n"
    "- pitfall: the mistake that wastes THIS build specifically. Not generic advice like "
    "'do not get caught' -- the one that follows from these items, these runes, these "
    "summoners, or this champion's cooldowns.\n"
    "Two or three plain sentences each, written to a player who knows the game. No "
    "headings, no bullet characters, no markdown.\n"

    "CHOOSE THE SUMMONER SPELLS from the pool given below, and treat it as a real "
    "decision rather than a habit: outside the jungle both slots are open, and the "
    "enemy team is the reason to deviate from the usual pair. Smite is the jungler's "
    "alone. Give the choice one line in `summonerReason`.\n"

    "PURCHASE ORDER IS TIMING, NOT A RANKING. Slot 1 is what you buy first, slot 5 "
    "is what you buy last and often never finish. Order each item by WHEN its effect "
    "is needed: the item that wins the lane, the first objective fight or the first "
    "skirmishes goes first. A cheap early-power item placed 4th or 5th is a mistake -- "
    "by then the game is usually decided, so if an item's value is early it goes early, "
    "and if it is not worth an early slot it does not belong in the five at all. "
    "Expensive scaling items and finishers go last. Cost is a signal but not the rule: "
    "justify any order where a cheaper item follows a more expensive one.\n"

    "SITUATIONAL SWAPS ARE REORDERINGS, NOT ONE-FOR-ONE TRADES. A real adaptation often "
    "inserts an item EARLY and pushes the rest back, rather than substituting in place. "
    "Each entry names the item, the position it is inserted at, the item it removes from "
    "the build, and the resulting five-item order in full. `resultingOrder` must contain "
    "exactly five legal non-boots items, must contain `item` at `insertAtPosition`, must "
    "not contain `removedItem`, and must obey hard legality. Most matchup problems have "
    "to be answered by the 2nd or 3rd purchase, because a swap that only happens at item "
    "5 arrives after the game is decided. Return an empty list rather than inventing "
    "swaps that do not matter.\n"

    # Stated as the acceptance test, because it IS one: the validator rejects a
    # list where every swap lands at 4 or 5, and the model was writing exactly
    # that and then paying a repair round trip to re-time it.
    "  HARD RULE ON TIMING: if you return any situational swaps at all, at least one "
    "MUST have insertAtPosition 2 or 3. A list where every swap lands at position 4 or "
    "5 will be rejected -- those answer a threat after it has already decided the game. "
    "Either re-time the swap that matters most to the purchase where the threat actually "
    "bites, or return an empty list.\n"

    "SITUATIONAL RUNES: when a rune answers a matchup better than an item does, return "
    "it in `situationalRunes`. Two forms are allowed. replacesType 'rune' swaps one of "
    "YOUR chosen runes: a minor must be replaced by another rune from the SAME tree and "
    "SAME slot, the flex may be replaced by any rune from a tree OTHER than the primary "
    "(the flex never joins the primary tree), and the keystone only by "
    "another keystone. replacesType 'item' means the rune covers a need well enough that "
    "one of your five items is no longer required -- and because that leaves a hole, you "
    "MUST also name `freedSlotItem`, the item that now takes the slot, and give the full "
    "`resultingItems` five-item build. A swap that empties a slot without filling it is "
    "an incomplete build, not advice. Say in `when` exactly what makes the swap correct. "
    "Empty list when nothing applies.\n"

    "TIE-BREAKERS, in order, when two items or builds are close: 1) earlier practical "
    "power spike; 2) stronger interaction with the champion's core combat pattern; "
    "3) greater usefulness across the supplied or unknown enemy context; 4) lower total "
    "or completion cost at similar expected value; 5) less reliance on perfect execution "
    "or a rare activation condition; 6) better role and stated playstyle fit; 7) higher "
    "supplied elite-player popularity, where that data is given and current; 8) higher "
    "rubric item score.\n"

    "ITEM SCORE RUBRIC (0-100): 30% kit and scaling synergy, 25% purchase timing and "
    "Wild Rift tempo, 20% role and playstyle fit, 15% robustness for the enemy context, "
    "10% gold efficiency and reliability. Subtract for redundancy with another item you "
    "chose, incompatible scaling, slow activation, or conditions that rarely occur.\n"

    "BUILD SCORE RUBRIC (0-100): 25% kit and scaling synergy, 20% purchase timing and "
    "power curve, 15% role and playstyle fit, 15% practical damage profile, 10% "
    "survivability and reliability, 10% usefulness across common or supplied "
    "compositions, 5% gold efficiency. Calibrate: 50 is playable/average, 70 is strong, "
    "85 is exceptional, 95+ is near-perfect and should be rare. The category scores "
    "(burst, sustainedDamage, survivability, mobility, utility, earlyPower) are COACH "
    "ESTIMATES grounded in the supplied facts. They are not measured or simulated "
    "outputs, and `confidence` should fall when the inputs are thin -- an unknown enemy "
    "team, or a champion whose supplied data is flagged as incomplete.\n"

    "Return ONLY JSON:\n"
    '{"candidateItemScores":[{"item":"<slug>","score":0-100,"reason":"..."}],'
    '"mandatoryAuditScores":[{"item":"<slug>","score":0-100,"reason":"..."}],'
    '"items":["<slug>", 5 in PURCHASE ORDER],'
    '"boots":"<tier-2 slug>","bootsUpgrade":"<tier-3 slug>",'
    '"situationalBoots":[{"boots":"<tier-2 slug>","when":"specific matchup condition"}],'
    '"buildScore":{"overall":0-100,"burst":0-100,"sustainedDamage":0-100,'
    '"survivability":0-100,"mobility":0-100,"utility":0-100,"earlyPower":0-100,'
    '"confidence":0-100,"reason":"short evidence-based verdict"},'
    '"runes":{"keystone":"<name>","primaryTree":"<tree>","minors":["<name>","<name>","<name>"],'
    '"flex":"<name>"},'
    '"summoners":["<spell>","<spell>"],'
    '"summonerReason":"one line: why these two for this kit and matchup",'
    '"bootsReason":"one line: why these boots for this kit and matchup",'
    '"runeReasons":{"keystone":"one line","minors":["one line","one line","one line"],'
    '"flex":"one line"},'
    '"situational":[{"item":"<slug>","insertAtPosition":1-5,"removedItem":"<slug>",'
    '"resultingOrder":["<slug>","<slug>","<slug>","<slug>","<slug>"],"when":"..."}],'
    '"situationalRunes":[{"rune":"<name>","replacesType":"rune"|"item",'
    '"replaces":"<rune name or item slug>","freedSlotItem":"<slug, item form only>",'
    '"atPosition":1-5,"resultingItems":["<slug>","<slug>","<slug>","<slug>","<slug>"],'
    '"when":"..."}],'
    '"snowballSwap":null or {"item":"<slug>","replaces":"<slug>","atPosition":1-5,'
    '"resultingOrder":["<slug>","<slug>","<slug>","<slug>","<slug>"],"when":"..."},'
    '"playGuide":{"earlyGame":"...","powerSpike":"...","teamfight":"...","pitfall":"..."},'
    '"why":["3-5 short bullets"]}'
)


# --------------------------------------------------------------------------
# champion block
# --------------------------------------------------------------------------

def champion_block(name: str, champions: dict, archetypes: dict, wrmeta: dict,
                   derived: dict | None = None) -> str:
    """The champion's facts. Pass `derived` when the caller already has it --
    deriving twice is wasted work and logs every data-quality warning twice."""
    champion = champions.get(name)
    if not champion:
        raise ValueError(f"unknown champion {name!r}")

    derived = derived if derived is not None else profiles.profile(name)
    lines = [
        f"CHAMPION: {name}",
        f"class={champion.get('class', '?')} primaryDamage={champion.get('primaryDamage', '?')}",
        "COMBAT PROFILE (derived from this kit's ability text, cooldowns and ratios): "
        + json.dumps(derived["combatProfile"]),
        "SCALING PROFILE (share of this kit's ratio weight, cooldown-adjusted): "
        + json.dumps(derived.get("scalingProfile", {})),
        "BUILD IDENTITY PROFILE (AUTHORITATIVE for itemisation and damage-source priority): "
        + json.dumps(derived["buildIdentityProfile"]),
    ]
    if derived.get("buildPathViability"):
        lines.append(
            "BUILD-PATH VIABILITY (this OVERRIDES the raw ratio share below): "
            + json.dumps(derived["buildPathViability"])
            + '. "core" can anchor a build; "secondary" may contribute to an item\'s value '
            'but cannot justify it alone; "not_viable" must not drive item choices. A large '
            "raw ratio does NOT authorise a build path -- viability does. A reviewed "
            "alternativePath is the only exception and applies only when selected.")
    if derived.get("rawRatioShare"):
        lines.append("rawRatioShare (informational only; viability above wins): "
                     + json.dumps(derived["rawRatioShare"]))
    for note in derived.get("scalingNotes", []):
        lines.append(f"  note: {note}")

    # Facts about HOW the kit attacks, which decide whether a stat is worth
    # buying at all. Placed before the ability prose so the model reads the
    # constraint before it reads the tooltip that tempts it.
    mechanics = profiles.kit_mechanics(name)
    if mechanics:
        lines.append("KIT MECHANICS (machine-extracted; these change which STATS are worth "
                     "buying, and they override any impression the ability prose gives):")
        lines.extend(f"  - {m}" for m in mechanics)

    if champion.get("baseStats"):
        lines.append("verifiedBaseStats=" + json.dumps(champion["baseStats"], ensure_ascii=False))
    if champion.get("statRules"):
        lines.append("verifiedStatRules=" + json.dumps(champion["statRules"], ensure_ascii=False))

    archetype = archetypes.get(name)
    if archetype:
        lines.append(f"archetype={archetype['archetype']} ({archetype.get('reason', '')})")

    meta = wrmeta.get(name) or {}
    for ability in profiles.normalized_abilities(name):
        mana = next((a.get("manaCosts") for a in meta.get("abilities", [])
                     if a.get("slot") == ability["slot"]), None)
        lines.append(f"[{ability['slot']}] {ability['name']}"
                     + (f" (mana {mana})" if mana else "")
                     + f": {ability['text']}")
    if meta.get("skillPriority"):
        lines.append(f"skillPriority={meta['skillPriority']}")

    if derived.get("structuredEffects"):
        lines.append(
            "STRUCTURED EFFECTS (machine-parsed; where these disagree with the ability "
            "prose above, TRUST THESE -- the prose is scraped and can be malformed): "
            + json.dumps(derived["structuredEffects"]))
    if derived.get("abilityTextArtifacts"):
        lines.append(
            "DATA QUALITY WARNING: the following ability text is known to be malformed. "
            "Do not infer a number from it; use the structured effects above, and lower "
            "your confidence score. " + " | ".join(derived["abilityTextArtifacts"]))
    return "\n".join(lines)


# --------------------------------------------------------------------------
# rules, in three tiers
# --------------------------------------------------------------------------

def rules_block(enemies_known: bool, combat_profile: dict) -> str:
    hard = RULES.get("hardExclusive") or {}
    redundancy = RULES.get("redundancyGroups") or {}
    situational = (RULES.get("situationalOnly") or {}).get("slugs", [])
    late = RULES.get("lateGameStrategic") or {}

    lines = [
        "RULES, IN THREE TIERS. Only tier A is absolute. Tier B is a strong default you "
        "may override with a stated reason. Tier C is preference.",
        "",
        "A. HARD LEGALITY -- the game forbids these; breaking one makes the build "
        "impossible, not merely bad:",
        "- Exactly 5 items, all NON-boots and all completed. Boots are chosen separately "
        "and never occupy one of the five slots.",
        "- Use only slugs from the supplied pools. Never invent or rename an item.",
        "- No duplicate items.",
        "- At most ONE item tagged `active` in the pool. Wild Rift allows a single "
        "activatable item per build. This is a CAP, not a discouragement: one active is "
        "normal and is often the most valuable slot in the build. Zero actives is a "
        "choice you should be able to defend, not a safe default.",
        "- Build AT MOST ONE item from each mutually exclusive group. These items cannot "
        "be equipped together in-game:",
    ]
    for name, group in hard.items():
        if name.startswith("_") or not isinstance(group, dict):
            continue
        lines.append(f"    {name}: {', '.join(group['slugs'])}")
    lines += [
        "- The rune page is 1 keystone + 3 minors from ONE tree, one from each of that "
        "tree's 3 slots, + 1 flex from any tree. The flex must not duplicate a rune "
        "already on the page.",
        "",
        "B. REDUNDANCY -- legal, and normally a waste. Build two from a group only when "
        "you say why the overlap earns its gold:",
    ]
    for name, group in redundancy.items():
        if name.startswith("_") or not isinstance(group, dict):
            continue
        lines.append(f"    {name}: {', '.join(group['slugs'])}")
        lines.append(f"      why it is usually wrong: {group.get('why', '')}")

    lines += [
        "",
        "C. DEFAULT STRATEGY -- preferences you may override with an argument:",
        # Actives were being skipped almost entirely, because the only thing the
        # prompt said about them was the one-per-build cap under HARD LEGALITY.
        # A rule that appears solely as a restriction teaches avoidance, so the
        # positive case has to be stated somewhere too.
        "- CONSIDER THE ACTIVE SLOT. Items tagged `active` do something no stat line can: "
        "Stasis buys three seconds against a burst combo, Shurelya's turns a won fight "
        "into a caught one, Goredrinker heals off a crowd. Ask whether one of them "
        "answers this kit's real problem better than another stat item. If none does, "
        "say so in `why` rather than leaving the slot unconsidered.",
    ]
    for preference in (RULES.get("defaultStrategy") or {}).get("preferences", []):
        lines.append(f"- {preference}")

    if situational:
        scope = ("The enemy team IS known, so these are available for the main five when "
                 "the composition justifies them -- name the threat."
                 if enemies_known else
                 "No enemy team was supplied, so there is nothing to react to: keep these "
                 "OUT of the main five and offer them as situational swaps instead.")
        lines += ["", f"- REACTIVE ITEMS: {', '.join(situational)}. {scope}"]

    # Guardian Angel and anything else that is neither reactive nor core.
    pattern = combat_profile.get("basicAttackPattern", "")
    for slug, cfg in late.items():
        if slug.startswith("_") or not isinstance(cfg, dict):
            continue
        allowed = cfg.get("allowedPatterns") or []
        if allowed and pattern not in allowed:
            lines.append(f"- {slug} does not suit this champion's combat pattern "
                         f"({pattern}); leave it out unless the enemy context demands it.")
            continue
        lines.append(
            f"- {slug} is a LATE STRATEGIC option, not a default and not merely reactive. "
            f"It may enter the main five only at position {cfg.get('minPosition', 4)} or "
            f"later, and only with an explicit reason. {cfg.get('why', '')}")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# unknown enemy team
# --------------------------------------------------------------------------

UNKNOWN_ENEMY_BLOCK = (
    "WHEN THE ENEMY TEAM IS UNKNOWN (it is, for this request):\n"
    "- Do not invent enemy champions, and do not describe threats you were not given.\n"
    "- Do not assume heavy healing, shielding, critical damage, crowd control or magic "
    "damage. You have no evidence for any of it.\n"
    "- Do not invent damage ratios or a damage split for the enemy team.\n"
    "- Optimise for a robust all-around build: prefer items that hold their value across "
    "the compositions this champion commonly meets in this role.\n"
    "- Use situational recommendations to cover the important deviations, each with the "
    "condition that would trigger it.\n"
    "- Never call a situational item mandatory. Without a supplied enemy condition there "
    "is nothing to make it mandatory.\n"
    "- Lower `confidence` relative to a fully specified matchup."
)


def enemy_threat_block(enemies: list[str], me: str, wrmeta: dict) -> str:
    """The structured team threat picture for a counter build.

    Replaces the old shallow per-enemy line. The team profile is weighted (a
    tank contributes less damage-threat than a carry), the priority threats are
    ranked, and hard counters carry the itemizable/non-itemizable split -- so
    the model prioritises real problems instead of counting mechanic tags.
    """
    profile = threats.team_threat_profile(enemies)
    priorities = threats.priority_threats(enemies, me)
    lines = [
        "ENEMY TEAM: " + ", ".join(enemies),
        "TEAM THREAT PROFILE (categorical, weighted by class so a tank does not count as "
        "much damage as a carry): " + json.dumps(profile),
        "PRIORITY THREATS (ranked; each names what items CAN answer and what only gameplay "
        "can): " + json.dumps(priorities),
    ]
    hard = [threats.hard_counter_warning(me, e, wrmeta) for e in enemies]
    hard = [h for h in hard if h]
    if hard:
        lines.append("HARD-COUNTER WARNINGS (evidence, NOT an instruction to spend several "
                     "slots on one enemy): " + json.dumps(hard))
    lines.append(
        "CHOOSE 2-4 PROBLEMS TO SOLVE. You cannot answer every threat with five items. "
        "Pick the threats with the best combination of severity, frequency, relevance to "
        "this champion's role, itemizability and number of enemies contributing, and build "
        "the answers into the MAIN FIVE. State the trade-offs you accept.")
    return "\n".join(lines)


def ally_context_block(allies: list[str]) -> str:
    """Allied-team context, or the explicit no-allies assumption."""
    if not allies:
        return (
            "NO ALLIED COMPOSITION was supplied. Build a self-sufficient version of the "
            "champion that keeps both its threat and enough durability to perform its normal "
            "role -- do not assume a frontline or peel that may not exist. Lower confidence "
            "slightly for the missing team context. Do not invent allied champions.")
    return ("ALLY TEAM: " + ", ".join(allies) + ". Account for what your team already "
            "provides (frontline, engage, peel, damage split) and cover what it lacks, "
            "rather than duplicating it.")


COUNTER_SUMMARY_SCHEMA = (
    '"counterSummary":{"confidence":0-100,"counterPriorities":["the 2-4 problems you chose '
    'to solve"],"threatResponses":[{"choiceType":"item|boots|rune","choice":"<name/slug>",'
    '"answers":["enemy or threat"],"reason":"..."}],"acceptedTradeoffs":["what you chose NOT '
    'to answer and why"],"unansweredThreats":["threats no reasonable build can fully '
    'answer"],"allyContextUsed":true|false}'
)


def boots_block(champion_class: str, enemies_known: bool, damage_path: str = "standard") -> str:
    """Boots, with defensive options gated on evidence rather than on class.

    The old rule forbade Mercury's Treads and Plated Steelcaps outright for
    Bruisers, Marksmen and Assassins. That is right with no enemy team -- there
    is nothing to be defensive about -- and wrong once the matchup is on the
    table, where the defensive boot is sometimes simply the higher win rate.
    """
    def stats(item: dict) -> str:
        return ",".join(
            f"{k}:{v['value']}{'%' if v.get('percent') else ''}"
            for k, v in (item.get("stats") or {}).items()
        ) or "none"

    def passives(item: dict) -> str:
        return " | ".join(_norm(p) for p in (item.get("passives") or [])) or "none"

    rows, defensive = [], []
    for slug, item in ITEMS.items():
        if item.get("bootsTier") != 2:
            continue
        upgrade = ITEMS.get(item.get("upgradesTo")) or {}
        row = (f"{slug} ({item['cost']}g; stats={stats(item)}; passives={passives(item)}) "
               f"-> upgrades at 10:00 to {item.get('upgradesTo')} "
               f"(stats={stats(upgrade)}; passives={passives(upgrade)})")
        (defensive if slug in DEFENSIVE_BOOTS else rows).append(row)

    block = ("BOOTS (pick ONE tier-2; it upgrades to the listed tier-3 for ~1000g after "
             "10:00 -- usually after your 2nd item):\n" + "\n".join(rows))

    # The damage path was reaching the ITEM rules and stopping there. The hard
    # legality rule says plainly that boots are not one of the five items, so
    # "do not mix in AD items" reads as not covering them -- and an AP Kayle
    # request came back with attack-speed boots.
    if damage_path in ("ap", "ad"):
        want, avoid = (("Ability Power", "attack speed or Attack Damage")
                       if damage_path == "ap" else
                       ("Attack Damage", "Ability Power"))
        block += (
            f"\n\nDAMAGE PATH APPLIES TO BOOTS TOO. This is an {damage_path.upper()} build. "
            f"If you take an OFFENSIVE boot it must be the one that gives {want}; a boot "
            f"whose stats are {avoid} does not belong in this build no matter how well it "
            f"suits the champion's usual playstyle. Defensive and neutral boots (armor, "
            f"magic resist, tenacity, ability haste, omnivamp) stay available on any path "
            f"and are often the right call -- this rule forbids the OFF-PATH offensive "
            f"boot, not every boot that is not {want}.")
    if defensive:
        if enemies_known:
            policy = (
                "DEFENSIVE BOOTS -- available as MAIN boots for this request, because an "
                "enemy team was supplied:\n"
                "Choose one of these as the main boots only when the enemy composition "
                "makes it the higher-win-rate choice, and say explicitly why surviving or "
                "holding combat uptime beats the offensive boot's damage. Naming the "
                "specific threat (which champions, which damage type, which lockdown) is "
                "required; 'they have some AD' is not a reason.\n")
        else:
            policy = (
                "DEFENSIVE BOOTS -- situationalBoots ONLY for this request:\n"
                "No enemy team was supplied, so there is no threat to itemise against. "
                "Take offensive or utility boots as the main choice and list BOTH "
                "defensive options in situationalBoots as general alternatives, each with "
                "the condition that would make it correct.\n")
        block += "\n" + policy + "\n".join(defensive)
    return block


DEFENSIVE_BOOTS = {"mercurys-treads", "plated-steelcaps"}


def item_pool_block(slugs: list[str]) -> str:
    """The candidate pool, one line per item, with structured tags appended."""
    rows = []
    for slug in slugs:
        item = ITEMS[slug]
        meta = itemmeta.metadata(slug)
        stats = ",".join(
            f"{k}:{v['value']}{'%' if v['percent'] else ''}"
            for k, v in item["stats"].items())
        passive = " | ".join(_norm(p) for p in item["passives"])
        tags = ",".join(meta["passiveTags"]) or "none"
        rows.append(f"{slug} [{item['category']}] {item['cost']}g {stats} "
                    f"(tempo={meta['tempoProfile']}; tags={tags}) :: {passive}")
    return ("ITEM POOL (the only items you may build; the description is the factual "
            "source, the tags are an index into it):\n" + "\n".join(rows))


def audit_block(slugs: list[str], combat_profile: dict) -> str:
    if not slugs:
        return ""
    return (
        "MANDATORY ITEM AUDIT:\n"
        f"This champion's combat profile is spellbladeProcReliability="
        f"{combat_profile.get('spellbladeProcReliability')}, repeatedOnHitReliance="
        f"{combat_profile.get('repeatedOnHitReliance')}, critValue="
        f"{combat_profile.get('critValue')}. The items below have passives that key off "
        "one of those, so each MUST appear in `mandatoryAuditScores` with an honest 0-100 "
        "score and a reason. Scoring is mandatory; selecting is not, and most of these "
        "should score low. These do NOT count toward your 15-18 competitive candidates:\n- "
        + "\n- ".join(slugs))


def filtered_note(removed: list[dict]) -> str:
    """Tell the model what was withheld, so it cannot silently miss something."""
    if not removed:
        return ""
    lines = [f"- {entry['item']}: {entry['reason']}" for entry in removed]
    return ("ITEMS WITHHELD FROM THE POOL (deterministic pre-filter, not a judgement about "
            "strength). If you believe one of these is genuinely correct for this build, "
            "say so in `why` rather than selecting it -- it is not in the pool and "
            "selecting it will fail validation:\n" + "\n".join(lines))
