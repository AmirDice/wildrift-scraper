"""Fill the interface translation tables for the shared page tree.

    node web-next/scripts/extract-ui-strings.mjs > keys.json   (run from web-next)
    python scripts/translate_ui_strings.py [--langs zh,vi] [--model gemini-3.5-flash-lite]

Reads every <T>/t() key (scripts/extract-ui-strings.mjs), translates only the
keys a language table does not have yet, and writes
web-next/src/i18n/ui/<lang>.json. Existing translations are never touched,
so a hand-corrected string survives every re-run.

Rules given to the model: keep {placeholders} exactly, keep champion, item,
rune and spell names in English, use the game's own terms (glossary below),
no em dashes, no emojis, keep it as short as the English.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web-next"
OUT = WEB / "src" / "i18n" / "ui"
LANGS = {
    "zh": "Simplified Chinese (as used in League of Legends: Wild Rift China)",
    "vi": "Vietnamese (the game is called Tốc Chiến in Vietnam)",
    "tr": "Turkish", "fr": "French", "pl": "Polish", "ko": "Korean", "es": "Spanish",
}
GLOSSARY = (
    "Glossary: Wild Rift = the game (in Vietnamese say Tốc Chiến; in Chinese 英雄联盟手游); "
    "tier list, win rate, pick rate, ban rate, build, runes, keystone, summoner spells, counter, matchup, "
    "Baron Lane, Jungle, Mid Lane, Dragon Lane, Support (lanes), patch, leaderboard, Legendary (the top China "
    "ranked bracket), EU, NA, CN (server names, keep as is), OTP (one-trick player, keep), GOD/S/A/B/C tiers (keep letters)."
)


def load_env() -> None:
    env = WEB / ".env.local"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\s*(GEMINI_API_KEY|GOOGLE_API_KEY)\s*=\s*\"?([^\"\s]+)", line)
            if m:
                os.environ.setdefault(m.group(1), m.group(2))


def keys() -> list[str]:
    out = subprocess.run(["node", "scripts/extract-ui-strings.mjs"], cwd=WEB, capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(out.stdout)


def translate(client, model: str, lang: str, batch: list[str]) -> dict[str, str]:
    from google.genai import types
    prompt = (
        f"Translate these website interface strings from English into {LANGS[lang]}.\n"
        f"The website is a stats site for the mobile game League of Legends: Wild Rift. {GLOSSARY}\n"
        "Rules: keep every {placeholder} exactly as written (same braces, same name). Keep champion, item, rune "
        "and summoner spell names in English. Keep the translation about as short as the English; a label stays "
        "a label. No em dashes, no emojis. Leading or trailing punctuation such as '·', ':' or '%' stays in place. "
        f"Return ONLY a JSON array of exactly {len(batch)} strings: the translations, in the same order as the "
        "numbered input (do not repeat the English, do not include the numbers).\n\n"
        + "\n".join(f"{i + 1}. {json.dumps(s, ensure_ascii=False)}" for i, s in enumerate(batch))
    )
    r = client.models.generate_content(
        model=model, contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0,
                                           thinking_config=types.ThinkingConfig(thinkingLevel=types.ThinkingLevel.LOW)))
    data = json.loads(r.text)
    if not isinstance(data, list) or len(data) != len(batch):
        raise ValueError(f"expected {len(batch)} translations, got {len(data) if isinstance(data, list) else type(data).__name__}")
    good = {}
    for en, tr_ in zip(batch, data):
        if not isinstance(tr_, str) or not tr_.strip():
            continue
        # Placeholders must survive exactly; reject the string otherwise.
        if sorted(re.findall(r"\{\w+\}", en)) != sorted(re.findall(r"\{\w+\}", tr_)):
            continue
        good[en] = tr_.replace("—", ", ").strip()
    return good


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--langs", default=",".join(LANGS))
    ap.add_argument("--model", default="gemini-3.5-flash-lite")
    ap.add_argument("--batch", type=int, default=80)
    args = ap.parse_args()
    load_env()
    from google import genai
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY") or os.environ["GOOGLE_API_KEY"])
    all_keys = keys()
    for lang in args.langs.split(","):
        path = OUT / f"{lang}.json"
        table = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        missing = [k for k in all_keys if k not in table]
        print(f"{lang}: {len(missing)} to translate", flush=True)
        for i in range(0, len(missing), args.batch):
            batch = missing[i:i + args.batch]
            try:
                table.update(translate(client, args.model, lang, batch))
            except Exception as exc:  # noqa: BLE001
                print(f"  batch {i}: {exc}", file=sys.stderr)
            path.write_text(json.dumps(dict(sorted(table.items())), ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{lang}: {len(table)}/{len(all_keys)} translated", flush=True)


if __name__ == "__main__":
    main()
