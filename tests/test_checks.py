import pytest

from engine.checks import already_fixed, check_answer, check_question
from engine.comments import analyze_comment


def codes(question):
    return {f.code for f in check_question(question)}


@pytest.mark.parametrize(
    ("prefix", "expected"),
    [
        ("68e87254", {"blank_option", "key_option_blank"}),
        ("622f08d7", {"missing_option", "align_amp_leak"}),
        ("6956d797", {"identical_options", "align_amp_leak"}),
        ("617fa18e", {"exam_tag"}),
        ("63765a28", {"latex_leak"}),
        ("622df25a", {"figure_missing"}),
        ("5fc60508", {"unit_not_stated"}),
        ("68f21caf", {"malformed_answer", "single_answer_mcq"}),
        ("68c8153c", {"malformed_answer"}),
    ],
)
def test_planted_defects_are_found(q, prefix, expected):
    assert expected <= codes(q(prefix))


@pytest.mark.parametrize("prefix", ["68dea87d", "68dea657", "695ede2a", "68dea6e6", "60f744b3"])
def test_clean_questions_have_no_findings(q, prefix):
    assert codes(q(prefix)) == set()


def test_exam_tag_find_is_exact_raw_span(q):
    tag = next(f for f in check_question(q("617fa18e")) if f.code == "exam_tag")
    assert tag.find == "(NEET 2019) "
    assert q("617fa18e").question_html.count(tag.find) == 1


def test_malformed_mcq_answers_normalize(q):
    assert check_answer(q("68c8153c")).normalized == ("A", "B", "D")
    assert check_answer(q("68f21caf")).normalized == ("B",)
    assert check_answer(q("60f744b3")).problems == ()


def test_already_fixed_uses_error_history_after_report(q, reports):
    r017 = next(r for r in reports if r.report_id == "R017")
    finding = already_fixed(r017, q("6208e80a"))
    assert finding is not None and "'mere' no longer in the text" in finding.detail


def test_already_fixed_ignores_reports_after_the_fix(q, reports):
    r017 = next(r for r in reports if r.report_id == "R017")
    late = r017.__class__(**{**r017.__dict__, "reported_at": "2026-11-09T00:00:00Z"})
    assert already_fixed(late, q("6208e80a")) is None


def test_comment_signals(reports):
    by_id = {r.report_id: analyze_comment(r.comment) for r in reports}
    assert by_id["R041"].is_noise
    assert by_id["R040"].is_vague and not by_id["R040"].is_noise
    assert by_id["R027"].injection
    assert [rid for rid, s in by_id.items() if s.injection] == ["R027"]
    assert by_id["R011"].hinglish and not by_id["R029"].hinglish
