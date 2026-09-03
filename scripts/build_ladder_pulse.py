"""Aggregate every complete capture session into the site's ladder pulse.

Two outputs:

1. web-next/src/data/ladder_pulse.json -- consumed at build time by the meta
   page's ladder section, the Hall of Fame page, and the champion combat
   profiles: global item/keystone/spell meta, per-champion measured profiles
   (KDA, teamfight, gold, damage dealt/taken, turret pressure, first blood,
   MVP and S-rating rates, the legendary tax, keystone consensus, build
   conformity, pentakills, tier composition), cross-champion baselines, and
   the hall-of-fame superlatives (grinder, perfectionist, KDA king, penta
   king, MVP machine, the wall, demolition expert, account extremes, guild
   power ranking, multi-board masters).

2. data/ladder_consensus.json -- the advisor's view of the same evidence:
   per champion, the top-50 players' item pick rates, keystone shares and
   spell pairs, injected into the build prompt and used to score generated
   builds' agreement with the ladder.

Run after extractions (idempotent, only complete sessions count):
    python -m scripts.build_ladder_pulse
"""
from __future__ import annotations

import functools
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.export_captures import (  # noqa: E402
    find_sessions, _builds_by_rank, _stats_by_rank, _players_by_rank,
    _read_csv, _slug,
)
from web.integrity import counts_toward_aggregates, eligible_for_title  # noqa: E402
from web.runes import canonical_rune, is_known_rune  # noqa: E402


@functools.lru_cache(maxsize=1)
def _rune_trees() -> dict[str, str]:
    """{rune name: tree}. Keystones are their own 'tree' in the catalogue, so
    a keystone's real tree is not recorded -- only minors carry one."""
    runes = json.loads((ROOT / "data" / "wrmeta_runes.json").read_text(encoding="utf-8"))
    return {r["name"]: (r.get("tree") or r.get("type") or "") for r in runes}


def _weighted(stat: dict) -> float | None:
    """Games-weighted mean win rate for a usage bucket, or None if too thin.

    Weighting by games matters: a rune carried by one 400-game main should not
    read the same as one used across forty short samples. The 200-game floor
    keeps a single lucky player from topping the table.
    """
    if stat["games"] < 200:
        return None
    return round(stat["wr_games"] / stat["games"], 2)

PULSE_OUT = ROOT / "web-next" / "src" / "data" / "ladder_pulse.json"
CONSENSUS_OUT = ROOT / "data" / "ladder_consensus.json"
ITEMS = {i["slug"]: i["name"]
         for i in json.loads((ROOT / "data" / "items.json").read_text(encoding="utf-8"))}

MIN_GAMES_FEATURED = 30   # a superlative needs a real sample behind it


def tier_family(tier: str) -> str:
    """'Legendary Grandmaster IV' -> 'legendary-grandmaster'; strips OCR
    punctuation ('Challenger:' -> 'challenger')."""
    words = [w for w in "".join(c for c in tier.lower() if c.isalpha() or c.isspace()).split() if w]
    if not words:
        return ""
    if words[0] == "legendary" and len(words) > 1:
        return f"legendary-{words[1]}"
    if words[0] == "ascended":
        return "legend"
    return words[0]


def _avg(a):
    a = [x for x in a if x is not None]
    return round(sum(a) / len(a), 2) if a else None


def _median(a):
    a = sorted(x for x in a if x is not None)
    return a[len(a) // 2] if a else None


def build() -> tuple[dict, dict]:
    # 40 matches export_captures --min-ranks: the same five owner-accepted
    # boards (42-44 filled) were absent from every pulse table while their
    # champions sat in the tier list, which is how "135 champions" met "we
    # have 140".
    sessions = find_sessions(40)
    item_global: Counter = Counter()
    keystone_global: Counter = Counter()
    spell_global: Counter = Counter()
    tree_global: Counter = Counter()
    minor_global: Counter = Counter()
    # {name: {"n": builds, "games": games, "wr_games": winrate*games}} so a
    # bucket's win rate can be games-weighted rather than a flat average
    perf: dict[str, dict] = {}

    def _note(bucket: str, name: str, wr, games) -> None:
        d = perf.setdefault(bucket + "|" + name, {"n": 0, "games": 0, "wr_games": 0.0})
        d["n"] += 1
        if wr is not None and games:
            d["games"] += games
            d["wr_games"] += wr * games
    tier_global: Counter = Counter()
    champions: dict = {}
    consensus: dict = {}
    cross: dict[str, list] = defaultdict(list)
    guilds: Counter = Counter()
    n_players = n_builds = 0

    # superlative candidate pools: (value, player, champion, detail)
    pools: dict[str, list] = defaultdict(list)

    for champ, sess in sorted(sessions.items()):
        rows = _read_csv(sess / "extracted.csv")
        ids = _players_by_rank(sess)
        builds = _builds_by_rank(sess)
        stats = _stats_by_rank(sess)
        name_by_rank: dict[int, str] = {}

        # Boosting and permabanned accounts contribute to nothing: not a
        # record, not a stat, not an item pick rate. Their ranks are blocked up
        # front so every loop below skips them (web/integrity.py explains why).
        blocked = {int(r["rank"]) for r in rows
                   if not counts_toward_aggregates(r.get("player_name"))}

        ks: Counter = Counter()
        minors: Counter = Counter()
        spells: Counter = Counter()
        items: Counter = Counter()
        exact: Counter = Counter()
        # win rate + games for the player who ran each build, so usage can be
        # weighted by how well it actually performed
        by_rank = {}
        for r in rows:
            try:
                by_rank[int(r["rank"])] = (float(r["winrate"]), int(float(r["games"])))
            except (TypeError, ValueError, KeyError):
                continue

        for rank, b in builds.items():
            if rank in blocked:
                continue
            n_builds += 1
            wr_g = by_rank.get(rank, (None, None))
            if b.get("runes"):
                key = canonical_rune(b["runes"][0])
                # Slot 0 must actually BE a keystone. A captured popup that was
                # not a build screen (one live frame carried plain UI text)
                # yields a page like ['Legend: Bloodline', '?', '?', '?', '?'],
                # and counting its slot 0 as a keystone poisons the consensus.
                # A page whose first rune is unknown or a minor is page-level
                # garbage: skip the whole rune read, keep the item read.
                if _rune_trees().get(key) == "Keystone":
                    ks[key] += 1
                    keystone_global[key] += 1
                    _note("keystone", key, *wr_g)
                for minor in b["runes"][1:]:
                    m = canonical_rune(minor)
                    if not is_known_rune(m):
                        continue
                    minors[m] += 1
                    minor_global[m] += 1
                    _note("minor", m, *wr_g)
                    tree = _rune_trees().get(m)
                    if tree and tree != "Keystone":
                        tree_global[tree] += 1
                        _note("tree", tree, *wr_g)
            if b.get("spells"):
                pair = " + ".join(sorted(b["spells"]))
                spells[pair] += 1
                spell_global[pair] += 1
            slugs = tuple(sorted(i["slug"] for i in b["items"] if i.get("slug")))
            for s in slugs:
                items[s] += 1
                item_global[s] += 1
                _note("item", s, *wr_g)
            if len(slugs) >= 5:
                exact[slugs] += 1

        wrs, r_wr, l_wr = [], [], []
        # Paired legendary-vs-ranked differences: SAME player, both queues,
        # both with enough games. See the legendaryTax comment below.
        tax_pairs: list[float] = []
        kda, tf, gpm, dmg, taken, turret = [], [], [], [], [], []
        fb, mvp_rate, s_rate, games_r = [], [], [], []
        pentas = 0
        tiers: Counter = Counter()

        for r in rows:
            name = r.get("player_name") or ""
            if not counts_toward_aggregates(name):
                continue
            try:
                g = int(float(r["games"]))
                w = float(r["winrate"])
            except (TypeError, ValueError):
                continue
            rank = int(r["rank"])
            name_by_rank[rank] = name
            n_players += 1
            wrs.append(w)
            # The anonymous aggregates above take every counted row. The named
            # pools below print the NAME, so they additionally require title
            # eligibility -- an advert's games belong in the average, its name
            # does not belong on a trophy. The mastery record went to
            # 'Insta wrsamboost' the day this distinction was lost.
            titled = eligible_for_title(name)
            if name and titled:
                cross[name].append({"champion": champ, "slug": _slug(champ),
                                    "rank": rank, "wr": w, "games": g})
            if titled:
                pools["grinder"].append((g, name, champ, f"{w:.1f}% win rate"))
                if g >= MIN_GAMES_FEATURED:
                    pools["perfectionist"].append((w, name, champ, f"{g} games"))
                try:
                    score = int(float(r["score"]))
                    pools["masteryRecord"].append((score, name, champ, f"rank {rank} by mastery"))
                except (TypeError, ValueError):
                    pass

        for rank, who in ids.items():
            if rank in blocked:
                continue
            fam = tier_family(who.get("tier") or "")
            if fam:
                tiers[fam] += 1
                tier_global[fam] += 1
            if who.get("guild"):
                guilds[who["guild"]] += 1
            if who.get("level") and eligible_for_title(name_by_rank.get(rank, "")):
                pools["veteran"].append((who["level"], name_by_rank.get(rank, ""), champ, "account level"))

        # Same split as the row loop: anonymous arrays take everyone, named
        # pools require title eligibility. `fpools` is a discard sink for
        # ineligible rows so the dozen appends below stay unconditional.
        discard: dict = defaultdict(list)
        for rank, q in stats.items():
            if rank in blocked:
                continue
            name = name_by_rank.get(rank, "")
            fpools = pools if eligible_for_title(name) else discard
            r0 = q.get("ranked")
            l0 = q.get("legendary")
            if r0:
                g0 = r0.get("games") or 0
                if r0.get("wr") is not None:
                    r_wr.append(r0["wr"])
                # Account-level season totals, not per-champion: "who has
                # played the most ranked, full stop". Grinder keeps the
                # one-champion crown from the board rows.
                if g0:
                    fpools["marathonRanked"].append(
                        (g0, name, champ, f"{r0['wr']:.1f}% win rate" if r0.get("wr") is not None else "ranked"))
                for arr, key in ((kda, "kda"), (tf, "tf"), (gpm, "gpm"),
                                 (dmg, "dmg"), (taken, "taken"), (turret, "turret")):
                    if r0.get(key) is not None:
                        arr.append(r0[key])
                if g0:
                    games_r.append(g0)
                    if r0.get("firstBlood") is not None:
                        fb.append(r0["firstBlood"] / g0 * 100)
                    if r0.get("mvp") is not None:
                        mvp_rate.append(r0["mvp"] / g0 * 100)
                    if r0.get("sRating") is not None:
                        s_rate.append(r0["sRating"] / g0 * 100)
                if r0.get("penta"):
                    pentas += r0["penta"]
                    fpools["pentaKing"].append((r0["penta"], name, champ, f"{g0} games"))
                if r0.get("quadra"):
                    fpools["quadraKing"].append((r0["quadra"], name, champ, f"{g0} games"))
                if g0 >= MIN_GAMES_FEATURED:
                    if r0.get("kda") is not None:
                        fpools["kdaKing"].append((r0["kda"], name, champ, f"{g0} games"))
                    if r0.get("mvp") is not None:
                        fpools["mvpMachine"].append((round(r0["mvp"] / g0 * 100, 1), name, champ,
                                                    f"{r0['mvp']} MVPs in {g0} games"))
                    if r0.get("taken") is not None:
                        fpools["wall"].append((r0["taken"], name, champ, "damage taken per match"))
                    if r0.get("turret") is not None:
                        fpools["demolition"].append((r0["turret"], name, champ, "turret damage per match"))
                    if r0.get("dmg") is not None:
                        fpools["executioner"].append((r0["dmg"], name, champ, "damage per match"))
                    if r0.get("gpm") is not None:
                        fpools["economist"].append((r0["gpm"], name, champ, "gold per minute"))
                    if r0.get("tf") is not None:
                        fpools["teamfighter"].append((r0["tf"], name, champ, f"{g0} games"))
                    if r0.get("firstBlood") is not None:
                        fpools["firstStriker"].append((round(r0["firstBlood"] / g0 * 100, 1), name,
                                                      champ, f"{r0['firstBlood']} first bloods in {g0} games"))
                    if r0.get("sRating") is not None:
                        fpools["sCollector"].append((r0["sRating"], name, champ, f"{g0} games"))
            if l0 and (l0.get("games") or 0):
                fpools["marathonLegendary"].append(
                    ((l0.get("games") or 0), name, champ,
                     f"{l0['wr']:.1f}% win rate" if l0.get("wr") is not None else "Legendary Ranked"))
            if l0 and (l0.get("games") or 0) >= 10 and l0.get("wr") is not None:
                l_wr.append(l0["wr"])
                if (r0 and (r0.get("games") or 0) >= 10
                        and r0.get("wr") is not None):
                    tax_pairs.append(l0["wr"] - r0["wr"])
            if l0 and (l0.get("games") or 0) >= 15 and l0.get("wr") is not None:
                fpools["legendKiller"].append((l0["wr"], name, champ,
                                              f"{l0['games']} Legendary Ranked games"))

        top_ks = ks.most_common(1)
        top_sp = spells.most_common(1)
        top_exact = exact.most_common(1)
        slug = _slug(champ)
        champions[slug] = {
            "name": champ,
            "avgWr": _avg(wrs),
            "kda": _avg(kda), "teamfight": _avg(tf), "gpm": _avg(gpm),
            "dmgDealt": _avg(dmg), "dmgTaken": _avg(taken), "turret": _avg(turret),
            "firstBlood": _avg(fb), "mvpRate": _avg(mvp_rate), "sRate": _avg(s_rate),
            "gamesMedian": _median(games_r),
            # PAIRED, per player, both queues at 10+ games, 5+ players -- or
            # nothing. The old number was avg(legendary WR of whoever queues
            # legendary) minus avg(ranked WR of everyone), which mixes three
            # errors: the two averages cover different players, the ranked
            # side had no games floor (one 1-game 100% entry moved it), and a
            # single legendary player could mint a champion-wide "tax". A
            # paired difference is immune to all three: each player is their
            # own control.
            "legendaryTax": (round(_avg(tax_pairs), 1)
                             if len(tax_pairs) >= 5 else None),
            "legendaryTaxN": len(tax_pairs) if len(tax_pairs) >= 5 else None,
            "keystone": ({"name": top_ks[0][0], "count": top_ks[0][1], "of": len(builds)}
                         if top_ks else None),
            "spells": ({"pair": top_sp[0][0], "count": top_sp[0][1], "of": len(builds)}
                       if top_sp else None),
            "conformity": ({"count": top_exact[0][1], "of": len(builds)} if top_exact else None),
            "pentas": pentas,
            "tiers": dict(tiers.most_common()),
        }
        consensus[champ] = {
            "items": [{"slug": s, "name": ITEMS.get(s, s), "count": c, "of": len(builds)}
                      for s, c in items.most_common(10)],
            "keystones": [{"name": k, "count": c, "of": len(builds)} for k, c in ks.most_common(4)],
            "spells": [{"pair": p, "count": c, "of": len(builds)} for p, c in spells.most_common(3)],
            # The three minors the board converges on, so the advisor can be
            # shown a complete rune page rather than a keystone in isolation.
            "minors": [{"name": m, "count": c, "of": len(builds)} for m, c in minors.most_common(3)],
        }

    def top(pool: str, n: int = 1, reverse: bool = True):
        rows = sorted(pools[pool], key=lambda x: x[0], reverse=reverse)
        out = []
        for v, name, champ, detail in rows[:n]:
            out.append({"value": v, "player": name, "champion": champ,
                        "slug": _slug(champ), "detail": detail})
        return out if n > 1 else (out[0] if out else None)

    # Two DISTINCT champions required: the same display name at two ranks of
    # one board is a duplicate (snap-back re-scrape or a name collision),
    # not a multi-board master.
    multi = sorted(
        ({"player": name, "boards": sorted(v, key=lambda b: b["rank"])}
         for name, v in cross.items()
         if name and len({b["slug"] for b in v}) >= 2),
        key=lambda m: (-len(m["boards"]), min(b["rank"] for b in m["boards"])))

    champs_list = list(champions.values())
    baseline = {k: _avg([c[k] for c in champs_list])
                for k in ("kda", "teamfight", "gpm", "dmgDealt", "dmgTaken",
                          "turret", "firstBlood", "mvpRate")}

    pulse = {
        "generatedAt": time.strftime("%Y-%m-%d %H:%M"),
        "nChampions": len(champions),
        "nPlayers": n_players,
        "nBuilds": n_builds,
        "itemMeta": [{"slug": s, "name": ITEMS.get(s, s), "count": c}
                     for s, c in item_global.most_common(20)],
        "keystoneMeta": [{"name": k, "count": c} for k, c in keystone_global.most_common(10)],
        "spellMeta": [{"pair": p, "count": c} for p, c in spell_global.most_common(6)],
        # Usage tables, ordered. "least used" counts only entries that were
        # actually seen at least once -- an item nobody built is absent from
        # the data, not the bottom of the ranking.
        "treeMeta": [{"name": t, "count": c, "wr": _weighted(perf.get("tree|" + t, {"games": 0}))}
                     for t, c in tree_global.most_common()],
        "keystoneAll": [{"name": k, "count": c,
                         "wr": _weighted(perf.get("keystone|" + k, {"games": 0}))}
                        for k, c in keystone_global.most_common()],
        "minorMeta": [{"name": m, "count": c,
                       "tree": _rune_trees().get(m, ""),
                       "wr": _weighted(perf.get("minor|" + m, {"games": 0}))}
                      for m, c in minor_global.most_common()],
        "itemAll": [{"slug": s, "name": ITEMS.get(s, s), "count": c,
                     "wr": _weighted(perf.get("item|" + s, {"games": 0}))}
                    for s, c in item_global.most_common()],
        "tierComposition": dict(tier_global.most_common()),
        "champions": champions,
        "baseline": baseline,
        "hallOfFame": {
            "grinder": top("grinder"),
            "marathonRanked": top("marathonRanked"),
            "marathonLegendary": top("marathonLegendary"),
            "perfectionist": top("perfectionist"),
            "kdaKing": top("kdaKing"),
            "pentaKing": top("pentaKing"),
            "quadraKing": top("quadraKing"),
            "mvpMachine": top("mvpMachine"),
            "wall": top("wall"),
            "demolition": top("demolition"),
            "executioner": top("executioner"),
            "economist": top("economist"),
            "teamfighter": top("teamfighter"),
            "firstStriker": top("firstStriker"),
            "sCollector": top("sCollector"),
            "legendKiller": top("legendKiller"),
            "masteryRecord": top("masteryRecord"),
            "veteran": top("veteran"),
            # No "lowest account level" crown: a level-25 account inside a
            # top-50 board is a smurf or a bought account far more often than
            # a prodigy, and the record would celebrate exactly the behaviour
            # the rest of this file filters out.
            "guilds": [{"guild": g, "spots": c} for g, c in guilds.most_common(10)],
            "multiBoard": multi[:12],
        },
    }
    return pulse, consensus


# Sections computed ENTIRELY from player builds. A win-rate-only collection
# has no builds in it, so these come back empty -- not because the meta is
# empty, but because this run never looked at it.
BUILD_DERIVED = ("itemMeta", "keystoneMeta", "spellMeta", "treeMeta",
                 "keystoneAll", "minorMeta", "itemAll")


def _carry_forward(pulse: dict) -> dict:
    """Keep the last known build meta when this run collected no builds.

    EU and NA are sometimes scraped for win rates alone, which is far quicker
    than reading every player's items. That run still produces a complete and
    current win-rate board, and it must not take the item and rune tables down
    with it: zeroing them replaces real, if slightly older, data with nothing,
    empties those sections on the site, and -- because an empty JSON array
    infers as never[] -- fails the production typecheck outright.

    So when a run sees no builds at all, the build-derived sections are carried
    over from the previous file and nBuilds reports what was carried, with
    buildsFrom saying when it was measured. Everything else on the page is
    still this run's.
    """
    if pulse["nBuilds"] or not PULSE_OUT.exists():
        return pulse
    try:
        prior = json.loads(PULSE_OUT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return pulse
    if not prior.get("nBuilds"):
        return pulse
    for key in BUILD_DERIVED:
        if prior.get(key):
            pulse[key] = prior[key]
    pulse["nBuilds"] = prior["nBuilds"]
    pulse["buildsFrom"] = prior.get("buildsFrom") or prior.get("generatedAt")
    print(f"  no builds in this collection: carried {pulse['nBuilds']} builds "
          f"forward from {pulse['buildsFrom']}")
    return pulse


def main() -> int:
    pulse, consensus = build()
    pulse = _carry_forward(pulse)
    PULSE_OUT.write_text(json.dumps(pulse, ensure_ascii=False, indent=1), encoding="utf-8")
    CONSENSUS_OUT.write_text(json.dumps(consensus, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"ladder_pulse.json: {pulse['nChampions']} champions, {pulse['nPlayers']} players, "
          f"{pulse['nBuilds']} builds -> {PULSE_OUT.relative_to(ROOT)}")
    print(f"ladder_consensus.json -> {CONSENSUS_OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
