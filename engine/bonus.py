"""Defects nobody reported: every candidate that no report's row used.

Each entry says how it was verified: an edit anchored once in the raw HTML that passes the
guard, a code check on the raw HTML, or model judgement only.
"""

from __future__ import annotations

import json
import re

from engine.evidence import TOPIC_ORDER, Candidate, Evidence
from engine.guard import edit_problems


def _key(c: Candidate | dict) -> str:
    d = c if isinstance(c, dict) else {"topic": c.topic, "edit": c.edit, "evidence": c.evidence}
    return json.dumps([d["topic"], d["edit"], d["evidence"]], sort_keys=True, ensure_ascii=False)


def _detail(evidence: str) -> str:
    """Reviewer evidence is "<detail> ('<quote>' -> '<fix>')...": the part before the quote."""
    return re.split(r" \('", evidence, maxsplit=1)[0]


def _verified(c: Candidate, problems: list[str]) -> str:
    if c.edit and not problems:
        return "edit anchored once in the raw HTML and passes the guard"
    if c.source == "check":
        return "found by a code check on the raw HTML"
    return "model judgement; checked by hand against the raw HTML (see build log)"


def _skip(c: Candidate, qid: str, chosen: set[str], rewritten: set, has_amp: bool) -> bool:
    if _key(c) in chosen or (c.topic == "answer" and c.edit is None):
        return True  # used by a report, or "answer unclear" (that is a review, not a defect)
    if c.edit and (qid, c.edit["field"]) in rewritten:
        return True  # the field is replaced wholesale by a chosen fix
    # The reviewer re-reporting the code-found '&' alignment leak as noise/notation.
    return has_amp and c.source == "reviewer" and "&" in c.evidence and c.topic != "spelling"


def bonus_defects(
    evidence: dict[str, Evidence], chosen: list[dict], rows: list[dict], taxonomy: dict
) -> list[dict]:
    chosen_keys = {_key(c) for c in chosen if c}
    rewritten = {
        (r["questionId"], r["edit"]["field"])
        for r in rows
        if r["edit"]
        and r["edit"]["field"] in ("question", "solution")
        and r["edit"]["find"] == evidence[r["questionId"]].question.field_value(r["edit"]["field"])
    }
    merged: dict[tuple, dict] = {}
    for qid, ev in evidence.items():
        has_amp = any("alignment '&'" in c.evidence for c in ev.candidates)
        for c in ev.candidates:
            if _skip(c, qid, chosen_keys, rewritten, has_amp):
                continue
            problems = edit_problems(c.edit, c.repair, ev.question, taxonomy) if c.edit else []
            key = (qid, c.repair, _detail(c.evidence) if c.edit is None else _key(c))
            if key in merged:
                merged[key]["occurrences"] += 1
                merged[key]["evidence"] += f" | {c.evidence}"
                continue
            merged[key] = {
                "questionId": qid,
                "subject": ev.question.subject,
                "chapter": ev.question.chapter,
                "repair": c.repair,
                "topic": c.topic,
                "auto": taxonomy["repairs"][c.repair]["auto"],
                "confidence": c.confidence,
                "evidence": c.evidence,
                "edit": c.edit,
                "occurrences": 1,
                "source": c.source,
                "verified": _verified(c, problems),
                "guard_problems": problems,
            }
    out = list(merged.values())
    out.sort(key=lambda d: (TOPIC_ORDER.index(d["topic"]), -d["confidence"]))
    return out
