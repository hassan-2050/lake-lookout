"""Deterministic checks on the model's checklist, applied after every call.

The model is constrained to the right SHAPE by the JSON schema, but shape is
not support. These rules decide what the log is allowed to claim:

* A yes or a no must name its evidence. An answer with no evidence becomes
  "unclear". A "no" is included on purpose: an unsupported "no" is the more
  dangerous error, because a blank that reads as "nothing there" never looks
  like a failure.
* An answer cannot cite a source that does not exist for this stop. Claiming
  the voice note when there was no voice note, or a photo when there was none,
  is a fabrication, and the answer becomes "unclear".
* A field the model skipped becomes "unclear", never "no".

Every downgrade is recorded with its reason, so the log shows what the model
said as well as what was kept.
"""
from __future__ import annotations

from .checklist import ANSWERS, ITEM_IDS

# Evidence strings that say nothing. Compared after lower-casing and stripping
# punctuation.
_EMPTY_EVIDENCE = {"", "n/a", "na", "none", "nothing", "unknown", "not visible",
                   "not applicable", "-", "unclear"}


def _is_empty(evidence: str) -> bool:
    return evidence.strip().lower().strip(".!:;,") in _EMPTY_EVIDENCE


def verify(raw: dict, *, has_photo: bool, has_voice: bool) -> tuple[dict, list[dict]]:
    """Return (checked answers, downgrades).

    `checked` maps each item id to {answer, evidence, source}, plus "summary".
    `downgrades` lists {item, model_answer, reason} for every answer changed.
    """
    checked: dict = {}
    downgrades: list[dict] = []
    for item in ITEM_IDS:
        entry = raw.get(item)
        if not isinstance(entry, dict):
            checked[item] = {"answer": "unclear", "evidence": "", "source": "none"}
            downgrades.append({"item": item, "model_answer": None,
                               "reason": "model did not answer"})
            continue

        answer = str(entry.get("answer", "")).strip().lower()
        evidence = str(entry.get("evidence", "")).strip()
        source = str(entry.get("source", "none")).strip().lower()
        reason = None

        if answer not in ANSWERS:
            reason = f"answer {answer!r} is not yes/no/unclear"
        elif answer != "unclear":
            if _is_empty(evidence):
                reason = f"'{answer}' given with no evidence"
            elif source in ("none", ""):
                reason = f"'{answer}' given with no source"
            elif source in ("voice", "both") and not has_voice:
                reason = "cites a voice note this stop does not have"
            elif source in ("photo", "both") and not has_photo:
                reason = "cites a photo this stop does not have"

        if reason:
            downgrades.append({"item": item, "model_answer": answer,
                               "reason": reason})
            checked[item] = {"answer": "unclear", "evidence": evidence,
                             "source": "none"}
        else:
            checked[item] = {"answer": answer, "evidence": evidence,
                             "source": source if answer != "unclear" else "none"}

    checked["summary"] = str(raw.get("summary", "")).strip()
    return checked, downgrades
