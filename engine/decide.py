"""Deterministic rules: claim + evidence -> verdict, repair, edit, route, confidence, evidence.

The student's claim only decides *which* defect we look at. Whether it is a defect, and what
edit is allowed, comes from the evidence. The guard runs after this and can only make it safer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from engine.candidates import agree_checks
from engine.checks import already_fixed
from engine.claim import Claim
from engine.confidence import Check, score
from engine.evidence import Candidate, Evidence, describe_solves, fmt_answer, same_answer
from engine.models import Report
from engine.syllabus import SOURCE as SYLLABUS_SOURCE
from engine.syllabus import SyllabusResult

AUTO_FLOOR = 0.8
CLAIM_TOPICS = {
    "answer_wrong": ["answer", "type", "unsound", "option_keyed"],
    "wrong_type": ["type", "answer"],
    "solution_wrong": ["solution", "answer", "unsound"],
    "data_missing": ["stem_data", "figure"],
    "figure_missing": ["figure"],
    "option_problem": ["option_keyed", "option", "identical"],
    "options_identical": ["identical"],
    "spelling": ["spelling"],
    "markup_visible": ["markup"],
    "exam_tag": ["exam_tag"],
    "unit_missing": ["unit"],
    "chapter": ["chapter"],
}
ALL_TOPICS = None  # vague / noise: the most urgent defect found, if any


@dataclass(frozen=True)
class Decision:
    row: dict  # brief schema (before guard and reply)
    candidate: Candidate | None
    student_was: str  # right | partly_right | wrong | n/a
    checks: tuple[Check, ...] = ()


def _row(
    report: Report,
    verdict: str,
    repair: str | None,
    edit: dict | None,
    route: str,
    confidence: float,
    evidence: str,
) -> dict:
    return {
        "reportId": report.report_id,
        "questionId": report.question_id,
        "verdict": verdict,
        "repair": repair,
        "edit": edit,
        "route": route,
        "confidence": round(confidence, 2),
        "evidence": evidence,
        "student_reply": "",
    }


def _matches(c: Candidate, claim: Claim) -> int:
    """How well a candidate matches what the student pointed at (quoted text / option)."""
    blob = f"{c.evidence} {c.edit or ''}".lower()
    score = 0
    if claim.quoted_text and claim.quoted_text.lower()[:4] in blob:
        score += 2
    if claim.option_letter and f"({claim.option_letter.lower()})" in blob:
        score += 1
    return score


def pick_candidate(ev: Evidence, claim: Claim) -> Candidate | None:
    topics = CLAIM_TOPICS.get(claim.claim, ALL_TOPICS)
    if claim.claim not in CLAIM_TOPICS and claim.claim not in ("vague", "noise"):
        return None
    pool = [c for c in ev.candidates if topics is None or c.topic in topics]
    if not pool:
        return None
    if topics is not None:
        pool.sort(key=lambda c: topics.index(c.topic))
    best_rank = pool[0].topic
    same_topic = [c for c in pool if c.topic == best_rank]
    # Ties: what the student pointed at, then fixable, then what students see (the question
    # before the solution), then confidence.
    return max(
        same_topic,
        key=lambda c: (
            _matches(c, claim),
            c.edit is not None,
            bool(c.edit) and c.edit["field"] != "solution",
            c.confidence,
        ),
    )


def _student_was(claim: Claim, cand: Candidate) -> str:
    """Right, or only partly right (the key was wrong but their own value is also wrong)."""
    if cand.topic == "unsound":
        return "partly_right"  # the question is broken, but their own claim is not the fix
    if cand.topic != "answer" or not claim.claimed_answer or cand.edit is None:
        return "right"
    claimed = set(re.findall(r"\d+(?:\.\d+)?", claim.claimed_answer))
    target = f"{cand.evidence} {fmt_answer(cand.edit['replace'])}"
    if not claimed:
        letters = set(re.findall(r"\b([A-D])\b", claim.claimed_answer.upper()))
        return (
            "right"
            if not letters or letters & set(fmt_answer(cand.edit["replace"]))
            else "partly_right"
        )
    return "right" if claimed & set(re.findall(r"\d+(?:\.\d+)?", target)) else "partly_right"


def _from_candidate(report: Report, c: Candidate) -> dict:
    auto = c.edit is not None and c.confidence >= AUTO_FLOOR
    route = "auto_apply" if auto else "faculty_review"
    return _row(report, "defect", c.repair, c.edit, route, c.confidence, c.evidence)


def _decision(
    report: Report,
    verdict: str,
    checks: list[Check],
    why: str,
    student_was: str,
    repair: str | None = None,
    route: str = "no_change",
) -> Decision:
    row = _row(report, verdict, repair, None, route, score(checks), why)
    return Decision(row, None, student_was, tuple(checks))


def _content_ok(ev: Evidence) -> list[Check]:
    gaps = {f.code for f in ev.findings} & {"missing_option", "blank_option", "figure_missing"}
    solved = ev.solve_a.answer is not None and ev.solve_b.answer is not None
    return [
        ("code: all options and text present in the stored HTML", not gaps),
        ("both solvers could solve it from the stored text", solved),
    ]


def _special(report: Report, ev: Evidence, claim: Claim) -> Decision | None:
    label = f"claim reader ({claim.source}): {claim.claim}"
    if claim.claim == "display":
        return _decision(
            report,
            "display_issue",
            [(label, True), *_content_ok(ev)],
            "Stored content is complete (all options and data present) and both "
            "solvers solved it as stored; this is a rendering or loading problem "
            "on the device.",
            "n/a",
        )
    if claim.claim == "app":
        checks = [
            (label, True),
            ("both solvers confirm the stored key", ev.key_status == "confirmed"),
        ]
        return _decision(
            report,
            "app_issue",
            checks,
            "Platform behaviour (how the attempt was "
            "recorded), not the question content; route to the app team.",
            "n/a",
        )
    if claim.claim == "language_request":
        english_only = not re.search(r"[ऀ-ॿ]", ev.question.question_html)
        checks = [(label, True), ("code: question stored in English only", english_only)]
        return _decision(
            report,
            "language_mode",
            checks,
            "Student wants another language; the question exists only in English.",
            "n/a",
        )
    return None


def _syllabus(report: Report, ev: Evidence, s: SyllabusResult) -> Decision:
    where = f'{SYLLABUS_SOURCE}; closest line: "{s.closest_line.strip()}"'
    if s.covered:
        return _decision(
            report,
            "no_error",
            list(s.checks),
            f"In the syllabus: the question tests {s.concept}. {where}. {s.reason}",
            "wrong",
        )
    status = "Not in the syllabus" if s.covered is False else "Syllabus fit disputed"
    return _decision(
        report,
        "defect",
        list(s.checks),
        f"{status}: the question tests {s.concept}. {where}. {s.reason} Faculty "
        "confirm; the question stays live meanwhile.",
        "right" if s.covered is False else "n/a",
        "syllabus",
        "faculty_review",
    )


def decide(
    report: Report, ev: Evidence, claim: Claim, syllabus: SyllabusResult | None = None
) -> Decision:
    fixed = already_fixed(report, ev.question)
    if fixed:
        checks = [("code: errorHistory fix dated after the report", True)]
        if fixed.extra.get("quoted"):
            checks.append(("code: the text the student quoted is gone", True))
        return _decision(report, "already_fixed", checks, fixed.detail, "right")
    special = _special(report, ev, claim)
    if special:
        return special
    if claim.claim == "syllabus" and syllabus is not None:
        return _syllabus(report, ev, syllabus)
    cand = pick_candidate(ev, claim)
    if cand is not None:
        return Decision(_from_candidate(report, cand), cand, _student_was(claim, cand), cand.checks)
    key_checks = agree_checks(ev.key.normalized, ev.solve_a, ev.solve_b, ev.review)
    if claim.claim in ("vague", "noise"):
        checks = [
            ("code: comment is noise or too vague to act on", True),
            ("code + reviewer: no defect found on this question", not ev.candidates),
            *key_checks,
        ]
        return _decision(
            report,
            "not_actionable",
            checks,
            "Comment gives nothing to act on, and all checks on this question came back clean.",
            "n/a",
        )
    if claim.claim in ("answer_wrong", "wrong_type", "solution_wrong"):
        solves = describe_solves(ev.solve_a, ev.solve_b)
        why = f"{solves}, matching the key {fmt_answer(ev.key.normalized)}; " + (
            "the stored solution agrees."
            if same_answer(ev.review.solution_answer, ev.key.normalized)
            else "the stored solution reaches no clear answer."
        )
        return _decision(report, "no_error", key_checks, why, "wrong")
    checks = [
        (f"code checks: no {claim.claim} defect", True),
        (f"reviewer ({ev.review.model}): no {claim.claim} defect", True),
    ]
    return _decision(
        report,
        "no_error",
        checks,
        f"Checked the stored question for the reported problem ({claim.claim}); none found.",
        "wrong",
    )
