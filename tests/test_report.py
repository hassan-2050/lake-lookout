import csv
import json
import re

from conftest import make_photo
from lookout import report
from lookout.checklist import ITEM_IDS
from lookout.pipeline import pick as _pick


def _stop(sid, photo, lat=27.9, lon=86.92, error=None, transcript=""):
    cl = {i: {"answer": "unclear", "evidence": "", "source": "none"} for i in ITEM_IDS}
    cl["water_body"] = {"answer": "yes", "evidence": "lake <b>here</b>", "source": "photo"}
    cl["summary"] = "A lake."
    return {"id": sid, "time_local": "2026-10-10 09:15", "lat": lat, "lon": lon,
            "alt_m": 5000.0 if lat is not None else None,
            "photos": [photo.name] if photo else [],
            "photo_paths": [str(photo)] if photo else [],
            "memos": [], "transcript": transcript, "error": error,
            "checklist": None if error else cl,
            "downgrades": [] if error else [{"item": "moraine_dam", "model_answer": "yes",
                                             "reason": "'yes' given with no evidence"}]}


META = {"day": "test-day", "model": "gemma4:e4b", "processed": "2026-10-10 20:00",
        "seconds": 12.3, "version": "0.1.0"}


def _outputs(tmp_path):
    a = make_photo(tmp_path / "a.jpg")
    b = make_photo(tmp_path / "b.jpg", gps=None)
    stops = [_stop("S01", a, transcript="<script>alert(1)</script> grey water"),
             _stop("S02", b, lat=None, lon=None),
             _stop("S03", None, lat=27.91, lon=86.93, error="model timed out")]
    paths = report.write_all(stops, META, tmp_path / "out")
    return stops, paths


def test_html_is_self_contained_and_escaped(tmp_path):
    stops, paths = _outputs(tmp_path)
    html = paths["html"].read_text(encoding="utf-8")
    assert not re.search(r'(src|href)\s*=\s*"(https?:)?//', html), "external resource"
    assert "<script" not in html.lower()
    assert "&lt;script&gt;" in html
    assert html.count('class="stop"') == len(stops)
    assert "data:image/jpeg;base64," in html


def test_failed_stop_shows_its_error_not_an_empty_checklist(tmp_path):
    _, paths = _outputs(tmp_path)
    html = paths["html"].read_text(encoding="utf-8")
    assert "Not processed: model timed out" in html
    assert "1</b>not processed" in html


def test_downgrades_are_shown(tmp_path):
    _, paths = _outputs(tmp_path)
    assert "kept as unclear" in paths["html"].read_text(encoding="utf-8")


def test_csv_has_one_row_per_stop_and_geojson_only_located_ones(tmp_path):
    stops, paths = _outputs(tmp_path)
    rows = list(csv.DictReader(paths["csv"].open(encoding="utf-8")))
    assert [r["stop"] for r in rows] == ["S01", "S02", "S03"]
    assert rows[0]["water_body"] == "yes" and rows[2]["error"] == "model timed out"
    gj = json.loads(paths["geojson"].read_text(encoding="utf-8"))
    assert [f["properties"]["stop"] for f in gj["features"]] == ["S01", "S03"]
    assert gj["features"][0]["geometry"]["coordinates"] == [86.92, 27.9]


def test_pick_spreads_photos_evenly():
    assert _pick(list(range(10)), 3) == [0, 4, 9]   # round(4.5) is 4 under banker's rounding
    assert _pick([1, 2], 3) == [1, 2]
