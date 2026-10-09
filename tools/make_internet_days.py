"""Build realistic test days from freely licensed internet photos.

    python tools/make_internet_days.py          # writes trips/test-hunza/ and trips/test-skardu/

TEST DATA, NOT A HIKE. Each day is assembled from Wikimedia Commons photos by
different photographers, taken in different years. What is real: the photos and
the camera positions recorded on each file's page, which are written into the
EXIF. What is invented: the clock times, which put the stops in route order on
one day, and the voice notes, which are written to describe what each photo
shows and read by the Windows speech engine. Licences and authors are written
to each day's ATTRIBUTION.md.

It exercises what the synthetic day cannot: real camera framings, glaciers with
no lake in frame, places with no water at all, a dammed reservoir, a heavily
processed winter photo, and stops a few hundred metres apart.
"""
from __future__ import annotations

import html
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_synthetic_day import speak  # noqa: E402  (Windows speech, shared)

ROOT = Path(__file__).resolve().parents[1]
UA = "LakeLookout/0.1 (open-source hackathon project; one-off download of test photos)"
API = "https://en.wikipedia.org/w/api.php"
UTC_OFFSET_H = 5          # the invented clock times are Pakistan time (UTC+5)

DAYS = {
    "test-hunza": {
        "date": "2026:10:07",
        "about": "Karimabad to Passu along the Karakoram Highway, Hunza, Gilgit-Baltistan.",
        "stops": [
            ("File:Baltit fort from ultar sar trek.jpg", "08:30:00",
             "Starting above Karimabad. No lake here, just the fort on the ridge and the "
             "poplars turning yellow."),
            ("File:Attabad Lake 2020.jpg", "10:15:00",
             "Attabad Lake from the road. Deep blue green water between bare rock slopes. "
             "No ice anywhere near the water."),
            ("File:Ghulkin Glacier.jpg", "12:00:00",
             "Ghulkin glacier from the viewpoint. The lower ice is covered in grey rubble. "
             "I can't see a lake at the snout from here."),
            ("File:Borith Lake in Hunza.jpg", "13:30:00",
             "Borith Lake. Small lake with green grass along the shore. The ridge behind it "
             "is bare brown rock."),
            ("File:Borith Lake by Azim Tajik.jpg", "13:55:00", None),
            ("File:Passu Glacier.jpg", "15:00:00",
             "Passu glacier. A big white ice tongue full of cracks comes down the valley. "
             "There is meltwater at the bottom but no proper lake."),
            (None, "16:10:00",
             "Walking back by the river. Passed a small muddy pond next to the road. "
             "No ice anywhere near it."),
        ],
    },
    "test-skardu": {
        "date": "2026:10:08",
        "about": "Satpara and the Kachura lakes near Skardu, Baltistan, then Machulu village.",
        "stops": [
            ("File:Sadpara Lake and road.jpg", "09:00:00", None),
            ("File:Turquoise Sadpara lake.jpg", "09:40:00",
             "Satpara Lake. There is a concrete dam at the lower end of the lake, behind me. "
             "The water is bright turquoise."),
            ("File:Beauty - Uppaer Kachura Lake Sakardu.jpg", "11:30:00", None),
            ("File:View of upper Kachura lake.jpg", "11:50:00", None),
            ("File:Shangrila Resorts.jpg", "12:40:00", None),
            ("File:Machulu baltistan.jpg", "15:30:00", None),
        ],
    },
}


def _get(params: dict) -> dict:
    url = API + "?" + urllib.parse.urlencode({**params, "format": "json"})
    return json.loads(_fetch(url).decode("utf-8"))


def _fetch(url: str) -> bytes:
    for attempt in range(5):
        time.sleep(1.5 * (2 ** attempt))
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except urllib.error.HTTPError as exc:
            if exc.code != 429:
                raise
    raise RuntimeError(f"rate-limited: {url}")


def _plain(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def info(title: str) -> dict:
    pages = _get({"action": "query", "titles": title, "prop": "imageinfo",
                  "iiprop": "url|extmetadata", "iiurlwidth": 1280})["query"]["pages"]
    i = next(iter(pages.values()))["imageinfo"][0]
    m = i["extmetadata"]
    val = lambda k: _plain(m.get(k, {}).get("value", ""))  # noqa: E731
    return {"thumb": i["thumburl"], "page": i["descriptionurl"],
            "licence": val("LicenseShortName"), "licence_url": val("LicenseUrl"),
            "author": val("Artist") or "unknown",
            "lat": float(val("GPSLatitude")), "lon": float(val("GPSLongitude"))}


def _dms(v: float) -> tuple:
    v = abs(v)
    d = int(v)
    m = int((v - d) * 60)
    return (float(d), float(m), round(((v - d) * 60 - m) * 60, 3))


def save_photo(data: bytes, dest: Path, when: str, lat: float, lon: float) -> None:
    with Image.open(io.BytesIO(data)) as im:
        im = im.convert("RGB")
        im.thumbnail((1600, 1600))       # the model sees at most 1024 px anyway
        exif = Image.Exif()
        exif[0x0132] = when
        exif.get_ifd(0x8769)[0x9003] = when
        exif.get_ifd(0x8825).update({1: "N" if lat >= 0 else "S", 2: _dms(lat),
                                     3: "E" if lon >= 0 else "W", 4: _dms(lon)})
        im.save(dest, "JPEG", quality=88, exif=exif)


def utc_iso(date: str, clock: str) -> str:
    h, m, s = map(int, clock.split(":"))
    h -= UTC_OFFSET_H
    return f"{date.replace(':', '-')}T{h:02d}:{m:02d}:{s:02d}Z"


def build(name: str, spec: dict) -> None:
    out = ROOT / "trips" / name
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        for n, (title, clock, words) in enumerate(spec["stops"], 1):
            stem = f"{n:02d}"
            if title:
                meta = info(title)
                slug = re.sub(r"[^a-z0-9]+", "_", title[5:].rsplit(".", 1)[0].lower()).strip("_")[:40]
                stem = f"{n:02d}_{slug}"
                save_photo(_fetch(meta["thumb"]), out / f"{stem}.jpg",
                           f"{spec['date']} {clock}", meta["lat"], meta["lon"])
                rows.append((f"{stem}.jpg", title, meta))
                print(f"  {name}: {stem}.jpg  {clock}  {meta['lat']:.4f},{meta['lon']:.4f}  {meta['licence']}")
            if words:
                # A minute after the photo, as a hiker would record it.
                hh, mm, ss = map(int, clock.split(":"))
                memo_clock = f"{hh:02d}:{mm + 1:02d}:{ss:02d}" if title else clock
                wav = Path(tmp) / "speech.wav"
                if speak(words, wav):
                    subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-y", "-i", str(wav),
                                    "-c:a", "aac", "-b:a", "64k", "-metadata",
                                    f"creation_time={utc_iso(spec['date'], memo_clock)}",
                                    str(out / f"{stem}_note.m4a")], check=True)
                    wav.unlink()
                    print(f"  {name}: {stem}_note.m4a  {memo_clock}")

    lines = [f"# {name}: test day assembled from internet photos", "",
             spec["about"], "",
             "**Test data, not a hike.** The photos are real and so are the camera positions "
             "(from each file page), written into the EXIF. The clock times are invented to put "
             "the stops in route order on one day, and the voice notes were written to describe "
             "each photo and read by a speech engine. Built by `tools/make_internet_days.py`.", "",
             "| file | original | author | licence |", "|---|---|---|---|"]
    for f, title, m in rows:
        lic = f"[{m['licence']}]({m['licence_url']})" if m["licence_url"] else m["licence"]
        author = m["author"].replace("|", "/").replace("\n", " ")
        lines.append(f"| {f} | [{title}]({m['page']}) | {author} | {lic} |")
    lines += ["", "Photos resized to 1280 px wide. Licences as stated on each file page."]
    (out / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    for name, spec in DAYS.items():
        build(name, spec)
    return 0


if __name__ == "__main__":
    sys.exit(main())
