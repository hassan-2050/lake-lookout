"""Write a processed day as field_log.csv, field_log.geojson and trip.html.

trip.html is one self-contained file: thumbnails are inlined, the route is an
inline SVG, and there are no external scripts, fonts or map tiles. It opens by
double-clicking with the network off, which is the point: the evening this is
read is usually the evening with no signal.

Every stop appears, including stops whose processing failed. A failed stop
shows the error, never an empty checklist, because an empty checklist reads as
"nothing seen".
"""
from __future__ import annotations

import base64
import csv
import html
import io
import json
import math
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageOps

from .checklist import BY_ID, ITEM_IDS, ITEMS

THUMB_SIDE = 420


def _esc(v) -> str:
    return html.escape("" if v is None else str(v))


def thumbnail_data_uri(path: Path, side: int = THUMB_SIDE) -> str:
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        im.thumbnail((side, side))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=80)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _metres(a, b) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


# --- CSV and GeoJSON --------------------------------------------------------

def _flat(stop: dict) -> dict:
    row = {
        "stop": stop["id"], "time_local": stop["time_local"],
        "lat": stop["lat"], "lon": stop["lon"], "alt_m": stop["alt_m"],
        "photos": ";".join(stop["photos"]),
        "memos": ";".join(m["name"] for m in stop["memos"]),
        "transcript": stop.get("transcript", ""),
        "summary": (stop.get("checklist") or {}).get("summary", ""),
    }
    cl = stop.get("checklist") or {}
    for item in ITEM_IDS:
        a = cl.get(item) or {}
        row[item] = a.get("answer", "")
        row[f"{item}_evidence"] = a.get("evidence", "")
        row[f"{item}_source"] = a.get("source", "")
    row["downgrades"] = len(stop.get("downgrades") or [])
    row["error"] = stop.get("error") or ""
    return row


def write_csv(stops: list[dict], path: Path) -> None:
    rows = [_flat(s) for s in stops]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["stop"])
        w.writeheader()
        w.writerows(rows)


def write_geojson(stops: list[dict], path: Path) -> None:
    features = []
    for s in stops:
        if s["lat"] is None or s["lon"] is None:
            continue
        props = _flat(s)
        for k in ("lat", "lon"):
            props.pop(k)
        features.append({"type": "Feature",
                         "geometry": {"type": "Point", "coordinates": [s["lon"], s["lat"]]},
                         "properties": props})
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features},
                               ensure_ascii=False, indent=1), encoding="utf-8")


# --- trip.html --------------------------------------------------------------

def _route_svg(stops: list[dict]) -> tuple[str, float]:
    pts = [(s["lat"], s["lon"], s["id"]) for s in stops
           if s["lat"] is not None and s["lon"] is not None]
    if not pts:
        return "", 0.0
    dist = sum(_metres(pts[i][:2], pts[i + 1][:2]) for i in range(len(pts) - 1))
    w, h, pad = 640, 300, 36
    lat0 = sum(p[0] for p in pts) / len(pts)
    k = math.cos(math.radians(lat0))
    xs = [p[1] * k for p in pts]
    ys = [p[0] for p in pts]
    span = max(max(xs) - min(xs), max(ys) - min(ys), 1e-6)
    scale = min((w - 2 * pad), (h - 2 * pad)) / span
    cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2

    def xy(i):
        return (w / 2 + (xs[i] - cx) * scale, h / 2 - (ys[i] - cy) * scale)

    coords = [xy(i) for i in range(len(pts))]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    marks = "".join(
        f'<g><circle cx="{x:.1f}" cy="{y:.1f}" r="11" class="pt"/>'
        f'<text x="{x:.1f}" y="{y + 4:.1f}" class="pl">{_esc(p[2][1:])}</text></g>'
        for (x, y), p in zip(coords, pts))
    svg = (f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Route between stops">'
           f'<polyline points="{line}" class="route"/>{marks}</svg>')
    return svg, dist


def _chip(answer: str) -> str:
    return f'<span class="chip {answer or "none"}">{_esc(answer or "-")}</span>'


def _card(stop: dict, thumbs: list[str]) -> str:
    where = (f'{stop["lat"]:.5f}, {stop["lon"]:.5f}'
             + (f' · {stop["alt_m"]:.0f} m' if stop["alt_m"] is not None else "")
             if stop["lat"] is not None else "no location in photo")
    bits = [f'{len(stop["photos"])} photo(s)' if stop["photos"] else "no photo",
            f'{len(stop["memos"])} voice note(s)' if stop["memos"] else "no voice note"]
    imgs = "".join(f'<img src="{t}" alt="photo from stop {_esc(stop["id"])}">'
                   for t in thumbs)
    out = [f'<article class="stop" id="{_esc(stop["id"])}">',
           f'<header><h2>{_esc(stop["id"])}</h2><p>{_esc(stop["time_local"])} · '
           f'{_esc(where)} · {_esc(", ".join(bits))}</p></header>']
    if imgs:
        out.append(f'<div class="thumbs">{imgs}</div>')
    if stop.get("transcript"):
        out.append(f'<blockquote>{_esc(stop["transcript"])}</blockquote>')
    if stop.get("error"):
        out.append(f'<p class="error">Not processed: {_esc(stop["error"])}</p></article>')
        return "".join(out)

    cl = stop["checklist"]
    if cl.get("summary"):
        out.append(f'<p class="summary">{_esc(cl["summary"])}</p>')
    rows = []
    for item in ITEMS:
        a = cl.get(item.id) or {}
        ev = _esc(a.get("evidence", "")) if a.get("answer") != "unclear" else ""
        src = _esc(a.get("source", "")) if a.get("answer") != "unclear" else ""
        rows.append(f'<tr><th scope="row">{_esc(item.label)}'
                    f'<small>{_esc(item.source)}</small></th>'
                    f'<td>{_chip(a.get("answer", ""))}</td><td>{ev}'
                    f'{f" <em>({src})</em>" if src else ""}</td></tr>')
    out.append('<table><thead><tr><th>Observation</th><th>Answer</th>'
               '<th>Evidence</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table>")
    if stop.get("downgrades"):
        items = "".join(
            f'<li>{_esc(BY_ID[d["item"]].label)}: model said '
            f'<b>{_esc(d["model_answer"] or "nothing")}</b>, kept as unclear '
            f'({_esc(d["reason"])})</li>' for d in stop["downgrades"])
        out.append(f'<details><summary>{len(stop["downgrades"])} answer(s) '
                   f'not supported, changed to unclear</summary><ul>{items}</ul></details>')
    out.append("</article>")
    return "".join(out)


CSS = """
:root{--bg:#f6f5f1;--card:#fff;--ink:#1d2321;--muted:#5d6763;--line:#dcdcd5;
--yes:#1f6f5c;--yesbg:#d9efe8;--no:#4a4f63;--nobg:#e3e5ee;--unc:#7a5a12;--uncbg:#f6ebcf;
--accent:#2a6f97;--err:#9b2c2c}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#121615;--card:#1b2120;
--ink:#e6ebe8;--muted:#9aa7a2;--line:#2c3533;--yesbg:#183a31;--yes:#8fd8c1;--nobg:#262a36;
--no:#c3c8d8;--uncbg:#3a3020;--unc:#f0cf86;--accent:#7fbfe3;--err:#f19a9a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:860px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:1.6rem;margin:0 0 4px}.lede{color:var(--muted);margin:0 0 20px}
.stats{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 20px;padding:0;list-style:none}
.stats li{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:6px 10px}
.stats b{font-size:1.1rem;margin-right:4px}
svg{width:100%;height:auto;background:var(--card);border:1px solid var(--line);border-radius:10px}
.route{fill:none;stroke:var(--accent);stroke-width:2.5;stroke-dasharray:6 5}
.pt{fill:var(--accent)}.pl{fill:#fff;font:600 11px system-ui;text-anchor:middle}
.stop{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin:18px 0}
.stop header h2{margin:0;font-size:1.2rem}.stop header p{margin:2px 0 10px;color:var(--muted);font-size:.9rem}
.thumbs{display:flex;gap:8px;overflow-x:auto}.thumbs img{height:180px;border-radius:8px}
blockquote{margin:12px 0;padding:8px 12px;border-left:3px solid var(--accent);color:var(--muted)}
.summary{margin:10px 0}table{width:100%;border-collapse:collapse;font-size:.92rem}
th,td{text-align:left;vertical-align:top;padding:6px 8px;border-top:1px solid var(--line)}
th small{display:block;color:var(--muted);font-weight:400;font-size:.75rem}
td em{color:var(--muted)}.chip{display:inline-block;min-width:64px;text-align:center;
border-radius:999px;padding:1px 8px;font-weight:600;font-size:.82rem}
.chip.yes{background:var(--yesbg);color:var(--yes)}.chip.no{background:var(--nobg);color:var(--no)}
.chip.unclear,.chip.none{background:var(--uncbg);color:var(--unc)}
.error{color:var(--err);font-weight:600}details{margin-top:10px;color:var(--muted);font-size:.9rem}
footer{color:var(--muted);font-size:.85rem;margin-top:32px;border-top:1px solid var(--line);padding-top:12px}
@media (max-width:560px){.thumbs img{height:130px}th small{display:none}}
"""


def write_html(stops: list[dict], meta: dict, path: Path) -> None:
    svg, dist = _route_svg(stops)
    answers = [((s.get("checklist") or {}).get(i) or {}).get("answer")
               for s in stops if not s.get("error") for i in ITEM_IDS]
    n_photos = sum(len(s["photos"]) for s in stops)
    n_memos = sum(len(s["memos"]) for s in stops)
    stats = [(len(stops), "stops"), (n_photos, "photos"), (n_memos, "voice notes"),
             (answers.count("yes"), "yes"), (answers.count("no"), "no"),
             (answers.count("unclear"), "unclear")]
    if dist:
        stats.insert(3, (f"{dist / 1000:.1f} km", "between stops"))
    failed = sum(1 for s in stops if s.get("error"))
    if failed:
        stats.append((failed, "not processed"))
    cards = []
    for s in stops:
        thumbs = [thumbnail_data_uri(Path(p)) for p in s["photo_paths"][:3]]
        cards.append(_card(s, thumbs))

    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Lake Lookout {_esc(meta["day"])}</title><style>{CSS}</style></head><body><main>
<h1>Lake Lookout · {_esc(meta["day"])}</h1>
<p class="lede">Field log made on this computer from the day's photos and voice notes by
{_esc(meta["model"])}, running locally with no internet connection. Every answer names
its evidence; anything the model could not see is marked unclear.</p>
<ul class="stats">{"".join(f"<li><b>{_esc(v)}</b>{_esc(k)}</li>" for v, k in stats)}</ul>
{svg}
{"".join(cards)}
<footer>These are field observations, not a hazard assessment, and nothing here is an
alert. The checklist items marked with a citation correspond to published glacial-lake
hazard indicators; interpretation belongs to people qualified to make it. Processed
{_esc(meta["processed"])} in {_esc(meta["seconds"])} s. Lake Lookout {_esc(meta["version"])}.</footer>
</main></body></html>"""
    path.write_text(doc, encoding="utf-8")


def write_all(stops: list[dict], meta: dict, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {"csv": out_dir / "field_log.csv", "geojson": out_dir / "field_log.geojson",
             "html": out_dir / "trip.html", "run": out_dir / "run.json"}
    write_csv(stops, paths["csv"])
    write_geojson(stops, paths["geojson"])
    write_html(stops, meta, paths["html"])
    record = {"meta": meta, "stops": [{k: v for k, v in s.items() if k != "photo_paths"}
                                      for s in stops]}
    paths["run"].write_text(json.dumps(record, ensure_ascii=False, indent=1, default=str),
                            encoding="utf-8")
    return paths


def local_time_label(dt: datetime, zone) -> str:
    return dt.astimezone(zone).strftime("%Y-%m-%d %H:%M")
