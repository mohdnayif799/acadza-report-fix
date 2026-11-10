"""Write a replacement solution that ends in the (independently confirmed) key."""

from __future__ import annotations

import re

from engine import llm, prompts
from engine.checks import AnswerCheck, options_of
from engine.config import Settings
from engine.models import Question
from engine.solve import render_question


def write_solution(q: Question, key: AnswerCheck, settings: Settings) -> str | None:
    if key.normalized is None:
        return None
    letters = key.normalized if isinstance(key.normalized, tuple) else (key.normalized,)
    opts = options_of(q)[1]
    keyed = ", ".join(f"({x}) {opts.get(x, '')}".strip() for x in letters)
    p = prompts.load("solution_writer")
    user = f"{render_question(q)}\n\nAnswer key (confirmed by two independent solvers): {keyed}"
    res = llm.call(
        purpose="write_solution",
        model=settings.reviewer,
        system=p.text,
        user=user,
        settings=settings,
    )
    text = res.text.strip()
    if "CANNOT_CONFIRM" in text or not re.fullmatch(r"<h3>.*</h3>", text, re.S):
        return None
    last_line = re.split(r"<br\s*/?>", text)[-1]
    if q.qtype != "integerQuestion" and not all(f"({x})" in last_line for x in letters):
        return None  # must end in the keyed answer
    return text
