"""End-to-end OpenRouter evaluation — runs against the real API.

These tests are intentionally excluded from the CI test suite (the
``--ignore=tests/evaluation`` flag in ``pyproject.toml``). To run them
locally, export an OpenRouter API key and execute:

    OPENROUTER_API_KEY=sk-or-... uv run pytest tests/evaluation/test_openrouter_e2e.py
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from abyss.llm import LLMRequest
from abyss.llm.openrouter import OpenRouterBackend

pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="OPENROUTER_API_KEY not set",
)


def _request(tmp_path: Path, prompt: str, *, max_history: int = 0) -> LLMRequest:
    session_dir = tmp_path / "sessions" / "chat_eval"
    session_dir.mkdir(parents=True, exist_ok=True)
    return LLMRequest(
        bot_name="eval_bot",
        bot_path=tmp_path,
        session_directory=session_dir,
        working_directory=str(session_dir),
        bot_config={
            "backend": {
                "type": "openrouter",
                "api_key_env": "OPENROUTER_API_KEY",
                "model": "anthropic/claude-haiku-4.5",
                "max_history": max_history,
                "max_tokens": 256,
            }
        },
        user_prompt=prompt,
        max_history=max_history,
    )


@pytest.mark.asyncio
async def test_openrouter_one_shot_korean(tmp_path: Path) -> None:
    backend = OpenRouterBackend(
        {
            "backend": {
                "type": "openrouter",
                "api_key_env": "OPENROUTER_API_KEY",
                "model": "anthropic/claude-haiku-4.5",
                "max_tokens": 256,
            }
        }
    )
    try:
        result = await backend.run(_request(tmp_path, "한국어로 짧게 답해줘. 안녕!"))
    finally:
        await backend.close()

    assert result.text.strip()
    # very loose sanity check — Claude haiku should answer in Korean.
    assert any(0xAC00 <= ord(ch) <= 0xD7A3 for ch in result.text)


@pytest.mark.asyncio
async def test_openrouter_streaming_yields_chunks(tmp_path: Path) -> None:
    backend = OpenRouterBackend(
        {
            "backend": {
                "type": "openrouter",
                "api_key_env": "OPENROUTER_API_KEY",
                "model": "anthropic/claude-haiku-4.5",
                "max_tokens": 256,
            }
        }
    )
    received: list[str] = []

    async def collect(chunk: str) -> None:
        received.append(chunk)

    try:
        result = await backend.run_streaming(_request(tmp_path, "Count: one, two, three."), collect)
    finally:
        await backend.close()

    assert result.text.strip()
    # Streaming should produce more than one chunk for a multi-token reply.
    assert len(received) >= 2
    assert "".join(received) == result.text


@pytest.mark.asyncio
async def test_openrouter_replays_history(tmp_path: Path) -> None:
    backend = OpenRouterBackend(
        {
            "backend": {
                "type": "openrouter",
                "api_key_env": "OPENROUTER_API_KEY",
                "model": "anthropic/claude-haiku-4.5",
                "max_history": 4,
                "max_tokens": 256,
            }
        }
    )
    request = _request(tmp_path, "내가 좋아하는 색이 뭐였지?", max_history=4)
    log = request.session_directory / "conversation-260425.md"
    log.write_text(
        "\n## user (2026-04-25 09:30:15 UTC)\n\n내가 좋아하는 색은 보라색이야.\n"
        "\n## assistant (2026-04-25 09:30:16 UTC)\n\n알겠습니다.\n",
        encoding="utf-8",
    )
    try:
        result = await backend.run(request)
    finally:
        await backend.close()

    assert "보라" in result.text
