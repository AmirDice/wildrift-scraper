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
from web.data_loader import (
    assign_tier,
    assign_tier_relative,
    best_player_per_champion,
    champion_summary,
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


HISTORY = ROOT / "data" / "history" / "eu"


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


def _save_snapshot(champions: list[dict], collected_on: str | None) -> None:
    """Write a dated, raw-win-rate snapshot so we can chart patch-over-patch later.
    Keyed by data date, so re-running on the same scrape overwrites (idempotent)."""
    HISTORY.mkdir(parents=True, exist_ok=True)
    d = _snapshot_date(collected_on)
    snap = {
        "date": d,
        "region": "eu",
        "champions": {
            c["slug"]: {"wr": c["wr"], "tier": c["tier"]}
            for c in champions if c.get("wr") is not None
        },
    }
    (HISTORY / f"{d}.json").write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  snapshot: data/history/eu/{d}.json ({len(snap['champions'])} champions)")


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
    df = load_leaderboard()
    if df.empty:
        raise SystemExit("data/winrates.csv is empty — scrape first.")

    summary = champion_summary(df)
    summary = summary[summary["weighted_winrate"].notna()].copy()
    summary["role"] = summary["champion"].apply(lambda c: roles_for(c)[0])

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
            "otpScore": _f(r.get("otp_score")),
            "isOtp": bool(r.get("is_otp", False)),
            "topPlayer": (str(r["top_player"]) if pd.notna(r.get("top_player")) else None),
            "tier": tier_label,
            "tierCss": tier_css,
            "tierRole": tier_role_label,
            "tierRoleCss": tier_role_css,
            "skillSpread": _f(spread_by_champ.get(name)),
            "icon": icon_url(name),
            "splash": splash_url(name),
            "bestPlayer": best_by_champ.get(name),
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

    # Center the champion win-rate figures on 50% (relative to the pool average).
    # These are each champion's top-50 mains, so raw win rates all sit above 50%
    # and people keep asking why. A constant shift keeps every tier, ordering and
    # gap identical while making the numbers read like a normal tier list.
    # Player-level metrics (best player, top mastery, the leaderboard) stay raw —
    # those are explicit "this player's actual record" contexts.
    # Snapshot raw (pre-centering) win rates for patch-over-patch history.
    _save_snapshot(champions, data_collected_on(df))

    # Shift only the champion *average* (wr, meanWr). maxWr is the ceiling — a
    # single best player's real win rate — and stays raw like the best-player stat.
    valid = [c["wr"] for c in champions if c["wr"] is not None]
    wr_offset = round(50 - sum(valid) / len(valid), 1) if valid else 0.0
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
    from web.integrity import display_name

    df = load_leaderboard(include_boosters=True)
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
