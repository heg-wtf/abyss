"""Backend-agnostic request / result types and the ``LLMBackend`` Protocol.

Two concrete backends ship today: ``claude_code`` (the default — wraps
``claude_runner.py`` + the Python Agent SDK) and ``openrouter`` (a
plain text-only chat adapter that talks to OpenRouter's OpenAI-compatible
chat completions endpoint).

The shape of :class:`LLMRequest` carries the union of fields needed by
both. Backends ignore fields that aren't meaningful to them
(``claude_session_id`` / ``resume_session`` are no-ops on OpenRouter,
for example).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, ClassVar, Protocol


class ToolUnavailableError(Exception):
    """Raised when a backend cannot satisfy a request that requires tools.

    The OpenRouter backend uses this to signal that a bot configured for
    text-only chat has been asked to invoke a tool. Handlers translate
    this into a user-facing message rather than crashing the run.
    """


@dataclass(frozen=True, slots=True)
class LLMRequest:
    """Backend-agnostic envelope for one LLM turn.

    Only the fields below are part of the public contract. Backends may
    consult ``bot_config`` for backend-specific options
    (``bot_config["backend"]["model"]`` etc.) without adding new
    parameters here.
    """

    bot_name: str
    bot_path: Path
    session_directory: Path
    working_directory: str
    bot_config: dict[str, Any]
    user_prompt: str
    timeout: int = 600
    session_key: str | None = None
    images: tuple[Path, ...] = ()
    extra_arguments: tuple[str, ...] = ()
    claude_session_id: str | None = None
    resume_session: bool = False
    max_history: int = 20


@dataclass(frozen=True, slots=True)
class LLMResult:
    """Outcome of one backend run."""

    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    session_id: str | None = None
    stop_reason: str | None = None
    raw: Any = None


OnChunk = Callable[[str], Awaitable[None]]


class LLMBackend(Protocol):
    """Contract every backend must satisfy.

    Backends are stateless on purpose — handlers create one instance per
    call (or per bot) and let it manage any internal state (HTTP client
    pools, SDK clients, etc.). The :func:`close` method releases those
    resources at shutdown.
    """

    type: ClassVar[str]
    """Stable identifier matching ``bot_config["backend"]["type"]``."""

    async def run(self, request: LLMRequest) -> LLMResult: ...

    async def run_streaming(
        self,
        request: LLMRequest,
        on_chunk: OnChunk,
    ) -> LLMResult: ...

    async def cancel(self, session_key: str) -> bool: ...

    async def close(self) -> None: ...

    def supports_tools(self) -> bool: ...

    def supports_session_resume(self) -> bool: ...


def resolve_backend_type(bot_config: dict[str, Any]) -> str:
    """Return the backend type from ``bot_config``, defaulting to claude_code."""
    block = bot_config.get("backend")
    if isinstance(block, dict):
        bt = block.get("type")
        if isinstance(bt, str) and bt.strip():
            return bt.strip()
    return "claude_code"


def backend_options(bot_config: dict[str, Any]) -> dict[str, Any]:
    """Return the ``backend.*`` sub-dict (excluding ``type``)."""
    block = bot_config.get("backend") or {}
    if not isinstance(block, dict):
        return {}
    return {k: v for k, v in block.items() if k != "type"}


_FROZEN_DEFAULTS = {
    "extra_arguments": (),
    "images": (),
}


def _normalize_tuple(value: Any, key: str) -> tuple:
    """Coerce list / None into the tuple form ``LLMRequest`` expects."""
    if value is None:
        return _FROZEN_DEFAULTS[key]
    if isinstance(value, tuple):
        return value
    return tuple(value)


def make_request(**kwargs: Any) -> LLMRequest:
    """Construct an :class:`LLMRequest`, coercing list args to tuples."""
    if "extra_arguments" in kwargs:
        kwargs["extra_arguments"] = _normalize_tuple(kwargs["extra_arguments"], "extra_arguments")
    if "images" in kwargs:
        kwargs["images"] = _normalize_tuple(kwargs["images"], "images")
    return LLMRequest(**kwargs)


# Re-export ``field`` so backend modules can build request defaults
# without importing ``dataclasses`` directly.
__all__ = [
    "LLMBackend",
    "LLMRequest",
    "LLMResult",
    "OnChunk",
    "ToolUnavailableError",
    "backend_options",
    "field",
    "make_request",
    "resolve_backend_type",
]
