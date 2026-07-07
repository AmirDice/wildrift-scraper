"""Scrape official China (国服) Wild Rift champion win/pick/ban rates.

Source: Tencent's official Wild Rift site (lolm.qq.com) exposes daily champion
statistics via two JSON endpoints used by its 国服数据 page:

  hero list:  https://game.gtimg.cn/images/lgamem/act/lrlib/js/heroList/hero_list.js
  rank data:  https://mlol.qt.qq.com/go/lgame_battle_info/hero_rank_list_v2

The rank data is keyed by cumulative rank bracket (0-4: Diamond+ / Master+ /
Challenger+ / Sovereign) then by position (1-5: top/jungle/mid/bot/support). Each entry has
win_rate_percent, appear_rate_percent (pick), forbid_rate_percent (ban) and
strength_level (tier). This is official, daily, high-elo data — a real CN source
to sit alongside our EU top-50 dataset.

Champion names are Chinese; we bridge them to our English roster once (via Gemini,
validated against site.json) and cache the map to data/cn_hero_map.json.

Output: data/cn_winrates.json

Run (Gemini key only needed the first time, to build the name map):
    GEMINI_API_KEY=... python -m scripts.scrape_cn
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "web-next" / "src" / "data" / "site.json"
NAME_MAP = ROOT / "data" / "cn_hero_map.json"
OUT = ROOT / "data" / "cn_winrates.json"
WEB_OUT = ROOT / "web-next" / "src" / "data" / "cn.json"  # what the frontend reads

HERO_LIST_URL = "https://game.gtimg.cn/images/lgamem/act/lrlib/js/heroList/hero_list.js"
RANK_URL = "https://mlol.qt.qq.com/go/lgame_battle_info/hero_rank_list_v2"
HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://lolm.qq.com/"}

# bracket keys verified against the site's rank tabs (钻石/大师/王者/峡谷之巅)
BRACKET_LABELS = {
    "0": "All ranks", "1": "Diamond+", "2": "Master+", "3": "Challenger+", "4": "Sovereign",
}
# Challenger and above (includes Sovereign): a larger, steadier top-elo sample
# than the Sovereign tier alone, so it's what the frontend surfaces as "highest".
DEFAULT_BRACKET = "3"
# position codes verified empirically against the champion pools per lane
POSITION_LABELS = {"1": "Mid", "2": "Baron", "3": "Dragon", "4": "Support", "5": "Jungle"}


def _slug(name: str) -> str:
    s = name.lower().replace("&", "and").replace("'", "")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def fetch_hero_list() -> dict[str, str]:
    """heroId -> Chinese name."""
    txt = requests.get(HERO_LIST_URL, headers=HEADERS, timeout=20).text
    obj = json.loads(txt)
    return {hid: h["name"] for hid, h in obj["heroList"].items()}


def fetch_rank() -> dict:
    r = requests.get(RANK_URL, headers=HEADERS, timeout=20).json()
    return r["data"]


def build_name_map(cn_names: dict[str, str], english: list[str]) -> dict[str, str]:
    """heroId -> English name. Cached; uses Gemini once to translate CN->EN."""
    if NAME_MAP.exists():
        return json.loads(NAME_MAP.read_text(encoding="utf-8"))

    from google import genai
    from google.genai import types

    prompt = (
        "Map each Chinese Wild Rift champion name to its exact English name, chosen "
        "ONLY from the provided English list. Return a JSON object {chineseName: englishName}. "
        "If a Chinese name has no match in the list, map it to \"\".\n\n"
        f"English champion names:\n{json.dumps(english, ensure_ascii=False)}\n\n"
        f"Chinese names to map:\n{json.dumps(sorted(set(cn_names.values())), ensure_ascii=False)}"
    )
    client = genai.Client()
    resp = client.models.generate_content(
        model="gemini-2.5-flash", contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0),
    )
    cn_to_en = json.loads(re.search(r"\{.*\}", resp.text, re.DOTALL).group(0))
    eng_set = set(english)
    hero_map: dict[str, str] = {}
    unmatched = []
    for hid, cn in cn_names.items():
        en = cn_to_en.get(cn, "")
        if en and en in eng_set:
            hero_map[hid] = en
        else:
            unmatched.append(f"{hid}:{cn}")
    NAME_MAP.write_text(json.dumps(hero_map, ensure_ascii=False, indent=2), encoding="utf-8")
    if unmatched:
        print(f"  ! {len(unmatched)} unmapped heroes: {unmatched}")
    print(f"  name map: {len(hero_map)}/{len(cn_names)} bridged -> {NAME_MAP.relative_to(ROOT)}")
    return hero_map


def main() -> None:
    site_champs = json.loads(SITE.read_text(encoding="utf-8"))["champions"]
    english = [c["name"] for c in site_champs]
    eu_role = {c["name"]: c["role"] for c in site_champs}  # align CN lane to EU role
    cn_names = fetch_hero_list()
    rank = fetch_rank()
    hero_map = build_name_map(cn_names, english)

    date = None
    # per champion: byBracket -> {wr, pick, ban, strength, position} at primary lane
    champs: dict[str, dict] = {}
    for bracket, positions in rank.items():
        for pos, entries in positions.items():
            for e in entries:
                hid = e["hero_id"]
                en = hero_map.get(hid)
                if not en:
                    continue
                date = date or e.get("dtstatdate")
                rec = champs.setdefault(en, {
                    "name": en, "slug": _slug(en), "heroId": hid,
                    "cnName": cn_names.get(hid, ""), "byBracket": {},
                })
                pick = float(e["appear_rate_percent"])
                cand = {
                    "winRate": float(e["win_rate_percent"]),
                    "pickRate": pick,
                    "banRate": float(e["forbid_rate_percent"]),
                    "strength": int(e["strength_level"]),
                    "position": POSITION_LABELS.get(pos, pos),
                }
                # Align the CN lane to the champion's EU role so cross-server stats
                # compare like-for-like (e.g. Olaf is Baron on EU but most-picked
                # Jungle in CN — we want his Baron win rate). The EU-role lane always
                # wins over a more-picked lane; ties fall back to highest pick rate.
                target = eu_role.get(en)
                stored = rec["byBracket"].get(bracket)
                cand_match = cand["position"] == target
                if stored is None:
                    take = True
                elif cand_match != (stored["position"] == target):
                    take = cand_match
                else:
                    take = pick > stored["pickRate"]
                if take:
                    rec["byBracket"][bracket] = cand

    out = {
        "source": "lolm.qq.com (official China server data)",
        "date": date,
        "bracketLabels": BRACKET_LABELS,
        "defaultBracket": DEFAULT_BRACKET,
        "nChampions": len(champs),
        "champions": sorted(champs.values(), key=lambda c: c["name"]),
    }
    payload = json.dumps(out, ensure_ascii=False, indent=2)
    OUT.write_text(payload, encoding="utf-8")
    WEB_OUT.write_text(payload, encoding="utf-8")  # keep the frontend copy in sync
    print(f"wrote {OUT.relative_to(ROOT)} + {WEB_OUT.relative_to(ROOT)} ({len(champs)} champions, date {date})")

    # dated snapshot (highest bracket) for patch-over-patch history
    from datetime import datetime as _dt
    snap_date = (_dt.strptime(date, "%Y%m%d").date().isoformat()
                 if date and len(date) == 8 and date.isdigit() else (date or "unknown"))
    hist = ROOT / "data" / "history" / "cn"
    hist.mkdir(parents=True, exist_ok=True)
    snap_champs = {}
    for c in champs.values():
        e = c["byBracket"].get(DEFAULT_BRACKET)
        if e:
            snap_champs[c["slug"]] = {"wr": e["winRate"], "pick": e["pickRate"], "ban": e["banRate"]}
    (hist / f"{snap_date}.json").write_text(
        json.dumps({"date": snap_date, "region": "cn", "champions": snap_champs},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  snapshot: data/history/cn/{snap_date}.json ({len(snap_champs)} champions)")


if __name__ == "__main__":
    main()
