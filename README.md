# wildrift-scraper

Python bot that scrapes Wild Rift Top-200 leaderboard winrates per champion
via ADB on MuMu Player.

## Stack

- **ADB** (`platform-tools`) — screenshots and tap/swipe input
- **MuMu Player** — Android emulator, ADB on `127.0.0.1:7555`
- **OpenCV + NumPy** — image handling and the coord-mapper GUI
- **pytesseract** — OCR for reading winrate numbers (requires Tesseract binary)

## Setup

```powershell
# from this folder
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Tesseract (only needed once we wire up OCR)

`pytesseract` is just a wrapper — the actual OCR engine must be installed
separately. On Windows, the easiest path is:

```powershell
winget install UB-Mannheim.TesseractOCR
```

Then either add `C:\Program Files\Tesseract-OCR` to PATH, or set
`pytesseract.pytesseract.tesseract_cmd` in code.

### ADB + MuMu

1. Start MuMu Player and launch Wild Rift.
2. Confirm ADB sees it:

   ```powershell
   adb connect 127.0.0.1:7555
   adb devices
   ```

   You should see `127.0.0.1:7555  device`.

## Coordinate mapper

Used to map UI element positions (search button, first leaderboard row,
winrate text bounding box, etc.) into a reusable JSON file.

```powershell
python -m src.coordinate_mapper
# or with explicit args:
python -m src.coordinate_mapper --device 127.0.0.1:7555 --output coords/ui_map.json
```

Controls (image window must be focused):

| key         | action                                                  |
|-------------|---------------------------------------------------------|
| left-click  | record a point; terminal prompts for a name            |
| `u`         | undo last recorded point                                |
| `r`         | grab a fresh screenshot (keeps existing points)         |
| `s`         | save to JSON                                            |
| `q` / ESC   | quit (prompts to save if unsaved)                       |

Output JSON shape:

```json
{
  "device": "127.0.0.1:7555",
  "resolution": { "width": 1280, "height": 720 },
  "points": {
    "search_button": { "x": 1050, "y": 80 },
    "first_champion_tile": { "x": 200, "y": 200 }
  }
}
```

If the device resolution is larger than your monitor, the window is
auto-scaled for display — click positions are still recorded in original
device coordinates.

## Screenshot capture

Grab a frame from the device and save it (for OCR tuning, region selection, etc.):

```powershell
python -m src.screenshot data/leaderboard_ahri.png
```

## Region picker (find OCR crop coords visually)

Instead of eyeballing pixel coordinates, drag a rectangle around the text you
want to OCR and the tool prints the `--crop` string:

```powershell
python -m src.region_picker data\leaderboard_sample.png
# or from a live device:
python -m src.region_picker --device 127.0.0.1:7555
```

Controls: click-drag to draw a rectangle, `o` runs OCR on it immediately,
`c` reprints the crop string, `r` refreshes the screenshot (device mode),
`q` quits.

## OCR tuning

`src/ocr.py` reads winrate-style text. Tune it against a saved screenshot by
specifying a crop region (`x,y,w,h` in device pixels) — easiest to find with
`src.region_picker` above:

```powershell
python -m src.ocr data/leaderboard_ahri.png --crop 980,310,140,40
python -m src.ocr data/leaderboard_ahri.png --crop 980,310,140,40 --debug
```

`--debug` writes the preprocessed image (post grayscale + upscale + Otsu) so
you can see what Tesseract actually saw. If results are unreliable, common
fixes are: bigger crop, different `scale=` in `preprocess()`, or relaxing
the character whitelist in `WINRATE_TESSERACT_CONFIG`.

Tesseract binary discovery order:
1. `TESSERACT_CMD` env var
2. `tesseract` on PATH
3. `C:\Program Files\Tesseract-OCR\tesseract.exe`

## CSV output schema

`src/storage.py` writes one row per leaderboard entry:

| column        | example                       |
|---------------|-------------------------------|
| champion      | `Ahri`                        |
| rank          | `1`                           |
| player_name   | `KR1Faker`                    |
| winrate       | `61.8`                        |
| captured_at   | `2026-05-27T18:42:11+00:00`   |

## Project layout

```
wildrift-scraper/
├── src/
│   ├── adb_client.py        # subprocess wrapper around `adb`
│   ├── coordinate_mapper.py # interactive UI coord tool (single points)
│   ├── region_picker.py     # drag-to-pick rectangles for OCR crop coords
│   ├── screenshot.py        # grab + save a screenshot
│   ├── ocr.py               # winrate OCR + tuning CLI
│   └── storage.py           # CSV writer
├── coords/                  # saved UI coordinate JSONs
├── data/                    # screenshots + scraped CSVs (gitignored)
├── requirements.txt
└── README.md
```
