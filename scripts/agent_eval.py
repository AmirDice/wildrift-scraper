"""Second half of the site-agent evaluation: send the questions the fast path
declined to the real model, with the exact context the site would send.

    cd web-next && npx tsx scripts/agent_eval.ts ../scripts/agent_eval_battery.json ../routed.json
    python -m scripts.agent_eval routed.json answers.json

scripts/agent_eval_battery.json is forty questions a player actually asks,
including the shapes that broke the first fast path (comparisons, "against",
possessives, "still good after the nerf"), a greeting that must not spend a
visitor's one model answer, and a prompt injection the model must refuse
without describing its instructions. On 2026-10-15 it went from
18 fast-path answers, about ten of them wrong, to 27 correct ones; re-run it
after any change to web-next/src/lib/agent-context.ts.

The model is called concurrently, a few at a time; it is the same call
web/site_agent.py makes in production, so what comes back is what a visitor
would have read.
"""
from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from web.site_agent import answer_site_question  # noqa: E402


def ask(row: dict) -> dict:
    if row["path"] != "model":
        return row
    t0 = time.time()
    try:
        res = answer_site_question(row["q"], row["context"], [])
        row["answer"] = res["answer"]
        row["evidence"] = res.get("evidence", [])
    except Exception as exc:  # noqa: BLE001
        row["answer"] = f"<<ERROR {type(exc).__name__}: {exc}>>"
    row["seconds"] = round(time.time() - t0, 1)
    return row


def main() -> int:
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    rows = json.loads(src.read_text(encoding="utf-8"))
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(ask, rows))
    for r in rows:
        r.pop("context", None)
    dst.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    for r in rows:
        if r["path"] == "model":
            print(f"\n[model {r.get('seconds')}s] ({r['page']}) {r['q']}")
            print("   " + (r["answer"] or "").replace("\n", " / ")[:420])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
