"""Is the question inside the official NEET UG syllabus? Two models judge; code checks the citation.

The official NMC text lives in engine/reference/ with its source. A model's "closest line"
only counts if it appears verbatim in that text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from engine import llm, prompts
from engine.confidence import Check
from engine.config import Settings
from engine.models import Question
from engine.solve import render_question

REFERENCE = Path(__file__).resolve().parent / "reference" / "nmc_neet_ug_2026_syllabus.txt"
SOURCE = "NMC NEET (UG)-2026 syllabus, U-14023/19/NEET (UG Exam)/UGMEB, 22-12-2025"
_SECTIONS = {
    "PHYSICS": ("PHYSICS", "CHEMISTRY"),
    "CHEMISTRY": ("CHEMISTRY", "BIOLOGY"),
    "BIOLOGY": ("BIOLOGY", None),
}
_NOISE = re.compile(r"^(File No\.|Generated from eOffice|DFA/|\d+\s*$|\d+/\d+/UGMEB)")
SCHEMA = {
    "type": "object",
    "properties": {
        "concept_tested": {"type": "string"},
        "covered": {"type": "boolean"},
        "closest_line": {"type": "string"},
        "reason": {"type": "string"},
    },
    "required": ["concept_tested", "covered", "closest_line", "reason"],
}


@dataclass(frozen=True)
class SyllabusResult:
    covered: bool | None  # None = the two models disagree
    concept: str
    closest_line: str
    reason: str
    checks: tuple[Check, ...]


def section_for(subject: str | None) -> str:
    name = (subject or "").upper()
    key = "BIOLOGY" if name in {"BOTANY", "ZOOLOGY", "BIOLOGY"} else name
    start, end = _SECTIONS.get(key, ("PHYSICS", None))
    lines = REFERENCE.read_text(encoding="utf-8").splitlines()
    begin = next(i for i, ln in enumerate(lines) if ln.strip() == start)
    stop = next(
        (
            i
            for i, ln in enumerate(lines[begin + 1 :], begin + 1)
            if end and ln.strip().startswith(end)
        ),
        len(lines),
    )
    kept = [ln for ln in lines[begin:stop] if not _NOISE.match(ln.strip())]
    return "\n".join(kept)


def _squash(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def check_syllabus(q: Question, settings: Settings) -> SyllabusResult:
    p = prompts.load("syllabus")
    text = section_for(q.subject)
    user = f"{render_question(q)}\n\nOfficial syllabus ({SOURCE}):\n{text}"
    verdicts = []
    for model in (settings.reviewer, settings.confirmer):
        res = llm.call(
            purpose="syllabus",
            model=model,
            system=p.text,
            user=user,
            schema=SCHEMA,
            settings=settings,
        )
        verdicts.append((model, res.data if isinstance(res.data, dict) else {}))
    (m1, first), (m2, second) = verdicts
    c1, c2 = bool(first.get("covered")), bool(second.get("covered"))
    line = str(first.get("closest_line") or "")
    quoted = bool(line) and _squash(line) in _squash(text)
    covered = c1 if c1 == c2 else None

    def say(c):
        return "covered" if c else "not covered"

    target = covered if covered is not None else False  # decision under review: "not covered"
    checks: list[Check] = [
        (f"{m1}: {say(c1)} ({first.get('concept_tested', '')})", c1 == target),
        (f"{m2}: {say(c2)} ({second.get('concept_tested', '')})", c2 == target),
        ("code: closest syllabus line found verbatim in the official text", quoted),
    ]
    return SyllabusResult(
        covered,
        str(first.get("concept_tested") or ""),
        line,
        str(first.get("reason") or ""),
        tuple(checks),
    )
