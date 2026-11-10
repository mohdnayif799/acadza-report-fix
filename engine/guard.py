"""Code guard: the last word on every row before it reaches results.json.

The LLM proposes; this module decides what is allowed to auto-apply. It can only make
a row *safer* (drop an edit, downgrade auto_apply -> faculty_review), never riskier.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from typing import Any

from engine.checks import check_answer, options_of
from engine.models import TEXT_FIELDS, Question

AUTO_MIN_CONFIDENCE = 0.8
ROUTES = ("auto_apply", "faculty_review", "no_change")
BRIEF_KEYS = (
    "reportId",
    "questionId",
    "verdict",
    "repair",
    "edit",
    "route",
    "confidence",
    "evidence",
    "student_reply",
)
EDIT_KEYS = {"field", "find", "replace"}
QUESTION_TYPES = ("scq", "mcq", "integerQuestion")
MAX_FIND_LEN = 400  # surgical: the span being replaced
MAX_GROWTH = 600  # how much longer replace may be than find
MAX_REWRITE_LEN = 4000  # solution rewrites (solution_fix / solution_missing)
REWRITE_REPAIRS = {"solution_fix", "solution_missing"}
NEEDS_PROOF = {"answer_key", "type_mismatch"}  # answer changes need independent proof


@dataclass(frozen=True)
class GuardContext:
    question: Question
    answer_proven: bool = False  # two independent methods agree on the (new) answer
    injection: bool = False  # the report's comment tried to instruct the system


@dataclass(frozen=True)
class GuardOutcome:
    row: dict
    notes: tuple[str, ...]


def apply_edit(q: Question, edit: dict) -> Any:
    """New value of edit['field'] after the edit. Strings: first occurrence only."""
    if edit["field"] in TEXT_FIELDS:
        return q.field_value(edit["field"]).replace(edit["find"], edit["replace"], 1)
    return edit["replace"]  # answer / questionType: whole-value replacement


def _non_letters(s: str) -> str:
    return re.sub(r"[^\W\d_]|\s", "", s)


def _repair_rule_problems(repair: str, edit: dict, q: Question) -> list[str]:
    find, replace = edit["find"], edit["replace"]
    if repair == "spelling" and _non_letters(find) != _non_letters(replace):
        return ["spelling edit changes a value, symbol or tag (words only)"]
    if repair in ("exam_reference", "noise") and (len(replace) >= len(find) or replace not in find):
        return [f"{repair} edit must only delete text"]
    if repair == "answer_form" and find not in replace:
        return ["answer_form edit must be additive (find kept inside replace)"]
    if repair == "option_repair":
        new_q = dataclasses.replace(q, question_html=apply_edit(q, edit))
        if options_of(new_q)[0] != options_of(q)[0]:
            return ["option_repair edit changes the stem text"]
    return []


def _value_problems(edit: dict, q: Question) -> list[str]:
    field, find, replace = edit["field"], edit["find"], edit["replace"]
    current = q.field_value(field)
    if field == "questionType":
        if find != current:
            return [f"find {find!r} is not the current questionType {current!r}"]
        return [] if replace in QUESTION_TYPES else [f"unknown questionType {replace!r}"]
    if field == "answer":
        if find != current:
            return [f"find {find!r} is not the current answer {current!r}"]
        new_q = dataclasses.replace(q, answer=replace)
        problems = list(check_answer(new_q).problems)
        if q.qtype == "scq" and not problems:
            opts = options_of(q)[1]
            if not opts.get(replace.strip().upper(), "").strip():
                problems.append(f"new answer {replace!r} is not a usable option")
        return problems
    if not isinstance(find, str) or not isinstance(replace, str) or not find:
        return ["find/replace must be non-empty strings for text fields"]
    count = current.count(find)
    return [] if count == 1 else [f"find text occurs {count} times in {field} (need exactly 1)"]


def edit_problems(edit: Any, repair: str, q: Question, taxonomy: dict) -> list[str]:
    """Everything wrong with a proposed edit. Empty list = allowed."""
    if not isinstance(edit, dict) or set(edit) != EDIT_KEYS:
        return [f"edit must be an object with exactly {sorted(EDIT_KEYS)}"]
    allowed = taxonomy["repairs"][repair]["fields"]
    if edit["field"] not in allowed:
        return [f"field {edit['field']!r} is outside {repair}'s scope {allowed}"]
    if edit["find"] == edit["replace"]:
        return ["edit changes nothing"]
    problems = _value_problems(edit, q)
    if problems or edit["field"] in ("answer", "questionType"):
        return problems
    if repair in REWRITE_REPAIRS:
        if len(edit["replace"]) > MAX_REWRITE_LEN:
            problems.append("solution rewrite is too long")
    elif len(edit["find"]) > MAX_FIND_LEN or len(edit["replace"]) > len(edit["find"]) + MAX_GROWTH:
        problems.append("edit is not surgical (span too large)")
    return problems + _repair_rule_problems(repair, edit, q)


def guard(row: dict, ctx: GuardContext, taxonomy: dict) -> GuardOutcome:
    """Return a safe copy of `row` plus notes on anything that was changed."""
    r = dict(row)
    notes: list[str] = []
    if r["verdict"] not in taxonomy["verdicts"]:
        raise ValueError(f"verdict {r['verdict']!r} not in taxonomy")
    if r["route"] not in ROUTES:
        raise ValueError(f"route {r['route']!r} not allowed")
    r["confidence"] = round(min(max(float(r["confidence"]), 0.0), 1.0), 2)

    if r["verdict"] != "defect":
        if r.get("repair") or r.get("edit") or r["route"] != "no_change":
            notes.append("non-defect verdict: repair/edit dropped, route set to no_change")
        r.update(repair=None, edit=None, route="no_change")
        return GuardOutcome(r, tuple(notes))

    repair = r.get("repair")
    if not isinstance(repair, str) or repair not in taxonomy["repairs"]:
        raise ValueError(f"defect needs a taxonomy repair, got {repair!r}")
    if r.get("edit") is not None:
        problems = edit_problems(r["edit"], repair, ctx.question, taxonomy)
        if problems:
            notes.append("edit rejected: " + "; ".join(problems))
            r["edit"] = None
    if r["route"] == "no_change":
        r["route"] = "faculty_review"
        notes.append("a defect cannot be no_change")

    def downgrade(reason: str) -> None:
        if r["route"] == "auto_apply":
            r["route"] = "faculty_review"
            notes.append(f"auto_apply blocked: {reason}")

    if not taxonomy["repairs"][repair]["auto"]:
        downgrade(f"{repair} is auto: false (faculty must approve)")
    if r["edit"] is None:
        downgrade("no valid edit to apply")
    touches_answer = r["edit"] is not None and r["edit"]["field"] == "answer"
    if (repair in NEEDS_PROOF or touches_answer) and not ctx.answer_proven:
        downgrade("answer change not proven by two independent methods")
    if r["confidence"] < AUTO_MIN_CONFIDENCE:
        downgrade(f"confidence {r['confidence']} < {AUTO_MIN_CONFIDENCE}")
    if ctx.injection:
        downgrade("report comment contains a prompt-injection attempt")
    return GuardOutcome(r, tuple(notes))
