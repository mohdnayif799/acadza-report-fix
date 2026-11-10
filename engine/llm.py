"""Gemini client: disk cache (reruns cost nothing), retries with backoff, token log.

Every call is keyed by sha256(model, system, user, schema, tools, temperature, seed). A cache
hit never touches the network. Each call (hit or miss) is appended to cache/token_log.jsonl.
The API key is read from the environment and never logged.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from engine.config import Settings, api_key, load_settings

log = logging.getLogger(__name__)
RETRYABLE_CODES = {408, 429, 500, 502, 503, 504}
# The pipeline calls from 8 threads; unlocked appends interleaved and corrupted log lines.
_LOG_LOCK = threading.Lock()


@dataclass(frozen=True)
class LLMResult:
    purpose: str
    model: str
    text: str
    data: Any  # parsed JSON (dict/list) or None
    code: tuple[str, ...]  # code the model executed (code-execution calls)
    code_output: tuple[str, ...]
    usage: dict
    cached: bool


class LLMError(RuntimeError):
    pass


_client = None


def _get_client(settings: Settings):
    global _client
    if _client is None:
        from google import genai
        from google.genai import types

        _client = genai.Client(
            api_key=api_key(), http_options=types.HttpOptions(timeout=settings.timeout_s * 1000)
        )
    return _client


def _cache_key(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def extract_json(text: str) -> Any:
    """Parse the JSON object in a model reply (whole text, a ```json fence, or the last {...})."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    fences = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    candidates = fences[::-1] + [text[i:] for i in _brace_starts(text)]
    for c in candidates:
        try:
            return json.JSONDecoder().raw_decode(c)[0]
        except json.JSONDecodeError:
            continue
    return None


def _brace_starts(text: str) -> list[int]:
    return [m.start() for m in re.finditer(r"\{", text)][::-1]


def _log_usage(settings: Settings, row: dict) -> None:
    path = Path(settings.cache_dir).parent / "token_log.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with _LOG_LOCK, path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def _usage(resp: Any) -> dict:
    u = getattr(resp, "usage_metadata", None)
    get = (lambda k: getattr(u, k, None) or 0) if u else (lambda k: 0)
    return {
        "prompt": get("prompt_token_count"),
        "output": get("candidates_token_count"),
        "thoughts": get("thoughts_token_count"),
        "tool": get("tool_use_prompt_token_count"),
        "total": get("total_token_count"),
    }


def _parts(resp: Any) -> tuple[str, list[str], list[str]]:
    text, code, out = [], [], []
    for cand in getattr(resp, "candidates", None) or []:
        for part in getattr(getattr(cand, "content", None), "parts", None) or []:
            if getattr(part, "thought", False):
                continue
            if getattr(part, "text", None):
                text.append(part.text)
            if getattr(part, "executable_code", None):
                code.append(part.executable_code.code or "")
            if getattr(part, "code_execution_result", None):
                out.append(part.code_execution_result.output or "")
    return "\n".join(text), code, out


def _is_retryable(exc: Exception) -> bool:
    code = getattr(exc, "code", None)
    if isinstance(code, int):
        return code in RETRYABLE_CODES
    return type(exc).__name__ in {
        "ReadTimeout",
        "ConnectTimeout",
        "ConnectError",
        "TimeoutException",
        "RemoteProtocolError",
        "ServerError",
    }


def _request(
    settings: Settings,
    model: str,
    system: str,
    user: str,
    schema: dict | None,
    code_execution: bool,
    temperature: float,
) -> Any:
    from google.genai import types

    config = types.GenerateContentConfig(
        system_instruction=system,
        temperature=temperature,
        seed=settings.seed,
        tools=[types.Tool(code_execution=types.ToolCodeExecution())] if code_execution else None,
        response_mime_type="application/json" if schema and not code_execution else None,
        response_json_schema=schema if not code_execution else None,
    )
    client = _get_client(settings)
    for attempt in range(1, settings.max_attempts + 1):
        try:
            return client.models.generate_content(model=model, contents=user, config=config)
        except Exception as exc:  # noqa: BLE001 - classified below, re-raised if not retryable
            if attempt == settings.max_attempts or not _is_retryable(exc):
                raise LLMError(f"{model} failed after {attempt} attempt(s): {exc}") from exc
            wait = 2**attempt
            log.warning("%s attempt %d failed (%s); retrying in %ds", model, attempt, exc, wait)
            time.sleep(wait)
    raise LLMError("unreachable")


def call(
    *,
    purpose: str,
    model: str,
    system: str,
    user: str,
    schema: dict | None = None,
    code_execution: bool = False,
    temperature: float = 0.0,
    settings: Settings | None = None,
) -> LLMResult:
    settings = settings or load_settings()
    payload = {
        "model": model,
        "system": system,
        "user": user,
        "schema": schema,
        "code_execution": code_execution,
        "temperature": temperature,
        "seed": settings.seed,
    }
    key = _cache_key(payload)
    path = Path(settings.cache_dir) / purpose / f"{key}.json"
    started = time.monotonic()
    if path.exists():
        stored = json.loads(path.read_text(encoding="utf-8"))
        cached = True
    else:
        resp = _request(settings, model, system, user, schema, code_execution, temperature)
        text, code, out = _parts(resp)
        stored = {
            "request": payload,
            "text": text,
            "code": code,
            "code_output": out,
            "usage": _usage(resp),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(stored, ensure_ascii=False, indent=1), encoding="utf-8")
        cached = False
    usage = stored["usage"]
    _log_usage(
        settings,
        {
            "ts": datetime.now(UTC).isoformat(timespec="seconds"),
            "purpose": purpose,
            "model": model,
            "cached": cached,
            "latency_s": round(time.monotonic() - started, 2),
            **({k: 0 for k in usage} if cached else usage),
        },
    )
    data = extract_json(stored["text"]) if (schema or code_execution) else None
    return LLMResult(
        purpose,
        model,
        stored["text"],
        data,
        tuple(stored["code"]),
        tuple(stored["code_output"]),
        usage,
        cached,
    )
