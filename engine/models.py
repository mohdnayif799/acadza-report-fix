"""Plain data types shared across the engine. All frozen: stages return new objects."""

from __future__ import annotations

import json
from dataclasses import dataclass
from dataclasses import field as dc_field
from datetime import datetime
from pathlib import Path
from typing import Any

TEXT_FIELDS = ("question", "solution")  # find/replace on substrings; other fields match whole
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value)


@dataclass(frozen=True)
class Question:
    id: str
    qid: str | None
    qtype: str  # "scq" | "mcq" | "integerQuestion"
    subject: str | None
    chapter: str | None
    concept: str | None
    sub_concept: str | None
    level: str | None
    question_html: str
    solution_html: str
    answer: Any  # str for scq/integer, list for mcq (as stored, possibly malformed)
    ques_images: tuple[str, ...]
    solution_images: tuple[str, ...]
    updated_at: str
    error_history: tuple[dict, ...]

    def field_value(self, name: str) -> Any:
        """Current value of a taxonomy field name (question/solution/answer/questionType)."""
        values = {
            "question": self.question_html,
            "solution": self.solution_html,
            "answer": self.answer,
            "questionType": self.qtype,
        }
        if name not in values:
            raise KeyError(f"unknown field {name!r}")
        return values[name]


@dataclass(frozen=True)
class Report:
    report_id: str
    question_id: str
    student_id: str
    source: str
    reported_at: str
    comment: str


@dataclass(frozen=True)
class Finding:
    """One deterministic observation about a question or report."""

    code: str  # e.g. "blank_option", "exam_tag"
    detail: str  # human-readable, goes into evidence
    repair: str | None = None  # suggested taxonomy repair, if this is a defect
    field: str | None = None  # taxonomy field it lives in
    find: str | None = None  # exact raw substring that shows it (for edits / verification)
    extra: dict = dc_field(default_factory=dict)


def _question_from_raw(raw: dict) -> Question:
    qtype = raw["questionType"]
    body = raw.get(qtype) or {}
    return Question(
        id=raw["_id"],
        qid=raw.get("qid"),
        qtype=qtype,
        subject=raw.get("subject"),
        chapter=raw.get("chapter"),
        concept=raw.get("concept"),
        sub_concept=raw.get("subConcept"),
        level=raw.get("level"),
        question_html=body.get("question") or "",
        solution_html=body.get("solution") or "",
        answer=body.get("answer"),
        ques_images=tuple(body.get("quesImages") or ()),
        solution_images=tuple(body.get("solutionImages") or ()),
        updated_at=raw.get("updatedAt") or "",
        error_history=tuple(raw.get("errorHistory") or ()),
    )


def load_questions(path: Path = DATA_DIR / "questions.json") -> dict[str, Question]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {q["_id"]: _question_from_raw(q) for q in raw}


def load_reports(path: Path = DATA_DIR / "reports.json") -> list[Report]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [
        Report(
            report_id=r["reportId"],
            question_id=r["questionId"],
            student_id=r["studentId"],
            source=r["source"],
            reported_at=r["reportedAt"],
            comment=r.get("comment") or "",
        )
        for r in raw
    ]


def load_taxonomy(path: Path = DATA_DIR / "taxonomy.json") -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def group_reports(reports: list[Report]) -> dict[str, list[Report]]:
    """Reports per question, oldest first."""
    groups: dict[str, list[Report]] = {}
    for r in sorted(reports, key=lambda r: parse_time(r.reported_at)):
        groups.setdefault(r.question_id, []).append(r)
    return groups
