"""Re-take the home-page hero screenshots.

    python scripts/shoot_hero.py            # needs `npm run dev` on :3000

Writes public/shots/{build,counter,draft,tier}.jpg. The overlay slide's picture
is NOT taken here: it is the Android app's own screen, copied from
wrdraft-overlay/images/captured/_app.png, and the only way to refresh it is a
screenshot from a phone.

Three things this does that a manual screenshot cannot:

  NO WALLPAPER. The site's background painting is hidden and replaced with a
  flat ground. A shot that kept the painting would sit on top of the same
  painting in the hero and read as a picture of a picture.

  NO CHROME. The banner, nav, tool cards, footer, social dock and the Next dev
  badge are all hidden, so the frame holds the tool and nothing else.

  NO TOURS. Every guided tour is marked as seen before the first paint. They
  open on a first visit and dim the page behind a spotlight, which is exactly
  what a fresh browser profile gives you.

The draft assistant is seeded through sessionStorage, because an empty board
shows the furniture rather than the point: five bans, two allies, four enemies
and Lee Sin in my seat, which is also what makes the counter-build row and the
enemy read appear.

Frames are 16:9 in the hero (aspect-video, object-cover object-top), so a clip
near 1340x700 arrives with nothing cropped. y0 skips whatever sits above the
part worth showing; re-check it after a layout change, since it is measured in
pixels rather than anchored to an element.
"""

import json
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright
from PIL import Image

BASE = "http://localhost:3000"
DST = "public/shots"
WIDTH = 1120          # displayed at ~560px, so 2x
QUALITY = 72

TOURS = ["wtm_tour_counter_v3", "wtm_tour_generate_v2", "wtm_tour_lab_v2", "tour:tier-list:v1"]

HIDE = """
  body > *:not(main):not(script):not(style) { display: none !important; }
  body { background: #080b14 !important; }
  main { padding-top: 0 !important; }
  nextjs-portal { display: none !important; }
"""

DRAFT = {
    "bans": ["yone", "zed", "kaisa", "nautilus", "vi", None, None, None, None, None],
    "allies": ["thresh", "lux", None, None],
    "enemies": ["hecarim", "pantheon", "kayn", "jinx", None],
    "me": "lee-sin",
    "myRole": "Jungle",
}
POOL = ["lee-sin", "hecarim", "kayn", "olaf", "graves"]

# name, path, clip height, pixels to skip above the interesting part
SHOTS = [
    ("build", "/build/hecarim", 700, 0),
    ("counter", "/build?champion=Hecarim&tab=counter", 700, 290),
    ("draft", "/draft", 760, 0),
    ("tier", "/tier-list", 700, 305),
]


def shoot(browser, name: str, path: str, tall: int, y0: int) -> None:
    page = browser.new_page(viewport={"width": 1340, "height": tall + y0}, device_scale_factor=2)
    page.add_init_script(
        "try{%s;sessionStorage.setItem('draft:state',%s);localStorage.setItem('draft:pool',%s);}catch(e){}"
        % (
            ";".join(f"localStorage.setItem('{key}','1')" for key in TOURS),
            json.dumps(json.dumps(DRAFT)),
            json.dumps(json.dumps(POOL)),
        )
    )
    page.goto(BASE + path, wait_until="load", timeout=120_000)
    page.wait_for_timeout(4500)          # client components, icons, the roster strip
    page.add_style_tag(content=HIDE)
    page.wait_for_timeout(700)
    box = page.locator("main").bounding_box()
    # The PNG is scratch: it is 2x and lossless, and public/ is served, so only
    # the JPEG belongs there.
    raw = Path(tempfile.gettempdir()) / f"wrtm_shot_{name}.png"
    page.screenshot(
        path=str(raw),
        clip={
            "x": 0,
            "y": max(0, box["y"]) + y0,
            "width": 1340,
            "height": min(tall, max(200, box["height"] - y0)),
        },
    )
    im = Image.open(raw).convert("RGB")
    im = im.resize((WIDTH, round(im.height * WIDTH / im.width)), Image.LANCZOS)
    im.save(f"{DST}/{name}.jpg", quality=QUALITY, optimize=True, progressive=True)
    print(f"{name}: {im.size[0]}x{im.size[1]}")
    page.close()


def main() -> int:
    wanted = set(sys.argv[1:])
    with sync_playwright() as p:
        # The installed Chrome, not a Playwright download: `playwright install`
        # has never been run on this machine and the channel needs no browser
        # of its own.
        browser = p.chromium.launch(channel="chrome")
        for name, path, tall, y0 in SHOTS:
            if wanted and name not in wanted:
                continue
            shoot(browser, name, path, tall, y0)
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
