"""The model's build and runes against the leaderboard's most common, judged by the engine.

No engine ranking is involved in CHOOSING either side. One is what the advisor
wrote; the other is what the top fifty most often hold. The engine only referees,
using everything it has:

  MIRROR        both builds on the same champion, each with its OWN rune page,
                rotations racing on one clock. mutual_duel says who kills first.
  FIVE TARGETS  duel() into adc, mage, fighter, bruiser and tank: time to kill,
                and damage dealt by 2s, 4s and 8s for the cases ttk ties.
  VECTOR        every measurement evaluation_vector carries, both sides.

That referee has known blind spots -- it cannot see mana as uptime, thorns,
stickiness, or anything multi-target beyond bolt damage -- so a verdict here is
the engine's opinion, not the truth. Where the engine and the leaderboard
disagree, the blind spot is the first thing to suspect.

    python -m scripts.model_vs_ladder --champions Ezreal,Amumu --out out.json
"""
from __future__ import annotations

import argparse
import collections
import csv
import glob
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import web.fight_engine as fe  # noqa: E402

LEVEL = 15
MIN_GAMES = 15


def _env() -> dict:
    out = {}
    try:
        for line in (ROOT / "web-next" / ".env.local").read_text("utf-8").splitlines():
            m = re.match(r'([A-Z0-9_]+)="?([^"]*)"?$', line.strip())
            if m:
                out[m.group(1)] = m.group(2)
    except OSError:
        pass
    return out


ENV = _env()


def model_build(champ: str) -> dict | None:
    """The advisor's own build and rune page, from the index the site fills."""
    key = f"latest:build:{re.sub(r'[^a-z0-9]+', '-', champ.lower()).strip('-')}"
    try:
        req = urllib.request.Request(
            f"{ENV['KV_REST_API_URL']}/get/{urllib.parse.quote(key, safe='')}",
            headers={"Authorization": f"Bearer {ENV['KV_REST_API_TOKEN']}"})
        raw = json.load(urllib.request.urlopen(req, timeout=20))["result"]
    except Exception:
        return None
    if not raw:
        return None
    d = json.loads(raw)
    items = [s for s in (d.get("items") or [])
             if s in fe.ITEMS and fe.ITEMS[s].get("category") != "Boots"]
    page = d.get("runes") or {}
    runes = [page.get("keystone") or ""] + list(page.get("minors") or [])[:3]
    if page.get("flex"):
        runes.append(page["flex"])
    runes = [r for r in runes if r]
    return {"items": items[:5], "runes": runes} if len(items) >= 5 else None


def ladder_build(champ: str) -> dict | None:
    """The five most-held items and the single most common rune page."""
    key = re.sub(r"[^a-z0-9]+", "-", champ.lower()).strip("-")
    items, pages, n = collections.Counter(), collections.Counter(), 0
    for sess in glob.glob(str(ROOT / "data" / "captures_archive" / "*" / f"{key}_*")):
        ok = set()
        try:
            rows = list(csv.DictReader(open(f"{sess}/extracted.csv", encoding="utf-8")))
        except OSError:
            continue
        for r in rows:
            # Per ROW. Wrapping this in one try around the session meant a
            # single empty games field discarded an entire champion's captures.
            try:
                if int(r["games"]) >= MIN_GAMES:
                    ok.add(int(r["rank"]))
            except (TypeError, ValueError, KeyError):
                continue
        try:
            lines = open(f"{sess}/builds.jsonl", encoding="utf-8").read().splitlines()
        except OSError:
            continue
        for ln in lines:
            if not ln.strip():
                continue
            b = json.loads(ln)
            if int(b["rank"]) not in ok:
                continue
            slugs = [i["slug"] for i in (b.get("items") or [])
                     if i.get("slug") in fe.ITEMS
                     and fe.ITEMS[i["slug"]].get("category") != "Boots"]
            if len(slugs) < 5:
                continue
            n += 1
            for s in slugs[:5]:
                items[s] += 1
            rn = [r for r in (b.get("runes") or []) if r]
            if len(rn) >= 4:
                pages[tuple(rn[:5])] += 1
    if n < 10 or len(items) < 5:
        return None
    top = items.most_common(5)
    page, page_n = (pages.most_common(1) or [((), 0)])[0]
    return {"items": [s for s, _c in top],
            "picks": [c for _s, c in top],
            "runes": list(page),
            "pagePct": round(100 * page_n / n, 1),
            "players": n,
            "consensusPct": round(100 * sum(c for _s, c in top) / (5 * n), 1)}


def judge(champ: str, a: dict, b: dict) -> dict:
    """a = model, b = ladder. Every measurement the engine has, both sides."""
    targets = {}
    wins_a = wins_b = 0
    for label, prof in fe.target_profiles(LEVEL).items():
        tgt = dict(prof)
        tgt.setdefault("label", label)
        tgt.setdefault("bonusHp", max(0.0, prof["hp"] - 1800))
        da = fe.duel(champ, a["items"], a["runes"], dict(tgt), LEVEL) or {}
        db = fe.duel(champ, b["items"], b["runes"], dict(tgt), LEVEL) or {}
        sa = {f"t{int(s)}": round(fe.rotation(
            champ, fe.resolve_stats(champ, LEVEL, a["items"], a["runes"]),
            dict(tgt), s, LEVEL)["total"]) for s in (2.0, 4.0, 8.0)}
        sb = {f"t{int(s)}": round(fe.rotation(
            champ, fe.resolve_stats(champ, LEVEL, b["items"], b["runes"]),
            dict(tgt), s, LEVEL)["total"]) for s in (2.0, 4.0, 8.0)}
        ta, tb = da.get("ttk"), db.get("ttk")
        if ta is not None and tb is not None and ta != tb:
            win = "model" if ta < tb else "ladder"
        elif ta is None and tb is not None:
            win = "ladder"
        elif tb is None and ta is not None:
            win = "model"
        else:
            # Same tick, or neither kills: settle on damage dealt by 4s, which
            # is the comparison ttk was too coarse to make -- but only when the
            # gap is real. On Ezreal the two builds share all five items and
            # differ by one flex rune; ttk was identical on every target and a
            # bare > handed all five to the model on gaps of 0.6%. Under 2% is
            # a tie, because the engine cannot resolve finer than that.
            lo, hi = sorted((sa["t4"], sb["t4"]))
            if hi and (hi - lo) / hi < 0.02:
                win = "tie"
            else:
                win = "model" if sa["t4"] > sb["t4"] else "ladder"
        wins_a += win == "model"
        wins_b += win == "ladder"
        targets[label] = {"hp": prof["hp"], "armor": prof["armor"], "mr": prof["mr"],
                          "modelTtk": ta, "ladderTtk": tb,
                          "model": sa, "ladder": sb, "winner": win}

    md = fe.mutual_duel(champ, a["items"], a["runes"],
                        champ, b["items"], b["runes"], LEVEL) or {}
    mirror = {"you": "model", "them": "ladder"}.get(md.get("verdict"), md.get("verdict"))

    va = fe.evaluation_vector(champ, a["items"], a["runes"], LEVEL)
    vb = fe.evaluation_vector(champ, b["items"], b["runes"], LEVEL)
    obj = fe.default_objective(champ)


    # THE VERDICT RULE, stated rather than tuned. Each standard target is one
    # vote, the mirror is one, surviving longer is one, and the champion's own
    # OBJECTIVE score is one.
    #
    # The objective vote is not decoration. Without it the rule judges purely on
    # damage and survival, which is the wrong question for an enchanter: Nami
    # won all five targets while both builds took six to fourteen seconds to
    # kill anything, and her support output -- the entire point of the build --
    # counted for nothing.
    score_a = fe.objective_score(va, obj)
    score_b = fe.objective_score(vb, obj)
    votes_a = (wins_a + (mirror == "model") + (va["timeToDie"] > vb["timeToDie"])
               + (score_a > score_b))
    votes_b = (wins_b + (mirror == "ladder") + (vb["timeToDie"] > va["timeToDie"])
               + (score_b > score_a))
    verdict = "model" if votes_a > votes_b else "ladder" if votes_b > votes_a else "tie"

    return {
        "champion": champ, "class": fe.CHAMP_CLASS.get(champ, ""),
        "role": fe.CHAMP_ROLE.get(champ, ""), "objective": obj,
        "model": {**a, "itemNames": [fe.ITEMS[s]["name"] for s in a["items"]],
                  "vector": va, "objectiveScore": score_a},
        "ladder": {**b, "itemNames": [fe.ITEMS[s]["name"] for s in b["items"]],
                   "vector": vb, "objectiveScore": score_b},
        "targets": targets, "targetWins": {"model": wins_a, "ladder": wins_b},
        "mirror": mirror,
        "mirrorMargin": md.get("margin"), "survivorHp": md.get("survivorHp"),
        "votes": {"model": votes_a, "ladder": votes_b}, "verdict": verdict,
        "sharedItems": sorted(set(a["items"]) & set(b["items"])),
        "sharedRunes": sorted(set(a["runes"]) & set(b["runes"])),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--champions", required=True)
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    out = []
    for champ in [c.strip() for c in args.champions.split(",") if c.strip()]:
        if champ not in fe.CHAMPS:
            print(f"{champ}: not in roster")
            continue
        a, b = model_build(champ), ladder_build(champ)
        if not a:
            print(f"{champ}: no cached model build")
            continue
        if not b:
            print(f"{champ}: not enough captured players")
            continue
        r = judge(champ, a, b)
        out.append(r)
        print(f"{champ:14} {r['verdict']:>6}   targets "
              f"{r['targetWins']['model']}-{r['targetWins']['ladder']}   "
              f"mirror {str(r['mirror']):9} items shared "
              f"{len(r['sharedItems'])}/5  runes {len(r['sharedRunes'])}/5")
    if args.out:
        Path(args.out).write_text(json.dumps(out, indent=1), encoding="utf-8")
        print(f"\nwrote {args.out}")
    tally = collections.Counter(r["verdict"] for r in out)
    print(f"\nverdicts: {dict(tally)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
