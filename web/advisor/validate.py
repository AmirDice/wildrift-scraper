"""Deterministic validation of the model's build.

This is the half of the system that does not reason. The model decides what is
strategically best; this decides whether what it returned is legal, complete and
internally consistent. Nothing here scores a build or prefers one item to
another -- the moment it does, the system has two opinions about strategy and no
way to reconcile them.

Every check returns a message written for two readers: a human reading a log,
and the repair prompt, which gets handed the message verbatim. So each one names
the offending value and the rule it broke, rather than reporting that something
is invalid.

Errors are grouped by SECTION so a failure in the rune page can be repaired
without regenerating the item build. See repair.py for how that is used.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from web.advisor import itemmeta, runemeta

ITEMS = itemmeta.ITEMS

# Sections a repair can target independently. Ordering matters only for display.
# `summoners` is absent even though the model now picks them. They are not
# validated-then-repaired like the rest: summoners.enforce() imposes the jungle
# rules on the answer directly, and anything it cannot use falls back to the
# rule table. A summoner spell is never worth a repair round-trip, and never
# worth failing a build that has five correct items in it.
SECTIONS = ("items", "boots", "runes", "situational",
            "situationalRunes", "snowball", "scores", "counterSummary",
            "playGuide", "locks")


@dataclass
class Report:
    """Errors that make a build unusable, and warnings that merely need saying."""
    errors: dict[str, list[str]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def fail(self, section: str, message: str) -> None:
        self.errors.setdefault(section, []).append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    @property
    def ok(self) -> bool:
        return not self.errors

    def flat(self) -> list[str]:
        return [m for section in SECTIONS for m in self.errors.get(section, [])]

    def sections(self) -> list[str]:
        return [s for s in SECTIONS if self.errors.get(s)]


DEFENSIVE_BOOTS = {"mercurys-treads", "plated-steelcaps"}
OFFENSE_FIRST_CLASSES = {"Bruiser", "Marksman", "Assassin"}

_SCORE_KEYS = ("overall", "burst", "sustainedDamage", "survivability",
               "mobility", "utility", "earlyPower", "confidence")


def _completed_non_boots(slug: str | None) -> bool:
    if not slug:
        return False
    item = ITEMS.get(slug) or {}
    return (item.get("category") != "Boots"
            and not (set(item.get("categories") or []) & {"Basic", "MidTier"}))


def hard_exclusive_violation(slugs: list[str]) -> str | None:
    """Two items from a group the game will not let you equip together -- a
    mutex group, or more than one active item (Wild Rift allows only one)."""
    for name, members in itemmeta.HARD_EXCLUSIVE.items():
        hit = [s for s in slugs if s in members]
        if len(hit) > 1:
            return (f"hard exclusivity ({name}): {hit} cannot be equipped together in-game "
                    f"-- keep exactly one and replace the other")
    actives = itemmeta.active_items_in(slugs)
    if len(actives) > 1:
        return (f"only ONE active item is allowed in a build; {actives} are all active items "
                "-- keep one and replace the rest with non-active items")
    return None


def redundancy_notes(slugs: list[str]) -> list[str]:
    """Overlaps that are legal but usually wasteful. Warnings, never errors."""
    notes = []
    for name, group in itemmeta.REDUNDANCY.items():
        hit = [s for s in slugs if s in group.get("slugs", [])]
        if len(hit) > 1:
            notes.append(f"redundancy ({name}): {hit} overlap. {group.get('why', '')}")
    return notes


def _resulting_order(
    report: Report, section: str, label: str, order: list, must_contain: str,
    at_position: int | None, must_not_contain: str | None, resolve,
) -> list[str] | None:
    """Validate a proposed five-item build produced by a swap.

    The old schema only asked which item replaced which, which cannot express
    the common real adaptation: buy the answer EARLY and push everything back.
    The cost of the richer schema is that the resulting build has to be checked
    as a build, which is what this does.
    """
    if not isinstance(order, list):
        report.fail(section, f"{label}: resultingOrder must be a list of 5 item slugs")
        return None
    resolved = [resolve(s) for s in order]
    if len(resolved) != 5 or not all(_completed_non_boots(s) for s in resolved):
        report.fail(section, f"{label}: resultingOrder must be exactly 5 known, completed, "
                             f"non-boots item slugs, got {order}")
        return None
    if len(set(resolved)) != 5:
        report.fail(section, f"{label}: resultingOrder repeats an item: {order}")
        return None
    if must_contain and must_contain not in resolved:
        report.fail(section, f"{label}: resultingOrder must contain {must_contain}, the item "
                             f"being brought in; got {resolved}")
        return None
    if at_position and must_contain:
        actual = resolved.index(must_contain) + 1
        if actual != at_position:
            report.fail(section, f"{label}: {must_contain} is placed at position {actual} in "
                                 f"resultingOrder but the entry says position {at_position}; "
                                 "the two must agree")
            return None
    if must_not_contain and must_not_contain in resolved:
        report.fail(section, f"{label}: resultingOrder still contains {must_not_contain}, "
                             "which this swap removes")
        return None
    violation = hard_exclusive_violation(resolved)
    if violation:
        report.fail(section, f"{label}: the resulting build is illegal -- {violation}")
        return None
    return resolved


def _named_rune(reason: str) -> str | None:
    """The rune a reason line is about, when it says so.

    Reasons come back self-labelled, as "Eyeball Collector: scales AD from
    takedowns" or "Electrocute procs easily with W-auto-Q". The name is the
    lead, so only the start of the line is considered: a reason for Sudden
    Impact that happens to mention Electrocute later is still about Sudden
    Impact.
    """
    head = (reason or "").split(":", 1)[0]
    # Longest first, so "Ultimate Hunter" is not matched as "Hunter".
    for name in sorted(runemeta.SLOT_OF, key=len, reverse=True):
        if head.lower().startswith(name.lower()):
            return name
    direct = runemeta.resolve(head.strip())
    return direct


def _realign_rune_reasons(res: dict, page: dict, report: Report) -> None:
    """Attach each rune's reason to THAT rune, rather than to its position.

    The two lists are zipped by index downstream, so one reason written for a
    rune that did not make the final page shifts every reason after it. That
    shipped: a Pantheon page showed Hubris explained as "Eyeball Collector:
    scales AD from takedowns" and Eyeball Collector explained as "Relentless
    Hunter: out-of-combat movement speed", a rune not in the build at all.

    Re-keying by the name each reason gives is deterministic and free, where
    failing the section would cost another model round trip to fix wording that
    is already correct -- it is only attached to the wrong rune.
    """
    reasons = res.get("runeReasons")
    if not isinstance(reasons, dict):
        return

    minors = list(page.get("minors") or [])
    given = list(reasons.get("minors") or [])
    if not minors or not given:
        return

    by_rune: dict[str, str] = {}
    unlabelled: list[str] = []
    for reason in given:
        if not isinstance(reason, str):
            continue
        named = _named_rune(reason)
        if named and named in minors and named not in by_rune:
            by_rune[named] = reason
        elif named:
            # Names a rune that is not in this page: it explains a choice that
            # was not made, so it cannot be shown against any of them.
            continue
        else:
            unlabelled.append(reason)

    if not by_rune:
        return  # nothing self-labelled; leave the model's order alone

    spare = iter(unlabelled)
    realigned = [by_rune.get(m) or next(spare, "") for m in minors]
    if realigned != given:
        report.warn("runeReasons were attached to the wrong runes and have been "
                    "realigned to the runes they name")
    reasons["minors"] = realigned


def identity_violations(slugs: list[str], identity: dict | None) -> list[str]:
    """Hard meta-identity lint: items whose defining stat the champion's
    curated identity card marks as never-build.

    Deliberately contained to stats an item cannot carry incidentally -- crit,
    Magic-category AP, lethality, heal/shield power. Stats like attack speed or
    mana ride along on hybrid items (Trinity Force) and are the PROMPT's job to
    keep in line, because failing them here would reject correct builds. This
    check exists for the stochastic tail: the one-in-N build that drifts into
    an archetype nobody builds on this champion."""
    if not identity:
        return []
    avoid = set(identity.get("avoidStats") or [])
    if not avoid:
        return []
    out: list[str] = []
    for slug in slugs:
        item = ITEMS.get(slug) or {}
        stats = item.get("stats") or {}
        hit = None
        if "crit" in avoid and "crit" in stats \
                and "physicalPen" not in stats and "physicalPenFlat" not in stats:
            # pen items carrying crit (Mortal Reminder, LDR) are bought for
            # the pen/anti-heal by no-crit champions; 14% of ladder Aatrox
            # carry Mortal Reminder inside strictly critless builds
            hit = "crit"
        elif "ap" in avoid and "ap" in stats and item.get("category") == "Magic":
            hit = "ap"
        elif "lethality" in avoid and "physicalPenFlat" in stats and "crit" not in stats:
            # crit items carrying lethality (The Collector) belong to crit
            # builds; 12% of ladder Vaynes buy it inside a no-lethality kit
            hit = "lethality"
        elif ("healing_power" in avoid or "shield_power" in avoid) and "healShieldPower" in stats:
            hit = "healing/shield power"
        if hit:
            out.append(f"{slug} is a {hit} item, and this champion's meta identity marks "
                       f"{hit} as never-build; replace it with an item from an approved "
                       "archetype in the META ITEMIZATION IDENTITY block")
    return out


def validate(
    res: dict,
    *,
    champion_class: str = "",
    role: str = "",
    mode: str = "studio",
    enemies_known: bool = False,
    damage_path: str = "standard",
    required_audit_items: list[str] | None = None,
    allowed_items: list[str] | None = None,
    item_locks: list[str] | None = None,
    boot_lock: str = "",
    rune_locks: list[str] | None = None,
    resolve_item=None,
    resolve_summoner=None,
    summoner_icons: dict | None = None,
    identity: dict | None = None,
    ladder_core: list[str] | None = None,
) -> Report:
    """Check and normalise the model's build in place. Returns a Report."""
    report = Report()
    resolve = resolve_item or (lambda s: s if s in ITEMS else None)
    allowed = set(allowed_items) if allowed_items else None

    # Counter mode answers a known comp in the main build itself, so reactive
    # swaps on top are contradictory advice rather than extra value. It also
    # skips the slower explanation fields (see buildScore below) for speed.
    if mode == "counter":
        res["situational"] = []
        res["situationalRunes"] = []
        res.pop("bootsReason", None)
        res.pop("runeReasons", None)
        # The counter summary replaces the build evaluation. Require it to carry
        # the two things that make it useful: what problems were chosen, and how
        # they were answered. Missing pieces are a repairable counterSummary
        # failure, not a whole-build failure.
        summary = res.get("counterSummary")
        if not isinstance(summary, dict):
            report.fail("counterSummary", "counter mode must return a counterSummary object")
        else:
            if not (summary.get("counterPriorities") or []):
                report.fail("counterSummary",
                            "counterSummary.counterPriorities must name the 2-4 problems chosen")
            if not (summary.get("threatResponses") or []):
                report.fail("counterSummary",
                            "counterSummary.threatResponses must say how the build answers them")
            summary.setdefault("acceptedTradeoffs", [])
            summary.setdefault("unansweredThreats", [])
            summary.setdefault("allyContextUsed", False)

    # ---- the five main items ------------------------------------------------
    items = [resolve(s) for s in (res.get("items") or [])]
    if len(items) != 5 or None in items or len(set(items)) != 5:
        report.fail("items", f"items must be 5 unique known slugs, got {res.get('items')}")
        items = []
    else:
        res["items"] = items
        bad_type = [s for s in items if not _completed_non_boots(s)]
        if bad_type:
            report.fail("items", f"the 5 items must all be completed NON-boots items; "
                                 f"{bad_type} are boots or components")
        outside = [s for s in items if allowed and s not in allowed]
        if outside:
            report.fail("items", f"{outside} were withheld from the item pool for this "
                                 "request and cannot be selected; pick from the supplied pool")
        reactive = [s for s in items if s in itemmeta.SITUATIONAL_ONLY] if not enemies_known else []
        if reactive:
            report.fail("items", f"reactive items {reactive} cannot be in the main 5 with no "
                                 "enemy team supplied -- move them to situational swaps")
        violation = hard_exclusive_violation(items)
        if violation:
            report.fail("items", violation)
        for note in redundancy_notes(items):
            report.warn(note)
        # Late-strategic items are allowed, but not anywhere and not silently.
        for slug, cfg in itemmeta.LATE_STRATEGIC.items():
            if slug not in items:
                continue
            position = items.index(slug) + 1
            minimum = int(cfg.get("minPosition", 4))
            if position < minimum:
                report.fail("items", f"{slug} is a late strategic purchase and cannot sit at "
                                     f"position {position}; it may enter the build at "
                                     f"position {minimum} or later")
        for problem in identity_violations(items, identity):
            report.fail("items", problem)

    main_items = [s for s in items if s]

    # ---- boots --------------------------------------------------------------
    boots = resolve(res.get("boots", ""))
    if not boots or (ITEMS.get(boots) or {}).get("bootsTier") != 2:
        report.fail("boots", f"boots must be a tier-2 boots slug, got {res.get('boots')}")
    else:
        res["boots"] = boots
        res["bootsUpgrade"] = ITEMS[boots].get("upgradesTo")
        # An AP request that comes back with attack-speed boots is not honouring
        # the request. Only OFF-PATH OFFENSIVE boots are rejected: neutral and
        # defensive boots (haste, armor, tenacity, omnivamp) are legitimate on
        # any path and are often correct, so this must not become a rule that
        # forces the offensive boot.
        boot_stats = set((ITEMS.get(boots) or {}).get("stats") or {})
        off_path = (
            ("ad" in boot_stats or "attackSpeed" in boot_stats) if damage_path == "ap"
            else ("ap" in boot_stats) if damage_path == "ad"
            else False)
        if off_path:
            report.fail("boots",
                        f"this is an {damage_path.upper()} build and {boots} is an offensive "
                        f"boot for the other damage type ({', '.join(sorted(boot_stats))}). "
                        f"Choose the {damage_path.upper()} offensive boot, or a neutral/"
                        f"defensive boot -- those stay available on any damage path.")
        # The old rule banned defensive boots outright for these classes. That
        # is right with no enemy team and wrong once a comp is on the table,
        # where the defensive boot is sometimes simply the better choice. So the
        # ban now applies only when there is nothing to be defensive about.
        if (boots in DEFENSIVE_BOOTS and champion_class in OFFENSE_FIRST_CLASSES
                and not enemies_known):
            report.fail("boots",
                        f"{champion_class} main boots cannot be defensive {boots} when no enemy "
                        "team was supplied -- there is no threat to itemise against. Choose "
                        "offensive/utility boots and put this in situationalBoots.")
        elif boots in DEFENSIVE_BOOTS and champion_class in OFFENSE_FIRST_CLASSES:
            reason = str((res.get("buildScore") or {}).get("reason") or "") + " " + \
                " ".join(str(w) for w in (res.get("why") or []))
            if len(reason.strip()) < 20:
                report.fail("boots",
                            f"{boots} is a defensive main boot for a {champion_class}. That is "
                            "allowed here because an enemy team was supplied, but you must say "
                            "in 'why' which specific enemy threat makes surviving or holding "
                            "combat uptime worth more than the offensive boot's damage.")

    situational_boots = []
    seen_boots = set()
    for entry in res.get("situationalBoots") or []:
        if not isinstance(entry, dict):
            report.fail("boots", f"situationalBoots entries must be objects, got {entry!r}")
            continue
        slug = resolve(entry.get("boots", ""))
        if not slug or (ITEMS.get(slug) or {}).get("bootsTier") != 2:
            report.fail("boots", f"situationalBoots must use tier-2 boots slugs, "
                                 f"got {entry.get('boots')}")
            continue
        if slug == boots or slug in seen_boots:
            continue
        when = str(entry.get("when") or "").strip()
        if not when:
            report.fail("boots", f"situational boot {slug} needs a specific 'when' condition")
            continue
        seen_boots.add(slug)
        situational_boots.append({
            "boots": slug, "bootsUpgrade": ITEMS[slug].get("upgradesTo"), "when": when})
    res["situationalBoots"] = situational_boots

    # ---- situational item swaps --------------------------------------------
    situational = []
    seen = set()
    for entry in res.get("situational") or []:
        if not isinstance(entry, dict):
            report.fail("situational", f"situational entries must be objects, got {entry!r}")
            continue
        add = resolve(entry.get("item", ""))
        if not add:
            report.fail("situational", f"unknown situational item {entry.get('item')!r}")
            continue
        if add in main_items:
            report.fail("situational", f"situational item {add} is already in the main five")
            continue
        if add in seen:
            continue
        when = str(entry.get("when") or "").strip()
        if not when:
            report.fail("situational", f"situational item {add} needs a specific 'when' condition")
            continue
        # Accept the old shape too: `replaces` + `atPosition` still describe a
        # valid (if less expressive) swap, and rejecting them would fail builds
        # that are merely conservative rather than wrong.
        removed = resolve(entry.get("removedItem") or entry.get("replaces") or "")
        if not removed or removed not in main_items:
            report.fail("situational",
                        f"situational '{add}' removes {entry.get('removedItem') or entry.get('replaces')!r}, "
                        "which must be one of the five main items")
            continue
        position = entry.get("insertAtPosition") or entry.get("atPosition")
        try:
            position = int(position)
        except (TypeError, ValueError):
            position = main_items.index(removed) + 1
        if not 1 <= position <= 5:
            report.fail("situational", f"situational '{add}' insertAtPosition must be 1-5, "
                                       f"got {position}")
            continue

        order = entry.get("resultingOrder")
        if order is None:
            # Derive it: drop the removed item, insert the new one at the stated
            # position. A build that omitted resultingOrder is under-specified,
            # not wrong, so we complete it rather than rejecting it.
            rest = [s for s in main_items if s != removed]
            rest.insert(min(position - 1, len(rest)), add)
            resolved_order = rest[:5]
            violation = hard_exclusive_violation(resolved_order)
            if violation:
                report.fail("situational", f"situational '{add}': the build it produces is "
                                           f"illegal -- {violation}")
                continue
        else:
            resolved_order = _resulting_order(
                report, "situational", f"situational '{add}'", order,
                must_contain=add, at_position=position, must_not_contain=removed,
                resolve=resolve)
            if resolved_order is None:
                continue

        seen.add(add)
        situational.append({
            "item": add, "insertAtPosition": position, "removedItem": removed,
            "resultingOrder": resolved_order, "when": when,
            # Old field names, kept so the existing frontend keeps rendering.
            "replaces": removed, "atPosition": position,
        })
    res["situational"] = situational
    if situational and all(s["atPosition"] >= 4 for s in situational):
        report.fail("situational",
                    "every situational swap lands on the 4th or 5th item, which is too late to "
                    "matter in a 15-20 minute game -- re-time at least one to the slot where the "
                    "threat actually needs answering (usually the 2nd or 3rd purchase), or drop it")

    # ---- rune page ----------------------------------------------------------
    page = res.get("runes") or {}
    for message in runemeta.page_errors(page):
        report.fail("runes", message)
    if not report.errors.get("runes"):
        page["keystone"] = runemeta.resolve(page.get("keystone", ""))
        page["minors"] = [runemeta.resolve(m) for m in (page.get("minors") or [])]
        page["flex"] = runemeta.resolve(page.get("flex", ""))
        res["runes"] = page
    page_all = [page.get("keystone"), *(page.get("minors") or []), page.get("flex")]
    _realign_rune_reasons(res, page, report)

    # ---- situational runes --------------------------------------------------
    situational_runes = []
    seen_runes = set()
    for entry in res.get("situationalRunes") or []:
        if not isinstance(entry, dict):
            report.fail("situationalRunes", f"entries must be objects, got {entry!r}")
            continue
        rune = runemeta.resolve(entry.get("rune", ""))
        if not rune:
            report.fail("situationalRunes",
                        f"unknown rune name {entry.get('rune')!r}")
            continue
        when = str(entry.get("when") or "").strip()
        if not when:
            report.fail("situationalRunes", f"situational rune {rune} needs a 'when' condition")
            continue
        if rune in page_all:
            report.fail("situationalRunes",
                        f"situational rune {rune} is already on the main rune page; a swap must "
                        "bring in a rune the page does not already run")
            continue
        if rune in seen_runes:
            continue

        kind = "item" if entry.get("replacesType") == "item" else "rune"
        if kind == "rune":
            replaced = runemeta.resolve(entry.get("replaces", ""))
            if not replaced or replaced not in page_all:
                report.fail("situationalRunes",
                            f"situational rune {rune} replaces {entry.get('replaces')!r}, which "
                            "is not on the rune page you chose")
                continue
            swap_error = runemeta.legal_swap_error(rune, replaced, page)
            if swap_error:
                report.fail("situationalRunes", swap_error)
                continue
            resolved_entry = {
                "rune": rune, "replaces": replaced, "replacesType": "rune",
                "replacesLabel": replaced, "when": when,
            }
        else:
            replaced = resolve(entry.get("replaces", ""))
            if not replaced or replaced not in main_items:
                report.fail("situationalRunes",
                            f"situational rune {rune} claims to replace item "
                            f"{entry.get('replaces')!r}, which must be one of the five main items")
                continue
            # Freeing an item slot without saying what fills it leaves a
            # four-item build. That is the hole this branch exists to close.
            freed = resolve(entry.get("freedSlotItem", ""))
            if not freed:
                report.fail("situationalRunes",
                            f"situational rune {rune} frees the slot held by {replaced}, so it "
                            "must also name freedSlotItem: the item that now takes that slot. "
                            "Without it the build is only four items.")
                continue
            if freed in main_items:
                report.fail("situationalRunes",
                            f"freedSlotItem {freed} is already in the main five; the freed slot "
                            "needs an item the build does not already have")
                continue
            position = entry.get("atPosition")
            try:
                position = int(position)
            except (TypeError, ValueError):
                position = main_items.index(replaced) + 1
            order = entry.get("resultingItems")
            if order is None:
                rest = [s for s in main_items if s != replaced]
                rest.insert(min(max(position, 1) - 1, len(rest)), freed)
                resolved_order = rest[:5]
                violation = hard_exclusive_violation(resolved_order)
                if violation:
                    report.fail("situationalRunes",
                                f"situational rune {rune}: the build it produces is illegal "
                                f"-- {violation}")
                    continue
            else:
                resolved_order = _resulting_order(
                    report, "situationalRunes", f"situational rune {rune}", order,
                    must_contain=freed, at_position=position, must_not_contain=replaced,
                    resolve=resolve)
                if resolved_order is None:
                    continue
            resolved_entry = {
                "rune": rune, "replaces": replaced, "replacesType": "item",
                "replacesLabel": (ITEMS.get(replaced) or {}).get("name", replaced),
                "freedSlotItem": freed, "atPosition": position,
                "resultingItems": resolved_order, "when": when,
            }

        seen_runes.add(rune)
        situational_runes.append(resolved_entry)
    res["situationalRunes"] = situational_runes

    # ---- snowball swap ------------------------------------------------------
    snowball = res.get("snowballSwap")
    if snowball is not None:
        if not isinstance(snowball, dict):
            report.fail("snowball", "snowballSwap must be an object or null")
        else:
            add = resolve(snowball.get("item", ""))
            removed = resolve(snowball.get("replaces", ""))
            when = str(snowball.get("when") or "").strip()
            if not add or not removed:
                report.fail("snowball", "snowballSwap must use known item and replaces slugs")
            elif removed not in main_items:
                report.fail("snowball", "snowballSwap.replaces must be one of the five main items")
            elif add in main_items:
                report.fail("snowball", "snowballSwap.item must not already be in the five")
            elif not when:
                report.fail("snowball", "snowballSwap.when is required")
            elif len(when) < 25 or when.lower().strip(" .") in {"when ahead", "when fed"}:
                # "when ahead" is not actionable: the player cannot tell whether
                # it applies. A usable condition names a measurable lead.
                report.fail("snowball",
                            f"snowballSwap.when is too vague ({when!r}). Name a concrete, "
                            "checkable condition -- a gold lead before a specific objective, a "
                            "first item completed well ahead of its normal timing, or a specific "
                            "shutdown you are carrying.")
            else:
                position = snowball.get("atPosition")
                try:
                    position = int(position)
                except (TypeError, ValueError):
                    position = main_items.index(removed) + 1
                order = snowball.get("resultingOrder")
                if order is None:
                    rest = [s for s in main_items if s != removed]
                    rest.insert(min(max(position, 1) - 1, len(rest)), add)
                    resolved_order = rest[:5]
                else:
                    resolved_order = _resulting_order(
                        report, "snowball", "snowballSwap", order, must_contain=add,
                        at_position=position, must_not_contain=removed, resolve=resolve)
                if resolved_order is not None:
                    snowball.update({
                        "item": add, "replaces": removed, "atPosition": position,
                        "resultingOrder": resolved_order, "when": when,
                    })

    # ---- item scores --------------------------------------------------------
    candidates = _score_rows(report, res, "candidateItemScores", resolve, allowed)
    audit = _score_rows(report, res, "mandatoryAuditScores", resolve, allowed)
    # The old single list is still published so nothing downstream breaks, but
    # it is now derived rather than authored.
    merged: dict[str, dict] = {}
    for row in candidates + audit:
        merged.setdefault(row["item"], row)
    res["itemScores"] = list(merged.values())

    scored = set(merged)
    missing_audit = sorted(set(required_audit_items or []) - scored)
    if missing_audit:
        report.fail("scores", "these items are in the mandatory audit and must each appear in "
                              "mandatoryAuditScores with a score and a reason: "
                    + ", ".join(missing_audit))
    # The free support item is exempt: it is mandatory for the role rather than
    # selected, so there is no competing candidate to score it against. Demanding
    # a score for it cost a whole repair round on the first live support build.
    _SUPPORT_ITEMS = {"bulwark-of-the-mountain", "black-mist-scythe"}
    missing_final = sorted(s for s in main_items
                           if s not in scored and s not in _SUPPORT_ITEMS)
    if missing_final:
        report.fail("scores", "every item you selected must also be scored: "
                    + ", ".join(missing_final) + " are missing from candidateItemScores")
    # The prompt's REQUIRED CANDIDATES (the ladder core, presented without
    # provenance) demand a score whether or not they reach the build. The rule
    # lived only in prose until a live Aatrox run silently skipped
    # trinity-force -- a core item -- and nothing caught it. Boots are exempt
    # for the same reason selected items' boots are: candidateItemScores never
    # carries boots, they are argued in bootsReason.
    missing_core = sorted(
        s for s in (ladder_core or [])
        if s not in scored and _completed_non_boots(s) and s not in _SUPPORT_ITEMS)
    if missing_core:
        report.fail("scores", "these required candidates must each appear in "
                              "candidateItemScores with a score and a reason, whether or "
                              "not they made your build: " + ", ".join(missing_core))
    if candidates and len(candidates) < 12:
        report.warn(f"only {len(candidates)} competitive candidates were scored; the brief asks "
                    "for 15-18 so the comparison is real")

    # ---- build score --------------------------------------------------------
    # Counter mode skips the full build evaluation on purpose: a counter build is
    # wanted fast, and the eight-category score is the slowest part of the output
    # to produce. Drop it rather than require it.
    if mode == "counter":
        res.pop("buildScore", None)
    else:
        build_score = res.get("buildScore") or {}
        if not isinstance(build_score, dict):
            report.fail("scores", "buildScore must be an object")
        else:
            for key in _SCORE_KEYS:
                try:
                    value = float(build_score.get(key))
                except (TypeError, ValueError):
                    report.fail("scores", f"buildScore.{key} must be numeric")
                    continue
                if not 0 <= value <= 100:
                    report.fail("scores", f"buildScore.{key} must be between 0 and 100")
                else:
                    build_score[key] = round(value, 1)
            if not str(build_score.get("reason") or "").strip():
                report.fail("scores", "buildScore.reason is required")
            res["buildScore"] = build_score

    # ---- summoners ----------------------------------------------------------
    # Deliberately left alone. This used to pop the key, because the advisor
    # assigned summoners itself and anything the model returned was noise. Now
    # the model's pick IS the answer, and summoners.enforce() applies the jungle
    # rules to it downstream, so discarding it here would silently throw away a
    # choice made against the enemy comp and fall back to the static table.

    # ---- play guide ---------------------------------------------------------
    # Checked for SUBSTANCE, not just presence. The failure mode for a written
    # section is not a missing key, it is four paragraphs of advice that would
    # be true of any build on this champion -- which is worse than nothing,
    # because it looks like an answer. So the guide has to name pieces of the
    # loadout it is describing, and the whole loadout counts: a guide that
    # discusses only items is describing a third of what was chosen.
    guide = res.get("playGuide")
    _GUIDE_KEYS = ("earlyGame", "powerSpike", "teamfight", "pitfall")
    if not isinstance(guide, dict):
        report.fail("playGuide", "playGuide must be an object with the keys "
                                 f"{', '.join(_GUIDE_KEYS)}")
    else:
        thin = [k for k in _GUIDE_KEYS if len(str(guide.get(k) or "").strip()) < 40]
        if thin:
            report.fail("playGuide",
                        f"these playGuide sections are missing or too short to be useful: "
                        f"{', '.join(thin)}. Each needs two or three real sentences about "
                        f"THIS build.")
        else:
            blob = " ".join(str(guide.get(k) or "") for k in _GUIDE_KEYS).lower()
            named = [s for s in main_items + [boots] if s
                     and (ITEMS.get(s, {}).get("name", "") or "").lower().split()[0] in blob]
            page = res.get("runes") or {}
            rune_names = [page.get("keystone"), *(page.get("minors") or []), page.get("flex")]
            named_runes = [r for r in rune_names if r and str(r).lower() in blob]
            if not named:
                report.fail("playGuide",
                            "the playGuide never names an item from this build, so it is "
                            "generic champion advice rather than a guide to this build. "
                            "Name the pieces the advice depends on.")
            elif not named_runes:
                report.fail("playGuide",
                            "the playGuide names items but never a rune from the page you "
                            "chose. The items, runes and summoners were picked to work "
                            "together -- say how, naming the runes involved.")

    # ---- locks --------------------------------------------------------------
    for slug in (item_locks or []):
        if slug not in main_items:
            report.fail("locks", f"locked item {(ITEMS.get(slug) or {}).get('name', slug)} "
                                 f"({slug}) is missing from the five main items -- the player "
                                 "pinned it and it must be included")
    if boot_lock and res.get("boots") != boot_lock:
        report.fail("locks", f"locked boots {(ITEMS.get(boot_lock) or {}).get('name', boot_lock)} "
                             f"({boot_lock}) must be the main boots -- the player pinned it")
    for name in (rune_locks or []):
        if name not in page_all:
            report.fail("locks", f"locked rune {name} is missing from the rune page -- the "
                                 "player pinned it")

    return report


def _score_rows(report: Report, res: dict, key: str, resolve, allowed) -> list[dict]:
    """Normalise one score list, dropping unusable rows.

    A bad row here is DROPPED with a warning rather than failing the build. The
    score lists are commentary on the decision, not the decision: the selection
    itself is checked against the pool separately, so a stray row for an item
    the model could not have built is noise, not a defect. Failing on it cost a
    full regeneration -- roughly 60 seconds and a second paid call -- to correct
    a line of text nobody would have acted on.

    The genuinely load-bearing checks (every selected item scored, every audit
    item answered) live in the caller and remain hard errors.
    """
    rows = res.get(key)
    if rows is None:
        return []
    if not isinstance(rows, list):
        report.fail("scores", f"{key} must be a list")
        res[key] = []
        return []
    out = []
    for entry in rows:
        if not isinstance(entry, dict):
            report.warn(f"{key}: dropped a malformed entry ({entry!r})")
            continue
        slug = resolve(entry.get("item", ""))
        if not _completed_non_boots(slug):
            report.warn(f"{key}: dropped {entry.get('item')!r}, which is not a known "
                        "completed non-boots item")
            continue
        if allowed and slug not in allowed:
            report.warn(f"{key}: dropped {slug}, which was withheld from the pool for this "
                        "request; it could not have been selected anyway")
            continue
        try:
            score = float(entry.get("score"))
        except (TypeError, ValueError):
            report.warn(f"{key}: dropped {slug}, its score was not numeric")
            continue
        if not 0 <= score <= 100:
            report.warn(f"{key}: dropped {slug}, score {score} is outside 0-100")
            continue
        entry["item"] = slug
        entry["score"] = score
        entry["synergyWith"] = _clean_synergy(report, key, slug, entry, resolve)
        out.append(entry)
    res[key] = out
    return out


def _clean_synergy(report: Report, key: str, slug: str, entry: dict, resolve) -> list[str]:
    """Normalise one row's `synergyWith`.

    Per-item scoring cannot express "this is worth more BECAUSE that is in the
    build" -- Guinsoo's doubling every other on-hit item, Runaan's turning
    single-target on-hit into AoE. Asking for it in prose produced nothing
    measurable across 25 items; a field can at least be checked.

    Cleaned, never failed. An unusable reference is dropped with a warning:
    this list is commentary on the decision rather than the decision, and the
    same reasoning applies as for the score rows themselves. What IS enforced
    is that it cannot name garbage or point at itself.
    """
    raw = entry.get("synergyWith")
    if raw in (None, ""):
        return []
    if not isinstance(raw, list):
        report.warn(f"{key}: {slug} synergyWith was not a list; ignored")
        return []
    seen: list[str] = []
    for ref in raw:
        target = resolve(ref if isinstance(ref, str) else "")
        if not target or not _completed_non_boots(target):
            report.warn(f"{key}: {slug} claims synergy with {ref!r}, which is not a known "
                        "completed non-boots item")
            continue
        if target == slug:
            report.warn(f"{key}: {slug} lists itself in synergyWith")
            continue
        if target not in seen:
            seen.append(target)
    return seen
