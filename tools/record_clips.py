"""Short feature clips of the real app, for the write-up (MP4 + GIF each).

    python tools/record_clips.py            # -> docs/post/clips/*.mp4 and *.gif

Five silent clips, 10-20 s each, recorded with Playwright from the real app,
real model and real live site, with a caption and a visible cursor:

  1-process     drop a day's files in, press Process (the model wait is sped up)
  2-evidence    open a stop from the map; every answer shows its evidence
  3-disagree    a stop where the photo and the hiker disagree
  4-live-demo   the read-only demo on GitHub Pages
  5-phone       the app at phone width

Uses the processed test days in trips/ and needs Ollama running for clip 1.
The narrated full demo is tools/record_demo.py.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from lookout.server import App, make_handler  # noqa: E402
from record_demo import OVERLAY, SMOOTH_SCROLL  # noqa: E402

OUT = ROOT / "docs" / "post" / "clips"
PORT = 8794
LOCAL = f"http://127.0.0.1:{PORT}/"
LIVE = "https://hassan-2050.github.io/lake-lookout/"
CLIP_DAY = "hunza-clip"
DESKTOP = (1280, 720)
PHONE = (390, 844)


class Clip:
    def __init__(self, page):
        self.page = page
        self.t0 = time.monotonic()
        self.marks: dict[str, float] = {}

    def mark(self, name: str) -> None:
        self.marks[name] = time.monotonic() - self.t0

    def caption(self, text: str | None, sub: str | None = None, hold: int = 0) -> None:
        self.page.evaluate("([t, s]) => window.__caption && __caption(t, s)", [text, sub])
        if hold:
            self.page.wait_for_timeout(hold)

    def move(self, locator, steps: int = 20) -> None:
        locator.scroll_into_view_if_needed()
        box = locator.bounding_box()
        self.page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=steps)

    def click(self, locator, pause: int = 600) -> None:
        self.move(locator)
        self.page.wait_for_timeout(150)
        self.page.mouse.down()
        self.page.mouse.up()
        self.page.wait_for_timeout(pause)

    def scroll(self, dy: int, ms: int = 900) -> None:
        self.page.evaluate(SMOOTH_SCROLL, [dy, ms])
        self.page.wait_for_timeout(200)

    def scroll_to(self, locator, offset: int = 80, ms: int = 900) -> None:
        top = locator.evaluate("(el) => el.getBoundingClientRect().top")
        self.scroll(int(top - offset), ms)

    def open_day(self, day: str) -> None:
        self.page.goto(f"{LOCAL}#/day/{day}")
        self.page.wait_for_function(
            f"(document.querySelector('.day-head h1')||{{}}).textContent === '{day}' && "
            "[...document.querySelectorAll('.card img.main')].every((i) => i.complete)")


# --- the five clips ------------------------------------------------------------

def clip_process(c: Clip) -> None:
    files = sorted(str(p) for p in (ROOT / "trips" / "test-hunza").iterdir()
                   if p.suffix.lower() in (".jpg", ".m4a"))
    page = c.page
    page.goto(LOCAL)
    page.wait_for_function("document.querySelector('#model-pill').textContent.includes('ready')")
    c.mark("start")
    c.caption("Make a day, drop in the photos and voice notes", "Test day: Wikimedia photos of Hunza, synthetic voice notes")
    c.click(page.locator(".hero [data-action='new-day']"), 300)
    page.keyboard.press("Control+A")
    page.keyboard.type(CLIP_DAY, delay=60)
    page.keyboard.press("Enter")
    page.wait_for_selector("#drop")
    c.move(page.locator("#drop"))
    page.set_input_files("#pick", files)
    page.wait_for_selector(".plan .pc", timeout=60000)
    page.wait_for_timeout(1500)
    c.caption("Press Process: Gemma 4 runs on this laptop, offline", "Sped up in this clip")
    c.click(page.locator("[data-action='process']"), 300)
    c.mark("fast_from")
    page.wait_for_selector(".card", timeout=600000)
    c.mark("fast_to")
    c.caption("A field log for the day", "Route, stops, and a checklist where every answer names its evidence")
    page.wait_for_timeout(1500)
    c.scroll_to(page.locator(".map"), offset=60, ms=1200)
    page.wait_for_timeout(1800)


def clip_evidence(c: Clip) -> None:
    page = c.page
    c.open_day("test-hunza")
    c.mark("start")
    c.caption("Every yes or no names its evidence")
    c.scroll_to(page.locator(".map"), offset=60, ms=900)
    c.move(page.locator(".pin[data-stop='S04'] circle").last, steps=24)
    page.wait_for_timeout(1300)
    c.click(page.locator(".pin[data-stop='S04'] circle").last, 900)
    card = page.locator("#stop-S04")
    rows = card.locator(".checks > .chip-row")
    c.click(rows.nth(0), 1200)
    c.click(rows.nth(1), 1200)
    c.caption("What it can't see stays “unclear”, never a silent “no”")
    fold = card.locator(".fold-btn")
    if fold.count():
        c.click(fold, 2200)
    page.wait_for_timeout(800)


def clip_disagree(c: Clip) -> None:
    page = c.page
    c.open_day("test-skardu")
    c.mark("start")
    c.caption("When the photo and the hiker disagree, it shows both and picks neither")
    c.scroll_to(page.locator(".filters"), offset=80, ms=800)
    c.click(page.locator("[data-filter='conflict']"), 900)
    card = page.locator("#stop-S02")
    c.scroll_to(card, offset=70, ms=800)
    for label in ("Dam or outlet in view", "Moraine dam"):
        row = card.locator(".chip-row", has_text=label).first
        if row.count():
            c.click(row, 1700)
    c.caption("The hiker's words count as evidence: “a concrete dam” answers “moraine dam: no”")
    page.wait_for_timeout(2600)


def clip_live(c: Clip) -> None:
    page = c.page
    page.goto(LIVE)
    page.wait_for_selector(".hero h1", timeout=30000)
    c.mark("start")
    c.caption("Live read-only demo, no server", "hassan-2050.github.io/lake-lookout")
    page.wait_for_timeout(1500)
    c.click(page.locator(".hero a.btn.primary"), 800)
    page.wait_for_function("[...document.querySelectorAll('.card img.main')].every((i) => i.complete)")
    c.scroll_to(page.locator(".map"), offset=60, ms=1000)
    page.wait_for_timeout(1000)
    photo = page.locator(".card img.main").nth(1)
    c.scroll_to(photo, offset=120, ms=900)
    c.click(photo, 1800)
    page.keyboard.press("Escape")
    page.wait_for_timeout(600)


def clip_phone(c: Clip) -> None:
    page = c.page
    c.open_day("test-hunza")
    page.add_style_tag(content="#__cap{font-size:15px!important;bottom:14px!important;max-width:92%!important}"
                               "#__cap small{font-size:12.5px!important}")
    c.mark("start")
    c.caption("Works at phone width")
    page.wait_for_timeout(1200)
    c.scroll_to(page.locator(".stats"), offset=10, ms=1000)
    page.wait_for_timeout(800)
    c.scroll_to(page.locator(".map"), offset=10, ms=1000)
    page.wait_for_timeout(1000)
    c.scroll_to(page.locator(".card").first, offset=10, ms=1200)
    page.wait_for_timeout(800)
    c.scroll(520, 1400)
    fold = page.locator(".card").first.locator(".fold-btn")
    if fold.count():
        c.click(fold, 1800)
    page.wait_for_timeout(600)


CLIPS = [
    ("1-process", clip_process, DESKTOP, False),
    ("2-evidence", clip_evidence, DESKTOP, False),
    ("3-disagree", clip_disagree, DESKTOP, False),
    ("4-live-demo", clip_live, DESKTOP, False),
    ("5-phone", clip_phone, PHONE, True),
]


# --- encoding ------------------------------------------------------------------

def encode(raw: Path, name: str, marks: dict, size) -> list[Path]:
    ff = shutil.which("ffmpeg")
    start = max(0.0, marks.get("start", 0.0) - 0.2)
    mp4, gif = OUT / f"{name}.mp4", OUT / f"{name}.gif"
    if "fast_from" in marks:
        a, b = marks["fast_from"] + 0.5, marks["fast_to"]
        factor = max(1.0, (b - a) / 3.0)          # the wait becomes about 3 s
        graph = (f"[0:v]trim={start}:{a},setpts=PTS-STARTPTS[v0];"
                 f"[0:v]trim={a}:{b},setpts=(PTS-STARTPTS)/{factor:.3f}[v1];"
                 f"[0:v]trim={b},setpts=PTS-STARTPTS[v2];"
                 "[v0][v1][v2]concat=n=3:v=1:a=0,fps=30,format=yuv420p[out]")
    else:
        graph = f"[0:v]trim={start},setpts=PTS-STARTPTS,fps=30,format=yuv420p[out]"
    subprocess.run([ff, "-v", "error", "-y", "-i", str(raw), "-filter_complex", graph, "-map", "[out]",
                    "-c:v", "libx264", "-preset", "slow", "-crf", "21", "-movflags", "+faststart",
                    str(mp4)], check=True)
    width = 360 if size == PHONE else 800
    vf = f"fps=10,scale={width}:-1:flags=lanczos"
    palette = OUT / "_palette.png"
    subprocess.run([ff, "-v", "error", "-y", "-i", str(mp4), "-vf", f"{vf},palettegen=stats_mode=diff",
                    str(palette)], check=True)
    subprocess.run([ff, "-v", "error", "-y", "-i", str(mp4), "-i", str(palette), "-lavfi",
                    f"{vf}[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=4", str(gif)], check=True)
    palette.unlink()
    return [mp4, gif]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    only = set(sys.argv[1:])
    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), make_handler(App(ROOT / "trips")))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    raw_dir = OUT / "_raw"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            for name, fn, size, mobile in CLIPS:
                if only and name not in only:
                    continue
                ctx = browser.new_context(
                    viewport={"width": size[0], "height": size[1]}, device_scale_factor=1,
                    is_mobile=mobile, has_touch=mobile, color_scheme="light",
                    record_video_dir=str(raw_dir / name),
                    record_video_size={"width": size[0], "height": size[1]})
                ctx.add_init_script(OVERLAY)
                page = ctx.new_page()
                clip = Clip(page)
                fn(clip)
                raw = Path(page.video.path())
                ctx.close()
                for f in encode(raw, name, clip.marks, size):
                    print(f"wrote {f.relative_to(ROOT)}  {f.stat().st_size / 1e6:.1f} MB")
            browser.close()
    finally:
        httpd.shutdown()
        shutil.rmtree(ROOT / "trips" / CLIP_DAY, ignore_errors=True)
        shutil.rmtree(raw_dir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
