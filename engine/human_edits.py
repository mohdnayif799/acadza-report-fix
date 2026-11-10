"""Human edits to model output, applied after the pipeline so a rerun never loses them.

Each edit is a find/replace on one field of one results row (engine/human_edits.json), with who,
when and why. A find that no longer matches fails loudly instead of being skipped silently.
"""

from __future__ import annotations

import json
from pathlib import Path

EDITS = Path(__file__).resolve().parent / "human_edits.json"
EDITABLE = {"student_reply", "evidence"}


class HumanEditError(ValueError):
    pass


def load_edits(path: Path = EDITS) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def apply_human_edits(rows: list[dict], edits: list[dict]) -> tuple[list[dict], dict[str, list]]:
    """Return new rows with edits applied, plus {reportId: [edit, ...]} for the trace."""
    by_id = {r["reportId"]: dict(r) for r in rows}
    applied: dict[str, list] = {}
    for e in edits:
        row = by_id.get(e["reportId"])
        if row is None or e["field"] not in EDITABLE:
            raise HumanEditError(f"bad human edit target: {e['reportId']} / {e['field']}")
        text = row[e["field"]]
        if text.count(e["find"]) != 1:
            raise HumanEditError(f"{e['reportId']}: {e['find']!r} not found exactly once")
        row[e["field"]] = text.replace(e["find"], e["replace"], 1)
        applied.setdefault(e["reportId"], []).append(e)
    return [by_id[r["reportId"]] for r in rows], applied
