# PRODUCT.md

*Draft. To be rewritten in my own words.*

## Who loses the most when a question is broken

The students who do not report it. One student taps "Report error"; hundreds of others meet the same wrong key, lose marks, and quietly decide they misunderstood the topic. A wrong answer key does the most harm because it teaches the wrong thing *and* punishes the right answer. Missing data or a blank option wastes a student's time but at least looks broken.

How the design reflects that:
- The queue is ordered by harm, not by arrival: wrong answer keys first, then questions that cannot be answered as shown, then wrong solutions, then cosmetic issues, then filing. More reporters move a question up.
- A proven answer-key fix is applied at once (two independent solvers and the stored solution agree), so the damage stops tonight rather than when someone reaches it in the queue. Faculty see it in "Applied automatically" and can revert it in one click.
- The student who reported gets an honest reply within the same run: right, partly right (R004: the key was wrong, but so was their 8225), or wrong with the one step they missed. Most reporters are wrong; the reply is where we keep them reporting.

## What I would never let the AI auto-apply

- **Anything a human would have to author:** a missing option, a new distractor, a missing figure, a re-written question. There is no ground truth to check it against.
- **An answer-key change on the student's word**, or on one model's word. It needs two independent methods plus the stored solution, and any disagreement goes to faculty.
- **Anything from a report that tries to instruct the system** (R027), whatever the evidence says.
- **Syllabus and chapter moves.** These are curriculum decisions, not facts in the question.

## One metric for week 1

**Faculty revert rate on auto-applied fixes**: the share of "Applied automatically" items a faculty member reverts or edits. It is the direct measure of whether auto-apply can be trusted. Target under 2%; any revert is read individually, and a repair type with two reverts goes back to faculty review until its rule is fixed.

## One idea beyond the brief

**Fix the class, not the question.** Most defects here are pipeline defects: MathML exported with LaTeX `&` alignment, units placed inside square roots, `(NEET 2019)` tags, `mcq` keys stored as `['', 'B']`. Each one found by a report becomes a code check run across all 8 lakh questions, producing a batch the content team reviews once instead of waiting for 8 lakh students to trip over them one at a time. This build already found 23 defects nobody reported in 43 questions.
