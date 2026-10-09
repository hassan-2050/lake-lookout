"""Build trips/synthetic-day/: a fake day out, for testing the whole pipeline.

    python tools/make_synthetic_day.py

SYNTHETIC. These are not one person's hike. The photos are the Wikimedia
evaluation photos, stamped with the real coordinates of each lake and invented
times on one day, and the voice notes are read by the Windows speech engine.
It exists so every path runs end to end before a real outing: photos with and
without GPS, a voice note paired with a photo, a voice note with no photo, and
memo times stored in UTC while photo times are local.

Speech is generated with Windows' built-in System.Speech, so the voice notes
need Windows; elsewhere the photos are still written.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
PHOTOS = ROOT / "eval" / "photos"
OUT = ROOT / "trips" / "synthetic-day"
DAY = "2026:10:10"

# photo slug, local time, (lat, lon, alt) or None
SHOTS = [
    ("gokyo", "09:10:00", (27.9555, 86.6935, 4790.0)),
    ("imja_tsho", "11:40:00", (27.8985, 86.9250, 5010.0)),
    ("tsho_rolpa", "14:05:00", (27.8600, 86.4770, 4580.0)),
    ("pond", "15:30:00", None),
]

# file name, UTC creation time, words
MEMOS = [
    ("gokyo_note.m4a", "2026-10-10T04:11:20Z",
     "Third Gokyo lake. The water is bright turquoise. On the left there is a "
     "long ridge of loose rock between the lake and the glacier. The lodges are "
     "at the near end of the lake."),
    ("imja_note.m4a", "2026-10-10T06:41:05Z",
     "Grey milky lake under steep rock walls with snow in the gullies. I can't "
     "see the far end of the lake from here."),
    ("trail_note.m4a", "2026-10-10T08:00:00Z",
     "Passed a small pond beside the trail. No ice anywhere near it, and the "
     "water looked clear. I didn't take a photo."),
]


def _dms(v: float) -> tuple:
    v = abs(v)
    d = int(v)
    m = int((v - d) * 60)
    return (float(d), float(m), round(((v - d) * 60 - m) * 60, 3))


def stamp_photo(slug: str, clock: str, gps) -> None:
    with Image.open(PHOTOS / f"{slug}.jpg") as im:
        exif = Image.Exif()
        when = f"{DAY} {clock}"
        exif[0x0132] = when
        exif.get_ifd(0x8769)[0x9003] = when
        if gps:
            lat, lon, alt = gps
            exif.get_ifd(0x8825).update({1: "N" if lat >= 0 else "S", 2: _dms(lat),
                                         3: "E" if lon >= 0 else "W", 4: _dms(lon),
                                         5: b"\x00", 6: alt})
        im.save(OUT / f"{slug}.jpg", "JPEG", quality=92, exif=exif)


def speak(text: str, wav: Path) -> bool:
    if sys.platform != "win32":
        return False
    script = ("Add-Type -AssemblyName System.Speech;"
              "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
              f"$s.SetOutputToWaveFile('{wav}');$s.Speak($env:LOOKOUT_TEXT);$s.Dispose()")
    env = {**__import__("os").environ, "LOOKOUT_TEXT": text}
    r = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                       env=env, capture_output=True, text=True)
    return r.returncode == 0 and wav.exists()


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    for slug, clock, gps in SHOTS:
        stamp_photo(slug, clock, gps)
        print(f"  photo {slug}.jpg  {clock}  {'GPS' if gps else 'no GPS'}")
    with tempfile.TemporaryDirectory() as tmp:
        for name, created, words in MEMOS:
            wav = Path(tmp) / "speech.wav"
            if not speak(words, wav):
                print(f"  memo {name}: skipped (needs Windows speech)")
                continue
            subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-y", "-i", str(wav),
                            "-c:a", "aac", "-b:a", "64k", "-metadata",
                            f"creation_time={created}", str(OUT / name)], check=True)
            wav.unlink()
            print(f"  memo {name}  {created}")
    (OUT / "README.md").write_text(
        "# Synthetic day (test data, not a real hike)\n\n"
        "Built by `tools/make_synthetic_day.py` from the Wikimedia evaluation photos "
        "(see `eval/photos/ATTRIBUTION.md`), stamped with each lake's real coordinates "
        "and invented times, plus voice notes read by a speech engine.\n",
        encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
