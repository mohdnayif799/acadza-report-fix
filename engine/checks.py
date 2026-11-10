"""Deterministic checks. No LLM. Every finding carries the raw substring that proves it."""

from __future__ import annotations

import re
from dataclasses import dataclass

from engine.models import Finding, Question, Report, parse_time
from engine.parse import html_to_text, split_options

LETTERS = "ABCD"

_LATEX = re.compile(
    r"\\(?:frac|dfrac|sqrt|times|cdot|left|right|alpha|beta|gamma|theta|lambda|mu|pi|"
    r"omega|Delta|AA|circ|text|mathrm|vec|hat|over)\b(?:\{[^{}]*\}){0,2}"
)
_ALIGN_AMP = re.compile(r"<mi>\s*&(?:amp;)?\s*</mi>")
EXAM_TAG = re.compile(
    r"\(\s*(?:NEET|AIPMT|AIIMS|JEE(?:\s+(?:Main|Mains|Advanced|Adv))?|MHT[- ]?CET|BITSAT|KCET|"
    r"EAMCET|CBSE)[^()]{0,20}?\b(?:19|20)\d{2}\s*\)\s?",
    re.I,
)
_FIGURE_REF = re.compile(r"\b(?:figure|fig\.|diagram|shown below|as shown)\b", re.I)
_UNIT_STATED = re.compile(
    r"\(in\s|\bin\s+(?:cm|mm|m|km|s|sec|seconds?|volts?|V|N|newtons?|dioptres?|diopters?|kg|g|J|"
    r"eV|Hz|K|°C|A|ampere|ohm|Ω|W|watt|Pa|mol|L)\b|_{2,}\s*\S",
    re.I,
)
_DIMENSIONLESS = re.compile(r"\b(?:value of|ratio|number of|how many|integer)\b", re.I)


@dataclass(frozen=True)
class AnswerCheck:
    normalized: str | tuple[str, ...] | None  # str for scq/integer, tuple for mcq, None if unusable
    problems: tuple[str, ...]


def options_of(q: Question) -> tuple[str, dict[str, str]]:
    return split_options(html_to_text(q.question_html))


def check_answer(q: Question) -> AnswerCheck:
    a = q.answer
    if q.qtype == "scq":
        if isinstance(a, str) and a.strip().upper() in LETTERS and len(a.strip()) == 1:
            return AnswerCheck(a.strip().upper(), ())
        return AnswerCheck(None, (f"scq answer {a!r} is not a single letter A-D",))
    if q.qtype == "integerQuestion":
        if isinstance(a, str) and re.fullmatch(r"-?\d+(?:\.\d+)?", a.strip()):
            return AnswerCheck(a.strip(), ())
        return AnswerCheck(None, (f"integer answer {a!r} is not a number",))
    if q.qtype == "mcq":
        return _check_mcq_answer(a)
    return AnswerCheck(None, (f"unknown questionType {q.qtype!r}",))


def _check_mcq_answer(a: object) -> AnswerCheck:
    if not isinstance(a, list):
        return AnswerCheck(None, (f"mcq answer {a!r} is not a list",))
    problems = []
    letters: list[str] = []
    for item in a:
        if not isinstance(item, str) or not item.strip():
            problems.append(f"empty entry {item!r} in mcq answer")
            continue
        parts = [p.strip().upper() for p in re.split(r"[,\s]+", item) if p.strip()]
        if len(parts) > 1:
            problems.append(f"several letters packed into one entry {item!r}")
        for p in parts:
            if p not in LETTERS:
                problems.append(f"{p!r} is not an option letter")
            elif p not in letters:
                letters.append(p)
    normalized = tuple(sorted(letters)) if letters else None
    return AnswerCheck(normalized, tuple(problems))


def check_options(q: Question) -> list[Finding]:
    if q.qtype == "integerQuestion":
        return []
    _, opts = options_of(q)
    findings = []
    missing = [x for x in LETTERS if x not in opts]
    if missing:
        findings.append(
            Finding(
                "missing_option",
                f"Option(s) {', '.join(missing)} absent; question shows "
                f"only {', '.join(opts) or 'none'}",
                "option_repair",
                "question",
            )
        )
    for letter, text in opts.items():
        if not text.strip():
            findings.append(
                Finding(
                    "blank_option",
                    f"Option ({letter}) is blank",
                    "option_repair",
                    "question",
                    f"({letter})",
                    {"letter": letter},
                )
            )
    seen: dict[str, str] = {}
    for letter, text in opts.items():
        key = re.sub(r"\s+", " ", text).strip().casefold()
        if key and key in seen:
            findings.append(
                Finding(
                    "identical_options",
                    f"Options ({seen[key]}) and ({letter}) are identical: {text!r}",
                    "identical_options",
                    None,
                    None,
                    {"letters": [seen[key], letter]},
                )
            )
        seen.setdefault(key, letter)
    return findings


def check_answer_field(q: Question) -> list[Finding]:
    ac = check_answer(q)
    findings = [
        Finding("malformed_answer", f"Answer key {q.answer!r}: {p}", "answer_key", "answer")
        for p in ac.problems
    ]
    if q.qtype == "mcq" and ac.normalized and len(ac.normalized) == 1:
        findings.append(
            Finding(
                "single_answer_mcq",
                f"Stored as multiple-correct (mcq) but the key has exactly one "
                f"correct option ({ac.normalized[0]})",
                "type_mismatch",
                "questionType",
                extra={"letter": ac.normalized[0]},
            )
        )
    if q.qtype in ("scq", "mcq") and ac.normalized:
        _, opts = options_of(q)
        keyed = [ac.normalized] if isinstance(ac.normalized, str) else list(ac.normalized)
        for letter in keyed:
            if letter not in opts:
                findings.append(
                    Finding(
                        "key_option_missing",
                        f"Keyed option ({letter}) does not exist in the question",
                        "option_repair",
                    )
                )
            elif not opts[letter].strip():
                findings.append(
                    Finding(
                        "key_option_blank",
                        f"Keyed option ({letter}) is blank, so no student can pick it knowingly",
                        "option_repair",
                    )
                )
    return findings


def check_markup(q: Question) -> list[Finding]:
    findings = []
    for fld, raw in (("question", q.question_html), ("solution", q.solution_html)):
        for m in _LATEX.finditer(raw):
            findings.append(
                Finding(
                    "latex_leak",
                    f"Raw LaTeX {m.group(0)!r} in {fld}",
                    "markup_leak",
                    fld,
                    m.group(0),
                )
            )
        for m in _ALIGN_AMP.finditer(raw):
            findings.append(
                Finding(
                    "align_amp_leak",
                    f"LaTeX alignment '&' rendered as text in {fld} math",
                    "markup_leak",
                    fld,
                    m.group(0),
                )
            )
    return findings


def check_question_text(q: Question) -> list[Finding]:
    findings = []
    m = EXAM_TAG.search(q.question_html)
    if m:
        findings.append(
            Finding(
                "exam_tag",
                f"Exam tag {m.group(0).strip()!r} in question text",
                "exam_reference",
                "question",
                m.group(0),
            )
        )
    stem = options_of(q)[0]
    has_image = bool(q.ques_images) or "<img" in q.question_html.lower()
    if _FIGURE_REF.search(stem) and not has_image:
        findings.append(
            Finding("figure_missing", "Question refers to a figure but has no image", "diagram")
        )
    if not html_to_text(q.solution_html).strip() and not q.solution_images:
        findings.append(
            Finding("solution_missing", "Solution is empty", "solution_missing", "solution")
        )
    if (
        q.qtype == "integerQuestion"
        and not _UNIT_STATED.search(stem)
        and not _DIMENSIONLESS.search(stem)
    ):
        findings.append(
            Finding(
                "unit_not_stated",
                "Integer question does not say which unit the answer is in",
                "answer_form",
                "question",
            )
        )
    return findings


def check_question(q: Question) -> list[Finding]:
    """All question-level checks (independent of any report)."""
    return [*check_options(q), *check_answer_field(q), *check_markup(q), *check_question_text(q)]


def already_fixed(report: Report, q: Question) -> Finding | None:
    """A faculty fix logged in errorHistory *after* the report, and the quoted text is gone."""
    reported = parse_time(report.reported_at)
    later = [e for e in q.error_history if e.get("at") and parse_time(e["at"]) > reported]
    if not later:
        return None
    quoted = re.findall(r"['\"‘’“”]([^'\"‘’“”]{2,40})['\"‘’“”]", report.comment)
    current = html_to_text(q.question_html) + "\n" + html_to_text(q.solution_html)
    still_there = [t for t in quoted if re.search(rf"\b{re.escape(t)}\b", current)]
    if still_there:
        return None
    entry = later[-1]
    return Finding(
        "already_fixed",
        f"Faculty fix logged {entry['at']} ({entry.get('type')}: "
        f"{entry.get('note')}), after this report ({report.reported_at})"
        + (f"; {', '.join(map(repr, quoted))} no longer in the text" if quoted else ""),
        extra={"entry": entry, "quoted": quoted},
    )
