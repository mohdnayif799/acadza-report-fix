import pytest

from engine.human_edits import HumanEditError, apply_human_edits, load_edits

ROWS = [
    {"reportId": "R023", "student_reply": "I have sent this to our faculty team.", "evidence": "e"}
]


def test_edit_is_applied_without_mutating_input():
    edit = {
        "reportId": "R023",
        "field": "student_reply",
        "find": "I have sent",
        "replace": "We have sent",
    }
    rows, applied = apply_human_edits(ROWS, [edit])
    assert rows[0]["student_reply"] == "We have sent this to our faculty team."
    assert ROWS[0]["student_reply"].startswith("I have")
    assert applied == {"R023": [edit]}


def test_stale_edit_fails_loudly():
    edit = {"reportId": "R023", "field": "student_reply", "find": "no such text", "replace": "x"}
    with pytest.raises(HumanEditError):
        apply_human_edits(ROWS, [edit])


def test_only_text_fields_can_be_edited():
    edit = {"reportId": "R023", "field": "verdict", "find": "a", "replace": "b"}
    with pytest.raises(HumanEditError):
        apply_human_edits(ROWS, [edit])


def test_committed_edits_file_loads():
    assert all({"reportId", "field", "find", "replace", "why"} <= set(e) for e in load_edits())
