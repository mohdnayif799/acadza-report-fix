# PROMPTS.md

> Status: work in progress (10 Nov 2026). The confidence rule and the prompt version history are final; the verbatim prompt texts, my prompts to the coding assistant, the "AI was wrong" moments and the design-decision log are being assembled from `docs/build-log.md` and `engine/prompts/`.

## How confidence is computed

Confidence is never typed in by hand. Every decision lists the **independent checks** behind it (shown in the console and in `out/trace.json`), and confidence is computed from them by `engine/confidence.py`:

- Start at **0.5** (a coin flip). Each independent check that **agrees** halves the remaining doubt: 1 check → 0.75, 2 → 0.88, 3 → 0.94, 4 → 0.97.
- Any check that **disagrees** caps confidence at **0.5**: the case is contested and a human decides.
- A check that can only confirm (a solver *noticing* a missing figure) counts when it fires; its silence is not counted against. Unknowns (the stored solution never reaches an answer) are left out, not guessed.
- If the code guard **rejects** the proposed edit, subtract **0.15** (floor 0.3): the proposal itself was flawed.
- The auto-apply floor is **0.8**, so **nothing auto-applies on fewer than two agreeing independent checks**, and nothing contested ever auto-applies.

Which checks count, by decision type:

| Decision | Independent checks |
|---|---|
| Answer key wrong / malformed, type mismatch, "no error" on an answer claim | solver A (gemini-3.8-flash, reasoning), solver B (gemini-3.5-flash + Python), the stored solution's final answer; plus the code check for a malformed key |
| Blank keyed option filled | code finds the blank; solver A's value; solver B's value; the stored solution's value (all must match) |
| Missing data added (stem_data) | reviewer flags it; a second model confirms; the edited question re-solves to the stored key |
| Unit added (answer_form) | reviewer; code finds no unit; second model; the stored solution's final answer is in that unit |
| Spelling, markup, exam tag, chapter | detector (code check or reviewer); a second model (different from the reviewer) confirms |
| Solution fix / rewrite | reviewer; both solvers confirm the key; second model confirms the fix; rewrite ends in the keyed answer |
| Unsound, identical options, missing option, figure | code check and/or each solver reporting the problem |
| Syllabus | two models judge coverage against the official NMC NEET (UG)-2026 text; code verifies the cited syllabus line is verbatim in that text |
| Display / app / language | the claim reading; code confirms the stored content is complete (and, for app, that both solvers confirm the key) |
| Already fixed | errorHistory entry dated after the report; the text the student quoted is gone |

## Prompts inside the product (version history)

All prompts live in `engine/prompts/<name>.v<N>.txt`; the highest version is used and old versions are kept.

| Prompt | Model | Versions | What changed and why |
|---|---|---|---|
| `solver_a` | gemini-3.8-flash | v1 | Independent solve; never sees key, solution or comment. |
| `solver_b` | gemini-3.5-flash + code execution | v1 | Different model *and* method (computes numerically), so a shared reasoning slip is unlikely. |
| `reviewer` | gemini-3.8-flash | v1 → v2 → v3 | v2: `solution_final_answer` came back null for all 43 questions (schema allowed string/array/null), which made the evidence falsely say "solution reaches no clear answer"; now a plain string mapped to the option or asked-for number. v2 also forces an option-by-option spelling pass (v1 missed "Canolla") and student-readable fixes ("95.5 mH", never "^"). v3: stem_data fixes may only insert the value (v2 slipped "are" → "is" into an edit). |
| `claim` | gemini-3.5-flash-lite | v1 | Comment is JSON-encoded inside a labelled block; output is one label from a closed list. Noise and injection comments never reach a model. |
| `reply` | gemini-3.5-flash | v1 → v2 → v3 | v2: no gendered/over-familiar address (v1 said "Bhai"), lead with what the student got right (v1 R004 opened "Tera answer bhi galat hai"), no LaTeX. v3: name the specific step the student missed using the full independent working (v2 passed one line and gave irrelevant hints); moved from flash-lite to flash because lite ignored the ordering rule. |
| `solution_writer` | gemini-3.8-flash | v1 | Writes a short solution ending in the key; only used when both solvers confirm the key. |
| `confirm` | gemini-3.5-flash | v1 | Second opinion on every proposed text edit, from a different model than the reviewer. |
| `syllabus` | gemini-3.8-flash + gemini-3.5-flash | v1 | Coverage against the official NMC text; must quote the closest syllabus line verbatim. |
