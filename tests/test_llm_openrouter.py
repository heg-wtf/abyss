"""Tests for the OpenRouterBackend (text-only chat adapter)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from abyss.llm import LLMRequest
from abyss.llm.openrouter import OpenRouterBackend


def _bot_config(**overrides: Any) -> dict[str, Any]:
    backend_block = {
        "type": "openrouter",
        "api_key_env": "OPENROUTER_TEST_KEY",
        "model": "anthropic/claude-haiku-4.5",
        "max_history": 5,
        "max_tokens": 2048,
    }
    backend_block.update(overrides.pop("backend", {}))
    config: dict[str, Any] = {"backend": backend_block}
    config.update(overrides)
    return config


def _request(tmp_path: Path, **overrides: Any) -> LLMRequest:
    session_dir = tmp_path / "sessions" / "chat_1"
    session_dir.mkdir(parents=True, exist_ok=True)
    base = {
        "bot_name": "alpha",
        "bot_path": tmp_path,
        "session_directory": session_dir,
        "working_directory": str(session_dir),
        "bot_config": _bot_config(),
        "user_prompt": "Hello",
        "max_history": 5,
    }
    base.update(overrides)
    return LLMRequest(**base)


def _post_response(
    payload: dict[str, Any] | None = None,
    *,
    status: int = 200,
    text: str | None = None,
) -> httpx.Response:
    """Build a fake httpx.Response with a request attached."""
    if text is not None:
        response = httpx.Response(status, text=text)
    else:
        response = httpx.Response(status, json=payload or {})
    response._request = httpx.Request(  # noqa: SLF001 - test plumbing
        "POST", "https://openrouter.ai/api/v1/chat/completions"
    )
    return response


@pytest.fixture
def env_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_TEST_KEY", "fake-key")


# ─── auth + headers ───────────────────────────────────────────────────────


def test_auth_headers_missing_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_TEST_KEY", raising=False)
    backend = OpenRouterBackend(_bot_config())
    with pytest.raises(RuntimeError, match="OPENROUTER_TEST_KEY"):
        backend._auth_headers()


def test_auth_headers_includes_attribution(env_api_key: None) -> None:
    backend = OpenRouterBackend(_bot_config())
    headers = backend._auth_headers()
    assert headers["Authorization"] == "Bearer fake-key"
    assert headers["X-Title"] == "abyss"
    assert headers["HTTP-Referer"].startswith("https://")


# ─── flags ─────────────────────────────────────────────────────────────────


def test_does_not_support_tools_or_resume() -> None:
    backend = OpenRouterBackend(_bot_config())
    assert backend.supports_tools() is False
    assert backend.supports_session_resume() is False


# ─── message building ──────────────────────────────────────────────────────


def test_build_messages_inserts_system_prompt(tmp_path: Path, env_api_key: None) -> None:
    request = _request(tmp_path)
    (request.bot_path / "CLAUDE.md").write_text("System prompt body")
    backend = OpenRouterBackend(_bot_config())

    messages = backend._build_messages(request)
    assert messages[0]["role"] == "system"
    assert "System prompt body" in messages[0]["content"]
    assert messages[-1] == {"role": "user", "content": "Hello"}


def test_build_messages_replays_history(tmp_path: Path, env_api_key: None) -> None:
    request = _request(tmp_path)
    (request.bot_path / "CLAUDE.md").write_text("system")
    log = request.session_directory / "conversation-260425.md"
    log.write_text(
        "\n## user (2026-04-25 09:30:15 UTC)\n\n첫 번째 메시지\n"
        "\n## assistant (2026-04-25 09:30:16 UTC)\n\n네 알겠습니다\n"
        "\n## user (2026-04-25 09:31:00 UTC)\n\n두 번째 메시지\n",
        encoding="utf-8",
    )
    backend = OpenRouterBackend(_bot_config())

    messages = backend._build_messages(request)
    # system + 3 historical + 1 current user
    assert len(messages) == 5
    assert messages[1]["role"] == "user"
    assert "첫 번째" in messages[1]["content"]
    assert messages[3]["role"] == "user"
    assert "두 번째" in messages[3]["content"]


def test_build_messages_caps_history_at_max(tmp_path: Path, env_api_key: None) -> None:
    backend = OpenRouterBackend(_bot_config(backend={"max_history": 2}))
    request = _request(tmp_path, max_history=2)
    log = request.session_directory / "conversation-260425.md"
    log.write_text(
        "\n## user (2026-04-25 09:30:15 UTC)\n\nfirst\n"
        "\n## assistant (2026-04-25 09:30:16 UTC)\n\nfirst-reply\n"
        "\n## user (2026-04-25 09:31:00 UTC)\n\nsecond\n"
        "\n## assistant (2026-04-25 09:31:01 UTC)\n\nsecond-reply\n",
        encoding="utf-8",
    )

    messages = backend._build_messages(request)
    history = [m for m in messages if m["role"] in ("user", "assistant")]
    # current user prompt + last 2 history = 3 total user/assistant entries
    assert len(history) == 3
    assert "first" not in history[0]["content"]


# ─── run / streaming via httpx mock ───────────────────────────────────────


@pytest.mark.asyncio
async def test_run_returns_text_and_usage(tmp_path: Path, env_api_key: None) -> None:
    backend = OpenRouterBackend(_bot_config())
    request = _request(tmp_path)

    fake_response = _post_response(
        {
            "choices": [
                {
                    "message": {"content": "안녕하세요"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 12, "completion_tokens": 5},
        }
    )

    async def fake_post(self, *args, **kwargs):
        return fake_response

    with patch.object(httpx.AsyncClient, "post", new=fake_post):
        result = await backend.run(request)

    assert result.text == "안녕하세요"
    assert result.input_tokens == 12
    assert result.output_tokens == 5
    assert result.stop_reason == "stop"


@pytest.mark.asyncio
async def test_run_streaming_dispatches_chunks(tmp_path: Path, env_api_key: None) -> None:
    backend = OpenRouterBackend(_bot_config())
    request = _request(tmp_path)
    received: list[str] = []

    async def on_chunk(chunk: str) -> None:
        received.append(chunk)

    chunk1 = {"choices": [{"delta": {"content": "안녕"}}]}
    chunk2 = {"choices": [{"delta": {"content": "하세요"}}]}
    final_chunk = {
        "choices": [{"delta": {}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 9, "completion_tokens": 4},
    }
    sse_lines = [
        f"data: {json.dumps(chunk1)}",
        "",
        f"data: {json.dumps(chunk2)}",
        "",
        f"data: {json.dumps(final_chunk)}",
        "",
        "data: [DONE]",
    ]

    class _StreamCM:
        async def __aenter__(self_inner):
            self_inner.response = MagicMock(spec=httpx.Response)
            self_inner.response.status_code = 200
            self_inner.response.raise_for_status = MagicMock()

            async def aiter_lines():
                for line in sse_lines:
                    yield line

            self_inner.response.aiter_lines = aiter_lines
            return self_inner.response

        async def __aexit__(self_inner, *args):
            return None

    def fake_stream(self, method, url, **kwargs):
        return _StreamCM()

    with patch.object(httpx.AsyncClient, "stream", new=fake_stream):
        result = await backend.run_streaming(request, on_chunk)

    assert received == ["안녕", "하세요"]
    assert result.text == "안녕하세요"
    assert result.input_tokens == 9
    assert result.output_tokens == 4
    assert result.stop_reason == "stop"


@pytest.mark.asyncio
async def test_run_raises_on_4xx_with_clear_message(tmp_path: Path, env_api_key: None) -> None:
    backend = OpenRouterBackend(_bot_config())
    request = _request(tmp_path)

    fake_response = _post_response({"error": "invalid"}, status=401)

    async def fake_post(self, *args, **kwargs):
        return fake_response

    with patch.object(httpx.AsyncClient, "post", new=fake_post):
        with pytest.raises(RuntimeError, match="OpenRouter rejected the API key"):
            await backend.run(request)


@pytest.mark.asyncio
async def test_run_raises_on_429(tmp_path: Path, env_api_key: None) -> None:
    backend = OpenRouterBackend(_bot_config())
    request = _request(tmp_path)

    fake_response = _post_response(status=429, text="Too many")

    async def fake_post(self, *args, **kwargs):
        return fake_response

    with patch.object(httpx.AsyncClient, "post", new=fake_post):
        with pytest.raises(RuntimeError, match="rate limit"):
            await backend.run(request)


@pytest.mark.asyncio
async def test_run_raises_on_5xx(tmp_path: Path, env_api_key: None) -> None:
    backend = OpenRouterBackend(_bot_config())
    request = _request(tmp_path)

    fake_response = _post_response(status=502, text="upstream down")

    async def fake_post(self, *args, **kwargs):
        return fake_response

    with patch.object(httpx.AsyncClient, "post", new=fake_post):
        with pytest.raises(RuntimeError, match="upstream error"):
            await backend.run(request)


# ─── cancel ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cancel_pending_task(tmp_path: Path, env_api_key: None) -> None:
    backend = OpenRouterBackend(_bot_config())

    async def long_running() -> None:
        await asyncio.sleep(5)

    task = asyncio.create_task(long_running())
    backend._tasks["alpha:42"] = task
    cancelled = await backend.cancel("alpha:42")
    await asyncio.sleep(0)
    assert cancelled is True
    assert task.cancelled()
    backend._tasks.pop("alpha:42", None)


@pytest.mark.asyncio
async def test_cancel_unknown_session_returns_false(tmp_path: Path, env_api_key: None) -> None:
    backend = OpenRouterBackend(_bot_config())
    assert await backend.cancel("missing") is False


# ─── close ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_close_calls_aclose(env_api_key: None) -> None:
    backend = OpenRouterBackend(_bot_config())
    backend._client = MagicMock()
    backend._client.aclose = AsyncMock()
    await backend.close()
    backend._client.aclose.assert_awaited_once()


# ─── option resolution ────────────────────────────────────────────────────


def test_options_default_to_documented_values() -> None:
    backend = OpenRouterBackend({"backend": {"type": "openrouter"}})
    assert backend.api_key_env == "OPENROUTER_API_KEY"
    assert backend.model == "anthropic/claude-haiku-4.5"
    assert backend.max_history == 20
    assert backend.max_tokens == 4096
    assert backend.base_url == "https://openrouter.ai/api/v1"


def test_base_url_trailing_slash_stripped() -> None:
    backend = OpenRouterBackend(
        {"backend": {"type": "openrouter", "base_url": "https://example.com/v1/"}}
    )
    assert backend.base_url == "https://example.com/v1"


# ─── regression: PR #8 review (Codex P1 + P2) ─────────────────────────────


def test_build_messages_dedupes_trailing_user_match(tmp_path: Path, env_api_key: None) -> None:
    """The current user turn must not appear twice when it's already the
    last entry in the markdown log (the abyss handler logs user input
    *before* calling backend.run). Regression for Codex P1 on PR #8.
    """
    backend = OpenRouterBackend(_bot_config())
    request = _request(tmp_path, user_prompt="오늘 점심 뭐 먹지")
    log = request.session_directory / "conversation-260425.md"
    log.write_text(
        "\n## user (2026-04-25 09:30:00 UTC)\n\n어제 저녁\n"
        "\n## assistant (2026-04-25 09:30:01 UTC)\n\n뭐였나요?\n"
        # The handler logs the current user message before backend.run:
        "\n## user (2026-04-25 09:31:00 UTC)\n\n오늘 점심 뭐 먹지\n",
        encoding="utf-8",
    )

    messages = backend._build_messages(request)
    user_turns = [m for m in messages if m["role"] == "user"]
    matching = [m for m in user_turns if m["content"] == "오늘 점심 뭐 먹지"]
    assert len(matching) == 1, (
        f"current user prompt should appear once, got {len(matching)}: {matching}"
    )
    # Older user turn survives.
    assert any(m["content"] == "어제 저녁" for m in user_turns)
    assert any(m["role"] == "assistant" for m in messages)


def test_build_messages_dedupes_only_when_content_matches(
    tmp_path: Path, env_api_key: None
) -> None:
    """A trailing user turn whose text differs from request.user_prompt
    must NOT be dropped — that would lose context.
    """
    backend = OpenRouterBackend(_bot_config())
    request = _request(tmp_path, user_prompt="새로운 질문")
    log = request.session_directory / "conversation-260425.md"
    log.write_text(
        "\n## user (2026-04-25 09:31:00 UTC)\n\n이전 질문\n",
        encoding="utf-8",
    )

    messages = backend._build_messages(request)
    user_turns = [m for m in messages if m["role"] == "user"]
    assert [m["content"] for m in user_turns] == ["이전 질문", "새로운 질문"]


def test_build_messages_respects_backend_max_history(tmp_path: Path, env_api_key: None) -> None:
    """``backend.max_history`` from bot.yaml must take effect. Regression
    for Codex P2 on PR #8 — previously the dataclass default of 20 was
    used regardless of the configured cap.
    """
    backend = OpenRouterBackend(_bot_config(backend={"max_history": 2}))
    # Use the dataclass default for request.max_history (callers don't set it).
    request = _request(tmp_path, user_prompt="현재 메시지")
    # The fixture sets max_history=5 explicitly; reset to dataclass
    # default so we exercise the precedence path that falls back to
    # ``backend.max_history``.
    object.__setattr__(request, "max_history", 20)

    log = request.session_directory / "conversation-260425.md"
    log.write_text(
        "\n## user (2026-04-25 09:30:00 UTC)\n\nmsg-1\n"
        "\n## assistant (2026-04-25 09:30:01 UTC)\n\nreply-1\n"
        "\n## user (2026-04-25 09:30:02 UTC)\n\nmsg-2\n"
        "\n## assistant (2026-04-25 09:30:03 UTC)\n\nreply-2\n"
        "\n## user (2026-04-25 09:30:04 UTC)\n\nmsg-3\n"
        "\n## assistant (2026-04-25 09:30:05 UTC)\n\nreply-3\n",
        encoding="utf-8",
    )

    messages = backend._build_messages(request)
    history = [m for m in messages if m["role"] in ("user", "assistant")]
    # cap=2 history + 1 current user = 3 user/assistant entries total.
    assert len(history) == 3, history
    contents = [m["content"] for m in history]
    assert contents[-1] == "현재 메시지"
    assert contents[-2] == "reply-3"
    assert contents[-3] == "msg-3"


def test_build_messages_request_override_wins_over_backend_cap(
    tmp_path: Path, env_api_key: None
) -> None:
    """A caller that explicitly raises ``request.max_history`` above the
    dataclass default of 20 wins over the bot-configured cap so one-off
    callers (cron, heartbeat) can widen the window for their own runs.
    """
    backend = OpenRouterBackend(_bot_config(backend={"max_history": 2}))
    request = _request(tmp_path, user_prompt="now", max_history=10)
    log = request.session_directory / "conversation-260425.md"
    log.write_text(
        "".join(
            f"\n## user (2026-04-25 09:30:{index:02d} UTC)\n\nmsg-{index}\n" for index in range(8)
        ),
        encoding="utf-8",
    )

    # max_history=10 means we keep up to 10 history items; we only have
    # 8 in the log so all of them survive plus the current message.
    messages = backend._build_messages(request)
    user_turns = [m for m in messages if m["role"] == "user"]
    assert len(user_turns) == 9
