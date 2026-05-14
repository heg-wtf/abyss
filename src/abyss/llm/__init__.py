"""LLM backend abstraction for abyss.

Each bot picks an :class:`LLMBackend` via its ``bot.yaml`` ``backend``
block (default: Claude Code via ``claude_runner.py`` and the Python
Agent SDK). Adding a new backend means dropping a module under
``abyss.llm`` and registering it via :func:`register`.
"""

from __future__ import annotations

from abyss.llm.base import LLMBackend, LLMRequest, LLMResult, ToolUnavailableError
from abyss.llm.registry import (
    cached_backend,
    close_all,
    drop,
    get_backend,
    get_or_create,
    register,
    registered_backend_types,
)

__all__ = [
    "LLMBackend",
    "LLMRequest",
    "LLMResult",
    "ToolUnavailableError",
    "cached_backend",
    "close_all",
    "drop",
    "get_backend",
    "get_or_create",
    "register",
    "registered_backend_types",
]


def _autoregister() -> None:
    """Import the bundled backends so their ``register`` calls run."""
    # Imported for their side-effects (calls to ``register`` at module scope).
    from abyss.llm import claude_code  # noqa: F401


_autoregister()
