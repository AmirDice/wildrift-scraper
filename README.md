# WrTrueMeta

The repository behind [wrtruemeta.com](https://wrtruemeta.com): a Wild Rift
meta tracker built on first-party data -- the win rates of the top players on
every champion's leaderboard, captured from the game itself, not aggregated
from other sites.

## How the parts fit

```
phone (ADB) -> src/ scraper -> data/captures/ -> extraction -> data/*.json|csv
                                                       |
                        scripts/ exports  ->  web-next/src/data/  ->  the site
                                                       |
                              web/ + api/  ->  the build advisor (own deploy)
```

| Piece | What it is |
|---|---|
| `src/` | The ADB scraper: captures leaderboard/profile/build frames from a real device, plus the offline frame extractor (`extract_frames`). |
| `data/` | Everything captured and derived: win rates, items, runes, champions, ability formulas, the official patch archive. |
| `scripts/` | The pipeline: exports (`export_captures`, `export_json`, `export_engine_data`, `export_champion_details`, `build_ladder_pulse`), LLM extraction (`extract_formulas`), patch appliers (`apply_patch_*`, which assert before writing), the advisor deploy, and the admin ops runner. |
| `web-next/` | The site: Next.js, deployed on Vercel from `origin/main`. Reads only committed JSON under `web-next/src/data/`. |
| `web/` + `api/` | The build advisor: a Python serverless function (own Vercel project, deployed by `scripts/deploy_advisor.py --deploy`) that generates builds with an LLM grounded in the scraped data. |
| `tests/` | Data-integrity tests, run by CI on every push. No API keys in CI, so nothing there can scrape or call an LLM. |

## Day-to-day operation

The admin page on the site has an Operations panel: scrape, extract, refresh
exports, fetch patch notes, publish, and redeploy the advisor are all one
click. Those buttons are executed on the collection machine by:

```powershell
python -m scripts.ops_runner
```

which also starts hidden at logon via a Startup-folder launcher. Jobs queue
while it is offline.

## Local setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-scrape.txt   # scraper + pipeline
pip install -r requirements-dev.txt      # test suite
```

`requirements.txt` alone is the advisor function's slim bundle -- do not grow
it casually; the serverless bundle has a 250MB ceiling.

OCR needs the Tesseract binary (`winget install UB-Mannheim.TesseractOCR`);
Gemini-engine extraction reads `GEMINI_API_KEY` from `web-next/.env.local`.
Scraping needs ADB and a connected device with Wild Rift installed. Secrets
live in `web-next/.env.local` (gitignored) and the Vercel projects, never in
the repo.

## When a new patch lands

Applying a balance patch touches five surfaces, and history shows missing one
goes unnoticed for weeks: advisor sources, `data/runes.json` -> engine export,
champion details export, change history + summary, and formula re-extraction
for changed champions -- then a cache-version bump and an advisor redeploy.
The `scripts/apply_patch_*.py` scripts document every applied delta and assert
current values before writing, so a double-run or a shifted base fails loudly.
