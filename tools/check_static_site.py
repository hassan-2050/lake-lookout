"""Check the exported read-only demo in a real browser, the way it will be hosted.

    python -m lookout export --out docs/demo
    python tools/check_static_site.py          # serves docs/ and opens /demo/

Serves docs/ as GitHub Pages would (the demo under a sub-path) and fails on:
any console error, any request to the local server API or to another host,
any photo that does not decode, any voice note or download that does not load,
upload or process controls being visible, or sideways scrolling on a phone.
"""
from __future__ import annotations

import functools
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
PORT = 8797
BASE = f"http://127.0.0.1:{PORT}/demo/"

fails = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global fails
    fails += not ok
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}{' - ' + detail if detail else ''}")


def main() -> int:
    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self, *args):          # one line per file is noise here
            pass

    class Server(ThreadingHTTPServer):
        def handle_error(self, request, client_address):
            pass                                # browsers cancel media downloads they no longer need

    httpd = Server(("127.0.0.1", PORT), functools.partial(Quiet, directory=str(DOCS)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    problems, offsite, api_calls, failed = [], [], [], []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 860})
            page.on("console", lambda m: problems.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: problems.append(str(e)))
            page.on("request", lambda r: (api_calls.append(r.url) if "/api/" in r.url else None,
                                          offsite.append(r.url) if not r.url.startswith(
                                              (f"http://127.0.0.1:{PORT}/", "data:")) else None))
            # Media requests are excluded: players cancel and re-request ranges as they please.
            media = lambda r: r.resource_type == "media"  # noqa: E731
            page.on("requestfailed", lambda r: None if media(r.request if hasattr(r, "request") else r) else failed.append(r.url))
            page.on("response", lambda r: failed.append(f"{r.status} {r.url}")
                    if r.status >= 400 and not media(r.request) else None)

            page.goto(BASE)
            page.wait_for_selector(".hero h1")
            check("home explains it is a read-only demo", page.locator(".hero .notice").count() == 1)
            check("no 'new day' or upload controls", not page.locator("[data-action='new-day']").first.is_visible()
                  and page.locator("#drop").count() == 0)
            featured = page.evaluate("window.LOOKOUT_STATIC.featured")
            page.click(".hero a.btn.primary")

            days = page.evaluate("fetch('data/days.json').then((r) => r.json()).then((d) => d.map((x) => x.name))")
            for day in [featured] + [d for d in days if d != featured]:
                page.goto(f"{BASE}#/day/{day}")
                page.wait_for_function(f"(document.querySelector('.day-head h1')||{{}}).textContent === '{day}'")
                stops = page.evaluate(f"fetch('data/days/{day}.json').then((r) => r.json()).then((d) => d.result.stops.length)")
                page.wait_for_function("[...document.querySelectorAll('.card img.main')].every((i) => i.complete)")
                n_cards = page.locator(".card").count()
                broken = page.evaluate("[...document.querySelectorAll('.card img.main')].filter((i) => !i.naturalWidth).length")
                check(f"{day}: one card per stop, every photo decodes", n_cards == stops and broken == 0,
                      f"{n_cards}/{stops} cards, {broken} broken")
                check(f"{day}: process controls hidden", not page.locator("[data-action='process']").is_visible())
                # Voice notes are checked the way a visitor hears them: in an audio
                # player. (On the machine this was built on, a script's fetch() of a
                # URL ending in .m4a returns an empty 204 while the player plays it.)
                played = page.evaluate("""() => Promise.all([...document.querySelectorAll('.card audio')].map((el) =>
                    new Promise((ok) => { const a = new Audio(el.src); a.muted = true;
                      a.onloadedmetadata = () => ok(a.duration > 0); a.onerror = () => ok(false);
                      setTimeout(() => ok(false), 8000); })))""")
                check(f"{day}: every voice note plays", all(played), f"{sum(played)}/{len(played)}")
                urls = page.evaluate("""[...document.querySelectorAll('.actions a')].map((a) => a.href)
                    .concat([...document.querySelectorAll('.notice a')].map((a) => a.href))""")
                status = page.evaluate("(urls) => Promise.all(urls.map((u) => fetch(u).then((r) => r.status)))", urls)
                bad = [u for u, s in zip(urls, status) if s != 200]
                check(f"{day}: downloads and credits load", not bad, f"{len(urls)} links" + (f"; bad: {bad[:2]}" if bad else ""))

            page.goto(f"{BASE}#/day/{featured}")
            page.wait_for_selector(".card img.main")
            page.locator(".card img.main").first.click()
            page.wait_for_function("!document.querySelector('#lightbox').hidden && document.querySelector('#lightbox img').naturalWidth > 0")
            check("photo opens full size", True)
            page.keyboard.press("Escape")
            page.locator("[data-filter='conflict']").click()
            check("filters work", page.locator("[data-filter='conflict']").get_attribute("aria-pressed") == "true")
            page.screenshot(path=str(ROOT / "docs" / "screenshots" / "static-demo.png"))

            page.set_viewport_size({"width": 390, "height": 844})
            page.wait_for_timeout(400)
            width = page.evaluate("document.documentElement.scrollWidth")
            check("no sideways scroll on a phone", width <= 392, f"{width} px")
            browser.close()
    finally:
        httpd.shutdown()

    check("never calls the local server API", not api_calls, ", ".join(api_calls[:2]))
    check("never contacts another host", not offsite, ", ".join(offsite[:2]))
    check("no failed requests", not failed, ", ".join(failed[:3]))
    check("no console errors", not problems, " | ".join(problems[:3]))
    print(f"\n{'FAIL' if fails else 'PASS'} ({fails} failed)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
