#!/usr/bin/env bash
# Publish a finished CN ladder collection to the site, in dependency order.
#
# Run from the repo root once every CN session has an extracted.csv:
#
#     bash scripts/publish_cn.sh
#
# WHY --min-ranks 15. The default is 40, which exists to reject sessions whose
# extraction failed wholesale on a 50-row board. CN boards are 30 deep, so 40
# rejects EVERY one of them and the export reports "no complete extracted
# sessions found". 15 keeps every genuine capture, including the handful that
# came in short (Jarvan 17, Soraka 17), and still rejects a wholesale failure,
# which reads 0.
#
# WHY EU AND NA ARE RE-EXPORTED AT THE END. Each region's site file carries the
# cross-server best-player podium, and players-global.json is written only by
# the EU run. Both are built from every winrates_*.csv that exists, so adding
# CN changes them -- leaving them alone would publish a "global" podium that
# silently excludes the server just added to it.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "== 1/6  CN captures -> winrates_cn.csv, players/cn, player-index-cn.json"
python -m scripts.export_captures --region cn --min-ranks 15

echo
echo "== 2/6  CN builds -> ladder_pulse_cn.json, ladder_consensus_cn.json"
python -m scripts.build_ladder_pulse --region cn --min-ranks 15

echo
echo "== 3/6  CN builds -> ladder_builds_cn.json"
python -m scripts.export_ladder_builds --region cn

echo
echo "== 4/6  CN -> site_cn.json, players-cn.json, history/cn_ladder"
python -m scripts.export_json --region cn

echo
echo "== 5/6  NA re-export (its global podium now includes CN)"
python -m scripts.export_json --region na

echo
echo "== 6/6  EU re-export (site.json + players-global.json, all three servers)"
python -m scripts.export_json

echo
echo "done. Typecheck before deploying -- empty arrays in src/data/*.json"
echo "infer as never[] and fail the next build:"
echo "    cd web-next && npx tsc --noEmit"
