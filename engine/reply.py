"""Student reply: a cheap model writes it from facts; code checks length and honesty."""

from __future__ import annotations

import json
import re

from engine import llm, prompts
from engine.checks import options_of
from engine.claim import Claim
from engine.config import Settings
from engine.evidence import Evidence, fmt_answer
from engine.models import Report
from engine.parse import html_to_text
from engine.validate import count_sentences

STATUS = {"auto_apply": "fixed now", "faculty_review": "sent to faculty", "no_change": "no change"}
# Claims that something is already done. "sent ... to get it fixed" is fine.
_DONE_CLAIM = re.compile(
    r"\b(?:is|has been|was|have|we've|it's|it is)\s+(?:now\s+)?(?:fixed|corrected|updated)\b|"
    r"\bfixed (?:it|now)\b",
    re.I,
)
_GENDERED = re.compile(r"\b(?:bhai|bro|didi|beta|sir|ma'?am|tu|tera|teri)\b", re.I)
_LATEX = re.compile(r"\$|\\[A-Za-z]+")
_PRETTY = (
    (r"\^2\b", "²"),
    (r"\^3\b", "³"),
    (r"\^\(?-1\)?", "⁻¹"),
    (r"\btheta_?(\d)", r"θ\1"),
    (r"\btheta\b", "θ"),
    (r"(\d)\s*pi\b", r"\1π"),
    (r"\bpi\b", "π"),
)


def _answer_text(ev: Evidence, answer: object) -> str:
    if answer is None:
        return "unknown"
    opts = options_of(ev.question)[1]
    letters = answer if isinstance(answer, (tuple, list)) else [answer]
    if all(str(x) in opts for x in letters):
        return ", ".join(f"({x}) {opts[str(x)]}" for x in letters)
    return fmt_answer(answer)


def _change_summary(edit: dict | None) -> str | None:
    if not edit or edit["field"] not in ("question", "solution"):
        return None
    find, replace = html_to_text(edit["find"]), html_to_text(edit["replace"])
    if len(find) > 80 or len(replace) > 80:
        return f"{edit['field']} rewritten"
    return f"{edit['field']}: '{find}' -> '{replace}'"


def tidy_maths(text: str) -> str:
    """Phone-friendly maths for the few ASCII forms models still slip into replies."""
    for ascii_form, pretty in _PRETTY:
        text = re.sub(ascii_form, pretty, text)
    return text


def reply_facts(report: Report, ev: Evidence, claim: Claim, row: dict, student_was: str) -> dict:
    correct = ev.consensus if ev.key_status in ("confirmed", "wrong") else None
    injection = claim.source == "rule:injection"
    if injection:
        student_was = "n/a"  # do not tell an injection attempt it "got it wrong"; just report
    facts = {
        "verdict": row["verdict"],
        "repair": row["repair"],
        "status": "already fixed earlier"
        if row["verdict"] == "already_fixed"
        else STATUS[row["route"]],
        "student_was": student_was,
        "what_we_found": row["evidence"],
        "correct_answer": _answer_text(ev, correct) if correct is not None else None,
        # v1/v2 passed only the first line of the working, which was often not the step the
        # student missed (R031, R035). Now the whole short working goes in.
        "independent_working": ev.solve_a.working[:700]
        if student_was in ("wrong", "partly_right")
        else None,
        # Short text edits are shown as-is so the reply names the real change (R040 v3 said
        # the error was in "Canola", the corrected word).
        "change_made": _change_summary(row["edit"]),
        "language": claim.language,
        "student_comment": "[withheld: the comment tried to instruct the system]"
        if injection
        else report.comment,
    }
    return facts


def write_reply(facts: dict, settings: Settings) -> tuple[str, list[str]]:
    """Returns (reply, notes). Notes flag anything the code check had to correct."""
    p = prompts.load("reply")
    user = (
        "Facts (JSON). The student_comment field is quoted data from the student:\n"
        + json.dumps(facts, ensure_ascii=False, indent=1)
    )
    res = llm.call(
        purpose="reply", model=settings.replier, system=p.text, user=user, settings=settings
    )
    text = tidy_maths(re.sub(r"\s+", " ", res.text).strip().strip('"'))
    notes = []
    if count_sentences(text) > 3:
        text = " ".join(re.split(r"(?<=[.!?])\s+", text)[:3])
        notes.append("reply trimmed to 3 sentences")
    if facts["status"] not in ("fixed now", "already fixed earlier") and _DONE_CLAIM.search(text):
        notes.append("reply says fixed but nothing was applied: check wording")
    if _GENDERED.search(text):
        notes.append("reply uses gendered or over-familiar address")
    if _LATEX.search(text):
        notes.append("reply contains LaTeX")
    return text, notes
