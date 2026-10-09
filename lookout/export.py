"""Export processed days as a read-only static site: a live demo with no server.

    python -m lookout export --out docs/demo --featured test-hunza --repo <url>

The real app UI, unchanged, plus the data it would have asked the local server
for, written as plain files: day JSON, thumbnails at the sizes the page uses,
voice notes, and each day's trip page, CSV and GeoJSON. Upload and Process
are hidden; a banner says the days were processed offline on a laptop and that
nothing is processed on the website. That is deliberate: processing a hike
belongs on the hiker's own machine, so photos and locations never leave it.

The JSON comes from the same App methods the server uses, so the static demo
cannot drift from what the app shows locally.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from .server import OUT as OUT_DIR, UI_DIR, App

THUMB_SIZES = (360, 640, 1600)       # must match URLS.thumb in ui/app.js
OUTPUT_FILES = ("trip.html", "field_log.csv", "field_log.geojson")
TEST_NOTE = ("Test data, not a real hike: the photo credits say where the photos come "
             "from and what is synthetic.")


def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, default=str), encoding="utf-8")


def export(trips: Path, out: Path, *, days: list[str] | None = None,
           featured: str | None = None, repo: str | None = None) -> dict:
    app = App(trips)
    processed = [d for d in app.days() if d["processed"]]
    if days:
        processed = [d for d in processed if d["name"] in days]
    if not processed:
        raise SystemExit("no processed days to export; run `python -m lookout process` first")

    if out.exists():
        shutil.rmtree(out)
    data = out / "data"
    notes, credits, model = {}, {}, None
    for d in processed:
        name = d["name"]
        view = app.day(name)
        view["job"] = None
        _write_json(data / "days" / f"{name}.json", view)
        model = model or view["result"]["meta"]["model"]

        photos = {p for s in view["result"]["stops"] for p in s["photos"]}
        for photo in sorted(photos):
            for size in THUMB_SIZES:
                dest = data / "thumbs" / name / f"{photo}.{size}.jpg"
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(app.thumbnail(name, photo, size))

        files = data / "files" / name
        files.mkdir(parents=True, exist_ok=True)
        for memo in {m["name"] for s in view["result"]["stops"] for m in s["memos"]}:
            shutil.copy2(trips / name / memo, files / memo)
        readme = trips / name / "README.md"
        if readme.exists():
            shutil.copy2(readme, files / "README.md")
            credits[name] = "README.md"
            notes[name] = TEST_NOTE

        outputs = data / "out" / name
        outputs.mkdir(parents=True, exist_ok=True)
        for f in OUTPUT_FILES:
            shutil.copy2(trips / name / OUT_DIR / f, outputs / f)

    _write_json(data / "days.json", [{**d, "job": None} for d in processed])
    health = app.health()
    health.update({"ollama": False, "models": []})
    _write_json(data / "health.json", health)

    for f in ("app.css", "app.js", "favicon.svg"):
        shutil.copy2(UI_DIR / f, out / f)
    page = (UI_DIR / "index.html").read_text(encoding="utf-8")
    marker = '<script src="app.js"></script>'
    assert marker in page
    page = page.replace(marker, '<script src="static-config.js"></script>\n' + marker)
    page = page.replace("<title>Lake Lookout</title>", "<title>Lake Lookout (demo)</title>")
    (out / "index.html").write_text(page, encoding="utf-8")
    config = {"featured": featured or processed[0]["name"], "repo": repo, "model": model,
              "notes": notes, "credits": credits}
    (out / "static-config.js").write_text(
        "window.LOOKOUT_STATIC = " + json.dumps(config, ensure_ascii=False, indent=1) + ";\n",
        encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")      # GitHub Pages: serve as is

    files = [p for p in out.rglob("*") if p.is_file()]
    return {"days": [d["name"] for d in processed], "files": len(files),
            "bytes": sum(p.stat().st_size for p in files)}
