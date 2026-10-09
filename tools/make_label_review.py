"""Build the label review page from eval/labels.json.

    python tools/make_label_review.py              # -> eval/label-review.html (open it directly)
    python tools/make_label_review.py --artifact   # -> body-only copy for a claude.ai page

One card per evaluation photo with its 13 answers (yes / no / unclear / skip),
starting from the current labels. Opened directly it works on its own and
offers "Copy answers"; published as a claude.ai page that declares the `db`
capability, answers save as you click (one document per photo in `reviews`).
Photos are read from eval/photos/, next to the output.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lookout import checklist  # noqa: E402

TEMPLATE = ROOT / "tools" / "label_review_template.html"
OUT = ROOT / "eval" / "label-review.html"


def data() -> str:
    labels = json.loads((ROOT / "eval" / "labels.json").read_text(encoding="utf-8"))
    photos = [{"slug": s, "kind": e["kind"], "note": e["note"], "labels": e["labels"]}
              for s, e in labels["photos"].items()]
    items = [{"id": i.id, "label": i.label, "question": i.question,
              "scope": any(j.needs == i.id for j in checklist.ITEMS)} for i in checklist.ITEMS]
    # "</" is escaped so the JSON cannot close its <script> element.
    return json.dumps({"photos": photos, "items": items}, ensure_ascii=False).replace("</", "<" + "\\" + "/")


def main() -> int:
    body = TEMPLATE.read_text(encoding="utf-8").replace("__DATA__", data())
    if "--artifact" in sys.argv:
        out = OUT.with_name("label-review.artifact.html")
        out.write_text(body, encoding="utf-8")
    else:
        out = OUT
        out.write_text("<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">\n"
                       "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n"
                       "</head><body style=\"margin:0\">\n" + body + "\n</body></html>\n", encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
