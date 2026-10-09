"""The field checklist. One definition drives the prompt, the JSON schema the
model is constrained to, and the source shown beside each answer, so the three
cannot drift apart.

Every item is something a hiker can SEE or SAY, not something that needs a
survey instrument. Where an item corresponds to a published GLOF hazard
indicator the citation is attached; where it is a plain field observation it
says so rather than borrowing authority it does not have.

There is deliberately no overall score. The output is a set of observations
for someone qualified to interpret, not a verdict on whether a lake is
dangerous.
"""
from __future__ import annotations

from dataclasses import dataclass

ANSWERS = ("yes", "no", "unclear")
SOURCES = ("photo", "voice", "both", "none")
UNSOURCED = "field observation (no published threshold)"


@dataclass(frozen=True)
class Item:
    id: str
    label: str
    question: str
    source: str = UNSOURCED


ITEMS: tuple[Item, ...] = (
    Item("water_body", "Water body",
         "Is a lake, pond or river visible, or described in the voice note?"),
    Item("glacial_setting", "Glacial setting",
         "Is this a glacial setting, with glacier ice or bare moraine ridges in "
         "view? Milky or turquoise water alone is not enough: rivers carry that "
         "colour far from any glacier."),
    Item("glacier_contact", "Glacier touches water",
         "Does glacier ice touch the water, or end very close to it?",
         "Rounce et al. 2016, HESS 20:3455 (mother glacier within 600 m)"),
    Item("calving_icebergs", "Icebergs or calving",
         "Are there icebergs on the water, or ice cliffs breaking into it?",
         "Sakai et al. 2009 (calving onset)"),
    Item("moraine_dam", "Moraine dam",
         "Is the water held back by a ridge of loose rock and debris (a moraine "
         "dam) rather than solid bedrock?"),
    Item("low_freeboard", "Low freeboard",
         "Does the top of the dam sit only a little above the water level?",
         "Mergili & Schneider 2011 (freeboard)"),
    Item("steep_dam_face", "Steep dam face",
         "Is the downstream (outer) face of the dam steep?",
         "Lv et al. 1999 (moderate confidence; not independently verified)"),
    Item("steep_slopes_above", "Steep slopes or hanging ice above",
         "Are there steep rock walls or hanging ice directly above the lake?",
         "Fujita et al. 2013, NHESS 13:1827; Rounce et al. 2016, HESS 20:3455"),
    Item("fresh_scars_above", "Fresh rockfall scars above",
         "Are there fresh rockfall or landslide scars on the slopes above the "
         "lake?",
         "Allen et al. 2019 (impulse-wave trigger)"),
    Item("seepage_breach", "Seepage or breach",
         "Is water seeping out through the dam face, or is there a breach "
         "channel cut through it?"),
    Item("downstream_people", "People or structures downstream",
         "Are trails, houses, bridges or fields visible downstream of the "
         "water?"),
)

ITEM_IDS = tuple(i.id for i in ITEMS)
BY_ID = {i.id: i for i in ITEMS}


def json_schema() -> dict:
    """The structure Ollama constrains the model's output to."""
    answer = {
        "type": "object",
        "properties": {
            "answer": {"type": "string", "enum": list(ANSWERS)},
            "evidence": {"type": "string"},
            "source": {"type": "string", "enum": list(SOURCES)},
        },
        "required": ["answer", "evidence", "source"],
    }
    props = {i.id: answer for i in ITEMS}
    props["summary"] = {"type": "string"}
    return {"type": "object", "properties": props,
            "required": [*ITEM_IDS, "summary"]}


def prompt(transcript: str | None, n_photos: int) -> str:
    """The instruction sent with the photos of one stop."""
    if n_photos and transcript:
        material = (f"You have {n_photos} photo(s) from this stop and the "
                    "hiker's voice note, transcribed below.")
    elif n_photos:
        material = (f"You have {n_photos} photo(s) from this stop and no voice "
                    "note.")
    else:
        material = ("You have no photo from this stop, only the hiker's voice "
                    "note, transcribed below.")
    lines = [
        "You are helping a hiker keep a field log of lakes they walked past.",
        material,
        "",
        "Answer every question below with yes, no or unclear.",
        "- Answer yes or no only when you can point to what you SEE in a photo "
        "or what the hiker SAYS. Put that in 'evidence' as a short phrase, and "
        "set 'source' to photo, voice or both.",
        "- If you cannot see it or it was not mentioned, answer unclear, with "
        "source none. Never answer no just because something is out of view.",
        "- Do not judge whether the lake is dangerous. Only record what is "
        "observed.",
        "",
        "Questions:",
    ]
    lines += [f"- {i.id}: {i.question}" for i in ITEMS]
    lines += ["",
              "Finally, write 'summary': one or two plain sentences describing "
              "the scene, with no hazard judgement."]
    if transcript:
        lines += ["", "Voice note transcript:", transcript.strip()]
    return "\n".join(lines)
