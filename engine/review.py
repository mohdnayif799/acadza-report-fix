"""Reviewer: reads question + stored solution (never the key or any comment).

Finds what the solution concludes, problems in it, surface text defects, and chapter fit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from engine import llm, prompts
from engine.checks import options_of
from engine.config import Settings, load_settings
from engine.models import Question
from engine.parse import html_to_text
from engine.solve import normalize_answer, render_question

TEXT_DEFECT_TYPES = ["spelling", "exam_reference", "noise", "notation", "answer_form", "stem_data"]
SOLUTION_PROBLEM_TYPES = [
    "wrong_step",
    "belongs_to_other_question",
    "self_contradictory",
    "factual_error",
]
_STR = {"type": "string"}
REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        # v1 used ["string", "array", "null"]: the model returned null for all 43 questions.
        "solution_final_answer": _STR,
        "solution_final_value": _STR,
        "solution_problems": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": SOLUTION_PROBLEM_TYPES},
                    "quote": _STR,
                    "correction": _STR,
                    "detail": _STR,
                },
                "required": ["type", "quote", "correction", "detail"],
            },
        },
        "text_defects": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": TEXT_DEFECT_TYPES},
                    "field": {"type": "string", "enum": ["question", "solution"]},
                    "quote": _STR,
                    "fix": _STR,
                    "detail": _STR,
                },
                "required": ["type", "field", "quote", "fix", "detail"],
            },
        },
        "chapter_fit": {
            "type": "object",
            "properties": {
                "fits": {"type": "boolean"},
                "subject": _STR,
                "chapter": _STR,
                "detail": _STR,
            },
            "required": ["fits", "subject", "chapter", "detail"],
        },
    },
    "required": [
        "solution_final_answer",
        "solution_final_value",
        "solution_problems",
        "text_defects",
        "chapter_fit",
    ],
}


@dataclass(frozen=True)
class Review:
    model: str
    solution_answer: str | tuple[str, ...] | None
    solution_value: str
    solution_problems: tuple[dict, ...]
    text_defects: tuple[dict, ...]
    chapter_fit: dict
    prompt_version: int


def render_for_review(q: Question) -> str:
    solution = html_to_text(q.solution_html) or "[no solution stored]"
    return (
        f"Stated subject: {q.subject or 'unknown'}\nStated chapter: {q.chapter or 'unknown'}\n"
        f"{render_question(q)}\n\nStored solution:\n{solution}"
    )


def review(q: Question, settings: Settings | None = None) -> Review:
    settings = settings or load_settings()
    p = prompts.load("reviewer")
    res = llm.call(
        purpose="review",
        model=settings.reviewer,
        system=p.text,
        user=render_for_review(q),
        schema=REVIEW_SCHEMA,
        settings=settings,
    )
    d = res.data if isinstance(res.data, dict) else {}
    value = str(d.get("solution_final_value") or "")
    answer = normalize_answer(q.qtype, d.get("solution_final_answer") or None)
    chapter_fit = d.get("chapter_fit")
    return Review(
        model=res.model,
        solution_answer=answer if answer is not None else answer_from_value(q, value),
        solution_value=value,
        solution_problems=tuple(x for x in d.get("solution_problems") or [] if isinstance(x, dict)),
        text_defects=tuple(x for x in d.get("text_defects") or [] if isinstance(x, dict)),
        chapter_fit=chapter_fit if isinstance(chapter_fit, dict) else {},
        prompt_version=p.version,
    )


def _first_number(text: str) -> float | None:
    m = re.search(r"-?\d+(?:\.\d+)?", text.replace("−", "-"))
    return float(m.group(0)) if m else None


def answer_from_value(q: Question, value: str) -> str | None:
    """Fallback: map the solution's final value onto the one option that shows that number."""
    target = _first_number(value)
    if target is None or q.qtype == "mcq":
        return None
    if q.qtype == "integerQuestion":
        return (
            normalize_answer(q.qtype, value) if re.fullmatch(r"\s*-?[\d.]+\s*\S*", value) else None
        )
    opts = options_of(q)[1]
    hits = [
        k
        for k, text in opts.items()
        if (n := _first_number(text)) is not None
        and abs(n - target) <= 1e-6 * max(1.0, abs(target))
    ]
    return hits[0] if len(hits) == 1 else None
