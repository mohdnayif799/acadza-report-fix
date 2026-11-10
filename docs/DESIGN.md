# DESIGN.md: Faculty review console

## Who it's for
A tired faculty member at 10 PM checking 60 reports. Every screen must answer in seconds: what changed, why, and can I trust it. Speed and clarity beat decoration.

## Avoid every "vibe coded" sign
- No purple, indigo or violet anywhere. No gradients. No glassmorphism, glows, coloured shadows or aurora backgrounds.
- No Inter, Space Grotesk, Geist or Instrument Serif. No serif italic accent words.
- No emojis as icons. No sparkle icons or "AI powered" badges.
- No cards inside cards. No coloured top or left borders on every card. No row of big stat cards at the top.
- No status dots unless each dot means a labelled state.
- No all-caps labels or headings. No centred hero layout, no badge above a heading.
- No default shadcn look, no rounded-2xl on everything, no big drop shadows.
- No marketing copy ("seamlessly", "unlock", "powerful"). Labels are short, plain and specific.
- Colour only where it means something. If removing a colour loses no information, remove it.

## Layout
- Three panes, all left-aligned:
  1. Left: the queue grouped by question. Each row: urgency label (text, not just colour), question subject/chapter, number of reports, route. Two sections: "Needs your decision" first, then "Applied automatically" (with one-click undo).
  2. Middle: the question rendered properly (sanitised HTML + native MathML), then a before/after diff of the proposed edit. Inline diff for short edits, side by side for longer ones.
  3. Right: verdict, repair, confidence (shown as a plain number like 0.92, no gauges), evidence in one or two sentences, all student comments for this question, the student reply preview, and the actions.
- The action bar stays fixed in view: Approve, Edit, Reject, Undo.
- Keyboard: J/K next/previous case, A approve, E edit, R reject, U undo, ? shows the shortcuts. Show the shortcut next to each button.
- After an action, move to the next case automatically and show a small, quiet confirmation.
- Audit log in a drawer: time, report, action, before/after. Export as JSON. State clearly that it's stored in this browser (localStorage).
- Empty state when the queue is done: one plain sentence, no illustration.
- Desktop first, works on a 13 inch laptop at 100% zoom with no horizontal scroll.

## Typography
- UI: IBM Plex Sans (400, 500, 600). Built for data interfaces; it clearly separates 1, l, I, 0 and O, which matters when reading answer keys and options.
- Code, IDs, answer keys, find/replace text: IBM Plex Mono.
- Math: `math { font-family: "STIX Two Math", math; }`
- Self-host the font files (WOFF2) in the repo. No Google Fonts CDN.
- Use tabular numbers (`font-variant-numeric: tabular-nums`) for confidence, counts and times.
- Body 15px, line-height 1.5. Question text 17px so the math is easy to read. Max 3 font sizes plus math. Sentence case everywhere.
- Spacing on a 4px scale (4, 8, 12, 16, 24, 32). Corner radius 6px. Borders 1px. Only the action bar may have a shadow, and it must be subtle.

## Colour
One neutral base, one accent, and colour for meaning only. Light mode by default, with a proper dark mode via prefers-color-scheme (not grey text on near-black).

Light:
- Page #FAFAF7, panels #FFFFFF, borders #E4E2DC
- Text #1C1B19, secondary text #5C5A55
- Accent (selected row, focus ring, primary button) deep teal #0F5F5C, text on it #FFFFFF
- Diff removed: background #FDECEA, text #8A1C1C, plus strikethrough
- Diff added: background #E6F4EA, text #14532D, plus underline
- Urgent label (answer key / unsolvable): text #B42318 on #FEF3F2, always with the word, never colour alone

Dark:
- Page #121413, panels #1A1D1C, borders #2C302E
- Text #E8E6E1, secondary text #A5A39D
- Accent #5FB3AD
- Diff removed: background #3A1B1B, text #F4B4B0. Diff added: background #16301F, text #A8DDB5

Rules:
- Write a small script that checks every text/background pair above reaches WCAG AA (4.5:1 for normal text). Adjust any colour that fails and tell me what you changed.
- Red/green diffs must also use strikethrough and underline so colour-blind users can read them.
- Visible keyboard focus ring on everything.

## Before you call the console done
- Take screenshots of the main screen in light and dark mode and check them against this list yourself.
- Check every item in "Avoid every vibe coded sign" and tell me which ones you checked.
