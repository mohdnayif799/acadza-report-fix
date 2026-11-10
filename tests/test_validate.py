"""validate_results: the contract results.json must meet (brief schema + taxonomy)."""

import json

import pytest

from engine.models import ROOT
from engine.validate import count_sentences, validate_results


def valid_rows(reports):
    return [
        {
            "reportId": r.report_id,
            "questionId": r.question_id,
            "verdict": "not_actionable",
            "repair": None,
            "edit": None,
            "route": "no_change",
            "confidence": 0.5,
            "evidence": "placeholder",
            "student_reply": "Thanks for flagging this.",
        }
        for r in reports
    ]


def errors_after(reports, questions, taxonomy, rid, **changes):
    rows = valid_rows(reports)
    target = next(r for r in rows if r["reportId"] == rid)
    target.update(changes)
    return validate_results(rows, reports, questions, taxonomy)


def test_a_complete_valid_file_passes(reports, questions, taxonomy):
    assert validate_results(valid_rows(reports), reports, questions, taxonomy) == []


def test_missing_and_duplicate_reports(reports, questions, taxonomy):
    rows = valid_rows(reports)
    errors = validate_results(rows[:-1] + [rows[0]], reports, questions, taxonomy)
    assert any("duplicate" in e for e in errors) and any("missing 1" in e for e in errors)


def test_extra_or_missing_keys_fail(reports, questions, taxonomy):
    rows = valid_rows(reports)
    rows[0]["extra"] = 1
    del rows[1]["evidence"]
    errors = validate_results(rows, reports, questions, taxonomy)
    assert len([e for e in errors if "keys must be exactly" in e]) == 2


@pytest.mark.parametrize(
    ("changes", "fragment"),
    [
        ({"verdict": "corrected"}, "not in taxonomy"),
        ({"verdict": "defect", "repair": "magic", "route": "faculty_review"}, "not in taxonomy"),
        ({"verdict": "defect", "repair": None, "route": "faculty_review"}, "if and only if"),
        ({"route": "auto_apply"}, "non-defect rows"),
        ({"verdict": "defect", "repair": "diagram", "route": "auto_apply"}, "auto: false"),
        ({"verdict": "defect", "repair": "spelling", "route": "no_change"}, "cannot be no_change"),
        ({"confidence": 1.2}, "confidence"),
        ({"student_reply": "One. Two. Three. Four."}, "1-3 sentences"),
        (
            {
                "verdict": "defect",
                "repair": "spelling",
                "route": "auto_apply",
                "edit": {"field": "answer", "find": "C", "replace": "A"},
            },
            "not allowed for spelling",
        ),
        (
            {
                "verdict": "defect",
                "repair": "answer_key",
                "route": "auto_apply",
                "edit": {"field": "answer", "find": "B", "replace": "A"},
            },
            "!= current answer",
        ),
        (
            {"verdict": "defect", "repair": "spelling", "route": "auto_apply", "edit": None},
            "without an edit",
        ),
    ],
)
def test_rule_violations_are_caught(reports, questions, taxonomy, changes, fragment):
    errors = errors_after(reports, questions, taxonomy, "R001", **changes)
    assert any(fragment in e for e in errors), errors


def test_answer_edit_must_match_the_whole_key_not_a_substring(reports, questions, taxonomy):
    # R033's key is "3113": find "3" is a substring but not the key. Caught by a failing test.
    edit = {"field": "answer", "find": "3", "replace": "4"}
    errors = errors_after(
        reports,
        questions,
        taxonomy,
        "R033",
        verdict="defect",
        repair="answer_key",
        route="auto_apply",
        edit=edit,
    )
    assert any("!= current answer" in e for e in errors), errors


def test_correct_answer_key_edit_passes(reports, questions, taxonomy):
    edit = {"field": "answer", "find": "C", "replace": "A"}
    assert (
        errors_after(
            reports,
            questions,
            taxonomy,
            "R001",
            verdict="defect",
            repair="answer_key",
            route="auto_apply",
            edit=edit,
        )
        == []
    )


def test_count_sentences():
    assert count_sentences("You're right. The key was wrong; it's (D). Fixed!") == 3
    assert count_sentences("Answer 4800 hai, 8225 nahi.") == 1


def test_committed_results_file_is_valid(reports, questions, taxonomy):
    path = ROOT / "results.json"
    if not path.exists():
        pytest.skip("results.json not generated yet (needs the Gemini key)")
    rows = json.loads(path.read_text(encoding="utf-8"))
    assert validate_results(rows, reports, questions, taxonomy) == []
