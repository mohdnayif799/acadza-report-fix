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
