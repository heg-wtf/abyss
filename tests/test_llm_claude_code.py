"""Tests for the ClaudeCodeBackend wrapper."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from abyss.llm import LLMRequest, LLMResult
from abyss.llm.claude_code import ClaudeCodeBackend


def _request(tmp_path: Path, **overrides) -> LLMRequest:
    base = {
        "bot_name": "alpha",
        "bot_path": tmp_path,
        "session_directory": tmp_path / "sessions" / "chat_42",
        "working_directory": str(tmp_path / "sessions" / "chat_42"),
        "bot_config": {"model": "opus", "skills": ["weather"]},
        "user_prompt": "hello",
    }
    base.update(overrides)
    return LLMRequest(**base)


def test_supports_flags() -> None:
    backend = ClaudeCodeBackend({"backend": {"type": "claude_code"}})
    assert backend.supports_tools() is True
    assert backend.supports_session_resume() is True


@pytest.mark.asyncio
async def test_run_invokes_run_claude_with_sdk(tmp_path: Path) -> None:
    backend = ClaudeCodeBackend({"model": "opus", "skills": ["weather"]})
    request = _request(tmp_path)

    with patch(
        "abyss.claude_runner.run_claude_with_sdk",
        new_callable=AsyncMock,
        return_value="ok",
    ) as mock_runner:
        result = await backend.run(request)

    assert isinstance(result, LLMResult)
    assert result.text == "ok"
    mock_runner.assert_awaited_once()
    kwargs = mock_runner.call_args.kwargs
    assert kwargs["model"] == "opus"
    assert kwargs["skill_names"] == ["weather"]
    assert kwargs["working_directory"] == request.working_directory


@pytest.mark.asyncio
async def test_run_streaming_passes_chunk_callback(tmp_path: Path) -> None:
    backend = ClaudeCodeBackend({"model": "haiku"})
    request = _request(tmp_path, bot_config={"model": "haiku"})
    seen: list[str] = []

    async def collect(chunk: str) -> None:
        seen.append(chunk)

    async def fake_streaming(*, on_text_chunk, **_kwargs):
        await on_text_chunk("hello")
        await on_text_chunk(" world")
        return "hello world"

    with patch(
        "abyss.claude_runner.run_claude_streaming_with_sdk",
        new=fake_streaming,
    ):
        result = await backend.run_streaming(request, collect)

    assert result.text == "hello world"
    assert seen == ["hello", " world"]


@pytest.mark.asyncio
async def test_cancel_dispatches_to_runner(tmp_path: Path) -> None:
    backend = ClaudeCodeBackend({})

    with (
        patch(
            "abyss.claude_runner.cancel_sdk_session",
            new_callable=AsyncMock,
            return_value=False,
        ) as mock_sdk,
        patch(
            "abyss.claude_runner.cancel_process",
            return_value=True,
        ) as mock_proc,
        patch("abyss.sdk_client.is_sdk_available", return_value=True),
    ):
        cancelled = await backend.cancel("alpha:42")

    assert cancelled is True
    mock_sdk.assert_awaited_once_with("alpha:42")
    mock_proc.assert_called_once_with("alpha:42")


@pytest.mark.asyncio
async def test_cancel_skips_sdk_when_unavailable(tmp_path: Path) -> None:
    backend = ClaudeCodeBackend({})

    with (
        patch("abyss.claude_runner.cancel_sdk_session", new_callable=AsyncMock) as mock_sdk,
        patch("abyss.claude_runner.cancel_process", return_value=False),
        patch("abyss.sdk_client.is_sdk_available", return_value=False),
    ):
        cancelled = await backend.cancel("alpha:42")

    assert cancelled is False
    mock_sdk.assert_not_called()


def test_resolve_model_defaults_when_blank() -> None:
    backend = ClaudeCodeBackend({"model": "  "})
    assert backend._resolve_model() is None


def test_resolve_skills_filters_invalid() -> None:
    backend = ClaudeCodeBackend({"skills": ["weather", "", 123, "qmd"]})
    assert backend._resolve_skills() == ["weather", "qmd"]
