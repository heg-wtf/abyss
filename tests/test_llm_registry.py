"""Tests for the per-bot LLM backend cache in ``abyss.llm.registry``."""

from __future__ import annotations

import logging

import pytest

from abyss.llm import registry


class _FakeBackend:
    type = "claude_code"

    def __init__(self, bot_config=None) -> None:
        self.bot_config = bot_config or {}
        self.closed = False

    async def run(self, request):  # pragma: no cover - unused
        raise NotImplementedError

    async def run_streaming(self, request, on_chunk):  # pragma: no cover - unused
        raise NotImplementedError

    async def cancel(self, _key):  # pragma: no cover - unused
        return True

    async def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def _isolate_registry():
    """Each test starts with an empty cache and ``claude_code`` rebound to
    ``_FakeBackend`` so we don't try to spin up the real SDK."""
    registry._INSTANCES.clear()
    backend_factory = registry._BACKENDS.get("claude_code")
    registry._BACKENDS["claude_code"] = _FakeBackend
    try:
        yield
    finally:
        if backend_factory is not None:
            registry._BACKENDS["claude_code"] = backend_factory
        registry._INSTANCES.clear()


def test_get_or_create_returns_cached_instance_and_refreshes_config():
    first = registry.get_or_create("alpha", {"backend": {"type": "claude_code"}, "model": "opus"})
    second = registry.get_or_create("alpha", {"backend": {"type": "claude_code"}, "model": "haiku"})
    assert first is second
    assert first.bot_config["model"] == "haiku"


def test_get_or_create_recreates_on_backend_type_change(caplog):
    alt_factory = registry._BACKENDS.get("openai_compat")

    class _OtherBackend:
        type = "openai_compat"

        def __init__(self, _bot_config=None) -> None:
            self.bot_config = {}

        async def run(self, request):  # pragma: no cover - unused
            raise NotImplementedError

        async def run_streaming(self, request, on_chunk):  # pragma: no cover - unused
            raise NotImplementedError

        async def cancel(self, _key):  # pragma: no cover - unused
            return True

        async def close(self):  # pragma: no cover - unused
            return None

    registry._BACKENDS["openai_compat"] = _OtherBackend
    try:
        first = registry.get_or_create("alpha", {"backend": {"type": "claude_code"}})
        with caplog.at_level(logging.WARNING):
            second = registry.get_or_create("alpha", {"backend": {"type": "openai_compat"}})
        assert first is not second
        assert any("Backend type changed" in record.message for record in caplog.records)
    finally:
        if alt_factory is not None:
            registry._BACKENDS["openai_compat"] = alt_factory


def test_drop_removes_entry_without_closing():
    registry.get_or_create("alpha", {"backend": {"type": "claude_code"}})
    dropped = registry.drop("alpha")
    assert dropped is not None
    assert "alpha" not in registry._INSTANCES
    assert dropped.closed is False


def test_drop_returns_none_when_missing():
    assert registry.drop("ghost") is None


@pytest.mark.asyncio
async def test_close_all_swallows_per_backend_errors(caplog):
    class _RaisingBackend(_FakeBackend):
        async def close(self):
            raise RuntimeError("close failed")

    registry._BACKENDS["claude_code"] = _RaisingBackend
    registry.get_or_create("alpha", {"backend": {"type": "claude_code"}})
    with caplog.at_level(logging.ERROR):
        await registry.close_all()
    assert "alpha" not in registry._INSTANCES
    assert any("error while closing backend" in record.message for record in caplog.records)


def test_cached_backend_returns_none_when_absent():
    assert registry.cached_backend("ghost") is None
