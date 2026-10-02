# September 25 leaderboard migration

The 2340×1080 leaderboard now uses champion portraits and a persistent
left sidebar. Selecting a player does not open a mini-profile popup;
build and profile buttons are on the right rail.

## Completed offline

- Portrait identification and selected-champion detection use the supplied screenshots.
- Rank-column calibration migrates to the new layout at startup without replacing
  account-name or fling-distance settings. Explicit `--badge-x` also resets its
  trusted reference, so old calibration cannot undo the override.
- Player-name crops and sidebar recovery use the new geometry.
- Capture manifests record `leaderboard_layout` and `badge_x_range`, keeping
  offline tap verification independent of future live calibration changes.
- Selected-player evidence is saved as `selection_frame`, not `popup_frame`.
  The removed popup's account level/tier/tag are not extracted from this screen.
  Legacy popup extraction and legacy name crops remain supported for old sessions.

## Still requires a connected device

Use a working Python 3.11+ environment with `requirements-scrape.txt` installed
and an authorized device listed by `adb devices`. The repository's current
`.venv` launcher points to a missing Python installation and needs repairing
before it can be used normally.

Open Xin Zhao's leaderboard at the top, then run a short smoke test:

```powershell
python -m src.scrape_timed --device DEVICE_SERIAL --target "Xin Zhao" --n 3 --auto-scroll --capture-only --builds --stats --step-wait 1.2
```

Inspect the saved build, strip, and both stats frames for the same player;
verify return navigation. Then test scrolling to double-digit ranks, switching
champions and recovery before starting a full collection. Existing fixtures only
show ranks 1–4; they cannot validate deep-rank scrolling or live transition timing.

New captures intentionally do not produce mini-popup identity fields. If those
fields are needed, capture the full profile and define a separate validated
extractor using a fresh screenshot of that page.
