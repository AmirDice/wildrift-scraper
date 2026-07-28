"""LLM-first build advisor: orchestration only.

The pivot (2026-07-17): the rule-based simulation engine is not reliable enough
for production. The LLM is the sole build-selection and scoring authority; our
structured champion, item and rune data is its factual knowledge. Nothing in
this pipeline simulates combat.

    user: champion + role + enemy team (+ ally team)
      -> DERIVE how this champion fights          web/advisor/profiles.py
      -> FILTER only impossible items away        web/advisor/itemmeta.py
      -> ASSEMBLE one prompt from our data        web/advisor/prompt.py
      -> DeepSeek thinking mode, JSON only
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
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

from web.advisor import env as advisor_env
from web.advisor import itemmeta, profiles, repair, runemeta, summoners
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
# of the repair rounds. The default stays DeepSeek until that is deployed with
# a key that has quota; locally, put ADVISOR_MODEL and GEMINI_API_KEY in
# web-next/.env.local and the dev server passes both through to this process.
MODEL = os.environ.get("ADVISOR_MODEL", "deepseek-v4-flash").strip() or "deepseek-v4-flash"
IS_GEMINI = MODEL.lower().startswith("gemini")
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

PLAYSTYLE_CONFIG = json.loads(PLAYSTYLE_CONFIG_PATH.read_text(encoding="utf-8"))
PLAYSTYLES_BY_CLASS: dict[str, list[str]] = PLAYSTYLE_CONFIG["byClass"]
PLAYSTYLE_OVERRIDES: dict[str, list[str]] = PLAYSTYLE_CONFIG["overrides"]


def available_playstyles(champion: str) -> list[str]:
    if champion in PLAYSTYLE_OVERRIDES:
        return PLAYSTYLE_OVERRIDES[champion]
    champ = CHAMPS.get(champion) or {}
    styles = list(PLAYSTYLES_BY_CLASS.get(champ.get("class", ""), ["standard", "damage"]))
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


def _summoner_block(role: str) -> str:
    rows = "\n".join(f"- {name}: {meta['desc']}" for name, meta in SUMMONERS.items())
    rule = ("This is a JUNGLER: Smite is MANDATORY; Flash is the default partner (Ghost only for "
            "run-down fighters like Hecarim). Never Ignite just because the build is damage."
            if role == "Jungle" else
            "Non-jungler: never take Smite. Flash is the default; the second is a matchup call "
            "(Ignite for kill-lane assassins, Heal/Barrier for marksmen, Exhaust/Cleanse situationally).")
    return "SUMMONER SPELLS (choose exactly 2 distinct):\n" + rows + "\n" + rule


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


def _gemini_call(prompt: str) -> dict:
    """The same contract as the DeepSeek path: prompt in, parsed build out.

    Kept deliberately thin. Everything that decides the build -- the prompt, the
    validator, the repair loop -- is shared, so switching providers changes the
    author and nothing else, which is what made the comparison meaningful.
    """
    from google import genai
    from google.genai import types

    api_key = (os.environ.get("GEMINI_API_KEY")
               or os.environ.get("GOOGLE_API_KEY") or "")
    if not api_key:
        raise SystemExit("GEMINI_API_KEY is not set, but ADVISOR_MODEL asks for "
                         f"{MODEL}. Put it in web-next/.env.local.")
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
            r = client.models.generate_content(model=MODEL, contents=prompt, config=config)
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


def _call(key: str, prompt: str, on_progress=None) -> dict:
    if IS_GEMINI:
        return _gemini_call(prompt)
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
    "maxstats": "OPTIMIZE FOR STAT EFFICIENCY: favor the items whose raw stats this kit "
                "uses most per gold; prefer stat-dense items over flashy actives when the "
                "value is close.",
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

KAYN_FORMS = {
    "shadow-assassin": (
        "KAYN FORM -- SHADOW ASSASSIN (blue): optimize the actual transformed kit. "
        "He is a burst assassin for ranged/squishy targets: his passive adds magic damage "
        "during the opening combat window, Blade's Reach can be cast while moving, Shadow "
        "Step has stronger roaming, and Umbral Trespass refreshes his passive. Favor fast "
        "physical burst, penetration, mobility and short target access."
    ),
    "rhaast": (
        "KAYN FORM -- RHAAST / DARKIN SLAYER (red): this OVERRIDES Shadow Assassin-specific "
        "lines in the supplied base record. Rhaast heals for 24-38% of physical damage dealt "
        "to champions. Reaping Slash hits twice and each hit adds target max-Health physical "
        "damage. Blade's Reach knocks up for 1 second. Shadow Step has less movement speed and "
        "no Shadow Assassin slow immunity. Umbral Trespass deals target max-Health physical "
        "damage and heals from the target's max Health. Favor bruiser durability, ability "
        "haste, sustained physical damage and healing; do not build him as blue Kayn."
    ),
}

RISK_TOLERANCE = {
    "low": "RISK TOLERANCE LOW: favour reliable activation and safer completion curves, "
           "avoid highly conditional items, keep a defensive margin.",
    "medium": "",  # the default optimisation, no extra bias
    "high": "RISK TOLERANCE HIGH: a glassier or more execution-heavy build is acceptable if "
            "it raises the ceiling -- but still reject mechanically incoherent items, and do "
            "not confuse risk tolerance with off-meta randomness.",
}


def advise(champion: str, role: str, enemies: list[str],
           allies: list[str] | None = None, playstyle: str = "standard",
           objective: str = "balanced", mode: str = "studio",
           game_phase: str = "balanced", damage_path: str = "standard",
           champion_form: str = "", ahead_enemy: str = "",
           risk_tolerance: str = "medium",
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
    # no 'sustained_damage' id -- 'dps' is that build). Unknown ids fall through
    # to the credibility check below.
    playstyle = {"sustain": "dps", "sustained_damage": "dps",
                 "glass_cannon": "oneshot"}.get(playstyle, playstyle)
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
    key = _api_key()
    if not key:
        raise SystemExit(
            "DEEPSEEK_API_KEY is not set. Either export it in this shell, or put it in "
            f"{ENV_FILE.relative_to(ROOT)} (where the web app already reads it from).")
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
    if mode == "studio":
        enemies = []
    enemies_known = bool(enemies)

    # Derive how this champion actually fights before anything else: the item
    # audit, the pre-filter and the boots policy all key off it.
    champion_record = CHAMPS.get(champion) or {}
    derived = profiles.profile(champion)
    combat = derived["combatProfile"]
    scaling = derived.get("scalingProfile", {})
    kit_linked_items = itemmeta.mandatory_audit(combat, scaling)
    pool_slugs, withheld = itemmeta.filter_candidates(
        champion_record, combat, scaling,
        damage_path=damage_path, enemies_known=enemies_known)
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
    prompt = "\n\n".join(x for x in [
        prompt_mod.champion_block(champion, CHAMPS, ARCHETYPES, WRMETA, derived),
        f"ROLE: {role}",
        f"PLAYSTYLE (build toward this): {style}",
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
        GAME_PHASES[game_phase],
        DAMAGE_PATHS[damage_path],
        KAYN_FORMS.get(champion_form, ""),
        # Counter mode gets the structured, weighted threat picture; other modes
        # get the plain enemy line (usually "unknown" in studio).
        prompt_mod.enemy_threat_block(enemies, champion, WRMETA) if enemies_known
        else _enemy_block(enemies or [], champion),
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
         "situationalRunes as empty lists. SKIP the full build evaluation: a counter build "
         "is wanted fast, so return buildScore as null and do not spend time scoring the "
         "eight categories. INSTEAD return a compact counterSummary that names the 2-4 "
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
        prompt_mod.boots_block(champion_record.get("class", ""), enemies_known),
        runemeta.pool_text_block(),
        prompt_mod.item_pool_block(pool_slugs),
        prompt_mod.filtered_note(withheld),
    ] if x)

    champion_class = champion_record.get("class", "")
    emit({"stage": "model", "chars": 0})

    def call(text: str) -> dict:
        # Only pass the callback when there is one, so the signature every
        # existing caller and test stub sees is unchanged.
        return _call(key, text, on_progress=on_progress) if on_progress else _call(key, text)

    res = call(prompt)
    emit({"stage": "validating"})

    def _check(build: dict):
        return validate_mod.validate(
            build, champion_class=champion_class, role=role, mode=mode,
            enemies_known=enemies_known, required_audit_items=kit_linked_items,
            allowed_items=pool_slugs, item_locks=item_locks, boot_lock=locked_boot,
            rune_locks=locked_runes, resolve_item=_resolve_item,
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

    # Summoners are assigned, not generated: the choice is a lookup, and asking
    # the model for it only created a way for an otherwise good build to fail.
    res["summoners"], summoner_reason = summoners.resolved(
        champion, role, champion_class)
    res["summonerReason"] = summoner_reason

    # Normalised request metadata, so the frontend can show what the build was
    # optimised for and flag any playstyle the champion could not honour. Added
    # additively under a bumped schema version; old consumers ignore it.
    res["schemaVersion"] = 2
    res["requestMeta"] = {
        "mode": mode,
        "requestedPlaystyle": playstyle,
        "resolvedPlaystyle": playstyle,   # a hard-invalid style errors earlier
        "playstyleAdjustment": None,
        "powerCurve": game_phase,
        "optimizationGoal": objective,
        "riskTolerance": risk_tolerance,
        "enemyContext": "known" if enemies_known else "unknown",
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
          f"risk={risk_tolerance} enemyContext={'known' if enemies_known else 'unknown'} "
          f"candidates={len(pool_slugs)} errors={len(report.flat())} "
          f"warnings={len(report.warnings)} schemaVersion=2", file=sys.stderr)
    return res


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
    ap.add_argument("--locked-items", default="", help="comma-separated item slugs to pin")
    ap.add_argument("--locked-runes", default="", help="comma-separated rune names to pin")
    args = ap.parse_args()
    res = advise(args.champion, args.role,
                 [e.strip() for e in args.enemies.split(",") if e.strip()],
                 [a.strip() for a in args.allies.split(",") if a.strip()],
                 playstyle=args.playstyle, objective=args.objective, mode=args.mode,
                 risk_tolerance=args.risk_tolerance,
                 game_phase=args.game_phase, damage_path=args.damage_path,
                 champion_form=args.champion_form, ahead_enemy=args.ahead_enemy,
                 locked_items=[s.strip() for s in args.locked_items.split(",") if s.strip()],
                 locked_runes=[s.strip() for s in args.locked_runes.split(",") if s.strip()])
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
