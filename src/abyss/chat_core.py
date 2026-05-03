"""Backend-agnostic chat orchestration shared by Telegram handlers and the
dashboard web chat server.

Provides session bootstrap, conversation logging, LLM backend invocation, and
``--resume`` fallback. Knows nothing about Telegram or HTTP — callers supply an
``on_chunk`` callback to receive streaming text.

The Telegram path in ``handlers.py`` keeps its own nested helpers for now; the
two implementations stay in sync intentionally (small, well-tested logic).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from abyss.llm import get_or_create
from abyss.llm.base import make_request
from abyss.session import (
    clear_claude_session_id,
    ensure_session,
    get_claude_session_id,
    load_bot_memory,
    load_conversation_history,
    load_global_memory,
    log_conversation,
    save_claude_session_id,
)

logger = logging.getLogger(__name__)

OnChunk = Callable[[str], Awaitable[None]]


def _build_bootstrap_prompt(bot_path: Path, session_dir: Path, user_message: str) -> str:
    """Compose the bootstrap prompt for a new (or fallback) Claude session."""
    parts: list[str] = []

    global_memory = load_global_memory()
    if global_memory:
        parts.append("아래는 글로벌 메모리입니다. 참고하세요 (수정 불가):\n\n" + global_memory)

    bot_memory = load_bot_memory(bot_path)
    if bot_memory:
        parts.append("아래는 장기 메모리입니다. 참고하세요:\n\n" + bot_memory)

    history = load_conversation_history(session_dir)
    if history:
        parts.append("아래는 이전 대화 기록입니다. 맥락으로 활용하세요:\n\n" + history)

    if not parts:
        return user_message
    return "\n\n---\n\n".join(parts) + f"\n\n---\n\n새 메시지: {user_message}"


def prepare_session_context(
    bot_path: Path, session_dir: Path, user_message: str
) -> tuple[str, str, bool]:
    """Return ``(prompt, claude_session_id, resume_session)`` for this turn.

    Mirrors ``handlers._prepare_session_context``. On a fresh session, prepends
    global + bot memory + conversation history to the user message and writes a
    new ``.claude_session_id``. On a resumed session, returns the raw user
    message and the existing session id with ``resume_session=True``.
    """
    claude_session_id = get_claude_session_id(session_dir)
    if claude_session_id:
        return user_message, claude_session_id, True

    new_session_id = str(uuid.uuid4())
    prompt = _build_bootstrap_prompt(bot_path, session_dir, user_message)
    save_claude_session_id(session_dir, new_session_id)
    return prompt, new_session_id, False


async def _run_with_resume_fallback(
    *,
    bot_name: str,
    bot_path: Path,
    bot_config: dict[str, Any],
    session_dir: Path,
    user_message: str,
    prompt: str,
    claude_session_id: str,
    resume_session: bool,
    session_key: str,
    on_chunk: OnChunk | None,
    timeout: int,
) -> str:
    """Run the backend once, retrying with bootstrap if --resume fails."""
    backend = get_or_create(bot_name, bot_config)

    async def _invoke(prompt_value: str, sid: str, resume: bool) -> str:
        request = make_request(
            bot_name=bot_name,
            bot_path=bot_path,
            session_directory=session_dir,
            working_directory=str(session_dir),
            bot_config=bot_config,
            user_prompt=prompt_value,
            session_key=session_key,
            claude_session_id=sid,
            resume_session=resume,
            timeout=timeout,
        )
        if on_chunk is not None:
            result = await backend.run_streaming(request, on_chunk)
        else:
            result = await backend.run(request)
        if result.session_id:
            save_claude_session_id(session_dir, result.session_id)
        return result.text or ""

    try:
        return await _invoke(prompt, claude_session_id, resume_session)
    except RuntimeError as error:
        if not resume_session:
            raise
        logger.warning(
            "Resume failed for session %s (bot=%s): %s. Falling back to bootstrap.",
            claude_session_id,
            bot_name,
            error,
        )
        clear_claude_session_id(session_dir)

        # Close stale SDK pool session so a fresh client is created.
        try:
            from abyss.sdk_client import get_pool, is_sdk_available

            if is_sdk_available():
                pool = get_pool()
                await pool.close_session(session_key)
        except Exception:  # noqa: BLE001 — pool cleanup is best-effort
            logger.debug("SDK pool cleanup failed", exc_info=True)

        new_session_id = str(uuid.uuid4())
        save_claude_session_id(session_dir, new_session_id)
        fallback_prompt = _build_bootstrap_prompt(bot_path, session_dir, user_message)
        return await _invoke(fallback_prompt, new_session_id, False)


async def process_chat_message(
    *,
    bot_name: str,
    bot_path: Path,
    bot_config: dict[str, Any],
    chat_id: int | str,
    user_message: str,
    on_chunk: OnChunk | None = None,
    session_key: str | None = None,
    timeout: int = 600,
) -> str:
    """End-to-end chat turn used by non-Telegram callers (dashboard chat).

    Steps:
      1. ``ensure_session`` to materialize the session directory + CLAUDE.md
      2. Append the user message to the conversation log
      3. Bootstrap or resume the Claude session
      4. Call ``LLMBackend.run_streaming`` (or ``run``) with optional ``on_chunk``
      5. Append the assistant response to the conversation log
      6. Return the full assistant text
    """
    session_dir = ensure_session(bot_path, chat_id, bot_name=bot_name)

    log_conversation(session_dir, "user", user_message)

    prompt, claude_session_id, resume_session = prepare_session_context(
        bot_path, session_dir, user_message
    )

    effective_key = session_key or f"{bot_name}:{chat_id}"

    try:
        full_text = await _run_with_resume_fallback(
            bot_name=bot_name,
            bot_path=bot_path,
            bot_config=bot_config,
            session_dir=session_dir,
            user_message=user_message,
            prompt=prompt,
            claude_session_id=claude_session_id,
            resume_session=resume_session,
            session_key=effective_key,
            on_chunk=on_chunk,
            timeout=timeout,
        )
    except Exception as error:
        logger.error("chat_core: backend failure for %s/%s: %s", bot_name, chat_id, error)
        full_text = f"Error: {error}"

    log_conversation(session_dir, "assistant", full_text)
    return full_text
