"""Validate results.json against the brief and the taxonomy.

Usage:  python -m engine.validate [path/to/results.json]   (exit code 1 on any error)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from engine.guard import BRIEF_KEYS, EDIT_KEYS, ROUTES
from engine.models import (
    ROOT,
    TEXT_FIELDS,
    Question,
    Report,
    load_questions,
    load_reports,
    load_taxonomy,
)

_SENTENCE_END = re.compile(r"(?<=[.!?।])\s+")


def count_sentences(text: str) -> int:
    return len([s for s in _SENTENCE_END.split(text.strip()) if s.strip()])


def _edit_errors(rid: str, row: dict, q: Question, taxonomy: dict) -> list[str]:
    edit, repair = row["edit"], row["repair"]
    if edit is None:
        return [f"{rid}: auto_apply without an edit"] if row["route"] == "auto_apply" else []
    if not isinstance(edit, dict) or set(edit) != EDIT_KEYS:
        return [f"{rid}: edit must have exactly the keys {sorted(EDIT_KEYS)}"]
    if repair is None:
        return [f"{rid}: edit present but repair is null"]
    allowed = taxonomy["repairs"][repair]["fields"]
    if edit["field"] not in allowed:
        return [f"{rid}: edit field {edit['field']!r} not allowed for {repair} {allowed}"]
    current = q.field_value(edit["field"])
    if edit["field"] in TEXT_FIELDS:
        if not isinstance(edit["find"], str) or current.count(edit["find"]) != 1:
            return [f"{rid}: edit.find does not occur exactly once in {edit['field']}"]
    elif edit["find"] != current:
        return [f"{rid}: edit.find {edit['find']!r} != current {edit['field']} {current!r}"]
    return []


def _row_errors(row: dict, report: Report, q: Question, taxonomy: dict) -> list[str]:
    rid = report.report_id
    if not isinstance(row, dict) or tuple(row) != BRIEF_KEYS:
        got = list(row) if isinstance(row, dict) else type(row).__name__
        return [f"{rid}: keys must be exactly {list(BRIEF_KEYS)} in order, got {got}"]
    errors = []
    if row["questionId"] != report.question_id:
        errors.append(f"{rid}: questionId does not match reports.json")
    verdict, repair, route = row["verdict"], row["repair"], row["route"]
    if verdict not in taxonomy["verdicts"]:
        errors.append(f"{rid}: verdict {verdict!r} not in taxonomy")
    if repair is not None and repair not in taxonomy["repairs"]:
        errors.append(f"{rid}: repair {repair!r} not in taxonomy")
    if route not in ROUTES:
        errors.append(f"{rid}: route {route!r} not allowed")
    if (verdict == "defect") != (repair is not None):
        errors.append(f"{rid}: repair must be set if and only if verdict is defect")
    if verdict != "defect" and (route != "no_change" or row["edit"] is not None):
        errors.append(f"{rid}: non-defect rows must be no_change with no edit")
    if verdict == "defect" and route == "no_change":
        errors.append(f"{rid}: a defect cannot be no_change")
    if (
        repair in taxonomy["repairs"]
        and not taxonomy["repairs"][repair]["auto"]
        and route == "auto_apply"
    ):
        errors.append(f"{rid}: {repair} is auto: false but route is auto_apply")
    conf = row["confidence"]
    if isinstance(conf, bool) or not isinstance(conf, (int, float)) or not 0 <= conf <= 1:
        errors.append(f"{rid}: confidence must be a number in [0, 1]")
    if not isinstance(row["evidence"], str) or not row["evidence"].strip():
        errors.append(f"{rid}: evidence is empty")
    reply = row["student_reply"]
    if not isinstance(reply, str) or not 1 <= count_sentences(reply) <= 3:
        errors.append(f"{rid}: student_reply must be 1-3 sentences")
    if not errors and repair in taxonomy["repairs"]:
        errors += _edit_errors(rid, row, q, taxonomy)
    return errors


def validate_results(
    rows: object, reports: list[Report], questions: dict[str, Question], taxonomy: dict
) -> list[str]:
    if not isinstance(rows, list):
        return ["results must be a JSON array"]
    by_id = {r.report_id: r for r in reports}
    seen: set[str] = set()
    errors = []
    for row in rows:
        rid = row.get("reportId") if isinstance(row, dict) else None
        if rid not in by_id:
            errors.append(f"unknown reportId {rid!r}")
            continue
        if rid in seen:
            errors.append(f"duplicate reportId {rid}")
        seen.add(rid)
        report = by_id[rid]
        errors += _row_errors(row, report, questions[report.question_id], taxonomy)
    missing = sorted(set(by_id) - seen)
    if missing:
        errors.append(f"missing {len(missing)} report(s): {', '.join(missing)}")
    return errors


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else ROOT / "results.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    errors = validate_results(rows, load_reports(), load_questions(), load_taxonomy())
    for e in errors:
        print("ERROR", e)
    print(f"{path.name}: {len(rows) if isinstance(rows, list) else 0} rows, {len(errors)} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
