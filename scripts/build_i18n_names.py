"""Localized champion, item, rune and spell names for the translated pages.

    python scripts/build_i18n_names.py

Writes web-next/src/data/i18n_names.json:
    {"champions": {"Ahri": {"zh": "...", "ko": "...", ...}}, "items": {...},
     "runes": {...}, "spells": {...}}

Source: Riot's public Data Dragon for League of Legends. Wild Rift shares
most names with League, matched here by the English name; anything Wild
Rift-only (or renamed) is simply absent and the pages fall back to English.
Chinese champion names come from the official Wild Rift China feed
(web-next/src/data/cn.json cnName) instead, because that is what Chinese
Wild Rift players see in their client.
"""
from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB_DATA = ROOT / "web-next" / "src" / "data"
OUT = WEB_DATA / "i18n_names.json"
LOCALES = {"zh": "zh_CN", "ko": "ko_KR", "tr": "tr_TR", "fr": "fr_FR", "pl": "pl_PL", "es": "es_ES"}


def get(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "wrtruemeta-i18n-build"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def main() -> None:
    version = get("https://ddragon.leagueoflegends.com/api/versions.json")[0]
    base = f"https://ddragon.leagueoflegends.com/cdn/{version}/data"

    site = json.loads((WEB_DATA / "site.json").read_text(encoding="utf-8"))
    our_champs = {key(c["name"]): c["name"] for c in site["champions"]}
    our_items = {key(i["name"]): i["name"] for i in json.loads((WEB_DATA / "items.json").read_text(encoding="utf-8"))}
    engine = json.loads((WEB_DATA / "engine.json").read_text(encoding="utf-8"))
    our_runes = {key(n): n for n in engine.get("runes", {})}
    our_spells = {key(s["name"]): s["name"] for s in json.loads((WEB_DATA / "spells.json").read_text(encoding="utf-8"))}

    def by_id(lang: str, path: str):
        return get(f"{base}/{lang}/{path}")

    en_champ = by_id("en_US", "champion.json")["data"]
    en_items = by_id("en_US", "item.json")["data"]
    en_runes = by_id("en_US", "runesReforged.json")
    en_spells = by_id("en_US", "summoner.json")["data"]

    def rune_names(trees) -> dict[int, str]:
        out = {}
        for tree in trees:
            for slot in tree["slots"]:
                for rune in slot["runes"]:
                    out[rune["id"]] = rune["name"]
        return out

    en_rune_ids = rune_names(en_runes)
    result = {"version": version, "champions": {}, "items": {}, "runes": {}, "spells": {}}
    for short, lang in LOCALES.items():
        champs = by_id(lang, "champion.json")["data"]
        items = by_id(lang, "item.json")["data"]
        runes = rune_names(by_id(lang, "runesReforged.json"))
        spells = by_id(lang, "summoner.json")["data"]
        for cid, c in en_champ.items():
            ours = our_champs.get(key(c["name"]))
            if ours and cid in champs:
                # zh_CN swaps the fields: "name" is the epithet (Nilah ->
                # "Joy Unbound"), "title" is what players call the champion.
                field = "title" if short == "zh" else "name"
                result["champions"].setdefault(ours, {})[short] = champs[cid][field]
        for iid, it in en_items.items():
            ours = our_items.get(key(it["name"]))
            if ours and iid in items:
                result["items"].setdefault(ours, {})[short] = items[iid]["name"]
        for rid, name in en_rune_ids.items():
            ours = our_runes.get(key(name))
            if ours and rid in runes:
                result["runes"].setdefault(ours, {})[short] = runes[rid]
        for sid, sp in en_spells.items():
            ours = our_spells.get(key(sp["name"]))
            if ours and sid in spells:
                result["spells"].setdefault(ours, {})[short] = spells[sid]["name"]

    # Official Wild Rift China names win for Chinese champions.
    cn = json.loads((WEB_DATA / "cn.json").read_text(encoding="utf-8"))
    for c in cn.get("champions", []):
        if c.get("cnName") and c.get("name") in our_champs.values():
            result["champions"].setdefault(c["name"], {})["zh"] = c["cnName"]

    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    print(f"ddragon {version}: champions {len(result['champions'])}/{len(our_champs)}, "
          f"items {len(result['items'])}/{len(our_items)}, runes {len(result['runes'])}/{len(our_runes)}, "
          f"spells {len(result['spells'])}/{len(our_spells)}")


if __name__ == "__main__":
    main()
