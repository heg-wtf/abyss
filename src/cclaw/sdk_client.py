"""Python Agent SDK client for cclaw.

Supports two modes:
- Pool mode: ``SDKClientPool`` keeps persistent ``ClaudeSDKClient`` instances per session,
  avoiding process re-spawn on follow-up messages (1-2s faster).
- One-shot mode: ``sdk_query()`` / ``sdk_query_streaming()`` for single queries (legacy).

Pool is the preferred mode. One-shot functions are kept for backward compatibility.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

_sdk_available: bool | None = None


def is_sdk_available() -> bool:
    """Check if claude-agent-sdk is installed and importable."""
    global _sdk_available
    if _sdk_available is None:
        try:
            import claude_agent_sdk  # noqa: F401

            _sdk_available = True
        except ImportError:
            _sdk_available = False
    return _sdk_available


@dataclass(frozen=True, slots=True)
class SDKQueryResult:
    """Result from an SDK query."""

    text: str
    session_id: str
    cost_usd: float | None = None


def _build_options(
    *,
    working_directory: str,
    model: str | None = None,
    permission_mode: str = "acceptEdits",
    allowed_tools: list[str] | None = None,
    system_prompt: str | None = None,
    environment_variables: dict[str, str] | None = None,
    session_id: str | None = None,
    resume_session: bool = False,
) -> Any:
    """Build ClaudeAgentOptions from the given parameters."""
    from claude_agent_sdk import ClaudeAgentOptions

    kwargs: dict[str, Any] = {
        "cwd": Path(working_directory),
        "permission_mode": permission_mode,
        "setting_sources": ["project"],
    }

    if model:
        kwargs["model"] = model
    if allowed_tools:
        kwargs["allowed_tools"] = allowed_tools
    if system_prompt:
        kwargs["system_prompt"] = system_prompt
    if environment_variables:
        kwargs["env"] = environment_variables
    if resume_session and session_id:
        kwargs["resume"] = session_id
        kwargs["continue_conversation"] = True

    return ClaudeAgentOptions(**kwargs)


async def sdk_query(
    *,
    session_key: str,
    prompt: str,
    working_directory: str,
    model: str | None = None,
    session_id: str | None = None,
    resume_session: bool = False,
    permission_mode: str = "acceptEdits",
    allowed_tools: list[str] | None = None,
    system_prompt: str | None = None,
    environment_variables: dict[str, str] | None = None,
    timeout: int = 300,
) -> SDKQueryResult:
    """Run a non-streaming query via Python Agent SDK.

    Args:
        session_key: Session identifier for logging.
        prompt: The prompt message.
        working_directory: Working directory for Claude Code.
        model: Claude model to use.
        session_id: Session ID for continuity.
        resume_session: If True, resume an existing session.
        permission_mode: Permission mode for tool execution.
        allowed_tools: List of tools to auto-approve.
        system_prompt: System prompt override.
        environment_variables: Environment variables to pass.
        timeout: Maximum execution time in seconds.

    Returns:
        SDKQueryResult with text, session_id, and cost.

    Raises:
        TimeoutError: If execution exceeds timeout.
        RuntimeError: If the SDK returns an error or no result.
    """
    from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock, query

    options = _build_options(
        working_directory=working_directory,
        model=model,
        permission_mode=permission_mode,
        allowed_tools=allowed_tools,
        system_prompt=system_prompt,
        environment_variables=environment_variables,
        session_id=session_id,
        resume_session=resume_session,
    )

    logger.info("SDK query for %s: %s", session_key, prompt[:100])

    result_text = ""
    result_session_id = ""
    cost_usd: float | None = None

    async def _run_query() -> None:
        nonlocal result_text, result_session_id, cost_usd
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        result_text += block.text
            elif isinstance(message, ResultMessage):
                if message.result is not None:
                    result_text = message.result
                result_session_id = message.session_id
                cost_usd = message.total_cost_usd

    try:
        await asyncio.wait_for(_run_query(), timeout=timeout)
    except asyncio.TimeoutError:
        logger.error("SDK query timed out after %ds for %s", timeout, session_key)
        raise TimeoutError(f"SDK query timed out after {timeout} seconds")

    if not result_text and not result_session_id:
        raise RuntimeError("SDK query returned no result")

    return SDKQueryResult(
        text=result_text.strip(),
        session_id=result_session_id,
        cost_usd=cost_usd,
    )


async def sdk_query_streaming(
    *,
    session_key: str,
    prompt: str,
    working_directory: str,
    on_text_chunk: Callable[[str], Any] | None = None,
    model: str | None = None,
    session_id: str | None = None,
    resume_session: bool = False,
    permission_mode: str = "acceptEdits",
    allowed_tools: list[str] | None = None,
    system_prompt: str | None = None,
    environment_variables: dict[str, str] | None = None,
    timeout: int = 300,
) -> SDKQueryResult:
    """Run a streaming query via Python Agent SDK.

    Calls on_text_chunk for each new text delta received.

    Args:
        session_key: Session identifier for logging.
        prompt: The prompt message.
        working_directory: Working directory for Claude Code.
        on_text_chunk: Callback for each text chunk (sync or async).
        model: Claude model to use.
        session_id: Session ID for continuity.
        resume_session: If True, resume an existing session.
        permission_mode: Permission mode for tool execution.
        allowed_tools: List of tools to auto-approve.
        system_prompt: System prompt override.
        environment_variables: Environment variables to pass.
        timeout: Maximum execution time in seconds.

    Returns:
        SDKQueryResult with final text, session_id, and cost.

    Raises:
        TimeoutError: If execution exceeds timeout.
        RuntimeError: If the SDK returns an error or no result.
    """
    from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock, query

    options = _build_options(
        working_directory=working_directory,
        model=model,
        permission_mode=permission_mode,
        allowed_tools=allowed_tools,
        system_prompt=system_prompt,
        environment_variables=environment_variables,
        session_id=session_id,
        resume_session=resume_session,
    )
    options.include_partial_messages = True

    logger.info("SDK streaming query for %s: %s", session_key, prompt[:100])

    result_text = ""
    result_session_id = ""
    cost_usd: float | None = None
    last_partial_length = 0

    async def _run_streaming() -> None:
        nonlocal result_text, result_session_id, cost_usd, last_partial_length
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                current_text = ""
                for block in message.content:
                    if isinstance(block, TextBlock):
                        current_text += block.text

                if current_text and on_text_chunk:
                    new_text = current_text[last_partial_length:]
                    if new_text:
                        try:
                            callback_result = on_text_chunk(new_text)
                            if asyncio.iscoroutine(callback_result):
                                await callback_result
                        except Exception as callback_error:
                            logger.debug("Stream chunk callback error: %s", callback_error)
                    last_partial_length = len(current_text)
                result_text = current_text

            elif isinstance(message, ResultMessage):
                if message.result is not None:
                    result_text = message.result
                result_session_id = message.session_id
                cost_usd = message.total_cost_usd

    try:
        await asyncio.wait_for(_run_streaming(), timeout=timeout)
    except asyncio.TimeoutError:
        logger.error("SDK streaming timed out after %ds for %s", timeout, session_key)
        raise TimeoutError(f"SDK streaming timed out after {timeout} seconds")

    if not result_text and not result_session_id:
        raise RuntimeError("SDK streaming query returned no result")

    return SDKQueryResult(
        text=result_text.strip(),
        session_id=result_session_id,
        cost_usd=cost_usd,
    )


# ─── SDKClientPool ──────────────────────────────────────────────────────────


class SDKClientPool:
    """Pool of persistent ``ClaudeSDKClient`` instances keyed by session.

    Each session key (e.g. ``"botname:chat_id"``) maps to one long-lived client.
    Subsequent ``query()`` calls on the same key reuse the existing process,
    avoiding the 1-2s spawn overhead.
    """

    def __init__(self) -> None:
        self._clients: dict[str, Any] = {}  # session_key -> ClaudeSDKClient
        self._last_used: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def query(
        self,
        session_key: str,
        prompt: str,
        *,
        working_directory: str,
        model: str | None = None,
        permission_mode: str = "acceptEdits",
        allowed_tools: list[str] | None = None,
        system_prompt: str | None = None,
        environment_variables: dict[str, str] | None = None,
        resume_session_id: str | None = None,
        timeout: int = 300,
    ) -> SDKQueryResult:
        """Send a query via a persistent client, creating one if needed.

        Args:
            session_key: Unique key for this session (e.g. "bot:chat_id").
            prompt: The prompt message.
            working_directory: Working directory for Claude Code.
            model: Claude model to use.
            permission_mode: Permission mode for tool execution.
            allowed_tools: List of tools to auto-approve.
            system_prompt: System prompt override.
            environment_variables: Environment variables to pass.
            resume_session_id: Session ID to resume (only for new client creation).
            timeout: Maximum execution time in seconds.

        Returns:
            SDKQueryResult with text, session_id, and cost.
        """
        from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock

        client = await self._get_or_create_client(
            session_key=session_key,
            working_directory=working_directory,
            model=model,
            permission_mode=permission_mode,
            allowed_tools=allowed_tools,
            system_prompt=system_prompt,
            environment_variables=environment_variables,
            resume_session_id=resume_session_id,
        )

        logger.info("Pool query for %s: %s", session_key, prompt[:100])

        result_text = ""
        result_session_id = ""
        cost_usd: float | None = None

        async def _run() -> None:
            nonlocal result_text, result_session_id, cost_usd
            await client.query(prompt)
            async for message in client.receive_response():
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            result_text += block.text
                elif isinstance(message, ResultMessage):
                    if message.result is not None:
                        result_text = message.result
                    result_session_id = message.session_id
                    cost_usd = message.total_cost_usd

        try:
            await asyncio.wait_for(_run(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.error("Pool query timed out after %ds for %s", timeout, session_key)
            raise TimeoutError(f"Pool query timed out after {timeout} seconds")

        if not result_text and not result_session_id:
            raise RuntimeError("Pool query returned no result")

        self._last_used[session_key] = time.monotonic()

        return SDKQueryResult(
            text=result_text.strip(),
            session_id=result_session_id,
            cost_usd=cost_usd,
        )

    async def query_streaming(
        self,
        session_key: str,
        prompt: str,
        *,
        on_text_chunk: Callable[[str], Any] | None = None,
        working_directory: str,
        model: str | None = None,
        permission_mode: str = "acceptEdits",
        allowed_tools: list[str] | None = None,
        system_prompt: str | None = None,
        environment_variables: dict[str, str] | None = None,
        resume_session_id: str | None = None,
        timeout: int = 300,
    ) -> SDKQueryResult:
        """Send a streaming query via a persistent client.

        Calls ``on_text_chunk`` for each new text delta received.
        """
        from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock

        client = await self._get_or_create_client(
            session_key=session_key,
            working_directory=working_directory,
            model=model,
            permission_mode=permission_mode,
            allowed_tools=allowed_tools,
            system_prompt=system_prompt,
            environment_variables=environment_variables,
            resume_session_id=resume_session_id,
        )

        logger.info("Pool streaming query for %s: %s", session_key, prompt[:100])

        result_text = ""
        result_session_id = ""
        cost_usd: float | None = None
        last_partial_length = 0

        async def _run() -> None:
            nonlocal result_text, result_session_id, cost_usd, last_partial_length
            await client.query(prompt)
            async for message in client.receive_response():
                if isinstance(message, AssistantMessage):
                    current_text = ""
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            current_text += block.text

                    if current_text and on_text_chunk:
                        new_text = current_text[last_partial_length:]
                        if new_text:
                            try:
                                callback_result = on_text_chunk(new_text)
                                if asyncio.iscoroutine(callback_result):
                                    await callback_result
                            except Exception as callback_error:
                                logger.debug(
                                    "Stream chunk callback error: %s",
                                    callback_error,
                                )
                        last_partial_length = len(current_text)
                    result_text = current_text

                elif isinstance(message, ResultMessage):
                    if message.result is not None:
                        result_text = message.result
                    result_session_id = message.session_id
                    cost_usd = message.total_cost_usd

        try:
            await asyncio.wait_for(_run(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.error("Pool streaming timed out after %ds for %s", timeout, session_key)
            raise TimeoutError(f"Pool streaming timed out after {timeout} seconds")

        if not result_text and not result_session_id:
            raise RuntimeError("Pool streaming query returned no result")

        self._last_used[session_key] = time.monotonic()

        return SDKQueryResult(
            text=result_text.strip(),
            session_id=result_session_id,
            cost_usd=cost_usd,
        )

    async def interrupt(self, session_key: str) -> bool:
        """Interrupt a running query for the given session.

        Returns True if a client was found and interrupted, False otherwise.
        """
        async with self._lock:
            client = self._clients.get(session_key)
        if client is None:
            return False
        try:
            await client.interrupt()
            logger.info("Interrupted SDK session %s", session_key)
            return True
        except Exception as error:
            logger.warning("Failed to interrupt SDK session %s: %s", session_key, error)
            return False

    async def close_session(self, session_key: str) -> None:
        """Close and remove a specific session's client."""
        async with self._lock:
            client = self._clients.pop(session_key, None)
            self._last_used.pop(session_key, None)
        if client is not None:
            try:
                await client.__aexit__(None, None, None)
            except Exception as error:
                logger.debug("Error closing SDK client for %s: %s", session_key, error)

    async def close_all(self) -> None:
        """Close all persistent clients."""
        async with self._lock:
            clients = list(self._clients.items())
            self._clients.clear()
            self._last_used.clear()

        for session_key, client in clients:
            try:
                await client.__aexit__(None, None, None)
            except Exception as error:
                logger.debug("Error closing SDK client for %s: %s", session_key, error)

        logger.info("Closed %d SDK client(s)", len(clients))

    def has_session(self, session_key: str) -> bool:
        """Check if a persistent client exists for the session key."""
        return session_key in self._clients

    async def _get_or_create_client(
        self,
        *,
        session_key: str,
        working_directory: str,
        model: str | None,
        permission_mode: str,
        allowed_tools: list[str] | None,
        system_prompt: str | None,
        environment_variables: dict[str, str] | None,
        resume_session_id: str | None,
    ) -> Any:
        """Get an existing client or create a new one."""
        from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

        async with self._lock:
            if session_key in self._clients:
                return self._clients[session_key]

            kwargs: dict[str, Any] = {
                "cwd": Path(working_directory),
                "permission_mode": permission_mode,
                "setting_sources": ["project"],
            }

            if model:
                kwargs["model"] = model
            if allowed_tools:
                kwargs["allowed_tools"] = allowed_tools
            if system_prompt:
                kwargs["system_prompt"] = system_prompt
            if environment_variables:
                kwargs["env"] = environment_variables
            if resume_session_id:
                kwargs["resume"] = resume_session_id
                kwargs["continue_conversation"] = True

            options = ClaudeAgentOptions(**kwargs)
            client = ClaudeSDKClient(options=options)
            await client.__aenter__()

            self._clients[session_key] = client
            self._last_used[session_key] = time.monotonic()
            logger.info("Created new SDK client for %s", session_key)
            return client


# ─── Module-level pool singleton ────────────────────────────────────────────

_pool: SDKClientPool | None = None


def get_pool() -> SDKClientPool:
    """Get the module-level SDK client pool (creates on first call)."""
    global _pool
    if _pool is None:
        _pool = SDKClientPool()
    return _pool


async def close_pool() -> None:
    """Close all clients in the module-level pool."""
    global _pool
    if _pool is not None:
        await _pool.close_all()
        _pool = None
