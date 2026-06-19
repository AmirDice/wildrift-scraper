"""Data loaders for the Streamlit frontend.

The CSV produced by `src.scrape_timed` lives at `data/winrates.csv` with
columns: champion, rank, player_name, score, games, winrate, captured_at.

Loaders are cached for 60 seconds so the app stays snappy but still picks
up newly scraped rows reasonably soon.

Two winrate philosophies live here, deliberately different:

  * CHAMPION winrate (`weighted_winrate`) answers "what can this champion
    actually do at a high level?". Three-step pipeline over the top-50
    players (see `champion_summary`):
      1. entry floor    — adaptive per champion: FLOOR_FRACTION x that
                          champion's median games, clamped to
                          [FLOOR_MIN, FLOOR_MAX] (quality gate);
      2. Bayesian shrink — each player's WR is pulled toward the champion's
                          own high-elo prior by SHRINKAGE_C games of fake
                          evidence:  adj = (wins + C*prior) / (games + C);
      3. capped weighting — weights are min(games, champion's p75 games), so
                          a spammer is capped relative to their own peers.

  * BEST-PLAYER score (`confidence_wr`) answers "who is genuinely the best
    on this champion?". It is the Wilson score lower bound of each player's
    win proportion — the conservative end of a 95% confidence interval.
    A small sample widens the interval and pushes the lower bound down, so
    you can't win the title on 3 lucky games, but a 25-game 88% run (a real
    22-3 record) legitimately ranks high.
"""
from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
import streamlit as st


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
LEADERBOARD_CSV = DATA_DIR / "winrates.csv"

# Shown in place of names the OCR couldn't read (usually CJK display names).
UNNAMED_PLACEHOLDER = "SomeChineseName"

# We rank and aggregate over the top this-many players per champion.
TOP_N_PLAYERS = 50

# --- Champion-winrate pipeline constants ------------------------------
# Play volume differs WILDLY per champion (live data 2026-06-10: median
# games 46 on Kha'Zix vs 163 on Aatrox), so the entry floor and the weight
# cap are derived from EACH CHAMPION'S OWN games distribution rather than
# one global number. A global 30-game floor was cutting 14% of Kha'Zix's
# pool while a global 150 cap bound half of Katarina's.
#
# Shrinkage strength: "how many games of evidence before I believe a
# player's own WR over the champion average?" 30 suits Wild Rift's top
# players (typically 50-300 champ games).
SHRINKAGE_C = 30
# Entry floor per champion = FLOOR_FRACTION x that champion's median games,
# clamped to [FLOOR_MIN, FLOOR_MAX]. The absolute clamp matters: below ~15
# games a winrate is statistical noise no matter how niche the champion,
# and above 30 we'd be gatekeeping harder than "top player" requires.
FLOOR_FRACTION = 0.30
FLOOR_MIN = 15
FLOOR_MAX = 30
# Weight cap per champion = that champion's CAP_QUANTILE games value (p75),
# never less than 2x the floor. Caps scale with each champion's economy:
# on Katarina (median 157g) only true outliers hit the cap; on Mel
# (p75 78g) it binds at 78.
CAP_QUANTILE = 0.75


def _wilson_lower_bound(wins: float, n: float, z: float = 1.96) -> float:
    """Lower bound of the Wilson score interval for a binomial proportion.

    Returns a value in [0, 1]. With z=1.96 this is the bottom of the 95%
    confidence interval: "we're 97.5% confident the true win rate is at
    least this high". Small n -> wide interval -> low bound, which is what
    discounts tiny-sample high win rates.
    """
    if n <= 0:
        return 0.0
    phat = wins / n
    denom = 1.0 + z * z / n
    centre = phat + z * z / (2 * n)
    margin = z * math.sqrt((phat * (1 - phat) + z * z / (4 * n)) / n)
    return max(0.0, (centre - margin) / denom)


def _adaptive_floor(games: pd.Series, champions: pd.Series) -> pd.Series:
    """Per-row entry floor derived from each champion's own play volume:
    FLOOR_FRACTION x the champion's median games, clamped to
    [FLOOR_MIN, FLOOR_MAX]. Rows of the same champion share one floor."""
    med = games.groupby(champions).transform("median")
    return (FLOOR_FRACTION * med).clip(FLOOR_MIN, FLOOR_MAX)


# Champions with an OTP score at or above this threshold get the "OTP" badge
# in the Champions table and on tier-list icons.
OTP_BADGE_THRESHOLD = 85.0

# Champions universally known as OTP picks regardless of what the algorithmic
# score says. Used because (a) some champions are OTP-magnets even if their
# current top-50 games distribution hasn't fully captured the skew, and (b)
# community knowledge of "this champion attracts one-tricks" is hard to fully
# encode in a single statistic.
KNOWN_OTP_CHAMPIONS: frozenset[str] = frozenset({
    "Akali", "Draven", "Graves", "Irelia", "Kalista", "Katarina", "Kayle",
    "Kennen", "Kindred", "Master Yi", "Nasus", "Nilah", "Pyke", "Rengar",
    "Riven", "Singed", "Urgot", "Yasuo", "Zoe",
})

# Champions the algorithmic score sometimes flags but community knowledge says
# aren't OTP picks (utility frontliners that happen to have a heavy-tail games
# distribution because the top engage tanks grind a LOT). Explicit blocklist
# wins over both the algorithm AND the KNOWN_OTP_CHAMPIONS set.
NON_OTP_CHAMPIONS: frozenset[str] = frozenset({
    "Ornn",
})


def _gini_coefficient(values: list[float]) -> float:
    """Gini coefficient of the games distribution. 0 = perfectly equal,
    1 = one player has everything. Higher means more concentrated on a few
    heavy-grinder OTPs."""
    vals = sorted(v for v in values if v > 0)
    n = len(vals)
    if n == 0:
        return 0.0
    total = sum(vals)
    if total == 0:
        return 0.0
    cumsum = sum((2 * i - n - 1) * v for i, v in enumerate(vals, 1))
    return cumsum / (n * total)


def _otp_score(games: pd.Series) -> float | None:
    """A 0-100 'OTP-ness' score from the games distribution.

    Combines three skew signals:
      * max/median ratio  — how far the top grinder pulls away from typical
      * p90/median ratio  — how heavy the right tail is
      * Gini coefficient  — overall inequality across the pool

    `tanh`-bounded so a typical champion sits near 50 and true OTP champions
    approach 100. Anti-OTP "comfort" champions land around 15-30.
    """
    g = games.dropna().astype(float)
    if len(g) < 20:
        return None
    med = float(g.median())
    if med <= 0:
        return None
    max_med = float(g.max()) / med
    p90_med = float(g.quantile(0.9)) / med
    gini = _gini_coefficient(g.tolist())
    # Recentred so a "typical" Wild Rift top-50 distribution sits near 35-50.
    # Wider offsets make the score more selective — only genuinely heavy-tailed
    # champions (max/median above 6, gini above 0.35) approach 90+.
    raw = 0.4 * (max_med - 6) + 0.2 * (p90_med - 3) + 1.0 * gini
    return round(50.0 * (math.tanh(raw) + 1.0), 1)


@st.cache_data(ttl=60)
def load_leaderboard() -> pd.DataFrame:
    """Return the full scraped leaderboard CSV as a DataFrame.

    Empty DataFrame (with the expected columns) if the file doesn't exist.
    Numeric columns are coerced to numbers; bad values become NaN.
    Malformed rows (e.g. two records that got stuck on the same line because
    the scraper was interrupted mid-write) are SKIPPED with a warning rather
    than crashing the whole page render.
    """
    cols = ["champion", "rank", "player_name", "score", "games", "winrate", "captured_at"]
    if not LEADERBOARD_CSV.exists():
        return pd.DataFrame(columns=cols)

    try:
        df = pd.read_csv(LEADERBOARD_CSV, on_bad_lines="skip")
    except Exception:
        # Last-resort fallback: the python engine is slower but far more
        # forgiving (e.g. tolerates inconsistent line endings).
        df = pd.read_csv(LEADERBOARD_CSV, on_bad_lines="skip", engine="python")
    for col in ("rank", "score", "games"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    if "winrate" in df.columns:
        df["winrate"] = pd.to_numeric(df["winrate"], errors="coerce")

    # Names the OCR couldn't read (blank, whitespace, or pure punctuation) are
    # almost always non-Latin display names — CJK etc. — that Tesseract dropped.
    # Standardise them to one honest placeholder.
    if "player_name" in df.columns:
        df["player_name"] = df["player_name"].apply(_clean_player_name)

    # Champion names — fix OCR casing drift ("smolder", "Kai'sa") so every
    # downstream lookup (role, class, icon, splash) hits the canonical entry.
    if "champion" in df.columns:
        df["champion"] = df["champion"].apply(_canonicalize_champion)
    return df


def _canonicalize_champion(value) -> str | None:
    """Map a scraped champion name to its canonical display form.

    Tesseract sometimes drops case ("smolder", "Kai'sa") even when the rest
    of the OCR pipeline matched correctly, so the CSV contains variants.
    This rescues them via the same normalization the OCR matcher uses.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return value
    from src.champions import NORMALIZED_TO_CANONICAL, _normalize
    canonical = NORMALIZED_TO_CANONICAL.get(_normalize(str(value)))
    return canonical if canonical else str(value)


def _clean_player_name(value) -> str:
    """Return a cleaned display name, or the CJK placeholder when the OCR
    produced nothing usable (empty / whitespace / punctuation-only)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return UNNAMED_PLACEHOLDER
    text = str(value).strip()
    # Strip to alphanumerics to test for "real" content; names that are only
    # symbols/garbage become the placeholder.
    if not any(ch.isalnum() for ch in text):
        return UNNAMED_PLACEHOLDER
    return text


def get_champions(df: pd.DataFrame) -> list[str]:
    """Sorted list of distinct champions present in the data."""
    if df.empty or "champion" not in df.columns:
        return []
    return sorted(df["champion"].dropna().unique().tolist())


def data_collected_on(df: pd.DataFrame) -> str | None:
    """Human-readable date the leaderboard snapshot was scraped.

    Uses the latest `captured_at` timestamp in the data (the most recent
    scrape pass). Returns e.g. "June 13, 2026", or None if unavailable.
    """
    if df.empty or "captured_at" not in df.columns:
        return None
    caps = pd.to_datetime(df["captured_at"], errors="coerce", utc=True).dropna()
    if caps.empty:
        return None
    d = caps.max()
    return f"{d.strftime('%B')} {d.day}, {d.year}"


# Tier cutoffs are calibrated for the GAMES-WEIGHTED top-50 winrate, which
# clusters roughly 55-65% in practice once smurf inflation is stripped out.
# Bands tightened so the bottom actually populates instead of leaving Ass
# permanently empty. (tier label, css class, min weighted winrate)
_TIER_BUCKETS: list[tuple[str, str, float]] = [
    ("GOD", "tier-god", 63.0),  # ~top 8%   (only the standout meta tyrants)
    ("S",   "tier-s",   61.0),  # 8-22%
    ("A",   "tier-a",   59.0),  # 22-44%
    ("B",   "tier-b",   57.0),  # 44-66%
    ("C",   "tier-c",   56.0),  # 66-78%
    ("Ass", "tier-ass",  0.0),  # bottom (<56%) -- weak even at top-50 level
]


def assign_tier(winrate: float | None) -> tuple[str, str]:
    """Return (label, css_class) for a champion's weighted winrate.

    Returns ("?", "tier-unknown") if winrate is None / NaN. Buckets are
    walked highest-to-lowest, so the first matching threshold wins.
    """
    if winrate is None or pd.isna(winrate):
        return ("?", "tier-unknown")
    for label, klass, threshold in _TIER_BUCKETS:
        if winrate >= threshold:
            return (label, klass)
    return ("Ass", "tier-ass")  # unreachable, last bucket has threshold 0


def tier_order() -> list[tuple[str, str]]:
    """Return [(label, css_class)] in display order (top-tier first)."""
    return [(lbl, klass) for lbl, klass, _ in _TIER_BUCKETS]


# Percentile-based tier cutoffs for ROLE-FILTERED views. Within a single
# role the absolute cutoffs (GOD = 63%+) leave most roles with no GOD or
# no Ass champion because the role's WR range is naturally narrower than
# the cross-role pool. These percentiles guarantee every role gets a full
# tier spread. Cumulative tops: 8% / 25% / 50% / 75% / 92%.
_RELATIVE_CUTOFFS: list[tuple[str, str, float]] = [
    ("GOD", "tier-god", 0.08),
    ("S",   "tier-s",   0.25),
    ("A",   "tier-a",   0.50),
    ("B",   "tier-b",   0.75),
    ("C",   "tier-c",   0.92),
    ("Ass", "tier-ass", 1.01),  # catches everything else
]


def assign_tier_relative(wr: float, pool_wrs: list[float]) -> tuple[str, str]:
    """Tier assignment based on RANK within a given win-rate pool.

    Use for role-filtered tier lists so a pool with a tight WR range (e.g.
    Support 54.7-61.1%) still gets a full GOD-to-Ass spread, instead of
    leaving most tiers empty under the absolute static cutoffs.

    A champion's percentile is computed as the share of the pool with a
    strictly higher WR (0.0 = top, ~1.0 = bottom), then bucketed.
    """
    if wr is None or pd.isna(wr) or not pool_wrs:
        return ("?", "tier-unknown")
    n = len(pool_wrs)
    better = sum(1 for v in pool_wrs if v > wr)
    pct = better / n
    for label, klass, cut in _RELATIVE_CUTOFFS:
        if pct < cut:
            return (label, klass)
    return ("Ass", "tier-ass")


def champion_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Per-champion aggregate stats over the top-50 players of each champion.

    Key column is `weighted_winrate` — the confidence-adjusted champion WR.
    Every threshold scales with the champion's OWN games distribution, since
    play volume differs per champion (a niche pick's mains have far fewer
    games than a meta blind-pick's):

        1. ENTRY FLOOR: drop players below FLOOR_FRACTION x the champion's
           median games, clamped to [FLOOR_MIN, FLOOR_MAX] (with a
           per-champion fallback so no champion ends up empty);
        2. BAYESIAN SHRINK: each remaining player's WR is pulled toward the
           champion's own prior (the pool's games-weighted raw WR) by
           SHRINKAGE_C games of synthetic evidence:
               adj_wr = (wins + C * prior) / (games + C)
           so 10 games at 70% becomes ~55%, while 400 games at 60% stays
           ~59.3% — small samples get muted, big samples speak for themselves;
        3. CAPPED WEIGHTING: the champion average is the weighted mean of
           adjusted WRs with weight = min(games, champion's p75 games), so
           a spammer is judged relative to that champion's player base.

    `mean_winrate` (simple mean) and `max_winrate` (the single highest raw
    WR, i.e. the ceiling) are kept for reference. Sorted by
    `weighted_winrate` descending.
    """
    cols = ["champion", "weighted_winrate", "mean_winrate", "max_winrate",
            "winrate_std", "max_score", "median_mastery", "mean_games",
            "median_games", "total_games", "n_players", "otp_score",
            "is_otp", "top_player"]
    if df.empty:
        return pd.DataFrame(columns=cols)

    # Restrict to the top-N players per champion before aggregating.
    top = df[df["rank"] <= TOP_N_PLAYERS].copy()
    if top.empty:
        top = df.copy()

    grouped = top.groupby("champion", as_index=False).agg(
        mean_winrate=("winrate", "mean"),
        max_winrate=("winrate", "max"),
        winrate_std=("winrate", "std"),
        max_score=("score", "max"),
        median_mastery=("score", "median"),
        mean_games=("games", "mean"),
        median_games=("games", "median"),
        total_games=("games", "sum"),
        n_players=("player_name", "count"),
    )

    # --- Confidence-adjusted champion winrate (floor -> shrink -> cap) ---
    w = top.dropna(subset=["winrate"]).copy()
    w["_g"] = w["games"].astype(float).fillna(0.0)
    w["_wr"] = w["winrate"].astype(float)

    # Per-champion thresholds, derived from the UNFILTERED pool (computing
    # them after the floor would be circular). Every champion gets its own
    # floor and cap matched to how much that champion actually gets played.
    floor_c = _adaptive_floor(w["_g"], w["champion"])
    p75_c = w.groupby("champion")["_g"].transform(lambda s: s.quantile(CAP_QUANTILE))
    cap_c = pd.concat([p75_c, 2.0 * floor_c], axis=1).max(axis=1)

    # 1) Entry floor, with per-champion fallback: a row qualifies if it has
    #    >= its champion's floor — but if NO row of a champion qualifies,
    #    keep that champion's whole pool rather than dropping the champ.
    w["_q"] = w["_g"] >= floor_c
    w["_cap"] = cap_c
    champ_has_q = w.groupby("champion")["_q"].transform("any")
    w = w[w["_q"] | ~champ_has_q].copy()

    # 2) Bayesian shrinkage toward the champion's own high-elo prior. The
    #    prior is the pool's games-weighted RAW winrate (not 50% — shrinking
    #    a high-elo Zed toward 50 when Zed's high-elo average is 53 would
    #    systematically underrate him).
    grp = w.groupby("champion")
    pool_gw = (w["_g"] * w["_wr"]).groupby(w["champion"]).transform("sum")
    pool_g = grp["_g"].transform("sum")
    prior = (pool_gw / pool_g.where(pool_g > 0)).fillna(grp["_wr"].transform("mean"))
    wins = w["_g"] * w["_wr"] / 100.0
    w["_adj"] = (wins + SHRINKAGE_C * prior / 100.0) / (w["_g"] + SHRINKAGE_C) * 100.0

    # 3) Capped-weight average of the adjusted winrates. The cap is the
    #    champion's own p75 games value, so "spammer" is judged relative to
    #    that champion's player base, not a global yardstick.
    w["_wt"] = w[["_g", "_cap"]].min(axis=1)
    w["_awt"] = w["_adj"] * w["_wt"]
    agg = w.groupby("champion", as_index=False).agg(
        _num=("_awt", "sum"), _den=("_wt", "sum"), _fallback=("_adj", "mean")
    )
    agg["weighted_winrate"] = (agg["_num"] / agg["_den"]).where(
        agg["_den"] > 0, agg["_fallback"]
    )
    out = grouped.merge(
        agg[["champion", "weighted_winrate"]], on="champion", how="left"
    )

    # top_player = the rank-1 player per champion (if present)
    rank1 = df[df["rank"] == 1][["champion", "player_name"]].rename(columns={"player_name": "top_player"})
    out = out.merge(rank1, on="champion", how="left")

    # Static metadata: combat class + difficulty rating.
    from web.champion_meta import champion_class, champion_difficulty
    out["champ_class"] = out["champion"].map(champion_class)
    out["difficulty"] = out["champion"].map(champion_difficulty)

    # OTP score per champion — derived from the games distribution of the
    # same top-N pool as the win-rate aggregates, so the score reflects how
    # one-trick-heavy the elite player base is for each champion.
    otp_rows = [
        {"champion": champ, "otp_score": _otp_score(g["games"])}
        for champ, g in top.groupby("champion")
    ]
    out = out.merge(pd.DataFrame(otp_rows), on="champion", how="left")

    # Final OTP flag = (algorithmic detection OR known OTP) AND NOT excluded.
    # This is what badges and the "Best OTP Champs" insight read from.
    out["is_otp"] = (
        (out["otp_score"].fillna(0.0) >= OTP_BADGE_THRESHOLD)
        | out["champion"].isin(KNOWN_OTP_CHAMPIONS)
    ) & ~out["champion"].isin(NON_OTP_CHAMPIONS)

    return out.sort_values("weighted_winrate", ascending=False).reset_index(drop=True)


META_TOP_N_PER_CLASS = 5


def meta_breakdown(df: pd.DataFrame, top_n: int = META_TOP_N_PER_CLASS) -> list[dict]:
    """Aggregate champion win rate by combat class to reveal the current meta.

    For each class we take the TOP `top_n` champions by adjusted win rate
    (default 5) and games-weight their win rates. Restricting to the top few
    answers "what's strong right now" — the long off-meta tail of a big class
    (Bruiser, Mage) shouldn't dilute the signal. Returns a list of dicts
    sorted by win rate descending:
        {"champ_class", "wr", "n_champions", "total_games"}
    Classes with no scraped champions are omitted.
    """
    from web.champion_meta import CLASSES

    if df.empty:
        return []
    summary = champion_summary(df)
    summary = summary[summary["weighted_winrate"].notna()]
    if summary.empty:
        return []

    out: list[dict] = []
    for cls in CLASSES:
        sub = summary[summary["champ_class"] == cls]
        if sub.empty:
            continue
        sub = sub.sort_values("weighted_winrate", ascending=False).head(top_n)
        games = sub["total_games"].astype(float)
        if games.sum() > 0:
            wr = float((sub["weighted_winrate"] * games).sum() / games.sum())
        else:
            wr = float(sub["weighted_winrate"].mean())
        out.append({
            "champ_class": cls,
            "wr": wr,
            "n_champions": int(len(sub)),
            "total_games": int(games.sum()),
        })
    out.sort(key=lambda d: d["wr"], reverse=True)
    return out


# A role's win rate is only trustworthy once enough distinct champions in it
# have been scraped; below this we still show the number but flag it.
ROLE_MIN_CHAMPS_CONFIDENT = 5
# When games-weighting champions within a role, cap any single champion's
# weight at this multiple of the role's median champion-games. Normal
# popularity differences are preserved; only a champion that's hugely
# over-represented (e.g. the only meta pick in a barely-scraped role) gets
# reined in so it can't single-handedly define the role number.
ROLE_CHAMP_WEIGHT_CAP_MULT = 3.0


def meta_role_strength(
    df: pd.DataFrame, top_n_per_role: int = 10
) -> dict[str, dict | None]:
    """Win rate of each role's TOP META PICKS only.

    Practical question this answers: "Which role has the strongest options
    in the current meta?" Unlike `role_avg_winrate` (which averages every
    tracked champion in the role, including off-meta picks no high-elo player
    actually touches), this takes the top `top_n_per_role` champions per
    role by confidence-adjusted win rate and games-weights those.

    Use this for the Best/Strongest Role widget. Use `role_avg_winrate` for
    the broader "role health" view.

    Returns the same shape as `role_avg_winrate`:
        {role: {"wr", "n_champions", "total_games", "low_confidence"}}
    `low_confidence` is True when the role doesn't have at least
    `top_n_per_role` scraped champions to fully populate the cut.
    """
    from web.champion_roles import ROLES, roles_for

    out: dict[str, dict | None] = {r: None for r in ROLES}
    if df.empty:
        return out

    summary = champion_summary(df)
    summary = summary[summary["weighted_winrate"].notna()].copy()
    if summary.empty:
        return out
    summary["_role"] = summary["champion"].map(lambda c: roles_for(c)[0])

    for role in ROLES:
        sub = summary[summary["_role"] == role].sort_values(
            "weighted_winrate", ascending=False
        )
        if sub.empty:
            continue
        top = sub.head(top_n_per_role)
        games = top["total_games"].astype(float)
        if games.sum() > 0:
            wr = float((top["weighted_winrate"] * games).sum() / games.sum())
        else:
            wr = float(top["weighted_winrate"].mean())
        out[role] = {
            "wr": wr,
            "n_champions": int(len(top)),
            "total_games": int(games.sum()),
            # If we couldn't even fill the top-N cut, the number is unreliable.
            "low_confidence": len(top) < top_n_per_role,
        }
    return out


def role_avg_winrate(df: pd.DataFrame) -> dict[str, dict | None]:
    """Confidence-adjusted win rate per role.

    Method (most-accurate given top-50-per-champion data):
      1. Start from each champion's already-robust `weighted_winrate`
         (per-champion floor + Bayesian shrink + capped weighting).
      2. Aggregate to the role as a GAMES-WEIGHTED mean — a champion that
         actually carries the lane's playtime counts more than a niche pick,
         so the number reflects the real meta rather than a flat average.
      3. Cap any single champion's weight at ROLE_CHAMP_WEIGHT_CAP_MULT x the
         role's median champion-games, so one over-represented champion can't
         own a thinly-scraped role.

    Returns {role: {"wr", "n_champions", "total_games", "low_confidence"}}
    or {role: None} for roles with no scraped champions. `low_confidence` is
    True when fewer than ROLE_MIN_CHAMPS_CONFIDENT champions back the number.
    """
    from web.champion_roles import ROLES, roles_for

    out: dict[str, dict | None] = {r: None for r in ROLES}
    if df.empty:
        return out

    summary = champion_summary(df)
    summary = summary[summary["weighted_winrate"].notna()].copy()
    if summary.empty:
        return out
    summary["_role"] = summary["champion"].map(lambda c: roles_for(c)[0])
    summary["_games"] = summary["total_games"].astype(float).fillna(0.0)

    for role in ROLES:
        sub = summary[summary["_role"] == role]
        if sub.empty:
            continue

        med = sub["_games"].median()
        cap = med * ROLE_CHAMP_WEIGHT_CAP_MULT if med > 0 else 0.0
        weights = sub["_games"].clip(upper=cap) if cap > 0 else sub["_games"]
        if weights.sum() > 0:
            wr = float((sub["weighted_winrate"] * weights).sum() / weights.sum())
        else:
            wr = float(sub["weighted_winrate"].mean())

        out[role] = {
            "wr": wr,
            "n_champions": int(len(sub)),
            "total_games": int(sub["_games"].sum()),
            "low_confidence": len(sub) < ROLE_MIN_CHAMPS_CONFIDENT,
        }
    return out


def best_player_per_champion(df: pd.DataFrame, z: float = 1.96) -> pd.DataFrame:
    """Rank each champion's players by a confidence-adjusted win rate and
    flag the single best one.

    "Best wins-per-game ratio, not skewed by low games + high WR" is exactly
    the Wilson score lower bound: it's the conservative end of the 95% CI for
    a player's true win proportion. A 3-game 100% run scores ~44% (huge
    uncertainty), while a 134-game 67% main scores ~59% (tight interval), so
    the title goes to demonstrated, high-volume performance rather than a
    lucky handful of games.

    Operates over the top-50 players per champion (matching the rest of the
    site). Returns the (filtered) DataFrame with two new columns:
      - `confidence_wr`: Wilson lower-bound win rate as a percentage (0-100)
      - `is_best_for_champ`: True for the highest-`confidence_wr` row per champ
    """
    cols_extra = ["confidence_wr", "is_best_for_champ"]
    if df.empty:
        out = df.copy()
        for c in cols_extra:
            out[c] = pd.Series(dtype=float if c == "confidence_wr" else bool)
        return out

    out = df[df["rank"] <= TOP_N_PLAYERS].copy()
    if out.empty:
        out = df.copy()

    # Entry floor: same adaptive quality gate as champion_summary — you
    # can't be a champion's "best player" off 8 games, but the bar scales
    # with how much that champion actually gets played. Per-champion
    # fallback keeps a champion's full pool when nobody clears the floor.
    g_check = out["games"].astype(float).fillna(0.0)
    qualifies = g_check >= _adaptive_floor(g_check, out["champion"])
    champ_has_q = qualifies.groupby(out["champion"]).transform("any")
    out = out[qualifies | ~champ_has_q].copy()

    games_f = out["games"].astype(float).fillna(0.0)
    wr_frac = out["winrate"].astype(float) / 100.0
    wins = (wr_frac * games_f).round()
    out["confidence_wr"] = [
        _wilson_lower_bound(w, n, z) * 100.0 for w, n in zip(wins, games_f)
    ]

    idx_best = out.groupby("champion")["confidence_wr"].idxmax()
    out["is_best_for_champ"] = False
    out.loc[idx_best, "is_best_for_champ"] = True
    return out


# Champions kept OUT of sleeper/off-meta suggestions even when the stats
# qualify them. These are contested/high-ban picks (or brand-new champions)
# that look under-played for the wrong reason — they're banned away or just
# haven't accumulated mastery yet, not genuinely hidden. Edit as the meta
# shifts.
OFF_META_EXCLUDE: frozenset[str] = frozenset({
    "Taliyah",   # high ban rate — contested, not a hidden gem
})


def off_meta_picks(
    df: pd.DataFrame,
    popularity_quantile: float = 0.40,
    winrate_quantile: float = 0.60,
) -> pd.DataFrame:
    """Sleeper picks: champions few people grind that still win a lot.

    We have no true ladder-wide pick rate (we scrape exactly the top 50 of
    every champion regardless of popularity, and the `games` column is *recent*
    games, which tracks activity not popularity). Instead we use MASTERY DEPTH
    as the popularity proxy: `median_mastery` is the median lifetime mastery
    score of a champion's top 50 — the "entry bar" to being elite on it. A
    popular, heavily-contested champion has a high bar; a niche one has a low
    bar. (Verified: games-share flags Hecarim/Aatrox as niche — wrong — while
    mastery depth correctly ranks them as the most contested.)

    A champion qualifies as a strong off-meta pick when it is BOTH:
      * in the bottom `popularity_quantile` of mastery depth (few grind it), AND
      * in the top (1 - `winrate_quantile`) of win rate (it actually wins),
    and is not in `OFF_META_EXCLUDE`.

    Returned sorted by win rate descending.
    """
    summary = champion_summary(df)
    valid = summary[summary["weighted_winrate"].notna() & summary["median_mastery"].notna()]
    valid = valid[~valid["champion"].isin(OFF_META_EXCLUDE)]
    if valid.empty:
        return valid.reset_index(drop=True)
    pop_cut = valid["median_mastery"].quantile(popularity_quantile)
    wr_cut = valid["weighted_winrate"].quantile(winrate_quantile)
    mask = (valid["median_mastery"] <= pop_cut) & (valid["weighted_winrate"] >= wr_cut)
    return valid[mask].sort_values("weighted_winrate", ascending=False).reset_index(drop=True)


# Hand-picked genuinely-funny player names spotted in the data. Funniness
# can't be computed reliably, so this is a curated shortlist; the card shows
# whichever of these are still present in the current leaderboard (falling
# through to later entries as the data changes). Keep it clean + clever.
_FUNNY_NAME_CANDIDATES: tuple[str, ...] = (
    # Cultural / pop-culture references — strongest material
    "Quoth the Draven",
    "Hide on Trash",
    "Voit Know Nothing",
    "Better Call FISH",
    "vlad the impaler",
    "Baby McGregor",
    "PROXY GOD SINGED",
    "the idgaf player",
    "Thresh bless you",
    "Mid for speed",

    # Self-deprecating / mood
    "IDK HOW TO ADC",
    "i mentally Dead",
    "Mad Cuz Bad",
    "egirl made u cry",
    "we all gonna die",
    "Stop gambling",
    "look Outside",

    # Champion-themed
    "Big Mommy Fiora",
    "Daddy Rengar",
    "Monster Yi",
    "Only Teemo",
    "Annie Bot",
    "Zed The Ripper",
    "Janna is my wife",
    "Zeri Top is GOAT",

    # Vibes
    "Potato Princess",
    "lord troll",
    "TRUE WHALE",
    "OTP Toxic Bot",
    "SCUBA CAT",
    "Dubai Monkey",
    "Top 1 Main",
    "Toxic Daddy",
    "Naughty dog",
    "Mom Rider",
    "TOP SHOTTA",

    # Originals worth keeping
    "A Tinder Enjoyer",
    "LetMeCook",
    "| Hate Butanito",
    "Lover boy Ayoub",
    "in another life",
    "FlashPPFish",
    "boboboboboboo",
    "ManGoBeast",
    "World Ender",
    "TheGoldenBoy",
    "i like mommies",
    "FINALBOSS",
)


def funny_names(df: pd.DataFrame, limit: int = 3) -> list[dict]:
    """Up to `limit` of the curated funny names that are present in the
    current data, each with the champion they were scraped on and their WR.
    Returns [{"player_name", "champion", "winrate"}]."""
    if df.empty:
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for cand in _FUNNY_NAME_CANDIDATES:
        if cand in seen:
            continue
        match = df[df["player_name"] == cand]
        if match.empty:
            continue
        row = match.iloc[0]
        out.append({
            "player_name": cand,
            "champion": str(row["champion"]),
            "winrate": float(row["winrate"]) if pd.notna(row["winrate"]) else None,
        })
        seen.add(cand)
        if len(out) >= limit:
            break
    return out


def skill_spread(df: pd.DataFrame, summary: pd.DataFrame) -> pd.DataFrame:
    """Summary with a `skill_spread` column = ceiling - weighted WR.

    The ceiling is the max WR among top-50 players who have at least
    `SHRINKAGE_C` games, so a one-off 100% from a 5-game sample doesn't
    inflate the spread. High spread = high skill expression (Yasuo / Lee Sin
    energy); low spread = champion floors near its ceiling (Garen). Sorted
    by spread desc."""
    if summary.empty or df.empty:
        return summary
    pool = df[df["rank"] <= TOP_N_PLAYERS].copy()
    qualified = pool[pool["games"].fillna(0) >= SHRINKAGE_C]
    ceiling = qualified.groupby("champion", as_index=False)["winrate"].max()
    ceiling = ceiling.rename(columns={"winrate": "ceiling_qualified"})
    out = summary.merge(ceiling, on="champion", how="left")
    # Fall back to max_winrate when nobody clears the games gate (niche champs).
    out["ceiling_qualified"] = out["ceiling_qualified"].fillna(out["max_winrate"])
    out["skill_spread"] = (out["ceiling_qualified"] - out["weighted_winrate"]).clip(lower=0.0)
    return out.sort_values("skill_spread", ascending=False).reset_index(drop=True)


def multi_champion_mains(df: pd.DataFrame, min_champions: int = 2) -> list[dict]:
    """Players appearing in the top-50 of `min_champions` or more champions.

    Top-50 on multiple champions is far harder than spamming one, so this
    surfaces the genuinely-strongest mechanics on the server. Sorted by
    (champion count desc, mean raw WR desc)."""
    if df.empty:
        return []
    pool = df[df["rank"] <= TOP_N_PLAYERS].copy()
    pool = pool[pool["player_name"].notna()]
    pool = pool[pool["player_name"].astype(str).str.strip() != ""]
    # Strip the OCR fallback placeholder — it represents many distinct CJK
    # players the OCR couldn't read, so collapsing them into "one player on
    # 100+ champions" is wrong.
    pool = pool[pool["player_name"] != UNNAMED_PLACEHOLDER]
    if pool.empty:
        return []
    grouped = pool.groupby("player_name", as_index=False).agg(
        n_champions=("champion", "nunique"),
        champions=("champion", lambda s: sorted(set(s))),
        avg_winrate=("winrate", "mean"),
        best_rank=("rank", "min"),
        total_games=("games", "sum"),
    )
    grouped = grouped[grouped["n_champions"] >= min_champions]
    grouped = grouped.sort_values(
        ["n_champions", "avg_winrate"], ascending=[False, False]
    )
    return [
        {
            "player_name": str(r["player_name"]),
            "n_champions": int(r["n_champions"]),
            "champions": list(r["champions"]),
            "avg_winrate": float(r["avg_winrate"]) if pd.notna(r["avg_winrate"]) else None,
            "best_rank": int(r["best_rank"]) if pd.notna(r["best_rank"]) else None,
            "total_games": int(r["total_games"]) if pd.notna(r["total_games"]) else 0,
        }
        for _, r in grouped.iterrows()
    ]


def winrate_by_difficulty(summary: pd.DataFrame) -> list[dict]:
    """Games-weighted average WR per difficulty bucket (Easy -> Very Hard).

    Answers "are hard champions actually worth grinding, or do easy champs
    win just as much?". Returns a list of dicts in difficulty order."""
    from web.champion_meta import difficulty_label
    if summary.empty:
        return []
    s = summary[summary["weighted_winrate"].notna()].copy()
    if s.empty:
        return []
    s["diff_label"] = s["difficulty"].apply(
        lambda d: difficulty_label(int(d)) if pd.notna(d) else "Unknown"
    )
    order = ["Easy", "Moderate", "Hard", "Very Hard"]
    out: list[dict] = []
    for label in order:
        sub = s[s["diff_label"] == label]
        if sub.empty:
            continue
        g = sub["total_games"].astype(float)
        wr = (
            float((sub["weighted_winrate"] * g).sum() / g.sum())
            if g.sum() > 0
            else float(sub["weighted_winrate"].mean())
        )
        out.append({
            "difficulty": label,
            "wr": wr,
            "n_champions": int(len(sub)),
            "total_games": int(g.sum()),
        })
    return out


def pick_of_the_patch(df: pd.DataFrame) -> dict | None:
    """The single highest weighted-WR champion. Returns a dict of summary
    fields, or None if there's no data."""
    summary = champion_summary(df)
    if summary.empty:
        return None
    row = summary.iloc[0]  # already sorted by weighted_winrate desc
    return {
        "champion": row["champion"],
        "weighted_winrate": float(row["weighted_winrate"]),
        "mean_winrate": float(row["mean_winrate"]),
        "max_winrate": float(row["max_winrate"]) if pd.notna(row["max_winrate"]) else None,
        "n_players": int(row["n_players"]),
    }
