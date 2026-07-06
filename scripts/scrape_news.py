"""Scrape the official Wild Rift news feed for a news/SEO index page.

The official site (wildrift.leagueoflegends.com/en-gb/news) is a Next.js app; the
article list is embedded in its __NEXT_DATA__ JSON (Sanity CMS content). We parse
that, pull each article's title, excerpt, date, category, image and link, and
write a compact feed. We link out to the official articles (index/aggregate), we
don't rehost content.

Output: data/news.json

Run:
    python -m scripts.scrape_news
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "news.json"
NEWS_URL = "https://wildrift.leagueoflegends.com/en-gb/news/"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def _text(html_or_str) -> str:
    if isinstance(html_or_str, dict):
        html_or_str = html_or_str.get("body", "")
    return " ".join(BeautifulSoup(str(html_or_str), "html.parser").get_text(" ").split())


def _url(action) -> str | None:
    if isinstance(action, dict):
        payload = action.get("payload") or {}
        return payload.get("url") or action.get("url")
    return None


def _collect(node, out: list[dict]) -> None:
    """Walk the __NEXT_DATA__ tree, collecting article-like items."""
    if isinstance(node, dict):
        if node.get("title") and node.get("publishedAt") and ("action" in node or "media" in node):
            out.append(node)
        for v in node.values():
            _collect(v, out)
    elif isinstance(node, list):
        for v in node:
            _collect(v, out)


def main() -> None:
    html = requests.get(NEWS_URL, headers=HEADERS, timeout=25).text
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.DOTALL)
    if not m:
        raise SystemExit("no __NEXT_DATA__ on news page")
    data = json.loads(m.group(1))

    raw: list[dict] = []
    _collect(data, raw)

    articles: list[dict] = []
    seen: set[str] = set()
    for a in raw:
        title = str(a.get("title", "")).strip()
        url = _url(a.get("action"))
        key = title.lower()
        if not title or key in seen:
            continue
        seen.add(key)
        media = a.get("media") or a.get("imageMedia") or {}
        image = media.get("url") if isinstance(media, dict) else None
        cat = a.get("category") or {}
        articles.append({
            "title": title,
            "excerpt": _text(a.get("description"))[:200],
            "date": a.get("publishedAt"),
            "url": url,
            "category": (cat.get("title") if isinstance(cat, dict) else None) or "News",
            "image": f"{image}?w=640&h=360&fit=crop&auto=format" if image else None,
        })

    articles.sort(key=lambda x: x["date"] or "", reverse=True)
    articles = articles[:24]

    OUT.write_text(json.dumps({
        "source": NEWS_URL,
        "count": len(articles),
        "articles": articles,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(articles)} articles)")
    for a in articles[:5]:
        print(f"  {a['date'][:10] if a['date'] else '????'} [{a['category']}] {a['title'][:56]}")


if __name__ == "__main__":
    main()
