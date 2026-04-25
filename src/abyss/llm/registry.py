"""Backend registry + per-bot instance cache."""

from __future__ import annotations

import logging
from typing import Any

from abyss.llm.base import LLMBackend, resolve_backend_type

logger = logging.getLogger(__name__)

_BACKENDS: dict[str, type[LLMBackend]] = {}
_INSTANCES: dict[str, LLMBackend] = {}


def register(name: str, cls: type[LLMBackend]) -> None:
    """Associate a backend class with its config ``type`` string."""
    _BACKENDS[name] = cls


def registered_backend_types() -> list[str]:
    """Return the list of registered backend types."""
    return sorted(_BACKENDS.keys())


def get_backend(bot_config: dict[str, Any]) -> LLMBackend:
    """Instantiate the backend referenced by ``bot_config``.

    Each call constructs a fresh instance — use :func:`get_or_create`
    when you need the per-bot cached version.
    """
    backend_type = resolve_backend_type(bot_config)
    cls = _BACKENDS.get(backend_type)
    if cls is None:
        registered = ", ".join(registered_backend_types()) or "(none)"
        raise ValueError(
            f"Unknown LLM backend type: {backend_type!r}. Registered backends: {registered}"
        )
    return cls(bot_config)


def get_or_create(bot_name: str, bot_config: dict[str, Any]) -> LLMBackend:
    """Return a cached backend for ``bot_name``, creating it on first use.

    The cache key is the bot name only — bot config changes that swap
    the backend type require a process restart (or an explicit
    :func:`drop` call). This trades runtime flexibility for the win of
    sharing connection pools and process-tracking state across the
    handler / cron / heartbeat call sites.
    """
    cached = _INSTANCES.get(bot_name)
    desired_type = resolve_backend_type(bot_config)
    if cached is not None and cached.type == desired_type:
        # Refresh in-place so callers see config changes (model, skills,
        # backend.* options) without paying for a new client / SDK pool.
        try:
            cached.bot_config = bot_config  # type: ignore[attr-defined]
        except AttributeError:
            pass
        return cached

    if cached is not None:
        logger.warning(
            "Backend type changed for bot %s (%s -> %s); recreating",
            bot_name,
            cached.type,
            desired_type,
        )

    backend = get_backend(bot_config)
    _INSTANCES[bot_name] = backend
    return backend


def drop(bot_name: str) -> LLMBackend | None:
    """Remove a bot's backend from the cache without closing it."""
    return _INSTANCES.pop(bot_name, None)


async def close_all() -> None:
    """Close every cached backend instance and clear the cache."""
    while _INSTANCES:
        bot_name, backend = _INSTANCES.popitem()
        try:
            await backend.close()
        except Exception:  # noqa: BLE001
            logger.exception("error while closing backend for %s", bot_name)


def cached_backend(bot_name: str) -> LLMBackend | None:
    """Return the cached backend for ``bot_name`` or ``None``."""
    return _INSTANCES.get(bot_name)
