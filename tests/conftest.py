import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def make_photo(path: Path, when: str | None = "2026:10:10 09:15:00",
               gps: tuple | None = (27.9, 86.925, 5010.0), offset: str | None = None,
               colour=(90, 140, 170)) -> Path:
    """A small JPEG with the EXIF a phone would write.

    gps is (lat, lon, alt) in signed decimal degrees, or None for no fix.
    """
    im = Image.new("RGB", (64, 48), colour)
    exif = Image.Exif()
    if when:
        exif[0x0132] = when
        sub = exif.get_ifd(0x8769)
        sub[0x9003] = when
        if offset:
            sub[0x9011] = offset
    if gps:
        lat, lon, alt = gps

        def dms(v):
            v = abs(v)
            d = int(v)
            m = int((v - d) * 60)
            s = round(((v - d) * 60 - m) * 60, 4)
            return (float(d), float(m), float(s))

        g = exif.get_ifd(0x8825)
        g.update({1: "N" if lat >= 0 else "S", 2: dms(lat),
                  3: "E" if lon >= 0 else "W", 4: dms(lon),
                  5: b"\x00", 6: float(alt)})
    im.save(path, "JPEG", exif=exif)
    return path


def make_memo(path: Path, created_utc: str | None, seconds: float = 2.0) -> Path:
    """A short silent m4a, optionally with a creation_time tag, via ffmpeg."""
    cmd = [shutil.which("ffmpeg"), "-v", "error", "-y", "-f", "lavfi", "-i",
           "anullsrc=r=16000:cl=mono", "-t", str(seconds)]
    if created_utc:
        cmd += ["-metadata", f"creation_time={created_utc}"]
    subprocess.run(cmd + [str(path)], check=True)
    return path


needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None,
                                  reason="ffmpeg not installed")
