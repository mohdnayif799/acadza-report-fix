"""Settings from environment (.env). Model names are configurable; defaults are pinned."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

from engine.models import ROOT

load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    solver_a: str  # independent solve #1 (strong reasoning model)
    solver_b: str  # independent solve #2 (different model, computes with code execution)
    reviewer: str  # reads question + solution (never key/comment): solution audit, defect scan
    cheap: str  # claim classification (a label from a closed list)
    replier: str  # student replies: tone matters, so one step up from the cheapest model
    confirmer: str  # second opinion on text defects; deliberately not the reviewer's model
    timeout_s: int
    max_attempts: int
    seed: int
    cache_dir: str


def load_settings() -> Settings:
    env = os.environ.get
    return Settings(
        solver_a=env("GEMINI_MODEL_SOLVER_A", "gemini-3.8-flash"),
        solver_b=env("GEMINI_MODEL_SOLVER_B", "gemini-3.5-flash"),
        reviewer=env("GEMINI_MODEL_REVIEWER", "gemini-3.8-flash"),
        cheap=env("GEMINI_MODEL_CHEAP", "gemini-3.5-flash-lite"),
        replier=env("GEMINI_MODEL_REPLIER", "gemini-3.5-flash"),
        confirmer=env("GEMINI_MODEL_CONFIRMER", "gemini-3.5-flash"),
        timeout_s=int(env("LLM_TIMEOUT_S", "180")),
        max_attempts=int(env("LLM_MAX_ATTEMPTS", "5")),
        seed=int(env("LLM_SEED", "7")),
        cache_dir=env("LLM_CACHE_DIR", str(ROOT / "cache" / "llm")),
    )


def api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is empty. Put it in .env (see .env.example).")
    return key
