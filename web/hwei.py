"""Single-target Hwei timeline. Mirrored by src/lib/hwei.ts; numbers live in hwei_kit.json.

One choice per subject, shared cooldowns, finite WE charges, distinct-cast
passive marks, mana costs and delayed R damage. See the kit's assumptions.
"""
import heapq


def timeline(kit, st, target, window, level=13):
    choices = {"1": "QQ", "2": "WE", "3": "EQ", **st.get("hweiChoices", {})}
    for slot, valid in {"1": ("QQ", "QW", "QE"), "2": ("WQ", "WW", "WE"),
                        "3": ("EQ", "EW", "EE")}.items():
        if choices[slot] not in valid:
            raise ValueError("Invalid Hwei subject choice")
    ranks = {s: sum(lv <= level for lv in levels) - 1 for s, levels in kit["skillOrder"].items()}
    value = lambda xs, rank: xs[min(max(rank, 0), len(xs) - 1)]
    ap = st.get("ap", 0)
    haste = 100 / (100 + st.get("haste", 0))
    result = {"damage": {s: 0.0 for s in ("P", "1", "2", "3", "4")},
              "casts": {s: 0 for s in ("1", "2", "3", "4")}, "autos": 0,
              "passives": 0, "empoweredHits": 0, "manaRestored": 0.0,
              "shield": 0.0, "allyShield": 0.0, "events": []}
    queue, serial = [], 0
    def push(t, kind, data=None):
        nonlocal serial
        serial += 1
        heapq.heappush(queue, (t, serial, kind, data))
    ready = {s: 0.0 for s in ranks}
    mana = st.get("mana", 0)
    mana_max = mana
    last_time, next_auto = 0.0, 0.0
    charges, light_id = 0, ""
    marked, mark_until = None, -1.0
    seen, empowered = set(), set()
    shield_casts = []
    dealt = 0.0
    def hit(t, slot, token, amount, use_lights=True):
        nonlocal charges, marked, mark_until, dealt, mana
        result["damage"][slot] += amount
        dealt += amount
        result["events"].append({"time": round(t, 4), "slot": slot, "damage": amount})
        if token not in seen and amount > 0:
            seen.add(token)
            if marked is not None and t <= mark_until and marked != token:
                marked = None
                p = kit["passive"]
                base = p["base"][0] + (p["base"][1] - p["base"][0]) * (level - 1) / 14
                push(t + 0.25, "passive", base + p["ap"] * ap)
            else:
                marked, mark_until = token, t + kit["passive"]["markSeconds"]
        if use_lights and charges and token not in empowered:
            empowered.add(token)
            charges -= 1
            we = kit["spells"]["WE"]
            restore = value(we["manaRestore"], ranks["2"])
            mana = min(mana_max, mana + restore)
            result["manaRestored"] += restore
            result["empoweredHits"] += 1
            hit(t, "2", light_id, value(we["base"], ranks["2"]) + we["ap"] * ap, False)
    push(0, "action")
    while queue:
        t, _, kind, data = heapq.heappop(queue)
        if t > window + 1e-9:
            break
        # Base mana regeneration, per five seconds. Item mana-regen effects
        # are not tracked by the existing engine stat block.
        regen = kit["baseStats"]["manaRegen"]
        mana = min(mana_max, mana + (t - last_time) * (regen[0] + regen[1] * (level - 1)) / 5)
        last_time = t
        if kind == "passive":
            result["damage"]["P"] += data
            result["passives"] += 1
            dealt += data
            continue
        if kind == "hit":
            hit(t, *data)
            continue
        if kind == "bolt":
            slot, token, spell, rank = data
            missing = min(1, max(0, 1 - target.get("currentHp", target["hp"]) / target["hp"]
                                   + dealt * target.get("magicMultiplier", 1) / target["hp"]))
            low = value(spell["base"], rank) + spell["ap"] * ap
            high = value(spell["maxBase"], rank) + spell["maxAp"] * ap
            hit(t, slot, token, low + (high - low) * missing)
            continue
        slot = next((s for s in ("2", "3", "1", "4") if ranks[s] >= 0
                     and ready[s] <= t + 1e-9 and mana >= kit["manaCosts"][s]), None)
        if slot is not None:
            rank = ranks[slot]
            code = "R" if slot == "4" else choices[slot]
            spell = kit["spells"][code]
            result["casts"][slot] += 1
            token = slot + ":" + str(result["casts"][slot])
            mana -= kit["manaCosts"][slot]
            ready[slot] = t + value(kit["cooldowns"][slot], rank) * haste
            impact = t + 0.25
            if code == "WE":
                charges, light_id = spell["charges"], token
            elif code == "WW":
                shield_casts.append((t, rank))
            elif code == "WQ":
                pass  # Movement and vision are outside a stationary target test.
            elif code == "QW":
                push(impact, "bolt", (slot, token, spell, rank))
            else:
                base = value(spell["base"], rank) + spell["ap"] * ap
                if code == "QQ":
                    base += value(spell["targetMaxHp"], rank) * target["hp"]
                if code == "R":
                    push(impact + spell["duration"], "hit", (slot, token, base))
                else:
                    push(impact, "hit", (slot, token, base))
                if code in ("QE", "R"):
                    tick = value(spell["tickBase"], rank) + spell["tickAp"] * ap
                    step = 0.5 if code == "QE" else 1.0
                    for i in range(1, round(spell["duration"] / step) + 1):
                        push(impact + i * step, "hit", (slot, token, tick * step))
        elif next_auto <= t + 1e-9:
            result["autos"] += 1
            next_auto = t + 1 / max(st.get("as", 0.75), 0.1)
            if charges:
                # Autos do not mark; the WE bonus attached to one does.
                token = "auto:" + str(result["autos"])
                empowered.add(token)
                charges -= 1
                we = kit["spells"]["WE"]
                restore = value(we["manaRestore"], ranks["2"])
                mana = min(mana_max, mana + restore)
                result["manaRestored"] += restore
                result["empoweredHits"] += 1
                hit(t, "2", light_id, value(we["base"], ranks["2"]) + we["ap"] * ap, False)
        push(t + 0.45, "action")
    for t, rank in shield_casts:
        ww = kit["spells"]["WW"]
        initial = value(ww["shieldBase"], rank) + ww["shieldAp"] * ap
        cap = value(ww["maxShieldBase"], rank) + ww["maxShieldAp"] * ap
        shield = initial + (cap - initial) * min(1, max(0, window - t) / ww["rampSeconds"])
        result["shield"] += shield
        result["allyShield"] += shield * ww["allyMultiplier"]
    result["manaRemaining"] = mana
    return result
