"""Provider-agnostic LLM protocol for cognitive pipeline stages (A2, A3, A6b)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


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
