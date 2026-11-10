"""WCAG AA contrast check for every text/background pair the console uses.

Reads the colour tokens straight from console/styles.css (light :root and the dark block),
so the check cannot drift from the real stylesheet.  Usage: python scripts/check_contrast.py
Exit code 1 if any pair is below 4.5:1 (normal text).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

CSS = Path(__file__).resolve().parent.parent / "console" / "styles.css"
AA = 4.5

# (text token, background token, where it is used)
PAIRS = [
    ("text", "page", "body text on the page"),
    ("text", "panel", "body text on panels"),
    ("text-2", "page", "secondary text on the page"),
    ("text-2", "panel", "secondary text, kbd hints, queue meta"),
    ("text", "selected", "selected queue row text"),
    ("text-2", "selected", "selected queue row status line"),
    ("accent", "selected", "teal marker / accent text on selected row"),
    ("text", "hover", "queue row on hover"),
    ("text-2", "hover", "queue meta on hover"),
    ("on-accent", "accent", "primary button text"),
    ("accent", "panel", "focus ring / accent on panels"),
    ("accent", "page", "focus ring / accent on the page"),
    ("rm-text", "rm-bg", "diff removed"),
    ("add-text", "add-bg", "diff added"),
    ("urgent-text", "urgent-bg", "urgent label"),
    ("urgent-text", "panel", "a disagreeing check"),
    ("panel", "text", "toast (inverted)"),
]


def tokens(block: str) -> dict[str, str]:
    return {k: v.upper() for k, v in re.findall(r"--([\w-]+):\s*(#[0-9A-Fa-f]{6})", block)}


def luminance(hex_colour: str) -> float:
    def chan(c: int) -> float:
        s = c / 255
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = (int(hex_colour[i : i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b)


def ratio(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def main() -> int:
    css = CSS.read_text(encoding="utf-8")
    head, rest = css.split("@media (prefers-color-scheme: dark)", 1)
    light = tokens(head)
    dark = {**light, **tokens(rest.split("\n}\n")[0])}
    failures = 0
    for name, theme in (("light", light), ("dark", dark)):
        print(f"\n{name}")
        for fg, bg, where in PAIRS:
            r = ratio(theme[fg], theme[bg])
            ok = r >= AA
            failures += not ok
            mark = "ok  " if ok else "FAIL"
            print(f"  {mark} {r:5.2f}  {theme[fg]} on {theme[bg]}  {fg} / {bg}  ({where})")
    print(f"\n{failures} pair(s) below {AA}:1")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
