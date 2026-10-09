"""Subtitles for the demo video, from the narration script and its real timings.

    python tools/make_subtitles.py      # -> docs/post/lake-lookout-demo.srt and .vtt

Each narration line starts where tools/record_demo.py placed it in the edited
video (docs/post/demo-timeline.json) and lasts as long as its spoken clip.
Long lines are split into short cues at sentence and clause breaks, with time
shared in proportion to length. Words spelled for the voice are shown as
written ("oh llama" is said, "Ollama" is shown).
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import record_demo  # noqa: E402

TIMELINE = ROOT / "docs" / "post" / "demo-timeline.json"
OUT = ROOT / "docs" / "post" / "lake-lookout-demo"
SHOWN_AS = {"oh llama": "Ollama"}      # spoken spelling -> written spelling
MAX_CHARS = 84                         # two lines of about 42 characters
MIN_CUE = 1.2                          # seconds


def durations(timeline: dict) -> dict[str, float]:
    """Clip lengths: from the timeline if recorded, else by speaking each line again
    (the voice model is deterministic, so the lengths are the same)."""
    if "durations" in timeline:
        return timeline["durations"]
    import narrate
    with tempfile.TemporaryDirectory() as tmp:
        return {k: narrate.say(v[2], Path(tmp) / f"{k}.wav")
                for k, v in record_demo.SCRIPT.items()}


def chunks(text: str) -> list[str]:
    """Split a line into cue-sized pieces at sentence, then clause, boundaries."""
    for spoken, shown in SHOWN_AS.items():
        text = text.replace(spoken, shown)
    pieces = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    out = []
    for p in pieces:
        while len(p) > MAX_CHARS:
            cut = max((m.end() for m in re.finditer(r"[,:;]\s", p[:MAX_CHARS])), default=0)
            if cut < 20:
                cut = p[:MAX_CHARS].rfind(" ") + 1
            out.append(p[:cut].strip())
            p = p[cut:].strip()
        out.append(p)
    return out


def wrap(text: str, width: int = 42) -> str:
    """At most two lines, broken at the space nearest the middle."""
    if len(text) <= width:
        return text
    mid = len(text) // 2
    spaces = [i for i, c in enumerate(text) if c == " "]
    i = min(spaces, key=lambda s: abs(s - mid))
    return text[:i] + "\n" + text[i + 1:]


def cues(timeline: dict) -> list[tuple[float, float, str]]:
    starts = timeline["edited"]
    lens = durations(timeline)
    result = []
    for key, (_, _, line) in record_demo.SCRIPT.items():
        t, total = starts[key], lens[key]
        parts = chunks(line)
        weights = [len(p) for p in parts]
        for part, w in zip(parts, weights):
            d = max(MIN_CUE, total * w / sum(weights))
            result.append((t, t + d, wrap(part)))
            t += d
    # never let a cue run into the next one
    fixed = []
    for i, (a, b, text) in enumerate(result):
        if i + 1 < len(result):
            b = min(b, result[i + 1][0] - 0.05)
        fixed.append((a, b, text))
    return fixed


def stamp(t: float, sep: str) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def main() -> int:
    timeline = json.loads(TIMELINE.read_text(encoding="utf-8"))
    cs = cues(timeline)
    srt = "\n".join(f"{n}\n{stamp(a, ',')} --> {stamp(b, ',')}\n{t}\n"
                    for n, (a, b, t) in enumerate(cs, 1))
    vtt = "WEBVTT\n\n" + "\n".join(f"{stamp(a, '.')} --> {stamp(b, '.')}\n{t}\n" for a, b, t in cs)
    OUT.with_suffix(".srt").write_text(srt, encoding="utf-8")
    OUT.with_suffix(".vtt").write_text(vtt, encoding="utf-8")
    print(f"{len(cs)} cues -> {OUT.with_suffix('.srt').name}, {OUT.with_suffix('.vtt').name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
