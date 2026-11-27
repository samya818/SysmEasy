"""Provider-agnostic LLM protocol and optional env-based HTTP provider."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

_CACHED_GEMINI_MODELS: list[str] | None = None
_LAST_WORKING_GEMINI_MODEL: str | None = None


@dataclass(frozen=True)
class LLMResponse:
    """Normalized response returned by an LLMProvider implementation."""

    content: str
    model: str
    usage_tokens: int = 0


@runtime_checkable
class LLMProvider(Protocol):
    """Abstract interface for remote or local LLM backends."""

    def complete(self, system_prompt: str, user_prompt: str, *, temperature: float = 0.0) -> LLMResponse:
        """Return a completion for the given system and user prompts."""
        ...


def _load_dotenv() -> None:
    """Load workspace .env in live server runs (skipped under pytest for determinism)."""
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _resolve_gemini_models(api_key: str) -> list[str]:
    """Query Google's REST /models endpoint and return available Gemini models ordered by preference.

    Uses the native REST API (key= param) which always returns JSON — avoids the OpenAI-compat
    endpoint that may return HTML on errors.
    """
    global _CACHED_GEMINI_MODELS
    if _CACHED_GEMINI_MODELS:
        return _CACHED_GEMINI_MODELS
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={urllib.parse.quote(api_key, safe='')}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
        data = json.loads(raw)
        # REST response: {"models": [{"name": "models/gemini-2.0-flash", ...}, ...]}
        ids = [str(m.get("name", "")).removeprefix("models/") for m in data.get("models", [])]
        candidates = [
            mid for mid in ids
            if mid.startswith("gemini-")
            and not any(x in mid for x in ("tts", "image", "audio", "embedding", "robotics", "computer"))
        ]
        if candidates:
            def _score(name: str) -> tuple[int, int, tuple[int, ...]]:
                is_flash = 1 if "flash" in name and "lite" not in name else 0
                is_stable = 0 if any(x in name for x in ("preview", "exp")) else 1
                nums = tuple(int(n) for n in re.findall(r"\d+", name)) or (0,)
                return (is_stable, is_flash, nums)
            ordered = sorted(candidates, key=_score, reverse=True)
            # Prioritize proven fast Flash models
            for preferred_m in reversed(["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-flash-8b"]):
                if preferred_m in ordered:
                    ordered.remove(preferred_m)
                    ordered.insert(0, preferred_m)
            _CACHED_GEMINI_MODELS = ordered[:3]
            return _CACHED_GEMINI_MODELS
    except Exception:
        pass
    return [os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")]


class EnvChatProvider:
    """Lightweight OpenAI-compatible HTTP provider with automatic model fallback on 404/429/503."""

    def __init__(self, api_key: str, base_url: str, model: str, fallback_models: list[str] | None = None) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.fallback_models = fallback_models or []

    def complete(self, system_prompt: str, user_prompt: str, *, temperature: float = 0.0) -> LLMResponse:
        global _LAST_WORKING_GEMINI_MODEL
        preferred = [_LAST_WORKING_GEMINI_MODEL] if _LAST_WORKING_GEMINI_MODEL else []
        models_to_try = []
        for m in preferred + [self.model] + list(self.fallback_models):
            if m and m not in models_to_try:
                models_to_try.append(m)
        last_exc: Exception | None = None
        for idx, mdl in enumerate(models_to_try):
            body: dict[str, object] = {
                "model": mdl,
                "temperature": temperature,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            }
            payload = json.dumps(body).encode("utf-8")
            req = urllib.request.Request(
                f"{self.base_url}/chat/completions",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                _LAST_WORKING_GEMINI_MODEL = mdl
                return LLMResponse(content=data["choices"][0]["message"]["content"], model=mdl)
            except urllib.error.HTTPError as exc:
                last_exc = exc
                if exc.code in (404, 429, 500, 503) and idx < len(models_to_try) - 1:
                    continue
                raise
            except (urllib.error.URLError, TimeoutError) as exc:
                last_exc = exc
                if idx < len(models_to_try) - 1:
                    continue
                raise
        raise last_exc or RuntimeError("Aucun modèle LLM disponible.")


def detect_env_llm_provider(override_gemini_key: str | None = None) -> LLMProvider | None:
    """Return an LLMProvider.

    Priority order:
    1. ``override_gemini_key`` – per-request key supplied by the user via the UI (X-Gemini-Api-Key header).
    2. Environment variables: OPENAI_API_KEY, GROQ_API_KEY, GEMINI_API_KEY (default key set by the platform owner).
    """
    _load_dotenv()
    if override_gemini_key and override_gemini_key.strip():
        key = override_gemini_key.strip()
        models = _resolve_gemini_models(key)
        return EnvChatProvider(
            key,
            "https://generativelanguage.googleapis.com/v1beta/openai",
            models[0],
            fallback_models=models[1:],
        )
    if key := os.environ.get("OPENAI_API_KEY"):
        return EnvChatProvider(
            key,
            os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        )
    if key := os.environ.get("GROQ_API_KEY"):
        return EnvChatProvider(
            key,
            "https://api.groq.com/openai/v1",
            os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant"),
        )
    if key := os.environ.get("GEMINI_API_KEY"):
        models = [os.environ["GEMINI_MODEL"]] if os.environ.get("GEMINI_MODEL") else _resolve_gemini_models(key)
        return EnvChatProvider(
            key,
            "https://generativelanguage.googleapis.com/v1beta/openai",
            models[0],
            fallback_models=models[1:],
        )
    return None


def set_gemini_api_key(api_key: str) -> list[str]:
    """Validate a user-supplied Gemini API key, activate it in memory, and persist to .env."""
    global _CACHED_GEMINI_MODELS, _LAST_WORKING_GEMINI_MODEL
    clean_key = api_key.strip()
    if not clean_key:
        raise ValueError("La clé API Gemini ne peut pas être vide.")

    # Validate key against the native REST endpoint (always returns JSON)
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={urllib.parse.quote(clean_key, safe='')}&pageSize=1"
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            json.loads(resp.read().decode("utf-8"))  # just check it parses
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
            err_data = json.loads(body)
            msg = err_data.get("error", {}).get("message", f"HTTP {exc.code}")
        except Exception:
            msg = f"HTTP {exc.code}"
        raise ValueError(f"Clé API refusée par Google Gemini : {msg}") from exc
    except Exception as exc:
        raise ValueError(f"Impossible de vérifier la clé Gemini : {exc}") from exc

    os.environ["GEMINI_API_KEY"] = clean_key
    _CACHED_GEMINI_MODELS = None
    _LAST_WORKING_GEMINI_MODEL = None

    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    lines: list[str] = []
    if env_path.is_file():
        lines = [ln for ln in env_path.read_text(encoding="utf-8").splitlines() if not ln.strip().startswith("GEMINI_API_KEY=")]
    lines.append(f"GEMINI_API_KEY={clean_key}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return _resolve_gemini_models(clean_key)
