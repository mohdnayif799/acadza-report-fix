"""Build console/data/cases.json from results.json + out/trace.json + data/ (no LLM calls).

Usage: python scripts/build_console_data.py

One case per question (reports grouped). Urgency (lower rank = more urgent):
  1 Answer key wrong  (answer_key, type_mismatch)           students lose marks on every attempt
  2 Unsolvable        (unsound, option_repair, stem_data,   students cannot answer it as shown
                       diagram, identical_options, wrong_question)
  3 Solution wrong    (solution_fix, solution_missing)      students learn a wrong method
  4 Cosmetic          (spelling, markup, exam tag, ...)     readable, but looks careless
  5 Filing            (wrong_chapter, syllabus)             wrong place in the bank
  6 No change         (no defect: reply only)
Within a rank: more reporters first, then the oldest report first.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.checks import options_of  # noqa: E402
from engine.guard import apply_edit  # noqa: E402
from engine.models import load_questions, load_reports, load_taxonomy  # noqa: E402
from engine.parse import html_to_text  # noqa: E402

TIERS = [
    ("Answer key wrong", {"answer_key", "type_mismatch"}),
    (
        "Unsolvable",
        {"unsound", "option_repair", "stem_data", "diagram", "identical_options", "wrong_question"},
    ),
    ("Solution wrong", {"solution_fix", "solution_missing"}),
    ("Cosmetic", {"spelling", "noise", "exam_reference", "markup_leak", "notation", "answer_form"}),
    ("Filing", {"wrong_chapter", "syllabus"}),
]
VERDICT_LABEL = {
    "defect": "Defect",
    "no_error": "No error: the question is correct",
    "display_issue": "Display issue on the device",
    "app_issue": "App issue, not the question",
    "language_mode": "Language request",
    "already_fixed": "Already fixed",
    "not_actionable": "Nothing to act on",
}
REPAIR_LABEL = {
    "answer_key": "Answer key",
    "type_mismatch": "Question type",
    "option_repair": "Option",
    "stem_data": "Missing data in the question",
    "diagram": "Missing figure",
    "unsound": "No valid answer as written",
    "identical_options": "Identical options",
    "wrong_question": "Question and solution mismatch",
    "solution_fix": "Solution",
    "solution_missing": "Missing solution",
    "spelling": "Spelling",
    "noise": "Stray text",
    "exam_reference": "Exam tag in question",
    "markup_leak": "Raw code showing",
    "notation": "Notation",
    "answer_form": "Answer unit",
    "wrong_chapter": "Wrong chapter",
    "syllabus": "Outside syllabus",
}
ROUTE_ORDER = {"faculty_review": 0, "auto_apply": 1, "no_change": 2}
SECTION = {"faculty_review": "decide", "auto_apply": "auto", "no_change": "reply"}
TYPE_LABEL = {"scq": "Single correct", "mcq": "Multiple correct", "integerQuestion": "Numerical"}


PROBLEM = {
    "answer_key": "Answer key wrong",
    "type_mismatch": "Wrong type",
    "stem_data": "Missing data",
    "unsound": "No correct option",
    "diagram": "Figure missing",
    "identical_options": "Identical options",
    "wrong_question": "Wrong solution",
    "solution_fix": "Wrong solution",
    "solution_missing": "Wrong solution",
    "spelling": "Spelling",
    "exam_reference": "Exam tag",
    "markup_leak": "Raw code showing",
    "notation": "Notation",
    "answer_form": "Unit missing",
    "noise": "Stray text",
    "wrong_chapter": "Wrong chapter",
    "syllabus": "Syllabus check",
}
NON_DEFECT = {
    "no_error": "No error",
    "display_issue": "Display issue",
    "app_issue": "App issue",
    "language_mode": "Language request",
    "already_fixed": "Already fixed",
    "not_actionable": "Nothing to act on",
}


def problem(row: dict, findings: list[dict]) -> str:
    """The specific problem in plain words (urgency is shown by order and section)."""
    if row["verdict"] != "defect":
        return NON_DEFECT[row["verdict"]]
    if row["repair"] == "option_repair":
        for f in findings:
            if f["code"] == "missing_option":
                letters = re.findall(
                    r"(?<![A-Za-z])([A-D])(?![A-Za-z])", f["detail"].split("absent")[0]
                )
                return f"Option {' and '.join(letters)} missing"
            if f["code"] == "blank_option":
                return f"Option {f['extra']['letter']} blank"
    return PROBLEM.get(row["repair"], REPAIR_LABEL.get(row["repair"], "Defect"))


def urgency(row: dict) -> tuple[int, str]:
    if row["verdict"] != "defect":
        return 6, "No change"
    for rank, (label, repairs) in enumerate(TIERS, start=1):
        if row["repair"] in repairs:
            return rank, label
    return 4, "Cosmetic"


def answer_text(q, value) -> str:
    opts = options_of(q)[1]
    letters = value if isinstance(value, list) else [value]
    parts = []
    for v in letters:
        s = str(v).strip()
        parts.append(f"({s}) {opts[s]}" if s in opts and opts[s] else (s or "''"))
    return ", ".join(parts) if parts else "(empty)"


def change_view(q, edit: dict | None, extra: list[dict]) -> dict | None:
    if not edit:
        return None
    field = edit["field"]
    if field in ("question", "solution"):
        before = q.field_value(field)
        after = apply_edit(q, edit)
        long = len(edit["find"]) > 160 or len(edit["replace"]) > 160
        return {
            "kind": "text",
            "field": field,
            "layout": "side" if long else "inline",
            "before_html": before,
            "after_html": after,
            "before_text": html_to_text(before),
            "after_text": html_to_text(after),
            "find": edit["find"],
            "replace": edit["replace"],
        }
    rows = [edit, *extra]
    lines = []
    for e in rows:
        if e["field"] == "answer":
            lines.append(
                {
                    "label": "Answer key",
                    "before": answer_text(q, e["find"]),
                    "after": answer_text(q, e["replace"]),
                    "raw_before": e["find"],
                    "raw_after": e["replace"],
                }
            )
        elif e["field"] == "questionType":
            lines.append(
                {
                    "label": "Question type",
                    "before": f"{TYPE_LABEL.get(e['find'], e['find'])} ({e['find']})",
                    "after": f"{TYPE_LABEL.get(e['replace'], e['replace'])} ({e['replace']})",
                    "raw_before": e["find"],
                    "raw_after": e["replace"],
                }
            )
    return {
        "kind": "fields",
        "lines": lines,
        "find": edit["find"],
        "replace": edit["replace"],
        "field": field,
    }


def primary(rows: list[dict]) -> dict:
    return min(rows, key=lambda r: (ROUTE_ORDER[r["route"]], r["verdict"] != "defect"))


def build() -> dict:
    questions, reports, taxonomy = load_questions(), load_reports(), load_taxonomy()
    rows = {r["reportId"]: r for r in json.loads((ROOT / "results.json").read_text("utf-8"))}
    trace = json.loads((ROOT / "out" / "trace.json").read_text("utf-8"))
    by_q: dict[str, list] = {}
    for rep in reports:
        by_q.setdefault(rep.question_id, []).append(rep)
    cases = []
    for qid, reps in by_q.items():
        q = questions[qid]
        reps.sort(key=lambda r: r.reported_at)
        rws = [rows[r.report_id] for r in reps]
        main = primary(rws)
        t = trace["reports"][main["reportId"]]
        rank, label = urgency(main)
        cases.append(
            {
                "id": qid,
                "qid": q.qid,
                "subject": q.subject,
                "chapter": q.chapter,
                "qtype": TYPE_LABEL.get(q.qtype, q.qtype),
                "level": q.level,
                "section": SECTION[main["route"]],
                "rank": rank,
                "urgency": label,
                "problem": problem(main, trace["questions"][qid]["findings"]),
                "urgent": rank <= 2,
                "verdict": main["verdict"],
                "verdict_label": VERDICT_LABEL[main["verdict"]],
                "repair": main["repair"],
                "repair_label": REPAIR_LABEL.get(main["repair"] or "", ""),
                "repair_auto": bool(main["repair"] and taxonomy["repairs"][main["repair"]]["auto"]),
                "route": main["route"],
                "confidence": main["confidence"],
                "checks": t["checks"],
                "evidence": main["evidence"],
                "edit": main["edit"],
                "change": change_view(q, main["edit"], t["extra_edits"]),
                "guard_notes": t["guard_notes"],
                "question_html": q.question_html,
                "solution_html": q.solution_html,
                "answer": answer_text(q, q.answer)
                if q.qtype != "integerQuestion"
                else str(q.answer),
                "reports": [
                    {
                        "reportId": r.report_id,
                        "source": r.source,
                        "reportedAt": r.reported_at,
                        "comment": r.comment,
                        "reply": rows[r.report_id]["student_reply"],
                        "verdict": rows[r.report_id]["verdict"],
                        "route": rows[r.report_id]["route"],
                        "student_was": trace["reports"][r.report_id]["student_was"],
                        "injection": trace["reports"][r.report_id]["signals"]["injection"],
                    }
                    for r in reps
                ],
                "oldest": reps[0].reported_at,
            }
        )
    cases.sort(key=lambda c: (c["rank"], -len(c["reports"]), c["oldest"]))
    bonus = json.loads((ROOT / "out" / "bonus_defects.json").read_text("utf-8"))
    return {
        "generated_at": trace["generated_at"],
        "models": trace["models"],
        "cases": cases,
        "bonus_count": len(bonus),
    }


if __name__ == "__main__":
    data = build()
    out = ROOT / "console" / "data" / "cases.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    sections = {
        s: sum(c["section"] == s for c in data["cases"]) for s in ("decide", "auto", "reply")
    }
    print(f"wrote {out.relative_to(ROOT)}: {len(data['cases'])} cases {sections}")
