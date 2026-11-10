"""Two independent solves. Neither sees the stored key, the stored solution or any comment.

Solver A: strong reasoning model, structured JSON.
Solver B: a *different* model that computes numerically with code execution, so a shared
reasoning slip in A is unlikely to be repeated in B.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from engine import llm, prompts
from engine.checks import LETTERS, options_of
from engine.config import Settings, load_settings
from engine.models import Question

ISSUE_TYPES = [
    "no_matching_option",
    "multiple_correct",
    "missing_data",
    "figure_needed",
    "blank_option",
]
TYPE_NAMES = {
    "scq": "scq (single correct option)",
    "mcq": "mcq (one or more correct options)",
    "integerQuestion": "integerQuestion (numerical answer)",
}
SOLVE_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": ["string", "array", "null"], "items": {"type": "string"}},
        "value": {"type": "string"},
        "working": {"type": "string"},
        "confidence": {"type": "number"},
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ISSUE_TYPES},
                    "detail": {"type": "string"},
                },
                "required": ["type", "detail"],
            },
        },
    },
    "required": ["answer", "value", "working", "confidence", "issues"],
}


@dataclass(frozen=True)
class Solve:
    solver: str  # "A" | "B"
    model: str
    answer: str | tuple[str, ...] | None  # normalized like the stored key
    value: str
    working: str
    confidence: float
    issues: tuple[dict, ...]
    code: tuple[str, ...]
    prompt_version: int

    def has_issue(self, kind: str) -> bool:
        return any(i.get("type") == kind for i in self.issues)


def render_question(q: Question, question_html: str | None = None) -> str:
    """Question as the solvers see it: subject, type, stem, options. No key, no solution."""
    shown = q if question_html is None else _with_html(q, question_html)
    stem, opts = options_of(shown)
    lines = [
        f"Subject: {q.subject or 'unknown'}",
        f"Type: {TYPE_NAMES.get(q.qtype, q.qtype)}",
        "",
        "Question:",
        stem,
    ]
    if q.qtype != "integerQuestion":
        lines += ["", "Options:"]
        for letter in LETTERS:
            if letter in opts:
                lines.append(f"({letter}) {opts[letter] or '[this option is blank]'}")
            else:
                lines.append(f"({letter}) [this option is missing]")
    return "\n".join(lines)


def _with_html(q: Question, question_html: str) -> Question:
    import dataclasses

    return dataclasses.replace(q, question_html=question_html)


def normalize_answer(qtype: str, raw: object) -> str | tuple[str, ...] | None:
    if raw is None:
        return None
    if qtype == "integerQuestion":
        m = re.search(r"-?\d+(?:\.\d+)?", str(raw))
        return _clean_number(m.group(0)) if m else None
    items = raw if isinstance(raw, list) else [raw]
    letters = sorted({x for item in items for x in re.findall(r"\b([A-D])\b", str(item).upper())})
    if not letters:
        return None
    if qtype == "scq":
        return letters[0] if len(letters) == 1 else tuple(letters)
    return tuple(letters)


def _clean_number(s: str) -> str:
    return s.rstrip("0").rstrip(".") if "." in s else s


def _to_solve(solver: str, result: llm.LLMResult, qtype: str, version: int) -> Solve:
    data = result.data if isinstance(result.data, dict) else {}
    conf = data.get("confidence")
    return Solve(
        solver=solver,
        model=result.model,
        answer=normalize_answer(qtype, data.get("answer")),
        value=str(data.get("value") or ""),
        working=str(data.get("working") or ""),
        confidence=float(conf) if isinstance(conf, (int, float)) else 0.0,
        issues=tuple(i for i in data.get("issues") or [] if isinstance(i, dict)),
        code=result.code,
        prompt_version=version,
    )


def solve_a(
    q: Question,
    settings: Settings | None = None,
    question_html: str | None = None,
    model: str | None = None,
) -> Solve:
    settings = settings or load_settings()
    p = prompts.load("solver_a")
    res = llm.call(
        purpose="solve_a",
        model=model or settings.solver_a,
        system=p.text,
        user=render_question(q, question_html),
        schema=SOLVE_SCHEMA,
        settings=settings,
    )
    return _to_solve("A", res, q.qtype, p.version)


def solve_b(
    q: Question,
    settings: Settings | None = None,
    question_html: str | None = None,
    model: str | None = None,
) -> Solve:
    settings = settings or load_settings()
    p = prompts.load("solver_b")
    res = llm.call(
        purpose="solve_b",
        model=model or settings.solver_b,
        system=p.text,
        user=render_question(q, question_html),
        code_execution=True,
        settings=settings,
    )
    return _to_solve("B", res, q.qtype, p.version)
