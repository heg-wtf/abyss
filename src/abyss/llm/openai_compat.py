"""OpenAI-compatible chat completions backend.

Supports any provider that exposes an OpenAI-compatible ``/v1/chat/completions``
endpoint. Use ``PROVIDER_PRESETS`` for named providers (openrouter, minimax,
minimax_china) or supply ``base_url`` / ``api_key_env`` directly in bot.yaml.

This backend deliberately covers only the *chat* surface:

* No tool calls (skills attached to a bot show up in the system prompt
  but the model cannot invoke them; tool-shaped requests fail loudly
  via :class:`abyss.llm.base.ToolUnavailableError`).
* No subagent spawning.
* No ``--resume``-style session continuity. The backend instead replays
  the last ``max_history`` turns from the bot's ``conversation-YYMMDD.md``
  files (and the bot's ``CLAUDE.md`` as the system prompt) so the model
  has working context.
* No file-write / shell tools — Claude Code's built-ins are unavailable.

bot.yaml examples
-----------------
MiniMax (international)::

    backend:
      type: openai_compat
      provider: minimax
      model: minimax-text-01

OpenRouter (named preset)::

    backend:
      type: openai_compat
      provider: openrouter
      model: anthropic/claude-haiku-4.5

Custom provider::

    backend:
      type: openai_compat
      base_url: https://api.example.com/v1
      api_key_env: MY_API_KEY
      model: my-model
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, ClassVar

import httpx

from abyss.llm.base import (
    LLMBackend,
    LLMRequest,
    LLMResult,
    OnChunk,
    backend_options,
)
from abyss.llm.registry import register

logger = logging.getLogger(__name__)

PROVIDER_PRESETS: dict[str, dict[str, str]] = {
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
    },
    "minimax": {
        "base_url": "https://api.minimaxi.chat/v1",
        "api_key_env": "MINIMAX_API_KEY",
    },
    "minimax_china": {
        "base_url": "https://api.minimax.chat/v1",
        "api_key_env": "MINIMAX_API_KEY",
    },
}

DEFAULT_MODEL = "anthropic/claude-haiku-4.5"
DEFAULT_MAX_TOKENS = 4096
DEFAULT_MAX_HISTORY = 20
DEFAULT_TIMEOUT_READ = 120.0
DEFAULT_TIMEOUT_CONNECT = 10.0

# Conversation header pattern — keep in sync with
# ``conversation_index.SESSION_HEADER_RE``.
_CONVERSATION_HEADER_RE = re.compile(
    r"^##\s+(?P<role>user|assistant)\s+\((?P<ts>[^)]+)\)\s*$",
    re.MULTILINE,
)


class OpenAICompatBackend(LLMBackend):
    """Backend for any OpenAI-compatible chat completions endpoint.

    Provider defaults are resolved in this order:
    1. Explicit ``base_url`` / ``api_key_env`` in bot.yaml backend block
    2. Named ``provider`` preset from :data:`PROVIDER_PRESETS`
    3. Subclass ``_default_provider`` (used by ``OpenRouterBackend`` stub)
    """

    type: ClassVar[str] = "openai_compat"
    _default_provider: ClassVar[str | None] = None
    _provider_label: ClassVar[str] = "OpenAI-compatible backend"

    def __init__(self, bot_config: dict[str, Any]) -> None:
        self.bot_config = bot_config
        options = backend_options(bot_config)

        provider = options.get("provider") or self._default_provider
        preset = PROVIDER_PRESETS.get(provider or "", {})

        self.api_key_env: str = (
            options.get("api_key_env") or preset.get("api_key_env") or "OPENAI_API_KEY"
        )
        self.model: str = options.get("model", DEFAULT_MODEL)
        self.base_url: str = (options.get("base_url") or preset.get("base_url") or "").rstrip("/")
        self.max_history: int = int(options.get("max_history", DEFAULT_MAX_HISTORY))
        self.max_tokens: int = int(options.get("max_tokens", DEFAULT_MAX_TOKENS))

        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=DEFAULT_TIMEOUT_CONNECT,
                read=DEFAULT_TIMEOUT_READ,
                write=DEFAULT_TIMEOUT_CONNECT,
                pool=DEFAULT_TIMEOUT_CONNECT,
            )
        )
        self._tasks: dict[str, asyncio.Task] = {}

    # ─── public API ───────────────────────────────────────────────────

    async def run(self, request: LLMRequest) -> LLMResult:
        payload = self._build_payload(request, stream=False)
        headers = self._auth_headers()

        async def _do() -> httpx.Response:
            return await self._client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
            )

        response = await self._track(request.session_key, _do())
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise self._wrap_status_error(exc) from exc

        data = response.json()
        choice = data["choices"][0]
        text = choice["message"].get("content") or ""
        usage = data.get("usage") or {}
        return LLMResult(
            text=text,
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            stop_reason=choice.get("finish_reason"),
            raw=data,
        )

    async def run_streaming(self, request: LLMRequest, on_chunk: OnChunk) -> LLMResult:
        payload = self._build_payload(request, stream=True)
        headers = self._auth_headers()

        accumulated: list[str] = []
        finish_reason: str | None = None
        usage: dict[str, Any] = {}

        async def _do() -> None:
            nonlocal finish_reason, usage
            async with self._client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
            ) as response:
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    body = (await response.aread()).decode("utf-8", errors="replace")
                    raise self._wrap_status_error(exc, body=body) from exc

                async for line in response.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if not data_str or data_str == "[DONE]":
                        if data_str == "[DONE]":
                            break
                        continue
                    try:
                        event = json.loads(data_str)
                    except json.JSONDecodeError:
                        logger.warning("invalid SSE chunk: %s", data_str[:200])
                        continue
                    choices = event.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    content = delta.get("content")
                    if content:
                        accumulated.append(content)
                        await on_chunk(content)
                    finish = choices[0].get("finish_reason")
                    if finish:
                        finish_reason = finish
                    if "usage" in event and isinstance(event["usage"], dict):
                        usage = event["usage"]

        await self._track(request.session_key, _do())

        return LLMResult(
            text="".join(accumulated),
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            stop_reason=finish_reason,
        )

    async def cancel(self, session_key: str) -> bool:
        task = self._tasks.get(session_key)
        if task is None or task.done():
            return False
        task.cancel()
        return True

    async def close(self) -> None:
        await self._client.aclose()

    def supports_tools(self) -> bool:
        return False

    def supports_session_resume(self) -> bool:
        return False

    # ─── helpers ──────────────────────────────────────────────────────

    async def _track(self, session_key: str | None, coro: Any) -> Any:
        if session_key is None:
            return await coro
        task = asyncio.create_task(coro)
        self._tasks[session_key] = task
        try:
            return await task
        finally:
            self._tasks.pop(session_key, None)

    def _auth_headers(self) -> dict[str, str]:
        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            raise RuntimeError(
                f"{self._provider_label} requires environment variable "
                f"{self.api_key_env!r} to be set."
            )
        return {
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "https://abyss.heg.wtf",
            "X-Title": "abyss",
        }

    def _build_payload(self, request: LLMRequest, *, stream: bool) -> dict[str, Any]:
        messages = self._build_messages(request)
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
        }
        if stream:
            payload["stream"] = True
            payload["stream_options"] = {"include_usage": True}
        return payload

    def _build_messages(self, request: LLMRequest) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []

        system_prompt = self._load_system_prompt(request)
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        history = self._load_history(request)
        # abyss's Telegram handlers call ``log_conversation`` *before*
        # ``backend.run``, so the markdown log already contains the
        # current user message. Drop any matching trailing user turn so
        # the model doesn't see the same input twice (which inflates
        # token usage and biases responses toward the repeated text).
        current = request.user_prompt.strip()
        while (
            history and history[-1]["role"] == "user" and history[-1]["content"].strip() == current
        ):
            history.pop()

        cap = self._resolve_max_history(request)
        if cap > 0 and len(history) > cap:
            history = history[-cap:]

        messages.extend(history)
        messages.append({"role": "user", "content": request.user_prompt})
        return messages

    def _load_system_prompt(self, request: LLMRequest) -> str:
        candidates = (
            request.session_directory / "CLAUDE.md",
            request.bot_path / "CLAUDE.md",
        )
        for path in candidates:
            try:
                if path.exists():
                    text = path.read_text(encoding="utf-8")
                    if text.strip():
                        return text
            except OSError as exc:  # noqa: PERF203
                logger.warning("could not read system prompt %s: %s", path, exc)
        return ""

    def _resolve_max_history(self, request: LLMRequest) -> int:
        """Return the active history cap for this turn.

        Precedence: explicit override on ``request.max_history`` (when
        the caller raises it above the dataclass default of 20) wins,
        otherwise the bot-configured ``backend.max_history`` is used.
        """
        request_value = request.max_history
        # 20 is the dataclass default — treat it as "unset" so the
        # backend config takes effect for bots that lower the cap.
        if request_value > 0 and request_value != 20:
            return request_value
        return max(0, self.max_history)

    def _load_history(self, request: LLMRequest) -> list[dict[str, str]]:
        """Replay the last ``max_history`` user/assistant turns from disk.

        Loads one extra entry beyond the cap so ``_build_messages`` can
        drop a duplicate trailing user turn without dipping below the
        configured window size. The final cap is enforced by the
        caller after dedup.
        """
        cap = self._resolve_max_history(request)
        if cap <= 0:
            return []
        files = sorted(
            request.session_directory.glob("conversation-[0-9][0-9][0-9][0-9][0-9][0-9].md")
        )
        if not files:
            return []
        target = cap + 1
        turns: list[dict[str, str]] = []
        for md_file in reversed(files):
            for entry in reversed(list(_iter_messages(md_file))):
                turns.append(entry)
                if len(turns) >= target:
                    break
            if len(turns) >= target:
                break
        turns.reverse()
        return turns

    def _wrap_status_error(
        self, exc: httpx.HTTPStatusError, *, body: str | None = None
    ) -> RuntimeError:
        status = exc.response.status_code
        body_preview = body or _safe_body(exc.response)
        label = self._provider_label
        if status in (401, 403):
            return RuntimeError(
                f"{label} rejected the API key in {self.api_key_env!r} "
                f"(HTTP {status}). Check the key is set and active."
            )
        if status == 429:
            return RuntimeError(
                f"{label} rate limit hit (HTTP 429). Retry shortly or "
                f"switch to a different model. Body: {body_preview[:300]}"
            )
        if 500 <= status < 600:
            return RuntimeError(
                f"{label} upstream error (HTTP {status}) for model "
                f"{self.model!r}. Body: {body_preview[:300]}"
            )
        return RuntimeError(
            f"{label} request failed (HTTP {status}) for model "
            f"{self.model!r}. Body: {body_preview[:300]}"
        )


def _iter_messages(md_file: Path):
    """Yield ``{"role": ..., "content": ...}`` per message in a session log."""
    try:
        text = md_file.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("could not read history %s: %s", md_file, exc)
        return

    matches = list(_CONVERSATION_HEADER_RE.finditer(text))
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if not body:
            continue
        yield {"role": match.group("role"), "content": body}


def _safe_body(response: httpx.Response) -> str:
    try:
        return response.text
    except Exception:  # noqa: BLE001
        return ""


register("openai_compat", OpenAICompatBackend)
