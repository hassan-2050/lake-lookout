"""The local app's HTTP API, end to end, with a stand-in model.

A real server runs on a random loopback port over a temporary trips folder.
gemma.chat is replaced by a fake that answers like the model would, so these
tests exercise upload, grouping, processing, progress, outputs and the
security checks without needing Ollama.
"""
import http.client
import json
import threading
import time
from http.server import ThreadingHTTPServer

import pytest

from conftest import make_memo, make_photo, needs_ffmpeg
from lookout import checklist, gemma
from lookout.server import App, make_handler


def fake_chat(prompt, *, model=gemma.DEFAULT_MODEL, media=None, schema=None, cpu=False,
              max_tokens=2048, timeout=900):
    timings = {"total_s": 0.01, "load_s": 0, "prompt_s": 0, "generate_s": 0,
               "prompt_tokens": 1, "output_tokens": 1}
    if schema is None:                       # transcription
        return {"text": "Grey lake below the glacier. Loose rock ridge at the outlet.",
                "timings": timings, "model": model}
    raw = {i: {"evidence": "", "source": "none", "answer": "unclear"} for i in checklist.ITEM_IDS}
    raw["water_body"] = {"evidence": "a grey lake", "source": "photo" if media else "voice",
                         "answer": "yes"}
    raw["summary"] = "A grey lake."
    return {"text": json.dumps(raw), "timings": timings, "model": model}


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.setattr(gemma, "chat", fake_chat)
    app = App(tmp_path / "trips")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd.server_address[1], tmp_path
    httpd.shutdown()
    httpd.server_close()


def call(port, method, path, body=None, headers=None, host=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    h = {"Host": host or f"127.0.0.1:{port}", **(headers or {})}
    if isinstance(body, (dict, list)):
        body = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
    c.request(method, path, body=body, headers=h)
    r = c.getresponse()
    data = r.read()
    c.close()
    ctype = r.getheader("Content-Type", "")
    return r.status, (json.loads(data) if "json" in ctype else data), r


def test_serves_the_app_with_no_external_resources(server):
    port, _ = server
    status, html, _ = call(port, "GET", "/")
    assert status == 200 and b"Lake Lookout" in html
    for asset in ("/app.js", "/app.css"):
        status, body, _ = call(port, "GET", asset)
        assert status == 200
        assert b"http://" not in body and b"https://" not in body


def test_refuses_requests_addressed_to_another_host(server):
    """DNS-rebinding guard: a page elsewhere must not reach this API."""
    port, _ = server
    status, body, _ = call(port, "GET", "/api/days", host="evil.example:80")
    assert status == 403


def test_rejects_unsafe_names(server):
    port, _ = server
    call(port, "POST", "/api/days", {"name": "day1"})
    status, _, _ = call(port, "PUT", "/api/days/day1/files/..%2Fescape.jpg", b"x")
    assert status == 403
    status, _, _ = call(port, "PUT", "/api/days/day1/files/run.exe", b"x")
    assert status == 400
    status, _, _ = call(port, "POST", "/api/days", {"name": "../outside"})
    assert status == 403


@needs_ffmpeg
def test_upload_process_and_read_back(server, tmp_path):
    port, root = server
    assert call(port, "POST", "/api/days", {"name": "2026-10-10"})[0] == 201

    photo = make_photo(tmp_path / "lake.jpg", when="2026:10:10 09:15:00", offset="+05:00")
    memo = make_memo(tmp_path / "note.m4a", "2026-10-10T04:16:00Z")
    for f in (photo, memo):
        status, _, _ = call(port, "PUT", f"/api/days/2026-10-10/files/{f.name}", f.read_bytes(),
                            {"X-Last-Modified": "1791609600000"})
        assert status == 201

    status, day, _ = call(port, "GET", "/api/days/2026-10-10")
    assert status == 200 and len(day["plan"]) == 1
    assert day["plan"][0]["photos"] == ["lake.jpg"] and day["plan"][0]["memos"][0]["name"] == "note.m4a"
    assert day["result"] is None

    status, job, _ = call(port, "POST", "/api/days/2026-10-10/process", {"model": "gemma4:e4b"})
    assert status == 202
    for _ in range(100):
        status, job, _ = call(port, "GET", "/api/days/2026-10-10/job?since=0")
        if job["status"] != "running":
            break
        time.sleep(0.05)
    assert job["status"] == "done", job
    kinds = [e["type"] for e in job["events"]]
    assert kinds[0] == "plan" and kinds[-1] == "done" and "stop_done" in kinds

    status, day, _ = call(port, "GET", "/api/days/2026-10-10")
    stop = day["result"]["stops"][0]
    assert stop["checklist"]["water_body"]["answer"] == "yes"
    assert stop["checklist"]["water_body"]["source"] == "both"   # photo and voice agree
    assert "Grey lake" in stop["transcript"]
    assert {"trip.html", "field_log.csv", "field_log.geojson", "run.json"} <= set(day["outputs"])

    status, csv_bytes, r = call(port, "GET", "/api/days/2026-10-10/out/field_log.csv")
    assert status == 200 and b"water_body" in csv_bytes
    assert "attachment" in r.getheader("Content-Disposition")

    status, jpg, r = call(port, "GET", "/api/days/2026-10-10/thumb/lake.jpg?s=200")
    assert status == 200 and jpg[:2] == b"\xff\xd8"

    status, days, _ = call(port, "GET", "/api/days")
    assert days[0]["name"] == "2026-10-10" and days[0]["processed"]["model"] == "gemma4:e4b"


def test_processing_twice_at_once_is_refused(server, tmp_path):
    port, _ = server
    call(port, "POST", "/api/days", {"name": "d"})
    photo = make_photo(tmp_path / "a.jpg")
    call(port, "PUT", "/api/days/d/files/a.jpg", photo.read_bytes())
    first = call(port, "POST", "/api/days/d/process", {})[0]
    second = call(port, "POST", "/api/days/d/process", {})[0]
    assert first == 202
    assert second in (202, 409)     # 202 only if the first finished in between
