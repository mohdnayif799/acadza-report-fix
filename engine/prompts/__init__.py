"""Versioned prompt files: engine/prompts/<name>.v<N>.txt. The highest N is used.

Old versions stay in the folder so PROMPTS.md can show what changed and why.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Prompt:
    name: str
    version: int
    text: str


def load(name: str) -> Prompt:
    files = []
    for p in _DIR.glob(f"{name}.v*.txt"):
        m = re.fullmatch(rf"{re.escape(name)}\.v(\d+)\.txt", p.name)
        if m:
            files.append((int(m.group(1)), p))
    if not files:
        raise FileNotFoundError(f"no prompt file for {name!r}")
    version, path = max(files)
    return Prompt(name, version, path.read_text(encoding="utf-8").strip())
