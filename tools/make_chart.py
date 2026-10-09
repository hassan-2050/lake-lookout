"""The prompt-iteration chart for the write-up, drawn from eval/results/.

    python tools/make_chart.py        # -> docs/post/09-iterations.png

Two small multiples on their own zero-based axes (never one chart with two
y-scales): false "no" answers, and accuracy, for each measured version. The
numbers are read from the result files, so the picture cannot drift from them.
"""
from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "eval" / "results"
OUT = ROOT / "docs" / "post" / "09-iterations.png"

VERSIONS = [  # file stem, short name
    ("v1-baseline", "answer first"),
    ("v2-evidence-first", "evidence first"),
    ("v3-scope", "in-view questions"),
    ("v4-final", "final prompt"),
    ("v5", "+ bug fixes"),
]
BAR = "#00869b"            # passes the palette validator on the light surface
SURFACE, GRID = "#fcfcfb", "#e6e5df"
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#7a7972"


def load() -> list[dict]:
    rows = []
    for stem, name in VERSIONS:
        r = json.loads((RESULTS / f"{stem}_gemma4-e4b.json").read_text(encoding="utf-8"))
        rows.append({"v": stem.split("-")[0], "name": name,
                     "false_no": r["counts"]["false_no"], "acc": round(r["accuracy"] * 100)})
    return rows


def panel(rows, key, top, ticks, title, fmt, label_idx, x0, w=520, h=300):
    """One column chart: zero baseline, hairline grid, 4px rounded tops."""
    pad_l, pad_b, pad_t = 44, 54, 34
    pw, ph = w - pad_l - 10, h - pad_b - pad_t
    band = pw / len(rows)
    bw = min(24 * 1.6, band * 0.42)
    y = lambda v: pad_t + ph - v / top * ph  # noqa: E731
    g = [f'<g transform="translate({x0},0)">',
         f'<text x="{pad_l}" y="18" font-size="15" font-weight="650" fill="{INK}">{title}</text>']
    for t in ticks:
        g.append(f'<line x1="{pad_l}" x2="{pad_l + pw}" y1="{y(t):.1f}" y2="{y(t):.1f}" stroke="{GRID}" stroke-width="1"/>')
        g.append(f'<text x="{pad_l - 8}" y="{y(t) + 4:.1f}" font-size="12" text-anchor="end" fill="{MUTED}">{fmt(t)}</text>')
    for i, r in enumerate(rows):
        cx = pad_l + band * i + band / 2
        v = r[key]
        top_y, base = y(v), y(0)
        rad = min(4, base - top_y)
        # rounded data end, square at the baseline
        g.append(f'<path d="M{cx - bw / 2:.1f},{base:.1f} V{top_y + rad:.1f} Q{cx - bw / 2:.1f},{top_y:.1f} {cx - bw / 2 + rad:.1f},{top_y:.1f} '
                 f'H{cx + bw / 2 - rad:.1f} Q{cx + bw / 2:.1f},{top_y:.1f} {cx + bw / 2:.1f},{top_y + rad:.1f} V{base:.1f} Z" fill="{BAR}"/>')
        if i in label_idx:
            g.append(f'<text x="{cx:.1f}" y="{top_y - 7:.1f}" font-size="13" font-weight="650" text-anchor="middle" fill="{INK}">{fmt(v)}</text>')
        g.append(f'<text x="{cx:.1f}" y="{pad_t + ph + 18:.1f}" font-size="12.5" font-weight="650" text-anchor="middle" fill="{INK2}">{r["v"]}</text>')
        g.append(f'<text x="{cx:.1f}" y="{pad_t + ph + 34:.1f}" font-size="11.5" text-anchor="middle" fill="{MUTED}">{r["name"]}</text>')
    g.append(f'<line x1="{pad_l}" x2="{pad_l + pw}" y1="{y(0):.1f}" y2="{y(0):.1f}" stroke="{INK2}" stroke-width="1"/>')
    g.append("</g>")
    return "".join(g)


def main() -> int:
    rows = load()
    peak = max(range(len(rows)), key=lambda i: rows[i]["false_no"])
    left = panel(rows, "false_no", 20, [0, 5, 10, 15, 20], "False “no” answers (lower is better)",
                 lambda v: f"{v}", {0, peak, len(rows) - 1}, 0)
    best = max(range(len(rows)), key=lambda i: rows[i]["acc"])
    right = panel(rows, "acc", 100, [0, 25, 50, 75, 100], "Accuracy against the labels",
                  lambda v: f"{v}%", {0, peak, best, len(rows) - 1}, 560)
    html = f"""<!doctype html><html><head><meta charset="utf-8"><style>
      body{{margin:0;background:{SURFACE};font-family:system-ui,"Segoe UI",sans-serif}}
      .wrap{{padding:22px 26px 16px}} h1{{font-size:19px;margin:0 0 4px;color:{INK}}}
      p{{margin:0 0 14px;font-size:13.5px;color:{INK2};max-width:1040px;line-height:1.45}}
      .foot{{font-size:11.5px;color:{MUTED};margin:6px 0 0}}</style></head><body><div class="wrap">
      <h1>Five measured versions of the checklist</h1>
      <p>gemma4:e4b on 11 labelled lake photos, 91 scored answers per version. Putting evidence first ended
         unsupported answers, then made the model claim absence for things out of view, until the
         in-view questions in v3.</p>
      <svg width="1100" height="300" viewBox="0 0 1100 300" font-family="system-ui,Segoe UI,sans-serif">{left}{right}</svg>
      <p class="foot">Source: eval/results/ in the Lake Lookout repo. Small sample; a few points move between runs.</p>
    </div></body></html>"""
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True)
        page = b.new_page(viewport={"width": 1150, "height": 440}, device_scale_factor=2)
        page.set_content(html)
        page.screenshot(path=str(OUT), full_page=True)
        b.close()
    print(f"wrote {OUT.relative_to(ROOT)}")
    for r in rows:
        print(f"  {r['v']:3s} {r['name']:18s} false no {r['false_no']:2d}  accuracy {r['acc']}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
