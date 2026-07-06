"""LLM-authored optimal builds + runes per champion (Gemini), grounded & validated.

Per-class build VARIANTS (not a fixed balanced+damage for everyone):
  Assassin  -> balanced, oneshot
  Bruiser   -> balanced, tanky, damage
  Marksman  -> crit, balanced, damage
  Mage      -> burst, balanced, battlemage
  Tank      -> tanky, damage
  Enchanter -> utility, poke

For each champion we give Gemini the full scraped kit + item/rune pools + the
item-exclusivity (mutex) rules, and ask it to design each variant. Grounding:
Gemini may ONLY use items/runes from the pool; every slug is validated, and each
build is checked against the mutex rules. Role-aware rune hints are injected
(e.g. junglers -> Overgrowth). Offline, once per patch -> data/champion_builds.json.

Run (needs GEMINI_API_KEY or GOOGLE_API_KEY):
    python -m scripts.build_champions_llm --only "Graves,Xin Zhao,Hecarim"
    python -m scripts.build_champions_llm
"""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

ROOT = Path(__file__).resolve().parent.parent
ITEMS = ROOT / "data" / "items.json"
RUNES = ROOT / "data" / "runes.json"
CHAMPS = ROOT / "data" / "champions_wr.json"
RULES = ROOT / "data" / "item_rules.json"
SITE = ROOT / "web-next" / "src" / "data" / "site.json"
OUT = ROOT / "data" / "champion_builds.json"

MODEL = "gemini-2.5-flash"

# --- per-class build variants ---------------------------------------------
VARIANT_SETS = {
    "Assassin":  ["balanced", "oneshot"],
    "Bruiser":   ["balanced", "tanky", "damage"],
    "Marksman":  ["crit", "balanced", "damage"],
    "Mage":      ["burst", "balanced", "battlemage"],
    "Tank":      ["tanky", "damage"],
    "Enchanter": ["utility", "poke"],
}
DEFAULT_VARIANTS = ["balanced", "damage"]

VARIANT_DESC = {
    "balanced":   "damage with some survivability — the safe default",
    "oneshot":    "maximum burst to instantly delete a priority target",
    "damage":     "maximum damage for this champion's kit (lethality / on-hit / AD as fits)",
    "tanky":      "frontline build prioritising survivability while staying a real threat",
    "crit":       "crit-based build stacking crit chance + crit damage",
    "burst":      "AP burst build to one-shot squishies",
    "battlemage": "sustained AP damage / drain-tank build",
    "utility":    "team-support build maximising heal / shield / CC uptime",
    "poke":       "poke-damage build for chipping enemies before fights",
}

# role -> extra rune guidance
ROLE_RUNE_HINTS = {
    "Jungle": "This is a JUNGLER: Overgrowth (Resolve) is very strong for junglers "
              "(scales HP off monster kills) — strongly favour it as a tree minor or flex "
              "unless a clearly better option fits this champion.",
}

SYSTEM = (
    "You are a top-tier Wild Rift theorycrafter. For a champion you design several "
    "BUILD VARIANTS (given per champion) that synergise with the champion's passive "
    "and abilities. Hard rules:\n"
    "- Wild Rift is burst-heavy and matches average 15-20 minutes: favour gold-efficient "
    "items and a realistic build order (item 1 is rushed first). Don't plan for 40-minute games.\n"
    "- Account for the champion's damage type and ability scalings (AD/AP/on-hit/crit/"
    "max-health/attack-speed) and per-level base stats.\n"
    "- Each variant is 5 items + 1 boots (+1 boot enchantment).\n"
    "- ITEM-EXCLUSIVITY: you may build AT MOST ONE item from each mutex group given. "
    "Never put two items from the same group in one build.\n"
    "- Wild Rift rune page = 1 keystone + 3 minors from ONE tree + 1 flex from any tree.\n"
    "- You may ONLY use items/runes from the provided pool (exact slug/name). Never invent.\n"
    "- Be decisive: the BEST option per variant, not a menu."
)


def _load(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _clip(s: str, n: int = 180) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1] + "…"


def _item_pool(items: list[dict]) -> str:
    by_cat: dict[str, list[str]] = {}
    for it in items:
        stats = ", ".join(f"{k} {v['value']}{'%' if v['percent'] else ''}"
                          for k, v in it["stats"].items()) or "no stats"
        passive = _clip(" ".join(it["passives"]) or "(no passive)")
        by_cat.setdefault(it["category"], []).append(
            f'  {it["slug"]} | {it["name"]} | {it["cost"]}g | {stats} | {passive}')
    order = ["Physical", "Magic", "Defense", "Support", "Boots", "Enchantment"]
    return "\n".join(f"[{c}]\n" + "\n".join(by_cat[c]) for c in order if c in by_cat)


def _rune_pool(runes: list[dict]) -> str:
    ks = [r["name"] for r in runes if r["type"] == "Keystone"]
    by_tree: dict[str, list[str]] = {}
    for r in runes:
        if r["type"] == "Minor":
            by_tree.setdefault(r.get("tree", "?"), []).append(r["name"])
    minors = "\n".join(f"  {t}: {', '.join(ns)}" for t, ns in by_tree.items())
    return "Keystones: " + ", ".join(ks) + "\nMinor runes by tree:\n" + minors


def _mutex_block(rules: dict, items_by_slug: dict) -> str:
    lines = []
    for name, slugs in rules.get("mutexGroups", {}).items():
        names = [items_by_slug[s]["name"] for s in slugs if s in items_by_slug]
        lines.append(f"  {name}: {', '.join(names)}")
    return "ITEM MUTEX GROUPS (build at most ONE from each):\n" + "\n".join(lines)


def _champion_block(c: dict, champ_class: str, role: str) -> str:
    bs = c.get("baseStats", {})
    def lvl(k):
        s = bs.get(k)
        return f"{s['base']}->{s['lvl15']}" if s else "?"
    stat_line = (f"HP {lvl('hp')}, AD {lvl('ad')}, AS {lvl('attackSpeed')}, "
                 f"Armor {lvl('armor')}, MR {lvl('mr')}, MS {bs.get('moveSpeed',{}).get('base','?')}")
    abils = "\n".join(f"  [{a['slot']}] {a['name']}: {_clip(a['text'], 220)}"
                      for a in c.get("abilities", []))
    return (f"CHAMPION: {c['name']}  (class {champ_class}, role {role})\n"
            f"Base stats (lvl1->lvl15): {stat_line}\n"
            f"Primary damage: {c.get('primaryDamage')} | scales with: {c.get('scalesWith')} "
            f"| mechanics: {c.get('mechanics')}\nAbilities:\n{abils}")


def _schema(variants: list[str]) -> str:
    build_shape = (
        '{"summary":"1-2 sentences","coreBuild":[{"slug":"...","reason":"<=14 words"}],'
        ' "boots":{"slug":"...","reason":"..."},"enchantment":{"slug":"...","reason":"..."},'
        ' "situational":[{"slug":"...","when":"vs ... "}],'
        ' "runes":{"keystone":{"name":"...","reason":"..."},'
        '"primaryTree":"Domination|Resolve|Precision|Sorcery",'
        '"treeMinors":[{"name":"...","reason":"<=10 words"}],'
        '"flexMinor":{"name":"...","reason":"<=10 words"}}}')
    vlines = "\n".join(f'    "{v}": {build_shape}   // {VARIANT_DESC[v]}' for v in variants)
    return (
        "coreBuild = 5 items IN BUILD ORDER (index 0 rushed first). treeMinors = exactly 3 "
        "from primaryTree; flexMinor = 1 from any tree. situational = 1-2 swaps.\n"
        "Return ONLY this JSON object:\n{\n"
        '  "damageProfile": "short label e.g. lethality / crit-adc / ap-bruiser / tank",\n'
        '  "canOneshot": true/false,\n'
        '  "builds": {\n' + vlines + "\n  }\n}")


def build_prompt(cblock, item_pool, rune_pool, mutex_block, variants, role) -> str:
    role_hint = ROLE_RUNE_HINTS.get(role, "")
    hint = f"\nROLE NOTE: {role_hint}\n" if role_hint else ""
    vlist = ", ".join(f"{v} ({VARIANT_DESC[v]})" for v in variants)
    return (f"{cblock}\n{hint}\nDesign these build variants: {vlist}\n\n"
            f"=== ITEM POOL (exact slugs only) ===\n{item_pool}\n\n{mutex_block}\n\n"
            f"=== RUNE POOL (exact names only) ===\n{rune_pool}\n\n{_schema(variants)}")


def _extract_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError("no JSON object in output")
    return json.loads(m.group(0))


def _canon(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _validate(rec, variants, item_by_slug, rune_by_name, mutex) -> tuple[dict, list[str]]:
    warn: list[str] = []
    item_canon = {_canon(s): it for s, it in item_by_slug.items()}
    item_canon.update({_canon(it["name"]): it for it in item_by_slug.values()})
    rune_canon = {_canon(n): r for n, r in rune_by_name.items()}

    def ok_item(slug, cat=None):
        it = item_by_slug.get(slug) or item_canon.get(_canon(slug))
        if not it:
            warn.append(f"unknown item: {slug}")
            return None
        if cat and it["category"] != cat:
            warn.append(f"{it['slug']} is {it['category']}, expected {cat}")
        return {"slug": it["slug"], "name": it["name"], "cost": it["cost"], "icon": it["icon"]}

    def ok_rune(name):
        return rune_by_name.get(name) or rune_canon.get(_canon(name))

    def rune_entry(e):
        r = ok_rune(e.get("name"))
        if not r:
            warn.append(f"unknown rune: {e.get('name')}")
            return None
        return {"name": r["name"], "slug": r["slug"], "tree": r.get("tree", ""),
                "icon": r["icon"], "reason": e.get("reason", "")}

    def val_build(bd, label):
        bd = bd or {}
        core = []
        for e in bd.get("coreBuild") or []:
            b = ok_item(e.get("slug"))
            if b:
                b["reason"] = e.get("reason", "")
                core.append(b)
        boots = ok_item((bd.get("boots") or {}).get("slug"), "Boots")
        if boots:
            boots["reason"] = (bd.get("boots") or {}).get("reason", "")
        ench = ok_item((bd.get("enchantment") or {}).get("slug"), "Enchantment")
        if ench:
            ench["reason"] = (bd.get("enchantment") or {}).get("reason", "")
        situ = []
        for e in bd.get("situational") or []:
            b = ok_item(e.get("slug"))
            if b:
                b["when"] = e.get("when", "")
                situ.append(b)
        # mutex legality check on the core items
        core_slugs = {c["slug"] for c in core}
        for gname, group in mutex.items():
            if len(core_slugs & set(group)) > 1:
                warn.append(f"{label}: illegal — 2+ from mutex '{gname}'")

        rin = bd.get("runes") or {}
        ks_in = rin.get("keystone") or {}
        ks = ok_rune(ks_in.get("name"))
        if ks_in.get("name") and not ks:
            warn.append(f"{label}: unknown keystone {ks_in.get('name')}")
        primary = rin.get("primaryTree", "")
        tmins = [x for x in (rune_entry(e) for e in rin.get("treeMinors") or []) if x]
        for tm in tmins:
            if primary and tm["tree"] != primary:
                warn.append(f"{label}: {tm['name']} not {primary}")
        flex = rune_entry(rin.get("flexMinor") or {})
        return {
            "summary": bd.get("summary", ""),
            "coreBuild": core, "boots": boots, "enchantment": ench, "situational": situ,
            "runes": {
                "keystone": ({"name": ks["name"], "slug": ks["slug"], "icon": ks["icon"],
                              "reason": ks_in.get("reason", "")} if ks else None),
                "primaryTree": primary, "treeMinors": tmins, "flexMinor": flex,
            },
        }

    builds_in = rec.get("builds") or {}
    out_builds = {}
    for v in variants:
        if v not in builds_in:
            warn.append(f"missing variant: {v}")
            continue
        out_builds[v] = val_build(builds_in[v], v)
    return {
        "damageProfile": rec.get("damageProfile", ""),
        "canOneshot": bool(rec.get("canOneshot", False)),
        "variants": variants,
        "builds": out_builds,
    }, warn


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--model", default=MODEL)
    args = ap.parse_args()

    items = _load(ITEMS)
    runes = _load(RUNES)
    champs = _load(CHAMPS)
    rules = _load(RULES) or {}
    site = {c["name"]: c for c in (_load(SITE) or {}).get("champions", [])}
    item_by_slug = {it["slug"]: it for it in items}
    rune_by_name = {r["name"]: r for r in runes}
    mutex = {k: set(v) for k, v in rules.get("mutexGroups", {}).items()}
    item_pool, rune_pool = _item_pool(items), _rune_pool(runes)
    mutex_block = _mutex_block(rules, item_by_slug)

    only = {n.strip() for n in args.only.split(",") if n.strip()}
    if only:
        champs = [c for c in champs if c["name"] in only]

    cache: dict[str, dict] = {}
    if OUT.exists() and not args.fresh:
        cache = json.loads(OUT.read_text(encoding="utf-8"))
    todo = [c for c in champs if only or c["name"] not in cache]
    print(f"{len(champs)} in scope | {len(todo)} to build | model {args.model}")

    client = genai.Client()
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM, response_mime_type="application/json", temperature=0.3)

    for i, c in enumerate(todo, 1):
        name = c["name"]
        meta = site.get(name, {})
        champ_class = meta.get("class", "")
        role = meta.get("role", "")
        variants = VARIANT_SETS.get(champ_class, DEFAULT_VARIANTS)
        cblock = _champion_block(c, champ_class or "?", role or "?")
        prompt = build_prompt(cblock, item_pool, rune_pool, mutex_block, variants, role)
        text = ""
        for attempt in range(5):
            try:
                resp = client.models.generate_content(model=args.model, contents=prompt, config=config)
                text = resp.text or ""
                break
            except (genai_errors.ServerError, genai_errors.ClientError) as e:
                code = getattr(e, "code", None)
                if code in (429, 500, 502, 503, 504) and attempt < 4:
                    wait = 3 * (attempt + 1)
                    print(f"  … {name}: {code}, retry in {wait}s")
                    time.sleep(wait)
                    continue
                raise
        try:
            rec = _extract_json(text)
        except Exception as e:  # noqa: BLE001
            print(f"  ! {name}: parse failed ({e}) — skipping")
            continue
        clean, warn = _validate(rec, variants, item_by_slug, rune_by_name, mutex)
        clean["name"] = name
        clean["class"] = champ_class
        clean["role"] = role
        cache[name] = clean
        OUT.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
        flag = f"  ⚠ {warn}" if warn else ""
        print(f"  [{i}/{len(todo)}] {name} [{champ_class}/{role}]: {'/'.join(variants)}{flag}")

    print(f"\nwrote {OUT.relative_to(ROOT)} ({len(cache)} champions)")


if __name__ == "__main__":
    main()
