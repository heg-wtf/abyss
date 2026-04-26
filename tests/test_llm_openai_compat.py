"""Tests for OpenAICompatBackend and PROVIDER_PRESETS."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from abyss.llm.openai_compat import (
    PROVIDER_PRESETS,
    OpenAICompatBackend,
)
from abyss.llm.openrouter import OpenRouterBackend


def _bot_config(backend_overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    block: dict[str, Any] = {"type": "openai_compat"}
    if backend_overrides:
        block.update(backend_overrides)
    return {"backend": block}


# ─── PROVIDER_PRESETS ─────────────────────────────────────────────────────


def test_provider_presets_contain_expected_keys() -> None:
    for name in ("openrouter", "minimax", "minimax_china"):
        assert name in PROVIDER_PRESETS
        assert "base_url" in PROVIDER_PRESETS[name]
        assert "api_key_env" in PROVIDER_PRESETS[name]


def test_minimax_international_endpoint() -> None:
    assert PROVIDER_PRESETS["minimax"]["base_url"] == "https://api.minimaxi.chat/v1"
    assert PROVIDER_PRESETS["minimax"]["api_key_env"] == "MINIMAX_API_KEY"


def test_minimax_china_endpoint() -> None:
    assert PROVIDER_PRESETS["minimax_china"]["base_url"] == "https://api.minimax.chat/v1"
    assert PROVIDER_PRESETS["minimax_china"]["api_key_env"] == "MINIMAX_API_KEY"


def test_openrouter_preset_endpoint() -> None:
    assert PROVIDER_PRESETS["openrouter"]["base_url"] == "https://openrouter.ai/api/v1"
    assert PROVIDER_PRESETS["openrouter"]["api_key_env"] == "OPENROUTER_API_KEY"


# ─── provider preset resolution ───────────────────────────────────────────


def test_provider_minimax_sets_base_url_and_api_key_env() -> None:
    backend = OpenAICompatBackend(_bot_config({"provider": "minimax", "model": "minimax-text-01"}))
    assert backend.base_url == "https://api.minimaxi.chat/v1"
    assert backend.api_key_env == "MINIMAX_API_KEY"
    assert backend.model == "minimax-text-01"


def test_provider_minimax_china_sets_china_endpoint() -> None:
    backend = OpenAICompatBackend(
        _bot_config({"provider": "minimax_china", "model": "minimax-text-01"})
    )
    assert backend.base_url == "https://api.minimax.chat/v1"
    assert backend.api_key_env == "MINIMAX_API_KEY"


def test_provider_openrouter_via_openai_compat_type() -> None:
    backend = OpenAICompatBackend(_bot_config({"provider": "openrouter"}))
    assert backend.base_url == "https://openrouter.ai/api/v1"
    assert backend.api_key_env == "OPENROUTER_API_KEY"


def test_explicit_base_url_overrides_preset() -> None:
    backend = OpenAICompatBackend(
        _bot_config(
            {
                "provider": "minimax",
                "base_url": "https://custom.example.com/v1",
            }
        )
    )
    assert backend.base_url == "https://custom.example.com/v1"


def test_explicit_api_key_env_overrides_preset() -> None:
    backend = OpenAICompatBackend(
        _bot_config({"provider": "minimax", "api_key_env": "MY_CUSTOM_KEY"})
    )
    assert backend.api_key_env == "MY_CUSTOM_KEY"


def test_unknown_provider_falls_back_to_generic_defaults() -> None:
    backend = OpenAICompatBackend(_bot_config({"provider": "nonexistent"}))
    assert backend.api_key_env == "OPENAI_API_KEY"
    assert backend.base_url == ""


def test_no_provider_falls_back_to_generic_defaults() -> None:
    backend = OpenAICompatBackend(_bot_config())
    assert backend.api_key_env == "OPENAI_API_KEY"
    assert backend.base_url == ""


# ─── OpenRouterBackend stub backward compat ───────────────────────────────


def test_openrouter_backend_is_subclass_of_openai_compat() -> None:
    assert issubclass(OpenRouterBackend, OpenAICompatBackend)


def test_openrouter_backend_type_is_openrouter() -> None:
    assert OpenRouterBackend.type == "openrouter"


def test_openrouter_backend_defaults_use_openrouter_preset() -> None:
    backend = OpenRouterBackend({"backend": {"type": "openrouter"}})
    assert backend.base_url == "https://openrouter.ai/api/v1"
    assert backend.api_key_env == "OPENROUTER_API_KEY"


def test_openrouter_backend_provider_label() -> None:
    assert OpenRouterBackend._provider_label == "OpenRouter"


# ─── registry ─────────────────────────────────────────────────────────────


def test_openai_compat_registered() -> None:
    from abyss.llm import registered_backend_types

    assert "openai_compat" in registered_backend_types()


def test_openrouter_still_registered_as_alias() -> None:
    from abyss.llm import registered_backend_types

    assert "openrouter" in registered_backend_types()


def test_get_backend_openai_compat_returns_correct_type() -> None:
    from abyss.llm import get_backend

    backend = get_backend(
        {"backend": {"type": "openai_compat", "provider": "minimax", "model": "minimax-text-01"}}
    )
    assert isinstance(backend, OpenAICompatBackend)
    assert backend.type == "openai_compat"


def test_get_backend_openrouter_returns_openrouter_subclass() -> None:
    from abyss.llm import get_backend

    backend = get_backend({"backend": {"type": "openrouter"}})
    assert isinstance(backend, OpenRouterBackend)
    assert backend.type == "openrouter"


# ─── auth error uses provider label ───────────────────────────────────────


def test_auth_error_uses_generic_label_for_openai_compat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    backend = OpenAICompatBackend(_bot_config())
    with pytest.raises(RuntimeError, match="OpenAI-compatible backend"):
        backend._auth_headers()


def test_auth_error_uses_openrouter_label_for_openrouter_subclass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    backend = OpenRouterBackend({"backend": {"type": "openrouter"}})
    with pytest.raises(RuntimeError, match="OpenRouter"):
        backend._auth_headers()


# ─── flags ─────────────────────────────────────────────────────────────────


def test_openai_compat_does_not_support_tools_or_resume() -> None:
    backend = OpenAICompatBackend(_bot_config({"provider": "minimax"}))
    assert backend.supports_tools() is False
    assert backend.supports_session_resume() is False


# ─── close ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_close_calls_aclose() -> None:
    backend = OpenAICompatBackend(_bot_config({"provider": "minimax"}))
    backend._client = MagicMock()
    backend._client.aclose = AsyncMock()
    await backend.close()
    backend._client.aclose.assert_awaited_once()
