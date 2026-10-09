"""Process one day's folder: the code shared by the command line and the app.

`run_day` scans the folder, processes every stop inside the offline guard,
writes the outputs, and reports progress through an optional callback so the
app can show it live. A stop that fails is recorded with its error and the run
carries on; a failure is shown, never dropped.
"""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from . import __version__, audio, checklist, gemma, ingest, report
from .offline import offline
from .verify import merge, verify

Progress = Callable[[dict], None]


def pick(items: list, n: int) -> list:
    """At most n items, spread evenly across the list."""
    if len(items) <= n:
        return items
    step = (len(items) - 1) / (n - 1) if n > 1 else 0
    return [items[round(i * step)] for i in range(n)]


def stop_plan(stop: ingest.Stop, zone) -> dict:
    """What is known about a stop before the model runs."""
    loc = stop.location
    return {
        "id": stop.id,
        "time_utc": stop.time.isoformat(),
        "time_local": report.local_time_label(stop.time, zone),
        "lat": loc[0] if loc else None, "lon": loc[1] if loc else None,
        "alt_m": loc[2] if loc else None,
        "photos": [p.path.name for p in stop.photos],
        "photo_paths": [str(p.path) for p in stop.photos],
        "photo_time_sources": sorted({p.time_source for p in stop.photos}),
        "memos": [{"name": m.path.name, "time_source": m.time_source,
                   "duration_s": round(m.duration_s, 1)} for m in stop.memos],
    }


def process_stop(stop: ingest.Stop, *, model: str, cpu: bool, max_photos: int,
                 zone, step: Callable[[str], None] = lambda s: None) -> dict:
    out = {**stop_plan(stop, zone), "model": model, "transcript": "",
           "timings": {}, "error": None}
    try:
        texts, t_timings = [], []
        for m in stop.memos:
            step(f"transcribing {m.path.name}")
            r = gemma.transcribe(audio.chunks_b64(m.path), model=model, cpu=cpu)
            if r["text"]:
                texts.append(r["text"])
            t_timings += r["timings"]
        out["transcript"] = "\n".join(texts)
        out["timings"]["transcribe"] = t_timings

        photos = pick(stop.photos, max_photos)
        if not photos and not out["transcript"]:
            out["error"] = "voice note had no speech and there is no photo"
            return out
        # Photo and voice note are asked about separately and then merged:
        # given both at once, the model stopped looking at the photo.
        photo_cl = voice_cl = None
        out["raw"], out["downgrades"] = {}, []
        if photos:
            step(f"reading {len(photos)} photo(s)")
            media = [gemma.image_b64(p.path) for p in photos]
            r = gemma.checklist(checklist.prompt(None, len(media)), media,
                                checklist.json_schema(), model=model, cpu=cpu)
            out["timings"]["checklist_photo"] = r["timings"]
            out["raw"]["photo"] = r["raw"]
            photo_cl, down = verify(r["raw"], has_photo=True, has_voice=False)
            out["downgrades"] += [{**d, "pass": "photo"} for d in down]
        if out["transcript"]:
            step("reading the voice note")
            r = gemma.checklist(checklist.prompt(out["transcript"], 0), [],
                                checklist.json_schema(), model=model, cpu=cpu)
            out["timings"]["checklist_voice"] = r["timings"]
            out["raw"]["voice"] = r["raw"]
            voice_cl, down = verify(r["raw"], has_photo=False, has_voice=True,
                                    transcript=out["transcript"])
            out["downgrades"] += [{**d, "pass": "voice"} for d in down]
        out["checklist"], out["conflicts"] = merge(photo_cl, voice_cl)
    except (gemma.ModelError, audio.AudioError, OSError) as exc:
        out["error"] = str(exc)
    return out


def answered(result: dict) -> int:
    cl = result.get("checklist") or {}
    return sum(1 for i in checklist.ITEM_IDS
               if (cl.get(i) or {}).get("answer") not in (None, "unclear"))


def run_day(folder: Path, *, model: str, cpu: bool = False, max_photos: int = 3,
            out_dir: Path | None = None, progress: Progress | None = None) -> dict:
    """Process `folder`. Returns {results, meta, paths}."""
    emit = progress or (lambda event: None)
    zone = ingest.local_zone()
    stops = ingest.scan(folder)
    emit({"type": "plan", "stops": [stop_plan(s, zone) for s in stops]})
    if not stops:
        raise ValueError("no photos or voice notes found")

    started = time.perf_counter()
    results = []
    with offline():
        for n, s in enumerate(stops, 1):
            emit({"type": "stop", "id": s.id, "index": n, "total": len(stops)})
            r = process_stop(
                s, model=model, cpu=cpu, max_photos=max_photos, zone=zone,
                step=lambda text, sid=s.id: emit({"type": "step", "id": sid, "text": text}))
            results.append(r)
            emit({"type": "stop_done", "id": s.id, "index": n, "total": len(stops),
                  "error": r["error"], "answered": answered(r),
                  "downgraded": len(r.get("downgrades") or []),
                  "conflicts": len(r.get("conflicts") or [])})
    seconds = round(time.perf_counter() - started, 1)

    meta = {"day": folder.name, "model": model, "cpu_only": cpu,
            "processed": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M"),
            "seconds": seconds, "version": __version__}
    paths = report.write_all(results, meta, out_dir or folder / "lookout_out")
    emit({"type": "done", "seconds": seconds, "failed": sum(1 for r in results if r["error"])})
    return {"results": results, "meta": meta, "paths": paths}
