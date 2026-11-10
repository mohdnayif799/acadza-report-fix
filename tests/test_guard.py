"""The guard may only make rows safer. These are the safety guarantees in executable form."""

import pytest

from engine.guard import GuardContext, apply_edit, edit_problems, guard


def row(**overrides):
    base = {
        "reportId": "R999",
        "questionId": "x",
        "verdict": "defect",
        "repair": "spelling",
        "edit": None,
        "route": "auto_apply",
        "confidence": 0.95,
        "evidence": "e",
        "student_reply": "Thanks.",
    }
    return {**base, **overrides}


def run(question, taxonomy, proven=False, injection=False, **overrides):
    ctx = GuardContext(question, answer_proven=proven, injection=injection)
    return guard(row(**overrides), ctx, taxonomy)


SPELLING = {"field": "question", "find": "Choroid plexux", "replace": "Choroid plexus"}
ANSWER_A_TO_D = {"field": "answer", "find": "A", "replace": "D"}


def test_valid_surgical_spelling_edit_auto_applies(q, taxonomy):
    out = run(q("61ee6c9d"), taxonomy, edit=SPELLING)
    assert out.row["route"] == "auto_apply" and out.row["edit"] == SPELLING and not out.notes


def test_edit_outside_repair_scope_is_rejected(q, taxonomy):
    out = run(q("68e870ef"), taxonomy, repair="spelling", edit=ANSWER_A_TO_D)
    assert out.row["edit"] is None and out.row["route"] == "faculty_review"
    assert "outside spelling's scope" in out.notes[0]


def test_auto_false_repair_always_goes_to_faculty(q, taxonomy):
    out = run(q("622df25a"), taxonomy, repair="diagram", edit=None)
    assert out.row["route"] == "faculty_review"


def test_answer_key_change_needs_independent_proof(q, taxonomy):
    unproven = run(q("68e870ef"), taxonomy, repair="answer_key", edit=ANSWER_A_TO_D)
    proven = run(q("68e870ef"), taxonomy, proven=True, repair="answer_key", edit=ANSWER_A_TO_D)
    assert unproven.row["route"] == "faculty_review"
    assert proven.row["route"] == "auto_apply"


def test_injection_report_can_never_auto_apply(q, taxonomy):
    edit = {"field": "answer", "find": "A", "replace": "C"}
    out = run(q("6062ec84"), taxonomy, proven=True, injection=True, repair="answer_key", edit=edit)
    assert out.row["route"] == "faculty_review"


def test_low_confidence_downgrades(q, taxonomy):
    out = run(q("61ee6c9d"), taxonomy, edit=SPELLING, confidence=0.6)
    assert out.row["route"] == "faculty_review"


def test_guard_never_upgrades_a_route(q, taxonomy):
    out = run(q("61ee6c9d"), taxonomy, edit=SPELLING, route="faculty_review")
    assert out.row["route"] == "faculty_review"


def test_non_defect_rows_lose_repair_and_edit(q, taxonomy):
    out = run(
        q("6062ec84"),
        taxonomy,
        verdict="no_error",
        repair="answer_key",
        edit={"field": "answer", "find": "A", "replace": "C"},
    )
    assert (out.row["repair"], out.row["edit"], out.row["route"]) == (None, None, "no_change")


def test_defect_cannot_be_no_change(q, taxonomy):
    out = run(q("61ee6c9d"), taxonomy, edit=SPELLING, route="no_change")
    assert out.row["route"] == "faculty_review"


def test_unknown_verdict_raises(q, taxonomy):
    with pytest.raises(ValueError):
        run(q("61ee6c9d"), taxonomy, verdict="corrected")


@pytest.mark.parametrize(
    ("prefix", "repair", "edit", "reason"),
    [
        (
            "61ee6c9d",
            "spelling",
            {"field": "question", "find": "Choroid plexux", "replace": "Choroid plexus 2"},
            "words only",
        ),
        (
            "61ee6c9d",
            "spelling",
            {"field": "question", "find": "<span", "replace": "<div"},
            "occurs",
        ),
        (
            "617fa18e",
            "exam_reference",
            {"field": "question", "find": "(NEET 2019) ", "replace": "(AIPMT 2020) "},
            "only delete",
        ),
        (
            "5fc60508",
            "answer_form",
            {"field": "question", "find": "is equal to", "replace": "is about"},
            "additive",
        ),
        (
            "68e87254",
            "option_repair",
            {"field": "question", "find": "certain distance", "replace": "fixed distance"},
            "changes the stem",
        ),
        (
            "622f08d7",
            "answer_key",
            {"field": "answer", "find": "C", "replace": "D"},
            "not a usable option",
        ),
        (
            "68e870ef",
            "answer_key",
            {"field": "answer", "find": "B", "replace": "D"},
            "not the current answer",
        ),
        (
            "61ee6c9d",
            "spelling",
            {"field": "question", "find": "Choroid plexux", "replace": "Choroid plexux"},
            "changes nothing",
        ),
    ],
)
def test_bad_edits_are_rejected(q, taxonomy, prefix, repair, edit, reason):
    problems = edit_problems(edit, repair, q(prefix), taxonomy)
    assert problems and reason in " ".join(problems)


def test_non_surgical_rewrite_is_rejected(q, taxonomy):
    question = q("61ee6c9d")
    edit = {"field": "question", "find": question.question_html, "replace": "x"}
    assert "not surgical" in " ".join(edit_problems(edit, "noise", question, taxonomy))


def test_good_edits_pass(q, taxonomy):
    cases = [
        (
            "617fa18e",
            "exam_reference",
            {"field": "question", "find": "(NEET 2019) ", "replace": ""},
        ),
        (
            "5fc60508",
            "answer_form",
            {
                "field": "question",
                "find": "the frictional force is equal to",
                "replace": "the frictional force is equal to (in N)",
            },
        ),
        (
            "68e87254",
            "option_repair",
            {"field": "question", "find": "(C) <br />", "replace": "(C) 1 : 1<br />"},
        ),
        ("68f21caf", "type_mismatch", {"field": "questionType", "find": "mcq", "replace": "scq"}),
        (
            "68c8153c",
            "answer_key",
            {"field": "answer", "find": ["A, B, D"], "replace": ["A", "B", "D"]},
        ),
    ]
    for prefix, repair, edit in cases:
        assert edit_problems(edit, repair, q(prefix), taxonomy) == [], prefix


def test_apply_edit_is_pure(q):
    question = q("61ee6c9d")
    before = question.question_html
    assert "Choroid plexus" in apply_edit(question, SPELLING)
    assert question.question_html == before
