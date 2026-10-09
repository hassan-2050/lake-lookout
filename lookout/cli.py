"""Command line.

    python -m lookout process trips/2026-10-10                # process one day
    python -m lookout process trips/2026-10-10 --dry-run      # show stops, no model
    python -m lookout process trips/2026-10-10 --cpu          # no GPU: gemma4:e2b on CPU
    python -m lookout ui                                      # the local app

Processing runs inside the offline guard: only the local model server can be
reached. A stop that fails is recorded with its error and the run continues.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import gemma, ingest, report
from .pipeline import run_day


def _print_event(event: dict) -> None:
    kind = event["type"]
    if kind == "plan":
        print(f"{len(event['stops'])} stop(s):")
        for s in event["stops"]:
            loc = "GPS" if s["lat"] is not None else "no GPS"
            print(f"  {s['id']}  {s['time_local']}  {len(s['photos'])} photo(s), "
                  f"{len(s['memos'])} memo(s), {loc}")
            for m in s["memos"]:
                if m["time_source"].startswith("file modified"):
                    print(f"      ! {m['name']}: time from {m['time_source']}")
    elif kind == "stop_done":
        status = (f"FAILED: {event['error']}" if event["error"] else
                  f"{event['answered']} answered, {event['downgraded']} downgraded, "
                  f"{event['conflicts']} photo/voice disagreements")
        print(f"  {event['id']}: {status}")


def cmd_process(args) -> int:
    folder = Path(args.folder)
    if not folder.is_dir():
        print(f"not a folder: {folder}", file=sys.stderr)
        return 2
    if args.dry_run:
        zone = ingest.local_zone()
        from .pipeline import stop_plan
        _print_event({"type": "plan",
                      "stops": [stop_plan(s, zone) for s in ingest.scan(folder)]})
        return 0
    try:
        run = run_day(folder, model=args.model, cpu=args.cpu,
                      max_photos=args.max_photos,
                      out_dir=Path(args.out) if args.out else None,
                      progress=_print_event)
    except ValueError as exc:
        print(exc)
        return 1
    print(f"done in {run['meta']['seconds']} s -> {run['paths']['html']}")
    return 0 if not any(r["error"] for r in run["results"]) else 3


def cmd_ui(args) -> int:
    from .server import serve
    return serve(Path(args.trips), port=args.port, open_browser=not args.no_browser)


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
    pu = sub.add_parser("ui", help="open the local app in your browser")
    pu.add_argument("--trips", default="trips", help="folder holding one folder per day")
    pu.add_argument("--port", type=int, default=8765)
    pu.add_argument("--no-browser", action="store_true")
    args = p.parse_args(argv)
    if args.cmd == "process":
        if not args.model:
            args.model = gemma.CPU_MODEL if args.cpu else gemma.DEFAULT_MODEL
        return cmd_process(args)
    return cmd_ui(args)
