"""Read a day's folder of phone photos and voice memos and group it into stops.

A stop is what happened at one place: one or more photos taken close together
in time and space, plus the voice memos recorded there. A memo with no photo
nearby is still a stop, a voice-only one, because "I saw ice on the far shore"
is an observation even when the camera stayed in the pocket.

TIME. Every timestamp is converted to an aware UTC datetime before anything
is compared. Phones are inconsistent here: a photo's EXIF time is usually local
wall-clock time with no zone, while a voice memo's container time is usually
UTC. Comparing them naively shifts every memo by the UTC offset, which at UTC+5
pairs nothing. A time with no zone is read as the laptop's local zone, which is
right when the phone and laptop are set to the same place.

Where each time came from is recorded in `time_source`, and a memo whose time
only came from the file's modified date is flagged, because copying files off
a phone can reset that date to the moment of the copy.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image

from . import audio

try:                                    # iPhone photos are HEIC
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:                     # pragma: no cover
    pass

PHOTO_EXT = {".jpg", ".jpeg", ".png", ".heic", ".heif"}
AUDIO_EXT = {".m4a", ".mp3", ".wav", ".ogg", ".opus", ".aac", ".amr", ".3gp",
             ".webm", ".flac"}

# Grouping and pairing windows.
SAME_STOP_GAP = timedelta(minutes=5)    # photos closer than this in time...
SAME_STOP_METRES = 150.0                # ...and in space belong to one stop
MEMO_BEFORE = timedelta(minutes=2)      # a memo may start a little before the photo
MEMO_AFTER = timedelta(minutes=10)      # or up to this long after the last one

_EXIF_IFD = 0x8769
_GPS_IFD = 0x8825
_DATETIME = 0x0132
_DATETIME_ORIGINAL = 0x9003
_OFFSET_TIME_ORIGINAL = 0x9011

_FILENAME_TIME = re.compile(
    r"(20\d{2})[-_.]?(\d{2})[-_.]?(\d{2})[ _T.-]?(\d{2})[-_.:]?(\d{2})[-_.:]?(\d{2})")


@dataclass
class Photo:
    path: Path
    time: datetime
    time_source: str
    lat: float | None = None
    lon: float | None = None
    alt_m: float | None = None


@dataclass
class Memo:
    path: Path
    time: datetime
    time_source: str
    duration_s: float = 0.0


@dataclass
class Stop:
    id: str
    photos: list[Photo] = field(default_factory=list)
    memos: list[Memo] = field(default_factory=list)

    @property
    def time(self) -> datetime:
        times = [p.time for p in self.photos] or [m.time for m in self.memos]
        return min(times)

    @property
    def location(self) -> tuple[float, float, float | None] | None:
        for p in self.photos:
            if p.lat is not None and p.lon is not None:
                return p.lat, p.lon, p.alt_m
        return None


def local_zone():
    return datetime.now().astimezone().tzinfo


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=local_zone())
    return dt.astimezone(timezone.utc)


def _mtime(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


def time_from_filename(name: str) -> datetime | None:
    """Recorder apps name files like Recording_20261010_091530.m4a (local time)."""
    m = _FILENAME_TIME.search(name)
    if not m:
        return None
    try:
        return _aware(datetime(*map(int, m.groups())))
    except ValueError:
        return None


def _rational(v) -> float:
    try:
        return float(v)
    except (TypeError, ZeroDivisionError, ValueError):
        num, den = v
        return num / den if den else 0.0


def dms_to_decimal(dms, ref: str) -> float:
    """EXIF degrees/minutes/seconds to signed decimal degrees."""
    d, m, s = (_rational(x) for x in dms)
    value = d + m / 60.0 + s / 3600.0
    return -value if str(ref).upper() in ("S", "W") else value


def read_photo(path: Path) -> Photo:
    with Image.open(path) as im:
        exif = im.getexif()
    sub = exif.get_ifd(_EXIF_IFD)
    gps = exif.get_ifd(_GPS_IFD)

    time, source = None, "file modified date"
    raw = sub.get(_DATETIME_ORIGINAL) or exif.get(_DATETIME)
    if raw:
        try:
            dt = datetime.strptime(str(raw).strip(), "%Y:%m:%d %H:%M:%S")
            offset = sub.get(_OFFSET_TIME_ORIGINAL)
            if offset:
                sign = -1 if str(offset).startswith("-") else 1
                hh, mm = str(offset).lstrip("+-").split(":")
                dt = dt.replace(tzinfo=timezone(sign * timedelta(
                    hours=int(hh), minutes=int(mm))))
            time, source = _aware(dt), "photo EXIF"
        except ValueError:
            time = None
    if time is None:
        time = _mtime(path)

    lat = lon = alt = None
    if gps.get(2) and gps.get(4):
        try:
            lat = dms_to_decimal(gps[2], gps.get(1, "N"))
            lon = dms_to_decimal(gps[4], gps.get(3, "E"))
            if gps.get(6) is not None:
                alt = _rational(gps[6]) * (-1 if gps.get(5) in (1, b"\x01") else 1)
        except (TypeError, ValueError, ZeroDivisionError):
            lat = lon = alt = None
        if lat is not None and (abs(lat) > 90 or abs(lon) > 180 or (lat == 0 and lon == 0)):
            lat = lon = alt = None          # a zeroed or corrupt fix is no fix
    return Photo(path, time, source, lat, lon, alt)


def read_memo(path: Path) -> Memo:
    info = audio.probe(path)
    if info["created"] is not None:
        return Memo(path, _aware(info["created"]), "audio metadata", info["duration_s"])
    from_name = time_from_filename(path.name)
    if from_name is not None:
        return Memo(path, from_name, "file name", info["duration_s"])
    return Memo(path, _mtime(path), "file modified date (may be the copy time)",
                info["duration_s"])


def metres_between(a: Photo, b: Photo) -> float | None:
    if None in (a.lat, a.lon, b.lat, b.lon):
        return None
    r = 6_371_000.0
    p1, p2 = math.radians(a.lat), math.radians(b.lat)
    dp, dl = p2 - p1, math.radians(b.lon - a.lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def group(photos: list[Photo], memos: list[Memo]) -> list[Stop]:
    """Photos into stops by time and distance, then memos onto the nearest stop."""
    stops: list[Stop] = []
    for p in sorted(photos, key=lambda x: x.time):
        if stops:
            last = stops[-1].photos[-1]
            dist = metres_between(last, p)
            if p.time - last.time <= SAME_STOP_GAP and (dist is None or dist <= SAME_STOP_METRES):
                stops[-1].photos.append(p)
                continue
        stops.append(Stop(id="", photos=[p]))

    voice_only: list[Stop] = []
    for m in sorted(memos, key=lambda x: x.time):
        best, best_gap = None, None
        for s in stops:
            start = s.photos[0].time - MEMO_BEFORE
            end = s.photos[-1].time + MEMO_AFTER
            if start <= m.time <= end:
                gap = abs((m.time - s.photos[-1].time).total_seconds())
                if best_gap is None or gap < best_gap:
                    best, best_gap = s, gap
        if best is not None:
            best.memos.append(m)
        else:
            voice_only.append(Stop(id="", memos=[m]))

    everything = sorted(stops + voice_only, key=lambda s: s.time)
    for n, s in enumerate(everything, 1):
        s.id = f"S{n:02d}"
    return everything


def scan(folder: Path) -> list[Stop]:
    """Read every photo and memo in `folder` (not recursive) and group them."""
    photos, memos = [], []
    for path in sorted(folder.iterdir()):
        ext = path.suffix.lower()
        if ext in PHOTO_EXT:
            photos.append(read_photo(path))
        elif ext in AUDIO_EXT:
            memos.append(read_memo(path))
    return group(photos, memos)
