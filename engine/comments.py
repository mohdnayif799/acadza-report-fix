"""Cheap signals about the student's comment. The comment is data, never an instruction."""

from __future__ import annotations

import re
from dataclasses import dataclass

_KEYBOARD_ROWS = ("qwertyuiop", "asdfghjkl", "zxcvbnm")
_VAGUE = {
    "wrong",
    "galat",
    "error",
    "incorrect",
    "wrong ans",
    "wrong answer",
    "galat hai",
    "mistake",
    "bad",
    "?",
}
_INJECTION = re.compile(
    r"ignore (?:all |any )?(?:previous|prior|above) (?:instructions|prompts?)|"
    r"\byou are (?:now )?(?:the |an? )?(?:admin|system|assistant|bot)\b|system prompt|"
    r"\bmark (?:this|the) report as\b|\bas an ai\b|\bdisregard\b.*\binstructions\b|"
    r"\bchange the answer to\b|\bnew instructions\b|<\s*/?\s*(?:system|instructions?)\s*>",
    re.I,
)
_HINGLISH = {
    "hai",
    "hain",
    "nahi",
    "nahin",
    "kyu",
    "kyun",
    "kya",
    "chahiye",
    "aa",
    "raha",
    "rahi",
    "karu",
    "karun",
    "hona",
    "toh",
    "galat",
    "ki",
    "di",
    "me",
    "mein",
    "ka",
    "ke",
    "bhi",
    "sahi",
    "aana",
    "hi",
    "ho",
}


@dataclass(frozen=True)
class CommentSignals:
    is_empty: bool
    is_noise: bool
    is_vague: bool
    injection: bool
    hinglish: bool


def _is_keyboard_mash(letters: str) -> bool:
    if len(letters) < 4:
        return False
    return any(letters in row or letters[::-1] in row for row in _KEYBOARD_ROWS) or (
        len(set(letters)) <= 2
    )


def analyze_comment(comment: str) -> CommentSignals:
    text = (comment or "").strip()
    letters = re.sub(r"[^a-z]", "", text.lower())
    words = re.findall(r"[a-z]+", text.lower())
    is_empty = not letters
    is_noise = is_empty or (len(words) == 1 and _is_keyboard_mash(letters))
    is_vague = not is_noise and text.lower().strip(" .!?") in _VAGUE
    hinglish = sum(w in _HINGLISH for w in words) >= 1 and any(
        w in {"hai", "nahi", "kyu", "chahiye", "galat", "karu", "hona", "aana", "raha", "kya"}
        for w in words
    )
    return CommentSignals(is_empty, is_noise, is_vague, bool(_INJECTION.search(text)), hinglish)
