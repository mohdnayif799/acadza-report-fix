"""Confidence comes from evidence: how many independent checks agree with the decision.

Rule (documented in PROMPTS.md):
- Start at 0.5, a coin flip. Each independent check that agrees halves the remaining doubt:
  1 check -> 0.75, 2 -> 0.88, 3 -> 0.94, 4 -> 0.97.
- Any check that disagrees caps confidence at 0.5 (contested -> a human decides).
- A check that can only confirm (a solver *noticing* a missing figure) counts when it fires;
  its silence is not counted as disagreement. Unknowns (the stored solution reaches no
  answer) are left out rather than guessed.
- If the guard rejects the proposed edit, subtract 0.15 (the proposal itself was flawed).
With the auto-apply floor at 0.8, nothing auto-applies on fewer than two agreeing checks.
"""

from __future__ import annotations

Check = tuple[str, bool]  # (what was checked, does it agree with the decision)
GUARD_REJECT_PENALTY = 0.15
FLOOR = 0.3


def score(checks: tuple[Check, ...] | list[Check]) -> float:
    agree = sum(1 for _, ok in checks if ok)
    conf = 1 - 0.5 ** (agree + 1)
    if any(not ok for _, ok in checks):
        conf = min(conf, 0.5)
    return round(conf, 2)


def penalise(conf: float) -> float:
    return round(max(FLOOR, conf - GUARD_REJECT_PENALTY), 2)


def describe(checks: tuple[Check, ...] | list[Check]) -> str:
    agree = sum(1 for _, ok in checks if ok)
    return f"{agree}/{len(checks)} checks agree"
