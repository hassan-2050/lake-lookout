"""List freely licensed, geotagged photos from Wikipedia lake and glacier articles.

    python tools/find_test_photos.py > candidates.json

A build-time helper for assembling realistic test days from internet photos.
For each article it lists every JPEG the article uses, keeps only freely
licensed ones (CC0, public domain, CC BY, CC BY-SA) whose file page records a
camera location, and prints title, licence, author, coordinates, size and the
image URL. Choosing which ones become a test day is done by hand, by looking
at them: see tools/make_internet_days.py.

Commons itself is unreachable from some networks, so this goes through the
English Wikipedia API, which serves Commons file metadata too.
"""
from __future__ import annotations

import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

UA = ("LakeLookout/0.1 (open-source hackathon project; one-off search for "
      "freely licensed test photos)")
API = "https://en.wikipedia.org/w/api.php"
FREE = re.compile(r"^(cc0|public domain|pd|cc by(-sa)? [0-9.]+)", re.I)

ARTICLES = {
    "hunza": ["Attabad Lake", "Borith Lake", "Passu Glacier", "Batura Glacier",
              "Hopper Glacier", "Rush Lake", "Passu Cones", "Hunza Valley"],
    "khumbu": ["Gokyo Lakes", "Imja Tsho", "Ngozumpa Glacier", "Khumbu Glacier",
               "Chola Tsho", "Gokyo Ri", "Dingboche", "Thame, Nepal"],
    "baltistan": ["Satpara Lake", "Sheosar Lake", "Deosai National Park", "Rama Lake",
                  "Naltar Valley", "Upper Kachura Lake", "Lower Kachura Lake",
                  "Fairy Meadows", "Nanga Parbat", "Lulusar Lake", "Saiful Muluk"],
    "nepal_more": ["Tsho Rolpa", "Rolwaling Valley", "Tilicho Lake", "Rara Lake",
                   "Gosaikunda", "Phoksundo Lake", "Annapurna Base Camp", "Langtang Valley"],
    "andes": ["Laguna 69", "Laguna Parón", "Llanganuco Lakes", "Huascarán National Park",
              "Pastoruri Glacier", "Laguna Churup"],
}

if len(sys.argv) > 1:          # restrict to the named regions
    ARTICLES = {k: v for k, v in ARTICLES.items() if k in sys.argv[1:]}


def _get(params: dict) -> dict:
    url = API + "?" + urllib.parse.urlencode({**params, "format": "json"})
    for attempt in range(5):
        time.sleep(1.5 * (2 ** attempt))
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code != 429:
                raise
    raise RuntimeError("rate-limited")


def _plain(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def files_in(article: str) -> list[str]:
    pages = _get({"action": "query", "titles": article, "redirects": 1,
                  "prop": "images", "imlimit": 60})["query"]["pages"]
    imgs = next(iter(pages.values())).get("images", [])
    return [i["title"] for i in imgs if i["title"].lower().endswith((".jpg", ".jpeg"))]


def describe(titles: list[str]) -> list[dict]:
    out = []
    for i in range(0, len(titles), 40):
        pages = _get({"action": "query", "titles": "|".join(titles[i:i + 40]),
                      "prop": "imageinfo", "iiprop": "url|extmetadata|mime|size",
                      "iiurlwidth": 2048})["query"]["pages"]
        for p in pages.values():
            info = (p.get("imageinfo") or [{}])[0]
            m = info.get("extmetadata", {})
            val = lambda k: _plain(m.get(k, {}).get("value", ""))  # noqa: E731
            lic = val("LicenseShortName")
            lat, lon = val("GPSLatitude"), val("GPSLongitude")
            if info.get("mime") != "image/jpeg" or not FREE.match(lic) or not (lat and lon):
                continue
            out.append({"title": p["title"], "licence": lic,
                        "licence_url": val("LicenseUrl"), "author": val("Artist") or "unknown",
                        "lat": float(lat), "lon": float(lon),
                        "taken": val("DateTimeOriginal"), "width": info.get("width"),
                        "height": info.get("height"), "bytes": info.get("size"),
                        "thumb": info.get("thumburl"), "page": info.get("descriptionurl"),
                        "description": val("ImageDescription")[:200]})
    return out


def main() -> int:
    result = {}
    for region, articles in ARTICLES.items():
        seen, found = set(), []
        for a in articles:
            titles = [t for t in files_in(a) if t not in seen]
            seen.update(titles)
            for d in describe(titles):
                d["article"] = a
                found.append(d)
        result[region] = found
        print(f"{region}: {len(found)} geotagged free photos", file=sys.stderr)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
