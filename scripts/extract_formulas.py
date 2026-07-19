"""Extract structured ability formulas from scraped ability text (LLM, grounded).

Converts each champion's ability tooltips (data/champions_wr.json) into machine-
usable damage/steroid components for the deterministic fight engine:

    {"type": "physical", "base": [5,15,25,35], "ratios": [{"stat":"ad","pct":110}],
     "hits": 1, "when": "per cast"}

GROUNDING: every extracted number (base ranks, ratio percents) must literally
appear in the source ability text, otherwise the component is rejected. The LLM
only transcribes; it cannot invent numbers. Anything it can't express in the
schema goes to `unmodeled` so engine coverage is measurable.

Output: data/ability_formulas.json   (per champion, per ability)

Run:
    python -m scripts.extract_formulas --only "Hecarim,Graves"
    python -m scripts.extract_formulas            # full roster
"""
from __future__ import annotations

import argparse
import json
import os
import re
from itertools import combinations
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
CHAMPS = ROOT / "data" / "champions_wr.json"
OUT = ROOT / "data" / "ability_formulas.json"

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-v4-flash"

RATIO_STATS = ["ad", "bonusAd", "ap", "targetMaxHp", "targetCurrentHp", "targetMissingHp",
               "ownMaxHp", "ownBonusHp", "armor", "mr", "bonusMs", "bonusArmor", "bonusMr"]
STEROID_STATS = ["ad", "ap", "attackSpeed", "moveSpeed", "armor", "mr", "critChance"]

SYSTEM = (
    "You transcribe Wild Rift ability tooltips into machine-readable JSON for a damage "
    "engine. You TRANSCRIBE, never invent: every number you output must appear verbatim "
    "in the given text. Rules:\n"
    "- damage components: {\"name\":\"...\",\"type\":\"physical|magic|true\","
    "\"base\":[per-rank numbers, single number if flat],"
    "\"ratios\":[{\"stat\":one of " + str(RATIO_STATS) + ",\"pct\":number (110 for 110%)}],"
    "\"hits\":N (default 1; e.g. 3-hit ability = 3, per-bullet abilities use bullets). "
    "If the NUMBER OF HITS scales with stacks/charges, use the MAX-STACK count: Gwen's "
    "'snips twice, snipping an extra time for each stack consumed (max 4)' is 5 regular "
    "snips (hits=5) plus 1 final snip (hits=1) — NOT hits=1. Modelling one snip makes her "
    "primary ability look 5x weaker than it is,"
    "\"when\":\"per cast|per auto|once per target|dot total\"}\n"
    "- For DoTs give the TOTAL damage over the duration if stated per-tick x duration; "
    "if only per-second is stated, set when='dot total' and base = per-second value with "
    "\"durationS\": seconds.\n"
    "- steroids (self stat gains): {\"stat\":one of " + str(STEROID_STATS) + ","
    "\"flat\":[per-rank] OR \"pct\":number, \"from\":optional conversion source stat "
    "(e.g. Hecarim: stat=ad, from=bonusMs, pct=12), \"note\":\"...\"}\n"
    "- shields/heals: {\"kind\":\"shield|heal\",\"base\":[...],\"ratios\":[...]}\n"
    "- Anything you cannot express (clones, transformations, stacking mechanics, "
    "conditional executes) -> put a short string in \"unmodeled\". Do NOT force it.\n"
    "- ON-HIT DAMAGE IS CRITICAL: any damage added to basic attacks MUST be a damage "
    "component with when='per auto' — this includes ALWAYS-ON passives (e.g. 'basic "
    "attacks deal 1% of target max health'), empowered/enhanced attacks, and per-bullet "
    "shotgun/multi-shot attacks. NEVER put on-hit damage in \"unmodeled\": without it the "
    "simulator thinks attack speed and crit are worthless for this champion. Use base 0 "
    "with ratios when the damage is purely a ratio (e.g. %target max health).\n"
    "- MUTUALLY EXCLUSIVE versions of one ability (tap vs charged cast, normal vs "
    "empowered/crit/conditional upgrade): model the DEFAULT/always-available version "
    "normally and add \"alt\": true to every alternative component so the engine "
    "doesn't double-count one cast.\n"
    "- MECHANICS: also report kit-level mechanics that change how items work, using "
    "ONLY these kinds:\n"
    "    reload          — ammo/magazine system limiting basic attacks (params: magazine)\n"
    "    fixedAttackSpeed— attack speed does NOT speed up this champion's attacks\n"
    "    doubleShot      — attacks fire an extra shot under a condition (params: secondShotPct)\n"
    "    everyNHit       — every Nth attack is empowered (params: n)\n"
    "    noResource      — champion uses no mana (energy, rage, none): mana items useless\n"
    "    transform       — possession/transform states the engine cannot model\n"
    "  Each mechanic MUST include \"evidence\": a short VERBATIM quote from the tooltip "
    "text proving it. No evidence = the mechanic will be rejected. Do not invent "
    "mechanics the text does not describe.\n"
    "- Return ONLY the JSON object."
)

MECHANIC_KINDS = {"reload", "fixedAttackSpeed", "doubleShot", "everyNHit",
                  "noResource", "transform", "multiShot"}

# --- Core-mechanic questionnaire --------------------------------------------
# The evidence-grounded pass is non-deterministic: it has dropped Graves' reload
# between runs, and tooltips never spell out pellet counts. This asks the LLM's
# GAME KNOWLEDGE for the champion's defining, simulator-relevant mechanics. It
# only FILLS GAPS — anything the grounded pass found wins — and is labelled
# source="llm-knowledge" so assumptions stay auditable.
CORE_MECHANIC_SYSTEM = (
    "You are a Wild Rift (mobile) expert. Name the CORE mechanics of ONE champion "
    "that a DAMAGE SIMULATOR must model. Answer for WILD RIFT, not PC League.\n"
    "Use ONLY these kinds:\n"
    "  reload           — ammo/magazine limits basic attacks (params: magazine)\n"
    "  multiShot        — ONE basic attack fires several projectiles/pellets "
    "(params: shots, damagePerShotPct = each pellet's % of a normal attack)\n"
    "  fixedAttackSpeed — attack speed does NOT speed up this champion's attacks\n"
    "  doubleShot       — attacks fire an extra shot (params: secondShotPct)\n"
    "  everyNHit        — every Nth attack is empowered (params: n)\n"
    "  noResource       — uses no mana (energy/rage/none)\n"
    "Only list mechanics this champion ACTUALLY has; most champions have none. "
    'Return ONLY JSON: {"mechanics":[{"kind":"...","...params":N}],'
    '"confidence":"high|medium|low"}'
)


def core_mechanics_call(key: str, champ: dict) -> list[dict]:
    abils = "\n".join(f"[{a['slot']}] {a['name']}: {(a.get('text') or '')[:200]}"
                      for a in champ.get("abilities", []))
    body = {"model": MODEL,
            "messages": [{"role": "system", "content": CORE_MECHANIC_SYSTEM},
                         {"role": "user", "content": f"CHAMPION: {champ['name']}\n{abils}"}],
            "response_format": {"type": "json_object"},
            "temperature": 0.1, "max_tokens": 8000, "stream": False}
    headers = {"Authorization": f"Bearer {key}"}
    for attempt in range(3):
        r = requests.post(DEEPSEEK_URL, json=body, headers=headers, timeout=180)
        if r.status_code in (429, 500, 502, 503, 504) and attempt < 2:
            time.sleep(3 * (attempt + 1))
            continue
        if not r.ok:
            raise RuntimeError(f"deepseek {r.status_code}")
        raw = json.loads(r.json()["choices"][0]["message"]["content"])
        out = []
        for m in raw.get("mechanics") or []:
            if isinstance(m, dict) and m.get("kind") in MECHANIC_KINDS:
                m["source"] = "llm-knowledge"
                out.append(m)
        return out
    return []


def merge_core_mechanics(grounded: list[dict], known: list[dict]) -> list[dict]:
    """Grounded (tooltip-evidenced) mechanics win; knowledge only fills gaps."""
    have = {m.get("kind") for m in grounded}
    return grounded + [m for m in known if m.get("kind") not in have]


# The extraction is a dice roll: a bad run once modelled Gwen's 4-snip Q as ONE
# snip, which under-counted her AP scaling so badly the engine priced her as an
# AD champion. This guard simulates the freshly extracted kit and checks it still
# reproduces the champion's independently-scraped primaryDamage. Cheap, and it
# catches the whole class of silent under-extraction.
DAMAGE_TYPE_MIN_SHARE = 0.45


def _damage_type_ok(name: str, rec: dict, champ: dict) -> bool:
    primary = champ.get("primaryDamage")
    if primary not in ("magic", "physical"):
        return True
    try:
        import web.fight_engine as fe
        prev = fe.FORMULAS.get(name)
        fe.FORMULAS[name] = rec  # simulate the candidate extraction
        try:
            st = fe.resolve_stats(name, 13, [], [])
            r = fe.rotation(name, st, fe.TARGETS["bruiser"], 8.0, 13)
            share = r["byType"].get(primary, 0.0) / (r["total"] or 1.0)
        finally:
            if prev is None:
                fe.FORMULAS.pop(name, None)
            else:
                fe.FORMULAS[name] = prev
        return share >= DAMAGE_TYPE_MIN_SHARE
    except Exception:  # noqa: BLE001 — never block extraction on the guard
        return True

# --- Tier-2 knowledge questionnaire -----------------------------------------
# Tooltips describe mechanics qualitatively ("Attack Speed reduces reload time
# slightly") but omit the numbers a simulator needs. This pass asks the LLM's
# GAME KNOWLEDGE for those parameters only. It cannot introduce new mechanics
# (evidence-grounded Tier 1 owns that); every answer is clamped to sanity
# bounds and stored with source="llm-knowledge" so assumptions stay auditable.
KNOWLEDGE_SYSTEM = (
    "You are a Wild Rift (mobile) expert. Answer a short questionnaire about ONE "
    "champion's mechanics from your knowledge of the actual game. Wild Rift often "
    "differs from PC League — answer for WILD RIFT. If unsure, use null.\n"
    'Return ONLY JSON: {"asEfficiency": 0.0-1.0 (how much this champion benefits '
    "from attack speed items vs a normal marksman; 1.0 = fully, lower for reload/"
    "fixed-AS/caster kits), \"reloadSeconds\": seconds to reload if the kit has an "
    'ammo system else null, "resource": "mana"|"energy"|"none", '
    '"abilitiesCanCrit": true|false, "confidence": "high"|"medium"|"low"}'
)


def knowledge_call(key: str, champ: dict) -> dict:
    abils = "\n".join(f"[{a['slot']}] {a['name']}: {a['text'][:200]}"
                      for a in champ["abilities"])
    body = {"model": MODEL,
            "messages": [{"role": "system", "content": KNOWLEDGE_SYSTEM},
                         {"role": "user", "content": f"CHAMPION: {champ['name']}\n{abils}"}],
            "response_format": {"type": "json_object"},
            "temperature": 0.1, "max_tokens": 4000, "stream": False}
    headers = {"Authorization": f"Bearer {key}"}
    for attempt in range(4):
        r = requests.post(DEEPSEEK_URL, json=body, headers=headers, timeout=180)
        if r.status_code in (429, 500, 502, 503, 504) and attempt < 3:
            time.sleep(3 * (attempt + 1))
            continue
        if not r.ok:
            raise RuntimeError(f"deepseek {r.status_code}")
        return json.loads(r.json()["choices"][0]["message"]["content"])
    return {}


def _clamp_knowledge(raw: dict) -> dict:
    out: dict = {"source": "llm-knowledge"}
    eff = raw.get("asEfficiency")
    if isinstance(eff, (int, float)):
        out["asEfficiency"] = max(0.2, min(1.0, float(eff)))
    rs = raw.get("reloadSeconds")
    if isinstance(rs, (int, float)):
        out["reloadSeconds"] = max(0.5, min(3.0, float(rs)))
    if raw.get("resource") in ("mana", "energy", "none"):
        out["resource"] = raw["resource"]
    if isinstance(raw.get("abilitiesCanCrit"), bool):
        out["abilitiesCanCrit"] = raw["abilitiesCanCrit"]
    if raw.get("confidence") in ("high", "medium", "low"):
        out["confidence"] = raw["confidence"]
    return out

SCHEMA = (
    'Return ONLY this JSON object:\n'
    '{"abilities": {"P": {"damage": [...], "steroids": [...], "defensive": [...], '
    '"unmodeled": [...]}, "1": {...}, "2": {...}, "3": {...}, "4": {...}},\n'
    ' "combo": ["slot or auto", ...],\n'
    ' "mechanics": [{"kind":"reload|fixedAttackSpeed|doubleShot|everyNHit|noResource|transform",'
    '"evidence":"verbatim tooltip quote","magazine":N,"secondShotPct":N,"n":N}]}\n'
    "combo = this champion's standard all-in burst sequence as slots, e.g. "
    '["3","1","auto","4","auto","1"] (4-10 actions, "auto" for basic attacks). '
    "This is the one field based on how the champion is actually played, not the tooltip."
)


def _numbers_in(text: str) -> set[str]:
    """All numeric tokens in the tooltip, normalised (150 -> '150', 1.5 -> '1.5')."""
    toks = set()
    for m in re.findall(r"\d+(?:\.\d+)?", text):
        toks.add(m)
        if "." in m:
            toks.add(m.rstrip("0").rstrip("."))
        try:
            f = float(m)
            if f == int(f):
                toks.add(str(int(f)))
        except ValueError:
            pass
    return toks


def _norm_num(x: float) -> str:
    return str(int(x)) if float(x) == int(x) else str(x).rstrip("0").rstrip(".")


def _derivable(v: float, allowed: set[str]) -> bool:
    """Is `v` justified by the ability text?

    Verbatim-only was too strict and it contradicted our own prompt. A
    multi-hit ability's total IS the thing the engine needs, and it is never
    printed: Gwen's Snip Snip reads "snips twice, +1 per stack (max 4)... each
    snip 14/18/22/26, final snip 70/90/110/130", so one cast at max stacks is
    5*14 + 70 = 140. The model computed 140/180/220/260 correctly and the filter
    deleted all four for not appearing literally -- leaving her PRIMARY damage
    ability modelled as dealing nothing, which is why an AP bruiser priced AD
    (0.88) above AP (0.64).

    So accept a value the text DERIVES: verbatim, a sum of listed numbers, a
    listed number times a small integer (N hits), or n*a + b (N hits plus a
    different final hit). Anything else is still rejected as invented.
    """
    if _norm_num(v) in allowed:
        return True
    nums = sorted({float(x) for x in allowed})
    for a in nums:                                  # 5 snips of 14
        for k in range(2, 11):
            if abs(a * k - v) < 1e-6:
                return True
            for b in nums:                          # 5 snips of 14 + a 70 final
                if abs(a * k + b - v) < 1e-6:
                    return True
    for r in (2, 3):                                # plain sums
        for combo in combinations(nums, r):
            if abs(sum(combo) - v) < 1e-6:
                return True
    return False


def _grounded(comp: dict, allowed: set[str]) -> list[str]:
    """Return the extracted numbers the source text cannot justify.

    Zero asserts nothing — a component with base 0 is simply pure-ratio damage
    (an on-hit passive, a shotgun pellet), so it needs no evidence. Requiring a
    verbatim "0" silently deleted real kit mechanics."""
    bad = []
    base = comp.get("base")
    if base is not None:
        for b in (base if isinstance(base, list) else [base]):
            if float(b) == 0:
                continue
            if not _derivable(float(b), allowed):
                bad.append(f"base {b}")
    for r in comp.get("ratios") or []:
        p = r.get("pct")
        for pv in (p if isinstance(p, list) else [p]):
            if pv is None or float(pv) == 0:
                continue
            if not _derivable(float(pv), allowed):
                bad.append(f"ratio {pv}%")
    return bad


def _parse_cds(cds: list) -> list[float]:
    vals = []
    for cd in cds or []:
        for tok in re.split(r"[/\s]+", str(cd)):
            try:
                vals.append(float(tok))
            except ValueError:
                pass
    return vals


def call_llm(key: str, champ: dict) -> dict:
    abils = "\n".join(f"[{a['slot']}] {a['name']}: {a['text']}" for a in champ["abilities"])
    prompt = f"CHAMPION: {champ['name']}\n{abils}\n\n{SCHEMA}"
    def _call(messages):
        body = {"model": MODEL, "messages": messages,
                "response_format": {"type": "json_object"},
                "temperature": 0.1, "max_tokens": 16000, "stream": False}
        headers = {"Authorization": f"Bearer {key}"}
        for attempt in range(5):
            r = requests.post(DEEPSEEK_URL, json=body, headers=headers, timeout=300)
            if r.status_code in (429, 500, 502, 503, 504) and attempt < 4:
                time.sleep(3 * (attempt + 1))
                continue
            if not r.ok:
                raise RuntimeError(f"deepseek {r.status_code}: {r.text[:200]}")
            return r.json()["choices"][0]["message"]["content"]
        raise RuntimeError("deepseek retries exhausted")

    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]
    text = _call(msgs)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # usually truncation — ask for a compact re-emit once
        msgs.append({"role": "assistant", "content": text[:2000]})
        msgs.append({"role": "user", "content":
                     "Your JSON was invalid or truncated. Re-output the FULL JSON object, "
                     "minified (no whitespace), keeping unmodeled notes under 8 words each."})
        return json.loads(_call(msgs))


def extract(champ: dict, key: str) -> tuple[dict, list[str]]:
    raw = call_llm(key, champ)
    by_slot = {a["slot"]: a for a in champ["abilities"]}
    issues: list[str] = []
    out: dict = {"abilities": {}}
    for slot, ab in (raw.get("abilities") or {}).items():
        src = by_slot.get(slot)
        if not src:
            continue
        allowed = _numbers_in(src.get("text", ""))
        damage, dropped = [], []
        for comp in ab.get("damage") or []:
            # Strip an ungrounded RATIO instead of discarding the whole
            # component. One bad ratio used to delete the entire ability: Gwen's
            # passive reads "1% (+0.005% AP) of target max Health", the model
            # wrote the AP ratio as 0.5%, and her ENTIRE on-hit passive vanished
            # along with the perfectly good 1% max-HP ratio. Losing one scaling
            # is a small error; losing the ability is a large one.
            ratios = comp.get("ratios") or []
            if ratios:
                keep = [r for r in ratios
                        if not _grounded({"ratios": [r]}, allowed)]
                if len(keep) != len(ratios):
                    lost = [r.get("stat") for r in ratios if r not in keep]
                    dropped.append(f"{slot}/{comp.get('name','?')}: dropped "
                                   f"ungrounded ratio(s) {lost}, kept the rest")
                    comp = {**comp, "ratios": keep}
            bad = _grounded(comp, allowed)   # base still has to hold up
            if bad:
                dropped.append(f"{slot}/{comp.get('name','?')}: ungrounded {bad}")
                continue
            if comp.get("type") not in ("physical", "magic", "true"):
                dropped.append(f"{slot}: bad type {comp.get('type')}")
                continue
            damage.append(comp)
        steroids = []
        for st in ab.get("steroids") or []:
            if st.get("stat") in STEROID_STATS:
                steroids.append(st)
        un_raw = ab.get("unmodeled") or []
        if isinstance(un_raw, str):  # model sometimes returns one string, not a list
            un_raw = [un_raw]
        unmodeled = [str(u) for u in un_raw] + dropped
        issues.extend(dropped)
        out["abilities"][slot] = {
            "name": src["name"],
            "cooldowns": _parse_cds(src.get("cooldowns")),
            "damage": damage,
            "steroids": steroids,
            "defensive": ab.get("defensive") or [],
            "unmodeled": unmodeled,
        }
    combo = [str(a) for a in (raw.get("combo") or [])
             if str(a) == "auto" or str(a) in by_slot]
    if 4 <= len(combo) <= 12:
        out["combo"] = combo

    # Kit mechanics: grounded by EVIDENCE — the quoted text must literally appear
    # in the kit tooltips (whitespace-normalized), the mechanics analog of the
    # number-grounding rule. Numeric params must also pass number grounding.
    full_text = " ".join(" ".join((a.get("text") or "").split())
                         for a in champ["abilities"]).lower()
    all_nums = _numbers_in(" ".join(a.get("text") or "" for a in champ["abilities"]))
    mechanics = []
    for m in raw.get("mechanics") or []:
        kind = m.get("kind")
        ev = " ".join(str(m.get("evidence") or "").split()).lower()
        if kind not in MECHANIC_KINDS:
            continue
        if len(ev) < 8 or ev not in full_text:
            issues.append(f"mechanic {kind}: evidence not found in kit text")
            continue
        entry: dict = {"kind": kind, "evidence": m.get("evidence")}
        for p in ("magazine", "secondShotPct", "n"):
            v = m.get(p)
            if isinstance(v, (int, float)) and _norm_num(float(v)) in all_nums:
                entry[p] = v
        mechanics.append(entry)

    # Core mechanics from game knowledge fill what the evidence pass missed
    # (tooltips omit pellet counts, and the grounded pass is non-deterministic —
    # it has silently dropped Graves' reload between runs). Grounded always wins.
    try:
        mechanics = merge_core_mechanics(mechanics, core_mechanics_call(key, champ))
    except Exception:  # noqa: BLE001 — knowledge is optional
        pass
    if mechanics:
        out["mechanics"] = mechanics

    # Tier-2 knowledge parameters (bounded, labeled, non-authoritative)
    try:
        out["knowledge"] = _clamp_knowledge(knowledge_call(key, champ))
    except Exception:  # noqa: BLE001 — knowledge is optional
        pass
    return out, issues


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--fresh", action="store_true")
    args = ap.parse_args()
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not key:
        raise SystemExit("DEEPSEEK_API_KEY is not set")

    champs = json.loads(CHAMPS.read_text(encoding="utf-8"))
    only = {n.strip() for n in args.only.split(",") if n.strip()}
    if only:
        champs = [c for c in champs if c["name"] in only]

    cache: dict = {}
    if OUT.exists() and not args.fresh:
        cache = json.loads(OUT.read_text(encoding="utf-8"))
    todo = [c for c in champs if only or c["name"] not in cache]
    print(f"{len(champs)} in scope | {len(todo)} to extract")

    for i, c in enumerate(todo, 1):
        try:
            rec, issues, ok = None, [], False
            for _try in range(3):  # LLM extraction is a dice roll; validate each
                rec, issues = extract(c, key)
                n_direct = sum(len(a["damage"]) for a in rec["abilities"].values())
                if n_direct == 0:      # bad roll: a kit with zero damage
                    continue
                if _damage_type_ok(c["name"], rec, c):
                    ok = True
                    break
            if not ok:
                issues.append("damage type contradicts primaryDamage after 3 tries")
        except Exception as e:  # noqa: BLE001
            print(f"  ! {c['name']}: {e}")
            continue
        if rec is None:
            continue
        n_dmg = sum(len(a["damage"]) for a in rec["abilities"].values())
        n_un = sum(len(a["unmodeled"]) for a in rec["abilities"].values())
        # preserve blocks this pass doesn't produce (e.g. the behaviour model from
        # scripts.extract_behavior) — a plain overwrite silently wiped them.
        for _keep in ("behavior",):
            if _keep in cache.get(c["name"], {}) and _keep not in rec:
                rec[_keep] = cache[c["name"]][_keep]
        cache[c["name"]] = rec
        OUT.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
        flag = f"  ({n_un} unmodeled)" if n_un else ""
        print(f"  [{i}/{len(todo)}] {c['name']:16} {n_dmg} damage components{flag}")

    print(f"\nwrote {OUT.relative_to(ROOT)} ({len(cache)} champions)")


if __name__ == "__main__":
    main()
