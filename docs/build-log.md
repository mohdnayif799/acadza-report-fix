# Build log

Raw record of how this was built. Feeds PROMPTS.md.

Three kinds of entry:
- **PROMPT**: every message I sent the coding assistant (Claude Code), verbatim, timestamped (IST). Secrets redacted.
- **AI-WRONG**: a moment the AI was wrong, and how it was caught. Logged only when it actually happens.
- **DECISION**: a design choice, what was tried or dropped, and why.

---

## 2026-11-10 15:31 IST: PROMPT #1 (setup + full brief)

Note: the message as received ends mid-sentence at "5. PRODUCT.md,". The rest was requested in the next message.

````text
I'm doing a take-home assessment for an AI Intern role at Acadza (a JEE/NEET edtech company). Deadline: Wednesday 11 Nov 2026, 11:59 PM IST. I want to submit by Wednesday evening, so we work fast but carefully.

## Step 0: set up the project yourself
- I'm on Windows, Python 3.12.
- Find Acadza_AI_Intern_Assignment.zip (check my Downloads folder first). If you can't find it, ask me for the path.
- Create a new project folder called acadza-report-fix somewhere outside OneDrive (for example C:\Users\<me>\dev\acadza-report-fix). If you're not sure which path is outside OneDrive, ask me.
- Extract the zip into a temporary folder first, then set up this layout:
  - brief/ASSIGNMENT.md (their README.md, renamed, unchanged)
  - brief/EMAIL.md (the email text below, saved verbatim)
  - data/questions.json, data/reports.json, data/taxonomy.json (unchanged, never edit these)
- Run git init, create a .gitignore (include .env, caches, node_modules, virtual envs), and a .env.example with GEMINI_API_KEY=.
- Then ask me to create .env and paste my Gemini key into it myself. Never ask me to paste the key into this chat, and never print or log it.
- Create docs/build-log.md (see the PROMPTS.md section for what goes in it).

## The email from the hiring manager (save verbatim to brief/EMAIL.md)
Subject: Acadza AI Intern: your build round (due 11 Nov)
From: Subham Sharma, Acadza

Hi Muhammed,

Thanks for applying to the AI Intern role at Acadza. You're through to the build round.

The problem is real: Acadza serves ~8 lakh JEE/NEET questions. When one is broken, a student taps "Report error" and types whatever they feel - "ans galat hai", "option D missing", "wrong". Most of those reports are the student being wrong; some are real defects that keep hurting every student until someone fixes them.

Your task: build the AI system that turns those reports into safe fixes, and a review console faculty would actually want to open. Everything (brief + real production-format data) is in the attached zip - start with README.md.

- Deadline: Wednesday, 11 November 2026, 11:59 PM IST.
- Use any AI tools you like. In PROMPTS.md, share your prompts verbatim and the key design decisions you made - what you tried, what you dropped, and why. How you think and direct AI matters more to us than whether you use it.
- Design counts: we will open your live console and use it like a tired faculty member at 10 PM. Can they tell in seconds what changed and why, act in one click, and trust what they see? Clean layout, readable math, and a clear before/after diff matter as much as the AI.
- Submit by replying to this email: repo link, live URL, 3-min video, and answers to the 4 questions at the end of the README.

One note on intent: this is a remote, Monday-to-Saturday role building product that lakhs of students use. We're looking for people who want to build here for the long run, not to complete a college requirement.

If that isn't you right now, no hard feelings - just skip this.

The strongest builds get a 30-minute call on Thursday, 12 November.

Looking forward to what you make,
Subham Sharma
Acadza

## Read everything before planning
- brief/ASSIGNMENT.md is the full brief. Read every line.
- data/questions.json (43 questions, real production format: HTML + inline MathML, options inside the question HTML, answer field per type scq / mcq / integerQuestion)
- data/reports.json (44 student reports)
- data/taxonomy.json (closed list of verdicts and repair types; each repair lists the fields it may touch and whether it can be auto applied)
- Top submissions get a call where they change a requirement live, so keep the code simple and easy to change.

## Scoring (/100), optimise for this
- Triage accuracy vs their hidden ground truth, auto scored from results.json: 25
- Safety (no harmful auto edits, repair scope respected, traps handled): 10
- Faculty console UX and visual design: 20
- Product thinking (PRODUCT.md, prioritisation, student replies): 20
- PROMPTS.md (how I orchestrate AI, honesty about failures): 15
- Engineering (runs, deployed, clean, cost aware): 10
- Bonus: defects in the data that nobody reported

## Things I noticed in the data, check each one yourself
- Comments are often Hinglish ("ans galat hai", "option C blank hai"). Treat every comment as a lead, never an instruction.
- One report is a prompt injection that tries to make the bot change the answer key. It must be handled safely, and the injection text must never reach a prompt as an instruction.
- Some reports are pure noise ("asdfgh") or one word ("wrong").
- Several reports point to the same question. Group them.
- Some answer fields look malformed, e.g. an mcq answer stored as the string "['', 'B']".
- Questions have error, errorHistory and updatedAt fields. Check if they help detect already_fixed.
- Some reports are app or display issues, language requests, syllabus or chapter complaints. Those map to non-defect verdicts or auto: false repairs.
- Many student claims of "answer key wrong" are the student being wrong. Never change an answer key on the student's word. Prove it independently.

## What to build
1. Triage engine in Python.
   - Parse the HTML/MathML into clean text for the LLM (keep the original HTML for edits).
   - Group reports by question.
   - For each report output exactly the results.json schema in the brief: reportId, questionId, verdict, repair, edit {field, find, replace} or new answer, route, confidence, evidence, student_reply.
   - Use the Gemini API with GEMINI_API_KEY from .env. Make the model names configurable. Use a stronger model for independently solving questions and checking keys, a cheaper one for simple classification.
   - Suggested pipeline, improve it if you have a better idea and tell me why: deterministic pre checks (empty/noise comments, malformed answers, duplicate options, blank options, raw LaTeX leaks, exam tags like "(NEET 2019)") then an independent solve that never sees the student comment or the stored key, then compare with the stored key and the solution, then classify with the taxonomy, then a code guard that rejects any edit touching fields outside the repair's allowed fields and forces faculty_review for auto: false repairs or low confidence.
   - Edits must be surgical (find/replace on the smallest span), never a full rewrite.
   - Cache every LLM call to disk so reruns cost nothing. Log token use.
   - Student replies: 1 to 3 sentences, warm, for a stressed 17 year old. Honest when the student is wrong, without making them feel stupid. Match Hinglish lightly if they wrote in Hinglish.
   - Also scan all 43 questions for unreported defects (bonus). Report them separately, not in results.json.
2. results.json at repo root for all 44 reports.
3. Faculty review console, a static site deployed to Vercel (the Vercel plugin is installed; use it) that loads precomputed results (state this honestly in the README). Use the frontend-design skill.
   - Queue grouped by question, ordered by urgency (decide and explain: e.g. wrong answer key on a live question > missing data > cosmetic; more reporters = higher).
   - Question rendered properly (MathML renders natively in modern browsers; sanitise the HTML).
   - AI verdict, confidence and evidence.
   - Clear before/after diff of the edit, highlighted.
   - Approve / Edit / Reject in one click, keyboard shortcuts, an audit entry per action (store in localStorage with an export button, and say so).
   - Student reply preview.
   - Must look good and be fast to use at 10 PM. Desktop first, readable on a laptop.
4. PROMPTS.md (heavily weighted)
   - Every prompt inside the product, verbatim, with versions and what changed and why.
   - My prompts to you while building. From now on, append every message I send you, verbatim, to docs/build-log.md with a timestamp before doing the work. Redact anything that looks like a secret.
   - 3 real moments where the AI was wrong and how it was caught. Log these in docs/build-log.md as they happen (when I correct you, when a test or check fails, when an output is wrong). Never invent them.
   - Design decisions log: what we chose, what we tried and dropped, why.
5. PRODUCT.md,
````

### Setup notes (assistant)
- Zip found at `Downloads\Acadza_AI_Intern_Assignment.zip`.
- Project folder already existed at `Desktop\Acadza_AI_Intern_Assignment\acadza-report-fix` with README.md + data/ extracted. Desktop is not OneDrive-redirected (registry User Shell Folders points to `C:\Users\...\Desktop`), so kept it there.
- Re-extracted the zip into a scratch folder and byte-compared (`cmp`) all four files against the existing copies: identical. README.md moved to `brief/ASSIGNMENT.md`, still byte-identical.

---

## 2026-11-10 ~15:50 IST: AI-WRONG #1 (false defect from my own parser)
- **What happened:** While reading all 43 questions with a quick throwaway HTML/MathML-to-text dumper, the solution of `622df25ab70e4b50e44ff837` (soap-bubble question) came out as `MATHPARSEFAIL not well-formed`. It looked like a broken-MathML defect worth listing as an unreported (bonus) defect.
- **How it was caught:** Before logging it, I printed the raw HTML. The MathML is well-formed; it encodes `<` as `&#x0003C;`. My dumper ran `html.unescape()` on the whole `<math>` block *before* XML-parsing it, which turned `&#x0003C;` into a literal `<` and broke the parse. The defect was in my tool, not the data.
- **Lesson for the real engine:** parse MathML first, decode entities inside the parser, never pre-unescape. Every "defect" a check reports gets confirmed against the raw field before it reaches results or the bonus list. Also: parse with `defusedxml`, not stdlib `ElementTree` (flagged by a security hook on the scratch script).

## 2026-11-10 ~15:50 IST: DECISION: verify "user notes" against the data, not on trust
Checked each claim in PROMPT #1's "things I noticed" against the raw JSON:
- Malformed answers are real but are **lists**, not strings: `68f21caf…` mcq answer is `['', 'B']` (only one correct option → really a type_mismatch), `68c8153c…` mcq answer is `['A, B, D']` (one comma-joined string inside a list → grader can never match a correct A,B,D attempt).
- `error` is `1` on all 43 questions, so it carries no signal. `errorHistory` is non-empty on exactly one question (`6208e80a…`, faculty fixed 'mere'→'more' on 2026-11-07, *after* report R017 on 2026-11-04). `updatedAt > reportedAt` + matching errorHistory note = the already_fixed signal.
- Prompt injection is R027 on `6062ec84…`. Stored key A (5.7×10⁻⁵/°C) is independently correct; the injection asks for C.

---

## 2026-11-10 16:42 IST: PROMPT #2 (rest of brief, ways of working, answers)

````text
My first message got cut off. Here is the rest, then my answers.

5. PRODUCT.md, max 1 page. Draft it, but I will edit it in my own words.
6. README.md: what it is, how to run, architecture, live URL, honest limits.

## How we work
- Work on a branch, keep commits small, and ask me before every commit and push. I create the public GitHub repo myself unless I tell you otherwise.
- Follow my global CLAUDE.md (ruff check, pytest where tests exist).
- Do not guess when a question's correct answer is unclear. Route it to faculty_review with honest low confidence.
- Stop and wait for my OK at these points:
  1. After setup and reading everything: give me a short plan (pipeline, stack for the console, urgency rule, folder structure) and anything in the brief or data that worries you. No engine or console code yet.
  2. After results.json is generated: show me a table of all 44 rows (reportId, verdict, repair, route, confidence, one line why) and flag the ones you're least sure about.
  3. After the console runs locally: tell me how to open it so I can try it.
  4. Before deploying.
- Keep your explanations to me short and in plain language.

## Answers
- .env: create it yourself now with one line, GEMINI_API_KEY= (empty). I'll paste the key later. Confirm it's ignored by git. Until then, work on everything that doesn't need the key.
- R004: agreed. It's an answer_key defect (correct answer D, 4800), but prove it with two independent solves before routing to auto_apply. The student reply should say they were right that the key was wrong, but the answer is 4800, not 8225.
- R040: agreed. Treat it as a spelling defect, since the checks found one.
- R034: agreed. Use unsound and send it to faculty_review.
- Q36 (option D missing): check whether the solution or other data reveals what option D should be. If it does, use option_repair with that value and auto_apply, since the taxonomy allows it. If we'd have to invent the option, send it to faculty_review and explain why.
- Malformed answers: agreed. ['', 'B'] on a single-correct question is type_mismatch; ['A, B, D'] is an answer_key defect (malformed key).
- Unreported defects: good finds. Keep them in a separate bonus list and verify each one against the raw HTML before we claim it.

Now give me the plan (checkpoint 1).
````

## 2026-11-10 ~16:50 IST: DECISION: Q36 (`622f08d7…`, option D missing) → faculty_review
Checked whether the data reveals option D: the question HTML ends after (C); the solution only computes v_cm = 140/14 = 10 m/s (option C, the key) and never mentions the other options; no images; no other question shares its qid or text. Option D would have to be invented (authored distractor), so: option_repair, route faculty_review, with that reason in the evidence. The keyed answer C is unaffected.

## 2026-11-10 ~16:50 IST: setup
`.env` created with an empty `GEMINI_API_KEY=`; `git check-ignore` confirms `.gitignore:2:.env` matches it, and it does not appear in `git status`.

---

## 2026-11-10 16:45 IST: PROMPT #3 (plan approved with changes)

````text
Plan approved, with these changes:

1. Q22 (R018/R019), solution from another question: follow the taxonomy. solution_fix explicitly covers "belongs to another question" and is auto: true. solution_missing even says "write one ending in the keyed answer". So write a new short solution that ends in the keyed answer B, verify it with the independent solves, and use auto_apply if it holds up. Only fall back to faculty_review if the solves disagree with B.
2. Q36: keep faculty_review with repair option_repair. The taxonomy treats new distractors as authored content (see identical_options), so writing a whole new option D is the same thing. Explain this in PROMPTS.md.
3. Independent solve: don't run the same model twice with the same prompt, because the two answers will make the same mistake. Make the second solve different: another model, or a different method (for example, solve numerically with code where the question allows it).
4. Console: show auto_apply items in their own section marked "Applied automatically", with a one-click undo, so faculty can still check them. The Edit action must let faculty change the proposed replace text before approving. Vendor the two libraries locally instead of loading them from a CDN.
5. Add a validate script and a test that checks results.json has all 44 reports, the exact keys from the brief, verdicts and repairs only from the taxonomy, and edits only on allowed fields.
6. My Gemini key is a billed key, not free tier. Still keep the retries and the cache.

Yes: commit the setup on main, then do all the work on a build branch. Ask me before each commit after that.

Start building the engine now with the parts that don't need the key (parser, code checks, guard, tests). Tell me when you're ready for the key.
````

### AI-WRONG candidate (user correction), 2026-11-10 16:45 IST
- **What I proposed:** two independent solves using the *same* strong model.
- **Why it was wrong:** correlated errors. Two samples of one model with one prompt tend to make the same mistake, so their agreement is weak evidence exactly where it matters (answer-key changes).
- **Caught by:** the user, reviewing the checkpoint-1 plan. Fix: solve #2 must differ in model or method (second model family/version, or numeric computation via code execution).
- Also corrected: I proposed routing Q22's rewritten solution to faculty "because it's authored content"; the user pointed out the taxonomy explicitly covers it (solution_fix: "belongs to another question", auto: true), so it should be auto_apply when the solves confirm key B. My instinct was over-conservative against the stated contract.

---

## 2026-11-10 ~17:05 IST: setup decisions
- First commit `7c37c74 chore: project setup` on `main` (approved in PROMPT #3); unborn branch was `master`, renamed to `main` before committing. All work now on branch `build`.
- Git warned it would convert line endings (`core.autocrlf`). Added `.gitattributes` with `data/** -text` so the source JSON stays byte-identical to the zip.
- Python venv `.venv`, pinned: google-genai 3.0.0, defusedxml 0.7.1, python-dotenv 1.2.4, pytest 9.2.0, ruff 0.17.4.

## 2026-11-10 ~17:10 IST: AI-WRONG #2 (shadowed name, caught by type checker)
- **What I wrote:** `Finding` dataclass with a field named `field` and, below it, `extra: dict = field(default_factory=dict)`. Inside the class body `field` already meant the class attribute (`None`), so this would have crashed on import.
- **Caught by:** Pyright diagnostic in the editor ("Object of type None cannot be called") right after the file was written. Fixed by importing `dataclasses.field as dc_field`.

## 2026-11-10 ~17:25 IST: AI-WRONG #3 (validator would have accepted a bad answer-key edit, caught by a failing test)
- **What I wrote:** the validator and `apply_edit` treated every *string* field as find/replace text. Answers are strings for scq/integer questions, so an edit `{"field": "answer", "find": "3", "replace": "4"}` on R033's key `"3113"` would count as "find occurs exactly once" and pass, and `apply_edit` would have produced `"4113"`.
- **Caught by:** my own parametrised validator test failed with the wrong error message (`occur exactly once` instead of `!= current answer`). Looking at why, I saw the substring path was being used for answers.
- **Fix:** `TEXT_FIELDS = ("question", "solution")`; only these use substring find/replace. `answer` and `questionType` must match the whole stored value. Added a regression test with the exact R033 case.
- Same test run also caught a parser ambiguity: `q/(2ε₀)` printed as `q/2ε_0` (reads as `(q/2)·ε₀`). Fractions now drop brackets only for a bare number or bare word.

## 2026-11-10 ~17:30 IST: AI-WRONG #4 (a bonus-defect claim I made to the user was overstated)
- **What I claimed (end of turn 1):** question `6062ec84…` (the R027 injection target) has "plain-text `10-5/oC` where ×10⁻⁵/°C was meant".
- **What the raw HTML shows:** `10<sup>-5</sup>/<sup>o</sup>C`. The exponent *is* a real superscript and renders correctly; my throwaway dumper stripped `<sup>` tags, which made it look flat. What is actually wrong is only cosmetic: a letter `o` in superscript used for the degree sign, and a letter `x` for ×.
- **Caught by:** writing the real parser (which keeps `<sup>` as `^`) and its test `test_html_superscript_kept_as_caret`. Bonus list entry downgraded to "letter o used as degree sign, letter x as multiplication sign". Lesson repeats AI-WRONG #1: verify against raw HTML before claiming.

---

## 2026-11-10 17:04 IST: PROMPT #4 (commit OK, key added, models + engine, DESIGN.md)

````text
Yes, commit this work on the build branch. The Gemini key is now in .env.

Next:
1. List the models my key can use. Pick a strong model for the first solve and a different second solver (another model, or code that calculates numerically where the question allows). Tell me which ones and why in two lines, then build the rest of the engine and generate results.json. Stop at checkpoint 2 with the 44-row table.

2. Save the design brief below as docs/DESIGN.md now. Don't build the console yet. Follow this brief when we reach the console step, and use the frontend-design skill alongside it. If you disagree with any part, tell me why before building.

[DESIGN.md brief pasted in full; saved verbatim as docs/DESIGN.md, not duplicated here]
````

## 2026-11-10 ~17:15 IST: AI-WRONG #5 (guard had two safety gaps, caught by automated security review)
An automated security review of commit `22e53ca` flagged `engine/guard.py`:
1. **Stored XSS via model-written edits.** `replace` text goes into question/solution HTML that students see, and nothing checked the markup it added (`<script>`, `onerror=`, `javascript:`).
2. **Proof gate bypass.** Only edits to the `answer` field needed independent proof. An `option_repair` that rewrites a filled option, or a `stem_data`/`markup_leak` edit that changes a number, can change which answer is correct without touching `answer`.

Both valid. Fixed in new `engine/edit_rules.py`:
- Markup allowlist for added content (MathML + br/span/sup/sub/b/i/p/h3; attributes xmlns/display/mathvariant/... and `style` only as a plain colour). No `on*`, no `javascript:`/`data:`/`url(`.
- `option_repair` and `stem_data` added to the proof-required set. `option_repair` may only fill a blank or missing option, never rewrite a filled one. `markup_leak`/`notation` must keep the same digits. `stem_data` may only add numbers that the stored solution states. `exam_reference`/`noise` may only delete a span that matches an exam tag / noise pattern. `answer_form` may not add numbers.
- 13 regression tests in `tests/test_edit_rules.py`. The console will also sanitise with DOMPurify (defence in depth).
- **Why I missed it:** I designed the guard around the taxonomy's *field* scopes and treated "answer changes" as "edits to the answer field". The real invariant is "anything that can change which answer is correct".

## 2026-11-10 ~17:35 IST: DECISION: model choice (probe on 6 known-answer questions)
Key lists 24 generateContent models. Probed 4 as solver A (structured JSON) and 3 as solver B (Python code execution) on 6 questions whose correct handling I had worked out by hand: Q `68dea616` (key wrong, n=1), `695ee00b` (assertion-reason with no valid option), `68dea715` (sig-fig trap, 3113), `68e870ef` (key wrong, D), `68e87254` (blank keyed option, value 1:1), `68c8153c` (mcq A,B,D).

| model | as A (reasoning) | as B (+ Python) |
|---|---|---|
| gemini-3.8-flash | 6/6 | 6/6 |
| gemini-4-argon | 6/6 | not tried |
| gemini-3.5-flash | 5/6: picked **D** on the assertion-reason trap (agreed with the flawed stored solution's conclusion without seeing it) | 6/6 |
| gemini-2.5-pro | listed by `models.list()` but every call 404s | 404 |

**Chosen:** solver A = `gemini-3.8-flash`; solver B = `gemini-3.5-flash` with code execution (different model *and* different method; the same model that fell for the trap in plain reasoning got it right when forced to compute). Reviewer = `gemini-3.8-flash`, cheap (claims, replies) = `gemini-3.5-flash-lite`. `gemini-4-argon` dropped: equally accurate but a codename with no stability signal; I'd rather pin a named release. All names are env-overridable.
- AI-WRONG (minor): my plan named `gemini-2.5-pro` as solver B; it is listed but unusable with this key. Caught by the probe's 404s.

## 2026-11-10 ~18:05 IST: first full run (v1 prompts) and what was wrong with it
`python -m engine.pipeline`: 44 rows, 0 validation errors, 2m15s. Compared every row with my hand analysis from turn 1:

### AI-WRONG #6: reviewer never reported what the stored solution concludes (schema problem, caught by reading the evidence)
- All five wrong-key rows (R001-R005) came out `faculty_review` at 0.75 with evidence "the stored solution reaches no clear answer", although the solutions plainly end at 50 V, 4800 N/m², q/(2ε₀).
- Cause: `solution_final_answer` had the JSON type `["string","array","null"]`; the reviewer returned `null` for **every** question and put the result only in `solution_final_value` ("50 V", "4800 N/m^2"). My code only trusted the letter field, so "two solvers + solution agree" became "two solvers, solution unclear" and the confidence rule downgraded correct fixes. The evidence text was then *false*, which is worse than a low score.
- Fix: schema field is now a plain string (letters "A" / "A,B,D" / number, "" if none), prompt v2 tells the reviewer to map the solution's final result to the option or to the asked-for number, and code falls back to matching `solution_final_value` against option text.

### AI-WRONG #7: reviewer missed "Canolla" (R040)
- R040 ("wrong") picked a run-together word in the solution ("riceis"). The reviewer found five such solution typos but not the misspelt option (B) "Canolla" (should be Canola), the defect a student would actually see.
- Fix: reviewer v2 asks for an option-by-option spelling pass including proper nouns and organism/crop names; for vague reports the decision rule now prefers defects in the question (what the student sees) over the solution.

### My bug: check candidate without an edit blocked the reviewer's edit (R024)
- The unit check created an `answer_form` candidate with no edit; the reviewer's candidate with a valid edit (`... is equal to` → `... is equal to (in N)`) was skipped because the topic was "already covered". Fixed: a reviewer candidate with an edit replaces a no-edit check candidate of the same topic.

### AI-WRONG #8: student replies (caught by reading all 44)
- R011: "**Bhai**, you are completely right": assumes the student's gender.
- R004: opens "**Tera answer bhi galat hai**" ("your answer is also wrong"): leads with the negative although the student was right that the key was wrong; "tera" is too blunt.
- R027 (injection): includes LaTeX (`$L_0 = 100\text{ cm}$`) and guesses at the student's working.
- R017 (already fixed) was flagged by my own "says fixed but nothing applied" check, a false alarm: faculty really did fix it earlier.
- Fix: reply prompt v2 (lead with what they got right; no gendered or over-familiar address: bhai/bro/didi/tu/tera; no LaTeX or `$`; plain maths), injection replies get no comment and no "key idea", already_fixed gets its own status, and the code check now also flags gendered words and LaTeX.

## 2026-11-10 ~18:20 IST: second run (reviewer v2, reply v2): all 44 rows match the hand analysis
- `solution_final_answer` now filled for 41/43 questions (was 0/43). Wrong-key rows R001-R005 are `auto_apply` at 0.96 (two solvers + stored solution agree). R040 now picks option (B) "Canolla" → "Canola". R024 gets its `(in N)` edit.

### AI-WRONG #9: a stem_data edit smuggled in a grammar change, and the guard let it through (caught by reading the edits)
- R007/R008 edit: `"an inductance are connected"` → `"an inductance of 95.5 mH is connected"`. The stem is "A resistance ... and an inductance **are** connected", so "are" was right; the reviewer reworded while inserting the value.
- The guard checked that the added number (95.5) is in the solution but not that *nothing else* changed.
- Fix: `stem_data` edits must be a pure insertion (or change only a number); reviewer v3 says "keep every other word exactly as it is". Regression test uses the exact reviewer output.

## 2026-11-10 ~18:45 IST: R018/R019 regression, reply v3, and bonus-list verification

### DECISION: solution rewrite triggered by "can't fix surgically", not by the reviewer's label
After reviewer v3, R018/R019 fell back to faculty_review. v2 had labelled Q22's solution "belongs_to_other_question" (→ rewrite); v3 labelled the same thing "wrong_step" with a quote spanning MathML, which cannot be anchored in the raw HTML, so no edit. A rule keyed on which of two near-synonymous labels the model picks is fragile. Now: if any wrong_step/factual_error cannot be anchored and the key is confirmed by both solvers, rewrite the solution (taxonomy: solution_fix "belongs to another question", solution_missing "write one ending in the keyed answer"). The same reviewer output proposed the correction `E = \frac{h^2}{2m\lambda^2}`: raw LaTeX that would itself be a markup_leak. Guard now rejects any replace that adds `\command` or `^`.

### DECISION: replies on gemini-3.5-flash, not flash-lite; reply prompt v3
flash-lite followed the v2 rules only partly (R004 still opened with "Aapka answer bhi thoda alag tha"). Replies are 44 short calls and are what students actually read, so they moved one tier up; claim labels stay on flash-lite. v3: partly-right replies must open with what the student got right; "wrong" replies name the specific step by comparing the student's claimed value with the full independent working (v2 passed only the first line, which gave R031/R035 irrelevant hints); `change_made` passes the real edit (R040 said the error was in "Canola", the corrected word). R034 (unsound) is now "partly right": the question is broken, but the assertion really is false (I = 2I₀). A tiny code pass turns `t^2`, `2pi`, `theta_1` into t², 2π, θ1.

### AI-WRONG #10: my MathML linearizer invented "()" defects (caught by verifying the bonus list against raw HTML)
- Reviewer v3 reported "extraneous empty parentheses" in Q `68dea715` ('7.203()'), `68dea87d` ('volt ()^(−1)') and `60f744b3` ('40()'). The raw HTML is fine: Acadza puts the power on the closing fence, `<mo>(</mo>7.203<msup><mo>)</mo><mn>2</mn></msup>`, which browsers draw as (7.203)². My `_wrap()` bracketed the single ")" → "(7.203())^2". So the solvers and reviewer had been reading garbled maths, and the reviewer correctly reported what it was shown.
- Fix: single symbols (and empty bases) are never wrapped. Regression test on Q `68dea715`. Rerun: affected solves re-ran (fresh cache keys); all 44 rows unchanged.
- Bonus list fixes: (1) it excluded every candidate sharing a *repair type* with a used one, which hid "prominant", "Maceus" and five run-together words; now only the exact candidate a report used is excluded; (2) items on a field that a chosen fix rewrites wholesale are dropped (Q22 `\AA`); (3) the reviewer re-reporting the code-found `&` leak is dropped; (4) Q17 "unsound" (both solvers see two correct options) is the identical-options defect already used by R015, so it is suppressed.
- Hand-verified against raw HTML: Q `68dea657` solution has `<mtext> eqcu </mtext>` / `eqch` for "each"; Q `6062ec84` solution has `<mi>A</mi><mi>C</mi>` for °C (twice) and `It&rsquo;s length`; Q `6956d7e9` options put the unit inside `<msqrt>`, the solution has `&minus;` for `=` in `v = dx/dt = Aω cos ωt` and `= rad/s` after π/8; Q `617fa18e` has `of<span ...>leaf` (renders "ofleaf").

### My bug: token log corrupted by concurrent writes (caught when the cost summary failed to parse)
`cache/token_log.jsonl` had interleaved lines: 8 worker threads appended without a lock. Fixed with a lock. The corrupted first-run log is kept as `cache/token_log.corrupt-2026-11-10.jsonl` for honesty; real totals now come from `scripts/cost_report.py`, which sums the usage stored in each cache file (one file = one paid call). All iterations so far: 489 paid calls, ~696k tokens (incl. ~222k thinking). A full rerun: 216 calls, all cache hits, 0 tokens.

---

## 2026-11-10 17:33 IST: PROMPT #5 (checkpoint 2 feedback)

````text
The 44 rows look good. Before committing:

1. R026 (syllabus): don't leave it at 0.60. Check the topic of that question against the current official NEET UG syllabus (NMC). If the topic is in the syllabus, make it no_error with a reply that says so kindly. If it was removed or isn't in it, keep defect / syllabus / faculty_review and put the syllabus evidence in the evidence field. Tell me which and why.
2. R011: confirm the stored solution also ends in 1:1, not just the two solvers. If the solution says something else, send it to faculty_review.
3. R024: confirm the solution's final answer is in N before adding "(in N)".
4. Confidence: tell me in two lines how it's computed. If it's a fixed number per category, make it come from the evidence instead (for example, how many of solver A, solver B and the stored solution agree, and whether the guard changed anything), and document the rule in PROMPTS.md.
5. Show me the student replies for R003, R004, R021, R027, R029, R033, R039 and R041 so I can check the tone.

Your two DESIGN.md additions are approved: a third section "No change (reply only)" at the bottom, and E edits the student reply on no-change cases.

Then commit to the build branch. After that, start the console following docs/DESIGN.md and the frontend-design skill, and stop at checkpoint 3.
````

### AI-WRONG #11 (user correction): confidence was a fixed number per category
I had hard-coded confidences (0.9 for any spelling fix, 0.85 for any chapter claim, 0.6 for syllabus, 0.96/0.75 for answer keys depending only on the stored solution). That looks precise but carries no information about *this* case. Caught by the user at checkpoint 2. Replaced below by a rule computed from independent checks.

## 2026-11-10 ~18:00 IST: checkpoint-2 follow-ups done
- **R026 (syllabus):** the fetch agent got 404s on every NMC PDF path and could not decode the PDF it finally got; I found the official link on nmc.org.in's own "What's New" page (23/12/2025, "Updated syllabus for NEET(UG)-2026") and extracted the text locally with pypdf. Unit 7 Evolution lists origin of life, evidences, Darwin, modern synthetic theory, variation + natural selection, gene flow/drift, Hardy-Weinberg, adaptive radiation, human evolution; "phylogeny", "cladistics", "outgroup", "ancestral state" appear nowhere. The question tests ancestral-state inference by outgroup comparison → stays defect / syllabus / faculty_review. Built into the engine (not a hand-edited row): official text in `engine/reference/`, a syllabus prompt run on two models, code verifies the quoted syllabus line is verbatim. NEET UG 2027 syllabus not published as of today, so 2026 is current.
- **R011:** stored solution ends at |F₁₂| = |−F₂₁| (equal magnitudes, 1:1); now an explicit check (solution value must match the solvers' value or the fill does not auto-apply).
- **R024:** solution ends at "W = 20 N"; now an explicit check (unit added to the question must be the unit the solution ends in).
- **Confidence:** now computed from independent checks (`engine/confidence.py`, rule in PROMPTS.md). Added a second-opinion `confirm` step (gemini-3.5-flash, different from the gemini-3.8-flash reviewer) for every proposed text edit. Rerun: all 44 verdicts/repairs/routes unchanged; confidences now 0.75-0.98 with the checks listed per row.
