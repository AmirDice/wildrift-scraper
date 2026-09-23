"""Apply patch 7.3's champion ABILITY changes.

Two files carry an ability: data/champions_wr.json holds the tooltip text the
site prints and the advisor reads, and data/ability_formulas.json holds the
structured numbers the two fight engines simulate. A change has to land in
both, or the page and the damage number disagree.

HOW IT WORKS

    Every "Label: old -> new" line in the notes is read from the parse and
    matched against what we hold, in this order:

      1. a base damage sequence in the formulas ("50 / 85 / 120 / 155")
      2. the same sequence in the tooltip text
      3. a cooldown sequence, in both places
      4. a single ratio ("135% Attack Damage") in the formulas
      5. a single number or percentage in the tooltip text, and only when it
         appears there exactly once

    A line that matches nothing is REPORTED, never skipped quietly. The
    report is the work list: everything on it is either a rework that needs
    prose (see TEXT_EDITS) or a mechanic the formula schema cannot express,
    which is recorded in the ability's `unmodeled` notes instead of being
    silently dropped.

WHAT 7.3 ASKS FOR THAT THE SCHEMA CANNOT SAY

    Several abilities now scale with Critical Rate and Critical Damage --
    Caitlyn's Headshot, Xayah's Bladecaller, Ashe's Frost Shot, Sivir's
    Boomerang Blade, Tristana's Explosive Charge and others. `ratios` carries
    stats the engine knows (ad, ap, maxHp...), and crit is not one of them: it
    is a multiplier on an attack, not a stat an ability scales off. Those lines
    go into `unmodeled` with their exact wording, so the text is right, the
    engine keeps the pre-patch shape of the ability, and the gap is written
    down rather than guessed at.

Run:
    python -m scripts.apply_patch_7_3_abilities
    python -m scripts.apply_patch_7_3_abilities --write
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PATCH = "7.3"

CHAMPIONS = DATA / "champions_wr.json"
FORMULAS = DATA / "ability_formulas.json"
NOTES = DATA / "patch_notes_7_3.json"

#: Notes wording -> the stat key formulas use for a ratio.
RATIO_STATS = {
    "attack damage": "ad",
    "bonus attack damage": "ad",
    "ability power": "ap",
    "maximum health": "maxHp",
    "max health": "maxHp",
    "target's max health": "targetMaxHp",
    "target missing health": "targetMissingHp",
    "bonus health": "bonusHp",
    "armor": "armor",
}


#: Tooltip rewrites the matchers above cannot do: a mechanic that was added,
#: removed or replaced rather than renumbered. (champion, ability, old, new),
#: and an entry whose `old` is not in the tooltip fails the run rather than
#: passing silently.
#:
#: These are the changes a player would notice, so the page has to say them
#: even though the scrape will eventually catch up on its own. The rest of the
#: unmatched lines are recorded in each ability's `unmodeled` notes.
TEXT_EDITS = [
    ("Tristana", "Rocket Jump",
     "85 /155 / 225 / 295 ( +50% AP )",
     "80 / 120 / 160 / 200 ( +80% bonus AD +50% AP )"),
    ("Tristana", "Rocket Jump", "for 1.5 / 2 / 2.5 / 3 seconds", "for 2 seconds"),

    # Twitch's rework: the attack speed moved from Deadly Venom's full stacks
    # to leaving camouflage, and Contaminate's Ability Power half became magic
    # damage with a range requirement.
    ("Twitch", "Ambush",
     "After exiting Camouflage , Twitch's attacks will apply an additional stack of "
     "Deadly Venom for 3 seconds.",
     "After exiting Camouflage , Twitch gains 35% / 40% / 45% / 50% bonus Attack Speed "
     "for 6 seconds."),
    ("Twitch", "Deadly Venom",
     "When an enemy champion has full stacks of Deadly Venom, Twitch gains 30% / 35% / "
     "40% / 45% / 50% attack speed for 5 seconds. ", ""),
    ("Twitch", "Venom Cask", "( +6% bonus )", "( +0.06% AP )"),
    ("Twitch", "Contaminate",
     "each stack deals 20 / 25 / 30 / 35 ( +35% bonus AD +18% AP ) damage to enemies.",
     "each stack deals 20 / 25 / 30 / 35 ( +35% bonus AD ) physical damage and ( +35% AP ) "
     "magic damage. Contaminate can only be cast while a poisoned target is within 1200 "
     "units of Twitch."),

    ("Lucian", "The Culling",
     "Fires a total of 22 / 26 / 30 bullets.",
     "Fires 20 bullets, plus 2 more for every 10% Critical Rate and more again for "
     "Critical Damage above 200%."),

    ("Caitlyn", "Headshot",
     "dealing 27 ( 60% AD + 200 Critical chance ) bonus physical damage",
     "dealing ( 60% - 100% AD + 100% x Critical Rate, and more for Critical Damage above "
     "200% ) bonus physical damage"),
    ("Caitlyn", "Yordle Snap Trap",
     "Trap charging time: 25 / 20 / 15 / 10 seconds.",
     "Trap charging time: 25 / 20 / 15 / 10 seconds. Headshots against trapped enemies "
     "deal 40 / 90 / 140 / 190 ( +30% bonus AD ) bonus physical damage."),

    ("Jhin", "Whisper",
     "Attack Damage scales with Critical Rate and bonus Attack Speed.",
     "Attack Damage scales with Critical Rate and bonus Attack Speed. Jhin's critical "
     "strikes deal 80% of normal critical strike damage."),

    ("Graves", "New Destiny", "Critical strikes fire 6 bullets, 130% damage each",
     "Critical strikes fire 6 bullets, 150% damage each"),

    ("Senna", "Absolution", "dealing 1% of their current health as bonus physical damage",
     "dealing 1% - 10% (based on level) of their current Health as bonus physical damage"),

    # Tryndamere: Bloodlust' flat attack damage is gone entirely, and Battle
    # Fury lost its attack speed steroid.
    ("Tryndamere", "Bloodlust",
     "Gains 7 / 12 / 17 / 22 Attack Damage plus an additional",
     "Gains an additional"),
    ("Tryndamere", "Battle Fury",
     "Attacking a champion grants 30% Attack Speed for 5 seconds. (6 second cooldown) ", ""),
    ("Tryndamere", "Battle Fury",
     "Battle Fury's Attack Speed bonus increases with Undying Rage's ability rank. ", ""),
    ("Tryndamere", "Undying Rage",
     "Passive : Increases Battle Fury's bonus Attack Speed to 45% / 60% / 75% . ", ""),

    # The jungle rework took the monster damage modifiers off these three.
    ("Zed", "Razor Shuriken", " Deals 80% damage to monsters.", ""),
    ("Zed", "Shadow Slash", " Deals 60% damage to monsters.", ""),
    ("Nunu & Willump", "Snowball Barrage", " Deals 150% damage to monsters.", ""),
]


# Removed mechanics need a postcondition as well as an exact rewrite. An empty
# replacement cannot prove idempotence: the old scrape may use different prose
# (the Tryndamere bug this guard was added for), and treating every missing
# exact phrase as success lets that stale variant ship indefinitely.
REMOVED_TEXT_FORBIDDEN = {
    "Twitch": (
        "full stacks of Deadly Venom, Twitch gains",
        "attacks apply an additional stack of Deadly Venom",
    ),
    "Tryndamere": (
        "Attacking a champion grants 30% Attack Speed",
        "Landing a basic attack on an enemy champion grants 30% Attack Speed",
        "Increases Battle Fury's bonus Attack Speed",
        "Battle Fury's Attack Speed bonus increases",
    ),
    "Nunu & Willump": ("Deals 150% damage to monsters",),
    "Zed": ("Deals 80% damage to monsters", "Deals 60% damage to monsters"),
}


def key_of(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").lower().replace("’", "'")
    return re.sub(r"[^a-z0-9]", "", text)


def numbers(text: str) -> list[float]:
    return [float(x) for x in re.findall(r"(?<![\w.])(\d+(?:\.\d+)?)", text or "")]


def head_numbers(side: str) -> list[float]:
    """The base sequence: the numbers before the first ratio or bracket."""
    return numbers(re.split(r"[+(]", side, 1)[0])


def as_list(value) -> list:
    """A field that is sometimes a number, sometimes a list, sometimes a
    {lvlRange: [...]} -- as a plain list of numbers."""
    if isinstance(value, dict):
        value = value.get("lvlRange") or []
    if not isinstance(value, list):
        value = [value]
    return value


def same(seq_a, seq_b) -> bool:
    a = [float(x) for x in as_list(seq_a) if isinstance(x, (int, float))]
    b = [float(x) for x in as_list(seq_b) if isinstance(x, (int, float))]
    return bool(a) and a == b


def text_variants(nums: list[float]) -> list[str]:
    """Every way wr-meta writes one sequence of numbers.

    The scrape is not consistent: per-rank values appear as "10 / 40 / 70",
    "10/40/70" and with percent signs on each rank, and a level range appears
    as both "31-45" and "31 - 45".
    """
    body = [f"{n:g}" for n in nums]
    pct = [f"{n:g}%" for n in nums]
    out = [" / ".join(body), "/".join(body), " /".join(body), "/ ".join(body),
           " / ".join(pct), "/".join(pct)]
    if len(nums) == 2:
        out += [f"{body[0]}-{body[1]}", f"{body[0]} - {body[1]}",
                f"{pct[0]}-{pct[1]}", f"{pct[0]} - {pct[1]}"]
    return out


def apply_removed_mechanics(formulas: dict) -> int:
    """Remove 7.3 mechanics whose notes have no ``old → new`` numeric shape.

    The generic matcher can rewrite numbers, but a deletion must also remove
    the structured steroid/note or the fight engine continues simulating it
    after the champion page looks correct. Keep this idempotent so a later
    scrape can safely be reconciled again.
    """
    changed = 0

    tryn = formulas["Tryndamere"]["abilities"]
    for slot in ("P", "1", "4"):
        if tryn[slot].get("steroids"):
            tryn[slot]["steroids"] = []
            changed += 1
    tryn["1"]["unmodeled"] = [
        "Active consumes all fury to heal",
        "Passive grants 0.3/0.5/0.7/0.9 Attack Damage per 1% missing Health; "
        "its non-linear runtime value is not modeled.",
    ]
    tryn["2"]["unmodeled"] = [
        "Reduces nearby enemy AD by 20/40/60/80% for 3s; if moving away, "
        "slows by 25/30/35/40% for 3s",
    ]

    twitch = formulas["Twitch"]["abilities"]
    if twitch["P"].get("steroids"):
        twitch["P"]["steroids"] = []
        changed += 1
    wanted_as = {
        "stat": "attackSpeed", "pct": [35, 40, 45, 50],
        "durationS": 6, "note": "after leaving camouflage",
    }
    ambush_steroids = [s for s in twitch["1"].get("steroids") or []
                       if s.get("stat") != "attackSpeed"]
    ambush_steroids.append(wanted_as)
    if twitch["1"].get("steroids") != ambush_steroids:
        twitch["1"]["steroids"] = ambush_steroids
        changed += 1
    twitch["1"]["unmodeled"] = [
        note for note in twitch["1"].get("unmodeled") or []
        if "additional stack of Deadly Venom" not in note
    ]
    for note in twitch["2"].get("unmodeled") or []:
        if "+6% bonus AD" in note:
            twitch["2"]["unmodeled"] = [
                n.replace("+6% bonus AD", "+0.06% AP")
                for n in twitch["2"]["unmodeled"]
            ]
            changed += 1
            break
    damage = twitch["3"].get("damage") or []
    per_stack = next((d for d in damage if d.get("name") == "Contaminate Per Stack"), None)
    if per_stack:
        per_stack["ratios"] = [{"stat": "bonusAd", "pct": 35}]
    magic = {
        "name": "Contaminate Magic Per Stack", "type": "magic", "base": 0,
        "ratios": [{"stat": "ap", "pct": 35}], "hits": 5,
    }
    existing_magic = next((d for d in damage if d.get("name") == magic["name"]), None)
    if existing_magic:
        existing_magic.update(magic)
    else:
        insert_at = damage.index(per_stack) + 1 if per_stack in damage else len(damage)
        damage.insert(insert_at, magic)
        changed += 1

    stale_notes = {
        "Nunu & Willump": {"3": ("Deals 150% damage to monsters",)},
        "Zed": {
            "1": ("Deals 80% damage to monsters",),
            "3": ("Deals 60% damage to monsters",),
        },
    }
    for champion, slots in stale_notes.items():
        for slot, phrases in slots.items():
            ability = formulas[champion]["abilities"][slot]
            before = ability.get("unmodeled") or []
            after = []
            for note in before:
                cleaned = note
                for phrase in phrases:
                    cleaned = cleaned.replace(f" {phrase}.", "").replace(phrase + ".", "")
                    cleaned = cleaned.replace(phrase, "")
                if cleaned.strip():
                    after.append(cleaned.strip())
            if before != after:
                ability["unmodeled"] = after
                changed += 1
    return changed


class Apply:
    """One champion's two records, and the edits made to them."""

    def __init__(self, name: str, champ: dict, formulas: dict):
        self.name = name
        self.champ = champ
        self.formulas = formulas
        self.done: list[str] = []
        self.todo: list[str] = []
        self.drift: list[str] = []

    def ability_text(self, title: str) -> dict | None:
        for ability in self.champ.get("abilities") or []:
            if key_of(ability.get("name")) == key_of(title):
                return ability
        return None

    def ability_formula(self, title: str) -> dict | None:
        for ability in (self.formulas.get("abilities") or {}).values():
            if key_of(ability.get("name")) == key_of(title):
                return ability
        return None

    # -- the matchers ------------------------------------------------------
    def base_in_formula(self, ability: dict | None, old: list[float], new: list[float]) -> bool:
        if not ability or not old or len(old) != len(new):
            return False
        hit = False
        for group in ("damage", "defensive", "steroids"):
            for part in ability.get(group) or []:
                if not isinstance(part, dict):
                    continue
                for field in ("base", "flat"):
                    if same(part.get(field) or [], old):
                        part[field] = list(new)
                        hit = True
        return hit

    def base_in_text(self, ability: dict | None, old: list[float], new: list[float]) -> bool:
        if not ability or len(old) < 2 or len(old) != len(new):
            return False
        text = ability.get("text") or ""
        for want, repl in zip(text_variants(old), text_variants(new)):
            if text.count(want) == 1:
                ability["text"] = text.replace(want, repl, 1)
                return True
        return False

    def cooldowns(self, title: str, old: list[float], new: list[float]) -> bool:
        """Cooldowns are stored as arrays in both files.

        The pre-patch value is checked, but a mismatch does not stop the write:
        wr-meta rounds and sometimes lags, and Ezreal is the live example --
        the notes say Mystic Shot was 4.5/4/3.5/3 and we hold 4/4/3/3. The
        post-patch value is unambiguous either way, so it is written and the
        disagreement is reported.
        """
        if len(old) != len(new):
            return False
        hit = False
        ability = self.ability_formula(title)
        if ability and ability.get("cooldowns") and len(ability["cooldowns"]) == len(new):
            if not same(ability["cooldowns"], old):
                self.drift.append(f"{title} cooldowns: notes say "
                                  f'{"/".join(f"{n:g}" for n in old)}, we hold '
                                  f'{"/".join(f"{float(c):g}" for c in ability["cooldowns"])}')
            ability["cooldowns"] = list(new)
            hit = True
        text = self.ability_text(title)
        if text and text.get("cooldowns") and len(text["cooldowns"]) == len(new):
            text["cooldowns"] = [f"{n:g}" for n in new]
            hit = True
        return hit

    def ratio_in_formula(self, ability: dict | None, old_side: str, new_side: str) -> bool:
        """"135% Attack Damage -> 150% Attack Damage", including per-rank lists."""
        if not ability:
            return False
        pairs_old = re.findall(r"([\d.\s/]+)%\s*(?:x\s*)?(?:bonus\s+)?([A-Za-z' ]+)", old_side)
        pairs_new = re.findall(r"([\d.\s/]+)%\s*(?:x\s*)?(?:bonus\s+)?([A-Za-z' ]+)", new_side)
        hit = False
        for (raw_old, stat_old), (raw_new, stat_new) in zip(pairs_old, pairs_new):
            stat = RATIO_STATS.get(stat_old.strip().lower())
            if not stat or stat != RATIO_STATS.get(stat_new.strip().lower()):
                continue
            old_nums, new_nums = numbers(raw_old), numbers(raw_new)
            if not old_nums or not new_nums:
                continue
            for group in ("damage", "defensive"):
                for part in ability.get(group) or []:
                    for ratio in part.get("ratios") or []:
                        if ratio.get("stat") != stat:
                            continue
                        have = ratio.get("pct")
                        have_list = have if isinstance(have, list) else [have]
                        if same(have_list, old_nums):
                            ratio["pct"] = new_nums[0] if len(new_nums) == 1 else list(new_nums)
                            hit = True
        return hit

    def ratio_by_value(self, ability: dict | None, old_nums: list[float], new_nums: list[float]) -> bool:
        """A ratio the notes name only in the label.

        "True Damage based on Maximum Health: 2 / 5 / 8 / 11% -> 6 / 7 / 8 / 9%"
        never says the stat beside the number, so the stat cannot be matched --
        but the VALUE can, and only when exactly one ratio in the ability holds
        it. One match is a fact; two would be a guess.
        """
        if not ability or not old_nums or len(old_nums) != len(new_nums) or old_nums == new_nums:
            return False
        found = []
        for group in ("damage", "defensive", "steroids"):
            for part in ability.get(group) or []:
                if not isinstance(part, dict):
                    continue
                for ratio in part.get("ratios") or []:
                    if same(ratio.get("pct"), old_nums):
                        found.append(ratio)
                if same(part.get("pct"), old_nums):
                    found.append(part)
        if len(found) != 1:
            return False
        found[0]["pct"] = new_nums[0] if len(new_nums) == 1 else list(new_nums)
        return True

    def ratio_in_text(self, ability: dict | None, old_side: str, new_side: str) -> bool:
        """"+135% AD" in the tooltip, when the notes move a ratio.

        wr-meta writes ratios as "( +135% AD )" or "( +75% / 80% AD )", so the
        numbers are matched and the stat word is left alone -- the notes say
        "bonus Attack Damage" where the scrape says "AD" and rewriting that
        would change the tooltip's voice for no gain.
        """
        if not ability:
            return False
        pairs_old = re.findall(r"([\d.\s/]+)%\s*(?:x\s*)?(?:bonus\s+)?([A-Za-z' ]+)", old_side)
        pairs_new = re.findall(r"([\d.\s/]+)%\s*(?:x\s*)?(?:bonus\s+)?([A-Za-z' ]+)", new_side)
        text = ability.get("text") or ""
        hit = False
        for (raw_old, stat_old), (raw_new, stat_new) in zip(pairs_old, pairs_new):
            if RATIO_STATS.get(stat_old.strip().lower()) != RATIO_STATS.get(stat_new.strip().lower()):
                continue
            old_nums, new_nums = numbers(raw_old), numbers(raw_new)
            if not old_nums or not new_nums or old_nums == new_nums:
                continue
            for want, repl in zip(text_variants(old_nums), text_variants(new_nums)):
                if text.count(f"{want}%") == 1:
                    text = text.replace(f"{want}%", f"{repl}%", 1)
                    hit = True
                    break
                if text.count(want) == 1 and "%" in want:
                    text = text.replace(want, repl, 1)
                    hit = True
                    break
        if hit:
            ability["text"] = text
        return hit

    def single_in_text(self, ability: dict | None, old_side: str, new_side: str) -> bool:
        """A lone number or percentage, replaced only when the tooltip says it
        exactly once -- two matches means we cannot tell which one moved."""
        if not ability:
            return False
        old_nums, new_nums = numbers(old_side), numbers(new_side)
        if len(old_nums) != 1 or len(new_nums) != 1:
            return False
        text = ability.get("text") or ""
        old_pct = "%" in old_side
        token = f"{old_nums[0]:g}%" if old_pct else f"{old_nums[0]:g}"
        repl = f"{new_nums[0]:g}%" if old_pct else f"{new_nums[0]:g}"
        if not old_pct:
            # A bare number must stand alone, or "5" rewrites the 5 in "15".
            hits = len(re.findall(rf"(?<![\w.]){re.escape(token)}(?![\w.%])", text))
            if hits != 1:
                return False
            ability["text"] = re.sub(rf"(?<![\w.]){re.escape(token)}(?![\w.%])", repl, text, count=1)
            return True
        if text.count(token) != 1:
            return False
        ability["text"] = text.replace(token, repl, 1)
        return True

    def note_unmodeled(self, title: str, line: str) -> None:
        ability = self.ability_formula(title)
        if ability is None:
            return
        note = f"7.3: {line}"
        notes = ability.setdefault("unmodeled", [])
        if note not in notes:
            notes.append(note)

    # -- the driver --------------------------------------------------------
    def line(self, title: str, raw: str) -> None:
        if "→" not in raw:
            self.todo.append(f"{title}: {raw}")
            return
        label, _, rest = raw.partition(":")
        if not rest:
            label, rest = "", raw
        old_side, new_side = [s.strip() for s in rest.split("→")[:2]]
        text = self.ability_text(title)
        formula = self.ability_formula(title)
        is_cd = "cooldown" in label.lower()
        old_nums, new_nums = head_numbers(old_side), head_numbers(new_side)

        # The verdict is whether anything actually MOVED, not whether a
        # matcher fired: several 7.3 lines restate a number that did not
        # change (Kai'Sa's Supercharge keeps 50/55/60/65 and rewrites what it
        # multiplies), and counting those as applied would hide the real work.
        before = json.dumps([self.champ, self.formulas], sort_keys=True)
        if is_cd:
            self.cooldowns(title, numbers(old_side), numbers(new_side))
        if not is_cd:
            # Base and ratios are tried independently: most damage lines move
            # BOTH ("20 / 35 / 50 / 65 + 115% AD" to "70 / 110 / 150 / 190 +
            # 100% bonus AD"), and stopping at the first hit left the old
            # ratio in place next to the new base.
            self.base_in_formula(formula, old_nums, new_nums)
            self.base_in_text(text, old_nums, new_nums)
            self.ratio_in_formula(formula, old_side, new_side)
            self.ratio_in_text(text, old_side, new_side)
            if "%" in old_side and "%" in new_side:
                self.ratio_by_value(formula, head_numbers(old_side), head_numbers(new_side))
        if before == json.dumps([self.champ, self.formulas], sort_keys=True):
            self.single_in_text(text, old_side, new_side)
        moved = before != json.dumps([self.champ, self.formulas], sort_keys=True)
        if not moved:
            # Written into the ability rather than left in a console log: the
            # engine keeps simulating the pre-patch shape either way, and a
            # note in the data is the only version of that fact anyone will
            # find later. Base-stat rows that the notes filed under an ability
            # (Senna's attack speed sits under Absolution) belong to
            # apply_patch_7_3_champion_stats and are not ability notes.
            if not re.match(r"^(attack speed|base attack speed|base bonus attack speed"
                            r"|attack speed ratio|attack speed per level|mana cost)\b",
                            label.strip().lower()):
                self.note_unmodeled(title, raw)
        (self.done if moved else self.todo).append(f"{title}: {raw}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--champion", help="only this one, for working through the list")
    args = ap.parse_args()

    notes = json.loads(NOTES.read_text(encoding="utf-8"))
    champions = json.loads(CHAMPIONS.read_text(encoding="utf-8"))
    formulas = json.loads(FORMULAS.read_text(encoding="utf-8"))
    by_key = {key_of(c["name"]): c for c in champions}

    # The scrape carries non-breaking spaces inside number runs ("Gains
    # 7 / 12 / 17 / 22"), which are invisible on the page and defeat every
    # match here. Normalised once for the whole roster, since the next scrape
    # will reintroduce them and this is where they are noticed.
    for champ in champions:
        for ability in champ.get("abilities") or []:
            if ability.get("text"):
                ability["text"] = re.sub(r"\s{2,}", " ", ability["text"].replace(" ", " "))

    done = todo = 0
    for blade in notes["blades"]:
        if blade["kind"] != "champion":
            continue
        champ = by_key.get(key_of(blade["champion"]))
        if champ is None:
            continue
        if args.champion and key_of(args.champion) != key_of(champ["name"]):
            continue
        work = Apply(champ["name"], champ, formulas.get(champ["name"]) or {})
        for block in blade["blocks"]:
            if block["title"] == "Base Stats":
                continue
            for line in block["lines"]:
                work.line(block["title"], line)
        if work.done or work.todo:
            print(f'=== {champ["name"]}  ({len(work.done)} applied, {len(work.todo)} left)')
            for line in work.done:
                print(f"  ok   {line[:150]}")
            for line in work.drift:
                print(f"  drift {line[:150]}")
            for line in work.todo:
                print(f"  TODO {line[:150]}")
        done += len(work.done)
        todo += len(work.todo)

    # -- the hand-written rewrites
    rewritten = 0
    for champ_name, ability_name, before_text, after_text in TEXT_EDITS:
        champ = by_key.get(key_of(champ_name))
        if champ is None:
            print(f"TEXT EDIT: no champion {champ_name}")
            return 1
        ability = next((a for a in champ.get("abilities") or []
                        if key_of(a.get("name")) == key_of(ability_name)), None)
        if ability is None:
            print(f"TEXT EDIT: {champ_name} has no ability {ability_name}")
            return 1
        text = ability.get("text") or ""
        if before_text not in text:
            if after_text and after_text in text:
                continue                       # already applied
            if not after_text:
                continue                       # verified by the postcondition below
            print(f"TEXT EDIT: {champ_name} {ability_name} does not contain {before_text[:60]!r}")
            return 1
        ability["text"] = re.sub(r"\s{2,}", " ", text.replace(before_text, after_text, 1)).strip()
        rewritten += 1

    for champ_name, phrases in REMOVED_TEXT_FORBIDDEN.items():
        champ = by_key[key_of(champ_name)]
        text = " ".join(a.get("text") or "" for a in champ.get("abilities") or [])
        stale = [phrase for phrase in phrases if phrase in text]
        if stale:
            print(f"REMOVED TEXT STILL PRESENT: {champ_name}: {stale}")
            return 1

    removed_formula_edits = apply_removed_mechanics(formulas)

    print(f"\n{done} lines applied, {rewritten} tooltips rewritten by hand, "
          f"{removed_formula_edits} removed-mechanic formula edits, "
          f"{todo} recorded as notes")
    if args.write:
        CHAMPIONS.write_text(json.dumps(champions, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        FORMULAS.write_text(json.dumps(formulas, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("wrote champions_wr.json, ability_formulas.json")
    else:
        print("dry run: pass --write to save")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
