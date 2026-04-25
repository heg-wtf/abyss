"""Claude Code backend — wraps ``claude_runner`` and the Python Agent SDK.

This is the default backend. It preserves every behaviour the Telegram
handlers relied on prior to the LLM-backend refactor: subprocess +
``--resume`` continuity, MCP / skills / SDK pool, ``/cancel``.
"""

from __future__ import annotations

from typing import Any

from abyss.llm.base import LLMBackend, LLMRequest, LLMResult, OnChunk
from abyss.llm.registry import register


class ClaudeCodeBackend(LLMBackend):
    type = "claude_code"

    def __init__(self, bot_config: dict[str, Any]) -> None:
        self.bot_config = bot_config

    async def run(self, request: LLMRequest) -> LLMResult:
        from abyss.claude_runner import run_claude_with_sdk

        text = await run_claude_with_sdk(
            working_directory=request.working_directory,
            message=request.user_prompt,
            extra_arguments=list(request.extra_arguments) or None,
            timeout=request.timeout,
            session_key=request.session_key,
            model=self._resolve_model(),
            skill_names=self._resolve_skills() or None,
            claude_session_id=request.claude_session_id,
            resume_session=request.resume_session,
            session_directory=request.session_directory,
        )
        return LLMResult(text=text, session_id=request.claude_session_id)

    async def run_streaming(
        self,
        request: LLMRequest,
        on_chunk: OnChunk,
    ) -> LLMResult:
        from abyss.claude_runner import run_claude_streaming_with_sdk

        text = await run_claude_streaming_with_sdk(
            working_directory=request.working_directory,
            message=request.user_prompt,
            on_text_chunk=on_chunk,
            extra_arguments=list(request.extra_arguments) or None,
            timeout=request.timeout,
            session_key=request.session_key,
            model=self._resolve_model(),
            skill_names=self._resolve_skills() or None,
            claude_session_id=request.claude_session_id,
            resume_session=request.resume_session,
            session_directory=request.session_directory,
        )
        return LLMResult(text=text, session_id=request.claude_session_id)

    async def cancel(self, session_key: str) -> bool:
        from abyss.claude_runner import cancel_process, cancel_sdk_session
        from abyss.sdk_client import is_sdk_available

        cancelled = False
        if is_sdk_available():
            cancelled = await cancel_sdk_session(session_key) or cancelled
        cancelled = cancel_process(session_key) or cancelled
        return cancelled

    async def close(self) -> None:
        # Subprocess + SDK pool have process-wide lifecycle managed by
        # ``bot_manager`` (cancel_all_processes / close_pool); per-backend
        # close is a no-op.
        return None

    def supports_tools(self) -> bool:
        return True

    def supports_session_resume(self) -> bool:
        return True

    # ─── helpers ─────────────────────────────────────────────────────

    def _resolve_model(self) -> str | None:
        model = self.bot_config.get("model")
        if isinstance(model, str) and model.strip():
            return model
        return None

    def _resolve_skills(self) -> list[str]:
        skills = self.bot_config.get("skills") or []
        if not isinstance(skills, list):
            return []
        return [str(s) for s in skills if isinstance(s, str) and s]


register("claude_code", ClaudeCodeBackend)
