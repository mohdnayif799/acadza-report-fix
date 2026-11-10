"""Evidence for one question: checks + two solves + reviewer -> candidate defects with edits.

A candidate is a possible defect with its proposed surgical edit and whether its effect on
the answer is independently proven. Reports later pick the candidate that matches their
claim; candidates no report picks become the bonus list.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass

from engine.checks import AnswerCheck
from engine.confidence import Check, score
from engine.models import Finding, Question
from engine.review import Review
from engine.solve import Solve

# Lower index = more urgent. Used to rank candidates and the console queue.
TOPIC_ORDER = [
    "answer",
    "type",
    "unsound",
    "option_keyed",
    "stem_data",
    "figure",
    "solution",
    "option",
    "identical",
    "markup",
    "notation",
    "unit",
    "spelling",
    "exam_tag",
    "noise",
    "chapter",
]
_LATEX_SYMBOLS = {
    r"\AA": "Å",
    r"\times": "×",
    r"\alpha": "α",
    r"\beta": "β",
    r"\theta": "θ",
    r"\lambda": "λ",
    r"\mu": "μ",
    r"\pi": "π",
    r"\omega": "ω",
    r"\Delta": "Δ",
}
_MATH = '<math xmlns="http://www.w3.org/1998/Math/MathML" display="inline">{}</math>'


@dataclass(frozen=True)
class Candidate:
    topic: str
    repair: str
    edit: dict | None
    proven: bool
    confidence: float  # always score(checks); build with Candidate.of
    evidence: str
    source: str  # "check" | "solvers" | "reviewer"
    checks: tuple[Check, ...] = ()
    extra_edits: tuple[dict, ...] = ()

    @classmethod
    def of(
        cls,
        topic: str,
        repair: str,
        edit: dict | None,
        proven: bool,
        checks: list[Check],
        evidence: str,
        source: str,
        extra_edits: tuple[dict, ...] = (),
    ) -> Candidate:
        return cls(
            topic, repair, edit, proven, score(checks), evidence, source, tuple(checks), extra_edits
        )


@dataclass(frozen=True)
class Evidence:
    question: Question
    findings: tuple[Finding, ...]
    key: AnswerCheck
    solve_a: Solve
    solve_b: Solve
    review: Review
    key_status: str  # confirmed | wrong | unsound | unclear
    consensus: str | tuple[str, ...] | None
    candidates: tuple[Candidate, ...]

    def by_topic(self, topic: str) -> list[Candidate]:
        return [c for c in self.candidates if c.topic == topic]


# ---------- comparison helpers ----------


def same_answer(a: object, b: object) -> bool:
    if a is None or b is None:
        return False
    if isinstance(a, str) and isinstance(b, str):
        try:
            x, y = float(a), float(b)
            return abs(x - y) <= 1e-6 * max(1.0, abs(x), abs(y))
        except ValueError:
            return a.strip().upper() == b.strip().upper()

    def as_t(v):
        return tuple(v) if isinstance(v, (tuple, list)) else (v,)

    return tuple(sorted(as_t(a))) == tuple(sorted(as_t(b)))


def same_value(a: str, b: str) -> bool:
    def norm(s):
        return re.sub(r"[\s()]", "", s.replace("−", "-").lower())

    return bool(a.strip()) and norm(a) == norm(b)


def fmt_answer(a: object) -> str:
    if isinstance(a, (tuple, list)):
        return ", ".join(a)
    return str(a)


def describe_solves(ev_a: Solve, ev_b: Solve) -> str:
    return (
        f"Solver A ({ev_a.model}) gets {fmt_answer(ev_a.answer)} ({ev_a.value}); "
        f"solver B ({ev_b.model} + Python) gets {fmt_answer(ev_b.answer)} ({ev_b.value})"
    )


def key_status(
    q: Question, key: AnswerCheck, a: Solve, b: Solve, findings: tuple[Finding, ...]
) -> tuple[str, object]:
    option_gap = any(f.code in {"blank_option", "missing_option"} for f in findings)
    if a.answer is not None and same_answer(a.answer, b.answer):
        return ("confirmed" if same_answer(a.answer, key.normalized) else "wrong"), a.answer
    no_fit = {"no_matching_option", "multiple_correct"}
    if not option_gap and any(map(a.has_issue, no_fit)) and any(map(b.has_issue, no_fit)):
        return "unsound", None
    return "unclear", None


# ---------- raw HTML anchoring ----------


def locate(raw: str, quote: str) -> str | None:
    """Exact raw-HTML substring for a quote taken from the clean text, if it is unique."""
    if not quote:
        return None
    variants = [
        quote,
        html.escape(quote, quote=False),
        quote.replace("’", "&rsquo;"),
        quote.replace("'", "&#39;"),
        quote.replace(" ", "&nbsp;", 1),
    ]
    for v in variants:
        if raw.count(v) == 1:
            return v
    return None


def anchored_edit(q: Question, field: str, quote: str, fix: str) -> dict | None:
    raw = q.field_value(field)
    found = locate(raw, quote)
    if found is None or not fix or fix == quote:
        return None
    replace = fix if found == quote else html.escape(fix, quote=False)
    return {"field": field, "find": found, "replace": replace}


def latex_to_mathml(latex: str) -> str | None:
    m = re.fullmatch(r"\\d?frac\{([^{}]+)\}\{([^{}]+)\}", latex)
    if m:
        num, den = (
            f"<mn>{x}</mn>" if re.fullmatch(r"\d+", x) else f"<mi>{x}</mi>" for x in m.groups()
        )
        return _MATH.format(f"<mfrac>{num}{den}</mfrac>")
    return _LATEX_SYMBOLS.get(latex)


def ratio_mathml(value: str) -> str | None:
    m = re.fullmatch(r"\s*(\d+)\s*:\s*(\d+)\s*", value)
    if not m:
        return None
    return _MATH.format(f"<mrow><mn>{m.group(1)}</mn><mi>:</mi><mn>{m.group(2)}</mn></mrow>")


def blank_option_edit(q: Question, letter: str, value: str) -> dict | None:
    m = re.search(rf"\({letter}\)((?:\s|&nbsp;)*)(<br\s*/?>)", q.question_html)
    if not m or q.question_html.count(m.group(0)) != 1:
        return None
    content = ratio_mathml(value) or html.escape(value.strip(), quote=False)
    return {"field": "question", "find": m.group(0), "replace": f"({letter}) {content}{m.group(2)}"}
