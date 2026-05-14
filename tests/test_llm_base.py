"""Tests for llm.base + llm.registry."""

from __future__ import annotations

from pathlib import Path

import pytest

from abyss.llm import (
    LLMRequest,
    LLMResult,
    cached_backend,
    close_all,
    get_backend,
    get_or_create,
    register,
    registered_backend_types,
)
from abyss.llm.base import backend_options, resolve_backend_type


def test_registered_backends_includes_defaults() -> None:
    types = registered_backend_types()
    assert "claude_code" in types


def test_resolve_backend_type_default() -> None:
    assert resolve_backend_type({}) == "claude_code"


def test_resolve_backend_type_explicit() -> None:
    assert resolve_backend_type({"backend": {"type": "claude_code"}}) == "claude_code"


def test_resolve_backend_type_blank_falls_back() -> None:
    assert resolve_backend_type({"backend": {"type": "  "}}) == "claude_code"


def test_backend_options_strips_type() -> None:
    options = backend_options({"backend": {"type": "claude_code", "model": "x"}})
    assert options == {"model": "x"}


def test_get_backend_unknown_type_raises() -> None:
    with pytest.raises(ValueError, match="Unknown LLM backend"):
        get_backend({"backend": {"type": "moonshine"}})


def test_get_backend_retired_openai_compat_raises_with_migration_hint() -> None:
    with pytest.raises(ValueError, match="removed in v2026.05.15"):
        get_backend({"backend": {"type": "openai_compat"}})


def test_get_backend_retired_openrouter_raises_with_migration_hint() -> None:
    with pytest.raises(ValueError, match="removed in v2026.05.15"):
        get_backend({"backend": {"type": "openrouter"}})


def test_get_backend_returns_fresh_instance() -> None:
    a = get_backend({"backend": {"type": "claude_code"}})
    b = get_backend({"backend": {"type": "claude_code"}})
    assert a is not b


def test_get_or_create_caches_per_bot_name() -> None:
    cfg = {"backend": {"type": "claude_code"}}
    a = get_or_create("alpha", cfg)
    b = get_or_create("alpha", cfg)
    assert a is b


def test_get_or_create_recreates_on_type_change() -> None:
    """Backend type swap clears the cached instance.

    Uses a registered stand-in backend instead of a second concrete
    backend because Claude Code is now the only shipped backend.
    """
    from abyss.llm import registry

    class _AltBackend:
        type = "alt"

        def __init__(self, bot_config: dict) -> None:
            self.bot_config = bot_config

        async def run(self, request):  # pragma: no cover
            return LLMResult(text="ok")

        async def run_streaming(self, request, on_chunk):  # pragma: no cover
            return LLMResult(text="ok")

        async def cancel(self, session_key: str) -> bool:  # pragma: no cover
            return False

        async def close(self) -> None:  # pragma: no cover
            return None

        def supports_tools(self) -> bool:
            return False

        def supports_session_resume(self) -> bool:
            return False

    register("alt", _AltBackend)
    try:
        a = get_or_create("alpha", {"backend": {"type": "claude_code"}})
        b = get_or_create("alpha", {"backend": {"type": "alt"}})
        assert a is not b
        assert b.type == "alt"
    finally:
        registry._INSTANCES.pop("alpha", None)
        registry._BACKENDS.pop("alt", None)


def test_get_or_create_updates_bot_config_on_cached_return() -> None:
    a = get_or_create(
        "alpha",
        {"backend": {"type": "claude_code"}, "model": "sonnet"},
    )
    b = get_or_create(
        "alpha",
        {"backend": {"type": "claude_code"}, "model": "opus"},
    )
    assert a is b
    assert b.bot_config["model"] == "opus"  # type: ignore[attr-defined]


def test_cached_backend_lookup() -> None:
    assert cached_backend("ghost") is None
    backend = get_or_create("ghost", {"backend": {"type": "claude_code"}})
    assert cached_backend("ghost") is backend


@pytest.mark.asyncio
async def test_close_all_clears_cache() -> None:
    get_or_create("alpha", {"backend": {"type": "claude_code"}})
    get_or_create("beta", {"backend": {"type": "claude_code"}})
    assert cached_backend("alpha") is not None
    await close_all()
    assert cached_backend("alpha") is None
    assert cached_backend("beta") is None


def test_llm_request_construction() -> None:
    req = LLMRequest(
        bot_name="x",
        bot_path=Path("/tmp/x"),
        session_directory=Path("/tmp/x/sessions/chat_1"),
        working_directory="/tmp/x/sessions/chat_1",
        bot_config={"model": "opus"},
        user_prompt="hi",
    )
    assert req.timeout == 600
    assert req.extra_arguments == ()
    assert req.images == ()


def test_llm_result_defaults() -> None:
    result = LLMResult(text="hello")
    assert result.input_tokens is None
    assert result.session_id is None


class _FakeBackend:
    type = "fake"

    def __init__(self, bot_config: dict) -> None:
        self.bot_config = bot_config

    async def run(self, request):  # pragma: no cover - not exercised here
        return LLMResult(text="ok")

    async def run_streaming(self, request, on_chunk):  # pragma: no cover
        return LLMResult(text="ok")

    async def cancel(self, session_key: str) -> bool:  # pragma: no cover
        return False

    async def close(self) -> None:  # pragma: no cover
        return None

    def supports_tools(self) -> bool:
        return False

    def supports_session_resume(self) -> bool:
        return False


def test_register_and_use_custom_backend() -> None:
    register("fake", _FakeBackend)
    try:
        backend = get_backend({"backend": {"type": "fake"}})
        assert isinstance(backend, _FakeBackend)
        assert backend.supports_tools() is False
    finally:
        # restore registry
        from abyss.llm import registry

        registry._BACKENDS.pop("fake", None)


def test_protocol_runtime_is_structural() -> None:
    """LLMBackend is a structural ``Protocol`` — duck typing suffices."""
    fake = _FakeBackend({})
    # The Protocol isn't ``@runtime_checkable`` so isinstance() raises.
    # We rely on duck typing instead — confirm the methods exist.
    assert callable(getattr(fake, "run"))
    assert callable(getattr(fake, "run_streaming"))
    assert callable(getattr(fake, "cancel"))
    assert callable(getattr(fake, "close"))
    assert fake.type == "fake"


def test_backend_options_returns_empty_when_block_is_not_a_dict() -> None:
    from abyss.llm.base import backend_options

    # ``backend`` keyed to a non-dict (e.g. a stray string) should not raise.
    assert backend_options({"backend": "not-a-dict"}) == {}


def test_make_request_normalizes_list_extra_arguments_and_images(tmp_path) -> None:
    from abyss.llm.base import make_request

    request = make_request(
        bot_name="alpha",
        bot_path=tmp_path,
        session_directory=tmp_path,
        working_directory=str(tmp_path),
        bot_config={},
        user_prompt="hi",
        extra_arguments=["--flag", "value"],
        images=[tmp_path / "a.png"],
    )
    assert isinstance(request.extra_arguments, tuple)
    assert request.extra_arguments == ("--flag", "value")
    assert isinstance(request.images, tuple)


def test_make_request_normalizes_none_to_empty_tuple(tmp_path) -> None:
    from abyss.llm.base import make_request

    request = make_request(
        bot_name="alpha",
        bot_path=tmp_path,
        session_directory=tmp_path,
        working_directory=str(tmp_path),
        bot_config={},
        user_prompt="hi",
        extra_arguments=None,
        images=None,
    )
    assert request.extra_arguments == ()
    assert request.images == ()


def test_make_request_passes_through_existing_tuple(tmp_path) -> None:
    from abyss.llm.base import make_request

    args = ("--flag",)
    request = make_request(
        bot_name="alpha",
        bot_path=tmp_path,
        session_directory=tmp_path,
        working_directory=str(tmp_path),
        bot_config={},
        user_prompt="hi",
        extra_arguments=args,
    )
    assert request.extra_arguments is args
