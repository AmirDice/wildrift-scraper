"""Run the engine tournament across champions and biases, and show every candidate.

The advisor response only makes the winner easy to read. To judge whether the
model was fair in rejecting an engine build, you need the whole field: every
model candidate and the ENGINE-D challenger, each with its full core, its
blended engine score and the raw dimensions behind it, next to the judge's own
explanation. This prints that as Markdown and keeps the raw responses as JSON.

    python scripts/tournament_matrix.py
    python scripts/tournament_matrix.py --champions Varus Graves --biases max_durability

Needs GEMINI_API_KEY (environment, or web-next/.env.local).
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from web import build_advisor as adv  # noqa: E402

DEFAULT_CHAMPIONS = {"Varus": "dragon", "Caitlyn": "dragon", "Graves": "jungle"}
DEFAULT_BIASES = ["max_damage", "balanced", "max_durability"]


def name(slug: str) -> str:
    return (adv.ITEMS.get(slug) or {}).get("name") or slug


def spell_names(spells) -> list[str]:
    return [s.get("name") if isinstance(s, dict) else s for s in spells or []]


def run_one(champion: str, role: str, bias: str) -> dict:
    started = time.time()
    try:
        res = adv.advise_best_of(champion, role, [], runs=1, build_bias=bias)
        return {"champion": champion, "role": role, "bias": bias,
                "seconds": round(time.time() - started, 1), "result": res}
    except Exception as exc:  # noqa: BLE001 -- the crash is the finding
        return {"champion": champion, "role": role, "bias": bias,
                "seconds": round(time.time() - started, 1),
                "crash": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc()}


def _mean(rows: list[dict], key: str) -> float | None:
    values = [r.get(key) for r in rows if isinstance(r.get(key), (int, float))]
    return round(sum(values) / len(values), 1) if values else None


def _fmt(value) -> str:
    if value is None:
        return "–"
    if isinstance(value, float):
        return f"{value:,.1f}"
    return f"{value:,}" if isinstance(value, int) else str(value)


def candidate_rows(meta: dict, final: dict) -> list[str]:
    scores = (meta.get("engineSearch") or {}).get("authoredScores") or {}
    challenger_score = (meta.get("engineSearch") or {}).get("challengerScore")
    winner = meta.get("winner")
    final_sig = (tuple(final.get("items") or []), final.get("boots"))
    lines = [
        "| | id | archetype | items (purchase order) | boots | runes | summoners "
        "| engine score | mean DPS 8s | mean burst 3s | 1v3 dmg | EHP | time to die "
        "| dmg before death |",
        "|" + "---|" * 14,
    ]
    for row in meta.get("measurements") or []:
        core, eng = row.get("core") or {}, row.get("engine") or {}
        rid = str(row.get("id"))
        score = challenger_score if rid == "ENGINE-D" else scores.get(rid)
        panel = eng.get("damageScenarios") or {}
        targets = list((panel.get("targets") or {}).values())
        runes = core.get("runes") or {}
        page = " · ".join([f"**{runes.get('keystone')}**"]
                          + list(runes.get("minors") or []) + [runes.get("flex") or ""])
        mark = ("★" if rid == winner else
                "◇" if (tuple(core.get("items") or []), core.get("boots")) == final_sig
                else "")
        lines.append(" | ".join([
            f"| {mark}", f"**{rid}**", str(row.get("archetype") or ""),
            " → ".join(name(s) for s in core.get("items") or []),
            name(core.get("boots") or ""), page,
            " + ".join(spell_names(core.get("summoners"))),
            _fmt(score), _fmt(_mean(targets, "dps8")), _fmt(_mean(targets, "burst3")),
            _fmt((panel.get("oneVsThree") or {}).get("totalDamage")),
            _fmt(eng.get("ehp")), _fmt(eng.get("timeToDie")),
            _fmt(eng.get("damageBeforeDeath")),
        ]) + " |")
    return lines


def report(run: dict) -> list[str]:
    title = f"## {run['champion']} ({run['role']}) — {run['bias'].replace('_', ' ')}"
    out = [title, ""]
    if "crash" in run:
        return out + [f"**CRASHED** after {run['seconds']}s: `{run['crash']}`", ""]
    res = run["result"]
    if res.get("error"):
        return out + [f"**ERROR**: {res['error']}", ""]
    meta = res.get("engineTournament")
    runes = res.get("runes") or {}
    if not meta:
        verdict = "no tournament ran; ordinary generation fallback (see stderr)"
    elif meta.get("coreRepairedAfterJudge"):
        verdict = (f"judge picked {meta.get('judgedWinner')}, then validation repaired "
                   "the core, so it is not engine-judged")
    else:
        verdict = f"judge picked **{meta.get('winner')}**"
    search = (meta or {}).get("engineSearch") or {}
    out += [
        f"**Final:** {' → '.join(name(s) for s in res.get('items') or [])} · "
        f"{name(res.get('boots') or '')} · {runes.get('keystone')} "
        f"({', '.join(runes.get('minors') or [])}, {runes.get('flex')}) · "
        f"{' + '.join(spell_names(res.get('summoners')))}",
        "",
        f"**Verdict:** {verdict}. Took {run['seconds']}s.",
    ]
    if search:
        out.append(f"Engine: best model candidate {_fmt(search.get('authoredBestScore'))}, "
                   f"best engine recombination {_fmt(search.get('challengerScore'))}"
                   + (f" ({search['reason']})" if search.get("reason") else "")
                   + (", challenger entered" if meta.get("engineChallenger")
                      else ", no challenger entered") + ".")
    if meta:
        out += ["", *candidate_rows(meta, res),
                "", "★ judge's pick · ◇ matches the shipped build"]
    why = res.get("why") or []
    verdict_reason = (res.get("buildScore") or {}).get("reason")
    if why or verdict_reason:
        out += ["", "**Judge's reasoning:**"]
        out += [f"- {line}" for line in why]
        if verdict_reason:
            out.append(f"- _{verdict_reason}_")
    if res.get("validationErrors"):
        out += ["", f"Validation errors: {res['validationErrors']}"]
    return out + [""]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--champions", nargs="+", default=list(DEFAULT_CHAMPIONS))
    ap.add_argument("--biases", nargs="+", default=DEFAULT_BIASES)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--out", default=str(ROOT / "reports"))
    args = ap.parse_args()

    if not adv._api_key(adv.KEY_NAME):
        sys.exit(adv.advisor_env.missing_key_message(adv.KEY_NAME))
    jobs = [(c, DEFAULT_CHAMPIONS.get(c) or (adv.CHAMPS.get(c) or {}).get("role", ""), b)
            for c in args.champions for b in args.biases]
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        runs = list(pool.map(lambda job: run_one(*job), jobs))

    stamp = time.strftime("%Y%m%d-%H%M%S")
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"tournament_matrix-{stamp}.json").write_text(
        json.dumps(runs, indent=1, ensure_ascii=False), encoding="utf-8")
    text = "\n".join(line for run in runs for line in report(run))
    (out_dir / f"tournament_matrix-{stamp}.md").write_text(text, encoding="utf-8")
    print(text)
    print(f"\nSaved to {out_dir}/tournament_matrix-{stamp}.{{md,json}}", file=sys.stderr)


if __name__ == "__main__":
    main()
