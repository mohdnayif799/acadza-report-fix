# Acadza report → fix

An AI system that turns students' "Report error" comments on JEE/NEET questions into safe, surgical fixes, and a review console a faculty member can work through quickly at 10 PM.

**Live console:** https://acadza-report-review.vercel.app

| File | What it is |
|---|---|
| [`results.json`](results.json) | Triage of all 44 reports, in the brief's exact schema |
| [`out/bonus_defects.json`](out/bonus_defects.json) | 23 defects nobody reported, each verified against the raw HTML |
| [`PROMPTS.md`](PROMPTS.md) | Every product prompt (with versions), my prompts to the coding assistant, where the AI was wrong, design decisions |
| [`PRODUCT.md`](PRODUCT.md) | Product thinking, one page |
| [`docs/build-log.md`](docs/build-log.md) | Timestamped raw log of the whole build |

## What it does

For each report: **verdict** and **repair** from the closed taxonomy, a **surgical edit** (`find`/`replace` on the smallest span of the stored HTML, or a new answer), a **route** (`auto_apply` / `faculty_review` / `no_change`), a **confidence** computed from independent checks, one or two sentences of **evidence**, and a 1-3 sentence **student reply** (light Hinglish when the student wrote in Hinglish).

Results on the 44 reports: 20 auto-applied, 8 to faculty, 16 no change (10 of them the student was mistaken). Five reports were right that the answer key was wrong; the injection attempt (R027) was ignored and the key independently confirmed.

## Architecture

```
reports ─► comment signals (code) ─► claim label (cheap model, closed list; noise/injection skip the model)
questions ─► HTML+MathML parser ─► code checks ─► solver A ─┐  solvers never see key, solution or comment
                                                 solver B ─┤  (different model + Python execution)
                                                 reviewer ─┤  (never sees key or comment)
                                                 confirmer ┘  (second model on every text edit)
          ─► candidate defects, each with its independent checks ─► deterministic rules ─► guard ─► reply
```

| Module | Job |
|---|---|
| `engine/parse.py` | HTML + MathML → clean text for models (raw HTML kept for edits); option splitting |
| `engine/checks.py`, `comments.py` | Code checks: blank/missing/identical options, malformed keys, LaTeX and `&` leaks, exam tags, missing figures, units, already-fixed (errorHistory after the report), noise, injection |
| `engine/solve.py` | Solver A (gemini-3.8-flash) and solver B (gemini-3.5-flash + code execution) |
| `engine/review.py`, `confirm.py`, `syllabus.py`, `writer.py` | Reviewer, second-opinion confirmer, official NMC syllabus check, solution writer |
| `engine/candidates.py`, `decide.py` | Candidate defects with checks; claim → decision rules |
| `engine/guard.py`, `edit_rules.py` | The last word: field scope, markup allowlist, proof gate for anything that can change the correct answer, per-repair content rules. It can only make a row safer |
| `engine/confidence.py` | Each agreeing independent check halves the doubt (1 → 0.75, 2 → 0.88, 3 → 0.94); any disagreement caps at 0.5; auto-apply needs ≥ 0.8 |
| `engine/llm.py` | Gemini client: disk cache keyed by content hash (reruns cost nothing), retries with backoff, timeouts, fixed seed, token log |
| `engine/validate.py` | Checks `results.json`: all 44 reports, exact keys, taxonomy-only values, edits only on allowed fields |
| `console/` | Static faculty console (HTML/CSS/JS, vendored DOMPurify + jsdiff, self-hosted IBM Plex and STIX Two Math) |

**Queue order (what "most urgent" means):** by harm to students. Wrong answer keys first (every attempt is marked wrong and the wrong idea is taught), then questions students can't solve as shown (missing option, data or figure, no correct option), then wrong solutions, then cosmetic issues, then filing (chapter, syllabus). Within each, more reports go higher, then the oldest report. The console groups cases needing a decision first, then automatic fixes (to spot-check), then reply-only cases.

Models are pinned in `engine/config.py` and overridable through `.env` (see `.env.example`).

## How to run

Windows / Python 3.12 (any OS works; use `.venv/bin/` instead of `.venv\Scripts\`).

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
```

Run the tests and lint (no API key needed):

```bash
.venv\Scripts\python -m pytest
.venv\Scripts\ruff check engine tests scripts
```

Re-run the triage. It is served from the committed cache, so it costs nothing and needs no key unless you change a prompt or model:

```bash
.venv\Scripts\python -m engine.pipeline
```

Validate the output and rebuild the console data:

```bash
.venv\Scripts\python -m engine.validate
.venv\Scripts\python scripts\build_console_data.py
```

Open the console locally:

```bash
python -m http.server 8765 --directory console
```

To make fresh model calls, copy `.env.example` to `.env` and set `GEMINI_API_KEY`. Other scripts: `scripts/cost_report.py` (tokens per model), `scripts/check_contrast.py` (WCAG AA for every colour pair), `scripts/build_prompts_md.py` (regenerates PROMPTS.md from the prompt files and build log).

## Honest limits

- **The console shows precomputed results.** It loads `console/data/cases.json`, built from this repo's `results.json`. Opening it makes no AI calls, and nothing a faculty member does there writes back to Acadza's database.
- **Decisions and the audit log live in the browser** (localStorage). They survive a reload but not another browser or device; use "Export JSON" in the audit log to keep a copy.
- **No authentication.** The console is a public demo of 39 cases; a real deployment would sit behind faculty login.
- **"Auto-applied" is a route, not a write.** Nothing is changed in any live system; the edits are proposals in `results.json` that the console shows as applied, with one-click revert.
- **Model judgement is still model judgement.** Answer-key changes need two independent solves plus the stored solution; text fixes need a second model. Rewritten solutions and syllabus calls are the least mechanically verifiable, so the second is never auto-applied and the first needs four agreeing checks.
- **The syllabus check uses the NMC NEET (UG)-2026 syllabus** (the latest published, as of 10 Nov 2026), stored in `engine/reference/` with its source.
- **Scale:** 43 questions cost about 735k tokens across every iteration of the build; a production run would batch, and could skip the second solver when the first agrees with both the key and the stored solution at high confidence.
