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
    "most of the roster and tells you nothing. Trust them over your own impression of "
    "the champion:\n"
    "- A ratio existing does NOT make items granting that stat viable. A kit can carry a "
    "real AP ratio and still have no AP build; `buildPathViability` labels each stat core / "
    "secondary / not_viable, and that label OVERRIDES the raw ratio share. Only 'core' can "
    "anchor the normal primary path. The sole exception is an explicitly supplied, reviewed "
    "`alternativePath`, whose listed anchorStats may anchor only when that path was selected.\n"
    "- `repeatedOnHitReliance` distinguishes a champion who applies an on-hit effect ONCE "
    "from one whose damage depends on applying it over and over. Only the latter wants "
    "attack-speed and on-hit stacking.\n"
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

    "ITEM-TO-ITEM SYNERGY IS A FIELD, NOT A FLOURISH. The synergy share above covers "
    "BOTH directions -- item-to-kit and item-to-item -- and `synergyWith` is where the "
    "second one is recorded. For every item you score, list the slugs of the items IN "
    "YOUR FINAL FIVE that it multiplies, or that multiply it.\n"
    "- A MULTIPLIER earns a score its own stat line cannot justify: extra on-hit "
    "applications, added attack instances, an amplifier across a whole rotation. It "
    "gets better with every partner, so list them all.\n"
    "- The reverse holds. An item unlocked BY another is worth little without it; do "
    "not score it as though the partner were bought unless you are buying it.\n"
    "- Penetration, amplification and shred stack against the SAME target, so a second "
    "source is worth LESS than the first. That is redundancy -- the negative case of "
    "this same rule, not a separate one.\n"
    "- Leave `synergyWith` empty when an item genuinely stands alone. [] is an honest "
    "answer; naming an item you did not build is not.\n"

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
    '{"candidateItemScores":[{"item":"<slug>","score":0-100,"reason":"...",'
    '"synergyWith":["<slug in your five that this multiplies or is multiplied by>"]}],'
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
        # The raw list covers the three BASIC abilities only, and saying just
        # "1, 2, 3" understated the ultimate into invisibility -- for many
        # kits the ultimate is the largest single damage source and the thing
        # the whole build exists to enable. Spell it out.
        lines.append(
            f"skillPriority={meta['skillPriority']} (basic abilities only -- the "
            "ULTIMATE is levelled the moment it is available at 5/9/13, sits outside "
            "this ordering, and for many kits is the primary damage source or the "
            "fight-deciding effect; weigh items that amplify or enable it accordingly)")

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
# meta itemization identity (curated cards, data/champion_identity.json)
# --------------------------------------------------------------------------

_IDENTITY_CACHE: dict | None = None


def _identity_store() -> dict:
    """Cards keyed by the same display names as champion_builds.json."""
    global _IDENTITY_CACHE
    if _IDENTITY_CACHE is None:
        p = DATA / "champion_identity.json"
        _IDENTITY_CACHE = (json.loads(p.read_text(encoding="utf-8")).get("champions", {})
                           if p.exists() else {})
    return _IDENTITY_CACHE


def identity_card(name: str) -> dict | None:
    """The raw card for callers that need the data, not the prompt text."""
    return _identity_store().get(name)


def meta_identity_block(name: str) -> str:
    """How this champion is ACTUALLY itemized at high rank.

    The kit-derived profiles above say what the abilities could use; this card
    says what the meta has settled on -- including which tempting paths are
    traps. It exists because the measured failure mode of every model tried is
    identity drift: a build that is internally coherent but that nobody who
    plays the champion would recognise. Verdicts marked "never" are hard
    constraints; the validator enforces them after generation too."""
    card = _identity_store().get(name)
    if not card:
        return ""
    verdicts = "; ".join(
        f"{a['path']}={a['status'].upper()}" + (f" ({_norm(a['note'])})" if a.get("note") else "")
        for a in card.get("archetypes", []))
    lines = [
        "META ITEMIZATION IDENTITY (curated, cross-checked against top-ladder builds; "
        "this CONSTRAINS which archetype the build may express -- the kit profiles above "
        "decide the details INSIDE the allowed archetypes, never outside them):",
        f"  is: {_norm(card.get('identitySummary', ''))}",
        f"  archetype verdicts: {verdicts}",
        "  statuses: PRIMARY anchors the default build; VIABLE is a legitimate alternative; "
        "SITUATIONAL only under its stated condition; FLEX_ONE_ITEM allows exactly ONE item "
        "of that archetype; OFF_META must not be recommended; NEVER is a hard constraint.",
    ]
    if card.get("statPriorities"):
        lines.append("  stat priorities: " + " > ".join(card["statPriorities"]))
    if card.get("avoidStats"):
        lines.append("  never build around: " + ", ".join(card["avoidStats"]))
    if card.get("flexPatterns"):
        lines.append("  accepted flexes: " + "; ".join(_norm(f) for f in card["flexPatterns"]))
    return "\n".join(lines)


_CONSENSUS_CACHE: dict | None = None


def _consensus_store() -> dict:
    global _CONSENSUS_CACHE
    if _CONSENSUS_CACHE is None:
        p = DATA / "ladder_consensus.json"
        _CONSENSUS_CACHE = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    return _CONSENSUS_CACHE


#: pick rate at which a ladder item is put in front of the model at all
LADDER_CORE_RATE = 0.30


def ladder_core_slugs(name: str) -> list[str]:
    """The non-boots slugs the REQUIRED CANDIDATES block will demand scores
    for -- exposed so the validator can enforce what the prompt asks. The rule
    lived only in prose until a live Aatrox run silently skipped
    trinity-force, a core item, and nothing caught it."""
    rec = _consensus_store().get(name.split(" (")[0])
    if not rec or not rec.get("items"):
        return []
    return [i["slug"] for i in rec["items"]
            if i.get("of") and i["count"] / i["of"] >= LADDER_CORE_RATE]


def ladder_consensus_block(name: str) -> str:
    """The ladder core as a mandatory candidate set -- with its origin hidden.

    The provenance IS the anchor. Every earlier wording named the source, and
    each time the model deferred to that authority instead of evaluating:
    shown pick-rate counts ("Kraken Slayer (36/50)") it rubber-stamped the
    whole core and reported "unchanged" while 100+ single swaps scored higher
    in the fight engine; told merely that "top ranked players equip these",
    it reproduced the list verbatim. A model cannot be asked to out-build the
    ladder while being told the ladder is the answer.

    So the block says nothing about where the list comes from. The items,
    keystone, minors and spells arrive as required CANDIDATES -- they must
    enter the evaluation, and any that misses the final build must be argued
    away, not skipped -- but they carry no counts, no ranking, and no appeal
    to who runs them. If the ladder is right, the model's own kit analysis
    should arrive there unprompted (blind-tested on Vayne it found 4 of the
    6 by itself); where it disagrees, the disagreement gets said out loud
    instead of being talked out of existence by a headline.

    The wording deliberately names no output field. Pointing at
    candidateItemScores made the requirement about filling in a schema; the
    schema section already says where answers go. Boots need no special note
    either: the list shows the finished tier-3 boot, and boots_block already
    explains the tier-2 purchase that upgrades into it.
    """
    rec = _consensus_store().get(name.split(" (")[0])
    if not rec or not rec.get("items"):
        return ""
    core = [i for i in rec["items"]
            if i.get("of") and i["count"] / i["of"] >= LADDER_CORE_RATE]
    if not core:
        return ""
    lines = [
        "REQUIRED CANDIDATES (must be in the initial candidate list you score; "
        "judge them exactly like every other candidate):",
        "  items: " + ", ".join(sorted(i["name"] for i in core)),
    ]
    if rec.get("keystones"):
        lines.append("  keystone: " + rec["keystones"][0]["name"])
    if rec.get("minors"):
        lines.append("  minor runes: " + ", ".join(m["name"] for m in rec["minors"]))
    if rec.get("spells"):
        lines.append("  summoner spells: " + rec["spells"][0]["pair"])
    lines.append(
        "  None of these has to reach your final build. For any that does not, "
        "state why it lost to what you chose instead.")
    return "\n".join(lines)


def ladder_agreement(name: str, slugs: list[str]) -> dict | None:
    """Share of a build's items that the champion's top-50 players also
    equip (pick rate >= 15%). None when no ladder data exists yet."""
    rec = _consensus_store().get(name.split(" (")[0])
    if not rec or not rec.get("items"):
        return None
    popular = {i["slug"] for i in rec["items"] if i["of"] and i["count"] / i["of"] >= 0.15}
    if not popular or not slugs:
        return None
    hits = sum(1 for s in slugs if s in popular)
    return {"matched": hits, "of": len(slugs),
            "score": round(hits / len(slugs) * 100)}


def identity_threat_lines(enemies: list[str]) -> str:
    """Per-enemy meta threat notes for the counter prompt: what each enemy
    DOES at high rank and the itemization answers players actually buy."""
    store = _identity_store()
    lines = []
    for enemy in enemies:
        tp = (store.get(enemy) or {}).get("threatProfile") or {}
        if not tp.get("threats"):
            continue
        lines.append(f"  {enemy}: threats: " + "; ".join(tp["threats"])
                     + (". itemization answers: " + "; ".join(tp.get("counterplay", []))
                        if tp.get("counterplay") else ""))
    if not lines:
        return ""
    return ("META THREAT NOTES (curated per-enemy: what each enemy actually does at high "
            "rank, and the answers high-rank players buy against them):\n" + "\n".join(lines))


# --------------------------------------------------------------------------
# rules, in three tiers
# --------------------------------------------------------------------------

def rules_block(enemies_known: bool, combat_profile: dict) -> str:
    hard = RULES.get("hardExclusive") or {}
    redundancy = RULES.get("redundancyGroups") or {}
    situational = (RULES.get("situationalOnly") or {}).get("slugs", [])
    late = RULES.get("lateGameStrategic") or {}

    has_redundancy = any(not n.startswith("_") and isinstance(g, dict)
                         for n, g in redundancy.items())
    lines = [
        ("RULES, IN THREE TIERS. Only tier A is absolute. Tier B is a strong default "
         "you may override with a stated reason. Tier C is preference."
         if has_redundancy else
         "RULES, IN TWO TIERS. Tier A is absolute. Tier B is preference you may "
         "override with an argument."),
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
    ]

    # Redundancy groups are empty by owner decision (see item_rules.json): the
    # only group ever defined was grievous-wounds, and it swept in Serylda's
    # Grudge -- a mainline armor-pen item the ladder pairs freely. The section
    # renders only if a group is ever added back, and the tier letters shift
    # so the prompt never shows an empty tier.
    groups = [(n, g) for n, g in redundancy.items()
              if not n.startswith("_") and isinstance(g, dict)]
    next_tier = "B"
    if groups:
        lines += ["", "B. REDUNDANCY -- legal, and normally a waste. Build two from a "
                      "group only when you say why the overlap earns its gold:"]
        for name, group in groups:
            lines.append(f"    {name}: {', '.join(group['slugs'])}")
            lines.append(f"      why it is usually wrong: {group.get('why', '')}")
        next_tier = "C"

    lines += [
        "",
        f"{next_tier}. DEFAULT STRATEGY -- preferences you may override with an argument:",
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

# When no enemy team is supplied, the model used to be told it had "no
# evidence" of anything -- which is false. Ranked compositions are highly
# regular, and a build made for the median comp beats a build made for a
# vacuum: anti-heal, armor pen and MR all have expected value before a single
# enemy is named (the ladder's top 50 buy them at 60%+ pick with exactly as
# little information). So the model now builds against the TYPICAL comp,
# stated as archetypes, while still forbidden from naming specific champions.
UNKNOWN_ENEMY_BLOCK = (
    "WHEN THE ENEMY TEAM IS UNKNOWN (it is, for this request):\n"
    "- Assume the typical ranked composition: BARON LANE one tank or bruiser, "
    "JUNGLE one bruiser, tank or AD assassin, MID one mage or assassin, DRAGON "
    "LANE one marksman, SUPPORT one enchanter or tank.\n"
    "- What that implies, and what you may build for: mixed but physical-leaning "
    "damage from two or three sources, one serious magic threat, a real frontline "
    "with resistances worth penetrating, meaningful healing and shielding "
    "somewhere on the team, and some crowd control.\n"
    "- Do NOT name specific enemy champions, and do not assume an extreme comp "
    "(full AD, five tanks, triple healer). Reason at the archetype level above.\n"
    "- Use situational recommendations for the real deviations from that typical "
    "comp, each with the condition that would trigger it.\n"
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
        "PRIORITY THREATS (ranked by each enemy's MEASURED meta win rate weighted by how "
        "much damage its class contributes -- metaWinrate is the number driving the order. "
        "A 56% jungler is a bigger problem than a 49% support even when both have scary "
        "kits. Each entry names what items CAN answer and what only gameplay can): "
        + json.dumps(priorities),
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
