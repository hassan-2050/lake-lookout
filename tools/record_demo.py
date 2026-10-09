"""Record the narrated demo video of the real app with Playwright.

    python tools/record_demo.py            # -> docs/post/lake-lookout-demo.mp4 (+ .gif, .srt, .vtt)

Everything on screen is the real app and the real local model: a day is
created, the test-hunza files are added through the file input, Gemma 4
processes them on this computer, and the result is explored. Captions and a
visible cursor are drawn into the page so the video explains itself.

The narration is generated first, by an open-weight text-to-speech model run
locally (tools/narrate.py), and drives the recording: every scene stays on
screen at least as long as its line takes to say. Afterwards ffmpeg speeds up
the processing wait (a caption says so) and lays each line at the moment its
scene began, adjusted for that speed-up.

The files are the internet-photo test day (Wikimedia photos, synthetic voice
notes); the narration and a caption say so. Needs Ollama running, Chrome, and
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
sys.path.insert(0, str(ROOT / "tools"))
from lookout.server import App, make_handler  # noqa: E402
import narrate  # noqa: E402

OUT = ROOT / "docs" / "post"
SOURCE = ROOT / "trips" / "test-hunza"
REVIEW = ROOT / "eval" / "label-review.html"      # tools/make_label_review.py
CHART_PAGE = OUT / "_chart.html"                   # written for the recording, then removed
DAY = "hunza-day"
PORT = 8799
W, H = 1280, 720
GAP = 0.45            # silence after each line before the next scene starts

# key: (caption, caption subtitle, spoken line). Spoken lines may spell a name
# the way it sounds ("oh llama"): the voice said "Alama" for "Ollama", and
# the round-trip check through Gemma 4 picked the spelling that comes back right.
SCRIPT = {
    "intro": ("Lake Lookout",
              "Hike with your phone. In the evening, a local open model turns your photos and voice "
              "notes into a glacial-lake field log.",
              "In August 2024, a glacial lake above the village of Thame, in Nepal, burst. "
              "Satellites rarely see these lakes through monsoon cloud, but hikers walk past them "
              "every day. Lake Lookout turns a hike into a field log, on your own laptop, with no internet."),
    "new_day": ("1 · Make a day for today's hike",
                "No account, no cloud: this app only answers this computer.",
                "In the evening, make a day for today's hike,"),
    "files": ("2 · Drop in the day's photos and voice notes",
              "Demo data: a test day built from freely licensed Wikimedia photos of Hunza, "
              "with synthetic voice notes.",
              "and drop in the photos and voice notes from your phone. This demo uses a test day "
              "built from Wikimedia photos of Hunza, with synthetic voice notes."),
    "process": ("3 · Process: Gemma 4 runs on this computer",
                "While it works, the app blocks every network connection except the one to the local model.",
                "Now press the Process button. Gemma 4 runs right here, through oh llama, and the app blocks every "
                "network connection except the one to the local model."),
    "processing": ("Transcribing voice notes and reading photos…",
                   "Sped up in this video. The real time is shown when it finishes.",
                   "It transcribes each voice note, and reads every photo."),
    "log": ("A field log for the day",
            "Route, stops and a checklist drawn from published glacial-lake hazard indicators.",
            "The result is a field log: your route, every stop, and a checklist drawn from "
            "published glacial-lake hazard indicators."),
    "evidence": ("Every yes or no has to name its evidence",
                 "Click an answer to see what the model saw or what you said, and the source behind the question.",
                 "Every yes or no has to name its evidence: what the model saw in the photo, "
                 "or what you said."),
    "unclear": ("What it cannot see stays “unclear”, never a silent “no”",
                "Dam and downstream questions count only when that part of the scene is in view.",
                "Anything it can't actually see is marked as unclear. Never a silent no."),
    "conflict": ("When the photo and the hiker disagree, it shows both and picks neither", None,
                 "When the photo and your voice note disagree, it shows both, and picks neither."),
    "downgrades": ("Answers the model could not back up are downgraded, with the reason kept", None,
                   "Answers the model couldn't back up are downgraded, and the reason is kept."),
    "measured": ("Measured against labelled photos",
                 "11 photos × 13 questions, including lakes that aren't glacial. "
                 "Labels drafted and re-checked by a coding agent.",
                 "How well does it work? Every answer is scored against labelled photos: glacial "
                 "lakes, a glacier with no lake, and three lakes that aren't glacial at all."),
    "chart": ("Five measured versions",
              "False “no” answers: 18 in v2, 3 by v4. Accuracy 74% to 89%.",
              "Across five measured versions, asking for evidence first stopped unsupported "
              "answers. Then the in-view questions cut false no answers from eighteen to three."),
    "photos": ("Your photos, full size", None, "Photos open full size."),
    "share": ("Share one offline page, plus CSV and GeoJSON for researchers",
              "No scripts, no map tiles, no fonts from the web. It opens with the network off.",
              "Then share one page that works offline, plus CSV and GeoJSON for researchers."),
    "dark": ("Dark mode for the tent", None, "And there's a dark mode for the tent."),
    "end": ("Lake Lookout · Gemma 4 · runs offline",
            "Field observations, not alerts. Narration: Kokoro-82M, an open-weight voice model, run locally.",
            "Lake Lookout. Open weights, no signal needed. Field observations, not alerts. "
            "Even this voice is an open model, running on this laptop."),
}

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


def make_voice(tmp: Path) -> dict[str, tuple[Path, float]]:
    """Speak every line once, up front; the lengths drive the recording."""
    clips = {}
    for key, (_, _, line) in SCRIPT.items():
        path = tmp / f"{key}.wav"
        clips[key] = (path, narrate.say(line, path))
    return clips


class Demo:
    def __init__(self, page, clips):
        self.page = page
        self.clips = clips
        self.t0 = time.monotonic()
        self.marks: dict[str, float] = {}
        self.current: str | None = None

    def now(self) -> float:
        return time.monotonic() - self.t0

    def mark(self, name: str) -> None:
        self.marks[name] = round(self.now(), 2)

    def finish(self) -> None:
        """Stay on the current scene until its line has been spoken."""
        if self.current:
            end = self.marks[self.current] + self.clips[self.current][1] + GAP
            left = end - self.now()
            if left > 0:
                self.page.wait_for_timeout(int(left * 1000))

    def scene(self, key: str) -> None:
        self.finish()
        caption, sub, _ = SCRIPT[key]
        self.page.evaluate("([t, s]) => __caption(t, s)", [caption, sub])
        self.current = key
        self.mark(key)

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


def record(clips) -> tuple[Path, dict]:
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
        d = Demo(page, clips)           # the video clock starts with the page
        page.goto(url)
        page.wait_for_selector(".hero h1")
        page.wait_for_function("document.querySelector('#model-pill').textContent.includes('ready')")

        d.scene("intro")
        page.wait_for_timeout(1200)

        d.scene("new_day")
        d.click(page.locator(".hero [data-action='new-day']"), 300)
        page.keyboard.press("Control+A")
        page.keyboard.type(DAY, delay=70)
        page.keyboard.press("Enter")
        page.wait_for_selector("#drop")

        d.scene("files")
        d.move(page.locator("#drop"))
        page.locator("#drop").evaluate("(el) => el.classList.add('over')")
        page.wait_for_timeout(700)
        page.set_input_files("#pick", files)
        page.wait_for_selector(".plan .pc", timeout=60000)

        d.scene("process")
        d.move(page.locator("#model"))
        page.wait_for_timeout(700)
        d.move(page.locator("[data-action='process']"))
        d.finish()                      # say the line, then press the button
        d.click(page.locator("[data-action='process']"), 200)
        d.scene("processing")
        d.mark("processing_start")
        page.wait_for_selector(".card", timeout=600000)
        d.mark("processing_end")

        d.scene("log")
        page.wait_for_timeout(600)
        d.scroll_to(page.locator(".map"), offset=70, ms=1100)
        for pin in ("3", "1"):
            d.move(page.locator(f".pin[data-stop='S0{pin}'] circle").last, steps=26)
            page.wait_for_timeout(1200)

        d.scene("evidence")
        d.click(page.locator(".pin[data-stop='S04'] circle").last, 800)
        card = page.locator("#stop-S04")
        d.scroll_to(card, offset=70, ms=900)
        rows = card.locator(".checks > .chip-row")
        d.click(rows.nth(0), 1100)
        if rows.count() > 2:
            d.click(rows.nth(2), 900)

        d.scene("unclear")
        fold = card.locator(".fold-btn")
        if fold.count():
            d.click(fold, 2200)
            d.click(fold, 300)

        d.scene("conflict")
        d.scroll_to(page.locator(".filters"), offset=80, ms=800)
        d.click(page.locator("[data-filter='conflict']"), 700)
        conflict_row = page.locator(".card .chip-row:has(small)").first
        if conflict_row.count():
            d.scroll_to(conflict_row, offset=260, ms=700)
            d.click(conflict_row, 1200)

        d.scene("downgrades")
        downs = page.locator(".card details.down summary").first
        if downs.count():
            d.scroll_to(downs, offset=330, ms=700)
            d.click(downs, 1400)
        d.finish()
        d.click(page.locator("[data-filter='all']"), 300)

        # How it was measured: the labelled photos, then the five versions.
        page.goto(REVIEW.as_uri())
        page.add_style_tag(content="#status,#copy,#fallback{display:none!important}")
        page.wait_for_function("[...document.images].every((i) => i.complete)")
        d.scene("measured")
        page.wait_for_timeout(1200)
        d.scroll_to(page.locator("#card-attabad"), offset=70, ms=1200)
        d.move(page.locator("#row-attabad-glacial_setting"))
        page.wait_for_timeout(1500)
        d.scroll_to(page.locator("#card-jokulsarlon"), offset=70, ms=1200)
        d.move(page.locator("#row-jokulsarlon-calving_icebergs"))
        d.finish()
        page.goto(CHART_PAGE.as_uri())
        page.wait_for_function("document.images[0] && document.images[0].complete")
        d.scene("chart")
        d.finish()
        page.goto(f"{url}#/day/{DAY}")
        page.wait_for_function("[...document.querySelectorAll('.card img.main')].every((i) => i.complete)")

        d.scene("photos")
        photo = page.locator(".card img.main").first
        d.scroll_to(photo, offset=120, ms=600)
        d.click(photo, 1400)
        d.finish()
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)

        d.scene("share")
        d.scroll(-page.evaluate("scrollY"), 600)
        d.move(page.locator("a.btn", has_text="Open trip page"))
        page.wait_for_timeout(500)
        page.goto(f"{url}api/days/{DAY}/out/trip.html")
        page.wait_for_load_state("load")
        caption, sub, _ = SCRIPT["share"]
        page.evaluate("([t, s]) => __caption(t, s)", [caption, sub])   # new page, same scene
        d.scroll(650, 1700)
        d.finish()
        page.go_back()
        page.wait_for_selector(".card")

        page.emulate_media(color_scheme="dark")
        d.scene("dark")

        d.scene("end")
        d.finish()
        page.wait_for_timeout(2500)     # let the last word breathe before the cut

        video = Path(page.video.path())
        ctx.close()
        browser.close()
    return video, d.marks


def edit(raw: Path, marks: dict, clips: dict) -> tuple[Path, Path]:
    """Speed up the processing wait, lay the narration on its scenes, write MP4 and GIF."""
    ff = shutil.which("ffmpeg")
    silent = OUT / "_silent.mp4"
    mp4 = OUT / "lake-lookout-demo.mp4"

    # The sped-up stretch lasts long enough for the line spoken over it.
    a = marks["processing_start"] + 0.6
    b = marks["processing_end"]
    target = max(5.0, clips["processing"][1] + 1.2)
    factor = max(1.0, (b - a) / target)
    graph = (f"[0:v]trim=0:{a},setpts=PTS-STARTPTS[v0];"
             f"[0:v]trim={a}:{b},setpts=(PTS-STARTPTS)/{factor:.3f}[v1];"
             f"[0:v]trim={b},setpts=PTS-STARTPTS[v2];"
             f"[v0][v1][v2]concat=n=3:v=1:a=0,tpad=stop_mode=clone:stop_duration=1.5,"
             "fps=30,format=yuv420p[out]")
    subprocess.run([ff, "-v", "error", "-y", "-i", str(raw), "-filter_complex", graph,
                    "-map", "[out]", "-c:v", "libx264", "-preset", "slow", "-crf", "21",
                    str(silent)], check=True)

    def edited(t: float) -> float:
        if t <= a:
            return t
        if t <= b:
            return a + (t - a) / factor
        return t - (b - a) + (b - a) / factor

    inputs, chains = [], []
    for i, key in enumerate(SCRIPT):
        inputs += ["-i", str(clips[key][0])]
        ms = int(edited(marks[key]) * 1000)
        chains.append(f"[{i + 1}:a]aresample=48000,adelay={ms}|{ms}[a{i}]")
    mix = "".join(f"[a{i}]" for i in range(len(SCRIPT)))
    audio_graph = (";".join(chains) + f";{mix}amix=inputs={len(SCRIPT)}:normalize=0:duration=longest,"
                   "loudnorm=I=-16:TP=-1.5:LRA=11[aud]")
    # End two seconds after the last word: the recorder keeps running a little
    # after the final scene, which would otherwise leave a silent tail.
    end = edited(marks["end"]) + clips["end"][1] + 2.0
    subprocess.run([ff, "-v", "error", "-y", "-i", str(silent), *inputs, "-t", f"{end:.2f}",
                    "-filter_complex", audio_graph, "-map", "0:v", "-map", "[aud]",
                    "-c:v", "libx264", "-preset", "slow", "-crf", "21",
                    "-c:a", "aac", "-b:a", "160k", "-ac", "2",
                    "-movflags", "+faststart", str(mp4)], check=True)
    silent.unlink()

    # GIF (no sound): the log being explored, after processing.
    gif = OUT / "lake-lookout-demo.gif"
    start = edited(marks["log"]) + 0.5
    palette = OUT / "_palette.png"
    vf = "fps=11,scale=880:-1:flags=lanczos"
    subprocess.run([ff, "-v", "error", "-y", "-ss", f"{start:.2f}", "-t", "14", "-i", str(mp4),
                    "-vf", f"{vf},palettegen=stats_mode=diff", str(palette)], check=True)
    subprocess.run([ff, "-v", "error", "-y", "-ss", f"{start:.2f}", "-t", "14", "-i", str(mp4),
                    "-i", str(palette), "-lavfi", f"{vf}[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=4",
                    str(gif)], check=True)
    palette.unlink()
    marks["edited"] = {k: round(edited(marks[k]), 2) for k in SCRIPT}
    marks["speedup"] = round(factor, 2)
    return mp4, gif


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = OUT / "_voice"
    tmp.mkdir(exist_ok=True)
    clips = make_voice(tmp)
    print("narration: " + ", ".join(f"{k} {v[1]:.1f}s" for k, v in clips.items()))
    subprocess.run([sys.executable, str(ROOT / "tools" / "make_label_review.py")], check=True)
    CHART_PAGE.write_text(
        "<!doctype html><meta charset='utf-8'><body style='margin:0;background:#fcfcfb;"
        "display:grid;place-items:center;height:100vh'>"
        "<img src='09-iterations.png' style='width:94vw' alt='Five measured versions'>", encoding="utf-8")
    httpd = serve()
    try:
        raw, marks = record(clips)
    finally:
        httpd.shutdown()
        shutil.rmtree(ROOT / "trips" / DAY, ignore_errors=True)
        CHART_PAGE.unlink(missing_ok=True)
    mp4, gif = edit(raw, marks, clips)
    shutil.rmtree(OUT / "_raw", ignore_errors=True)
    shutil.rmtree(tmp, ignore_errors=True)
    marks["durations"] = {k: round(c[1], 3) for k, c in clips.items()}
    (OUT / "demo-timeline.json").write_text(json.dumps(marks, indent=1), encoding="utf-8")
    import make_subtitles                 # captions from the same timeline
    make_subtitles.main()
    real = marks["processing_end"] - marks["processing_start"]
    print(f"processing took {real:.1f} s on this computer (sped up {marks['speedup']}x in the video)")
    for f in (mp4, gif):
        print(f"wrote {f.relative_to(ROOT)}  {f.stat().st_size / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
