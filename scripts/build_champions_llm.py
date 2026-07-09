"""LLM-authored optimal builds + runes per champion, grounded & validated.

Per-class build VARIANTS (not a fixed balanced+damage for everyone):
  Assassin  -> balanced, oneshot
  Bruiser   -> balanced, tanky, damage
  Marksman  -> crit, balanced, damage
  Mage      -> burst, balanced, battlemage
  Tank      -> tanky, damage
  Enchanter -> utility, poke

For each champion we give the model the full scraped kit + item/rune pools + the
item-exclusivity (mutex) rules, plus KIT FLAGS: deterministic synergy hooks
detected from the ability text (move-speed -> damage conversion, short-CD spam
engines, %max-HP damage, ...) that the model MUST address. Grounding: the model
may ONLY use items/runes/summoners from the pools; every slug is validated, and
each build is checked against mutex + rune-page + scaling rules, with a repair
round-trip on failures.

--best-of N generates N candidates and a judge pass picks the strongest build
per variant before validation (self-consistency beats a single sample).

Providers: --provider deepseek (default; needs DEEPSEEK_API_KEY), gemini (needs
GEMINI_API_KEY / GOOGLE_API_KEY), or ollama (local; needs `ollama serve`).

Run:
    python -m scripts.build_champions_llm --only "Hecarim" --best-of 3
    python -m scripts.build_champions_llm --provider gemini
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path

import requests

from web.fight_engine import FORMULAS as ENGINE_FORMULAS, score_build

ROOT = Path(__file__).resolve().parent.parent
ITEMS = ROOT / "data" / "items.json"
RUNES = ROOT / "data" / "runes.json"
CHAMPS = ROOT / "data" / "champions_wr.json"
RULES = ROOT / "data" / "item_rules.json"
SITE = ROOT / "web-next" / "src" / "data" / "site.json"
OUT = ROOT / "data" / "champion_builds.json"
WEB_OUT = ROOT / "web-next" / "src" / "data" / "builds.json"  # what the frontend reads

# ollama default sized for an 8GB-RAM machine: qwen2.5 3B (~2GB) is the smallest
# model that reliably follows our JSON schema over a ~13K-token prompt.
DEFAULT_MODELS = {
    "deepseek": "deepseek-v4-flash",
    "gemini": "gemini-2.5-flash",
    "ollama": "qwen2.5:3b-instruct",
}
OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"

_RULES_EARLY = json.loads(RULES.read_text(encoding="utf-8")) if RULES.exists() else {}
# Reactive anti-comp items: allowed in situational swaps, never in the core build.
SITUATIONAL_ONLY = set((_RULES_EARLY.get("situationalOnly") or {}).get("slugs") or [])

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

# Champions with a scraped kit but no site entry yet (no EU leaderboard data),
# so class/role can't come from site.json. Keep this tiny map current.
CLASS_FALLBACK: dict[str, tuple[str, str]] = {
    "Skarner": ("Tank", "Jungle"),
    "Yunara": ("Marksman", "Dragon"),
    "Cho'Gath": ("Tank", "Baron"),
}

# Wild Rift summoner spells. Icons via ddragon (reliable CDN).
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


def _summoner_pool() -> str:
    return "\n".join(f"  {n}: {v['desc']}" for n, v in SUMMONERS.items())

SYSTEM = (
    "You are a top-tier Wild Rift theorycrafter. For a champion you design several "
    "BUILD VARIANTS (given per champion) that synergise with the champion's passive "
    "and abilities. Hard rules:\n"
    "- SYNERGY FIRST: before choosing anything, mine the PASSIVE and each ability for "
    "stat conversions and interactions (e.g. 'gains AD from bonus move speed' means "
    "move-speed items/runes ARE damage items for this champion; max-health scaling "
    "wants HP stacking; on-hit effects want attack speed; ability-spam kits want "
    "haste/mana). Write these hooks in synergyNotes FIRST, then build around them. "
    "A generically-strong item is WRONG if a synergistic one multiplies the kit.\n"
    "- RESOURCE ENGINE: check the kit's spam pattern. A champion that casts cheap "
    "abilities every few seconds (short-CD spam) turns mana-scaling and per-cast items "
    "(Manamune/Muramana, Archangel's, Spear of Shojin, spellblade) into a compounding "
    "damage engine, and ability haste into raw DPS. A champion with long cooldowns or "
    "no mana gets little from these. Build the ENGINE, not just raw stats.\n"
    "- Wild Rift is burst-heavy and matches average 15-20 minutes: favour gold-efficient "
    "items and a realistic build order (item 1 is rushed first). Don't plan for 40-minute games.\n"
    "- Account for the champion's damage type and ability scalings (AD/AP/on-hit/crit/"
    "max-health/attack-speed) and per-level base stats.\n"
    "- Each variant is 5 items + 1 boots (+1 boot enchantment) + exactly 2 summoner spells.\n"
    "- SUMMONERS: junglers MUST take Smite; non-junglers must NOT. Pick the second spell "
    "for the kit and variant (Ghost for run-you-down fighters, Ignite for kill-lane "
    "assassins, Heal/Barrier for marksmen, Exhaust/Cleanse as matchup calls).\n"
    "- ITEM-EXCLUSIVITY: you may build AT MOST ONE item from each mutex group given. "
    "Never put two items from the same group in one build.\n"
    "- REACTIVE ITEMS (Guardian Angel, Maw, Serpent's Fang, anti-heal items...) answer "
    "a specific enemy comp: they belong in situational swaps ONLY, never the core build.\n"
    "- Wild Rift rune page = 1 keystone + 3 minors from ONE tree + 1 flex from any tree. "
    "Read the rune EFFECTS given and pick for synergy, not popularity.\n"
    "- You may ONLY use items/runes/summoners from the provided pools (exact slug/name). "
    "Never invent.\n"
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
        # Full-ish passive text: clipping at 180 chars used to cut tooltips
        # mid-mechanic (Manamune's Muramana transform, Shojin's stack cap),
        # leaving the model blind to exactly the synergies that matter.
        passive = _clip(" ".join(it["passives"]) or "(no passive)", 340)
        by_cat.setdefault(it["category"], []).append(
            f'  {it["slug"]} | {it["name"]} | {it["cost"]}g | {stats} | {passive}')
    order = ["Physical", "Magic", "Defense", "Support", "Boots", "Enchantment"]
    return "\n".join(f"[{c}]\n" + "\n".join(by_cat[c]) for c in order if c in by_cat)


def _rune_pool(runes: list[dict]) -> str:
    """Keystones + minors WITH their effect text, so the model can actually
    reason about synergies (e.g. Phase Rush move speed with Hecarim's Warpath)
    instead of guessing from names."""
    ks = [f'  {r["name"]}: {_clip(r.get("description", ""), 150)}'
          for r in runes if r["type"] == "Keystone"]
    by_tree: dict[str, list[str]] = {}
    for r in runes:
        if r["type"] == "Minor":
            by_tree.setdefault(r.get("tree", "?"), []).append(
                f'  {r["name"]}: {_clip(r.get("description", ""), 110)}')
    minors = "\n".join(f"[{t}]\n" + "\n".join(ns) for t, ns in by_tree.items())
    return "Keystones:\n" + "\n".join(ks) + "\nMinor runes by tree:\n" + minors


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
    abils = "\n".join(f"  [{a['slot']}] {a['name']}: {_clip(a['text'], 420)}"
                      for a in c.get("abilities", []))
    return (f"CHAMPION: {c['name']}  (class {champ_class}, role {role})\n"
            f"Base stats (lvl1->lvl15): {stat_line}\n"
            f"Primary damage: {c.get('primaryDamage')} | scales with: {c.get('scalesWith')} "
            f"| mechanics: {c.get('mechanics')}\nAbilities:\n{abils}")


def _kit_hints(c: dict) -> list[str]:
    """Deterministic synergy hooks detected from ability text. These are injected
    as mandatory considerations so the model can't overlook a conversion mechanic
    (an LLM pass sometimes did, e.g. Hecarim's move-speed -> AD passive)."""
    abilities = c.get("abilities", [])
    texts = {a["slot"]: " ".join((a.get("text") or "").lower().split()) for a in abilities}
    full = " ".join(texts.values())
    hints: list[str] = []

    # Move speed converts to damage (Hecarim Warpath style).
    for slot, t in texts.items():
        if re.search(r"\(\s*\d+(\.\d+)?%\s*bonus (ms|movement speed)\s*\)", t) or \
           re.search(r"(attack damage|\bad\b|damage)[^.]{0,60}equal to[^.]{0,60}bonus (movement speed|ms)", t) or \
           re.search(r"bonus (movement speed|ms)[^.]{0,60}(as|into|converted to)[^.]{0,30}(attack damage|\bad\b)", t):
            hints.append(
                f"MOVE SPEED IS A DAMAGE STAT: ability [{slot}] converts bonus move speed into damage. "
                "Move-speed sources (Phase Rush, Nimbus Cloak, Celerity, Ghost, MS item passives) are "
                "damage picks here; at least one variant must be built around this.")
            break

    # Energy user: mana items are dead stats.
    is_energy = "energy" in full
    if is_energy:
        hints.append("ENERGY USER: this champion has no mana. Mana items and mana runes are useless.")

    # Short-cooldown spam kit -> compounding per-cast engines.
    def _min_cd(a) -> float | None:
        vals = []
        for cd in a.get("cooldowns") or []:
            for tok in re.split(r"[/\s]+", str(cd)):
                try:
                    vals.append(float(tok))
                except ValueError:
                    pass
        return min(vals) if vals else None
    spam = [(a["slot"], _min_cd(a)) for a in abilities
            if a["slot"] in ("1", "2", "3") and _min_cd(a) is not None and _min_cd(a) <= 4.5]
    if spam and not is_energy:
        slot, cd = spam[0]
        hints.append(
            f"SHORT-CD SPAM KIT: ability [{slot}] recharges every ~{cd:g}s. Per-cast engines compound "
            "hard here: Manamune/Muramana, Spear of Shojin, spellblade items, ability haste. Mana "
            "economy is a real constraint — evaluate this engine explicitly.")

    # % max-health damage (tank shred already in kit).
    if re.search(r"(target'?s?|enemy'?s?|their) (maximum|max)(imum)? (health|hp)", full):
        hints.append("BUILT-IN %MAX-HP DAMAGE: the kit already shreds high-HP targets; attack speed / "
                     "haste multiply it, and anti-tank items are less needed.")
    # Scales with own max health.
    elif re.search(r"(his|her|your|its) (maximum|max)(imum)? (health|hp)", full):
        hints.append("OWN MAX-HP SCALING: abilities scale with the champion's own max health, so HP "
                     "items are damage items too (Heartsteel-style stacking is premium).")

    # On-hit / empowered attack kit.
    if "onHit" in (c.get("mechanics") or []):
        hints.append("ON-HIT KIT: empowered/next-attack effects in the kit; attack speed and on-hit "
                     "items multiply the passive.")

    # Crit interaction written into the kit.
    if "critical" in full:
        hints.append("CRIT INTERACTION: the kit references critical strikes; crit items scale it.")

    return hints[:4]


def _schema(variants: list[str]) -> str:
    build_shape = (
        '{"summary":"1-2 sentences","coreBuild":[{"slug":"...","reason":"<=14 words"}],'
        ' "boots":{"slug":"...","reason":"..."},"enchantment":{"slug":"...","reason":"..."},'
        ' "situational":[{"slug":"...","when":"vs ... "}],'
        ' "summoners":[{"name":"...","reason":"<=8 words"},{"name":"...","reason":"<=8 words"}],'
        ' "runes":{"keystone":{"name":"...","reason":"..."},'
        '"primaryTree":"Domination|Resolve|Precision|Sorcery",'
        '"treeMinors":[{"name":"...","reason":"<=10 words"}],'
        '"flexMinor":{"name":"...","reason":"<=10 words"}}}')
    vlines = "\n".join(f'    "{v}": {build_shape}   // {VARIANT_DESC[v]}' for v in variants)
    return (
        "coreBuild = 5 items IN BUILD ORDER (index 0 rushed first). treeMinors = exactly 3 "
        "from primaryTree; flexMinor = 1 from any tree. situational = 1-2 swaps. "
        "summoners = exactly 2 distinct spells.\n"
        "Return ONLY this JSON object (synergyNotes FIRST — the builds must follow from them):\n{\n"
        '  "synergyNotes": ["2-4 short bullets: the kit\'s strongest passive/ability <-> '
        'item/rune interactions"],\n'
        '  "damageProfile": "short label e.g. lethality / crit-adc / ap-bruiser / tank",\n'
        '  "canOneshot": true/false,\n'
        '  "builds": {\n' + vlines + "\n  }\n}")


def build_prompt(cblock, item_pool, rune_pool, mutex_block, variants, role,
                 kit_flags: list[str] | None = None) -> str:
    role_hint = ROLE_RUNE_HINTS.get(role, "")
    hint = f"\nROLE NOTE: {role_hint}\n" if role_hint else ""
    flags = ""
    if kit_flags:
        flags = ("\nKIT FLAGS (auto-detected from the ability text — you MUST address each one "
                 "in synergyNotes and reflect it in the builds where it fits):\n"
                 + "\n".join(f"- {f}" for f in kit_flags) + "\n")
    vlist = ", ".join(f"{v} ({VARIANT_DESC[v]})" for v in variants)
    return (f"{cblock}\n{hint}{flags}\nDesign these build variants: {vlist}\n\n"
            f"=== ITEM POOL (exact slugs only) ===\n{item_pool}\n\n{mutex_block}\n\n"
            f"=== RUNE POOL (exact names only, effects shown) ===\n{rune_pool}\n\n"
            f"=== SUMMONER SPELLS (pick exactly 2 per build) ===\n{_summoner_pool()}\n\n"
            f"{_schema(variants)}")


def _extract_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError("no JSON object in output")
    return json.loads(m.group(0))


def _canon(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


# Variants whose core items must match the champion's ability scaling.
DAMAGE_VARIANTS = {"damage", "burst", "oneshot", "crit", "poke", "battlemage"}


def _validate(rec, variants, item_by_slug, rune_by_name, mutex,
              scales: list[str] | None = None, role: str = "") -> tuple[dict, list[str], list[str]]:
    """Validate + normalise one champion record.

    Returns (clean, errors, warnings). `errors` are hard failures that make a
    build unshippable (illegal / incomplete / contradicts the champion's
    scalings) and trigger a repair round-trip; `warnings` are issues we
    tolerate but persist for auditing.
    """
    err: list[str] = []
    warn: list[str] = []
    scales = scales or []
    item_canon = {_canon(s): it for s, it in item_by_slug.items()}
    item_canon.update({_canon(it["name"]): it for it in item_by_slug.values()})
    rune_canon = {_canon(n): r for n, r in rune_by_name.items()}

    def ok_item(slug, label, cat=None, forbid=("Boots", "Enchantment")):
        it = item_by_slug.get(slug) or item_canon.get(_canon(slug))
        if not it:
            err.append(f"{label}: unknown item '{slug}'")
            return None
        if cat and it["category"] != cat:
            err.append(f"{label}: {it['slug']} is category {it['category']}, expected {cat}")
        if not cat and it["category"] in forbid:
            err.append(f"{label}: {it['slug']} is {it['category']} — not allowed in this slot")
        return {"slug": it["slug"], "name": it["name"], "cost": it["cost"], "icon": it["icon"]}

    def ok_rune(name):
        return rune_by_name.get(name) or rune_canon.get(_canon(name))

    def rune_entry(e, label, want_type="Minor"):
        r = ok_rune(e.get("name"))
        if not r:
            err.append(f"{label}: unknown rune '{e.get('name')}'")
            return None
        if r.get("type") != want_type:
            err.append(f"{label}: {r['name']} is a {r.get('type')}, expected {want_type}")
        return {"name": r["name"], "slug": r["slug"], "tree": r.get("tree", ""),
                "icon": r["icon"], "reason": e.get("reason", "")}

    def val_build(bd, label):
        bd = bd or {}
        core = []
        for e in bd.get("coreBuild") or []:
            b = ok_item(e.get("slug"), f"{label} core")
            if b:
                b["reason"] = e.get("reason", "")
                core.append(b)
        slugs = [c["slug"] for c in core]
        for s in slugs:
            if s in SITUATIONAL_ONLY:
                err.append(f"{label}: {s} is a reactive/situational item — move it to "
                           f"situational swaps, never the core build")
        if len(core) != 5:
            err.append(f"{label}: coreBuild has {len(core)} valid items, need exactly 5")
        if len(set(slugs)) != len(slugs):
            err.append(f"{label}: duplicate item in coreBuild")
        for gname, group in mutex.items():
            hit = sorted(set(slugs) & set(group))
            if len(hit) > 1:
                err.append(f"{label}: ILLEGAL — {' + '.join(hit)} share mutex group '{gname}'")

        # Scaling coherence: a damage variant must build the stat the champion's
        # abilities actually scale with (caught Malphite getting an AD 'damage'
        # build despite scalesWith=['ap']). Hybrid scalers are exempt; attack-
        # speed scalers only warn, since on-hit AD builds are legitimate there.
        if label in DAMAGE_VARIANTS and core:
            has_ad = any(s in scales for s in ("ad", "bonusAd"))
            has_ap = "ap" in scales
            phys = sum(1 for c in core if item_by_slug[c["slug"]]["category"] == "Physical")
            magic = sum(1 for c in core if item_by_slug[c["slug"]]["category"] == "Magic")
            msg = None
            if has_ap and not has_ad and phys > magic:
                msg = (f"{label}: champion scales ONLY with AP but core is {phys} physical vs "
                       f"{magic} magic items — build AP damage items instead")
            elif has_ad and not has_ap and magic > phys:
                msg = (f"{label}: champion scales ONLY with AD but core is {magic} magic vs "
                       f"{phys} physical items — build AD damage items instead")
            if msg:
                (warn if "attackSpeed" in scales else err).append(msg)

        boots_in = bd.get("boots") or {}
        boots = ok_item(boots_in.get("slug"), f"{label} boots", cat="Boots") if boots_in.get("slug") else None
        if boots:
            boots["reason"] = boots_in.get("reason", "")
        else:
            err.append(f"{label}: missing boots")
        ench_in = bd.get("enchantment") or {}
        ench = ok_item(ench_in.get("slug"), f"{label} enchant", cat="Enchantment") if ench_in.get("slug") else None
        if ench:
            ench["reason"] = ench_in.get("reason", "")
        else:
            err.append(f"{label}: missing boot enchantment")
        situ = []
        for e in bd.get("situational") or []:
            b = ok_item(e.get("slug"), f"{label} situational", forbid=())
            if b:
                b["when"] = e.get("when", "")
                situ.append(b)
        if not situ:
            warn.append(f"{label}: no situational swaps")

        # Summoner spells: exactly 2 distinct known spells; junglers must take
        # Smite, everyone else must not.
        sums = []
        for e in bd.get("summoners") or []:
            n = next((k for k in SUMMONERS if _canon(k) == _canon(e.get("name", ""))), None)
            if not n:
                err.append(f"{label}: unknown summoner '{e.get('name')}'")
                continue
            sums.append({"name": n, "icon": f"{_DD_SPELL}/{SUMMONERS[n]['dd']}.png",
                         "reason": e.get("reason", "")})
        names = [s["name"] for s in sums]
        if len(sums) != 2:
            err.append(f"{label}: {len(sums)} valid summoners, need exactly 2")
        if len(set(names)) != len(names):
            err.append(f"{label}: duplicate summoner spell")
        if role == "Jungle" and "Smite" not in names:
            err.append(f"{label}: jungler must take Smite")
        if role and role != "Jungle" and "Smite" in names:
            err.append(f"{label}: Smite on a non-jungler ({role})")

        rin = bd.get("runes") or {}
        ks_in = rin.get("keystone") or {}
        ks = ok_rune(ks_in.get("name"))
        if not ks:
            err.append(f"{label}: unknown/missing keystone '{ks_in.get('name')}'")
        elif ks.get("type") != "Keystone":
            err.append(f"{label}: {ks['name']} is not a keystone")
        primary = rin.get("primaryTree", "")
        if primary not in ("Domination", "Resolve", "Precision", "Sorcery"):
            err.append(f"{label}: bad primaryTree '{primary}'")
        tmins = [x for x in (rune_entry(e, f"{label} minors") for e in rin.get("treeMinors") or []) if x]
        if len(tmins) != 3:
            err.append(f"{label}: {len(tmins)} valid tree minors, need exactly 3")
        if len({t["name"] for t in tmins}) != len(tmins):
            err.append(f"{label}: duplicate tree minor")
        for tm in tmins:
            if primary and tm["tree"] != primary:
                err.append(f"{label}: minor {tm['name']} is {tm['tree']}, not {primary}")
        flex = rune_entry(rin.get("flexMinor") or {}, f"{label} flex") if (rin.get("flexMinor") or {}).get("name") else None
        if not flex:
            err.append(f"{label}: missing flex minor")
        elif flex["name"] in {t["name"] for t in tmins}:
            err.append(f"{label}: flex minor duplicates a tree minor ({flex['name']})")
        return {
            "summary": bd.get("summary", ""),
            "coreBuild": core, "boots": boots, "enchantment": ench, "situational": situ,
            "summoners": sums,
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
            err.append(f"missing variant: {v}")
            continue
        out_builds[v] = val_build(builds_in[v], v)
    notes = [str(n) for n in (rec.get("synergyNotes") or []) if str(n).strip()][:4]
    if not notes:
        warn.append("no synergyNotes")
    return {
        "synergyNotes": notes,
        "damageProfile": rec.get("damageProfile", ""),
        "canOneshot": bool(rec.get("canOneshot", False)),
        "variants": variants,
        "builds": out_builds,
    }, err, warn


REPAIR_ATTEMPTS = 2


class LLM:
    """Thin provider wrapper: deepseek / gemini (cloud) or ollama (local)."""

    def __init__(self, provider: str, model: str):
        self.provider = provider
        self.model = model
        if provider == "gemini":
            from google import genai
            from google.genai import errors as genai_errors
            from google.genai import types
            self._types = types
            self._errors = genai_errors
            self._client = genai.Client()
        elif provider == "deepseek":
            self._key = os.environ.get("DEEPSEEK_API_KEY", "")
            if not self._key:
                raise SystemExit("DEEPSEEK_API_KEY is not set")

    def generate(self, parts: list[str], temperature: float, system: str | None = None) -> str:
        system = system or SYSTEM
        if self.provider == "deepseek":
            # OpenAI-compatible chat completions with JSON mode.
            body = {
                "model": self.model,
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": "\n\n".join(parts)}],
                "response_format": {"type": "json_object"},
                "temperature": temperature,
                "max_tokens": 16000,
                "stream": False,
            }
            headers = {"Authorization": f"Bearer {self._key}"}
            for attempt in range(5):
                try:
                    r = requests.post(DEEPSEEK_URL, json=body, headers=headers, timeout=300)
                    if r.status_code in (429, 500, 502, 503, 504) and attempt < 4:
                        wait = 3 * (attempt + 1)
                        print(f"    … deepseek {r.status_code}, retry in {wait}s")
                        time.sleep(wait)
                        continue
                    if not r.ok:  # 4xx is permanent: surface the body, don't retry
                        raise RuntimeError(f"deepseek {r.status_code}: {r.text[:300]}")
                    return r.json()["choices"][0]["message"]["content"] or ""
                except requests.RequestException as e:
                    if attempt < 4:
                        print(f"    … deepseek error ({e}), retry in 5s")
                        time.sleep(5)
                        continue
                    raise
            return ""
        if self.provider == "gemini":
            config = self._types.GenerateContentConfig(
                system_instruction=system, response_mime_type="application/json",
                temperature=temperature)
            for attempt in range(5):
                try:
                    resp = self._client.models.generate_content(
                        model=self.model, contents=parts, config=config)
                    return resp.text or ""
                except (self._errors.ServerError, self._errors.ClientError) as e:
                    code = getattr(e, "code", None)
                    if code in (429, 500, 502, 503, 504) and attempt < 4:
                        wait = 3 * (attempt + 1)
                        print(f"    … {code}, retry in {wait}s")
                        time.sleep(wait)
                        continue
                    raise
            return ""
        # ollama: single user message, JSON mode. num_ctx must cover our ~14K-token
        # prompt — ollama's default (2048) silently truncates otherwise.
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": "\n\n".join(parts)}],
            "format": "json",
            "stream": False,
            "options": {"temperature": temperature, "num_ctx": 16384},
        }
        for attempt in range(3):
            try:
                r = requests.post(f"{OLLAMA_URL}/api/chat", json=body, timeout=900)
                r.raise_for_status()
                return r.json().get("message", {}).get("content", "")
            except requests.RequestException as e:
                if attempt < 2:
                    print(f"    … ollama error ({e}), retry in 5s")
                    time.sleep(5)
                    continue
                raise
        return ""


JUDGE_SYSTEM = (
    "You are a ruthless Wild Rift build reviewer. You are given a champion's kit, "
    "deterministic KIT FLAGS, and several candidate build sets from theorycrafters. "
    "Per variant, pick the candidate whose build best exploits the kit's synergies "
    "(flags addressed, compounding engines, legal choices; validation errors listed "
    "count heavily against a candidate). Judge the BUILD QUALITY, not the prose."
)


def _judge_prompt(cblock: str, kit_flags: list[str], variants: list[str],
                  cands: list[dict]) -> str:
    flags = "\n".join(f"- {f}" for f in kit_flags) or "(none)"
    blocks = []
    for i, c in enumerate(cands):
        errs = "; ".join(c["err"]) or "none"
        blocks.append(f"--- CANDIDATE {i} (validation errors: {errs}) ---\n"
                      + json.dumps(c["raw"], ensure_ascii=False))
    return (f"{cblock}\n\nKIT FLAGS:\n{flags}\n\n"
            + "\n\n".join(blocks)
            + "\n\nPick the best candidate PER VARIANT and the best synergyNotes. "
            + "Return ONLY this JSON object:\n"
            + '{"picks": {' + ", ".join(f'"{v}": <candidate index>' for v in variants)
            + '}, "synergyFrom": <candidate index>, '
            + '"why": {' + ", ".join(f'"{v}": "<=15 words"' for v in variants) + "}}")


def _assemble(cands: list[dict], picks: dict, synergy_from: int, variants: list[str]) -> dict:
    """Merge the judge's per-variant picks into one raw record."""
    n = len(cands)
    src = cands[synergy_from if 0 <= synergy_from < n else 0]["raw"]
    merged = {
        "synergyNotes": src.get("synergyNotes") or [],
        "damageProfile": src.get("damageProfile", ""),
        "canOneshot": sum(bool(c["raw"].get("canOneshot")) for c in cands) * 2 > n,
        "builds": {},
    }
    for v in variants:
        idx = picks.get(v)
        idx = idx if isinstance(idx, int) and 0 <= idx < n else 0
        chosen = cands[idx]["raw"].get("builds", {}).get(v)
        if chosen is None:  # fall back to any candidate that has the variant
            for c in cands:
                if v in c["raw"].get("builds", {}):
                    chosen = c["raw"]["builds"][v]
                    break
        merged["builds"][v] = chosen or {}
    return merged


def _repair_prompt(raw: dict, errors: list[str]) -> str:
    return (
        "Your previous build JSON has validation errors. Fix EVERY error and return the "
        "FULL corrected JSON in the exact same schema (all variants, not just the broken "
        "parts). Keep everything that was already valid.\n\nERRORS:\n"
        + "\n".join(f"- {e}" for e in errors)
        + "\n\nPREVIOUS JSON:\n" + json.dumps(raw, ensure_ascii=False)
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--provider", choices=("deepseek", "gemini", "ollama"), default="deepseek")
    ap.add_argument("--model", default="", help="defaults per provider")
    ap.add_argument("--best-of", type=int, default=1,
                    help="generate N candidates and judge-pick the best per variant")
    ap.add_argument("--validate-only", action="store_true",
                    help="re-audit data/champion_builds.json offline, no API calls")
    args = ap.parse_args()
    args.model = args.model or DEFAULT_MODELS[args.provider]

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

    def class_role(name: str) -> tuple[str, str]:
        meta = site.get(name)
        if meta:
            return meta.get("class", ""), meta.get("role", "")
        return CLASS_FALLBACK.get(name, ("", ""))

    scales_by_name = {c["name"]: c.get("scalesWith") or [] for c in champs}

    if args.validate_only:
        cache = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
        bad = 0
        for name, rec in sorted(cache.items()):
            _, err, warn = _validate(rec, rec.get("variants") or [], item_by_slug,
                                     rune_by_name, mutex, scales_by_name.get(name),
                                     rec.get("role", ""))
            if err or warn:
                bad += 1 if err else 0
                print(f"  {name}: " + "; ".join(err + [f"(warn) {w}" for w in warn]))
        print(f"\n{len(cache)} champions audited, {bad} with hard errors")
        return

    only = {n.strip() for n in args.only.split(",") if n.strip()}
    if only:
        champs = [c for c in champs if c["name"] in only]

    cache: dict[str, dict] = {}
    if OUT.exists() and not args.fresh:
        cache = json.loads(OUT.read_text(encoding="utf-8"))
    todo = [c for c in champs if only or c["name"] not in cache]
    print(f"{len(champs)} in scope | {len(todo)} to build | {args.provider}:{args.model} "
          f"| best-of {args.best_of}")

    llm = LLM(args.provider, args.model)

    unresolved: list[str] = []
    for i, c in enumerate(todo, 1):
        name = c["name"]
        champ_class, role = class_role(name)
        variants = VARIANT_SETS.get(champ_class, DEFAULT_VARIANTS)
        cblock = _champion_block(c, champ_class or "?", role or "?")
        kit_flags = _kit_hints(c)
        prompt = build_prompt(cblock, item_pool, rune_pool, mutex_block, variants, role, kit_flags)

        def _validated(text):
            raw = _extract_json(text)
            clean, err, warn = _validate(raw, variants, item_by_slug, rune_by_name,
                                         mutex, c.get("scalesWith"), role)
            return raw, clean, err, warn

        # Generate candidate(s). Single-shot at low temperature; best-of at a
        # higher one so the candidates actually differ.
        cands = []
        n = max(1, args.best_of)
        for k in range(n):
            temp = 0.3 if n == 1 else 0.65
            try:
                raw, clean, err, warn = _validated(llm.generate([prompt], temp))
                cands.append({"raw": raw, "clean": clean, "err": err, "warn": warn})
            except Exception as e:  # noqa: BLE001
                print(f"    candidate {k}: parse failed ({e})")
        if not cands:
            print(f"  ! {name}: all candidates failed — skipping")
            unresolved.append(name)
            continue

        if len(cands) > 1:
            # Judge pass picks the best build per variant across candidates.
            # Preferred judge: the deterministic fight engine (kill speed x
            # survivability at the 15-min gold reality). LLM judge is the
            # fallback for champions without extracted formulas.
            picks: dict = {}
            if name in ENGINE_FORMULAS:
                log = []
                for v in variants:
                    best_i, best_s = 0, float("-inf")
                    for k2, cand in enumerate(cands):
                        bd = (cand["clean"].get("builds") or {}).get(v)
                        if not bd or any(e.startswith(v) for e in cand["err"]):
                            continue
                        try:
                            s = score_build(name, bd, v, role)["score"]
                        except Exception:  # noqa: BLE001
                            continue
                        if s > best_s:
                            best_i, best_s = k2, s
                    picks[v] = best_i
                    log.append(f"{v}->c{best_i}({best_s:g})")
                syn_from = max(set(picks.values()), key=list(picks.values()).count)
                raw = _assemble(cands, picks, syn_from, variants)
                print("    engine judge: " + " ".join(log))
            else:
                try:
                    verdict = _extract_json(llm.generate(
                        [_judge_prompt(cblock, kit_flags, variants, cands)], 0.1, JUDGE_SYSTEM))
                    raw = _assemble(cands, verdict.get("picks") or {},
                                    verdict.get("synergyFrom", 0), variants)
                except Exception as e:  # noqa: BLE001
                    print(f"    judge failed ({e}) — falling back to cleanest candidate")
                    raw = min(cands, key=lambda x: len(x["err"]))["raw"]
            clean, err, warn = _validate(raw, variants, item_by_slug, rune_by_name,
                                         mutex, c.get("scalesWith"), role)
        else:
            raw, clean, err, warn = (cands[0]["raw"], cands[0]["clean"],
                                     cands[0]["err"], cands[0]["warn"])

        # Repair loop: hand the errors back and ask for a corrected full JSON.
        rounds = 0
        while err and rounds < REPAIR_ATTEMPTS:
            rounds += 1
            print(f"    repair {rounds}/{REPAIR_ATTEMPTS}: {len(err)} errors — {err[:3]}")
            text = llm.generate([prompt, _repair_prompt(raw, err)], 0.3)
            try:
                raw = _extract_json(text)
            except Exception:  # noqa: BLE001
                break
            clean, err, warn = _validate(raw, variants, item_by_slug, rune_by_name,
                                         mutex, c.get("scalesWith"), role)

        clean["name"] = name
        clean["class"] = champ_class
        clean["role"] = role
        if name in ENGINE_FORMULAS:  # deterministic fight metrics per variant
            for v, bd in (clean.get("builds") or {}).items():
                try:
                    bd["engine"] = score_build(name, bd, v, role)
                except Exception:  # noqa: BLE001
                    pass
        if err:
            clean["errors"] = err  # shipped ONLY for auditing; frontend must skip these
            unresolved.append(name)
        if warn:
            clean["warnings"] = warn
        cache[name] = clean
        payload = json.dumps(cache, ensure_ascii=False, indent=2)
        OUT.write_text(payload, encoding="utf-8")
        WEB_OUT.write_text(payload, encoding="utf-8")  # keep the frontend copy in sync
        flag = f"  ✗ {len(err)} errors" if err else (f"  ⚠ {len(warn)} warnings" if warn else "")
        print(f"  [{i}/{len(todo)}] {name} [{champ_class}/{role}]: {'/'.join(variants)}{flag}")

    print(f"\nwrote {OUT.relative_to(ROOT)} + {WEB_OUT.relative_to(ROOT)} ({len(cache)} champions)")
    if unresolved:
        print(f"UNRESOLVED after repair ({len(unresolved)}): {', '.join(unresolved)}")


if __name__ == "__main__":
    main()
