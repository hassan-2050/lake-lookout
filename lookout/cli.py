"""Command line: process one day's folder of photos and voice notes.

    python -m lookout process trips/2026-10-10
    python -m lookout process trips/2026-10-10 --dry-run      # show stops, no model
    python -m lookout process trips/2026-10-10 --model gemma4:e2b --cpu

Processing runs inside the offline guard: only the local model server can be
reached. A stop that fails is recorded with its error and the run continues.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

from . import __version__, audio, checklist, gemma, ingest, report
from .offline import offline
from .verify import merge, verify


def _pick(items: list, n: int) -> list:
    """At most n items, spread evenly across the list."""
    if len(items) <= n:
        return items
    step = (len(items) - 1) / (n - 1) if n > 1 else 0
    return [items[round(i * step)] for i in range(n)]


def process_stop(stop: ingest.Stop, *, model: str, cpu: bool, max_photos: int,
                 zone) -> dict:
    loc = stop.location
    out = {
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
        "model": model, "transcript": "", "timings": {}, "error": None,
    }
    try:
        texts, t_timings = [], []
        for m in stop.memos:
            r = gemma.transcribe(audio.chunks_b64(m.path), model=model, cpu=cpu)
            if r["text"]:
                texts.append(r["text"])
            t_timings += r["timings"]
        out["transcript"] = "\n".join(texts)
        out["timings"]["transcribe"] = t_timings

        photos = _pick(stop.photos, max_photos)
        if not photos and not out["transcript"]:
            out["error"] = "voice note had no speech and there is no photo"
            return out
        # Photo and voice note are asked about separately and then merged:
        # given both at once, the model stopped looking at the photo.
        photo_cl = voice_cl = None
        out["raw"], out["downgrades"] = {}, []
        if photos:
            media = [gemma.image_b64(p.path) for p in photos]
            r = gemma.checklist(checklist.prompt(None, len(media)), media,
                                checklist.json_schema(), model=model, cpu=cpu)
            out["timings"]["checklist_photo"] = r["timings"]
            out["raw"]["photo"] = r["raw"]
            photo_cl, down = verify(r["raw"], has_photo=True, has_voice=False)
            out["downgrades"] += [{**d, "pass": "photo"} for d in down]
        if out["transcript"]:
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


def cmd_process(args) -> int:
    folder = Path(args.folder)
    if not folder.is_dir():
        print(f"not a folder: {folder}", file=sys.stderr)
        return 2
    zone = ingest.local_zone()
    stops = ingest.scan(folder)
    if not stops:
        print("no photos or voice notes found")
        return 1

    print(f"{len(stops)} stop(s) in {folder}:")
    for s in stops:
        loc = "GPS" if s.location else "no GPS"
        print(f"  {s.id}  {report.local_time_label(s.time, zone)}  "
              f"{len(s.photos)} photo(s), {len(s.memos)} memo(s), {loc}")
        for m in s.memos:
            if m.time_source.startswith("file modified"):
                print(f"      ! {m.path.name}: time from {m.time_source}")
    if args.dry_run:
        return 0

    started = time.perf_counter()
    results = []
    with offline():
        for s in stops:
            r = process_stop(s, model=args.model, cpu=args.cpu,
                             max_photos=args.max_photos, zone=zone)
            status = "FAILED: " + r["error"] if r["error"] else (
                f'{sum(1 for i in checklist.ITEM_IDS if r["checklist"][i]["answer"] != "unclear")}'
                f'/{len(checklist.ITEM_IDS)} answered, {len(r["downgrades"])} downgraded')
            print(f"  {r['id']}: {status}")
            results.append(r)
    seconds = round(time.perf_counter() - started, 1)

    meta = {"day": folder.name, "model": args.model, "cpu_only": args.cpu,
            "processed": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M"),
            "seconds": seconds, "version": __version__}
    out_dir = Path(args.out) if args.out else folder / "lookout_out"
    paths = report.write_all(results, meta, out_dir)
    print(f"done in {seconds} s -> {paths['html']}")
    return 0 if not any(r["error"] for r in results) else 3


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="lookout", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    pp = sub.add_parser("process", help="process one day's folder")
    pp.add_argument("folder")
    pp.add_argument("--model", help=f"Ollama model (default {gemma.DEFAULT_MODEL}, "
                                    f"or {gemma.CPU_MODEL} with --cpu)")
    pp.add_argument("--cpu", action="store_true", help="run the model on CPU only")
    pp.add_argument("--max-photos", type=int, default=3,
                    help="photos sent to the model per stop (default 3)")
    pp.add_argument("--out", help="output folder (default <folder>/lookout_out)")
    pp.add_argument("--dry-run", action="store_true",
                    help="show how files group into stops, without the model")
    args = p.parse_args(argv)
    if not args.model:
        args.model = gemma.CPU_MODEL if args.cpu else gemma.DEFAULT_MODEL
    return cmd_process(args)
