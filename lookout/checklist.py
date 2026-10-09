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
    # Id of a scope item that must be "yes" before this item can be judged
    # from a photo. Absence can only be claimed for what is in view.
    needs: str | None = None


DAM = "dam_in_view"
DOWNSTREAM = "downstream_in_view"

# Order matters: the model answers in this order, so each scope question comes
# before the items that depend on it.
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
    Item("steep_slopes_above", "Steep slopes or hanging ice above",
         "Do steep rock walls or hanging ice rise directly from the lake shore, "
         "close enough for falling rock or ice to reach the water? Distant "
         "mountains in the background do not count.",
         "Fujita et al. 2013, NHESS 13:1827; Rounce et al. 2016, HESS 20:3455"),
    Item("fresh_scars_above", "Fresh rockfall scars above",
         "Are there fresh rockfall or landslide scars on the slopes directly "
         "above the lake?",
         "Allen et al. 2019 (impulse-wave trigger)"),
    Item(DAM, "Dam or outlet in view",
         "Can you see the end of the lake where water flows out, and the ridge "
         "or dam at that end?"),
    Item("moraine_dam", "Moraine dam",
         "Is the water held back by a ridge of loose rock and debris (a moraine "
         "dam) rather than solid bedrock?", needs=DAM),
    Item("low_freeboard", "Low freeboard",
         "Does the top of the dam sit only a little above the water level?",
         "Mergili & Schneider 2011 (freeboard)", needs=DAM),
    Item("steep_dam_face", "Steep dam face",
         "Is the downstream (outer) face of the dam steep?",
         "Lv et al. 1999 (moderate confidence; not independently verified)",
         needs=DAM),
    Item("seepage_breach", "Seepage or breach",
         "Is water seeping out through the dam face, or is there a breach "
         "channel cut through it?", needs=DAM),
    Item(DOWNSTREAM, "Downstream in view",
         "Can you see the land below the lake's outlet, where water flowing "
         "out of the lake would go?"),
    Item("downstream_people", "People or structures downstream",
         "Are trails, houses, bridges or fields visible downstream of the "
         "water?", needs=DOWNSTREAM),
)

ITEM_IDS = tuple(i.id for i in ITEMS)
BY_ID = {i.id: i for i in ITEMS}


def json_schema() -> dict:
    """The structure Ollama constrains the model's output to.

    Evidence comes BEFORE the answer. The model writes the fields in schema
    order, so it has to state what it sees before committing to yes or no.
    With the answer first it wrote "no" and then "none" as the evidence (see
    eval/results/v1-baseline.md).
    """
    answer = {
        "type": "object",
        "properties": {
            "evidence": {"type": "string"},
            "source": {"type": "string", "enum": list(SOURCES)},
            "answer": {"type": "string", "enum": list(ANSWERS)},
        },
        "required": ["evidence", "source", "answer"],
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
        "For every question below, first write 'evidence', then 'source', then "
        "the 'answer' (yes, no or unclear).",
        "- evidence is a short phrase about what you SEE in a photo or what the "
        "hiker SAYS. source is photo, voice or both.",
        "- yes: the evidence shows the feature.",
        "- no: the place where the feature would be IS in view, and the "
        "evidence says what is there instead (for example 'grassy banks, no "
        "ice anywhere in view').",
        "- unclear: that part of the scene is out of view or cannot be judged, "
        "and source is none. Never answer no just because something is out of "
        "view: if the photo does not show what is downstream of the water, "
        "downstream questions are unclear.",
        "- Anything the hiker describes in the voice note counts as evidence, "
        "with source voice.",
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
