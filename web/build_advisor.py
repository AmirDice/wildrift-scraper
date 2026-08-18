"""LLM-first build advisor: orchestration only.

The pivot (2026-07-17): the rule-based simulation engine is not reliable enough
for production. The LLM is the sole build-selection and scoring authority; our
structured champion, item and rune data is its factual knowledge. Nothing in
this pipeline simulates combat.

    user: champion + role + enemy team (+ ally team)
      -> DERIVE how this champion fights          web/advisor/profiles.py
      -> FILTER only impossible items away        web/advisor/itemmeta.py
      -> ASSEMBLE one prompt from our data        web/advisor/prompt.py
      -> the model (gemini-3.6-flash by default), JSON only
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
DEFAULT_MODEL = "gemini-3.6-flash"
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


def available_playstyles(champion: str) -> list[str]:
    if champion in PLAYSTYLE_OVERRIDES:
        return PLAYSTYLE_OVERRIDES[champion]
    champ = CHAMPS.get(champion) or {}
    styles = list(PLAYSTYLES_BY_CLASS.get(champ.get("class", ""), ["standard", "oneshot"]))
    if champ.get("role") == "Support" and "utility" not in styles:
        styles.append("utility")
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


def advise(champion: str, role: str, enemies: list[str],
           allies: list[str] | None = None, playstyle: str = "standard",
           objective: str = "balanced", mode: str = "studio",
           game_phase: str = "balanced", damage_path: str = "standard",
           champion_form: str = "", ahead_enemy: str = "",
           risk_tolerance: str = "medium", skill_level: str = "average",
           build_bias: str = "balanced",
           locked_items: list[str] | None = None,
           locked_runes: list[str] | None = None,
           on_progress=None) -> dict:
    # on_progress(event) is called with {"stage": ...} as the generation moves.
    # It is optional and side-effect free: nothing about the build depends on
    # whether anyone is listening.
    emit = on_progress or (lambda _event: None)
    mode = "counter" if mode == "counter" else "studio"
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
        prompt_mod.meta_identity_block(identity_key),
        prompt_mod.ladder_consensus_block(identity_key),
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
        prompt_mod.enemy_threat_block(enemies, champion, WRMETA, role) if enemies_known
        else _enemy_block(enemies or [], champion),
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
         "eight categories. SKIP the per-pick explanations for the same reason: "
         "candidateItemScores rows carry `item` and `score` ONLY -- no `reason` and no "
         "`synergyWith` -- and omit runeReasons and bootsReason entirely, returning "
         "situationalBoots as an empty list. The counterSummary is where the reasoning "
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
        prompt_mod.item_pool_block(pool_slugs),
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
            # core item; this is the teeth behind that prose. Studio only:
            # counter mode trades scoring depth for speed on purpose.
            ladder_core=(prompt_mod.ladder_core_slugs(identity_key)
                         if mode != "counter" else None),
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
            patch = call(repair.repair_prompt(section, res, errors, pool_slugs))
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
    # Counter mode does not display per-pick reasoning (the counterSummary
    # carries it), so drop anything the model returned anyway rather than
    # caching and shipping text nothing renders.
    if mode == "counter":
        res["situationalBoots"] = []
        for _row in res.get("candidateItemScores") or []:
            if isinstance(_row, dict):
                _row.pop("reason", None)
                _row.pop("synergyWith", None)

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

    # Normalised request metadata, so the frontend can show what the build was
    # optimised for and flag any playstyle the champion could not honour. Added
    # additively under a bumped schema version; old consumers ignore it.
    # How much of the final build the champion's top-50 ladder players also
    # equip -- surfaced to the UI as a credibility badge. None when this
    # champion has no fresh capture yet.
    res["ladderAgreement"] = prompt_mod.ladder_agreement(
        identity_key, [s for s in (res.get("items") or []) if s])

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
            playstyle: str = "standard", build_bias: str = "balanced") -> dict:
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
    # The champion's kit facts, from the same store the full generation reads.
    # Without them this small call had NOTHING but the champion's name, so the
    # model answered from its own priors -- which is how a live answer once
    # described a mana champion as energy-based. Facts beat priors, stated so.
    try:
        kit_facts = " ".join(profiles.kit_mechanics(champion))
    except Exception:
        kit_facts = ""
    cand_stats = ", ".join(
        f"{k} {v.get('value')}" for k, v in (cand.get("stats") or {}).items())
    cand_passives = " | ".join(cand.get("passives") or [])[:600]
    bias_line = ("" if build_bias == "balanced"
                 else "The build was generated with a "
                      + build_bias.replace("_", " ") + " bias.\n")

    prompt = (
        f"You are the build engine that produced a Wild Rift build for {champion} "
        f"(playstyle: {playstyle}). A player asks why one item was not chosen.\n\n"
        + (f"KIT FACTS for {champion}, authoritative -- if your own recollection "
           f"disagrees, these win: {kit_facts}\n\n" if kit_facts else "")
        + f"THE BUILD: {', '.join(build_names)} with boots {boots_name}. "
        f"Runes: {', '.join(rune_names or []) or 'unknown'}.\n"
        + bias_line +
        f"\nTHE ITEM IN QUESTION: {cand.get('name', candidate)} "
        f"(cost {cand.get('cost')}, stats: {cand_stats or 'none'}; "
        f"passives: {cand_passives or 'none'}).\n\n"
        "Answer as the engine defending a judgement call, not a marketing voice. "
        "2 to 4 sentences, concrete: name the item in the build it competes with "
        "and the actual trade (damage type, spike timing, durability, synergy, "
        "cost curve). If the candidate is genuinely fine here, say so plainly.\n\n"
        'Return ONLY a JSON object: {"verdict": one of '
        '"viable_alternative" | "situational" | "worse_here" | "not_viable", '
        '"answer": string, "competesWith": item name from the build or null}'
    )
    data = _call(key, prompt)
    verdict = str(data.get("verdict") or "").strip()
    if verdict not in ("viable_alternative", "situational", "worse_here", "not_viable"):
        verdict = "worse_here"
    answer = " ".join(str(data.get("answer") or "").split())[:700]
    if not answer:
        return {"error": "the model returned no answer; ask again"}
    competes = str(data.get("competesWith") or "").strip() or None
    return {"verdict": verdict, "answer": answer, "competesWith": competes,
            "candidate": candidate, "candidateName": cand.get("name", candidate)}


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
                      build_bias=payload.get("buildBias") or "balanced")
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
