"""Machine-translate the site's long data text into the page languages.

    python scripts/translate_content.py [--langs zh,vi] [--workers 6]

Sources: ability names and descriptions (web-next/src/data/champion_details.json)
and patch-change history (champion_change_history.json: summaries, change
lines and ability names). Output: web-next/src/i18n/content/<lang>.json,
{sha1(text)[:12]: translation} -- the key lib/content-i18n.ts looks up.
Only texts without a translation are sent, so a re-run after a patch costs
only what changed.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import re
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "web-next" / "src" / "data"
OUT = ROOT / "web-next" / "src" / "i18n" / "content"
LANGS = {
    "zh": "Simplified Chinese (League of Legends: Wild Rift China terminology)",
    "vi": "Vietnamese (Tốc Chiến terminology)",
    "tr": "Turkish", "fr": "French", "pl": "Polish", "ko": "Korean", "es": "Spanish",
}


def key(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def sources() -> list[str]:
    texts: set[str] = set()
    details = json.loads((DATA / "champion_details.json").read_text(encoding="utf-8"))
    for c in details.values():
        for a in c.get("abilities") or []:
            for f in ("name", "text"):
                if a.get(f):
                    texts.add(a[f])
    history = json.loads((DATA / "champion_change_history.json").read_text(encoding="utf-8"))["champions"]
    for rows in history.values():
        for r in rows:
            if r.get("summary"):
                texts.add(r["summary"])
            for c in r.get("changes") or []:
                for f in ("text", "ability"):
                    if c.get(f):
                        texts.add(c[f])
    # Kit synergy notes (builds.json) and combo explanations, shown on the
    # champion page.
    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "synergyNotes" and isinstance(v, list):
                    texts.update(x for x in v if isinstance(x, str) and x)
                else:
                    walk(v)
        elif isinstance(o, list):
            for x in o:
                walk(x)
    walk(json.loads((DATA / "builds.json").read_text(encoding="utf-8")))
    combos = json.loads((DATA / "champion_combos.json").read_text(encoding="utf-8")).get("champions", {})
    for v in combos.values():
        if v.get("why"):
            texts.add(v["why"])
    return sorted(texts)


def load_env() -> None:
    env = ROOT / "web-next" / ".env.local"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\s*(GEMINI_API_KEY|GOOGLE_API_KEY)\s*=\s*\"?([^\"\s]+)", line)
            if m:
                os.environ.setdefault(m.group(1), m.group(2))


def translate(client, model, lang, batch):
    from google.genai import types
    prompt = (
        f"Translate these texts from the mobile game League of Legends: Wild Rift into {LANGS[lang]}. "
        "They are ability descriptions, ability names and patch-note lines. Keep numbers, percentages, "
        "ratios and stat abbreviations exactly (e.g. '10/20/30', '(+50% AP)', 'AD', 'AP', 'HP'). Translate "
        "ability names the way the game would. No em dashes, no emojis. "
        f"Return ONLY a JSON array of exactly {len(batch)} strings, the translations in the same order.\n\n"
        + "\n".join(f"{i + 1}. {json.dumps(s, ensure_ascii=False)}" for i, s in enumerate(batch))
    )
    r = client.models.generate_content(
        model=model, contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0,
                                           thinking_config=types.ThinkingConfig(thinkingLevel=types.ThinkingLevel.LOW)))
    data = json.loads(r.text)
    if not isinstance(data, list) or len(data) != len(batch):
        raise ValueError(f"expected {len(batch)}, got {len(data) if isinstance(data, list) else type(data).__name__}")
    return {key(en): tr.replace("—", ", ").strip() for en, tr in zip(batch, data) if isinstance(tr, str) and tr.strip()}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--langs", default=",".join(LANGS))
    ap.add_argument("--model", default="gemini-3.5-flash-lite")
    ap.add_argument("--batch", type=int, default=30)
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    load_env()
    from google import genai
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY") or os.environ["GOOGLE_API_KEY"])
    texts = sources()
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"{len(texts)} source texts", flush=True)
    for lang in args.langs.split(","):
        path = OUT / f"{lang}.json"
        table = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        missing = [t for t in texts if key(t) not in table]
        batches = [missing[i:i + args.batch] for i in range(0, len(missing), args.batch)]
        lock = threading.Lock()
        failed = 0

        def run(batch):
            nonlocal failed
            try:
                got = translate(client, args.model, lang, batch)
                with lock:
                    table.update(got)
            except Exception as exc:  # noqa: BLE001
                with lock:
                    failed += 1
                print(f"  {lang} batch failed: {str(exc)[:120]}", file=sys.stderr, flush=True)

        with concurrent.futures.ThreadPoolExecutor(args.workers) as pool:
            for i, _ in enumerate(pool.map(run, batches)):
                if i % 20 == 19:
                    with lock:
                        path.write_text(json.dumps(table, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        path.write_text(json.dumps(table, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        print(f"{lang}: {len(table)}/{len(texts)} translated ({failed} failed batches)", flush=True)


if __name__ == "__main__":
    main()
