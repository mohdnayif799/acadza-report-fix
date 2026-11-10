"""Run the whole triage: python -m engine.pipeline

Writes results.json (brief schema), out/trace.json (everything the console shows) and
out/bonus_defects.json (defects nobody reported). Reruns are free: every LLM call is cached.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

from engine.bonus import bonus_defects
from engine.candidates import build_evidence
from engine.claim import Claim, classify
from engine.comments import analyze_comment
from engine.config import load_settings
from engine.decide import decide
from engine.evidence import Evidence
from engine.guard import BRIEF_KEYS, GuardContext, guard
from engine.human_edits import apply_human_edits, load_edits
from engine.models import ROOT, Report, load_questions, load_reports, load_taxonomy
from engine.reply import reply_facts, write_reply
from engine.syllabus import check_syllabus
from engine.validate import validate_results

log = logging.getLogger("pipeline")
OUT = ROOT / "out"
WORKERS = 8


def _jsonable(obj: object) -> object:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: _jsonable(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    return obj


def triage_report(
    report: Report, ev: Evidence, claim: Claim, taxonomy: dict, settings
) -> tuple[dict, dict]:
    signals = analyze_comment(report.comment)
    syllabus = check_syllabus(ev.question, settings) if claim.claim == "syllabus" else None
    decision = decide(report, ev, claim, syllabus)
    cand = decision.candidate
    ctx = GuardContext(
        ev.question, answer_proven=bool(cand and cand.proven), injection=signals.injection
    )
    guarded = guard(decision.row, ctx, taxonomy)
    row = dict(guarded.row)
    facts = reply_facts(report, ev, claim, row, decision.student_was)
    row["student_reply"], reply_notes = write_reply(facts, settings)
    row = {k: row[k] for k in BRIEF_KEYS}
    trace = {
        "report": _jsonable(report),
        "signals": _jsonable(signals),
        "claim": _jsonable(claim),
        "candidate": _jsonable(cand),
        "extra_edits": _jsonable(cand.extra_edits) if cand else [],
        "student_was": decision.student_was,
        "checks": [{"check": c, "agrees": ok} for c, ok in decision.checks],
        "syllabus": _jsonable(syllabus),
        "guard_notes": list(guarded.notes),
        "reply_notes": reply_notes,
        "reply_facts": facts,
    }
    return row, trace


def run() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    settings = load_settings()
    questions, reports, taxonomy = load_questions(), load_reports(), load_taxonomy()
    started = datetime.now(UTC).isoformat(timespec="seconds")
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        evs = list(pool.map(lambda q: build_evidence(q, settings), questions.values()))
        evidence = {ev.question.id: ev for ev in evs}
        claims = list(
            pool.map(lambda r: classify(r.comment, analyze_comment(r.comment), settings), reports)
        )
        pairs = list(
            pool.map(
                lambda rc: triage_report(
                    rc[0], evidence[rc[0].question_id], rc[1], taxonomy, settings
                ),
                zip(reports, claims, strict=True),
            )
        )
    pairs.sort(key=lambda p: p[0]["reportId"])
    # Human edits to model output (engine/human_edits.json) are applied last and recorded.
    rows, human = apply_human_edits([p[0] for p in pairs], load_edits())
    pairs = [
        (row, {**t, "human_edits": human.get(row["reportId"], [])})
        for row, (_, t) in zip(rows, pairs, strict=True)
    ]
    errors = validate_results(rows, reports, questions, taxonomy)
    OUT.mkdir(exist_ok=True)
    (ROOT / "results.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    trace = {
        "generated_at": started,
        "models": {
            "solver_a": settings.solver_a,
            "solver_b": settings.solver_b,
            "reviewer": settings.reviewer,
            "cheap": settings.cheap,
        },
        "reports": {p[0]["reportId"]: {**p[1], "row": p[0]} for p in pairs},
        "questions": {
            qid: {
                "key_status": ev.key_status,
                "consensus": _jsonable(ev.consensus),
                "findings": _jsonable(ev.findings),
                "solve_a": _jsonable(ev.solve_a),
                "solve_b": _jsonable(ev.solve_b),
                "review": _jsonable(ev.review),
                "candidates": _jsonable(ev.candidates),
            }
            for qid, ev in evidence.items()
        },
    }
    (OUT / "trace.json").write_text(
        json.dumps(trace, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    chosen = [p[1]["candidate"] for p in pairs]
    bonus = bonus_defects(evidence, chosen, rows, taxonomy)
    (OUT / "bonus_defects.json").write_text(
        json.dumps(bonus, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    log.info(
        "wrote %d results, %d bonus defects; validation errors: %d",
        len(rows),
        len(bonus),
        len(errors),
    )
    for e in errors:
        log.error(e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(run())
