from lookout.checklist import ITEM_IDS, json_schema, prompt
from lookout.verify import merge, verify


def _raw(**over):
    raw = {i: {"answer": "unclear", "evidence": "", "source": "none"} for i in ITEM_IDS}
    raw["summary"] = "A lake below a glacier."
    raw.update(over)
    return raw


def test_supported_answers_pass_unchanged():
    raw = _raw(water_body={"answer": "yes", "evidence": "grey lake in centre",
                           "source": "photo"})
    checked, down = verify(raw, has_photo=True, has_voice=False)
    assert checked["water_body"]["answer"] == "yes"
    assert down == []


def test_yes_without_evidence_becomes_unclear():
    raw = _raw(calving_icebergs={"answer": "yes", "evidence": "", "source": "photo"})
    checked, down = verify(raw, has_photo=True, has_voice=False)
    assert checked["calving_icebergs"]["answer"] == "unclear"
    assert down[0]["item"] == "calving_icebergs" and down[0]["model_answer"] == "yes"


def test_no_without_evidence_becomes_unclear():
    """An unsupported 'no' is the silent-zero failure: it reads as 'nothing there'."""
    raw = _raw(seepage_breach={"answer": "no", "evidence": "N/A", "source": "photo"})
    checked, down = verify(raw, has_photo=True, has_voice=False)
    assert checked["seepage_breach"]["answer"] == "unclear"


def test_citing_a_voice_note_that_does_not_exist_is_rejected():
    raw = _raw(moraine_dam={"answer": "yes", "evidence": "hiker says loose ridge",
                            "source": "voice"})
    checked, down = verify(raw, has_photo=True, has_voice=False)
    assert checked["moraine_dam"]["answer"] == "unclear"
    assert "voice note" in down[0]["reason"]


def test_citing_a_photo_that_does_not_exist_is_rejected():
    raw = _raw(glacier_contact={"answer": "yes", "evidence": "ice at waterline",
                                "source": "both"})
    checked, _ = verify(raw, has_photo=False, has_voice=True)
    assert checked["glacier_contact"]["answer"] == "unclear"


def test_answer_with_no_source_is_rejected():
    raw = _raw(water_body={"answer": "yes", "evidence": "a lake", "source": "none"})
    checked, _ = verify(raw, has_photo=True, has_voice=False)
    assert checked["water_body"]["answer"] == "unclear"


def test_missing_item_becomes_unclear_never_no():
    raw = _raw()
    del raw["low_freeboard"]
    checked, down = verify(raw, has_photo=True, has_voice=False)
    assert checked["low_freeboard"]["answer"] == "unclear"
    assert down[0]["model_answer"] is None


def test_unknown_answer_word_becomes_unclear():
    raw = _raw(water_body={"answer": "probably", "evidence": "x", "source": "photo"})
    checked, _ = verify(raw, has_photo=True, has_voice=False)
    assert checked["water_body"]["answer"] == "unclear"


def test_dam_items_need_the_dam_in_view():
    """'No seepage visible' about a dam behind the camera is not an observation."""
    raw = _raw(seepage_breach={"answer": "no", "evidence": "no seepage visible",
                               "source": "photo"},
               dam_in_view={"answer": "no", "evidence": "outlet end out of frame",
                            "source": "photo"})
    checked, down = verify(raw, has_photo=True, has_voice=False)
    assert checked["seepage_breach"]["answer"] == "unclear"
    assert "not confirmed" in down[-1]["reason"]


def test_dam_items_stand_when_the_dam_is_in_view():
    raw = _raw(seepage_breach={"answer": "no", "evidence": "dry outer face of ridge",
                               "source": "photo"},
               dam_in_view={"answer": "yes", "evidence": "outlet ridge at left",
                            "source": "photo"})
    checked, down = verify(raw, has_photo=True, has_voice=False)
    assert checked["seepage_breach"]["answer"] == "no"
    assert down == []


def test_hikers_words_can_answer_out_of_view_items():
    raw = _raw(moraine_dam={"answer": "yes", "evidence": "ridge of loose rock",
                            "source": "voice"})
    checked, _ = verify(raw, has_photo=True, has_voice=True)
    assert checked["moraine_dam"]["answer"] == "yes"


def test_downstream_needs_downstream_in_view():
    raw = _raw(downstream_people={"answer": "no", "evidence": "no houses visible",
                                  "source": "photo"})
    checked, _ = verify(raw, has_photo=True, has_voice=False)
    assert checked["downstream_people"]["answer"] == "unclear"


GOKYO = ("Third Gokyo lake. The water is bright turquoise. On the left there is a "
         "long ridge of loose rock between the lake and the glacier.")


def test_one_voice_sentence_cannot_answer_unrelated_questions():
    """Seen in the synthetic day: the rock-ridge sentence 'proved' no seepage."""
    ridge = "long ridge of loose rock between the lake and the glacier"
    raw = _raw(moraine_dam={"answer": "yes", "evidence": ridge, "source": "voice"},
               fresh_scars_above={"answer": "no", "evidence": ridge, "source": "voice"})
    checked, down = verify(raw, has_photo=True, has_voice=True, transcript=GOKYO)
    assert checked["moraine_dam"]["answer"] == "yes"
    assert checked["fresh_scars_above"]["answer"] == "unclear"
    assert "not about this question" in down[0]["reason"]


def test_voice_evidence_must_be_in_the_transcript():
    raw = _raw(calving_icebergs={"answer": "yes", "evidence": "icebergs drifting by the shore",
                                 "source": "voice"})
    checked, down = verify(raw, has_photo=True, has_voice=True, transcript=GOKYO)
    assert checked["calving_icebergs"]["answer"] == "unclear"
    assert "not in the transcript" in down[0]["reason"]


def test_cannot_see_is_unclear_not_no():
    raw = _raw(downstream_people={"answer": "no", "source": "voice",
                                  "evidence": "I can't see the far end of the lake from here"})
    checked, _ = verify(raw, has_photo=True, has_voice=True,
                        transcript="I can't see the far end of the lake from here.")
    assert checked["downstream_people"]["answer"] == "unclear"


def test_both_as_a_source_does_not_bypass_the_view_check():
    raw = _raw(seepage_breach={"answer": "no", "evidence": "no seepage at the dam",
                               "source": "both"})
    checked, _ = verify(raw, has_photo=True, has_voice=True, transcript="a lake")
    assert checked["seepage_breach"]["answer"] == "unclear"


def test_curly_apostrophe_in_cannot_see_is_caught():
    raw = _raw(downstream_people={"answer": "no", "source": "voice",
                                  "evidence": "I can’t see the far end of the lake"})
    checked, _ = verify(raw, has_photo=False, has_voice=True,
                        transcript="I can’t see the far end of the lake")
    assert checked["downstream_people"]["answer"] == "unclear"


def test_cannot_see_answers_the_in_view_questions():
    raw = _raw(dam_in_view={"answer": "no", "source": "voice",
                            "evidence": "I can't see the far end of the lake"})
    checked, _ = verify(raw, has_photo=False, has_voice=True,
                        transcript="I can't see the far end of the lake from here")
    assert checked["dam_in_view"]["answer"] == "no"


def _a(answer, evidence="x", source="photo"):
    return {"answer": answer, "evidence": evidence, "source": source}


def _cl(**items):
    base = {i: _a("unclear", "", "none") for i in ITEM_IDS}
    base.update(items)
    base["summary"] = "s"
    return base


def test_merge_fills_gaps_and_marks_agreement():
    photo = _cl(water_body=_a("yes", "lake"), steep_slopes_above=_a("yes", "cliffs"))
    voice = _cl(water_body=_a("yes", "a lake", "voice"),
                moraine_dam=_a("yes", "loose ridge", "voice"))
    merged, conflicts = merge(photo, voice)
    assert merged["water_body"]["source"] == "both"
    assert merged["steep_slopes_above"]["answer"] == "yes"
    assert merged["moraine_dam"]["source"] == "voice"
    assert conflicts == []


def test_merge_never_picks_a_side_in_a_disagreement():
    photo = _cl(calving_icebergs=_a("no", "clear water surface"))
    voice = _cl(calving_icebergs=_a("yes", "icebergs by the far shore", "voice"))
    merged, conflicts = merge(photo, voice)
    assert merged["calving_icebergs"]["answer"] == "unclear"
    assert "photo says no" in merged["calving_icebergs"]["evidence"]
    assert "hiker says yes" in merged["calving_icebergs"]["evidence"]
    assert conflicts == [{"item": "calving_icebergs", "photo": "no", "voice": "yes"}]


def test_merge_with_one_source_returns_it():
    photo = _cl(water_body=_a("yes", "lake"))
    assert merge(photo, None) == (photo, [])
    assert merge(None, photo) == (photo, [])


def test_schema_puts_evidence_before_answer():
    """Field order is generation order; see json_schema's docstring."""
    props = list(json_schema()["properties"]["water_body"]["properties"])
    assert props.index("evidence") < props.index("answer")


def test_schema_requires_every_item_and_summary():
    s = json_schema()
    assert set(s["required"]) == set(ITEM_IDS) | {"summary"}
    assert s["properties"]["water_body"]["properties"]["answer"]["enum"] == \
        ["yes", "no", "unclear"]


def test_prompt_includes_transcript_only_when_given():
    assert "Voice note transcript" not in prompt(None, 2)
    assert "ice on the far shore" in prompt("ice on the far shore", 1)
    assert "no photo" in prompt("a lake", 0)
