"""Download the evaluation photos from Wikimedia, once, with attribution.

    python eval/fetch_photos.py            # writes eval/photos/*.jpg + ATTRIBUTION.md

This is the only part of the project that uses the internet, and it is a build
step, not part of processing a hike. Only freely licensed files are kept
(CC0, public domain, CC BY, CC BY-SA), and each one's author, licence and
source page are written to eval/photos/ATTRIBUTION.md as the licences require.

Each photo is the lead image of a Wikipedia article about a lake, looked up
through the English Wikipedia API (which also serves the licence metadata of
Commons files) and downloaded from upload.wikimedia.org. The lakes are chosen
for what they show: glacier contact, icebergs, a moraine dam, or nothing
glacial at all (the negative controls).
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
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "photos"
UA = ("LakeLookout/0.1 (open-source hackathon project; one-off download of "
      "evaluation photos)")
API = "https://en.wikipedia.org/w/api.php"
FREE = re.compile(r"^(cc0|public domain|pd|cc by(-sa)? [0-9.]+)", re.I)
PAUSE_S = 2.0

# slug -> Wikipedia article whose lead image is used
ARTICLES = {
    "imja_tsho": "Imja Tsho",
    "tsho_rolpa": "Tsho Rolpa",
    "gokyo": "Gokyo Lakes",
    "palcacocha": "Lake Palcacocha",
    "jokulsarlon": "Jökulsárlón",
    "tasman": "Tasman Glacier",
    "mueller": "Mueller Glacier",
    "saiful_muluk": "Lake Saiful Muluk",
    "attabad": "Attabad Lake",
    "rawal": "Rawal Lake",
    "pond": "Pond",
    "reservoir": "Reservoir",
}


def _fetch(url: str, timeout: float = 60) -> bytes:
    """GET with a pause before every request and back-off on HTTP 429."""
    for attempt in range(5):
        time.sleep(PAUSE_S * (2 ** attempt))
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as exc:
            if exc.code != 429:
                raise
    raise RuntimeError(f"still rate-limited after 5 attempts: {url}")


def _get(params: dict) -> dict:
    url = API + "?" + urllib.parse.urlencode({**params, "format": "json"})
    return json.loads(_fetch(url).decode("utf-8"))


def _plain(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def find(article: str) -> dict | None:
    pages = _get({"action": "query", "titles": article, "redirects": 1,
                  "prop": "pageimages", "piprop": "name"})["query"]["pages"]
    name = next(iter(pages.values())).get("pageimage")
    if not name:
        return None
    info_pages = _get({"action": "query", "titles": f"File:{name}",
                       "prop": "imageinfo", "iiprop": "url|extmetadata|mime",
                       "iiurlwidth": 1280})["query"]["pages"]
    info = (next(iter(info_pages.values())).get("imageinfo") or [{}])[0]
    meta = info.get("extmetadata", {})
    licence = _plain(meta.get("LicenseShortName", {}).get("value", ""))
    if info.get("mime") != "image/jpeg" or not FREE.match(licence):
        print(f"    skipped {name}: {info.get('mime')} / {licence or 'no licence'}")
        return None
    return {"title": f"File:{name}", "thumb": info.get("thumburl") or info["url"],
            "page": info.get("descriptionurl", ""), "licence": licence,
            "licence_url": _plain(meta.get("LicenseUrl", {}).get("value", "")),
            "author": _plain(meta.get("Artist", {}).get("value", "")) or "unknown"}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for slug, article in ARTICLES.items():
        hit = find(article)
        if not hit:
            print(f"  {slug}: no freely licensed JPEG lead image")
            continue
        dest = OUT / f"{slug}.jpg"
        if not dest.exists():
            dest.write_bytes(_fetch(hit["thumb"], timeout=120))
        rows.append((slug, hit))
        print(f"  {slug}: {hit['title']} ({hit['licence']})")

    lines = ["# Evaluation photo attribution", "",
             "All photos are from Wikimedia Commons, resized to 1280 px wide. "
             "Licences as stated on each file page.", "",
             "| file | original | author | licence |", "|---|---|---|---|"]
    for slug, h in rows:
        lic = f"[{h['licence']}]({h['licence_url']})" if h["licence_url"] else h["licence"]
        author = h["author"].replace("|", "/").replace("\n", " ")
        lines.append(f"| {slug}.jpg | [{h['title']}]({h['page']}) | {author} | {lic} |")
    (OUT / "ATTRIBUTION.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {len(rows)} photos and ATTRIBUTION.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
