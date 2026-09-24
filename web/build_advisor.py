"""LLM-first build advisor with an optional engine-judged tournament.

The rule-based simulation engine is not reliable enough to author builds by
itself. The LLM remains the selection authority, but maximum-damage requests
can now ask for three candidates in one model response, measure each candidate
under identical engine assumptions, then give those measurements back to the
LLM for the final judgement.

    user: champion + role + enemy team (+ ally team)
      -> DERIVE how this champion fights          web/advisor/profiles.py
      -> FILTER only impossible items away        web/advisor/itemmeta.py
      -> ASSEMBLE one prompt from our data        web/advisor/prompt.py
      -> the model (gemini-3.8-flash by default), JSON only
      -> VALIDATE legality and completeness       web/advisor/validate.py
      -> REPAIR the broken section alone          web/advisor/repair.py

This file is the orchestrator: it owns the CLI, request normalisation, the model
call and the repair loop. The reasoning about what a champion is and what a legal
build looks like lives in web/advisor/, so that each piece can be tested without
an API key (see tests/).

IMPORTANT: stdout carries the build JSON and nothing else --
web-next/src/app/api/build/route.ts parses it directly. Every diagnostic goes to
stderr. tests/test_prompt.py guards this.

Run:
    python -m web.build_advisor --champion Graves --role Jungle \
        --enemies "Malphite,Ahri,Ashe,Leona,Master Yi"
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path

import requests

from web.advisor import env as advisor_env
from web.advisor import itemmeta, profiles, repair, runemeta, summoners, supportitem
from web.advisor import prompt as prompt_mod
from web.advisor import threats as threats_mod
from web.advisor import validate as validate_mod

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"

# Which model authors the build. Set ADVISOR_MODEL to switch; a name starting
# with "gemini" routes to the Gemini API, anything else to DeepSeek.
#
# Gemini won a five-champion, fifty-build comparison judged on the builds
# themselves: better picks on four of five champions, ~17% faster, and a third
# of the repair rounds. It has been what production serves since then, set as a
# Vercel environment variable on the advisor project.
#
# The DEFAULT here stayed DeepSeek for a while after that, and the gap between
# the two cost real work: anything not started by the dev server -- a script, a
# benchmark, a timing run -- silently used a model the site does not serve. A
# latency investigation measured DeepSeek at 272-293s per build, four times
# Gemini's, and reported it as a production incident before anyone noticed that
# production was never on DeepSeek. So the default is now what production runs.
DEFAULT_MODEL = "gemini-3.8-flash"
MODEL = os.environ.get("ADVISOR_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
IS_GEMINI = MODEL.lower().startswith("gemini")
# The key the ACTIVE model needs. Checking DEEPSEEK_API_KEY on a Gemini run
# refuses a request the model could have served, and the reverse hands the
# DeepSeek endpoint an empty Authorization header.
KEY_NAME = "GEMINI_API_KEY" if IS_GEMINI else "DEEPSEEK_API_KEY"
# Escalation model for requests the cheap model measurably cannot serve.
# gemini-3.5-flash-lite matches flash on standard builds at a fraction of the
# price, but it IGNORES explicit playstyle requests when they contradict its
# prior about the champion: a Rhaast BURST request produced the drain-bruiser
# build four runs out of four with the model calling it deliberate ("Built
# strictly around Rhaast's drain-bruiser identity"), while gemini-3.6-flash
# honoured the same prompt (Eclipse opener, Electrocute page). Same failure
# family as the measured Malphite tank-identity and Yordle Trap misses.
# Standard/adaptive requests -- the bulk of traffic -- stay on ADVISOR_MODEL;
# explicit playstyles escalate. Unset means no escalation (everything on
# ADVISOR_MODEL), so this is inert unless configured.
PREMIUM_MODEL = os.environ.get("ADVISOR_MODEL_PREMIUM", "").strip()


def _complex_champions() -> frozenset[str]:
    """Champions the cheap model gets wrong even on STANDARD requests.

    Three groups, each tied to evidence rather than taste:
      - transform forms (Kayn): the form block and the base record disagree,
        and the lite resolved that disagreement against a live request;
      - champions with a curated build identity in combat_profiles.json: the
        derivation got them wrong, which is the definition of a confusing kit;
      - every champion whose derived build path is "tank": the lite built Rod
        of Ages / Riftmaker / Rabadon's Malphite three STANDARD runs out of
        three, straight past an identity block marked AUTHORITATIVE.

    Derived at import from the same data everything else reads, so a new
    curated override or a re-derived tank automatically joins the set.
    """
    out = {n for n, c in CHAMPS.items() if c.get("forms")}
    for name, entry in ((_load("combat_profiles.json", {}) or {}).get("champions") or {}).items():
        if any(k in entry for k in ("buildIdentity", "buildIdentityProfile", "alternativePath")):
            out.add(name)
    for name in CHAMPS:
        try:
            if profiles.build_identity_profile(name).get("primaryBuildPath") == "tank":
                out.add(name)
        except Exception:  # noqa: BLE001 -- a broken profile must not kill import
            continue
    # Champions whose scraped class or damage type had to be corrected by hand.
    # Needing an override IS the evidence that the kit is confusing, and it is
    # the same reasoning as the curated-identity group above. Garen reached
    # this set as a "tank" until he was reclassified a bruiser, which would
    # otherwise have silently dropped him to the cheap model; the five
    # assassin-bruisers whose class and shopping list disagree join him.
    out |= set((_load("champion_meta_overrides.json", {}) or {}).get("champions", {}))
    return frozenset(out)


# Assigned after the champion data loads below; the function body reads CHAMPS
# and the profiles module at call time, not at definition time.
COMPLEX_CHAMPIONS: frozenset[str] = frozenset()


def model_for_request(playstyle: str, champion: str = "") -> str:
    """Which model authors this build. Escalation applies only within the
    Gemini family: mixing providers per-request would change auth and the
    response contract mid-pipeline. Two triggers, both measured failures of
    the cheap model: an explicit playstyle it ignores, or a champion whose
    identity it overrides even on standard requests."""
    if not (PREMIUM_MODEL and IS_GEMINI and PREMIUM_MODEL.lower().startswith("gemini")):
        return MODEL
    if playstyle not in ("standard", "adaptive") or champion in COMPLEX_CHAMPIONS:
        return PREMIUM_MODEL
    return MODEL
THINKING = {"type": "enabled"}
# Caps COMPLETION tokens, which include the model's reasoning, not just the
# JSON. Measured on a full studio generation: 4,401 completion tokens, of which
# 2,719 were reasoning, for 5,478 characters of build. This was 384,000, which
# is ~87x the observed need and so far above any real answer that its only
# effect was to let a runaway generation burn the entire 240s request timeout
# before tripping the finish_reason == "length" guard below.
#
# 32,000 leaves roughly 7x headroom over the largest call measured -- enough
# that reasoning_effort "high" on a counter build with a full enemy team stays
# comfortably inside it -- while turning a runaway into a fast, explicit error.
MAX_OUTPUT_TOKENS = 32_000
PLAYSTYLE_CONFIG_PATH = ROOT / "web-next" / "src" / "data" / "playstyles.json"


def _load(name: str, default=None):
    p = DATA / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def _norm(text: str) -> str:
    """Collapse whitespace without clipping any source mechanic or tooltip."""
    return " ".join((text or "").split())


# Key loading lives in web/advisor/env.py so both generators share one
# implementation. They did not, briefly, and the curated one failed on its first
# real run for exactly that reason.
ENV_FILE = advisor_env.ENV_FILE
_api_key = advisor_env.api_key


ITEMS = {i["slug"]: i for i in _load("items.json", [])}
RUNES = _load("wrmeta_runes.json", [])
RUNE_SLOTS = (_load("rune_slots.json", {}) or {}).get("trees", {})
ARCHETYPES = _load("champion_archetypes.json", {})
COUNTERS = _load("counters.json", {})
WRMETA = _load("wrmeta_champions.json", {})
ITEM_RULES = _load("item_rules.json", {})
_champs_raw = _load("champions_wr.json", [])
CHAMPS = {c["name"]: c for c in (_champs_raw.values() if isinstance(_champs_raw, dict)
                                 else _champs_raw)}
_CHAMPION_STAT_OVERRIDES = (_load("champion_stat_overrides.json", {}) or {}).get("champions", {})
for _name, _override in _CHAMPION_STAT_OVERRIDES.items():
    if _name not in CHAMPS:
        continue
    for _stat, _values in (_override.get("baseStats") or {}).items():
        CHAMPS[_name].setdefault("baseStats", {})[_stat] = {
            key: value for key, value in _values.items()
            if key in {"base", "perLevel", "lvl15"}
        }
    if _override.get("statRules"):
        CHAMPS[_name]["statRules"] = _override["statRules"]
# class/role live in the builds file, not the raw champion scrape; fold them in
# so the champion block and enemy block can state them.
_BUILDS = _load("../web-next/src/data/builds.json", {}) or _load("champion_builds.json", {})
for _n, _rec in (_BUILDS or {}).items():
    if _n in CHAMPS:
        CHAMPS[_n].setdefault("class", _rec.get("class", ""))
        CHAMPS[_n].setdefault("role", _rec.get("role", ""))

# The pre-generated catalogue is intentionally partial. Fold the complete site
# roster in as the fallback so every champion exposed by Build Studio validates
# against the same class-based playstyles as the UI.
_ROSTER = _load("../web-next/src/data/roster.json", []) or []
for _rec in (_ROSTER.values() if isinstance(_ROSTER, dict) else _ROSTER):
    _name = _rec.get("name")
    if _name in CHAMPS:
        CHAMPS[_name].setdefault("class", _rec.get("class", ""))
        CHAMPS[_name].setdefault("role", _rec.get("role", ""))

COMPLEX_CHAMPIONS = _complex_champions()

PLAYSTYLE_CONFIG = json.loads(PLAYSTYLE_CONFIG_PATH.read_text(encoding="utf-8"))
PLAYSTYLES_BY_CLASS: dict[str, list[str]] = PLAYSTYLE_CONFIG["byClass"]
PLAYSTYLE_OVERRIDES: dict[str, list[str]] = PLAYSTYLE_CONFIG["overrides"]


#: Granted to EVERY champion rather than listed per class. It is not a build
#: archetype a class table can hand out -- it is a request to leave the
#: consensus build behind on whatever kit it is given -- so the per-class lists
#: stay what they have always been: a statement about what that class can
#: actually build. It is also why this cannot be a silent default: the UI has
#: to label the result as an experiment, which the retired `offmeta` builds did
#: not, and that is exactly how unreviewed builds came to look recommended.
EXPERIMENTAL = "experimental"


def available_playstyles(champion: str) -> list[str]:
    if champion in PLAYSTYLE_OVERRIDES:
        # COPY. This used to hand back the config's own list, and appending to
        # it below would have edited the loaded playstyle table in place.
        styles = list(PLAYSTYLE_OVERRIDES[champion])
    else:
        champ = CHAMPS.get(champion) or {}
        styles = list(PLAYSTYLES_BY_CLASS.get(champ.get("class", ""), ["standard", "oneshot"]))
        if champ.get("role") == "Support" and "utility" not in styles:
            styles.append("utility")
    if EXPERIMENTAL not in styles:
        styles.append(EXPERIMENTAL)
    return styles

# canonical slug lookup, forgiving about case/punctuation
def _canon(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())

ITEM_CANON = {_canon(s): s for s in ITEMS} | {_canon(i["name"]): s
                                             for s, i in ITEMS.items()}
ITEM_CANON.update({
    _canon("hextech-roketbelt"): "hextech-rocketbelt",
    _canon("Hextech Roketbelt"): "hextech-rocketbelt",
    _canon("immortal-treds"): "immortal-treads",
    _canon("Immortal Treds"): "immortal-treads",
})


def _resolve_item(s: str) -> str | None:
    """Slug from a model-written name, tolerant of the variants it reaches for:
    exact, then trailing-s (Dominik's Regard vs Regards), then unique substring.
    The model has seen wr-meta's plural spellings, so a strict match rejected
    legitimate picks and the repair round would repeat the same near-miss."""
    c = _canon(s)
    if c in ITEM_CANON:
        return ITEM_CANON[c]
    for cand in (c.rstrip("s"), c + "s"):
        if cand in ITEM_CANON:
            return ITEM_CANON[cand]
    hits = [slug for cc, slug in ITEM_CANON.items()
            if c and (c in cc or cc in c)]
    return hits[0] if len(set(hits)) == 1 else None
RUNE_NAMES = {r["name"] for r in RUNES}
RUNE_CANON = {_canon(n): n for n in RUNE_NAMES}


# --------------------------------------------------------------------------
# context assembly: the model knows NOTHING except what we send
# --------------------------------------------------------------------------


def _enemy_block(enemies: list[str], me: str) -> str:
    if not enemies:
        return "ENEMY TEAM: unknown"
    out = ["ENEMY TEAM (their damage type + threat profile):"]
    for e in enemies:
        c = CHAMPS.get(e) or {}
        out.append(f"  {e}: class={c.get('class','?')} "
                   f"damage={c.get('primaryDamage','?')} "
                   f"mechanics={c.get('mechanics') or []}")
    mine = COUNTERS.get(_canon(me).replace(" ", "-"), {}) or COUNTERS.get(
        me.lower().replace(" ", "-"), {})
    hard = (WRMETA.get(me) or {}).get("hardCounters") or []
    bad = [e for e in enemies if e in hard]
    if bad:
        out.append(f"  WARNING: {', '.join(bad)} hard-counter {me}: itemize for it.")
    if mine.get("strong"):
        good = [e for e in enemies if e.lower().replace(' ', '-') in mine["strong"]]
        if good:
            out.append(f"  {me} is strong into: {', '.join(good)}")
    return "\n".join(out)







DEFENSIVE_BOOTS = {"mercurys-treads", "plated-steelcaps"}
OFFENSE_FIRST_CLASSES = {"Bruiser", "Marksman", "Assassin"}

# Summoner spells, mirrored from scripts/build_champions_llm.py so the live
# advisor and the curated generator draw from the same pool and rules. The live
# builds did not include summoners at all; a full loadout has to.
_DD_SPELL = "https://ddragon.leagueoflegends.com/cdn/16.11.1/img/spell"
SUMMONERS: dict[str, dict] = {
    "Flash": {"desc": "Short-range blink. The default safety/playmaking spell.", "dd": "SummonerFlash"},
    "Ignite": {"desc": "True damage burn + 50% Grievous Wounds. Kill pressure.", "dd": "SummonerDot"},
    "Ghost": {"desc": "Large move speed for 6s. For champions that run enemies down.", "dd": "SummonerHaste"},
    "Exhaust": {"desc": "Slows an enemy and cuts their damage 35%. Anti-assassin/carry.", "dd": "SummonerExhaust"},
    "Smite": {"dd": "SummonerSmite", "desc": "Monster/objective execute. MANDATORY for the jungler."},
    "Cleanse": {"desc": "Removes CC and lowers further CC. Into heavy lockdown.", "dd": "SummonerBoost"},
    "Heal": {"desc": "Burst heal + move speed for you and an ally. Marksman staple.", "dd": "SummonerHeal"},
    "Barrier": {"desc": "Self shield. Anti-burst alternative to Heal.", "dd": "SummonerBarrier"},
}
SUMMONER_CANON = {_canon(n): n for n in SUMMONERS}


def _summoner_block(role: str, enemies_known: bool = True, immobile: bool = False) -> str:
    """The pool and the hard rules. The jungle rules are also enforced in code.

    Stating them here anyway is not redundant: a model told the constraint picks
    a sensible partner spell, whereas a model that has its answer corrected
    afterwards writes a `summonerReason` explaining a choice it did not make.
    """
    pool = summoners.allowed_pool(role, enemies_known)
    rows = "\n".join(f"- {name}: {meta['desc']}"
                     for name, meta in SUMMONERS.items()
                     if name in pool or name == summoners.JUNGLE_SPELL)

    if (role or "").strip().lower() == "jungle":
        rule = ("This is a JUNGLER. Smite is MANDATORY and occupies one slot -- it is not a "
                "choice and you do not need to justify it. This applies even if the champion "
                "is not normally played in the jungle: a jungle build takes Smite. The ONLY "
                "decision is the second slot, and it must be either Flash or Ghost: Ghost for "
                "champions that win by running a target down and holding on, Flash for "
                "everyone else. Do not return any other second spell.")
    elif not enemies_known:
        # No NAMED enemies, but not blind either: the prompt has the model
        # assume the typical ranked comp, and the summoner choice should read
        # THAT comp the same way the items and runes do. Ignite stays out (an
        # archetype cannot tell you the lane is a kill lane) and Heal stays
        # support-only (it is an ALLY heal; a solo laner gets a worse Barrier).
        rule = ("Not a jungler. No enemy champions were NAMED, so read the TYPICAL RANKED "
                "COMP assumed above the way your items and runes already do: it has a real "
                "frontline, one serious magic or burst threat mid, a marksman, and some "
                "crowd control. Choose two from the pool above against those archetypes -- "
                "Flash is the usual anchor; Ghost for a champion that must walk to its "
                "target; Exhaust to blunt the carry or assassin; Cleanse when THIS champion "
                "is shut down by the comp's crowd control; Barrier when its burst threat "
                "is the bigger danger to you. Heal and Ignite are deliberately not offered: "
                "each answers a SPECIFIC lane, and archetypes cannot name one.")
    else:
        rule = ("Not a jungler: NEVER take Smite. Both slots are open and this is a real "
                "matchup decision, so use the enemy team above. Flash is the usual anchor "
                "but it is not compulsory. Weigh the alternatives on what this specific comp "
                "does to this specific champion: Cleanse against heavy lockdown, Exhaust "
                "against a fed assassin or a hypercarry, Barrier against burst, Ignite when "
                "the lane is a kill lane or the enemy heals."
                + ("" if (role or "").strip().lower() == "support" else
                   " Heal is a SUPPORT spell and is not offered here: it heals the ally it "
                   "is cast on, which is the reason to bring it, and a solo laner gets a "
                   "worse Barrier."))

    # The playstyle reaches here too. A Sustain request wants the spell that
    # keeps the champion in the fight, a Burst request the one that secures the
    # kill -- and until this was said, the summoner slot was the one part of the
    # loadout the brief never touched.
    rule += (" THE REQUEST APPLIES HERE TOO: the playstyle, the power curve and the risk "
             "tolerance bear on these two slots as much as on the items and the runes -- "
             "an early-game build wants the spell that wins the first fight, a durable one "
             "the spell that survives it. Choose the pair that serves what was asked for "
             "on THIS kit, and say in `summonerReason` how they do.")

    if immobile:
        rule += (" MOBILITY: this champion has no dash, blink or leap of its own, so it "
                 "cannot create distance or close it without help. Flash and Ghost are the "
                 "two spells that substitute for that, and both should be seriously "
                 "considered here -- taking neither leaves the champion unable to reposition "
                 "at all. Say why in `summonerReason` if you choose otherwise.")

    return ("SUMMONER SPELLS (choose exactly 2 distinct, from this pool only):\n"
            + rows + "\n" + rule)


def _support_item_block(role: str) -> str:
    """Only rendered for supports. Also enforced in code, same as Smite."""
    if not supportitem.is_support(role):
        return ""
    return (
        "SUPPORT ITEM (MANDATORY, FIRST PURCHASE):\n"
        "This is a SUPPORT build, so item 1 MUST be one of the two free support items. "
        "They cost 0 gold, they are the role's entire income (Soulcast pays 75 gold a "
        "minute and stacks up to 250 Health and 20 AD or 40 AP), and they are never "
        "sold. Choose between them on what this champion needs:\n"
        f"- {ITEMS[supportitem.TANKY]['name']} ({supportitem.TANKY}): 175 Health, 10 ability "
        "haste. For supports who absorb damage -- engage, tanks, front line.\n"
        f"- {ITEMS[supportitem.DAMAGE]['name']} ({supportitem.DAMAGE}): 10 ability haste plus "
        "an adaptive 14 Attack Damage or 28 Ability Power. For supports who convert gold "
        "into threat -- enchanters, mages, poke.\n"
        "Return it as items[1] in the purchase order. The remaining four items are the "
        "real build, so choose them knowing you have four slots and boots, not five.")


def _lock_block(item_locks: list[str], boot_lock: str, rune_locks: list[str]) -> str:
    """The player's pinned items and runes, as a hard constraint on the build."""
    if not item_locks and not boot_lock and not rune_locks:
        return ""
    lines = ["LOCKED CHOICES (the build MUST include every one of these):"]
    for slug in item_locks:
        lines.append(f"- item {ITEMS[slug]['name']} ({slug}) must be one of the five main items")
    if boot_lock:
        lines.append(f"- boots {ITEMS[boot_lock]['name']} ({boot_lock}) must be the main boots")
    for name in rune_locks:
        lines.append(f"- rune {name} must be on the rune page (keystone if it is a keystone, "
                     "otherwise a minor in its own slot, or the flex)")
    lines.append("Build the strongest legal loadout that still contains all of the above. Do not "
                 "drop a lock, and do not treat a lock as merely 'considered'.")
    return "\n".join(lines)



def _meta_block(name: str) -> str:
    """Live meta the model cannot know: tier + win rate from our site data.

    The EU win rate is centred so 50 = the average champion (each champion's
    top-50 mains sit high on absolute numbers), which we tell the model so it
    reads the figure correctly.
    """
    p = DATA / "../web-next/src/data/site.json"
    if not p.exists():
        return ""
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        champs = d.get("champions") if isinstance(d, dict) else d
        for c in champs or []:
            if c.get("name") != name:
                continue
            keep: dict = {}
            if c.get("tier") is not None:
                keep["tier"] = c["tier"]
            if c.get("wr") is not None:
                keep["euWinRateRelative"] = c["wr"]
            if c.get("maxWr") is not None:
                keep["bestPlayerCeiling"] = c["maxWr"]
            if keep:
                return (f"CURRENT META for {name} (EU top-50 players; win rate is centred "
                        f"so 50 = average champion): {json.dumps(keep)}")
    except Exception:  # noqa: BLE001
        return ""
    return ""



def _stream_call(key: str, body: dict, on_progress) -> dict:
    """One streamed completion, reporting how much has arrived as it arrives.

    The build cannot be shown before it is finished -- it still has to be
    validated and possibly repaired, and rendering a draft that then changes
    would be worse than waiting. What streaming buys is an HONEST progress
    signal during the ~50s wait, in place of a bar that eases toward 92% on a
    timer and stalls there.

    So the content is accumulated exactly as the non-streaming path would, and
    only the byte count is reported outward.
    """
    body = {**body, "stream": True}
    chunks: list[str] = []
    received = 0
    reasoned = 0
    last_report = 0.0
    r = requests.post(DEEPSEEK_URL, json=body,
                      headers={"Authorization": f"Bearer {key}"},
                      timeout=300, stream=True)
    if not r.ok:
        raise RuntimeError(f"deepseek {r.status_code}: {r.text[:500]}")
    finish_reason = None
    for line in r.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        try:
            event = json.loads(data)
        except json.JSONDecodeError:
            continue
        choice = (event.get("choices") or [{}])[0]
        finish_reason = choice.get("finish_reason") or finish_reason
        delta = choice.get("delta") or {}
        piece = delta.get("content") or ""
        # Thinking mode emits nothing on `content` until it has finished
        # reasoning -- measured at ~50s of silence on a 66s generation, which is
        # most of the wait. The reasoning deltas arrive throughout, so they are
        # what makes a progress bar move honestly rather than on a timer.
        thought = delta.get("reasoning_content") or ""
        if piece:
            chunks.append(piece)
            received += len(piece)
        if piece or thought:
            reasoned += len(thought)
            # Throttled: one event per 400ms is plenty to animate a bar, and
            # every event is a chunk written down two more hops.
            now = time.time()
            if now - last_report > 0.4:
                last_report = now
                on_progress({"stage": "writing" if piece else "thinking",
                             "chars": received, "reasoning": reasoned})
    if finish_reason == "length":
        raise RuntimeError("deepseek output reached max_tokens; refusing truncated JSON")
    return json.loads("".join(chunks))


def _gemini_call(prompt: str, model: str = "") -> dict:
    """The same contract as the DeepSeek path: prompt in, parsed build out.

    Kept deliberately thin. Everything that decides the build -- the prompt, the
    validator, the repair loop -- is shared, so switching providers changes the
    author and nothing else, which is what made the comparison meaningful.
    """
    from google import genai
    from google.genai import types

    # Read through advisor_env, not straight off os.environ. The Gemini path
    # used to look only at the process environment while the DeepSeek path had
    # the web-next/.env.local fallback, so a script that worked on DeepSeek
    # failed on Gemini with the key sitting in the repo -- and every measurement
    # script grew its own bootstrap to paper over it.
    api_key = _api_key("GEMINI_API_KEY") or _api_key("GOOGLE_API_KEY")
    if not api_key:
        raise SystemExit(advisor_env.missing_key_message("GEMINI_API_KEY")
                         + f" (the build model is {MODEL!r})")
    client = genai.Client(api_key=api_key)
    config = types.GenerateContentConfig(
        system_instruction=prompt_mod.SYSTEM,
        response_mime_type="application/json",
        temperature=0,
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )
    last = None
    for attempt in range(4):
        try:
            r = client.models.generate_content(model=model or MODEL, contents=prompt, config=config)
            return json.loads(r.text)
        except Exception as exc:                       # noqa: BLE001
            last = exc
            text = str(exc)
            if "RESOURCE_EXHAUSTED" in text or "429" in text:
                # The free tier throttles hard and recovers in minutes, so wait
                # rather than failing a generation the player is watching.
                time.sleep(min(60, 15 * (attempt + 1)))
                continue
            if attempt < 3:
                time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"gemini failed after 4 attempts: {str(last)[:300]}")


def _call(key: str, prompt: str, on_progress=None, model: str = "") -> dict:
    if IS_GEMINI:
        return _gemini_call(prompt, model=model)
    body = {"model": MODEL,
            "messages": [{"role": "system", "content": prompt_mod.SYSTEM},
                         {"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
            "thinking": THINKING, "reasoning_effort": "high",
            "temperature": 0,
            "max_tokens": MAX_OUTPUT_TOKENS, "stream": False}
    for attempt in range(4):
        try:
            if on_progress:
                return _stream_call(key, body, on_progress)
            r = requests.post(DEEPSEEK_URL, json=body,
                              headers={"Authorization": f"Bearer {key}"}, timeout=240)
        except requests.RequestException:
            if attempt < 3:
                time.sleep(3 * (attempt + 1))
                continue
            raise
        if r.status_code in (429, 500, 502, 503, 504) and attempt < 3:
            time.sleep(3 * (attempt + 1))
            continue
        if not r.ok:
            raise RuntimeError(f"deepseek {r.status_code}: {r.text}")
        payload = r.json()
        choice = payload["choices"][0]
        if choice.get("finish_reason") == "length":
            raise RuntimeError("deepseek output reached max_tokens; refusing truncated JSON")
        return json.loads(choice["message"]["content"])
    raise RuntimeError("retries exhausted")


# --------------------------------------------------------------------------
# validation: the LLM reasons, but it does not get to invent
# --------------------------------------------------------------------------


# Shared with the UI so the labels and champion-specific options stay aligned.
PLAYSTYLES = {
    definition["key"]: definition["prompt"]
    for definition in PLAYSTYLE_CONFIG["definitions"]
}

# A second, orthogonal axis: HOW to optimize, independent of the playstyle.
OBJECTIVES = {
    "balanced": "",  # default: no extra bias
    # "prefer stat-dense items over flashy actives" used to end this line, and
    # it was a thumb on the scale in the wrong direction: actives were already
    # being skipped almost entirely, and calling them flashy told the model they
    # were frivolous. Stat efficiency is about gold conversion, not about
    # excluding a category -- an active is one of the things an item does.
    "maxstats": "OPTIMIZE FOR STAT EFFICIENCY: favor the items whose raw stats this kit "
                "uses most per gold. When two items are close, prefer the one whose stat "
                "line this kit converts more completely. An item's ACTIVE counts as part "
                "of what it delivers: weigh it by what it is worth to this kit, not "
                "discounted for being an active.",
    "maxsynergy": "OPTIMIZE FOR SYNERGY: favor items and runes that combo with the kit's "
                  "mechanics and with each other (spellblade on weavers, on-hit on on-hit "
                  "casters, actives that chain into the kit), even at some raw-stat cost.",
    # The other objectives each pick an AXIS to optimise along. This one names
    # no axis: it asks for the strongest loadout the kit can support, and lets
    # the model decide what "strongest" means for this champion. Paired with
    # ladder_anchor=False below, because a question about the best possible
    # build cannot be asked while handing over the list of what is popular.
    "best": "BUILD THE STRONGEST LOADOUT THIS CHAMPION CAN HAVE. Not the "
            "conventional one, not the popular one: the one that makes this "
            "specific kit as strong as it can be, judged on the whole package "
            "-- items, boots, runes and summoners working together. Decide "
            "for yourself which axis matters most for this kit rather than "
            "spreading power evenly, and commit to it. If the strongest "
            "answer is something the average player would not build, that is "
            "an acceptable answer: say plainly in the reasoning what it beats "
            "and what it gives up. Do not reach for an unusual pick to be "
            "interesting -- justify it or take the ordinary one.",
}

# Timing is a preference, not permission to discard a champion's core synergy.
GAME_PHASES = {
    "balanced": "BALANCED CURVE: optimize for the full 15-20 minute Wild Rift match.",
    "early": "EARLY-GAME CURVE: prioritize cheap first-item spikes, first objectives, "
             "clear speed and immediate skirmish power. Do not force weak items merely "
             "because they are cheap.",
    "mid": "MID-GAME CURVE: maximize the two-to-three item spike around grouped fights "
           "and major objectives, while preserving a coherent finished build.",
    "late": "LATE-GAME CURVE: prioritize the strongest realistic finished build, scaling, "
            "penetration and cap-aware stat conversion. Still provide a playable purchase order.",
}

# Curated: these champions have genuinely playable AD and AP item paths in Wild
# Rift. Raw ability tags are too noisy (many champions have one incidental ratio).
HYBRID_DAMAGE_CHAMPIONS = {
    "Akali", "Corki", "Ezreal", "Jax", "Kai'Sa", "Katarina", "Kayle",
    "Shyvana", "Teemo", "Twitch", "Varus", "Volibear", "Warwick",
}

DAMAGE_PATHS = {
    "standard": "STANDARD DAMAGE PATH: choose the most practical damage profile for this game.",
    "ad": "AD DAMAGE PATH: build a coherent Attack Damage path; do not mix in AP items unless "
          "an individual item is indispensable and you explain why.",
    "ap": "AP DAMAGE PATH: build a coherent Ability Power path; do not mix in AD items unless "
          "an individual item is indispensable and you explain why.",
    "hybrid": "HYBRID DAMAGE PATH: deliberately combine AD and AP/on-hit scaling only where the "
              "kit converts both efficiently. Every mixed purchase must have a kit-linked reason.",
}

# Split per form into KIT FACTS (always sent) and the form's DEFAULT identity
# (sent only when no explicit playstyle was chosen). The identity used to be an
# unconditional command inside one string -- "Favor bruiser durability ... do
# not build him as blue Kayn" -- which contradicted any non-standard playstyle
# in the same prompt. A live Rhaast BURST request carried both "delete a target
# in one rotation" and "favor durability", and the model built the bruiser and
# said so ("Built strictly around Rhaast's drain-bruiser identity"). Rewording
# the identity into a conditional default did NOT fix it -- the model anchored
# on the identity sentence anyway -- so the choice is now made at assembly
# time, where it cannot be misread: an explicit playstyle simply removes the
# competing instruction from the prompt.
_KAYN_FORM_FACTS = {
    "shadow-assassin": (
        "KAYN FORM -- SHADOW ASSASSIN (blue): optimize the actual transformed kit. "
        "His passive adds magic damage during the opening combat window, Blade's Reach "
        "can be cast while moving, Shadow Step has stronger roaming and slow immunity, "
        "and Umbral Trespass refreshes his passive. Physical damage, penetration and "
        "mobility are what this form converts."
    ),
    "rhaast": (
        "KAYN FORM -- RHAAST / DARKIN SLAYER (red): this OVERRIDES Shadow Assassin-specific "
        "lines in the supplied base record. Rhaast heals for 24-38% of physical damage dealt "
        "to champions. Reaping Slash hits twice and each hit adds target max-Health physical "
        "damage. Blade's Reach knocks up for 1 second. Shadow Step has less movement speed and "
        "no Shadow Assassin slow immunity. Umbral Trespass deals target max-Health physical "
        "damage and heals from the target's max Health. His healing scales with the physical "
        "damage he deals, so damage doubles as durability on this form. Never build him as "
        "blue Kayn: no lethality-assassin one-shot itemisation."
    ),
}
_KAYN_FORM_DEFAULT = {
    "shadow-assassin": (
        "No specific playstyle was requested, so build his natural identity: a burst "
        "assassin for ranged/squishy targets -- fast physical burst, penetration, "
        "mobility and short target access."
    ),
    "rhaast": (
        "No specific playstyle was requested, so build his natural identity: a durable "
        "drain bruiser -- durability, ability haste, sustained physical damage and healing."
    ),
}
# Kept for the request-validation check and any external reader; the prompt
# itself is assembled by kayn_form_block below.
KAYN_FORMS = _KAYN_FORM_FACTS


def kayn_form_block(form: str, playstyle: str) -> str:
    """The form text the prompt actually carries, resolved against the request.

    Standard/adaptive requests get the form's default identity; an explicit
    playstyle replaces it with a direct handover, so the prompt never contains
    two competing itemisation instructions for the model to reconcile.
    """
    facts = _KAYN_FORM_FACTS.get(form, "")
    if not facts:
        return ""
    if playstyle in ("standard", "adaptive"):
        return f"{facts} {_KAYN_FORM_DEFAULT[form]}"
    return (f"{facts} The player explicitly selected the {playstyle!r} playstyle for this "
            f"form and it GOVERNS the loadout: express that playstyle through what this "
            f"form's kit converts, not through the form's usual default build.")

# The player's own rank. Build advice is not rank-neutral: Dark Harvest is a
# different rune at 45% win rate than at Master, because stacking it requires
# winning skirmishes you are not guaranteed to win. The default sends NOTHING --
# the site cannot verify a claim, so the middle is silence, and the two ends
# are the only statements worth making.
SKILL_LEVEL = {
    "developing": (
        "PLAYER RANK: EMERALD OR BELOW. Prefer forgiving, reliable choices across the "
        "whole loadout: keystones that pay out without a snowball (no Dark Harvest, no "
        "stack-or-nothing patterns), items without razor-thin activation windows, and a "
        "build that still performs on a rough game. Reliability outranks ceiling at this "
        "rank -- the game that goes badly is the one the build must survive."),
    "average": "",  # unverifiable middle: no line
    "high": (
        "PLAYER RANK: MASTER OR ABOVE. Execution-gated, snowball-scaling choices are ON "
        "the table when they raise the ceiling: Dark Harvest where its stacking is "
        "realistic for this kit, aggressive early-fight keystones, stacking items, and "
        "greedy timings a skilled pilot converts. Do not pick the safe option purely for "
        "reliability when the higher-ceiling choice is mechanically coherent -- this "
        "player can execute it. Incoherent picks are still wrong at every rank."),
}

RISK_TOLERANCE = {
    "low": "RISK TOLERANCE LOW: favour reliable activation and safer completion curves, "
           "avoid highly conditional items, keep a defensive margin.",
    "medium": "",  # the default optimisation, no extra bias
    "high": "RISK TOLERANCE HIGH: a glassier or more execution-heavy build is acceptable if "
            "it raises the ceiling -- but still reject mechanically incoherent items, and do "
            "not confuse risk tolerance with off-meta randomness.",
}

# Damage <-> durability lean, set by the Build Bias slider. A TIE-BREAKER, not
# a licence: it never outranks champion identity, the selected playstyle, the
# role, or item/rune legality. The hierarchy is stated inside each entry
# because the model reads these one at a time, and "balanced" is the empty
# string on purpose -- the default request must build the exact prompt it
# builds today, which also keeps every cached balanced build valid.
_BIAS_GUARD = (
    " This bias NEVER overrides champion identity, viable damage type, scaling, the "
    "selected playstyle, role requirements, or item/rune legality. It decides between "
    "viable alternatives that are otherwise close, nothing more. Do not invent an "
    "off-meta archetype to satisfy it. Where the bias materially changed a pick, say so "
    "in that item's or rune's reason -- once, where it mattered, not on every line.")

BUILD_BIAS = {
    "max_durability": (
        "BUILD BIAS MAXIMUM DURABILITY: build the most durable competitive version of THIS "
        "champion on THIS playstyle. That is not 'full tank': a damage champion stays a "
        "damage champion and keeps the offensive core its kit scales from -- express the "
        "bias through the most defensive VIABLE options instead: survivability-oriented "
        "damage items, HP-carrying options of the right damage type, defensive boots, "
        "protective actives, sustain and safety in the rune page, the less greedy choice "
        "wherever two viable picks differ mainly in risk."
        + _BIAS_GUARD),
    "durability": (
        "BUILD BIAS DURABILITY-LEANING: when two viable options are close, prefer the one "
        "that adds survivability -- HP, resists, sustain, shields, defensive boots, safer "
        "runes -- while keeping the offense this champion and playstyle need to function. "
        "A bruiser stays a bruiser, on its safer side."
        + _BIAS_GUARD),
    "balanced": "",  # the default optimisation, no extra bias
    "damage": (
        "BUILD BIAS DAMAGE-LEANING: when two viable options are close, prefer the one that "
        "adds damage -- but keep survivability that is load-bearing for this champion and "
        "playstyle. A bruiser stays a bruiser, on its more aggressive side."
        + _BIAS_GUARD),
    "max_damage": (
        "BUILD BIAS MAXIMUM DAMAGE: optimise aggressively toward this kit's damage -- "
        "burst, sustained output, penetration and offensive scaling as THIS champion "
        "expresses them. Keep defensive investment only where it is load-bearing: required "
        "for the champion to function, or carrying unusually strong offensive synergy. "
        "This does not mean glass cannon on champions it does not suit, and a tank asked "
        "for maximum damage becomes the most offensive viable TANK, not a different class."
        + _BIAS_GUARD),
}

# Candidate archetypes are deliberately more specific than the public AD/AP
# selector.  AD/AP says which stat scales the build; an archetype says how the
# damage is delivered.  Treating "AD" as one build path is what allowed three
# crit Varus candidates to hide both lethality and on-hit from the engine.
_ARCHETYPE_TEXT = {
    "ad-caster": "AD ability burst/poke with physical penetration and haste",
    "ad-crit": "critical-strike basic attacks",
    "ad-on-hit": "attack-speed/on-hit sustained damage",
    "ap-caster": "AP ability burst/poke with magic penetration and haste",
    "ap-on-hit": "AP attack-speed/on-hit sustained damage",
    "hybrid-on-hit": "a coherent mixed-scaling on-hit path",
}


def _damage_archetypes(champion: str, combat: dict, scaling: dict,
                       damage_path: str = "standard") -> list[dict]:
    """Return every credible damage engine the tournament must represent.

    This is intentionally conservative.  A stray AP ratio never creates an AP
    build: only the reviewed hybrid roster may cross the champion's normal
    damage identity.  Crit and on-hit are delivery engines, not aliases for AD,
    so they remain separate even when both buy physical items.
    """
    identity = profiles.build_identity(champion)
    pattern = combat.get("basicAttackPattern", "mixed")
    champion_class = (CHAMPS.get(champion) or {}).get("class", "")
    crit = (combat.get("critValue") == "high" or champion_class == "Marksman")
    on_hit = combat.get("repeatedOnHitReliance") in {"medium", "high"}
    attack_based = pattern in {"basic-attack-carry", "repeated-attacks", "mixed"}
    ids: list[str] = []

    def add(value: str) -> None:
        if value not in ids:
            ids.append(value)

    allow_ad = damage_path in {"standard", "ad", "hybrid"}
    allow_ap = damage_path in {"standard", "ap", "hybrid"}
    if damage_path == "standard":
        allow_ad = identity == "physical" or champion in HYBRID_DAMAGE_CHAMPIONS
        allow_ap = identity == "magic" or champion in HYBRID_DAMAGE_CHAMPIONS

    if allow_ad:
        if (pattern in {"caster", "ability-weaving", "mixed"} or not attack_based
                or champion in HYBRID_DAMAGE_CHAMPIONS):
            add("ad-caster")
        if crit:
            add("ad-crit")
        if on_hit:
            add("ad-on-hit")
        if not any(x.startswith("ad-") for x in ids):
            add("ad-caster")
    if allow_ap:
        add("ap-caster")
        if on_hit or attack_based:
            add("ap-on-hit")
    if damage_path in {"standard", "hybrid"} and champion in HYBRID_DAMAGE_CHAMPIONS:
        add("hybrid-on-hit" if on_hit or attack_based else "ap-caster")

    # One completion can cheaply provide more hypotheses.  Five bounds prompt
    # size and engine latency while covering every meaningful axis on the most
    # flexible champions (Varus/Kai'Sa/Kayle).
    ids = ids[:5]
    return [{"id": value, "description": _ARCHETYPE_TEXT[value]} for value in ids]


def _tournament_candidate_count(archetypes: list[dict]) -> int:
    """Three hypotheses for simple kits, one per path for flexible kits."""
    return max(3, min(5, len(archetypes)))


def _candidate_rune_names(candidate: dict) -> list[str]:
    """Flatten a tournament candidate's rune page for the fight engine."""
    page = candidate.get("runes") or {}
    return [r for r in ([page.get("keystone")] + list(page.get("minors") or [])
                        + [page.get("flex")]) if isinstance(r, str) and r]


def _candidate_signature(candidate: dict) -> tuple:
    """The tested core a final answer must preserve exactly."""
    page = candidate.get("runes") or {}
    spells = [s.get("name") if isinstance(s, dict) else s
              for s in (candidate.get("summoners") or [])]
    return (
        tuple(candidate.get("items") or []),
        candidate.get("boots") or "",
        page.get("keystone") or "",
        tuple(page.get("minors") or []),
        page.get("flex") or "",
        tuple(sorted(s for s in spells if isinstance(s, str))),
    )


def _legal_tournament_candidates(payload: dict, allowed_items: list[str], *,
                                 item_locks: list[str] | None = None,
                                 boot_lock: str = "",
                                 rune_locks: list[str] | None = None,
                                 role: str = "", enemies_known: bool = False,
                                 expected_count: int = 3,
                                 required_archetypes: list[str] | None = None,
                                 ) -> tuple[list[dict], list[str]]:
    """Apply the cheap, deterministic core gate before spending engine time.

    Full validation still runs on the winner. This pass only prevents invented
    items/runes and incomplete or duplicate cores from entering the comparison.
    """
    raw = payload.get("candidates") if isinstance(payload, dict) else None
    if not isinstance(raw, list):
        return [], ["response has no candidates list"]
    allowed = set(allowed_items)
    accepted: list[dict] = []
    errors: list[str] = []
    seen: set[tuple] = set()
    valid_archetypes = set(required_archetypes or [])
    represented: set[str] = set()
    for index, candidate in enumerate(raw[:expected_count], 1):
        if not isinstance(candidate, dict):
            errors.append(f"candidate {index} is not an object")
            continue
        label = str(candidate.get("id") or index)
        items = candidate.get("items") or []
        boots = candidate.get("boots") or ""
        runes = _candidate_rune_names(candidate)
        archetype = str(candidate.get("archetype") or "")
        problem = ""
        if len(items) != 5 or len(set(items)) != 5:
            problem = "must contain five unique items"
        elif any(item not in allowed for item in items):
            problem = "contains an item outside the supplied pool"
        elif validate_mod.hard_exclusive_violation(items):
            problem = validate_mod.hard_exclusive_violation(items) or "illegal item combination"
        elif any(lock not in items for lock in (item_locks or [])):
            problem = "does not preserve every locked item"
        elif boots not in ITEMS or ITEMS[boots].get("bootsTier") != 2:
            problem = "has invalid tier-2 boots"
        elif boot_lock and boots != boot_lock:
            problem = "does not preserve the locked boots"
        elif (rune_errors := runemeta.page_errors(candidate.get("runes") or {})):
            problem = "has an illegal rune page: " + rune_errors[0]
        elif any(lock not in runes for lock in (rune_locks or [])):
            problem = "does not preserve every locked rune"
        elif len(candidate.get("summoners") or []) != 2:
            problem = "must contain two summoner spells"
        elif not (legal_spells := summoners.enforce(
                candidate.get("summoners") or [], role, enemies_known)):
            problem = "has illegal summoner spells"
        elif valid_archetypes and archetype not in valid_archetypes:
            problem = f"has unknown or missing archetype {archetype!r}"
        elif valid_archetypes and not _combo_matches_archetype(tuple(items), archetype):
            problem = f"does not actually satisfy its declared {archetype!r} archetype"
        if not problem and sorted(legal_spells) != sorted(candidate.get("summoners") or []):
            # A jungler without Smite, or a spell outside the request's pool, is
            # repaired deterministically after the judge anyway.  Rejecting the
            # candidate for it meant a jungle tournament almost never ran; apply
            # the same repair here so the measured core is the one that ships.
            candidate = {**candidate, "summoners": legal_spells}
        signature = _candidate_signature(candidate)
        if not problem and signature in seen:
            problem = "duplicates another candidate"
        if problem:
            errors.append(f"candidate {label} {problem}")
            continue
        seen.add(signature)
        if archetype:
            represented.add(archetype)
        accepted.append(candidate)
    if len(raw) != expected_count:
        errors.append(f"expected exactly {expected_count} candidates, received {len(raw)}")
    missing = valid_archetypes - represented
    # When there are more paths than slots this can never happen because the
    # caller sets expected_count to the number of paths (up to five).  Simple
    # kits have fewer paths than the three-hypothesis floor and may repeat one.
    if missing:
        errors.append("missing required damage archetypes: " + ", ".join(sorted(missing)))
    return accepted, errors


def _settle_tournament_label(res: dict, meta: dict | None,
                             tested_signatures: set[tuple]) -> dict | None:
    """Keep the engine verdict only while the final core is one it measured.

    Post-judge validation can legitimately repair items, runes or summoners.
    That used to raise, which turned a legal build into a 500; now the build
    ships and the tournament metadata keeps its measurements but names no
    winner, so nothing downstream can present it as engine-judged.
    """
    if not meta or _candidate_signature(res) in tested_signatures:
        return meta
    print(f"[advisor] post-judge validation changed the tested core "
          f"(judged {meta.get('winner')!r}); returning the repaired build "
          "without the engine-judged label", file=sys.stderr)
    return {**meta, "winner": None, "judgedWinner": meta.get("winner"),
            "coreRepairedAfterJudge": True}


def _simulate_tournament(champion: str, candidates: list[dict],
                         skill_level: str = "average") -> list[dict]:
    """Measure every legal candidate under the same level and target suite."""
    from web.fight_engine import (ENGINE_FX, analyze_build, champion_mechanics_coverage,
                                  conditional_damage_scenarios,
                                  evaluation_vector)

    overrides = _load("item_engine_overrides.json", {}) or {}

    def coverage(slugs: list[str]) -> list[dict]:
        gaps = []
        for slug in slugs:
            if not (ITEMS.get(slug) or {}).get("passives"):
                continue
            fx = ENGINE_FX.get(slug) or {}
            active = [k for k, value in fx.items() if not k.startswith("_")
                      and value not in (0, 0.0, None, {}, [])]
            entry = overrides.get(slug) or {}
            notes = str(entry.get("_why") or " ".join(
                str(value) for key, value in entry.items()
                if key.startswith("_") and isinstance(value, str)))
            incomplete = re.search(
                r"not model(?:led|ed)|no (?:separate )?(?:combat )?(?:effect )?key|"
                r"engine has neither|priced on its stats|left out|cannot (?:open|see|price)",
                notes, re.I)
            if not active or incomplete:
                gaps.append({
                    "item": slug,
                    "status": "stats_only" if not active else "partial",
                    "modeledChannels": sorted(active),
                    "limitation": notes[:700],
                })
        return gaps

    measured: list[dict] = []
    champion_coverage = champion_mechanics_coverage(champion)
    for candidate in candidates:
        items = list(candidate["items"]) + [candidate["boots"]]
        runes = _candidate_rune_names(candidate)
        full = analyze_build(champion, items, runes, level=15)
        vector = evaluation_vector(champion, items, runes, level=15)
        conditional = conditional_damage_scenarios(
            champion, items, runes, level=15, skill_level=skill_level)
        expected_panel = conditional["bands"]["expected"]
        measured.append({
            "id": candidate.get("id"),
            "archetype": candidate.get("archetype"),
            "hypothesis": str(candidate.get("hypothesis") or "")[:300],
            "core": {
                "items": candidate["items"], "boots": candidate["boots"],
                "runes": candidate["runes"], "summoners": candidate["summoners"],
            },
            "engine": {
                "burst": full.get("burst"), "dps": full.get("dps"),
                "ttk": full.get("ttk"), "damageBeforeDeath": vector.get("damageBeforeDeath"),
                "aoeDamage": vector.get("aoeDamage"), "ehp": full.get("ehp"),
                "timeToDie": vector.get("timeToDie"),
                "survivalTime": full.get("survivalTime"),
                "healing": full.get("healing"), "shields": full.get("shields"),
                "damagePrevented": full.get("damagePrevented"),
                "goldEfficiency": vector.get("goldEfficiency"),
                "itemAblation": full.get("items"), "runeAblation": full.get("runes"),
                "damageLost": full.get("damageLost"),
                "damageScenarios": expected_panel,
                "conditionalDamage": conditional,
                "coverageGaps": coverage(items),
                "championMechanicsCoverage": champion_coverage,
            },
        })
    return measured


def _candidate_rune_pages(candidates: list[dict], rune_locks: list[str] | None = None) -> list[dict]:
    """Legal pages made only from runes the model nominated in its three builds."""
    from itertools import product

    pages: list[dict] = []
    seen: set[tuple] = set()
    all_names = {r for candidate in candidates for r in _candidate_rune_names(candidate)}
    keystones = sorted(r for r in all_names
                       if runemeta.BY_NAME.get(r, {}).get("type") == "Keystone")
    trees = sorted({str((candidate.get("runes") or {}).get("primaryTree") or "")
                    for candidate in candidates} - {""})
    for tree in trees:
        by_slot = {
            slot: sorted(r for r in all_names if runemeta.SLOT_OF.get(r) == (tree, slot))
            for slot in (1, 2, 3)
        }
        flexes = sorted(r for r in all_names
                        if runemeta.BY_NAME.get(r, {}).get("type") != "Keystone"
                        and runemeta.SLOT_OF.get(r, ("", 0))[0] not in ("", tree))
        if any(not by_slot[slot] for slot in (1, 2, 3)) or not flexes:
            continue
        for keystone, minors, flex in product(
                keystones, product(by_slot[1], by_slot[2], by_slot[3]), flexes):
            page = {"keystone": keystone, "primaryTree": tree,
                    "minors": list(minors), "flex": flex}
            if runemeta.page_errors(page):
                continue
            names = _candidate_rune_names({"runes": page})
            if any(lock not in names for lock in (rune_locks or [])):
                continue
            signature = (keystone, tree, tuple(minors), flex)
            if signature not in seen:
                seen.add(signature)
                pages.append(page)

    # Always retain the authored pages. This also handles a three-build set
    # whose union cannot form all three slots of another candidate's tree.
    for candidate in candidates:
        page = dict(candidate.get("runes") or {})
        names = _candidate_rune_names({"runes": page})
        signature = (page.get("keystone"), page.get("primaryTree"),
                     tuple(page.get("minors") or []), page.get("flex"))
        if (not runemeta.page_errors(page)
                and not any(lock not in names for lock in (rune_locks or []))
                and signature not in seen):
            seen.add(signature)
            pages.append(page)
    return pages


def _ordered_engine_items(combo: tuple[str, ...], candidates: list[dict]) -> list[str]:
    """Give an engine-discovered set the purchase order the model implied."""
    missing = 99
    position = {}
    for slug in combo:
        seen = [list(c.get("items") or []).index(slug)
                for c in candidates if slug in (c.get("items") or [])]
        position[slug] = sum(seen) / len(seen) if seen else missing
    ordered = sorted(combo, key=lambda slug: (position[slug], slug))
    # Late strategic items still obey their minimum purchase position.
    for slug, cfg in itemmeta.LATE_STRATEGIC.items():
        if slug not in ordered:
            continue
        minimum = int(cfg.get("minPosition", 4)) - 1
        current = ordered.index(slug)
        if current < minimum:
            ordered.insert(min(minimum, len(ordered) - 1), ordered.pop(current))
    return ordered


def _item_archetype_signals(slug: str) -> set[str]:
    """Damage-engine signals used to keep optimizer paths coherent."""
    item = ITEMS.get(slug) or {}
    stats = set(item.get("stats") or {})
    text = " ".join(item.get("passives") or []).lower()
    signals: set[str] = set()
    if "ad" in stats:
        signals.add("ad")
    if "ap" in stats:
        signals.add("ap")
    if "crit" in stats or "critical strike" in text:
        signals.add("crit")
    if "attackSpeed" in stats:
        signals.add("attack-speed")
    if ("on hit" in text or "on-hit" in text or "attacks deal" in text
            or "attackSpeed" in stats):
        signals.add("on-hit")
    if "physicalPenFlat" in stats or "physicalPen" in stats:
        signals.add("physical-pen")
    if "magicPenFlat" in stats or "magicPen" in stats:
        signals.add("magic-pen")
    return signals


def _item_supports_archetype(slug: str, archetype: str) -> bool:
    """Whether an item belongs in a path's search pool.

    ATTACK SPEED IS SCALING-AGNOSTIC and must never on its own qualify an item
    for a specific scaling path.  It amplifies whatever damage the build
    already deals, so "has attack speed" says nothing about whether the item's
    own damage comes from AD or AP.

    Leaving it in the `ad-crit` OR meant every attack-speed item qualified for
    an AD crit search, including items with zero AD and zero crit.  Exactly two
    live items are affected and both are pure AP: Nashor's Tooth and Dusk and
    Dawn.  That is how a 3,100-gold item giving Jinx 60 AP, 20 ability haste
    and no crit reached her maximum-damage pool, where it then won on on-hit
    re-applications while most of its stat line was wasted.

    An item whose offensive stat line is purely magical has no place in an AD
    path, and a purely physical one has none in an AP path.  Items carrying
    BOTH (Guinsoo's Rageblade) stay eligible for both, which is what the
    hybrid roster needs.  Items carrying NEITHER, such as At Wit's End with its
    flat magic on-hit and no AP to scale, stay eligible for on-hit paths on
    either side, because nothing about them is wasted.
    """
    sig = _item_archetype_signals(slug)
    magic_only = "ap" in sig and "ad" not in sig
    phys_only = "ad" in sig and "ap" not in sig
    return {
        "ad-caster": bool(sig & {"ad", "physical-pen"}) and not magic_only,
        "ad-crit": bool(sig & {"ad", "crit"}) and not magic_only,
        "ad-on-hit": bool(sig & {"ad", "on-hit", "attack-speed"}) and not magic_only,
        "ap-caster": bool(sig & {"ap", "magic-pen"}) and not phys_only,
        "ap-on-hit": bool(sig & {"ap", "on-hit", "attack-speed"}) and not phys_only,
        "hybrid-on-hit": bool(sig & {"ad", "ap", "on-hit", "attack-speed"}),
    }.get(archetype, True)


def _combo_matches_archetype(combo: tuple[str, ...], archetype: str) -> bool:
    sigs = [_item_archetype_signals(slug) for slug in combo]
    count = lambda key: sum(key in row for row in sigs)
    if archetype == "ad-crit":
        return count("crit") >= 2 and count("ad") >= 2
    if archetype == "ad-on-hit":
        return count("on-hit") >= 2 and count("ad") >= 1
    if archetype == "ap-on-hit":
        return count("on-hit") >= 2 and count("ap") >= 1
    if archetype == "hybrid-on-hit":
        return count("on-hit") >= 2 and count("ad") >= 1 and count("ap") >= 1
    if archetype == "ap-caster":
        return count("ap") >= 3
    if archetype == "ad-caster":
        return count("ad") >= 3
    return True


# How much of the tournament objective is dealing damage, and how much is being
# there to deal it.  The tournament started life measuring damage only, which
# was the right place to start -- damage is the axis the engine measures best --
# but it also meant a durability request was answered by a damage optimizer,
# and the engine challenger could only ever hand back the bloodiest build it
# found.  max_damage keeps a survival weight of exactly zero so that path is
# numerically unchanged.
TOURNAMENT_BLEND = {
    "max_damage": (1.00, 0.00),
    "damage": (0.80, 0.20),
    "balanced": (0.60, 0.40),
    "durability": (0.40, 0.60),
    "max_durability": (0.20, 0.80),
}

# The survival half, written in the vocabulary data/build_objectives.json
# already uses so there is one set of reference values, not two.
#
# damageBeforeDeath sits HERE rather than on the damage side on purpose: it is
# the only measurement that prices durability in the currency a carry actually
# cares about. A pure timeToDie objective rewards a marksman for buying two
# armour items and contributing nothing, which is the failure mode that makes
# "durability" builds useless. Weighted with compEhp it asks the real question:
# how much damage does this build get to deliver before it dies.
TOURNAMENT_SURVIVAL_WEIGHTS = {
    "damageBeforeDeath": 0.28,
    "timeToDie": 0.34,
    "compEhp": 0.24,
    "selfSustain": 0.14,
}


# Which biases actually route through the tournament.  Kept separate from the
# blend table because it is a LATENCY decision, not a modelling one: the engine
# search costs roughly 25-30 seconds of local compute on top of two model calls
# (the advisor function allows 300s, so it fits, but the user waits for it).
# Dropping "balanced" from this set is the one-line way to keep the default
# generation on the fast single-call path while every explicit lean still gets
# measured.
TOURNAMENT_BIASES = frozenset(TOURNAMENT_BLEND)


def _tournament_blend(build_bias: str) -> tuple[float, float]:
    return TOURNAMENT_BLEND.get(build_bias, TOURNAMENT_BLEND["max_damage"])


def _tournament_prefilter_weights(base_objective: str, damage_w: float,
                                  survival_w: float) -> dict | str:
    """Blend the cheap prefilter the same way as the final objective.

    The prefilter decides which items even reach the expensive scenario pass.
    Leaving it on pure damage while the final score counted survival meant a
    durability request searched a damage-ranked pool and never saw an armour
    item, so the challenger was drawn from the wrong shortlist every time.
    """
    from web.fight_engine import objective_weights

    if not survival_w:
        return base_objective
    blended = {field: weight * damage_w
               for field, weight in objective_weights(base_objective).items()}
    for field, weight in TOURNAMENT_SURVIVAL_WEIGHTS.items():
        blended[field] = blended.get(field, 0.0) + weight * survival_w
    return blended


def _engine_challenger(champion: str, candidates: list[dict], *, role: str = "",
                       enemies_known: bool = False,
                       item_locks: list[str] | None = None,
                       rune_locks: list[str] | None = None,
                       skill_level: str = "average",
                       build_bias: str = "max_damage",
                       allowed_items: list[str] | None = None) -> tuple[dict | None, dict]:
    """Search each declared archetype for an engine challenger.

    The model supplies a coherent seed and rune page for every path.  Items are
    then drawn from the full legal advisor pool for that path, not merely the
    union of the model's nominations.  A challenger is returned only when it
    beats every authored candidate on the objective for THIS request, which is
    a blend of damage delivered and surviving to deliver it: see
    TOURNAMENT_BLEND.  For max_damage the survival weight is zero and the score
    is the damage scenario score exactly as it was before the blend existed.
    """
    from itertools import combinations

    from web.fight_engine import (REF_BURST, REF_DPS, REF_FIGHT,
                                  conditional_damage_scenarios, evaluation_vector,
                                  objective_score)

    base_prefilter = ("burst_damage" if (CHAMPS.get(champion) or {}).get("class")
                      in {"Mage", "Assassin"} else "sustained_damage")
    damage_w, survival_w = _tournament_blend(build_bias)
    prefilter_objective = _tournament_prefilter_weights(
        base_prefilter, damage_w, survival_w)
    objective = ("multi_profile_damage" if not survival_w
                 else f"multi_profile_{build_bias}")
    weights = {"fiveTargetDps": 0.60, "fiveTargetBurst": 0.10,
               "oneVsThreeDamage": 0.30}

    def scenario_score(panel: dict) -> float:
        targets = list((panel.get("targets") or {}).values())
        one_three = (panel.get("oneVsThree") or {}).get("totalDamage", 0)
        if not targets:
            return 0.0
        mean_dps = sum(row.get("dps8", 0) for row in targets) / len(targets)
        mean_burst = sum(row.get("burst3", 0) for row in targets) / len(targets)
        # The 1v3 reference is three targets receiving reference DPS for the
        # full fight. A no-AoE build still earns its primary-target damage.
        return round(100.0 * (
            weights["fiveTargetDps"] * mean_dps / REF_DPS
            + weights["fiveTargetBurst"] * mean_burst / REF_BURST
            + weights["oneVsThreeDamage"] * one_three
            / (REF_DPS * REF_FIGHT * 3.0)
        ), 1)

    def survival_score(items: list[str], rune_names: list[str]) -> float:
        """The staying-alive half, on the same 0-100 scale as the damage half.

        Not conditional-banded: the floor/expected/ceiling panels describe
        execution-dependent DAMAGE triggers, and health, resists and sustain do
        not need a player to land anything.
        """
        return objective_score(
            evaluation_vector(champion, items, rune_names, level=15),
            TOURNAMENT_SURVIVAL_WEIGHTS)

    def skill_adjusted_score(items: list[str], rune_names: list[str]) -> float:
        conditional = conditional_damage_scenarios(
            champion, items, rune_names, level=15, skill_level=skill_level)
        bands = conditional["bands"]
        if not conditional["hasConditionalEffects"]:
            damage = scenario_score(bands["expected"])
        else:
            damage = sum(conditional["weights"][band] * scenario_score(panel)
                         for band, panel in bands.items())
        if not survival_w:
            return round(damage, 1)
        return round(damage_w * damage
                     + survival_w * survival_score(items, rune_names), 1)
    def legal_items(combo: tuple[str, ...]) -> bool:
        return not (
            validate_mod.hard_exclusive_violation(list(combo))
            or any(lock not in combo for lock in (item_locks or []))
            or (not enemies_known and any(s in itemmeta.SITUATIONAL_ONLY for s in combo))
            or not supportitem.build_is_legal(list(combo), role)
        )

    # Establish the score to beat across every target profile and the capped
    # 1v3. Boots count as the sixth inventory purchase in the engine.
    authored_scores = []
    for candidate in candidates:
        authored_scores.append(skill_adjusted_score(
            list(candidate["items"]) + [candidate["boots"]],
            _candidate_rune_names(candidate)))
    threshold = max(authored_scores)

    # Search each path independently.  Start from the full legal advisor item
    # pool, rank individual items cheaply, then enumerate the best bounded path
    # pool.  Authored items and locks are always retained even when a one-item
    # probe understates a synergy piece such as Infinity Edge or Runaan's.
    by_path: dict[str, list[dict]] = {}
    for candidate in candidates:
        by_path.setdefault(str(candidate.get("archetype") or "unlabelled"), []).append(candidate)
    universe = sorted(set(allowed_items or []) | {
        slug for candidate in candidates for slug in candidate.get("items") or []
    })
    finalists: list[tuple[float, tuple[str, ...], str, dict, str]] = []
    searched = 0
    path_meta: dict[str, dict] = {}
    for archetype, seeds in by_path.items():
        boots = sorted({str(c.get("boots") or "") for c in seeds} - {""})
        pages = _candidate_rune_pages(seeds, rune_locks)
        authored_pages = [c.get("runes") or {} for c in seeds]
        if not boots or not pages:
            path_meta[archetype] = {"reason": "no legal boots or rune pages"}
            continue
        seed_boot = Counter(c.get("boots") for c in seeds if c.get("boots")).most_common(1)[0][0]
        probe_page = authored_pages[0]
        authored_items = {slug for c in seeds for slug in c.get("items") or []}
        eligible = [slug for slug in universe
                    if archetype == "unlabelled" or _item_supports_archetype(slug, archetype)]
        ranked_items = []
        for slug in eligible:
            vector = evaluation_vector(
                champion, [slug, seed_boot],
                _candidate_rune_names({"runes": probe_page}), level=15, fast=True)
            ranked_items.append((objective_score(vector, prefilter_objective), slug))
            searched += 1
        ranked_items.sort(reverse=True)
        pool = sorted(set(slug for _score, slug in ranked_items[:11])
                      | authored_items | set(item_locks or []))
        shortlist: list[tuple[float, tuple[str, ...]]] = []
        for combo in combinations(pool, 5):
            if (not legal_items(combo)
                    or (archetype != "unlabelled"
                        and not _combo_matches_archetype(combo, archetype))):
                continue
            best_seed = 0.0
            for page in authored_pages:
                vector = evaluation_vector(
                    champion, list(combo) + [seed_boot],
                    _candidate_rune_names({"runes": page}), level=15, fast=True)
                best_seed = max(best_seed, objective_score(vector, prefilter_objective))
                searched += 1
            shortlist.append((best_seed, combo))
        shortlist.sort(key=lambda row: row[0], reverse=True)
        for _seed, combo in shortlist[:35]:
            for boot in boots:
                for page in pages:
                    vector = evaluation_vector(
                        champion, list(combo) + [boot],
                        _candidate_rune_names({"runes": page}), level=15, fast=True)
                    score = objective_score(vector, prefilter_objective)
                    searched += 1
                    finalists.append((score, combo, boot, page, archetype))
        path_meta[archetype] = {
            "eligibleItems": len(eligible), "boundedPool": len(pool),
            "legalCombinations": len(shortlist),
        }
    finalists.sort(key=lambda row: row[0], reverse=True)

    best: tuple[float, tuple[str, ...], str, dict, str] | None = None
    scenario_evaluations = 0
    for _prefilter, combo, boot, page, archetype in finalists[:120]:
        score = skill_adjusted_score(
            list(combo) + [boot], _candidate_rune_names({"runes": page}))
        scenario_evaluations += 1
        if best is None or score > best[0]:
            best = (score, combo, boot, page, archetype)
    if best is None or best[0] <= threshold + 0.1:
        return None, {"objective": objective, "weights": weights,
                      "blend": {"damage": damage_w, "survival": survival_w},
                      "prefilterObjective": prefilter_objective,
                      "searched": searched,
                      "scenarioEvaluations": scenario_evaluations,
                      "paths": path_meta,
                      "authoredBestScore": threshold,
                      "challengerScore": best[0] if best else None}

    score, combo, boot, page, archetype = best
    # Summoners do not alter the engine measurements. Keep the most common
    # complete pair rather than letting the optimizer pretend otherwise.
    spell_votes = Counter(tuple(sorted(
        s.get("name") if isinstance(s, dict) else s
        for s in (candidate.get("summoners") or []))) for candidate in candidates)
    spells = list(spell_votes.most_common(1)[0][0])
    challenger = {
        "id": "ENGINE-D",
        "archetype": archetype,
        "hypothesis": (f"Engine recombination winner across five target profiles and "
                       f"a capped 1v3, scored {damage_w:.0%} damage / "
                       f"{survival_w:.0%} survival for a {build_bias} request, "
                       f"conditional effects weighted for {skill_level} "
                       f"skill; score {score:.1f} versus authored best "
                       f"{threshold:.1f} across {searched} prefilter trials and "
                       f"{scenario_evaluations} scenario finalists."),
        "items": _ordered_engine_items(combo, candidates),
        "boots": boot, "runes": page, "summoners": spells,
    }
    if _candidate_signature(challenger) in {_candidate_signature(c) for c in candidates}:
        return None, {"objective": objective, "weights": weights,
                      "blend": {"damage": damage_w, "survival": survival_w},
                      "prefilterObjective": prefilter_objective,
                      "searched": searched,
                      "scenarioEvaluations": scenario_evaluations,
                      "paths": path_meta,
                      "authoredBestScore": threshold, "challengerScore": score,
                      "reason": "winner duplicates an authored candidate"}
    return challenger, {"objective": objective, "weights": weights,
                        "blend": {"damage": damage_w, "survival": survival_w},
                        "buildBias": build_bias,
                        "skillLevel": skill_level,
                        "prefilterObjective": prefilter_objective,
                        "searched": searched,
                        "scenarioEvaluations": scenario_evaluations,
                        "paths": path_meta,
                        "authoredBestScore": threshold, "challengerScore": score}


def _tournament_generation_prompt(prompt: str, archetypes: list[dict] | None = None,
                                  candidate_count: int = 3,
                                  build_bias: str = "max_damage") -> str:
    archetypes = archetypes or []
    damage_w, survival_w = _tournament_blend(build_bias)
    # This pass used to ask for "the requested maximum-damage goal" whatever
    # the bias was.  A champion with as many archetypes as slots (Varus: five)
    # then spent every slot on a pure damage probe, the durability request had
    # no durable candidate to choose, and all three biases returned the same
    # five items.  The bias has to shape each candidate, not just the judge.
    goal = (
        "the requested maximum-damage goal" if not survival_w else
        f"the requested {build_bias.replace('_', ' ')} goal. The engine will rank "
        f"them {damage_w:.0%} on damage delivered and {survival_w:.0%} on surviving "
        "to deliver it (damage before death, time to die, effective health, "
        "self-sustain). Build EACH archetype in the version that best serves that "
        "blend: an archetype probe is not an excuse to ignore the bias, and at "
        f"{survival_w:.0%} survival weight a candidate with no survivability-oriented "
        "option anywhere in its items, boots or runes is answering a different "
        "request")
    path_text = "\n".join(
        f"- {row['id']}: {row['description']}" for row in archetypes)
    path_rule = (f"""
The engine has identified these credible damage archetypes for this champion:
{path_text}
Every listed archetype MUST appear at least once. Use any remaining slots for
a materially different burst/sustained/delivery hypothesis inside the strongest
archetype. Do not label a build with an archetype it does not actually follow.
""" if archetypes else "")
    labels = "|".join(chr(ord("A") + i) for i in range(candidate_count))
    return prompt + f"""

ENGINE TOURNAMENT -- CANDIDATE PASS.
Do not return the full presentation schema above on this pass. In ONE response,
propose exactly {candidate_count} genuinely competitive, materially different builds for
{goal}. These are hypotheses for measurement, not
random novelty. One may favour peak sustained DPS, one burst/TTK, and one
damage delivery or survival where appropriate for this champion. Every build
must obey every item, rune, role, lock and identity rule above.
{path_rule}

Return ONLY JSON:
{{"candidates":[{{"id":"{labels}","archetype":"one exact archetype id above",
"hypothesis":"short trade-off hypothesis",
"items":["five slugs in purchase order"],"boots":"tier-2 slug",
"runes":{{"keystone":"name","primaryTree":"tree","minors":["three names"],
"flex":"name"}},"summoners":["spell","spell"]}}]}}
"""


def _tournament_judge_prompt(prompt: str, measured: list[dict],
                             build_bias: str = "max_damage") -> str:
    damage_w, survival_w = _tournament_blend(build_bias)
    # The judge has to know which question the numbers were ranked against.
    # Without this it read every tournament as a damage contest and explained
    # away a durability winner as "slightly lower DPS", which is the whole
    # point of the request rather than a flaw in the answer.
    objective_line = (
        f"\nOBJECTIVE FOR THIS REQUEST: {build_bias.replace('_', ' ')}. The engine "
        f"ranked candidates {damage_w:.0%} on damage delivered across the five target "
        f"profiles and the capped 1v3, and {survival_w:.0%} on surviving to deliver it "
        f"(damage before death, time to die, effective health against a mixed "
        f"composition, and self-sustain). "
        + ("Survivability carries no weight here, so judge on output and treat "
           "defensive value only as the practical trade it buys.\n"
           if not survival_w else
           "A candidate that wins on raw damage alone is NOT automatically the "
           "answer: say what the durability buys and what it costs. Still refuse a "
           "build that has stopped threatening anyone -- durability is worth nothing "
           "on a champion who can no longer kill.\n"))
    return prompt + objective_line + """

ENGINE TOURNAMENT -- FINAL JUDGE.
Below are the builds you proposed plus, when it found a measurable
improvement, one ENGINE-D challenger searched inside its declared damage
archetype. Every listed candidate was measured at level 15 under identical
deterministic reference targets. Select ONE WHOLE tested core. Do not splice a
new untested build. Return the normal full build JSON schema requested above,
preserving the selected candidate's exact five items and order, boots, rune
page and summoners.

The engine is authoritative only for the stated synthetic scenario. Prefer the
raw dimensions over a single hidden score. A small damage edge may be outweighed
by a real passive, revive, Lifeline, Stasis, delivery reliability or practical
fight value, but explain that trade using supplied facts. Never invent a metric.
Each candidate carries championMechanicsCoverage. If it is partial, do NOT use
the numeric score to eliminate an archetype whose defining passive, stack,
recast, conversion or execute appears in buildRelevantGaps. Explain the missing
mechanic and decide that comparison from grounded kit facts instead.

ENGINE COVERAGE: ordinary stats, rotations, target defenses, Lifeline shields,
damage reduction, Guardian Angel revive and Stasis are modeled, some only as
approximations. Stated item and rune proc cooldowns and arming delays are
applied to the simulated fight window; a 30-second proc cannot repeat in an
eight-second teamfight. Positioning, peel, objective timing, reset position and
actual proc opportunity are incomplete. Trigger eligibility is not inferred reliably:
Sudden Impact is now gated by an intrinsic dash, blink, teleport or stealth in
the champion's own ability text, and Flash is explicitly excluded. Treat other
unstructured positional or takedown opportunities conservatively.

DAMAGE SCENARIOS: every candidate includes separate three-second burst and
eight-second damage/DPS against ADC, mage, fighter, bruiser and tank profiles.
The oneVsThree case focuses a bruiser while an ADC and mage are available as
exactly two secondary targets for eight seconds. Treat it as an outgoing
damage-coverage test, NOT literal 1v3 win probability. Item AoE and champion
ability area damage are both counted on at most those two secondaries: the
ability shapes are derived across the roster from each ability's own damage
text, so a kit that clears three bodies is credited for it rather than scoring
zero. Three things are deliberately excluded and will read as single-target
even on an area champion: passive slots, empowered basic attacks and other
every-third-hit riders, all of which land on the body being attacked. Falloff
is applied where the tooltip states it, so a piercing line can credit less than
full damage to the secondaries. Positioning, target switching, enemy damage,
enemy abilities and CC are not simulated there at all.

CONDITIONAL DAMAGE: execution- or positioning-dependent effects are disclosed
as floor, expected and ceiling panels instead of being silently assumed active.
The skillLevel weights beside those panels are the numeric recommendation
weights: developing players lean toward floor/reliability, average players lean
toward expected value, and high-skill players receive more ceiling weight.
Unconditional stats such as Hexoptics C44's 25% Critical Rate remain active in
all three panels; only its distance-based Magnification changes. Do not quote a
ceiling number as expected damage, and do not treat a floor/ceiling spread as
free power. Mechanically proven cooldown, hit-count and health-threshold
conditions are evaluated directly and are not discounted merely for rank.

MEASUREMENTS:
""" + json.dumps(measured, ensure_ascii=False, separators=(",", ":"))


def advise(champion: str, role: str, enemies: list[str],
           allies: list[str] | None = None, playstyle: str = "standard",
           objective: str = "balanced", mode: str = "studio",
           game_phase: str = "balanced", damage_path: str = "standard",
           champion_form: str = "", ahead_enemy: str = "",
           risk_tolerance: str = "medium", skill_level: str = "average",
           build_bias: str = "balanced",
           locked_items: list[str] | None = None,
           locked_runes: list[str] | None = None,
           ladder_anchor: bool = True,
           engine_tournament: bool = False,
           on_progress=None) -> dict:
    # on_progress(event) is called with {"stage": ...} as the generation moves.
    # It is optional and side-effect free: nothing about the build depends on
    # whether anyone is listening.
    emit = on_progress or (lambda _event: None)
    mode = "counter" if mode == "counter" else "studio"
    # ladder_anchor=False is the "what would you build on your own" switch.
    #
    # The ladder block hands the model the items, keystones, spells and minors
    # the top fifty players run, as candidates it must score and argue away.
    # That is a strong anchor by design -- it stops identity drift, and the
    # validator enforces it -- but it means an answer is never purely the
    # model's own reading of the kit. Turning it off asks exactly that
    # question, and the difference between the two is itself informative: on
    # Graves into four tanks the anchored build and the free one agreed on the
    # keystone and on four of five items.
    #
    # The validator's ladder_core check is skipped with it, because demanding
    # a build justify skipping items it was never shown is incoherent.
    # A blank role is not "no role", it is a role nobody told us. Every rule
    # keyed on it then quietly does not apply -- most visibly Smite, which is
    # imposed on jungle builds and which a Hecarim counter came back without
    # because the request carried no role and the advisor therefore did not
    # know it was a jungle build. An explicit role always wins; this only
    # fills the blank, from the champion's own primary role.
    if not (role or "").strip():
        role = (CHAMPS.get(champion) or {}).get("role") or ""
    # Legacy playstyle aliases from older saved builds. 'sustain' predates the
    # split into damage variants; map it to the sustained-DPS preset (the app has
    # no 'sustained_damage' id -- 'dps' is that build). 'burst' and 'damage'
    # (Glass cannon) were presets in their own right until both turned out to
    # ask for the same build as one-shot; shared links, albums and cached keys
    # still carry those ids. Unknown ids fall through to the check below.
    playstyle = {"sustain": "dps", "sustained_damage": "dps",
                 "glass_cannon": "oneshot", "burst": "oneshot",
                 "damage": "oneshot"}.get(playstyle, playstyle)
    if mode == "counter" and not enemies:
        return {"error": "at least one enemy is required for a counter build"}
    if mode == "counter" and playstyle == "standard":
        playstyle = "adaptive"
    elif mode == "studio" and playstyle == "adaptive":
        playstyle = "standard"
    validation_style = "standard" if playstyle == "adaptive" else playstyle
    allowed_styles = available_playstyles(champion)
    if validation_style not in allowed_styles:
        return {
            "error": f"{playstyle!r} is not a supported preset for {champion}",
            "availablePlaystyles": (["adaptive"] + [s for s in allowed_styles if s != "standard"]
                                    if mode == "counter" else allowed_styles),
        }
    game_phase = game_phase if game_phase in GAME_PHASES else "balanced"
    damage_path = damage_path if damage_path in DAMAGE_PATHS else "standard"
    if damage_path != "standard" and champion not in HYBRID_DAMAGE_CHAMPIONS:
        return {"error": f"{damage_path!r} is not a supported damage path for {champion}"}
    # The key is checked AFTER the request is validated. A malformed request is
    # malformed whether or not this deployment can reach the model, and checking
    # in the other order made the answer depend on the environment: the same bad
    # playstyle reported "not a supported preset" on a machine with a key and
    # "DEEPSEEK_API_KEY is not set" on one without. CI, which has no key, is the
    # one that caught it.
    #
    # It checks the key the ACTIVE model needs, not DeepSeek's. Those were the
    # same thing while DeepSeek was the default and are not now.
    key = _api_key(KEY_NAME)
    if not key:
        raise SystemExit(advisor_env.missing_key_message(KEY_NAME)
                         + f" (ADVISOR_MODEL is {MODEL!r})")
    if champion == "Kayn":
        champion_form = champion_form if champion_form in KAYN_FORMS else "shadow-assassin"
    else:
        champion_form = ""
    if ahead_enemy not in (enemies or []):
        ahead_enemy = ""
    style = PLAYSTYLES.get(playstyle, PLAYSTYLES["standard"])
    obj = OBJECTIVES.get(objective, "")
    # "best" answers "what is the strongest build for this champion", and the
    # ladder block answers "what do the top fifty run". Asking the first while
    # supplying the second gets the second: measured on Graves, the block's
    # single named keystone was taken 4 runs out of 4 against a comp it did
    # not suit. So the anchor comes off with this objective unless the caller
    # has explicitly asked for it back.
    if objective == "best":
        ladder_anchor = False
    # And off whenever the measured builds are older than the patch being
    # played. Straight after a patch the list is nine items bought under
    # different rules, with nothing to say about anything the patch added --
    # 7.3 replaced ten items and rewrote forty-two, and Jinx's list still
    # named one the patch deleted. It comes back on its own with the first
    # collection on the new patch; see prompt.consensus_predates_patch.
    if ladder_anchor and prompt_mod.consensus_predates_patch():
        ladder_anchor = False
    risk_tolerance = risk_tolerance if risk_tolerance in RISK_TOLERANCE else "medium"
    risk = RISK_TOLERANCE[risk_tolerance]
    build_bias = build_bias if build_bias in BUILD_BIAS else "balanced"
    bias = BUILD_BIAS[build_bias]
    skill_level = skill_level if skill_level in SKILL_LEVEL else "average"
    skill = SKILL_LEVEL[skill_level]
    if mode == "studio":
        enemies = []
    enemies_known = bool(enemies)

    # Derive how this champion actually fights before anything else: the item
    # audit, the pre-filter and the boots policy all key off it.
    champion_record = CHAMPS.get(champion) or {}
    derived = profiles.profile(champion)
    combat = derived["combatProfile"]
    scaling = derived.get("scalingProfile", {})
    kit_linked_items = itemmeta.mandatory_audit(
        combat, scaling, damage_identity=profiles.build_identity(champion))
    pool_slugs, withheld = itemmeta.filter_candidates(
        champion_record, combat, scaling,
        damage_path=damage_path, enemies_known=enemies_known, role=role)
    # Locked items are the player's explicit instruction and outrank the filter:
    # withholding one would make the lock impossible to honour.
    for slug in (locked_items or []):
        resolved = _resolve_item(slug)
        if resolved and resolved not in pool_slugs and resolved in itemmeta.completed_items():
            pool_slugs.append(resolved)
            withheld = [w for w in withheld if w["item"] != resolved]
    pool_slugs.sort()
    for entry in withheld:
        print(f"[advisor] withheld {entry['item']}: {entry['reason']}", file=sys.stderr)

    # Never demand an audit of an item that was withheld from the pool. The two
    # lists are computed independently, so a kit-linked item that the filter
    # removes (Runaan's Hurricane is ranged-only, and Xin Zhao is melee) was
    # still required to appear in mandatoryAuditScores -- the model was being
    # asked to justify rejecting something it was never offered.
    #
    # Validation then failed on its absence, and the repair could not fix it
    # either, because the item is not in the pool the repair prompt carries: a
    # measured Gemini run burned two repair rounds and 68 of its 117 seconds on
    # exactly this, and the build that finally passed had the entry dropped
    # again as unselectable.
    audit_pool = set(pool_slugs)
    dropped_audit = [s for s in kit_linked_items if s not in audit_pool]
    if dropped_audit:
        kit_linked_items = [s for s in kit_linked_items if s in audit_pool]
        print(f"[advisor] audit skips withheld items: {', '.join(dropped_audit)}",
              file=sys.stderr)

    # Locks: items and runes the player pinned before generating. Resolve them
    # against the real pools now (a lock on an unknown slug is silently dropped
    # rather than failing the whole request), and cap them so a "locked" build is
    # still mostly the model's -- 3 of 5 items, 2 runes.
    locked_items = [s for s in (_resolve_item(x) for x in (locked_items or [])) if s][:3]
    boots_locks = [s for s in locked_items if ITEMS.get(s, {}).get("category") == "Boots"]
    item_locks = [s for s in locked_items if s not in boots_locks][:3]
    locked_boot = boots_locks[0] if boots_locks else ""
    locked_runes = [r for r in (RUNE_CANON.get(_canon(x)) for x in (locked_runes or [])) if r][:2]
    # Meta identity cards are keyed by display name including transform forms
    # ("Kayn (Rhaast)"); pick the form's card when a form was requested.
    identity_key = champion
    if champion_form == "rhaast":
        identity_key = "Kayn (Rhaast)"
    identity_card = prompt_mod.identity_card(identity_key)

    prompt = "\n\n".join(x for x in [
        prompt_mod.champion_block(champion, CHAMPS, ARCHETYPES, WRMETA, derived),
        prompt_mod.meta_identity_block(identity_key, constrain=(objective != "best")),
        prompt_mod.ladder_consensus_block(identity_key) if ladder_anchor else "",
        f"ROLE: {role}",
        # Every selected option governs the WHOLE loadout. Stated once here
        # rather than repeated inside each option's own text: those are written
        # per option, and this rule is the same for all of them. Almost all of
        # them were phrased about items -- "cheap first-ITEM spikes", "avoid
        # conditional ITEMS", "do not mix in AP ITEMS" -- so the rune page and
        # the summoner slots were the parts of the build the request never
        # reached, and a Sustain Early-game build could itemise correctly and
        # then take a keystone and a summoner that served neither.
        f"PLAYSTYLE (build toward this): {style}\n"
        "EVERY SELECTED OPTION GOVERNS THE ENTIRE LOADOUT -- items, boots, the rune page "
        "AND the summoner spells. That means the playstyle, the power curve, the "
        "optimisation goal, the damage path and the risk tolerance: each is a constraint "
        "on all four parts, not on the item list alone. Several of them are worded below "
        "in terms of items; read them as applying to the whole build. A rune page or a "
        "summoner pair that ignores the request has answered part of it.\n"
        "Apply each the way THIS kit can express it: a rune whose trigger the champion "
        "cannot meet, or a summoner that does nothing for how it actually fights, is not "
        "serving the request whatever its description promises.",
        # Personal optimisation contract: the chosen playstyle must actually
        # move the weighting, not collapse back to the safe Standard build.
        ("PERSONAL OPTIMISATION: within legality and practical champion function, optimise "
         "toward the selected playstyle, power curve, optimisation goal and risk tolerance. "
         "Do NOT pull the result back toward the Standard build merely because Standard would "
         "be safer -- the player asked for this playstyle on purpose. Illegal, "
         "resource-incompatible, or role-breaking builds are still rejected."
         if mode == "studio" else ""),
        f"OPTIMIZE FOR: {obj}" if obj else "",
        risk,
        bias,
        skill,
        GAME_PHASES[game_phase],
        DAMAGE_PATHS[damage_path],
        kayn_form_block(champion_form, playstyle),
        # Counter mode gets the structured, weighted threat picture; other modes
        # get the plain enemy line (usually "unknown" in studio).
        prompt_mod.enemy_threat_block(enemies, champion, WRMETA, role, pool_slugs)
        if enemies_known else _enemy_block(enemies or [], champion),
        prompt_mod.identity_threat_lines(enemies) if enemies_known else "",
        (f"SNOWBALL THREAT: {ahead_enemy} is ahead. If one main-build item should be "
         "replaced to survive or shut down this specific lead, return snowballSwap with "
         "the item to add, the main item it replaces, and the timing/condition. Return null "
         "only when no responsible single-item swap applies. Do not rebuild solely for one "
         "champion." if ahead_enemy else
         "SNOWBALL THREAT: none specified; return snowballSwap as null."),
        # Ally context (or the explicit no-allies assumption) only matters when
        # there is an enemy team to build against.
        prompt_mod.ally_context_block(allies) if enemies_known else (
            f"ALLY TEAM: {', '.join(allies)}" if allies else ""),
        _summoner_block(role, enemies_known, immobile=not summoners.has_mobility(
            champion, ' '.join((a.get('text') or '')
                               for a in (champion_record.get('abilities') or [])))),
        _support_item_block(role),
        # Locks: the player has pinned these and the build MUST contain them.
        # They are a constraint on an otherwise free optimisation, so build the
        # best loadout that still honours them -- do not just append them.
        _lock_block(item_locks, locked_boot, locked_runes),
        # Counter mode has the whole enemy comp in hand, so the build IS the
        # answer to it. Asking for reactive swaps on top produces contradictory
        # advice ("buy anti-heal vs their healing" when the comp already has the
        # healing the build is countering) and is the top source of the
        # needs-review flag. Tell the model plainly not to return them.
        ("COUNTER MODE: this build already targets the exact enemy comp above, so do NOT "
         "return any 'situational' item swaps or 'situationalRunes'. Bake every answer to "
         "this comp into the main five items and the rune page. Return situational and "
         "situationalRunes as empty lists. "
         "THE RUNE PAGE IS PART OF THE COUNTER, not a default carried over: pick the "
         "keystone and every minor against THIS comp the same way you pick items against "
         "it -- a comp of shields and disengage, a comp of hard engage, and a comp of "
         "sustained frontline each want a different page on the same champion. At least "
         "one threatResponses entry must have choiceType 'rune' naming which enemy or "
         "threat that rune answers; if you keep the champion's usual page, that entry "
         "must say why the usual page IS the counter. "
         "SKIP the full build evaluation: a counter build "
         "is wanted fast, so return buildScore as null and do not spend time scoring the "
         "eight categories. SKIP the per-pick PROSE for the same reason: "
         "candidateItemScores rows carry `item`, `score` and `synergyWith` only -- no "
         "`reason` -- and omit runeReasons and bootsReason entirely, returning "
         "situationalBoots as an empty list. "
         "KEEP `synergyWith`. It is a list of slugs, not prose, so it costs nothing to "
         "write, and a counter build is exactly where it matters most: five items chosen "
         "against a comp still have to work as ONE build on THIS champion. An item that "
         "answers an enemy but multiplies nothing in your kit is a slot spent on them "
         "rather than on winning, and the synergy share of the item rubric is what "
         "catches that. "
         "The counterSummary is where the prose "
         "belongs in this mode; writing it twice only makes the player wait. INSTEAD return a compact counterSummary that names the 2-4 "
         "problems you chose to solve, how each item/boot/rune choice answers them, the "
         "trade-offs you accepted, and the threats no build can fully answer. Do not imply "
         "the build perfectly counters all five enemies. Schema: "
         + prompt_mod.COUNTER_SUMMARY_SCHEMA if mode == "counter" else ""),
        # With no enemy team the model's strongest failure mode is inventing
        # one, then itemising against threats nobody mentioned.
        "" if enemies_known else prompt_mod.UNKNOWN_ENEMY_BLOCK,
        _meta_block(champion),
        prompt_mod.audit_block(kit_linked_items, combat),
        prompt_mod.rules_block(enemies_known, combat),
        prompt_mod.boots_block(champion_record.get("class", ""), enemies_known, damage_path),
        runemeta.pool_text_block(),
        prompt_mod.item_pool_block(
            pool_slugs,
            repeats_on_hit=combat.get("repeatedOnHitReliance") == "high"),
        prompt_mod.filtered_note(withheld),
    ] if x)

    champion_class = champion_record.get("class", "")
    emit({"stage": "model", "chars": 0})

    request_model = model_for_request(playstyle, champion)
    if request_model != MODEL:
        why = (f"champion {champion!r} is in the complex set"
               if playstyle in ("standard", "adaptive")
               else f"playstyle {playstyle!r} is an explicit request")
        print(f"[advisor] escalated to {request_model}: {why} "
              f"the base model measurably gets wrong", file=sys.stderr)

    def call(text: str) -> dict:
        # Pass each keyword only when it deviates from the default, so the
        # signature every existing caller and test stub sees is unchanged --
        # stubs monkeypatch _call as (key, text). The chosen model covers the
        # repair rounds too: a build authored by the premium model must not be
        # repaired by the one that caused the escalation.
        kwargs = {}
        if on_progress:
            kwargs["on_progress"] = on_progress
        if request_model != MODEL:
            kwargs["model"] = request_model
        return _call(key, text, **kwargs)

    tournament_meta = None
    tested_signatures: set[tuple] = set()
    if engine_tournament:
        # One candidate-generation completion, not three independent samples.
        # The second completion is the judge and sees measurements that did not
        # exist until after the first completion, so it cannot be collapsed into
        # the same model turn.
        try:
            damage_archetypes = _damage_archetypes(
                champion, combat, scaling, damage_path)
            candidate_count = _tournament_candidate_count(damage_archetypes)
            raw_candidates = call(_tournament_generation_prompt(
                prompt, damage_archetypes, candidate_count, build_bias))
            candidates, candidate_errors = _legal_tournament_candidates(
                raw_candidates, pool_slugs, item_locks=item_locks,
                boot_lock=locked_boot, rune_locks=locked_runes,
                role=role, enemies_known=enemies_known,
                expected_count=candidate_count,
                required_archetypes=[row["id"] for row in damage_archetypes])
            for message in candidate_errors:
                print(f"[advisor] tournament candidate rejected: {message}",
                      file=sys.stderr)
            if candidate_errors or len(candidates) != candidate_count:
                raise ValueError(
                    f"the candidate pass did not return {candidate_count} legal, distinct builds")
            emit({"stage": "simulating", "candidates": candidate_count})
            engine_name = ("Kayn (Rhaast)" if champion_form == "rhaast" else
                           "Kayn (Shadow Assassin)" if champion == "Kayn" else champion)
            challenger, search_meta = _engine_challenger(
                engine_name, candidates, role=role, enemies_known=enemies_known,
                item_locks=item_locks, rune_locks=locked_runes,
                skill_level=skill_level, build_bias=build_bias,
                allowed_items=pool_slugs)
            if challenger:
                candidates.append(challenger)
                print(f"[advisor] engine challenger added: {challenger['items']} "
                      f"({search_meta['challengerScore']} > "
                      f"{search_meta['authoredBestScore']})", file=sys.stderr)
            else:
                print(f"[advisor] engine search found no stronger challenger: "
                      f"{search_meta}", file=sys.stderr)
            measured = _simulate_tournament(
                engine_name, candidates, skill_level=skill_level)
            emit({"stage": "judging", "candidates": len(candidates)})
            judge_prompt = _tournament_judge_prompt(prompt, measured, build_bias)
            res = call(judge_prompt)

            tested_signatures = {_candidate_signature(c) for c in candidates}
            if _candidate_signature(res) not in tested_signatures:
                print("[advisor] tournament judge invented an untested core; requesting "
                      "a constrained correction", file=sys.stderr)
                res = call(judge_prompt + "\n\nERROR: Your previous final answer did not "
                           "preserve one tested core exactly. Return the full schema again "
                           "using one listed candidate unchanged.")
            if _candidate_signature(res) not in tested_signatures:
                raise RuntimeError("tournament judge refused to select a tested core")
            winner_id = next((c.get("id") for c in candidates
                              if _candidate_signature(c) == _candidate_signature(res)), None)
            tournament_meta = {
                "candidateCount": len(candidates),
                "modelCandidateCount": candidate_count,
                "damageArchetypes": damage_archetypes,
                "engineChallenger": bool(challenger),
                "engineSearch": search_meta,
                "winner": winner_id,
                "level": 15,
                "measurements": measured,
            }
        except Exception as exc:  # noqa: BLE001 -- tournament safely degrades
            # Max-damage generation should remain available if a newly added
            # champion has no engine formula or the compact candidate response
            # is malformed. The ordinary advisor is the known-good fallback.
            print(f"[advisor] engine tournament unavailable: {type(exc).__name__}: {exc}; "
                  "falling back to one ordinary generation", file=sys.stderr)
            tournament_meta = None
            res = call(prompt)
    else:
        res = call(prompt)
    emit({"stage": "validating"})

    def _check(build: dict):
        return validate_mod.validate(
            build, champion_class=champion_class, role=role, mode=mode,
            enemies_known=enemies_known, damage_path=damage_path,
            required_audit_items=kit_linked_items,
            allowed_items=pool_slugs, item_locks=item_locks, boot_lock=locked_boot,
            rune_locks=locked_runes, resolve_item=_resolve_item,
            # An explicitly selected alternative damage path is the player
            # overriding the standard identity on purpose; the lint stands
            # down rather than fight the request it was told to honour.
            identity=identity_card if damage_path == "standard" else None,
            # The REQUIRED CANDIDATES block demands a score for each ladder
            # core item. Counter mode receives that block already -- it was
            # only the enforcement that was studio-only, so a counter build
            # could quietly skip the champion's staple items and nothing
            # objected. That is identity drift, and it is the failure the
            # ladder core exists to catch; answering an enemy comp is not a
            # licence to stop playing the champion. Now enforced in both.
            ladder_core=(prompt_mod.ladder_core_slugs(identity_key)
                         if ladder_anchor else []),
            # How many enemies actually have hard crowd control, so the
            # validator can reject a tenacity rune bought against one.
            hard_cc_count=(threats_mod.team_threat_profile(enemies).get("hardCcCount")
                           if mode == "counter" and enemies else None),
            # How much the enemy team heals, so the validator can reject a
            # build that answers three heavy healers with nothing.
            healing_level=(threats_mod.team_threat_profile(enemies).get("healing", "")
                           if mode == "counter" and enemies else ""),
        )

    report = _check(res)
    # Repair the smallest thing that is wrong. A bad rune page should cost one
    # short call, not a whole regeneration that also throws away a correct build.
    for _ in range(repair.MAX_ATTEMPTS):
        if report.ok:
            break
        # Log WHAT failed, not just which section. Without this a regeneration
        # is invisible: you can see that it cost a second call and not why.
        for section in report.sections():
            for message in report.errors[section]:
                print(f"[advisor] invalid {section}: {message}", file=sys.stderr)
        targeted, blocking = repair.plan(report.sections())
        # An item list that is only MECHANICALLY wrong -- an exclusive pair, two
        # actives, an out-of-pool or reactive pick -- does not need a fresh
        # build, and regenerating for it is the single most expensive thing this
        # function does. Measured on a Riven counter run: two full regenerations
        # burned in a row, each returning the SAME illegal pair, before the
        # mechanical fallback at the end fixed it in microseconds. So fix it in
        # place first and only regenerate when that cannot.
        if "items" in blocking:
            fixes = repair.mechanical_item_repair(res, pool_slugs, enemies_known,
                                                  locked_items)
            # A missing requirement is not an illegality, so the repair above
            # cannot satisfy it -- it only ever drops offending items. Anti-heal
            # was costing a full regeneration, and regenerations dominate
            # counter-mode latency, so buy it with a swap instead.
            if not fixes and any("Grievous Wounds" in m for m in report.flat()):
                fixes = repair.anti_heal_repair(res, pool_slugs, locked_items)
            if fixes:
                for note in fixes:
                    print(f"[advisor] mechanical item repair: {note}", file=sys.stderr)
                report = _check(res)
                if report.ok:
                    break
                targeted, blocking = repair.plan(report.sections())
        if blocking or not targeted:
            # The item selection is wrong, and everything else describes that
            # selection -- so there is nothing worth preserving.
            print(f"[advisor] full regeneration; unrepairable sections: {blocking}",
                  file=sys.stderr)
            res = _call(key, prompt + "\n\nYour previous answer had ERRORS. Fix them and "
                        "return the corrected JSON only:\n- " + "\n- ".join(report.flat()))
            report = _check(res)
            continue
        for section in targeted:
            errors = report.errors[section]
            print(f"[advisor] targeted repair: {section} ({len(errors)} errors)",
                  file=sys.stderr)
            emit({"stage": "repairing", "section": section})
            patch = call(repair.repair_prompt(section, res, errors, pool_slugs, context=prompt))
            repair.apply_repair(res, section, patch)
        report = _check(res)

    # The repair budget can run out with the build still invalid, and until now
    # that build was returned anyway: validated, found broken, logged, served.
    # A measured Akali run shipped five times with boots sitting in the item
    # slots and once with an item that does not exist in the game, every failure
    # printed to the log first. Cached, one of those becomes that champion's
    # permanent answer.
    #
    # So the core is now a hard gate and the extras degrade instead. A build
    # whose items, boots, runes or locks are wrong is not a build; a build whose
    # situational swaps are badly timed is a good build with a bad footnote, and
    # dropping the footnote serves the player better than refusing outright.
    if not report.ok:
        CORE = ("items", "boots", "runes", "locks")
        broken_core = [s for s in report.sections() if s in CORE]
        # When the ONLY core failure is the item list, try fixing it
        # deterministically before refusing: exclusivity pairs, double actives
        # and pool violations are mechanical faults with mechanical fixes, and
        # the model has already supplied its own ranked alternatives to fill
        # from. A prod Riven run 502'd twice on Cleaver + Serylda's with the
        # LLM repair budget spent; the player should get the legal build, not
        # the error.
        if broken_core == ["items"]:
            fixes = repair.mechanical_item_repair(res, pool_slugs, enemies_known,
                                                  locked_items)
            if fixes:
                for note in fixes:
                    print(f"[advisor] mechanical item repair: {note}", file=sys.stderr)
                report = _check(res)
                broken_core = [s for s in report.sections() if s in CORE]
        if broken_core:
            detail = "; ".join(report.flat()[:3])
            print(f"[advisor] REFUSING to return an invalid build; "
                  f"unrepaired sections: {broken_core}", file=sys.stderr)
            raise RuntimeError(
                f"the build could not be made valid after {repair.MAX_ATTEMPTS} repair "
                f"attempts ({', '.join(broken_core)}): {detail}")
        dropped = report.sections()
        for section in dropped:
            if section in ("situational", "situationalRunes"):
                res[section] = []
            elif section == "snowball":
                res["snowballSwap"] = None
            elif section == "scores":
                # Scores explain the build rather than being it, so an unfixable
                # scoring section costs the explanation, not the recommendation.
                res["candidateItemScores"] = []
                res["mandatoryAuditScores"] = []
        print(f"[advisor] dropped unrepairable non-core sections: {dropped}", file=sys.stderr)

    # Summoners are the model's call now, because the choice reads the enemy
    # comp and the old lookup could not. The jungle rules are imposed on the
    # answer rather than trusted from it, and anything unusable falls back to
    # the lookup: a build should not be thrown away over a summoner spell.
    # The support item is guaranteed, not requested: a support build without it
    # has given up the role's gold income for the whole game. Runs before the
    # summoners so both corrections land on the same object.
    # Counter mode does not display per-pick PROSE (the counterSummary carries
    # it), so drop the reason text rather than caching and shipping something
    # nothing renders. `synergyWith` stays: it is the record of which of the
    # five items multiply each other, it costs a list of slugs rather than a
    # sentence, and stripping it turned the chemistry rule off in the one mode
    # where five items are picked against an enemy and still have to work as
    # one build.
    if mode == "counter":
        res["situationalBoots"] = []
        for _row in res.get("candidateItemScores") or []:
            if isinstance(_row, dict):
                _row.pop("reason", None)

    fixed_items, changed = supportitem.enforce(
        res.get("items") or [], role, champion_class)
    if changed:
        print(f"[advisor] support item enforced for {champion} ({role}): "
              f"{res.get('items')} -> {fixed_items}", file=sys.stderr)
        res["items"] = fixed_items

    raw_summoners = res.get("summoners") or []
    picked = summoners.enforce(raw_summoners, role, enemies_known)
    if picked:
        res["summoners"] = summoners.icons_for(picked)
        reason = str(res.get("summonerReason") or "").strip()
        res["summonerReason"] = reason or (
            f"{' and '.join(picked)}, chosen for this matchup.")
    else:
        res["summoners"], res["summonerReason"] = summoners.resolved(
            champion, role, champion_class, enemies_known)
        print(f"[advisor] summoners fell back to the rule table for {champion} "
              f"({role}); model returned {raw_summoners!r}", file=sys.stderr)

    # Validation and deterministic enforcement run after the judge. They may
    # repair prose or situational advice, but the engine badge is truthful only
    # while the item/rune/summoner core is still one of the measured candidates.
    # When repair did touch the core, the repaired build is still the legal one
    # to return; it just stops claiming a verdict the engine never gave.
    tournament_meta = _settle_tournament_label(res, tournament_meta, tested_signatures)

    # Normalised request metadata, so the frontend can show what the build was
    # optimised for and flag any playstyle the champion could not honour. Added
    # additively under a bumped schema version; old consumers ignore it.
    # How much of the final build the champion's top-50 ladder players also
    # equip -- surfaced to the UI as a credibility badge. None when this
    # champion has no fresh capture yet.
    #
    # Withheld while those captures predate the patch. The badge reads "items
    # this champion's top-50 players also equip RIGHT NOW", and after a patch
    # that rewrote the shop it would be measuring agreement with a game nobody
    # is playing -- a build that ignores three deleted items would score badly
    # for being correct. It also feeds the best-of vote, where it would pull
    # the winner toward pre-patch builds for the same wrong reason.
    res["ladderAgreement"] = (
        None if prompt_mod.consensus_predates_patch()
        else prompt_mod.ladder_agreement(
            identity_key, [s for s in (res.get("items") or []) if s]))

    res["schemaVersion"] = 2
    res["requestMeta"] = {
        "mode": mode,
        "requestedPlaystyle": playstyle,
        "resolvedPlaystyle": playstyle,   # a hard-invalid style errors earlier
        "playstyleAdjustment": None,
        "powerCurve": game_phase,
        "optimizationGoal": objective,
        "riskTolerance": risk_tolerance,
        "skillLevel": skill_level,
        "buildBias": build_bias,
        "enemyContext": "known" if enemies_known else "unknown",
        # Which transform form this build is for. The studio needs it to
        # show the matching kit: without it a Rhaast build was rendered
        # against Shadow Assassin's abilities and base stats.
        "championForm": champion_form or "",
    }
    if tournament_meta:
        res["engineTournament"] = tournament_meta

    for warning in report.warnings:
        print(f"[advisor] warning: {warning}", file=sys.stderr)
    if not report.ok:
        res["validationErrors"] = report.flat()
    if report.warnings:
        res["validationWarnings"] = report.warnings

    # One structured line per generation, to stderr (never stdout -- /api/build
    # parses stdout as JSON). Enough to diagnose a bad build without storing the
    # model's reasoning: mode, champion, what it was optimised for, and how the
    # validation went.
    print("[advisor] generated "
          f"mode={mode} champion={champion!r} role={role!r} playstyle={playstyle} "
          f"risk={risk_tolerance} bias={build_bias} enemyContext={'known' if enemies_known else 'unknown'} "
          f"candidates={len(pool_slugs)} errors={len(report.flat())} "
          f"warnings={len(report.warnings)} schemaVersion=2", file=sys.stderr)
    return res


# --------------------------------------------------------------------------
# best of N: the same prompt does not produce the same build
# --------------------------------------------------------------------------

# One generation is one sample from a model that is not deterministic, and the
# spread is not small: Vayne, asked three times on an IDENTICAL prompt, returned
# three different builds. Whichever one a player happens to get is then CACHED
# and becomes that champion's answer for everybody until the patch rolls.
#
# So the first generation of a request -- the one that fills an empty cache --
# samples the model several times and keeps the build the samples agree on.


def _build_elements(res: dict) -> dict:
    """The parts of a build that get voted on: items, boots, keystone, minors.

    Purchase order is deliberately excluded. Two runs that buy the same five
    items in a different order agree about the build; making the order part of
    the vote would score that as a disagreement.
    """
    runes = res.get("runes") or {}
    return {
        "items": [s for s in (res.get("items") or []) if s],
        "boots": [s for s in [res.get("boots")] if s],
        "runes": [r for r in ([runes.get("keystone")] + list(runes.get("minors") or [])) if r],
    }


def why_not(champion: str, items: list[str], boots: str,
            rune_names: list[str], candidate: str,
            playstyle: str = "standard", build_bias: str = "balanced",
            situational: list | None = None,
            situational_boots: list | None = None,
            enemies: list[str] | None = None, role: str = "",
            item_reasons: list | None = None, rune_reasons: dict | None = None,
            boots_reason: str = "", candidate_score: dict | None = None) -> dict:
    """Answer "why is CANDIDATE not in this build" for a build we generated.

    People disagree with builds constantly, and the difference between "this
    generator is stupid" and "fair enough" is whether the disagreement gets an
    answer. This is a deliberately SMALL call: one question, one comparison,
    a few sentences -- not a second build generation.

    The verdict is a closed set so the UI can colour it without parsing prose:
      viable_alternative  the candidate works here; the build's pick was a
                          preference, and the answer says what the trade is
      situational         right against specific conditions, wrong as a default
      worse_here          legal but beaten by what the build already does
      not_viable          wrong damage type, role, or resource for this kit

    The build's own situational swaps are passed in and checked FIRST. Without
    them the call could not see that the build already recommends the queried
    item against specific conditions, so it argued the item down as
    `worse_here` while the page above it listed the same item as a swap. That
    verdict is now impossible: a candidate the build recommends situationally
    is clamped to `situational` no matter what the model returns.
    """
    candidate = (candidate or "").strip()
    cand = ITEMS.get(candidate)
    if not cand:
        return {"error": f"unknown item {candidate!r}"}
    if candidate in (items or []) or candidate == boots:
        return {"error": f"{cand.get('name', candidate)} is already in this build"}
    key = _api_key(KEY_NAME)
    if not key:
        raise SystemExit(advisor_env.missing_key_message(KEY_NAME))

    build_names = [ITEMS.get(i, {}).get("name", i) for i in (items or [])]
    boots_name = ITEMS.get(boots, {}).get("name", boots) if boots else "none"
    # The whole brief the full generation reasons from -- the champion block
    # (abilities, ratios, stat profile), the meta identity card and the enemy
    # threat lines -- rather than a one-line kit summary. "Why not this item"
    # is the same judgement as "why these items", and it needs the same facts.
    # Each block is optional so an unknown champion or a missing card degrades
    # to a shorter prompt, never a crash.
    try:
        kit_facts = " ".join(profiles.kit_mechanics(champion))
    except Exception:
        kit_facts = ""
    brief: list[str] = []
    try:
        brief.append(prompt_mod.champion_block(champion, CHAMPS, ARCHETYPES, WRMETA,
                                              profiles.profile(champion)))
    except Exception:
        pass
    try:
        identity_key = "Kayn (Rhaast)" if champion == "Kayn" and playstyle == "rhaast" else champion
        brief.append(prompt_mod.meta_identity_block(identity_key))
    except Exception:
        pass
    enemies = [e for e in (enemies or []) if e]
    if enemies:
        try:
            brief.append(prompt_mod.enemy_threat_block(enemies, champion, WRMETA, role))
            brief.append(prompt_mod.identity_threat_lines(enemies))
        except Exception:
            pass
    brief_block = "\n\n".join(b for b in brief if b)

    # The build's own words: what it said about each item it chose, which items
    # it said multiply each other, why these runes and these boots. The answer
    # has to be consistent with them -- a verdict that contradicts the reason
    # printed three lines above it on the page is worse than no verdict.
    reasons_by: dict[str, dict] = {}
    for row in (item_reasons or []):
        if isinstance(row, dict) and row.get("item"):
            reasons_by[str(row["item"])] = row
    item_lines = []
    for slug in (items or []):
        it = ITEMS.get(slug) or {}
        stats = ", ".join(f"{k} {v.get('value')}" for k, v in (it.get("stats") or {}).items())
        passives = " | ".join(it.get("passives") or [])[:300]
        row = reasons_by.get(slug) or {}
        partners = [ITEMS.get(p, {}).get("name", p) for p in (row.get("synergyWith") or [])]
        line = f"- {it.get('name', slug)} (cost {it.get('cost')}; {stats or 'no stats'}"
        if passives:
            line += f"; {passives}"
        line += ")"
        if row.get("reason"):
            line += f" -- your reason: {str(row['reason'])[:300]}"
        if partners:
            line += f" -- synergy with {', '.join(partners)}"
        item_lines.append(line)
    rune_lines = []
    rr = rune_reasons or {}
    if rr.get("keystone"):
        rune_lines.append(f"- keystone: {str(rr['keystone'])[:300]}")
    for m in (rr.get("minors") or [])[:4]:
        rune_lines.append(f"- minor: {str(m)[:200]}")
    if rr.get("flex"):
        rune_lines.append(f"- flex: {str(rr['flex'])[:200]}")
    boots_line = f"Boots: {boots_name}" + (f" -- your reason: {boots_reason[:300]}" if boots_reason else "")
    scored_line = ""
    if isinstance(candidate_score, dict) and candidate_score.get("reason"):
        scored_line = (f"You already scored this item {candidate_score.get('score')}/100 when "
                       f"building: {str(candidate_score['reason'])[:300]}\n")
    cand_stats = ", ".join(
        f"{k} {v.get('value')}" for k, v in (cand.get("stats") or {}).items())
    cand_passives = " | ".join(cand.get("passives") or [])[:600]

    # The build's own conditional recommendations. The queried item being in
    # here is the single most important fact about it, so it is established
    # before the model is asked to judge anything.
    def _name(slug: str) -> str:
        return ITEMS.get(slug, {}).get("name", slug) if slug else ""

    swap_lines: list[str] = []
    candidate_swap: dict | None = None
    for row in (situational or []):
        if not isinstance(row, dict):
            continue
        slug = str(row.get("item") or "").strip()
        if not slug:
            continue
        when = " ".join(str(row.get("when") or "").split())[:160]
        replaces = str(row.get("replaces") or "").strip()
        swap_lines.append(
            f"- {_name(slug)} comes in for {_name(replaces) or 'a core item'}"
            + (f" when {when}" if when else ""))
        if slug == candidate:
            candidate_swap = {"replaces": _name(replaces), "when": when}
    for row in (situational_boots or []):
        if not isinstance(row, dict):
            continue
        slug = str(row.get("boots") or "").strip()
        if not slug:
            continue
        when = " ".join(str(row.get("when") or "").split())[:160]
        swap_lines.append(f"- {_name(slug)} as alternative boots"
                          + (f" when {when}" if when else ""))
        if slug == candidate:
            candidate_swap = {"replaces": boots_name, "when": when}

    if candidate_swap:
        swap_block = (
            "THIS BUILD ALREADY RECOMMENDS THE QUERIED ITEM as a situational swap"
            + (f", in place of {candidate_swap['replaces']}" if candidate_swap["replaces"] else "")
            + (f", for when {candidate_swap['when']}" if candidate_swap["when"] else "")
            + ".\nSo the verdict is SITUATIONAL and the answer must explain three "
              "things: why the default pick is preferred in a normal game, the "
              "specific conditions that make the queried item better, and which "
              "item it replaces. Do NOT argue that it is worse; the build already "
              "recommends it under those conditions.\n\n")
    elif swap_lines:
        swap_block = ("SITUATIONAL SWAPS this build already lists (the queried item is "
                      "NOT among them):\n" + "\n".join(swap_lines) + "\n\n")
    else:
        swap_block = "This build lists no situational swaps.\n\n"
    bias_line = ("" if build_bias == "balanced"
                 else "The build was generated with a "
                      + build_bias.replace("_", " ") + " bias.\n")

    prompt = (
        f"You are the build engine that produced a Wild Rift build for {champion} "
        f"(playstyle: {playstyle}). A player asks why one item was not chosen.\n\n"
        + (brief_block + "\n\n" if brief_block else "")
        + (f"KIT FACTS for {champion}, authoritative -- if your own recollection "
           f"disagrees, these win: {kit_facts}\n\n" if kit_facts else "")
        + "THE BUILD YOU PRODUCED, in purchase order, with your own reasons:\n"
        + ("\n".join(item_lines) if item_lines else f"- {', '.join(build_names)}") + "\n"
        + boots_line + "\n"
        + f"Runes: {', '.join(rune_names or []) or 'unknown'}.\n"
        + ("\n".join(rune_lines) + "\n" if rune_lines else "")
        + bias_line +
        f"\nTHE ITEM IN QUESTION: {cand.get('name', candidate)} "
        f"(cost {cand.get('cost')}, stats: {cand_stats or 'none'}; "
        f"passives: {cand_passives or 'none'}).\n"
        + scored_line + "\n"
        + swap_block +
        "Answer as the engine defending a judgement call, not a marketing voice. "
        "2 to 4 sentences, concrete: name the item in the build it competes with "
        "and the actual trade (damage type, spike timing, durability, synergy, "
        "cost curve). If the candidate is genuinely fine here, say so plainly.\n"
        "Reason ONLY from the champion facts, stats, passives, your own stated "
        "reasons, the enemies and the conditions given above, and stay consistent "
        "with the reasons you already gave for the build. Do not invent stats, "
        "ratios or interactions, and do not assert anything this prompt has not "
        "told you.\n\n"
        'Return ONLY a JSON object: {"verdict": one of '
        '"viable_alternative" | "situational" | "worse_here" | "not_viable", '
        '"answer": string, "competesWith": item name from the build or null}'
    )
    data = _call(key, prompt)
    verdict = str(data.get("verdict") or "").strip()
    if verdict not in ("viable_alternative", "situational", "worse_here", "not_viable"):
        verdict = "worse_here"
    # An item the build itself recommends conditionally cannot be "worse here",
    # whatever the model decided. Asking was not enough: the instruction lives
    # in the prompt, the guarantee lives here.
    if candidate_swap:
        verdict = "situational"
    answer = " ".join(str(data.get("answer") or "").split())[:700]
    if not answer:
        return {"error": "the model returned no answer; ask again"}
    competes = str(data.get("competesWith") or "").strip() or None
    return {"verdict": verdict, "answer": answer, "competesWith": competes,
            "candidate": candidate, "candidateName": cand.get("name", candidate)}



RUNES_ONLY_SCHEMA = (
    'Return ONLY this JSON, no prose around it: '
    '{"runes":{"keystone":"<name>","primaryTree":"<tree>",'
    '"minors":["<name>","<name>","<name>"],"flex":"<name>"},'
    '"runeReasons":{"<rune name>":"<=14 words why, against THIS comp"},'
    '"summoners":["<name>","<name>"]}'
)


def advise_runes(champion: str, role: str, enemies: list[str],
                 allies: list[str] | None = None, playstyle: str = "standard",
                 objective: str = "balanced", mode: str = "counter",
                 champion_form: str = "", locked_runes: list[str] | None = None,
                 on_progress=None) -> dict:
    """The rune page and the summoner spells, and nothing else.

    WHY THIS EXISTS, separately from advise().

    Runes and summoners are the only part of a build with a DEADLINE. They are
    chosen in champion select and cannot be changed once the game starts, while
    items are bought over the following twenty minutes. A full build takes
    fifteen to thirty seconds, which is most of a draft, so the player was
    waiting on item advice they could not use yet to get rune advice they had
    minutes to enter.

    Splitting it helps for two reasons rather than one. The obvious one is
    output length: a rune page is a fraction of five items with reasons, boots,
    situational swaps and a counter summary. The larger one is that full
    REGENERATIONS dominate this function's latency -- the item validator has
    many ways to reject a build, and each rejection can cost another whole
    call. A rune page answers to one narrow validator, so it far more often
    passes first time.

    The follow-up item call should be given these runes as locks, so the items
    are chosen to fit the page the player has already entered rather than a
    different one the second call invented.
    """
    emit = on_progress or (lambda _event: None)
    if not (role or "").strip():
        role = (CHAMPS.get(champion) or {}).get("role") or ""
    champion_record = CHAMPS.get(champion) or {}
    if not champion_record:
        raise SystemExit(f"unknown champion: {champion}")
    enemies = [e for e in (enemies or []) if e]
    enemies_known = bool(enemies)
    allies = [a for a in (allies or []) if a]
    key = _api_key()

    combat = (champion_record.get("combat") or {})
    abilities_text = " ".join((a.get("text") or "")
                              for a in (champion_record.get("abilities") or []))

    prompt = "\n\n".join(x for x in [
        "You are picking the RUNE PAGE and the SUMMONER SPELLS for one player, "
        "right now, in champion select. They cannot be changed after the game "
        "starts, so this answer is needed in seconds, not after a full build.",
        f"CHAMPION: {champion}" + (f" ({role})" if role else ""),
        f"PLAYSTYLE: {playstyle}" if playstyle and playstyle != "standard" else "",
        f"OPTIMIZE FOR: {objective}" if objective and objective != "balanced" else "",
        kayn_form_block(champion_form, playstyle),
        _meta_block(champion),
        # The full threat picture, minus the item suggestions: this call is not
        # choosing items, and naming them would invite it to.
        prompt_mod.enemy_threat_block(enemies, champion, WRMETA, role)
        if enemies_known else _enemy_block(enemies, champion),
        prompt_mod.identity_threat_lines(enemies) if enemies_known else "",
        (f"ALLY TEAM: {', '.join(allies)}" if allies else ""),
        ("THE RUNE PAGE IS THE COUNTER, not a default carried over: pick the "
         "keystone and every minor against THIS comp -- a comp of shields and "
         "disengage, one of hard engage, and one of sustained frontline each "
         "want a different page on the same champion. If the champion's usual "
         "page IS the right answer here, say why in its reasons."
         if enemies_known else ""),
        _summoner_block(role, enemies_known,
                        immobile=not summoners.has_mobility(champion, abilities_text)),
        _lock_block([], "", [r for r in (locked_runes or []) if r]),
        runemeta.pool_text_block(role),
        "Keep every reason under fourteen words. No prose outside the JSON.",
        RUNES_ONLY_SCHEMA,
    ] if x)

    emit({"stage": "model", "chars": 0})
    request_model = model_for_request(playstyle, champion)

    def call(text: str) -> dict:
        kwargs = {}
        if on_progress:
            kwargs["on_progress"] = on_progress
        if request_model != MODEL:
            kwargs["model"] = request_model
        return _call(key, text, **kwargs)

    res = call(prompt)
    emit({"stage": "validating"})

    page = res.get("runes") if isinstance(res, dict) else None
    errors = runemeta.page_errors(page if isinstance(page, dict) else {})
    if errors:
        # One targeted repair, never a full regeneration: there is nothing else
        # in this answer worth throwing away to fix a rune page.
        for message in errors:
            print(f"[advisor] runes-only invalid: {message}", file=sys.stderr)
        emit({"stage": "repairing", "section": "runes"})
        fixed = call(prompt + "\n\nYour previous rune page had ERRORS. Return the "
                     "corrected JSON only:\n- " + "\n- ".join(errors))
        if isinstance(fixed, dict) and isinstance(fixed.get("runes"), dict):
            if not runemeta.page_errors(fixed["runes"]):
                res = fixed
                page = fixed["runes"]
                errors = []

    if not isinstance(page, dict) or errors:
        return {"error": "could not produce a legal rune page",
                "details": errors[:4]}

    picks = [p for p in (res.get("summoners") or []) if isinstance(p, str)]
    legal = summoners.enforce(picks, role, enemies_known)
    if legal is None:
        legal, _why = summoners.summoners_for(
            champion, role, champion_record.get("class", ""))

    return {
        "runes": page,
        "runeReasons": res.get("runeReasons") or {},
        "summoners": summoners.icons_for(legal),
        "partial": "runes",
    }

def advise_best_of(champion: str, role: str, enemies: list[str],
                   runs: int = 3, on_progress=None, **kwargs) -> dict:
    """Sample `advise` `runs` times and return the sample the others agree with.

    The result is one COMPLETE build that the model actually authored, not a
    per-slot majority spliced together. A spliced build is one no run proposed:
    its item reasons argue for items that are no longer in it, its purchase
    order has gaps, its situational swaps replace items that were voted out,
    and its `synergyWith` pairs point at absent partners. It would also arrive
    unvalidated, because every check that passed did so against a build this is
    not.

    Picking the most-agreed COMPLETE run keeps all of that coherent and still
    gets what the vote is for. An element in every sample is in the winner by
    construction -- the winner is one of the samples -- and an element only one
    sample wanted can only survive if the rest of that sample carried it there.

    Failed runs are dropped rather than fatal: two samples still vote, and one
    surviving sample is exactly what a single-run generation would have given.
    """
    # Bias requests benefit more from measured disagreement than popularity
    # voting. Generate every hypothesis in one completion, run the engine, then
    # let a second completion judge the disclosed dimensions. This also replaces
    # three full authoring calls with two purposeful calls.
    #
    # Every bias on the damage/durability axis routes here, not only maximum
    # damage: the objective is blended by TOURNAMENT_BLEND, so a durability
    # request is measured on staying alive and delivering rather than being
    # handed to a damage optimizer and hoping the prose carried it.
    if kwargs.get("build_bias") in TOURNAMENT_BIASES:
        return advise(champion, role, enemies, on_progress=on_progress,
                      engine_tournament=True, **kwargs)

    if runs <= 1:
        return advise(champion, role, enemies, on_progress=on_progress, **kwargs)

    results: list[dict] = []
    errors: list[BaseException] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=runs) as pool:
        # Progress is reported by the first sample only. All of them move
        # through the same stages at roughly the same pace, and interleaving
        # three streams would make the bar jump backwards.
        futures = [pool.submit(advise, champion, role, enemies,
                               on_progress=on_progress if i == 0 else None, **kwargs)
                   for i in range(runs)]
        for future in futures:
            try:
                res = future.result()
            except Exception as exc:                    # noqa: BLE001
                print(f"[advisor] consensus sample failed: {type(exc).__name__}: {exc}",
                      file=sys.stderr)
                errors.append(exc)
                continue
            # A rejected REQUEST (unsupported playstyle, unknown damage path) is
            # not a bad sample, it is a bad request, and every sample will say
            # the same thing. Hand it straight back.
            if res.get("error"):
                return res
            results.append(res)

    if not results:
        raise errors[0]
    if len(results) == 1:
        print("[advisor] consensus: only one sample survived; returning it unvoted",
              file=sys.stderr)
        return results[0]

    votes = {kind: Counter() for kind in ("items", "boots", "runes")}
    for res in results:
        for kind, values in _build_elements(res).items():
            votes[kind].update(set(values))

    def agreement(res: dict) -> tuple[int, int, int]:
        elements = _build_elements(res)
        score = sum(votes[kind][value] for kind, values in elements.items() for value in values)
        ladder = (res.get("ladderAgreement") or {}).get("matched") or 0
        return score, ladder, -len(res.get("validationWarnings") or [])

    winner = max(results, key=agreement)
    elements = _build_elements(winner)
    total = sum(len(v) for v in elements.values())
    unanimous = sum(1 for kind, values in elements.items()
                    for value in values if votes[kind][value] == len(results))

    # What the samples disagreed about, so a bad build can be read afterwards as
    # "the model was guessing here" rather than just "the model chose this".
    winner["consensus"] = {
        "runs": len(results),
        "requested": runs,
        "unanimous": unanimous,
        "of": total,
        "votes": {kind: dict(counter.most_common()) for kind, counter in votes.items()},
    }
    contested = [f"{value} ({votes[kind][value]}/{len(results)})"
                 for kind, values in elements.items()
                 for value in values if votes[kind][value] < len(results)]
    print(f"[advisor] consensus over {len(results)} samples: {unanimous}/{total} unanimous"
          + (f"; contested: {', '.join(contested)}" if contested else ""), file=sys.stderr)
    return winner


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--champion", required=True)
    ap.add_argument("--role", default="")
    ap.add_argument("--enemies", default="")
    ap.add_argument("--allies", default="")
    ap.add_argument("--playstyle", default="standard")
    ap.add_argument("--objective", default="balanced")
    ap.add_argument("--game-phase", choices=tuple(GAME_PHASES), default="balanced")
    ap.add_argument("--damage-path", choices=tuple(DAMAGE_PATHS), default="standard")
    ap.add_argument("--champion-form", default="")
    ap.add_argument("--ahead-enemy", default="")
    ap.add_argument("--mode", choices=("studio", "counter"), default="studio")
    ap.add_argument("--risk-tolerance", choices=tuple(RISK_TOLERANCE), default="medium")
    ap.add_argument("--build-bias", choices=tuple(BUILD_BIAS), default="balanced")
    ap.add_argument("--why-not", default="", help="JSON {items,boots,runes,candidate,playstyle,buildBias}: answer why the candidate is absent instead of generating")
    ap.add_argument("--skill-level", choices=tuple(SKILL_LEVEL), default="average")
    ap.add_argument("--locked-items", default="", help="comma-separated item slugs to pin")
    ap.add_argument("--locked-runes", default="", help="comma-separated rune names to pin")
    ap.add_argument("--runs", type=int, default=1,
                    help="sample the model this many times and return the build the "
                         "samples agree on (default 1: one sample, no vote)")
    args = ap.parse_args()
    if args.why_not:
        payload = json.loads(args.why_not)
        out = why_not(args.champion,
                      payload.get("items") or [], payload.get("boots") or "",
                      payload.get("runes") or [], payload.get("candidate") or "",
                      playstyle=payload.get("playstyle") or "standard",
                      build_bias=payload.get("buildBias") or "balanced",
                      situational=payload.get("situational") or [],
                      situational_boots=payload.get("situationalBoots") or [])
        print(json.dumps(out, ensure_ascii=False))
        return
    res = advise_best_of(args.champion, args.role,
                 [e.strip() for e in args.enemies.split(",") if e.strip()],
                 runs=max(1, args.runs),
                 allies=[a.strip() for a in args.allies.split(",") if a.strip()],
                 playstyle=args.playstyle, objective=args.objective, mode=args.mode,
                 risk_tolerance=args.risk_tolerance, skill_level=args.skill_level,
                 build_bias=args.build_bias,
                 game_phase=args.game_phase, damage_path=args.damage_path,
                 champion_form=args.champion_form, ahead_enemy=args.ahead_enemy,
                 locked_items=[s.strip() for s in args.locked_items.split(",") if s.strip()],
                 locked_runes=[s.strip() for s in args.locked_runes.split(",") if s.strip()])
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
