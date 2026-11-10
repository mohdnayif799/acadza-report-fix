"""Security review findings (2026-11-10): unsafe markup in edits, and answer-changing edits
that bypassed the proof gate by not touching the `answer` field."""

import pytest

from engine.edit_rules import markup_problems
from engine.guard import GuardContext, edit_problems, guard

MATH_7_8 = (
    '<math xmlns="http://www.w3.org/1998/Math/MathML" display="inline">'
    "<mfrac><mn>7</mn><mn>8</mn></mfrac></math>"
)


@pytest.mark.parametrize(
    "replace",
    [
        "Choroid plexus<script>alert(1)</script>",
        'Choroid plexus<img src=x onerror="alert(1)">',
        '<span onclick="steal()">Choroid plexus</span>',
        '<a href="javascript:alert(1)">Choroid plexus</a>',
        '<span style="background:url(http://evil)">Choroid plexus</span>',
        "<iframe src=//evil></iframe>Choroid plexus",
    ],
)
def test_unsafe_markup_in_replace_is_rejected(replace):
    assert markup_problems("Choroid plexux", replace)


def test_mathml_and_plain_colour_spans_are_allowed():
    assert markup_problems(r"\frac{7}{8}", MATH_7_8) == []
    assert markup_problems("x", '<span style="color:#000000">y</span>') == []


def test_markup_leak_fix_must_keep_the_digits(q, taxonomy):
    good = {"field": "question", "find": r"\frac{7}{8}", "replace": MATH_7_8}
    bad = {"field": "question", "find": r"\frac{7}{8}", "replace": MATH_7_8.replace("7", "5")}
    assert edit_problems(good, "markup_leak", q("63765a28"), taxonomy) == []
    assert "changes the digits" in " ".join(
        edit_problems(bad, "markup_leak", q("63765a28"), taxonomy)
    )


def test_option_repair_may_not_rewrite_a_filled_option(q, taxonomy):
    # Changing option A's text would silently change which option is correct.
    edit = {"field": "question", "find": "(A) 100 N", "replace": "(A) 99 N"}
    question = q("60ca4feb")
    if question.question_html.count("(A) 100 N") != 1:
        edit = {"field": "question", "find": "100 N<br />", "replace": "99 N<br />"}
    assert "rewrites existing option" in " ".join(
        edit_problems(edit, "option_repair", question, taxonomy)
    )


def test_option_repair_needs_proof_to_auto_apply(q, taxonomy):
    edit = {"field": "question", "find": "(C) <br />", "replace": "(C) 1 : 1<br />"}
    row = {
        "reportId": "R011",
        "questionId": "x",
        "verdict": "defect",
        "repair": "option_repair",
        "edit": edit,
        "route": "auto_apply",
        "confidence": 0.95,
        "evidence": "e",
        "student_reply": "Thanks.",
    }
    unproven = guard(row, GuardContext(q("68e87254")), taxonomy)
    proven = guard(row, GuardContext(q("68e87254"), answer_proven=True), taxonomy)
    assert unproven.row["route"] == "faculty_review"
    assert proven.row["route"] == "auto_apply"


def test_stem_data_value_must_come_from_the_solution(q, taxonomy):
    question = q("60f742f6")
    good = {"field": "question", "find": "an inductance", "replace": "an inductance of 95.5 mH"}
    bad = {"field": "question", "find": "an inductance", "replace": "an inductance of 80 mH"}
    assert edit_problems(good, "stem_data", question, taxonomy) == []
    assert "does not state" in " ".join(edit_problems(bad, "stem_data", question, taxonomy))


def test_exam_reference_may_only_delete_an_exam_tag(q, taxonomy):
    question = q("617fa18e")
    sneaky = {"field": "question", "find": "(NEET 2019) Which", "replace": "(NEET 2019) "}
    assert "does not look like" in " ".join(
        edit_problems(sneaky, "exam_reference", question, taxonomy)
    )


def test_answer_form_may_not_add_numbers(q, taxonomy):
    edit = {"field": "question", "find": "is equal to", "replace": "is equal to 20 (in N)"}
    assert "may not add numbers" in " ".join(
        edit_problems(edit, "answer_form", q("5fc60508"), taxonomy)
    )


def test_stem_data_may_not_reword_the_stem(q, taxonomy):
    # Real reviewer output (v2): inserted the value AND changed "are" -> "is".
    question = q("60f742f6")
    reworded = {
        "field": "question",
        "find": "an inductance are connected",
        "replace": "an inductance of 95.5 mH is connected",
    }
    insert_only = {
        "field": "question",
        "find": "an inductance are connected",
        "replace": "an inductance of 95.5 mH are connected",
    }
    assert "only insert" in " ".join(edit_problems(reworded, "stem_data", question, taxonomy))
    assert edit_problems(insert_only, "stem_data", question, taxonomy) == []
