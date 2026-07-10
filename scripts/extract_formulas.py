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
    "\"hits\":N (default 1; e.g. 3-hit ability = 3, per-bullet abilities use bullets),"
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
    "- Empowered/enhanced basic attacks are damage components with when='per auto'.\n"
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
                  "noResource", "transform"}

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


def _grounded(comp: dict, allowed: set[str]) -> list[str]:
    """Return the extracted numbers that do NOT appear in the source text."""
    bad = []
    base = comp.get("base")
    if base is not None:
        for b in (base if isinstance(base, list) else [base]):
            if _norm_num(float(b)) not in allowed:
                bad.append(f"base {b}")
    for r in comp.get("ratios") or []:
        p = r.get("pct")
        for pv in (p if isinstance(p, list) else [p]):
            if pv is not None and _norm_num(float(pv)) not in allowed:
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
            bad = _grounded(comp, allowed)
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
            rec, issues = extract(c, key)
            n_direct = sum(len(a["damage"]) for a in rec["abilities"].values())
            if n_direct == 0:  # bad roll: a kit with zero damage components
                rec, issues = extract(c, key)
        except Exception as e:  # noqa: BLE001
            print(f"  ! {c['name']}: {e}")
            continue
        n_dmg = sum(len(a["damage"]) for a in rec["abilities"].values())
        n_un = sum(len(a["unmodeled"]) for a in rec["abilities"].values())
        cache[c["name"]] = rec
        OUT.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
        flag = f"  ({n_un} unmodeled)" if n_un else ""
        print(f"  [{i}/{len(todo)}] {c['name']:16} {n_dmg} damage components{flag}")

    print(f"\nwrote {OUT.relative_to(ROOT)} ({len(cache)} champions)")


if __name__ == "__main__":
    main()
