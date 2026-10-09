"""Record the demo video of the real app with Playwright.

    python tools/record_demo.py            # -> docs/post/lake-lookout-demo.mp4 (+ .gif)

Everything on screen is the real app and the real local model: a day is
created, the test-hunza files are added through the file input, Gemma 4
processes them on this computer, and the result is explored. Captions and a
visible cursor are drawn into the page so the video explains itself. The
processing wait is sped up afterwards with ffmpeg, and a caption says so.

The files are the internet-photo test day (Wikimedia photos, synthetic voice
notes); the opening caption says that too. Needs Ollama running, Chrome, and
`playwright install ffmpeg` once for Playwright's recorder.
"""
from __future__ import annotations

import json
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
from lookout.server import App, make_handler  # noqa: E402

OUT = ROOT / "docs" / "post"
SOURCE = ROOT / "trips" / "test-hunza"
DAY = "hunza-day"
PORT = 8799
W, H = 1280, 720
PROCESSING_SECONDS_IN_VIDEO = 5.0

OVERLAY = """
(() => {
  const css = `#__cap{position:fixed;left:50%;bottom:26px;transform:translateX(-50%);z-index:99999;
    max-width:84%;background:rgba(9,22,27,.88);color:#fff;font:600 21px/1.35 system-ui,"Segoe UI",sans-serif;
    padding:12px 22px;border-radius:12px;box-shadow:0 8px 28px rgba(0,0,0,.28);text-align:center;
    transition:opacity .35s;pointer-events:none}
    #__cap small{display:block;font-weight:400;font-size:15.5px;opacity:.86;margin-top:4px}
    #__cur{position:fixed;left:640px;top:360px;z-index:100000;width:20px;height:20px;margin:-10px 0 0 -10px;
    border-radius:50%;background:rgba(255,166,0,.9);border:2.5px solid #fff;box-shadow:0 1px 8px rgba(0,0,0,.45);
    pointer-events:none;transition:transform .12s}
    #__cur.down{transform:scale(.62)}`;
  const boot = () => {
    if (document.getElementById("__cur")) return;
    const s = document.createElement("style"); s.textContent = css; document.head.appendChild(s);
    const c = document.createElement("div"); c.id = "__cur"; document.body.appendChild(c);
    addEventListener("mousemove", (e) => { c.style.left = e.clientX + "px"; c.style.top = e.clientY + "px"; }, true);
    addEventListener("mousedown", () => c.classList.add("down"), true);
    addEventListener("mouseup", () => c.classList.remove("down"), true);
  };
  document.readyState === "loading" ? addEventListener("DOMContentLoaded", boot) : boot();
  window.__caption = (t, sub) => {
    let el = document.getElementById("__cap");
    if (!el) { el = document.createElement("div"); el.id = "__cap"; document.body.appendChild(el); }
    if (!t) { el.style.opacity = 0; return; }
    el.innerHTML = ""; el.append(t);
    if (sub) { const sm = document.createElement("small"); sm.textContent = sub; el.append(sm); }
    el.style.opacity = 1;
  };
})();
"""

SMOOTH_SCROLL = """([dy, ms]) => new Promise((done) => {
  const y0 = scrollY, t0 = performance.now();
  const f = (t) => { const k = Math.min(1, (t - t0) / ms), e = k < .5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
    scrollTo(0, y0 + dy * e); k < 1 ? requestAnimationFrame(f) : done(); };
  requestAnimationFrame(f); })"""


class Demo:
    def __init__(self, page):
        self.page = page
        self.t0 = time.monotonic()
        self.marks: dict[str, float] = {}

    def mark(self, name: str) -> None:
        self.marks[name] = round(time.monotonic() - self.t0, 2)

    def caption(self, text: str | None, sub: str | None = None, hold: int = 0) -> None:
        self.page.evaluate("([t, s]) => __caption(t, s)", [text, sub])
        if hold:
            self.page.wait_for_timeout(hold)

    def move(self, locator, steps: int = 22) -> None:
        locator.scroll_into_view_if_needed()
        box = locator.bounding_box()
        self.page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=steps)

    def click(self, locator, pause: int = 500) -> None:
        self.move(locator)
        self.page.wait_for_timeout(180)
        self.page.mouse.down()
        self.page.mouse.up()
        self.page.wait_for_timeout(pause)

    def scroll(self, dy: int, ms: int = 1000) -> None:
        self.page.evaluate(SMOOTH_SCROLL, [dy, ms])
        self.page.wait_for_timeout(250)

    def scroll_to(self, locator, offset: int = 90, ms: int = 1000) -> None:
        top = locator.evaluate("(el) => el.getBoundingClientRect().top")
        self.scroll(int(top - offset), ms)


def serve() -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), make_handler(App(ROOT / "trips")))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def record() -> tuple[Path, dict]:
    url = f"http://127.0.0.1:{PORT}/"
    files = sorted(str(p) for p in SOURCE.iterdir() if p.suffix.lower() in (".jpg", ".m4a"))
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        ctx = browser.new_context(viewport={"width": W, "height": H}, device_scale_factor=1,
                                  record_video_dir=str(OUT / "_raw"),
                                  record_video_size={"width": W, "height": H},
                                  color_scheme="light")
        ctx.add_init_script(OVERLAY)
        page = ctx.new_page()
        d = Demo(page)
        page.goto(url)
        page.wait_for_selector(".hero h1")
        page.wait_for_function("document.querySelector('#model-pill').textContent.includes('ready')")

        # -- opening
        d.caption("Lake Lookout",
                  "Hike with your phone. In the evening, a local open model turns your photos and "
                  "voice notes into a glacial-lake field log.", 4200)

        # -- 1. a day
        d.caption("1 · Make a day for today's hike", "No account, no cloud: this app only answers this computer.")
        d.click(page.locator(".hero [data-action='new-day']"), 400)
        page.keyboard.press("Control+A")
        page.keyboard.type(DAY, delay=85)
        page.wait_for_timeout(300)
        page.keyboard.press("Enter")
        page.wait_for_selector("#drop")
        page.wait_for_timeout(600)

        # -- 2. the files
        d.caption("2 · Drop in the day's photos and voice notes",
                  "Demo data: a test day built from freely licensed Wikimedia photos of Hunza, "
                  "with synthetic voice notes.")
        d.move(page.locator("#drop"))
        page.locator("#drop").evaluate("(el) => el.classList.add('over')")
        page.wait_for_timeout(900)
        page.set_input_files("#pick", files)
        page.wait_for_selector(".plan .pc", timeout=60000)
        page.wait_for_timeout(2600)

        # -- 3. process
        d.caption("3 · Process: Gemma 4 runs on this computer",
                  "While it works, the app blocks every network connection except the one to the local model.")
        d.move(page.locator("#model"))
        page.wait_for_timeout(900)
        d.click(page.locator("[data-action='process']"), 300)
        d.mark("processing_start")
        d.caption("Transcribing voice notes and reading photos…", "Sped up in this video. The real time is shown when it finishes.")
        page.wait_for_selector(".card", timeout=600000)
        d.mark("processing_end")
        page.wait_for_timeout(500)

        # -- 4. the log
        d.caption("A field log for the day",
                  "Route, stops and a checklist drawn from published glacial-lake hazard indicators.", 2600)
        d.scroll_to(page.locator(".map"), offset=70, ms=1100)
        for pin in ("3", "1"):
            d.move(page.locator(f".pin[data-stop='S0{pin}'] circle").last, steps=26)
            page.wait_for_timeout(1300)

        # -- 5. evidence
        d.caption("Every yes or no has to name its evidence",
                  "Click an answer to see what the model saw or what you said, and the source behind the question.")
        d.click(page.locator(".pin[data-stop='S04'] circle").last, 900)
        card = page.locator("#stop-S04")
        d.scroll_to(card, offset=70, ms=900)
        rows = card.locator(".checks > .chip-row")
        d.click(rows.nth(0), 1300)
        if rows.count() > 2:
            d.click(rows.nth(2), 1500)
        d.caption("What it cannot see stays “unclear”, never a silent “no”",
                  "Dam and downstream questions count only when that part of the scene is in view.")
        fold = card.locator(".fold-btn")
        if fold.count():
            d.click(fold, 2400)
            d.click(fold, 500)

        # -- 6. disagreements and downgrades
        d.scroll(-page.evaluate("scrollY") + 0, 700)
        d.caption("When the photo and the hiker disagree, it shows both and picks neither")
        d.scroll_to(page.locator(".filters"), offset=80, ms=800)
        d.click(page.locator("[data-filter='conflict']"), 900)
        conflict_row = page.locator(".card .chip-row:has(small)").first
        if conflict_row.count():
            d.scroll_to(conflict_row, offset=260, ms=700)
            d.click(conflict_row, 2600)
        downs = page.locator(".card details.down summary").first
        if downs.count():
            d.caption("Answers the model could not back up are downgraded, with the reason kept")
            d.scroll_to(downs, offset=330, ms=700)
            d.click(downs, 2800)
        d.click(page.locator("[data-filter='all']"), 500)

        # -- 7. photos
        d.caption("Your photos, full size")
        photo = page.locator(".card img.main").first
        d.scroll_to(photo, offset=120, ms=700)
        d.click(photo, 1800)
        page.keyboard.press("Escape")
        page.wait_for_timeout(400)

        # -- 8. share
        d.caption("Share one offline page, plus CSV and GeoJSON for researchers",
                  "No scripts, no map tiles, no fonts from the web. It opens with the network off.")
        d.scroll(-page.evaluate("scrollY"), 700)
        d.move(page.locator("a.btn", has_text="Open trip page"))
        page.wait_for_timeout(700)
        page.goto(f"{url}api/days/{DAY}/out/trip.html")
        page.wait_for_timeout(1500)
        d.caption("Share one offline page, plus CSV and GeoJSON for researchers",
                  "No scripts, no map tiles, no fonts from the web. It opens with the network off.")
        d.scroll(700, 1800)
        page.wait_for_timeout(900)
        page.go_back()
        page.wait_for_selector(".card")

        # -- 9. dark
        page.emulate_media(color_scheme="dark")
        d.caption("Dark mode for the tent", None, 2200)

        # -- end
        d.caption("Lake Lookout · Gemma 4 · runs offline",
                  "Field observations for people qualified to interpret them. No risk scores, no alerts.", 3800)

        video = Path(page.video.path())
        ctx.close()
        browser.close()
    return video, d.marks


def edit(raw: Path, marks: dict) -> tuple[Path, Path]:
    """Speed up the processing wait; write MP4 (H.264) and a short GIF."""
    ff = shutil.which("ffmpeg")
    mp4 = OUT / "lake-lookout-demo.mp4"
    a, b = marks["processing_start"] + 0.8, marks["processing_end"]
    factor = max(1.0, (b - a) / PROCESSING_SECONDS_IN_VIDEO)
    graph = (f"[0:v]trim=0:{a},setpts=PTS-STARTPTS[v0];"
             f"[0:v]trim={a}:{b},setpts=(PTS-STARTPTS)/{factor:.3f}[v1];"
             f"[0:v]trim={b},setpts=PTS-STARTPTS[v2];"
             f"[v0][v1][v2]concat=n=3:v=1:a=0,fps=30,format=yuv420p[out]")
    subprocess.run([ff, "-v", "error", "-y", "-i", str(raw), "-filter_complex", graph,
                    "-map", "[out]", "-c:v", "libx264", "-preset", "slow", "-crf", "21",
                    "-movflags", "+faststart", str(mp4)], check=True)
    # GIF: the part after processing, where the log is explored (about 14 s).
    gif = OUT / "lake-lookout-demo.gif"
    start = a + (b - a) / factor + 0.5
    palette = OUT / "_palette.png"
    vf = "fps=11,scale=880:-1:flags=lanczos"
    subprocess.run([ff, "-v", "error", "-y", "-ss", f"{start:.2f}", "-t", "14", "-i", str(mp4),
                    "-vf", f"{vf},palettegen=stats_mode=diff", str(palette)], check=True)
    subprocess.run([ff, "-v", "error", "-y", "-ss", f"{start:.2f}", "-t", "14", "-i", str(mp4),
                    "-i", str(palette), "-lavfi", f"{vf}[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=4",
                    str(gif)], check=True)
    palette.unlink()
    return mp4, gif


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    httpd = serve()
    try:
        raw, marks = record()
    finally:
        httpd.shutdown()
        shutil.rmtree(ROOT / "trips" / DAY, ignore_errors=True)
    mp4, gif = edit(raw, marks)
    shutil.rmtree(OUT / "_raw", ignore_errors=True)
    (OUT / "demo-timeline.json").write_text(json.dumps(marks, indent=1), encoding="utf-8")
    real = marks["processing_end"] - marks["processing_start"]
    print(f"processing took {real:.1f} s on this computer (sped up in the video)")
    for f in (mp4, gif):
        print(f"wrote {f.relative_to(ROOT)}  {f.stat().st_size / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
