"""The local app: a small web server for your own browser, on 127.0.0.1 only.

    python -m lookout ui            # opens http://127.0.0.1:8765

Standard library only. It never listens on the network: the socket is bound to
loopback, and requests whose Host header is not this machine are refused, so a
web page elsewhere cannot reach it through your browser (DNS rebinding).
Processing runs in a background thread under the same offline guard as the
command line, and the page polls for progress.

One folder per day under trips/. The app reads and writes only there.
"""
from __future__ import annotations

import io
import json
import mimetypes
import os
import re
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PIL import Image, ImageOps

from . import __version__, checklist, gemma, ingest
from .pipeline import run_day, stop_plan

UI_DIR = Path(__file__).resolve().parent / "ui"
MAX_UPLOAD = 300 * 1024 * 1024
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.\-]{0,80}$")
OUT = "lookout_out"


class Job:
    def __init__(self, day: str, model: str, cpu: bool):
        self.day, self.model, self.cpu = day, model, cpu
        self.status = "running"
        self.events: list[dict] = []
        self.error: str | None = None
        self.started = time.time()
        self.lock = threading.Lock()

    def add(self, event: dict) -> None:
        with self.lock:
            self.events.append({**event, "t": round(time.time() - self.started, 1)})

    def view(self, since: int = 0) -> dict:
        with self.lock:
            return {"day": self.day, "model": self.model, "cpu": self.cpu,
                    "status": self.status, "error": self.error,
                    "events": self.events[since:], "next": len(self.events)}


class App:
    def __init__(self, trips: Path):
        self.trips = trips.resolve()
        self.trips.mkdir(parents=True, exist_ok=True)
        self.jobs: dict[str, Job] = {}
        self.thumbs: dict[tuple, bytes] = {}

    # --- paths -------------------------------------------------------------
    def day_dir(self, name: str) -> Path:
        if not _SAFE_NAME.match(name or ""):
            raise PermissionError("bad day name")
        path = (self.trips / name).resolve()
        if path.parent != self.trips:
            raise PermissionError("outside trips folder")
        return path

    def file_in(self, day: str, name: str, sub: str | None = None) -> Path:
        base = self.day_dir(day) / sub if sub else self.day_dir(day)
        if not _SAFE_NAME.match(name or ""):
            raise PermissionError("bad file name")
        path = (base / name).resolve()
        if path.parent != base.resolve():
            raise PermissionError("outside day folder")
        return path

    # --- views -------------------------------------------------------------
    def days(self) -> list[dict]:
        out = []
        for d in sorted(p for p in self.trips.iterdir() if p.is_dir() and _SAFE_NAME.match(p.name)):
            files = [f for f in d.iterdir() if f.is_file()]
            run = d / OUT / "run.json"
            meta = json.loads(run.read_text(encoding="utf-8"))["meta"] if run.exists() else None
            job = self.jobs.get(d.name)
            out.append({
                "name": d.name,
                "photos": sum(f.suffix.lower() in ingest.PHOTO_EXT for f in files),
                "memos": sum(f.suffix.lower() in ingest.AUDIO_EXT for f in files),
                "processed": meta, "job": job.status if job else None})
        return out

    def day(self, name: str) -> dict:
        d = self.day_dir(name)
        if not d.is_dir():
            raise FileNotFoundError(name)
        zone = ingest.local_zone()
        plan, plan_error = [], None
        try:
            plan = [stop_plan(s, zone) for s in ingest.scan(d)]
        except Exception as exc:  # noqa: BLE001 - shown to the user, not swallowed
            plan_error = str(exc)
        for s in plan:
            s.pop("photo_paths", None)
        run = d / OUT / "run.json"
        result = json.loads(run.read_text(encoding="utf-8")) if run.exists() else None
        job = self.jobs.get(name)
        return {"name": name, "plan": plan, "plan_error": plan_error, "result": result,
                "job": job.view() if job else None,
                "outputs": sorted(p.name for p in (d / OUT).iterdir()) if (d / OUT).is_dir() else []}

    def health(self) -> dict:
        models, ok = [], False
        try:
            with urllib.request.urlopen(f"{gemma.BASE_URL.rstrip('/')}/api/tags", timeout=3) as r:
                tags = json.loads(r.read().decode("utf-8"))
            ok = True
            models = sorted(m["name"] for m in tags.get("models", [])
                            if m["name"].startswith(("gemma4", "gemma3")))
        except OSError:
            pass
        return {"ollama": ok, "models": models, "default_model": gemma.DEFAULT_MODEL,
                "cpu_model": gemma.CPU_MODEL, "version": __version__,
                "checklist": [{"id": i.id, "label": i.label, "question": i.question,
                               "source": i.source, "needs": i.needs}
                              for i in checklist.ITEMS]}

    # --- actions -----------------------------------------------------------
    def start(self, name: str, model: str, cpu: bool) -> dict:
        d = self.day_dir(name)
        current = self.jobs.get(name)
        if current and current.status == "running":
            raise RuntimeError("already processing this day")
        job = Job(name, model, cpu)
        self.jobs[name] = job

        def work():
            try:
                run_day(d, model=model, cpu=cpu, progress=job.add)
                job.status = "done"
            except Exception as exc:  # noqa: BLE001 - reported to the page
                job.error, job.status = str(exc), "failed"
                job.add({"type": "error", "text": str(exc)})

        threading.Thread(target=work, daemon=True).start()
        return job.view()

    def thumbnail(self, day: str, name: str, side: int) -> bytes:
        path = self.file_in(day, name)
        st = path.stat()
        key = (str(path), st.st_mtime, st.st_size, side)
        if key not in self.thumbs:
            with Image.open(path) as im:
                im = ImageOps.exif_transpose(im).convert("RGB")
                im.thumbnail((side, side))
                buf = io.BytesIO()
                im.save(buf, "JPEG", quality=82)
            self.thumbs[key] = buf.getvalue()
        return self.thumbs[key]


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        server_version = f"LakeLookout/{__version__}"

        def log_message(self, fmt, *args):  # quiet
            pass

        # --- helpers -------------------------------------------------------
        def _send(self, status: int, body: bytes, ctype: str, extra: dict | None = None):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, obj, status: int = 200):
            self._send(status, json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8"),
                       "application/json; charset=utf-8")

        def _error(self, status: int, text: str):
            self._json({"error": text}, status)

        def _body(self) -> bytes:
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_UPLOAD:
                raise ValueError("file too large")
            return self.rfile.read(n)

        def _route(self):
            port = self.server.server_address[1]
            if self.headers.get("Host") not in (f"127.0.0.1:{port}", f"localhost:{port}"):
                self._error(403, "this app only answers requests from this computer")
                return None
            url = urllib.parse.urlsplit(self.path)
            parts = [urllib.parse.unquote(p) for p in url.path.split("/") if p]
            return parts, urllib.parse.parse_qs(url.query)

        def _guard(self, fn):
            try:
                fn()
            except PermissionError as exc:
                self._error(403, str(exc))
            except FileNotFoundError as exc:
                self._error(404, f"not found: {exc}")
            except (ValueError, RuntimeError) as exc:
                self._error(409 if isinstance(exc, RuntimeError) else 400, str(exc))

        # --- GET -----------------------------------------------------------
        def do_GET(self):
            r = self._route()
            if r is None:
                return
            parts, q = r
            self._guard(lambda: self._get(parts, q))

        do_HEAD = do_GET

        def _get(self, parts, q):
            if not parts:
                return self._static("index.html")
            if parts[0] in ("app.js", "app.css", "favicon.svg"):
                return self._static(parts[0])
            if parts[:2] == ["api", "health"]:
                return self._json(app.health())
            if parts == ["api", "days"]:
                return self._json(app.days())
            if len(parts) >= 3 and parts[:2] == ["api", "days"]:
                day = parts[2]
                if len(parts) == 3:
                    return self._json(app.day(day))
                if parts[3] == "job" and len(parts) == 4:
                    job = app.jobs.get(day)
                    since = int((q.get("since") or ["0"])[0])
                    return self._json(job.view(since) if job else {"status": None})
                if parts[3] == "thumb" and len(parts) == 5:
                    side = max(64, min(1600, int((q.get("s") or ["480"])[0])))
                    return self._send(200, app.thumbnail(day, parts[4], side), "image/jpeg")
                if parts[3] == "file" and len(parts) == 5:
                    path = app.file_in(day, parts[4])
                    ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                    if path.suffix.lower() == ".m4a":
                        ctype = "audio/mp4"
                    return self._send(200, path.read_bytes(), ctype)
                if parts[3] == "out" and len(parts) == 5:
                    path = app.file_in(day, parts[4], sub=OUT)
                    ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                    disp = {} if path.suffix == ".html" else {
                        "Content-Disposition": f'attachment; filename="{day}_{path.name}"'}
                    return self._send(200, path.read_bytes(), ctype, disp)
            raise FileNotFoundError("/".join(parts))

        def _static(self, name: str):
            path = UI_DIR / name
            ctype = {"html": "text/html; charset=utf-8", "js": "text/javascript; charset=utf-8",
                     "css": "text/css; charset=utf-8", "svg": "image/svg+xml"}[name.rsplit(".", 1)[1]]
            self._send(200, path.read_bytes(), ctype)

        # --- POST / PUT ----------------------------------------------------
        def do_POST(self):
            r = self._route()
            if r is None:
                return
            parts, _ = r
            self._guard(lambda: self._post(parts))

        def _post(self, parts):
            data = json.loads(self._body() or b"{}")
            if parts == ["api", "days"]:
                d = app.day_dir(str(data.get("name", "")).strip())
                d.mkdir(exist_ok=True)
                return self._json({"name": d.name}, 201)
            if len(parts) == 4 and parts[:2] == ["api", "days"] and parts[3] == "process":
                cpu = bool(data.get("cpu"))
                model = data.get("model") or (gemma.CPU_MODEL if cpu else gemma.DEFAULT_MODEL)
                if not re.match(r"^[a-z0-9][a-z0-9.:\-_]{0,60}$", model):
                    raise ValueError("bad model name")
                return self._json(app.start(parts[2], model, cpu), 202)
            raise FileNotFoundError("/".join(parts))

        def do_PUT(self):
            r = self._route()
            if r is None:
                return
            parts, _ = r
            self._guard(lambda: self._put(parts))

        def _put(self, parts):
            if not (len(parts) == 5 and parts[:2] == ["api", "days"] and parts[3] == "files"):
                raise FileNotFoundError("/".join(parts))
            day, name = parts[2], parts[4]
            if Path(name).suffix.lower() not in ingest.PHOTO_EXT | ingest.AUDIO_EXT:
                raise ValueError(f"{name}: not a photo or voice note")
            app.day_dir(day).mkdir(exist_ok=True)
            path = app.file_in(day, name)
            path.write_bytes(self._body())
            # Keep the phone's modified time: a memo with no recorded time and
            # no time in its name is placed by it.
            modified = self.headers.get("X-Last-Modified")
            if modified and modified.isdigit():
                ts = int(modified) / 1000
                os.utime(path, (ts, ts))
            self._json({"saved": name}, 201)

    return Handler


def serve(trips: Path, port: int = 8765, open_browser: bool = True) -> int:
    app = App(trips)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(app))
    url = f"http://127.0.0.1:{port}/"
    print(f"Lake Lookout {__version__} at {url}  (trips folder: {app.trips})")
    print("Only this computer can open it. Ctrl+C to stop.")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0
