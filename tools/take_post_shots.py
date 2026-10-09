"""Screenshots for the write-up, taken from the real app with Playwright.

    python tools/take_post_shots.py        # -> docs/post/*.png

Uses the processed test days already in trips/ (run `python -m lookout process
trips/test-hunza` and `trips/test-skardu` first). Images are taken at 2x pixel
density so they stay sharp on DEV. Also renders the 1000x420 cover image.
"""
from __future__ import annotations

import base64
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lookout.server import App, make_handler  # noqa: E402

OUT = ROOT / "docs" / "post"
PORT = 8798
URL = f"http://127.0.0.1:{PORT}/"


def ready(page, day: str) -> None:
    page.goto(f"{URL}#/day/{day}")
    page.wait_for_function(
        f"(document.querySelector('.day-head h1')||{{}}).textContent === '{day}' && "
        "[...document.querySelectorAll('.card img.main')].every((i) => i.complete && i.naturalWidth > 0)")
    page.wait_for_timeout(300)


def shots(p) -> None:
    browser = p.chromium.launch(channel="chrome", headless=True)

    def ctx(w, h, scale=2, dark=False, mobile=False):
        return browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=scale,
                                   color_scheme="dark" if dark else "light", is_mobile=mobile,
                                   has_touch=mobile)

    # 1. the app on a processed day, and the home screen
    c = ctx(1440, 900)
    page = c.new_page()
    page.goto(URL)
    page.wait_for_selector(".hero h1")
    page.wait_for_function("document.querySelector('#model-pill').textContent.includes('ready')")
    page.screenshot(path=OUT / "08-home.png")
    ready(page, "test-hunza")
    page.screenshot(path=OUT / "01-app.png")

    # 2. the map with a photo preview on hover
    pin = page.locator(".pin[data-stop='S04'] circle").last
    pin.hover()
    page.wait_for_timeout(600)
    box = page.locator(".map").bounding_box()
    page.screenshot(path=OUT / "03-map.png", clip={"x": box["x"], "y": box["y"],
                                                   "width": box["width"], "height": box["height"]})
    page.mouse.move(5, 5)

    # 3. downgrades: what the model said, and why it was not kept
    card = page.locator("#stop-S03")
    card.locator("details.down summary").click()
    card.locator(".fold-btn").click()
    page.wait_for_timeout(200)
    card.screenshot(path=OUT / "04-downgrades.png")
    c.close()

    # 4. evidence and a photo/voice disagreement (Satpara: the hiker mentions the dam)
    c = ctx(1280, 900)
    page = c.new_page()
    ready(page, "test-skardu")
    card = page.locator("#stop-S02")
    for row in card.locator(".checks > .chip-row").all():
        label = row.locator(".lab").inner_text()
        if any(k in label for k in ("Moraine dam", "Dam or outlet", "Water body")):
            row.click()
    page.wait_for_timeout(200)
    card.screenshot(path=OUT / "02-evidence.png")
    c.close()

    # 5. dark mode
    c = ctx(1440, 900, dark=True)
    page = c.new_page()
    ready(page, "test-hunza")
    page.screenshot(path=OUT / "06-dark.png")
    c.close()

    # 6. phone
    c = ctx(390, 844, scale=3, mobile=True)
    page = c.new_page()
    ready(page, "test-hunza")
    page.evaluate("document.querySelector('.stats').scrollIntoView()")
    page.wait_for_timeout(300)
    page.screenshot(path=OUT / "05-phone.png")
    c.close()

    # 7. the shareable trip page
    c = ctx(1200, 900)
    page = c.new_page()
    page.goto(f"{URL}api/days/test-hunza/out/trip.html")
    page.wait_for_load_state("load")
    page.screenshot(path=OUT / "07-trip-page.png")
    c.close()

    # 8. cover image, 1000x420 as DEV crops it
    app_png = base64.b64encode((OUT / "01-app.png").read_bytes()).decode()
    mark = (ROOT / "lookout" / "ui" / "favicon.svg").read_text(encoding="utf-8")
    c = ctx(1000, 420)
    page = c.new_page()
    page.set_content(f"""<!doctype html><html><head><meta charset="utf-8"><style>
      *{{box-sizing:border-box}} body{{margin:0;width:1000px;height:420px;overflow:hidden;
        background:linear-gradient(135deg,#0d2f3a 0%,#123b4a 55%,#17808f 100%);
        font-family:system-ui,"Segoe UI",sans-serif;color:#fff;position:relative}}
      .txt{{position:absolute;left:52px;top:58px;width:430px}}
      .logo{{display:flex;align-items:center;gap:12px;font-weight:700;font-size:20px;opacity:.95}}
      .logo svg{{width:38px;height:38px}}
      h1{{font-size:44px;line-height:1.08;margin:26px 0 14px;letter-spacing:-.5px}}
      p{{font-size:18px;line-height:1.45;margin:0;color:#d5eef1}}
      .tags{{display:flex;gap:8px;margin-top:22px;flex-wrap:wrap}}
      .tags span{{border:1px solid rgba(255,255,255,.35);border-radius:999px;padding:4px 12px;font-size:14px}}
      .shot{{position:absolute;right:-70px;top:44px;width:560px;border-radius:12px;
        box-shadow:0 24px 60px rgba(0,0,0,.45);border:1px solid rgba(255,255,255,.25)}}
    </style></head><body>
      <div class="txt"><div class="logo">{mark}<span>Lake Lookout</span></div>
        <h1>Be the eyes the satellites lack</h1>
        <p>Hike with your phone. In the evening, Gemma&nbsp;4 turns your photos and voice notes into a
           glacial-lake field log, offline, on your own laptop.</p>
        <div class="tags"><span>Gemma 4 · local</span><span>no signal needed</span><span>MIT</span></div></div>
      <img class="shot" src="data:image/png;base64,{app_png}">
    </body></html>""")
    page.wait_for_timeout(300)
    page.screenshot(path=OUT / "cover.png")
    c.close()

    # 9. the live read-only demo on GitHub Pages
    c = ctx(1440, 900)
    page = c.new_page()
    page.goto("https://hassan-2050.github.io/lake-lookout/demo/#/day/test-hunza")
    page.wait_for_function("(document.querySelector('.day-head h1')||{}).textContent === 'test-hunza' && "
                           "[...document.querySelectorAll('.card img.main')].every((i) => i.complete && i.naturalWidth > 0)",
                           timeout=60000)
    page.wait_for_timeout(400)
    page.screenshot(path=OUT / "10-live-demo.png")
    c.close()
    browser.close()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), make_handler(App(ROOT / "trips")))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as p:
            shots(p)
    finally:
        httpd.shutdown()
    for f in sorted(OUT.glob("*.png")):
        print(f"{f.name:22s} {f.stat().st_size / 1e3:7.0f} kB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
