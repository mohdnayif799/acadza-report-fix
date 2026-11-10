"""Turn Acadza's HTML + inline MathML into clean text for the LLM.

Read-only: raw HTML is never modified here. Edits are find/replace on the raw strings.

MathML is parsed with defusedxml *before* any entity decoding (decoding `&#x3C;` first
turns it into a literal `<` and breaks the parse; see build-log AI-WRONG #1).
"""

from __future__ import annotations

import html
import re
from html.entities import name2codepoint
from xml.etree.ElementTree import Element

from defusedxml import DefusedXmlException
from defusedxml.ElementTree import ParseError, fromstring

MATH_RE = re.compile(r"<math\b.*?</math>", re.S | re.I)
_NAMED_ENTITY = re.compile(r"&([A-Za-z][A-Za-z0-9]*);")
_BARE_AMP = re.compile(r"&(?!#\d+;|#x[0-9A-Fa-f]+;|[A-Za-z][A-Za-z0-9]*;)")
_XML_ENTITIES = {"amp", "lt", "gt", "quot", "apos"}
_TOKEN_TAGS = {"mi", "mn", "mo", "ms"}
_ARROWS = {"→", "⃗", "⟶"}
_RING = {"∘", "°", "˚"}
_BARS = {"¯", "‾", "―", "_", "−"}
_PLACEHOLDER = "\x00{}\x00"
_PLACEHOLDER_RE = re.compile(r"\x00(\d+)\x00")
_OPTION_MARK = re.compile(r"^[ \t]*\(([A-D])\)[ \t]*", re.M)


def _xml_safe(math_html: str) -> str:
    """Make a browser-tolerated <math> block parseable as XML without decoding it."""

    def named(m: re.Match) -> str:
        name = m.group(1)
        if name in _XML_ENTITIES:
            return m.group(0)
        cp = name2codepoint.get(name)
        return f"&#{cp};" if cp else f"&amp;{name};"

    return _NAMED_ENTITY.sub(named, _BARE_AMP.sub("&amp;", math_html))


def _wrap(s: str) -> str:
    s = s.strip()
    # Only a bare number or a bare word is safe without brackets: "2ε_0" is not.
    return s if re.fullmatch(r"\d+(?:\.\d+)?|[^\W\d_]+", s) else f"({s})"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _mover(base: str, over: str) -> str:
    if over in _ARROWS:
        return f"vec({base})"
    if over in _RING and base == "A":
        return "Å"
    if over in _BARS:
        return f"bar({base})"
    if over in {"^", "ˆ"}:
        return f"hat({base})"
    return f"{base}{over}"


def mathml_to_text(el: Element) -> str:
    tag = _local(el.tag)
    if tag in _TOKEN_TAGS:
        return (el.text or "").replace("\xa0", " ").strip()
    if tag == "mtext":
        return (el.text or "").replace("\xa0", " ")
    if tag == "mspace":
        return "\n" if el.get("linebreak") == "newline" else " "
    parts = [mathml_to_text(k) for k in el]
    n = len(parts)
    if tag == "mfrac" and n == 2:
        return f"{_wrap(parts[0])}/{_wrap(parts[1])}"
    if tag == "msup" and n == 2:
        return f"{_wrap(parts[0])}^{_wrap(parts[1])}"
    if tag == "msub" and n == 2:
        return f"{_wrap(parts[0])}_{_wrap(parts[1])}"
    if tag == "msubsup" and n == 3:
        return f"{_wrap(parts[0])}_{_wrap(parts[1])}^{_wrap(parts[2])}"
    if tag == "msqrt":
        return "√(" + "".join(parts) + ")"
    if tag == "mroot" and n == 2:
        return f"{_wrap(parts[1])}√({parts[0]})"
    if tag == "mover" and n == 2:
        return _mover(parts[0].strip(), parts[1].strip())
    if tag == "munder" and n == 2:
        return f"{_wrap(parts[0])}_{_wrap(parts[1])}"
    if tag == "munderover" and n == 3:
        return f"{_wrap(parts[0])}_{_wrap(parts[1])}^{_wrap(parts[2])}"
    if tag == "mtr":
        return " ".join(parts)
    if tag == "mtable":
        return "\n".join(parts)
    return "".join(parts)


def math_block_to_text(math_html: str) -> str:
    """One <math>...</math> block -> linear text. Falls back to tag stripping."""
    try:
        return mathml_to_text(fromstring(_xml_safe(math_html))).strip()
    except (ParseError, DefusedXmlException):
        return html.unescape(re.sub(r"<[^>]+>", "", math_html)).strip()


def _strip_html(s: str) -> str:
    s = re.sub(r"<br\s*/?>|</p>|</h\d>|</div>|</li>|<li\b[^>]*>", "\n", s, flags=re.I)
    s = re.sub(r"<img\b[^>]*>", " [image] ", s, flags=re.I)
    s = re.sub(r"<sup\b[^>]*>", "^", s, flags=re.I)
    s = re.sub(r"<sub\b[^>]*>", "_", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    return html.unescape(s)


def _tidy(s: str) -> str:
    s = s.replace("\xa0", " ").replace("​", "")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in s.split("\n")]
    return "\n".join(line for line in lines if line)


def html_to_text(raw: str | None) -> str:
    """Question/solution HTML -> clean, readable text (math linearised inline)."""
    if not raw:
        return ""
    maths: list[str] = []

    def stash(m: re.Match) -> str:
        maths.append(math_block_to_text(m.group(0)))
        return _PLACEHOLDER.format(len(maths) - 1)

    text = _strip_html(MATH_RE.sub(stash, raw))
    text = _PLACEHOLDER_RE.sub(lambda m: f" {maths[int(m.group(1))]} ", text)
    return _tidy(text)


def split_options(text: str) -> tuple[str, dict[str, str]]:
    """Split question text into (stem, {letter: option text}).

    Options are `(A) ...` markers at the start of a line. Uses the *last* run that
    starts at (A) and continues B, C, D in order, so "Assertion (A):" in a stem
    (mid-line) and stray letters do not count. A blank option maps to "".
    """
    marks = list(_OPTION_MARK.finditer(text))
    run: list[re.Match] = []
    for i, m in enumerate(marks):
        if m.group(1) != "A":
            continue
        candidate = [m]
        for nxt in marks[i + 1 :]:
            if ord(nxt.group(1)) != ord(candidate[-1].group(1)) + 1:
                break
            candidate.append(nxt)
        run = candidate
    if not run:
        return text.strip(), {}
    options = {}
    for j, m in enumerate(run):
        end = run[j + 1].start() if j + 1 < len(run) else len(text)
        options[m.group(1)] = text[m.end() : end].strip()
    return text[: run[0].start()].strip(), options
