"""Voice memos: decode with ffmpeg, split into chunks the model accepts.

Phones record m4a/AAC, 3gp, ogg or wav. Everything is decoded to 16 kHz mono
16-bit PCM, the format speech models are trained on, and cut into chunks of at
most CHUNK_SECONDS, because a single audio input to Gemma's audio encoder is
limited in length. Each chunk is wrapped as a WAV file in memory; nothing is
written to disk.
"""
from __future__ import annotations

import base64
import io
import json
import shutil
import subprocess
import wave
from datetime import datetime
from pathlib import Path

RATE = 16_000
CHUNK_SECONDS = 30


class AudioError(RuntimeError):
    pass


def _tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise AudioError(f"{name} not found on PATH. Install ffmpeg "
                         "(https://ffmpeg.org) to read voice memos.")
    return path


def probe(path: Path) -> dict:
    """Duration in seconds and the container's creation_time tag, if any."""
    out = subprocess.run(
        [_tool("ffprobe"), "-v", "quiet", "-print_format", "json",
         "-show_format", str(path)],
        capture_output=True, text=True, check=False)
    if out.returncode != 0:
        raise AudioError(f"ffprobe could not read {path.name}")
    fmt = json.loads(out.stdout or "{}").get("format", {})
    tags = {k.lower(): v for k, v in (fmt.get("tags") or {}).items()}
    created = None
    raw = tags.get("creation_time") or tags.get("date")
    if raw:
        try:
            created = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            created = None
    return {"duration_s": float(fmt.get("duration") or 0.0), "created": created}


def decode_pcm(path: Path) -> bytes:
    """16 kHz mono s16le PCM for the whole file."""
    out = subprocess.run(
        [_tool("ffmpeg"), "-v", "error", "-i", str(path), "-ac", "1",
         "-ar", str(RATE), "-f", "s16le", "-"],
        capture_output=True, check=False)
    if out.returncode != 0 or not out.stdout:
        raise AudioError(f"ffmpeg could not decode {path.name}: "
                         f"{out.stderr.decode('utf-8', 'replace')[:200]}")
    return out.stdout


def _wav(pcm: bytes) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm)
    return buf.getvalue()


def chunks_b64(path: Path, chunk_seconds: int = CHUNK_SECONDS) -> list[str]:
    """The memo as base64 WAV chunks, each at most `chunk_seconds` long.

    A final fragment shorter than one second is dropped: it is almost always
    the tail of a pause, and the model tends to invent words for near-silence.
    """
    pcm = decode_pcm(path)
    step = RATE * 2 * chunk_seconds
    min_tail = RATE * 2
    parts = [pcm[i:i + step] for i in range(0, len(pcm), step)]
    if len(parts) > 1 and len(parts[-1]) < min_tail:
        parts.pop()
    return [base64.b64encode(_wav(p)).decode("ascii") for p in parts]
