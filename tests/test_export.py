"""The read-only static demo: what gets written, and what must not leak."""
import json

import pytest

from conftest import make_memo, make_photo, needs_ffmpeg
from lookout import gemma
from lookout.export import THUMB_SIZES, export
from lookout.pipeline import run_day
from test_server import fake_chat


@pytest.fixture
def processed(tmp_path, monkeypatch):
    monkeypatch.setattr(gemma, "chat", fake_chat)
    trips = tmp_path / "trips"
    day = trips / "day-one"
    day.mkdir(parents=True)
    make_photo(day / "lake.jpg", when="2026:10:10 09:15:00", offset="+05:00")
    make_memo(day / "note.m4a", "2026-10-10T04:16:00Z")
    (day / "README.md").write_text("# Test day\n", encoding="utf-8")
    run_day(day, model="gemma4:e4b")
    return trips


@needs_ffmpeg
def test_export_writes_the_site(processed, tmp_path):
    out = tmp_path / "site"
    info = export(processed, out, featured="day-one", repo="https://example.org/code")
    assert info["days"] == ["day-one"]
    page = (out / "index.html").read_text(encoding="utf-8")
    assert page.index("static-config.js") < page.index('src="app.js"')
    config = (out / "static-config.js").read_text(encoding="utf-8")
    assert '"featured": "day-one"' in config and "example.org/code" in config
    day = json.loads((out / "data/days/day-one.json").read_text(encoding="utf-8"))
    assert day["job"] is None and len(day["result"]["stops"]) == 1
    for size in THUMB_SIZES:
        assert (out / f"data/thumbs/day-one/lake.jpg.{size}.jpg").read_bytes()[:2] == b"\xff\xd8"
    voice = out / "data/audio/day-one/note.m4a.mp4"
    assert voice.exists() and voice.read_bytes()[4:8] == b"ftyp"     # an MP4 container
    assert (out / "data/files/day-one/README.md").exists()
    for f in ("trip.html", "field_log.csv", "field_log.geojson"):
        assert (out / "data/out/day-one" / f).exists()
    health = json.loads((out / "data/health.json").read_text(encoding="utf-8"))
    assert health["ollama"] is False and health["checklist"]


@needs_ffmpeg
def test_export_leaks_no_local_paths(processed, tmp_path):
    """A public demo must not carry the folder names of the machine it came from."""
    out = tmp_path / "site"
    export(processed, out)
    local = str(tmp_path)
    for f in out.rglob("*"):
        if f.suffix in (".json", ".js", ".html", ".csv", ".geojson"):
            text = f.read_text(encoding="utf-8")
            assert local not in text and local.replace("\\", "/") not in text, f


def test_export_refuses_when_nothing_is_processed(tmp_path):
    (tmp_path / "trips" / "empty-day").mkdir(parents=True)
    with pytest.raises(SystemExit):
        export(tmp_path / "trips", tmp_path / "site")
