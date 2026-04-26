"""Backward-compatible OpenRouter backend stub.

OpenRouter support is now implemented in :mod:`abyss.llm.openai_compat`
as ``OpenAICompatBackend`` with the ``openrouter`` provider preset.
This module re-exports ``OpenRouterBackend`` for backward compatibility:

* Old bot.yaml with ``backend.type: openrouter`` continues to work.
* Code that imports ``from abyss.llm.openrouter import OpenRouterBackend``
  continues to work.

For new bots prefer::

    backend:
      type: openai_compat
      provider: openrouter
      model: anthropic/claude-haiku-4.5
"""

from __future__ import annotations

from typing import ClassVar

from abyss.llm.openai_compat import (
    DEFAULT_MAX_HISTORY,
    DEFAULT_MAX_TOKENS,
    DEFAULT_MODEL,
    PROVIDER_PRESETS,
    OpenAICompatBackend,
    _iter_messages,
    _safe_body,
)
from abyss.llm.registry import register

__all__ = [
    "DEFAULT_MAX_HISTORY",
    "DEFAULT_MAX_TOKENS",
    "DEFAULT_MODEL",
    "PROVIDER_PRESETS",
    "OpenRouterBackend",
    "_iter_messages",
    "_safe_body",
]


class OpenRouterBackend(OpenAICompatBackend):
    """OpenRouter-specific backend (legacy alias for OpenAICompatBackend).

    Sets ``_default_provider = "openrouter"`` so bots with
    ``backend.type: openrouter`` pick up the correct base URL and
    API key env var without needing a ``provider`` key in bot.yaml.
    """

    type: ClassVar[str] = "openrouter"
    _default_provider: ClassVar[str | None] = "openrouter"
    _provider_label: ClassVar[str] = "OpenRouter"


register("openrouter", OpenRouterBackend)
