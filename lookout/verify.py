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
* An item about the dam, or about what is downstream, can only be judged from
  a photo when that part of the scene is confirmed in view (the scope items
  dam_in_view and downstream_in_view). Otherwise only the hiker's own words can
  answer it. Without this rule the model wrote "no seepage visible" about dams
  that were behind the camera (eval/results/v2-evidence-first.md).
* Evidence attributed to the voice note must be found in the transcript and
  must be about the question (one of the item's keywords). Given a voice note,
  the model quoted one sentence about a rock ridge as the evidence for six
  unrelated answers, including "no seepage" and "no fresh rockfall".
* Evidence that says the place cannot be seen ("I can't see the far end") is
  a reason for unclear, never for a yes or no.

Every downgrade is recorded with its reason, so the log shows what the model
said as well as what was kept.
"""
from __future__ import annotations

import re

from .checklist import ANSWERS, BY_ID, ITEM_IDS, ITEMS

# Evidence strings that say nothing. Compared after lower-casing and stripping
# punctuation. "yes" and "no" are here because the model sometimes repeats the
# answer as its evidence (seen on a village photo with no water in it).
_EMPTY_EVIDENCE = {"", "n/a", "na", "none", "nothing", "unknown", "not visible",
                   "not applicable", "-", "unclear", "yes", "no"}


_CANNOT_SEE = re.compile(
    r"\b(can'?t|cannot|could ?n'?t|could not|unable to) see\b|"
    r"\bout of (view|frame|sight)\b|\bnot in (view|frame|the photo)\b")

# Fraction of the evidence's words that must occur in the transcript for a
# quote from the voice note to count as a quote.
VOICE_OVERLAP = 0.6


def _is_empty(evidence: str) -> bool:
    return evidence.strip().lower().strip(".!:;,") in _EMPTY_EVIDENCE


def _norm(text: str) -> str:
    """Lower-case with typographic apostrophes straightened; models emit both."""
    return text.lower().replace("’", "'").replace("‘", "'")


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z']{3,}", _norm(text)))


def _is_scope(item_id: str) -> bool:
    """Scope items ask whether a place is in view; 'I can't see it' answers them."""
    return any(i.needs == item_id for i in ITEMS)


def _voice_problem(item_id: str, evidence: str, transcript: str) -> str | None:
    words = _words(evidence)
    if words and len(words & _words(transcript)) / len(words) < VOICE_OVERLAP:
        return "evidence attributed to the voice note is not in the transcript"
    keywords = BY_ID[item_id].keywords
    # Matched at the start of a word, so "ice" does not match "nice" or "price"
    # and stems like "calv" still match "calving".
    text = _norm(evidence)
    if keywords and not any(re.search(r"\b" + re.escape(k), text) for k in keywords):
        return "voice evidence is not about this question"
    return None


def verify(raw: dict, *, has_photo: bool, has_voice: bool,
           transcript: str = "") -> tuple[dict, list[dict]]:
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
            elif _CANNOT_SEE.search(_norm(evidence)) and not _is_scope(item):
                reason = "the evidence says this part cannot be seen"
            elif source == "voice" and transcript:
                reason = _voice_problem(item, evidence, transcript)

        if reason:
            downgrades.append({"item": item, "model_answer": answer,
                               "reason": reason})
            checked[item] = {"answer": "unclear", "evidence": evidence,
                             "source": "none"}
        else:
            checked[item] = {"answer": answer, "evidence": evidence,
                             "source": source if answer != "unclear" else "none"}

    for item in ITEMS:
        if not item.needs:
            continue
        entry = checked[item.id]
        in_view = checked[item.needs]["answer"] == "yes"
        from_voice = entry["source"] == "voice"   # already checked against the transcript
        if entry["answer"] != "unclear" and not in_view and not from_voice:
            downgrades.append({
                "item": item.id, "model_answer": entry["answer"],
                "reason": f"'{BY_ID[item.needs].label}' is not confirmed, so this "
                          "cannot be judged from the photo"})
            checked[item.id] = {"answer": "unclear", "evidence": entry["evidence"],
                                "source": "none"}

    checked["summary"] = str(raw.get("summary", "")).strip()
    return checked, downgrades


def merge(photo: dict | None, voice: dict | None) -> tuple[dict, list[dict]]:
    """Combine the verified photo checklist and the verified voice checklist.

    The two are asked for separately because, given both at once, the model
    leaned on the voice note and stopped looking at the photo. Per item:
    one unclear -> take the other; both agree -> keep, source "both";
    yes against no -> unclear, with both pieces of evidence kept and the
    disagreement recorded. A disagreement is shown, never resolved by picking
    a side: the hiker may have seen what the camera missed, or misremembered.
    """
    if photo is None or voice is None:
        only = photo or voice
        return only, []
    merged: dict = {}
    conflicts: list[dict] = []
    for item in ITEM_IDS:
        a, b = photo[item], voice[item]
        if a["answer"] == "unclear":
            merged[item] = dict(b)
        elif b["answer"] == "unclear" or a["answer"] == b["answer"]:
            same = b["answer"] == a["answer"]
            merged[item] = {"answer": a["answer"],
                            "evidence": (f"{a['evidence']} / hiker: {b['evidence']}"
                                         if same else a["evidence"]),
                            "source": "both" if same else a["source"]}
        else:
            merged[item] = {"answer": "unclear", "source": "none",
                            "evidence": f"photo says {a['answer']} ({a['evidence']}); "
                                        f"hiker says {b['answer']} ({b['evidence']})"}
            conflicts.append({"item": item, "photo": a["answer"], "voice": b["answer"]})
    merged["summary"] = photo.get("summary") or voice.get("summary", "")
    return merged, conflicts
