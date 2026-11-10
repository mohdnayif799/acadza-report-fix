"""Build PROMPTS.md from docs/PROMPTS.template.md so quoted prompts are byte-for-byte verbatim.

Inlines: every product prompt (latest version in full, earlier versions as diffs), my messages
to the coding assistant from docs/build-log.md, the confidence rule, and token totals.
Usage: python scripts/build_prompts_md.py
"""

from __future__ import annotations

import collections
import difflib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROMPTS = ROOT / "engine" / "prompts"

# name: (model(s), what it does, what it never sees, {version: why it changed})
PRODUCT = {
    "solver_a": (
        "gemini-3.8-flash, JSON schema",
        "Solves the question independently.",
        "the answer key, the stored solution, the student's comment",
        {},
    ),
    "solver_b": (
        "gemini-3.5-flash with Python code execution",
        "Second, independent solve by "
        "computing numerically; also re-solves an edited stem to prove a stem_data fix.",
        "the answer key, the stored solution, the student's comment",
        {},
    ),
    "reviewer": (
        "gemini-3.8-flash, JSON schema",
        "Reads question + stored solution: what the "
        "solution concludes, problems in it, surface defects, chapter fit.",
        "the answer key, the student's comment",
        {
            2: "v1's `solution_final_answer` came back null for all 43 questions (the "
            "schema allowed string/array/null), so the evidence wrongly said the "
            "solution 'reaches no clear answer'. v2 asks for the result mapped onto the "
            "option or the asked-for number. v1 also missed 'Canolla' while listing "
            "five solution typos, so v2 makes it check every option word by word, "
            "including proper nouns. v1 fixes used '^' notation ('95.5×10^(−3) H'); "
            "v2 asks for text as students should see it ('95.5 mH').",
            3: "v2 inserted the missing inductance but also changed 'are connected' to "
            "'is connected'. v3: insert only the value, keep every other word.",
        },
    ),
    "confirm": (
        "gemini-3.5-flash, JSON schema (deliberately not the reviewer's model)",
        "Second opinion on every proposed text edit (is it a defect, is the fix right, "
        "does it change only the defect).",
        "the answer key, the student's comment",
        {},
    ),
    "claim": (
        "gemini-3.5-flash-lite, JSON schema",
        "Labels what the student claims, from a "
        "closed list. Noise and prompt-injection comments never reach it.",
        "the question (it only describes the comment)",
        {},
    ),
    "reply": (
        "gemini-3.5-flash",
        "Writes the 1-3 sentence student reply from a facts object.",
        "anything not in the facts; an injection comment is withheld",
        {
            2: "v1 called a student 'Bhai' (assumes gender), opened R004 with 'Tera answer "
            "bhi galat hai' (leads with the negative), and put LaTeX in a reply. v2: lead "
            "with what the student got right, no gendered or over-familiar address, "
            "plain maths, an 'already fixed earlier' status.",
            3: "v2 hints were often irrelevant because only the first line of the working "
            "was passed. v3 gets the whole independent working and must name the step "
            "where the student's claimed answer goes off; partly-right replies must open "
            "with the part they got right. Moved from flash-lite to flash, which ignored "
            "the ordering rule.",
        },
    ),
    "solution_writer": (
        "gemini-3.8-flash",
        "Writes a replacement solution ending in the key (only when both solvers confirm the key).",
        "the student's comment",
        {},
    ),
    "syllabus": (
        "gemini-3.8-flash and gemini-3.5-flash (both must agree)",
        "Checks a syllabus "
        "claim against the official NMC NEET (UG)-2026 text; code verifies the quoted "
        "line.",
        "the student's comment",
        {},
    ),
}


def versions(name: str) -> dict[int, str]:
    out = {}
    for p in PROMPTS.glob(f"{name}.v*.txt"):
        m = re.fullmatch(rf"{name}\.v(\d+)\.txt", p.name)
        if m:
            out[int(m.group(1))] = p.read_text(encoding="utf-8").replace("\r\n", "\n").strip()
    return dict(sorted(out.items()))


def product_prompts() -> str:
    parts = []
    for name, (model, does, never, why) in PRODUCT.items():
        vs = versions(name)
        latest = max(vs)
        parts.append(
            f"### `{name}` (v{latest})\n\n- **Model:** {model}\n- **Job:** {does}\n"
            f"- **Never sees:** {never}\n- **File:** `engine/prompts/{name}.v{latest}.txt`"
            f"\n\n````text\n{vs[latest]}\n````\n"
        )
        for v in sorted(vs)[1:]:
            diff = "\n".join(
                difflib.unified_diff(
                    vs[v - 1].splitlines(),
                    vs[v].splitlines(),
                    f"{name}.v{v - 1}.txt",
                    f"{name}.v{v}.txt",
                    lineterm="",
                )
            )
            parts.append(f"**v{v - 1} → v{v}: why.** {why.get(v, '')}\n\n````diff\n{diff}\n````\n")
    return "\n".join(parts)


def user_prompt(n: int) -> str:
    log = (ROOT / "docs" / "build-log.md").read_text(encoding="utf-8")
    m = re.search(rf"## [^\n]*PROMPT #{n} [^\n]*\n.*?````text\n(.*?)\n````", log, re.S)
    if not m:
        raise SystemExit(f"PROMPT #{n} not found in build log")
    return f"````text\n{m.group(1)}\n````"


def confidence() -> str:
    text = (ROOT / "engine" / "confidence.py").read_text(encoding="utf-8")
    rule = re.search(r'"""(.*?)"""', text, re.S).group(1).strip()
    return (
        f"From `engine/confidence.py` (the code is the source of truth):\n\n```text\n{rule}\n```\n"
        "\nWhich checks count for which decision is listed per row in the console and in "
        "`out/trace.json` (`checks`). Examples: an answer-key change needs solver A, solver B "
        "and the stored solution; a spelling fix needs the detector and a second model; a "
        "stem_data fix also needs the edited question to re-solve to the key; a syllabus call "
        "needs two models to agree and the cited syllabus line to exist verbatim."
    )


def cost() -> str:
    by = collections.defaultdict(collections.Counter)
    for f in (ROOT / "cache" / "llm").glob("*/*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        by[d["request"]["model"]].update({"calls": 1, **d["usage"]})
    rows = "\n".join(
        f"| {m} | {c['calls']} | {c['prompt']:,} | {c['output']:,} | "
        f"{c['thoughts']:,} | {c['total']:,} |"
        for m, c in sorted(by.items())
    )
    total = sum(c["total"] for c in by.values())
    return (
        "Every paid call in the build (all prompt versions, the model probe and reruns), "
        "summed from the cache by `scripts/cost_report.py`:\n\n| model | calls | prompt | "
        f"output | thinking | total |\n|---|---|---|---|---|---|\n{rows}\n\n**{total:,} "
        "tokens in total.** A full rerun of the pipeline is free: all calls are cache hits."
    )


def main() -> None:
    out = (ROOT / "docs" / "PROMPTS.template.md").read_text(encoding="utf-8")
    out = out.replace("{{PRODUCT_PROMPTS}}", product_prompts())
    out = out.replace("{{CONFIDENCE}}", confidence()).replace("{{COST}}", cost())
    out = re.sub(r"\{\{USER_PROMPT:(\d+)\}\}", lambda m: user_prompt(int(m.group(1))), out)
    (ROOT / "PROMPTS.md").write_text(out, encoding="utf-8", newline="\n")
    print(f"wrote PROMPTS.md ({len(out):,} chars)")


if __name__ == "__main__":
    main()
