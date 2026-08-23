"""Export the champion data pipeline to a single JSON the Next.js app reads.

The Python pipeline (web/data_loader.py) stays the source of truth for all the
statistics — Bayesian shrinkage, Wilson best-player scores, tier cutoffs, OTP
detection, etc. This script runs it once and serialises everything the Next.js
frontend needs into web-next/src/data/site.json, which Next reads at build time
to statically generate the content pages.

Run after each scrape:
    python -m scripts.export_json
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from web.champion_assets import icon_url, splash_url
from web.champion_meta import champion_class, champion_difficulty, difficulty_label
from web.champion_roles import ROLES, roles_for

#: Per-champion specialisation and player tags, built from the captured
#: boards by scripts/build_specialisation.py. Absent champions fall back
#: to the old skew score so a partial build never blanks the field.
_SPEC_PATH = Path(__file__).resolve().parent.parent / "data" / "champion_specialisation.json"
_SPEC: dict = {}
if _SPEC_PATH.exists():
    import json as _json
    _SPEC = _json.loads(_SPEC_PATH.read_text(encoding="utf-8")).get("champions", {})

from web.integrity import display_name, eligible_for_title
from web.data_loader import (
    tier_order,
    assign_tier,
    assign_tier_relative,
    best_player_per_champion,
    champion_summary,
    collection_started_on,
    data_collected_on,
    funny_names,
    load_leaderboard,
    meta_breakdown,
    meta_role_strength,
    multi_champion_mains,
    off_meta_picks,
    skill_spread,
    winrate_by_difficulty,
)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "web-next" / "src" / "data" / "site.json"
PLAYERS_OUT = ROOT / "web-next" / "public" / "players.json"
TOP_N = 50

# Per-region inputs and outputs. EU keeps every unsuffixed path so the
# existing pipeline, its history and its consumers are untouched.
REGION_FILES = {
    "eu": {
        "csv": ROOT / "data" / "winrates.csv",
        "site": ROOT / "web-next" / "src" / "data" / "site.json",
        "players": ROOT / "web-next" / "public" / "players.json",
        "history": ROOT / "data" / "history" / "eu",
    },
    "na": {
        "csv": ROOT / "data" / "winrates_na.csv",
        "site": ROOT / "web-next" / "src" / "data" / "site_na.json",
        "players": ROOT / "web-next" / "public" / "players-na.json",
        "history": ROOT / "data" / "history" / "na",
    },
}
REGION_CSV: Path | None = None   # None = EU default inside data_loader


HISTORY = ROOT / "data" / "history" / "eu"
REGION = "eu"


def _slug(name: str) -> str:
    import re
    s = name.lower().replace("&", "and").replace("'", "")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def _snapshot_date(collected_on: str | None) -> str:
    """Parse 'June 13, 2026' -> '2026-06-13'; fall back to today."""
    if collected_on:
        for fmt in ("%B %d, %Y", "%b %d, %Y"):
            try:
                return datetime.strptime(collected_on, fmt).date().isoformat()
            except ValueError:
                pass
    return date.today().isoformat()


def _prev_role_tiers(prev_snap: dict) -> dict[str, str]:
    """{slug: role tier} for the baseline snapshot, from what it STORED.

    This used to rebuild the cohort from the snapshot's win rates and re-rank
    it. That cannot work, for two reasons found by checking the output against
    the deployed site:

      * role tiers are percentile ranks WITHIN a role, so one champion changing
        role moves everyone's rank. Riven alone moving Baron -> Jungle between
        the August collections re-banded five of the six champions spot-checked.
      * snapshots store win rates rounded to one decimal, and the live ranking
        uses full precision. Rounding creates ties exactly at the boundaries
        where the band is decided.

    So the role tier is stored, not derived. Snapshots older than that key were
    backfilled from the deployed site they produced; anything that still lacks
    it reports no role movement at all, which is honest, rather than a
    reconstructed guess that reads as fact.
    """
    return {slug: row["tierRole"] for slug, row in prev_snap.items()
            if row.get("tierRole")}


def _save_snapshot(champions: list[dict], collected_on: str | None,
                   wr_offset: float = 0.0) -> None:
    """Write a dated, raw-win-rate snapshot so we can chart patch-over-patch later.
    Keyed by data date, so re-running on the same scrape overwrites (idempotent)."""
    HISTORY.mkdir(parents=True, exist_ok=True)
    d = _snapshot_date(collected_on)
    snap = {
        "date": d,
        "region": REGION,
        # The offset this collection was centred with. Win rates below are RAW;
        # the site shows raw + offset. Movement has to be measured in the units
        # the reader is looking at, so the delta needs both collections' offsets.
        "wrOffset": wr_offset,
        # role and tierRole are stored as well as the all-roles tier, because
        # the ROLE tier is the one a reader is looking at whenever a role
        # filter is on, and 63 of 141 champions currently sit in a different
        # band there than they do in the combined list. Older snapshots predate
        # these keys; _prev_role_tiers rebuilds them from the win rates.
        "champions": {
            c["slug"]: {"wr": c["wr"], "tier": c["tier"],
                        "tierRole": c.get("tierRole"), "role": c.get("role")}
            for c in champions if c.get("wr") is not None
        },
    }
    (HISTORY / f"{d}.json").write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  snapshot: {HISTORY.relative_to(ROOT).as_posix()}/{d}.json "
          f"({len(snap['champions'])} champions)")


def _is_otp(name: str, row) -> bool:
    """OTP badge, decided by the share measure the card now shows.

    Curated intent is preserved: KNOWN_OTP_CHAMPIONS still badges a champion the
    share does not catch, and NON_OTP_CHAMPIONS still overrules everything. A
    champion with no specialisation record keeps whatever the pipeline decided,
    so a partial capture set never silently strips badges.
    """
    from web.data_loader import KNOWN_OTP_CHAMPIONS, NON_OTP_CHAMPIONS
    if name in NON_OTP_CHAMPIONS:
        return False
    spec = _SPEC.get(name)
    if not spec:
        return bool(row.get("is_otp", False))
    return "otp" in (spec.get("tags") or []) or name in KNOWN_OTP_CHAMPIONS


def _f(v, ndigits: int = 1):
    """Float or None, rounded."""
    if v is None or pd.isna(v):
        return None
    return round(float(v), ndigits)


def _i(v):
    if v is None or pd.isna(v):
        return None
    return int(round(float(v)))


def build() -> dict:
    df = load_leaderboard(csv_path=REGION_CSV)
    if df.empty:
        raise SystemExit(f"{(REGION_CSV or 'data/winrates.csv')} is empty — scrape first.")

    summary = champion_summary(df)
    summary = summary[summary["weighted_winrate"].notna()].copy()
    summary["role"] = summary["champion"].apply(lambda c: roles_for(c)[0])

    # Pool depths for the tier list's "All / Top 25 / Top 10 / Top 5" toggle.
    # Each depth is the same pipeline on a shallower slice of the board, and
    # each is centred with ITS OWN offset: shallower pools have higher raw
    # averages (the best players of the best players), and reusing the
    # 50-player offset would make every champion look 2-3 points stronger the
    # moment the toggle moved. EU only -- the CN numbers are Tencent's own
    # bracket aggregates, which have no per-player rows to re-slice.
    POOL_DEPTHS = (25, 10, 5)
    pool_summaries = {}
    for depth in POOL_DEPTHS:
        ps = champion_summary(df, top_n=depth)
        ps = ps[ps["weighted_winrate"].notna()].copy()
        ps["role"] = ps["champion"].apply(lambda c: roles_for(c)[0])
        pool_summaries[depth] = ps

    # Per-role win-rate pools for role-relative tiers.
    role_pools = {
        role: summary[summary["role"] == role]["weighted_winrate"].astype(float).tolist()
        for role in summary["role"].unique()
    }

    # Skill spread (ceiling vs weighted), keyed by champion.
    spread = skill_spread(df, summary)
    spread_by_champ = dict(zip(spread["champion"], spread["skill_spread"]))

    # Best player per champion (Wilson), flagged across the whole pool.
    best_df = best_player_per_champion(df)
    best_flagged = best_df[best_df["is_best_for_champ"]]
    best_by_champ = {}
    for _, b in best_flagged.iterrows():
        best_by_champ[str(b["champion"])] = {
            "player": str(b["player_name"]),
            "rank": _i(b.get("rank")),
            "confidence_wr": _f(b.get("confidence_wr")),
        }

    # Off-meta champions (pickrate logic) — store as an ordered slug list.
    off_meta = off_meta_picks(df)
    off_meta_slugs = [_slug(str(c)) for c in off_meta["champion"].tolist()]

    # Per-depth (wr, tier, tierRole), centred per depth, tiers from the same
    # threshold functions as the main list so a toggle never invents a new
    # tier scale.
    pools_by_champ: dict[str, dict] = {}
    for depth, ps in pool_summaries.items():
        vals = ps["weighted_winrate"].astype(float)
        offset = round(50 - vals.mean(), 1) if len(vals) else 0.0
        # Tiers are assigned on RAW win rates -- assign_tier's buckets are
        # raw-scale, exactly as the main list does it -- and only the DISPLAY
        # value is centred. Centring first would land everything in the bottom
        # tiers. assign_tier_relative is percentile-based, so raw vs centred
        # is indifferent there; raw keeps the two calls consistent.
        depth_role_pools = {
            role: ps[ps["role"] == role]["weighted_winrate"].astype(float).tolist()
            for role in ps["role"].unique()
        }
        for _, r in ps.iterrows():
            wr_raw = float(r["weighted_winrate"])
            label, css = assign_tier(wr_raw)
            r_label, r_css = assign_tier_relative(wr_raw, depth_role_pools[r["role"]])
            pools_by_champ.setdefault(str(r["champion"]), {})[str(depth)] = {
                "wr": _f(wr_raw + offset),
                # The offset this depth was centred with, so the UI can undo it
                # and show the raw number. Each depth has its own (shallower
                # pools average higher), and without it stored a centred value
                # cannot be turned back into a raw one: the raw mean is gone.
                "wrOffset": offset,
                "nPlayers": _i(r.get("n_players")),
                "tier": label, "tierCss": css,
                "tierRole": r_label, "tierRoleCss": r_css,
            }

    champions = []
    for _, r in summary.sort_values("weighted_winrate", ascending=False).iterrows():
        name = str(r["champion"])
        role = r["role"]
        wr = float(r["weighted_winrate"])
        tier_label, tier_css = assign_tier(wr)
        tier_role_label, tier_role_css = assign_tier_relative(wr, role_pools[role])
        diff = champion_difficulty(name)
        diff_word = difficulty_label(diff)
        champions.append({
            "name": name,
            "slug": _slug(name),
            "role": role,
            "class": champion_class(name),
            "difficulty": int(diff),
            "difficultyLabel": diff_word,
            "isHard": diff_word in ("Hard", "Very Hard"),
            "wr": _f(wr),
            "meanWr": _f(r.get("mean_winrate")),
            "maxWr": _f(r.get("max_winrate")),
            "winrateStd": _f(r.get("winrate_std"), 2),
            "medianGames": _i(r.get("median_games")),
            "totalGames": _i(r.get("total_games")),
            "nPlayers": _i(r.get("n_players")),
            "medianMastery": _i(r.get("median_mastery")),
            "maxScore": _i(r.get("max_score")),
            # otpScore is now the MEDIAN SHARE of a main's ranked games spent on
            # this champion (data/champion_specialisation.json), which answers
            # "is this board specialists" directly. The previous score measured
            # skew WITHIN a board -- a property of the player pool, not the
            # champion -- and misfired badly: Hecarim scored 78.6 on it while
            # only 18% of a Hecarim main's ranked games are on Hecarim. It is
            # kept as otpScoreSkew rather than deleted, because the tier
            # explanations and the OTP badge were built against its scale.
            "otpScore": _f((_SPEC.get(name) or {}).get("otpScore"),
                           ) if _SPEC.get(name) else _f(r.get("otp_score")),
            "otpScoreSkew": _f(r.get("otp_score")),
            "specialisationShare": _f((_SPEC.get(name) or {}).get("specialisationShare")),
            "heavyOtpShare": _f((_SPEC.get(name) or {}).get("heavyOtpShare")),
            "contestedGap": _i((_SPEC.get(name) or {}).get("contestedGap")),
            # otp / comfort / contested / generalist -- see the _tags block in
            # data/champion_specialisation.json for what each one means.
            "playerTags": (_SPEC.get(name) or {}).get("tags") or [],
            # The badge follows the SAME measure the card displays. It used to
            # run off the old skew score, which disagreed with the new one on 5
            # of 19 badged champions and rated Kennen -- the most specialised
            # board on the roster -- at 12.1. The curated lists still win:
            # KNOWN_OTP_CHAMPIONS can badge a champion the share misses, and
            # NON_OTP_CHAMPIONS overrules everything. Champions with no
            # specialisation record keep the old flag rather than losing a badge
            # to missing data.
            "isOtp": _is_otp(name, r),
            # display_name, not raw: rank 1 is occasionally an advert, and this
            # string lands on every champion card.
            "topPlayer": (display_name(str(r["top_player"])) if pd.notna(r.get("top_player")) else None),
            "tier": tier_label,
            "tierCss": tier_css,
            "tierRole": tier_role_label,
            "tierRoleCss": tier_role_css,
            "skillSpread": _f(spread_by_champ.get(name)),
            "icon": icon_url(name),
            "splash": splash_url(name),
            "bestPlayer": best_by_champ.get(name),
            # "All" is the top-level wr/tier; these are the shallower slices.
            "pools": pools_by_champ.get(name) or None,
        })

    meta = [
        {
            "class": m["champ_class"],
            "wr": _f(m["wr"]),
            "nChampions": int(m["n_champions"]),
            "totalGames": int(m["total_games"]),
        }
        for m in meta_breakdown(df)
    ]

    by_diff = [
        {
            "difficulty": d["difficulty"],
            "wr": _f(d["wr"]),
            "nChampions": int(d["n_champions"]),
        }
        for d in winrate_by_difficulty(summary)
    ]

    role_strength = {}
    for role, st in meta_role_strength(df, top_n_per_role=10).items():
        if st is None:
            continue
        role_strength[role] = {
            "wr": _f(st["wr"]),
            "lowConfidence": bool(st.get("low_confidence", False)),
        }

    mains = [
        {
            "player": m["player_name"],
            "nChampions": m["n_champions"],
            "champions": m["champions"],
            "avgWr": _f(m["avg_winrate"]),
            "bestRank": m["best_rank"],
            "firstChampionIcon": icon_url(m["champions"][0]) if m["champions"] else None,
        }
        for m in multi_champion_mains(df, min_champions=3)[:18]
    ]

    funny = [
        {
            "player": f["player_name"],
            "champion": f["champion"],
            "icon": icon_url(f["champion"]),
        }
        for f in funny_names(df, limit=18)
    ]

    # Top of the leaderboard — highest champion-mastery scores across the
    # whole top-50 pool, deduped by player (keep their single highest).
    pool = df[df["rank"] <= TOP_N].dropna(subset=["score"]).copy()
    pool = pool.sort_values("score", ascending=False)
    top_mastery = []
    seen_players: set[str] = set()
    for _, r in pool.iterrows():
        name = str(r["player_name"]) if pd.notna(r.get("player_name")) else "—"
        if name in seen_players:
            continue
        # Highest mastery is a named showcase; skip accounts that cannot be
        # crowned rather than printing them with a hidden name.
        if not eligible_for_title(name):
            continue
        seen_players.add(name)
        champ = str(r["champion"])
        top_mastery.append({
            "player": name,
            "champion": champ,
            "slug": _slug(champ),
            "icon": icon_url(champ),
            "score": _i(r.get("score")),
            "wr": _f(r.get("winrate")),
        })
        if len(top_mastery) >= 8:
            break

    # EU movement since the previous collection, computed RAW vs RAW before any
    # centering: both snapshots store raw win rates, and the display offset
    # differs per collection, so centred-vs-centred would smuggle the offset
    # difference into every delta. This is what the tier list's riser/faller
    # badges read.
    # The cutoff is when this collection STARTED, not when it finished.
    #
    # A collection is a multi-day run -- the 141-champion August pass ran from
    # the 17th to the 20th -- and export_json writes a snapshot every time it
    # is run. Cutting at the finish date therefore selected a snapshot from
    # INSIDE the same run as the baseline: on 2026-08-20 it picked 2026-08-19,
    # which held the same captures, so Diana read S -> S with a 0.0 delta and
    # wore no badge, when against the previous real collection she had gone
    # A -> S. Only the 15 champions extracted between the two exports showed
    # any movement at all, which is a report on our scraping schedule rather
    # than on the meta.
    #
    # Cutting at the start date skips every snapshot belonging to this run and
    # lands on the previous collection, which is what "since" means to a reader.
    current_key = _snapshot_date(data_collected_on(df))
    cutoff = collection_started_on(df) or current_key
    # Computed here rather than at the centering step below, because movement
    # is measured in centred units and needs it before the comparison.
    _valid = [c["wr"] for c in champions if c["wr"] is not None]
    wr_offset = round(50 - sum(_valid) / len(_valid), 1) if _valid else 0.0
    prev_date, prev_snap, prev_snap_meta = None, {}, {}
    for f in sorted(HISTORY.glob("*.json")):
        d = f.stem
        if d < cutoff:
            try:
                doc = json.loads(f.read_text(encoding="utf-8"))
                snap_champs = doc["champions"]
            except (json.JSONDecodeError, KeyError, OSError):
                continue
            # export_json writes a snapshot every time it runs, including the
            # mid-collection runs that exist to publish partial data early.
            # Such a snapshot covers a fraction of the roster (NA 8 August: 74
            # of 141) and is not a collection to measure against.
            if len(snap_champs) < 0.9 * len(champions):
                print(f"  note: snapshot {d} covers {len(snap_champs)} of "
                      f"{len(champions)} champions; not a baseline")
                continue
            prev_date, prev_snap, prev_snap_meta = d, snap_champs, doc
    # Tier movement gates the ARROW badge; the wr delta is the fine print. A
    # tier is what the list is ABOUT, so "riser" means crossed a tier boundary,
    # not wobbled half a point inside one.
    tier_rank = {label: i for i, (label, _css) in enumerate(tier_order())}
    # The ROLE tier is what the reader sees whenever a role filter is on, and
    # it is a different band for 63 of 141 champions. Comparing the all-roles
    # tier there produced a badge that contradicted the list it sat in:
    # Kassadin shows GOD under Mid, and wore a "GOD -> S" arrow taken from the
    # combined ranking, where he really had dropped.
    prev_role_tier = _prev_role_tiers(prev_snap)

    # THE DELTA IS IN THE UNITS THE READER SEES.
    #
    # Both snapshots store RAW win rates, and the site shows raw + a per-
    # collection offset that centres the field on 50%. Subtracting raw from raw
    # produced a number that cannot be checked against anything on the page:
    # Jayce reads 51.6% on the previous collection and 52.8% on this one, an
    # obvious +1.2, and the badge said +0.4 because the offset moved 0.8 between
    # them. Worse, +0.4 fell under the 0.5 display threshold, so the champion
    # showed no movement at all.
    #
    # Centred-vs-centred is also the more honest measure for a list that
    # presents every number as "relative to the average champion": it says this
    # champion gained a point ON THE FIELD, not that the whole field drifted.
    prev_offset = prev_snap_meta.get("wrOffset")
    if prev_offset is None and prev_snap:
        # Older snapshots predate the key, but they store the raw win rates the
        # offset is a function of, and the formula is the one line above: the
        # baseline's offset is recomputed the same way, so the delta stays in
        # centred units instead of quietly reverting to raw-vs-raw.
        _prev_valid = [row.get("wr") for row in prev_snap.values() if row.get("wr") is not None]
        prev_offset = round(50 - sum(_prev_valid) / len(_prev_valid), 1) if _prev_valid else wr_offset
        print(f"  note: snapshot {prev_date} has no wrOffset; recomputed as {prev_offset}")
    elif prev_offset is None:
        prev_offset = wr_offset
    for c in champions:
        prev = prev_snap.get(c["slug"]) or {}
        prev_wr_val = prev.get("wr")
        c["wrDelta"] = (round((c["wr"] + wr_offset) - (prev_wr_val + prev_offset), 1)
                        if c.get("wr") is not None and prev_wr_val is not None else None)

        def _move(prev_label, cur_label):
            """(prevTier or None, "up"/"down"/None) for one pair of bands."""
            a, b = tier_rank.get(prev_label), tier_rank.get(cur_label)
            if a is None or b is None or a == b:
                return None, None
            return prev_label, ("up" if b < a else "down")

        c["prevTier"], c["tierMoved"] = _move(prev.get("tier"), c.get("tier"))
        c["prevTierRole"], c["tierRoleMoved"] = _move(
            prev_role_tier.get(c["slug"]), c.get("tierRole"))

    # Center the champion win-rate figures on 50% (relative to the pool average).
    # These are each champion's top-50 mains, so raw win rates all sit above 50%
    # and people keep asking why. A constant shift keeps every tier, ordering and
    # gap identical while making the numbers read like a normal tier list.
    # Player-level metrics (best player, top mastery, the leaderboard) stay raw —
    # those are explicit "this player's actual record" contexts.
    # Snapshot raw (pre-centering) win rates for patch-over-patch history.
    _save_snapshot(champions, data_collected_on(df), wr_offset)

    # Shift only the champion *average* (wr, meanWr). maxWr is the ceiling — a
    # single best player's real win rate — and stays raw like the best-player stat.
    for c in champions:
        for k in ("wr", "meanWr"):
            if c.get(k) is not None:
                c[k] = round(c[k] + wr_offset, 1)

    # The class / role / difficulty aggregates are (games-weighted) averages of
    # the same champion win rates, so shift them by the same offset — otherwise a
    # class average would read ~62% next to a #1 champion at ~56% on one page.
    for m in meta:
        if m["wr"] is not None:
            m["wr"] = round(m["wr"] + wr_offset, 1)
    for d in by_diff:
        if d["wr"] is not None:
            d["wr"] = round(d["wr"] + wr_offset, 1)
    for st in role_strength.values():
        if st["wr"] is not None:
            st["wr"] = round(st["wr"] + wr_offset, 1)

    return {
        "collectedOn": data_collected_on(df),
        # the snapshot the tier list's riser/faller badges compare against
        "movementSince": prev_date,
        "roles": list(ROLES),
        "nChampions": len(champions),
        "nPlayers": int(len(df)),
        "wrOffset": wr_offset,
        "champions": champions,
        "metaBreakdown": meta,
        "winrateByDifficulty": by_diff,
        "roleStrength": role_strength,
        "multiChampionMains": mains,
        "funnyNames": funny,
        "offMetaSlugs": off_meta_slugs,
        "topMastery": top_mastery,
    }


def build_players() -> dict:
    """Per-champion top-50 player rows for the leaderboard, keyed by slug.

    Compact short keys keep the file small (it's served as a static asset the
    leaderboard page fetches on demand): r=rank, p=player, w=winrate,
    g=games, s=score (mastery).
    """
    # The board is a mirror of the game, so boosting accounts keep their ROW
    # (ranks stay contiguous) with the name hidden -- unlike every statistic,
    # which drops them entirely. See web/integrity.py.

    df = load_leaderboard(unfiltered=True, csv_path=REGION_CSV)
    if df.empty:
        return {}
    top = df[df["rank"] <= TOP_N].copy()
    out: dict[str, list[dict]] = {}
    for champ, g in top.groupby("champion"):
        rows = []
        for _, r in g.sort_values("rank").iterrows():
            rows.append({
                "r": _i(r.get("rank")),
                "p": display_name(str(r["player_name"])) if pd.notna(r.get("player_name")) else "—",
                "w": _f(r.get("winrate")),
                "g": _i(r.get("games")),
                "s": _i(r.get("score")),
            })
        out[_slug(str(champ))] = rows
    return out


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--region", default="eu", choices=sorted(REGION_FILES),
                    help="Which region's winrates to export (default: eu)")
    args = ap.parse_args()

    global OUT, PLAYERS_OUT, HISTORY, REGION_CSV, REGION
    REGION = args.region
    files = REGION_FILES[args.region]
    # the specialisation table is per region (scripts/build_specialisation.py
    # --region na); fall back to the EU table only when NA's was never built
    global _SPEC
    if args.region != "eu":
        regional = _SPEC_PATH.with_name(f"champion_specialisation_{args.region}.json")
        if regional.exists():
            import json as _json
            _SPEC = _json.loads(regional.read_text(encoding="utf-8")).get("champions", {})
            print(f"specialisation: {regional.name}")
        else:
            print(f"WARNING: {regional.name} missing; one-trick shares fall back to the EU table")
    # EU passes None so data_loader keeps its own default; a region passes its
    # CSV explicitly.
    REGION_CSV = None if args.region == "eu" else files["csv"]
    OUT, PLAYERS_OUT, HISTORY = files["site"], files["players"], files["history"]
    print(f"region: {args.region.upper()}")

    data = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    size_kb = OUT.stat().st_size / 1024
    print(f"wrote {OUT.relative_to(ROOT)} ({size_kb:.0f} KB, {data['nChampions']} champions)")

    players = build_players()
    PLAYERS_OUT.parent.mkdir(parents=True, exist_ok=True)
    PLAYERS_OUT.write_text(json.dumps(players, ensure_ascii=False), encoding="utf-8")
    p_kb = PLAYERS_OUT.stat().st_size / 1024
    n_rows = sum(len(v) for v in players.values())
    print(f"wrote {PLAYERS_OUT.relative_to(ROOT)} ({p_kb:.0f} KB, {n_rows} player rows)")


if __name__ == "__main__":
    main()
