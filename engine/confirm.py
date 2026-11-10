"""Second opinion on a proposed text defect, from a different model than the reviewer."""

from __future__ import annotations

from dataclasses import dataclass

from engine import llm, prompts
from engine.config import Settings
from engine.models import Question
from engine.parse import html_to_text
from engine.solve import render_question

CONFIRM_SCHEMA = {
    "type": "object",
    "properties": {
        "is_defect": {"type": "boolean"},
        "fix_is_correct": {"type": "boolean"},
        "changes_only_the_defect": {"type": "boolean"},
        "reason": {"type": "string"},
    },
    "required": ["is_defect", "fix_is_correct", "changes_only_the_defect", "reason"],
}


@dataclass(frozen=True)
class Confirmation:
    agrees: bool
    reason: str
    model: str


def confirm(
    q: Question,
    kind: str,
    quote: str,
    fix: str | None,
    settings: Settings,
    include_solution: bool = True,
) -> Confirmation:
    p = prompts.load("confirm")
    parts = [render_question(q)]
    if include_solution:
        parts.append("Stored solution:\n" + (html_to_text(q.solution_html) or "[none]"))
    shown_fix = html_to_text(fix) if fix and "<" in fix else (fix or "n/a")
    parts.append(f"Defect type: {kind}\nQuoted text: {quote}\nProposed replacement: {shown_fix}")
    res = llm.call(
        purpose="confirm",
        model=settings.confirmer,
        system=p.text,
        user="\n\n".join(parts),
        schema=CONFIRM_SCHEMA,
        settings=settings,
    )
    d = res.data if isinstance(res.data, dict) else {}
    ok = (
        bool(d.get("is_defect"))
        and bool(d.get("fix_is_correct"))
        and bool(d.get("changes_only_the_defect"))
    )
    return Confirmation(ok, str(d.get("reason") or ""), res.model)
