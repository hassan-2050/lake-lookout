"""Re-score every saved evaluation result against the current labels.

    python eval/rescore.py

The model's answers are kept in eval/results/<tag>_<model>.json; only the
labels changed. This re-grades those saved answers with eval/labels.json and
rewrites each file's counts and each tag's .md table, so a label correction
updates every version and model without re-running anything. Counting rules
are the same as run_eval.py's (scope items are scored separately).
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
from run_eval import SCOPE_ITEMS  # noqa: E402


def rescore(result: dict, labels: dict) -> dict:
    counts = {"scored": 0, "correct": 0, "false_yes": 0, "false_no": 0,
              "too_cautious": 0, "rejected": result["counts"].get("rejected", 0)}
    scope = {"scored": 0, "correct": 0}
    for slug, photo in result["photos"].items():
        want_all = labels["photos"][slug]["labels"]
        for item, row in photo["items"].items():
            want = want_all.get(item, "skip")
            row["label"] = want
            got = row["answer"]
            if want == "skip":
                continue
            if item in SCOPE_ITEMS:
                scope["scored"] += 1
                scope["correct"] += got == want
                continue
            counts["scored"] += 1
            if got == want:
                counts["correct"] += 1
            elif got == "yes":
                counts["false_yes"] += 1
            elif got == "no":
                counts["false_no"] += 1
            else:
                counts["too_cautious"] += 1
    result["counts"] = counts
    result["accuracy"] = round(counts["correct"] / counts["scored"], 3)
    if scope["scored"]:
        result["scope_accuracy"] = round(scope["correct"] / scope["scored"], 3)
    result["labels_second_pass"] = labels.get("second_pass", {}).get("date")
    result["labels_reviewed_by_human"] = labels.get("reviewed_by_human", False)
    return result


def table(tag: str, results: list[dict], labels: dict) -> str:
    cpu = any(r.get("cpu_only") for r in results)
    lines = [f"## {tag}{' (CPU only)' if cpu else ''}", "",
             f"{results[0]['counts']['scored']} scored observation answers over "
             f"{len(labels['photos'])} photos. Labels: drafted by the coding agent and re-checked by it in a "
             f"second pass; not independently reviewed by a person.", "",
             "| model | accuracy | false yes | false no | too cautious | rejected | in-view questions | "
             "warm latency (prompt + generate) |", "|---|---|---|---|---|---|---|---|"]
    for r in results:
        c, lat = r["counts"], r["latency_s"]
        sc = f"{r['scope_accuracy']:.0%}" if r.get("scope_accuracy") is not None else "-"
        lines.append(f"| {r['model']} | {r['accuracy']:.0%} | {c['false_yes']} | {c['false_no']} | "
                     f"{c['too_cautious']} | {c['rejected']} | {sc} | "
                     f"{lat['total']} s ({lat['prompt']} + {lat['generate']}) |")
    return "\n".join(lines) + "\n"


def main() -> int:
    labels = json.loads((HERE / "labels.json").read_text(encoding="utf-8"))
    by_tag = defaultdict(list)
    for f in sorted((HERE / "results").glob("*_*.json")):
        r = rescore(json.loads(f.read_text(encoding="utf-8")), labels)
        f.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
        tag = f.stem.rsplit("_", 1)[0]
        by_tag[tag].append(r)
        c = r["counts"]
        print(f"{f.stem:32s} accuracy {r['accuracy']:.1%}  false yes {c['false_yes']:2d}  "
              f"false no {c['false_no']:2d}  cautious {c['too_cautious']:2d}  scored {c['scored']}")
    for tag, results in by_tag.items():
        (HERE / "results" / f"{tag}.md").write_text(table(tag, results, labels), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
