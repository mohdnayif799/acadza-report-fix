"""Turn the evidence for one question into ranked candidate defects (with surgical edits).

Every candidate lists the independent checks behind it; its confidence is computed from
those checks (engine/confidence.py), never typed in by hand.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from engine.checks import AnswerCheck, check_answer, check_question
from engine.confidence import Check
from engine.config import Settings, load_settings
from engine.confirm import confirm
from engine.evidence import (
    TOPIC_ORDER,
    Candidate,
    Evidence,
    anchored_edit,
    blank_option_edit,
    describe_solves,
    fmt_answer,
    key_status,
    latex_to_mathml,
    same_answer,
    same_value,
)
from engine.guard import apply_edit
from engine.models import Finding, Question
from engine.parse import html_to_text
from engine.review import Review, review
from engine.solve import Solve, solve_a, solve_b
from engine.writer import write_solution

Resolver = Callable[[str], Solve]  # question_html -> solve (used to re-solve an edited stem)
REVIEW_TOPIC = {
    "spelling": "spelling",
    "noise": "noise",
    "notation": "notation",
    "answer_form": "unit",
    "stem_data": "stem_data",
    "exam_reference": "exam_tag",
}
CODE_FINDING_FOR_TOPIC = {"unit": "unit_not_stated", "exam_tag": "exam_tag"}


def _stored_form(q: Question, answer: object) -> object:
    if q.qtype == "mcq":
        return list(answer) if isinstance(answer, (tuple, list)) else [answer]
    return fmt_answer(answer)


def _solution_phrase(rv: Review) -> str:
    if rv.solution_answer is None:
        return "the stored solution reaches no clear answer"
    return f"the stored solution ends at {fmt_answer(rv.solution_answer)} ({rv.solution_value})"


def agree_checks(target: object, a: Solve, b: Solve, rv: Review) -> list[Check]:
    """Solver A, solver B, and the stored solution (left out if it reaches no answer)."""
    checks: list[Check] = [
        (f"solver A ({a.model}) gets {fmt_answer(a.answer)}", same_answer(a.answer, target)),
        (
            f"solver B ({b.model} + Python) gets {fmt_answer(b.answer)}",
            same_answer(b.answer, target),
        ),
    ]
    if rv.solution_answer is not None:
        checks.append(
            (
                f"stored solution ends at {fmt_answer(rv.solution_answer)}",
                same_answer(rv.solution_answer, target),
            )
        )
    return checks


def _flags(a: Solve, b: Solve, kinds: set[str]) -> list[Check]:
    """Confirm-only checks: a solver noticing the problem counts; silence does not."""
    return [
        (f"solver {s.solver} also reports it", True)
        for s in (a, b)
        if any(s.has_issue(k) for k in kinds)
    ]


def answer_candidates(
    q: Question,
    key: AnswerCheck,
    a: Solve,
    b: Solve,
    rv: Review,
    status: str,
    consensus: object,
    codes: set[str],
) -> list[Candidate]:
    solves, sol = describe_solves(a, b), _solution_phrase(rv)
    stored = fmt_answer(key.normalized if key.normalized else q.answer)
    if "single_answer_mcq" in codes and key.normalized:
        letter = key.normalized[0]
        checks = [
            ("code: mcq key holds exactly one letter", True),
            *agree_checks(key.normalized, a, b, rv),
        ]
        return [
            Candidate.of(
                "type",
                "type_mismatch",
                {"field": "questionType", "find": q.qtype, "replace": "scq"},
                status == "confirmed",
                checks,
                f"Stored as multiple-correct (mcq) with key {q.answer!r}, but only ({letter}) is "
                f'correct: {solves}. Make it scq with key "{letter}".',
                "check",
                ({"field": "answer", "find": q.answer, "replace": letter},),
            )
        ]
    if status == "wrong":
        return [
            Candidate.of(
                "answer",
                "answer_key",
                {"field": "answer", "find": q.answer, "replace": _stored_form(q, consensus)},
                True,
                agree_checks(consensus, a, b, rv),
                f"{solves}; {sol}; the key says {stored}.",
                "solvers",
            )
        ]
    if "malformed_answer" in codes and key.normalized:
        new = _stored_form(q, key.normalized)
        checks = [("code: stored key is malformed", True), *agree_checks(key.normalized, a, b, rv)]
        return [
            Candidate.of(
                "answer",
                "answer_key",
                {"field": "answer", "find": q.answer, "replace": new},
                status == "confirmed",
                checks,
                f"Key is stored as {q.answer!r}, which no attempt can match. {solves}, the same "
                f"letters as the key once cleaned up: {new}.",
                "check",
            )
        ]
    if status == "unsound" and "identical_options" not in codes:  # identical options explain it
        issues = "; ".join(i.get("detail", "") for i in (*a.issues, *b.issues))[:300]
        checks = _flags(a, b, {"no_matching_option", "multiple_correct"})
        if any(p.get("type") == "self_contradictory" for p in rv.solution_problems):
            checks.append(("reviewer: stored solution contradicts itself", True))
        return [
            Candidate.of(
                "unsound",
                "unsound",
                None,
                False,
                checks,
                f"Both solvers find no valid option as written ({issues}). "
                f"{sol}. Faculty must re-author.",
                "solvers",
            )
        ]
    if status == "unclear" and not codes & {"blank_option", "missing_option"}:
        return [
            Candidate.of(
                "answer",
                "answer_key",
                None,
                False,
                agree_checks(key.normalized, a, b, rv),
                f"Solvers disagree ({solves}); {sol}; key {stored}. The correct "
                "answer is unclear, so no change is proposed.",
                "solvers",
            )
        ]
    return []


def _keyed_blank(q: Question, letter: str, a: Solve, b: Solve, rv: Review) -> Candidate:
    checks: list[Check] = [
        (f"code: keyed option ({letter}) is blank", True),
        (f"solver A computes {a.value!r}", bool(a.value.strip())),
        (f"solver B computes {b.value!r}", same_value(a.value, b.value)),
    ]
    if rv.solution_value.strip():
        checks.append(
            (
                f"stored solution reaches {rv.solution_value!r}",
                same_value(rv.solution_value, a.value),
            )
        )
    agree = all(ok for _, ok in checks)
    edit = blank_option_edit(q, letter, a.value) if agree else None
    return Candidate.of(
        "option_keyed",
        "option_repair",
        edit,
        agree,
        checks,
        f"Option ({letter}) is blank but is the keyed answer. Solvers compute {a.value!r} / "
        f"{b.value!r}; {_solution_phrase(rv)} (value {rv.solution_value!r}). Fill ({letter}) "
        f"with {a.value}; stem unchanged.",
        "check",
    )


def option_candidates(
    q: Question, key: AnswerCheck, a: Solve, b: Solve, rv: Review, findings: tuple[Finding, ...]
) -> list[Candidate]:
    keyed = set(key.normalized if isinstance(key.normalized, tuple) else [key.normalized])
    out = []
    for f in findings:
        letter = f.extra.get("letter")
        if f.code == "blank_option" and letter in keyed:
            out.append(_keyed_blank(q, letter, a, b, rv))
        elif f.code in {"blank_option", "missing_option"}:
            out.append(
                Candidate.of(
                    "option",
                    "option_repair",
                    None,
                    False,
                    [
                        ("code: option absent or blank in the raw HTML", True),
                        *_flags(a, b, {"blank_option", "no_matching_option"}),
                    ],
                    f"{f.detail}. Nothing in the solution or data shows what it was, so filling it "
                    "means inventing a distractor: authored content, like identical_options "
                    f"(auto: false). Keyed answer ({fmt_answer(key.normalized)}) is unaffected.",
                    "check",
                )
            )
        elif f.code == "identical_options":
            out.append(
                Candidate.of(
                    "identical",
                    "identical_options",
                    None,
                    False,
                    [
                        ("code: two option texts are identical", True),
                        *_flags(a, b, {"multiple_correct"}),
                    ],
                    f"{f.detail}; a new distractor is authored content.",
                    "check",
                )
            )
    return out


def check_candidates(
    q: Question, findings: tuple[Finding, ...], a: Solve, b: Solve, settings: Settings
) -> list[Candidate]:
    out, seen = [], set()
    for f in findings:
        if f.code == "figure_missing":
            out.append(
                Candidate.of(
                    "figure",
                    "diagram",
                    None,
                    False,
                    [
                        ("code: refers to a figure, no image stored", True),
                        *_flags(a, b, {"figure_needed"}),
                    ],
                    f.detail,
                    "check",
                )
            )
        elif f.code == "exam_tag":
            edit = {"field": "question", "find": f.find, "replace": ""}
            c = confirm(q, "exam_reference", f.find.strip(), "(removed)", settings, False)
            checks = [
                ("code: exam-tag pattern in raw HTML", True),
                (f"confirmer ({c.model}): {c.reason}", c.agrees),
            ]
            out.append(
                Candidate.of("exam_tag", "exam_reference", edit, False, checks, f.detail, "check")
            )
        elif f.code in {"latex_leak", "align_amp_leak"} and (f.field, f.find) not in seen:
            seen.add((f.field, f.find))
            out.append(_markup_candidate(q, f, settings))
        elif f.code == "unit_not_stated":
            out.append(
                Candidate.of(
                    "unit",
                    "answer_form",
                    None,
                    False,
                    [("code: no unit in an integer question", True)],
                    f.detail,
                    "check",
                )
            )
    return out


def _markup_candidate(q: Question, f: Finding, settings: Settings) -> Candidate:
    raw = q.field_value(f.field)
    count = raw.count(f.find)
    new = latex_to_mathml(f.find) if f.code == "latex_leak" else ""
    edit = (
        {"field": f.field, "find": f.find, "replace": new}
        if count == 1 and new is not None
        else None
    )
    checks: list[Check] = [("code: raw LaTeX / alignment '&' found in the HTML", True)]
    if edit:
        c = confirm(q, "markup_leak", f.find, new or "(removed)", settings, f.field == "solution")
        checks.append((f"confirmer ({c.model}): {c.reason}", c.agrees))
    note = "" if count == 1 else f" ({count} occurrences; fix all in one pass)"
    return Candidate.of("markup", "markup_leak", edit, False, checks, f.detail + note, "check")


def _unit_check(fix: str, rv: Review, q: Question) -> Check | None:
    """answer_form: the unit added to the question must be the unit the solution ends in."""
    m = re.search(r"\(in\s+([^)]+)\)", fix)
    if not m:
        return None
    unit = m.group(1).strip()
    tail = html_to_text(q.solution_html)[-300:]
    found = bool(
        re.search(rf"(?<![A-Za-z]){re.escape(unit)}(?![A-Za-z])", f"{rv.solution_value} {tail}")
    )
    return (f"stored solution's final answer is in {unit} ({rv.solution_value!r})", found)


def _reviewer_candidate(
    q: Question,
    key: AnswerCheck,
    rv: Review,
    d: dict,
    codes: set[str],
    resolve: Resolver,
    settings: Settings,
) -> Candidate | None:
    kind, field, quote, fix = d.get("type"), d.get("field"), d.get("quote", ""), d.get("fix", "")
    topic = REVIEW_TOPIC.get(kind)
    if topic is None or field not in ("question", "solution"):
        return None
    edit = anchored_edit(q, field, quote, fix)
    detail = f"{d.get('detail', '')} ({quote!r} -> {fix!r})"
    checks: list[Check] = [(f"reviewer ({rv.model}) flagged it", True)]
    if CODE_FINDING_FOR_TOPIC.get(topic) in codes:
        checks.append((f"code: {CODE_FINDING_FOR_TOPIC[topic]} on the raw HTML", True))
    if edit is None:
        detail += "; quote not found once in the raw HTML, so no edit is proposed"
        return Candidate.of(topic, kind, None, False, checks, detail, "reviewer")
    c = confirm(
        q, kind, quote, fix, settings, include_solution=field == "solution" or kind == "stem_data"
    )
    checks.append((f"confirmer ({c.model}): {c.reason}", c.agrees))
    proven = False
    if kind == "answer_form" and (unit := _unit_check(fix, rv, q)) is not None:
        checks.append(unit)
    if kind == "stem_data":
        resolved = resolve(apply_edit(q, edit))
        proven = same_answer(resolved.answer, key.normalized)
        checks.append(
            (
                f"edited question re-solves to {fmt_answer(resolved.answer)} "
                f"({resolved.model} + Python); key {fmt_answer(key.normalized)}",
                proven,
            )
        )
    return Candidate.of(topic, kind, edit, proven, checks, detail, "reviewer")


def reviewer_candidates(
    q: Question,
    key: AnswerCheck,
    rv: Review,
    a: Solve,
    b: Solve,
    resolve: Resolver,
    have: set[str],
    codes: set[str],
    settings: Settings,
) -> list[Candidate]:
    out = []
    for d in rv.text_defects:
        topic = REVIEW_TOPIC.get(d.get("type"))
        if topic in have and topic != "spelling":
            continue
        cand = _reviewer_candidate(q, key, rv, d, codes, resolve, settings)
        if cand:
            out.append(cand)
    if (
        "stem_data" not in {c.topic for c in out}
        and a.has_issue("missing_data")
        and b.has_issue("missing_data")
    ):
        what = next(i["detail"] for i in a.issues if i.get("type") == "missing_data")
        out.append(
            Candidate.of(
                "stem_data",
                "stem_data",
                None,
                False,
                _flags(a, b, {"missing_data"}),
                f"Both solvers say data is missing: {what}",
                "solvers",
            )
        )
    return out


def solution_candidates(
    q: Question, key: AnswerCheck, rv: Review, a: Solve, b: Solve, status: str, settings: Settings
) -> list[Candidate]:
    if status != "confirmed":
        return []  # never "fix" a solution toward a key we could not confirm
    kinds = {p.get("type") for p in rv.solution_problems}
    # A problem that cannot be fixed surgically (its quote spans math markup, so it is not
    # found once in the raw HTML) means the solution is unusable as stored: rewrite it.
    # Deciding on anchorability, not on the reviewer's label, keeps this stable across
    # prompt versions (v2 said "belongs_to_other_question", v3 said "wrong_step" for Q22).
    unanchorable = any(
        p.get("type") in ("wrong_step", "factual_error")
        and anchored_edit(q, "solution", p.get("quote", ""), p.get("correction", "")) is None
        for p in rv.solution_problems
    )
    key_checks = [
        (f"solver {s.solver} ({s.model}) confirms the key {fmt_answer(key.normalized)}", True)
        for s in (a, b)
    ]
    if kinds & {"belongs_to_other_question", "self_contradictory"} or unanchorable:
        return [_rewrite_candidate(q, key, rv, key_checks, settings)]
    out = []
    for p in rv.solution_problems:
        if p.get("type") not in ("wrong_step", "factual_error"):
            continue
        edit = anchored_edit(q, "solution", p.get("quote", ""), p.get("correction", ""))
        checks: list[Check] = [(f"reviewer ({rv.model}) flagged it", True), *key_checks]
        if edit:
            c = confirm(q, p.get("type", ""), p.get("quote", ""), p.get("correction", ""), settings)
            checks.append((f"confirmer ({c.model}): {c.reason}", c.agrees))
        out.append(
            Candidate.of(
                "solution",
                "solution_fix",
                edit,
                False,
                checks,
                f"{p.get('detail', '')} ({p.get('quote')!r} -> {p.get('correction')!r})",
                "reviewer",
            )
        )
    return out


def _rewrite_candidate(
    q: Question, key: AnswerCheck, rv: Review, key_checks: list[Check], settings: Settings
) -> Candidate:
    new = write_solution(q, key, settings)
    detail = "; ".join(p.get("detail", "") for p in rv.solution_problems).rstrip(".")
    checks: list[Check] = [(f"reviewer ({rv.model}): stored solution unusable", True), *key_checks]
    edit = None
    if new:
        edit = {"field": "solution", "find": q.solution_html, "replace": new}
        c = confirm(q, "solution_rewrite", "(whole stored solution)", new, settings)
        checks += [
            ("rewrite ends in the keyed answer", True),
            (f"confirmer ({c.model}): {c.reason}", c.agrees),
        ]
    return Candidate.of(
        "solution",
        "solution_fix",
        edit,
        False,
        checks,
        f"Stored solution is unusable: {detail}. Rewritten to end in the "
        f"confirmed key ({fmt_answer(key.normalized)}).",
        "reviewer",
    )


def chapter_candidates(q: Question, rv: Review, settings: Settings) -> list[Candidate]:
    cf = rv.chapter_fit
    if not cf or cf.get("fits", True):
        return []
    claim = (
        f"filed under {q.subject} / {q.chapter}; belongs to {cf.get('subject')} / "
        f"{cf.get('chapter')}"
    )
    c = confirm(q, "wrong_chapter", claim, "n/a", settings, include_solution=False)
    checks = [
        (f"reviewer ({rv.model}): chapter does not fit", True),
        (f"confirmer ({c.model}): {c.reason}", c.agrees),
    ]
    return [
        Candidate.of(
            "chapter",
            "wrong_chapter",
            None,
            False,
            checks,
            f"Filed under {q.subject} / {q.chapter}; the content is "
            f"{cf.get('subject')} / {cf.get('chapter')}. {cf.get('detail', '')}",
            "reviewer",
        )
    ]


def build_evidence(q: Question, settings: Settings | None = None) -> Evidence:
    settings = settings or load_settings()
    findings = tuple(check_question(q))
    key = check_answer(q)
    a, b, rv = solve_a(q, settings), solve_b(q, settings), review(q, settings)
    status, consensus = key_status(q, key, a, b, findings)
    codes = {f.code for f in findings}
    cands = [
        *answer_candidates(q, key, a, b, rv, status, consensus, codes),
        *option_candidates(q, key, a, b, rv, findings),
        *check_candidates(q, findings, a, b, settings),
    ]
    have = {c.topic for c in cands if c.edit is not None}  # topics already fixable by code

    def resolve(question_html: str) -> Solve:
        return solve_b(q, settings, question_html=question_html)

    reviewed = reviewer_candidates(q, key, rv, a, b, resolve, have, codes, settings)
    fixable = {c.topic for c in reviewed if c.edit is not None}
    # A reviewer candidate that carries a valid edit replaces a code finding that has none.
    cands = [c for c in cands if c.edit is not None or c.topic not in fixable] + reviewed
    cands += solution_candidates(q, key, rv, a, b, status, settings)
    cands += chapter_candidates(q, rv, settings)
    cands.sort(key=lambda c: (TOPIC_ORDER.index(c.topic), -c.confidence))
    return Evidence(q, findings, key, a, b, rv, status, consensus, tuple(cands))
