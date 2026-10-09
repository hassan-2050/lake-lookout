"""Score models on the labelled evaluation photos.

    python eval/run_eval.py --tag v2 --models gemma4:e4b gemma4:e2b gemma3:4b
    python eval/run_eval.py --tag v2-cpu --models gemma4:e2b --cpu

Each photo is sent alone (no voice note), exactly as a stop is processed, and
the VERIFIED answers are scored against eval/labels.json. Items labelled "skip"
are not scored.

What is counted, and why:
  accuracy      answer equals the label
  false yes     said yes where the label is no or unclear: an invented feature
  false no      said no where the label is yes or unclear: a dismissed feature,
                or an absence claimed for something out of view
  too cautious  said unclear where the label is yes or no
  rejected      answers the verifier turned into unclear for lack of support
Latency is the median over warm calls (the first call, which loads the model,
is excluded) and is split into prompt processing and generation.

The labels were drafted by the coding agent and are marked unreviewed until a
person checks them (labels.json: reviewed_by_human). With 11 photos the numbers
are indicative, and the README says so.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lookout import checklist, gemma  # noqa: E402
from lookout.offline import offline  # noqa: E402
from lookout.verify import verify  # noqa: E402

HERE = Path(__file__).resolve().parent


SCOPE_ITEMS = {i.id for i in checklist.ITEMS if any(j.needs == i.id for j in checklist.ITEMS)}


def score(model: str, labels: dict, cpu: bool) -> dict:
    """Headline counts cover the observation items only. The scope items
    (is the dam / downstream in view?) arrived in v3, so they are scored
    separately to keep runs comparable."""
    per_photo, latency = {}, []
    counts = {"scored": 0, "correct": 0, "false_yes": 0, "false_no": 0,
              "too_cautious": 0, "rejected": 0}
    scope = {"scored": 0, "correct": 0}
    for n, (slug, entry) in enumerate(labels["photos"].items()):
        img = gemma.image_b64(HERE / "photos" / f"{slug}.jpg")
        r = gemma.checklist(checklist.prompt(None, 1), [img], checklist.json_schema(),
                            model=model, cpu=cpu)
        checked, down = verify(r["raw"], has_photo=True, has_voice=False)
        if n > 0:
            latency.append(r["timings"])
        counts["rejected"] += len(down)
        rows = {}
        for item, want in entry["labels"].items():
            got = checked[item]["answer"]
            rows[item] = {"label": want, "answer": got,
                          "evidence": checked[item]["evidence"]}
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
        per_photo[slug] = {"kind": entry["kind"], "items": rows, "downgrades": down,
                           "summary": checked["summary"], "timings": r["timings"]}
        print(f"    {slug:12s} " + " ".join(
            f"{'.' if v['label'] == 'skip' else ('=' if v['answer'] == v['label'] else v['answer'][0])}"
            for v in rows.values()))

    def med(key):
        return round(statistics.median(t[key] for t in latency), 2) if latency else None

    return {"model": model, "cpu_only": cpu, "counts": counts,
            "accuracy": round(counts["correct"] / counts["scored"], 3),
            "scope_accuracy": (round(scope["correct"] / scope["scored"], 3)
                               if scope["scored"] else None),
            "latency_s": {"total": med("total_s"), "prompt": med("prompt_s"),
                          "generate": med("generate_s")},
            "photos": per_photo}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--models", nargs="+", default=[gemma.DEFAULT_MODEL])
    p.add_argument("--tag", required=True, help="name for this run, e.g. v2")
    p.add_argument("--cpu", action="store_true")
    args = p.parse_args(argv)

    labels = json.loads((HERE / "labels.json").read_text(encoding="utf-8"))
    out_dir = HERE / "results"
    out_dir.mkdir(exist_ok=True)
    print("legend: '=' matches label, '.' not scored, y/n/u = wrong answer given")
    summary = []
    with offline():
        for model in args.models:
            print(f"  {model}{' (CPU only)' if args.cpu else ''}")
            res = score(model, labels, args.cpu)
            res["labels_reviewed_by_human"] = labels.get("reviewed_by_human", False)
            name = f"{args.tag}_{model.replace(':', '-')}.json"
            (out_dir / name).write_text(json.dumps(res, ensure_ascii=False, indent=1),
                                        encoding="utf-8")
            summary.append(res)

    head = ("| model | accuracy | false yes | false no | too cautious | rejected | "
            "in-view questions | warm latency (prompt + generate) |")
    lines = [f"## {args.tag}{' (CPU only)' if args.cpu else ''}", "",
             f"{summary[0]['counts']['scored']} scored observation answers over "
             f"{len(labels['photos'])} photos. Labels reviewed by a person: "
             f"{'yes' if labels.get('reviewed_by_human') else 'not yet'}.", "",
             head, "|---|---|---|---|---|---|---|---|"]
    for r in summary:
        c, lat = r["counts"], r["latency_s"]
        sc = f"{r['scope_accuracy']:.0%}" if r["scope_accuracy"] is not None else "-"
        lines.append(f"| {r['model']} | {r['accuracy']:.0%} | {c['false_yes']} | "
                     f"{c['false_no']} | {c['too_cautious']} | {c['rejected']} | {sc} | "
                     f"{lat['total']} s ({lat['prompt']} + {lat['generate']}) |")
    table = "\n".join(lines) + "\n"
    (out_dir / f"{args.tag}.md").write_text(table, encoding="utf-8")
    print()
    print(table)
    return 0


if __name__ == "__main__":
    sys.exit(main())
