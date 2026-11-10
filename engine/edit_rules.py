"""Content rules for proposed edits: what each repair type may change, and markup safety.

Edits are written into HTML that students see, and some of them are model-written, so
added markup is allowlisted (no scripts, event handlers or javascript:/data: URLs) and
each repair type may only change what its taxonomy label says.
"""

from __future__ import annotations

import dataclasses
import re

from engine.checks import EXAM_TAG, options_of
from engine.models import Question
from engine.parse import html_to_text

ALLOWED_TAGS = {
    "br",
    "span",
    "sup",
    "sub",
    "b",
    "i",
    "em",
    "strong",
    "p",
    "h3",
    "math",
    "mrow",
    "mi",
    "mn",
    "mo",
    "mtext",
    "mfrac",
    "msup",
    "msub",
    "msubsup",
    "msqrt",
    "mroot",
    "mover",
    "munder",
    "munderover",
    "mspace",
    "mstyle",
    "mtable",
    "mtr",
    "mtd",
}
ALLOWED_ATTRS = {
    "xmlns",
    "display",
    "mathvariant",
    "displaystyle",
    "stretchy",
    "fence",
    "form",
    "linebreak",
    "width",
    "columnalign",
    "style",
}
_TAG = re.compile(r"<\s*/?\s*([A-Za-z][\w:-]*)([^>]*)>")
_ATTR = re.compile(r"([A-Za-z_:][\w:.-]*)\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)")
_SAFE_STYLE = re.compile(r"^\s*color\s*:\s*#[0-9A-Fa-f]{3,8}\s*;?\s*$")
_DANGEROUS = re.compile(r"javascript:|vbscript:|data:|expression\s*\(|url\s*\(|<!--|<!\[", re.I)
_NOISE_TEXT = re.compile(
    r"^\s*(?:Q\.?\s*\d+[.):]?|\d+[.)]|space for rough work|\(?source:[^)]*\)?|"
    r"rough work)\s*$",
    re.I,
)


def markup_problems(find: str, replace: str) -> list[str]:
    """Markup added by an edit must be on the allowlist and carry no active content."""
    if not isinstance(replace, str):
        return []
    problems = []
    if _DANGEROUS.search(replace) and not _DANGEROUS.search(find):
        problems.append("replace adds a script-capable URL, CSS expression or comment")
    # Raw LaTeX or caret powers would create a new markup_leak defect for students to see.
    for pattern, what in ((r"\\[A-Za-z]+", "raw LaTeX"), (r"\^", "a '^' power")):
        if re.search(pattern, replace) and not re.search(pattern, find):
            problems.append(f"replace adds {what}, which students would see as code")
    for tag, attrs in _TAG.findall(replace):
        if tag.lower() not in ALLOWED_TAGS:
            problems.append(f"replace adds disallowed tag <{tag}>")
        for name, value in _ATTR.findall(attrs):
            lname = name.lower()
            if lname not in ALLOWED_ATTRS or lname.startswith("on"):
                problems.append(f"replace adds disallowed attribute {name!r}")
            elif lname == "style" and not _SAFE_STYLE.match(value.strip("\"'")):
                problems.append("replace adds a style other than a plain colour")
    return problems


def _digits(html: str) -> str:
    text = re.sub(r"\\[A-Za-z]+", "", html_to_text(html) if "<" in html else html)
    return re.sub(r"\D", "", text)


def _numbers(text: str) -> set[str]:
    return set(re.findall(r"\d+(?:\.\d+)?", text))


def _non_letters(s: str) -> str:
    return re.sub(r"[^\W\d_]|\s", "", s)


def _changed_options(before: Question, after: Question) -> list[str]:
    old, new = options_of(before)[1], options_of(after)[1]
    return [k for k, v in old.items() if v.strip() and new.get(k, "").strip() != v.strip()]


def _deleted_text(find: str, replace: str) -> str | None:
    """The removed span if `replace` is `find` with one contiguous piece cut out."""
    if len(replace) >= len(find):
        return None
    for i in range(len(replace) + 1):
        if find[:i] == replace[:i] and find[i + len(find) - len(replace) :] == replace[i:]:
            return find[i : i + len(find) - len(replace)]
    return None


def repair_rule_problems(repair: str, edit: dict, q: Question) -> list[str]:
    """What a given repair type is allowed to change (taxonomy labels, made executable)."""
    find, replace = edit["find"], edit["replace"]
    if repair == "spelling" and _non_letters(find) != _non_letters(replace):
        return ["spelling edit changes a value, symbol or tag (words only)"]
    if repair in ("exam_reference", "noise"):
        removed = _deleted_text(find, replace)
        if removed is None:
            return [f"{repair} edit must only delete text"]
        pattern = EXAM_TAG if repair == "exam_reference" else _NOISE_TEXT
        m = pattern.search(removed)
        if not m or m.group(0).strip() != removed.strip():
            return [f"deleted text {removed!r} does not look like a {repair.replace('_', ' ')}"]
    if repair == "answer_form":
        if find not in replace:
            return ["answer_form edit must be additive (find kept inside replace)"]
        if re.search(r"\d", replace.replace(find, "", 1)):
            return ["answer_form may not add numbers (only a unit or answer form)"]
    if repair in ("markup_leak", "notation") and _digits(find) != _digits(replace):
        return [f"{repair} edit changes the digits shown ({_digits(find)} -> {_digits(replace)})"]
    if repair == "stem_data":
        # Insert the missing value, or change only a number. Nothing else in the stem moves
        # (a reviewer once slipped "are connected" -> "is connected" into this edit).
        only_insert = _deleted_text(replace, find) is not None
        only_numbers = re.sub(r"\d+(?:\.\d+)?", "#", find) == re.sub(r"\d+(?:\.\d+)?", "#", replace)
        if not (only_insert or only_numbers):
            return ["stem_data edit may only insert the missing value or change a number"]
        solution_numbers = _numbers(html_to_text(q.solution_html))
        added = _numbers(html_to_text(replace)) - _numbers(html_to_text(find))
        missing = sorted(n for n in added if n not in solution_numbers)
        if not added:
            return ["stem_data edit adds no value"]
        if missing:
            return [f"stem_data adds {missing}, which the solution does not state"]
    if repair == "option_repair":
        after = dataclasses.replace(q, question_html=q.question_html.replace(find, replace, 1))
        if options_of(after)[0] != options_of(q)[0]:
            return ["option_repair edit changes the stem text"]
        changed = _changed_options(q, after)
        if changed:
            return [
                f"option_repair rewrites existing option(s) {changed}; only blank or "
                "missing options may be filled"
            ]
    return []
