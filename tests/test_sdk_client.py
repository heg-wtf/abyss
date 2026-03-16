"""Tests for the Python Agent SDK client."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from cclaw.sdk_client import (
    SDKClientPool,
    SDKQueryResult,
    _build_options,
    close_pool,
    get_pool,
    is_sdk_available,
    sdk_query,
    sdk_query_streaming,
)

# ─── Mock helpers ────────────────────────────────────────────────────────────


@dataclass
class MockTextBlock:
    text: str


@dataclass
class MockAssistantMessage:
    content: list
    model: str = "claude-sonnet-4-5"
    parent_tool_use_id: str | None = None
    error: str | None = None


@dataclass
class MockResultMessage:
    result: str | None
    session_id: str
    total_cost_usd: float | None = None
    subtype: str = "success"
    duration_ms: int = 100
    duration_api_ms: int = 80
    is_error: bool = False
    num_turns: int = 1
    stop_reason: str | None = None
    usage: dict | None = None
    structured_output: object = None


async def _mock_query_generator(messages):
    """Create an async generator that yields mock messages."""
    for message in messages:
        yield message


def _sdk_patches(query_return_value):
    """Create combined patch context for SDK types and query function.

    Patches AssistantMessage, ResultMessage, TextBlock, and query together
    so that isinstance checks inside sdk_client.py match our mock objects.
    """
    return patch.multiple(
        "claude_agent_sdk",
        query=MagicMock(return_value=query_return_value),
        AssistantMessage=MockAssistantMessage,
        ResultMessage=MockResultMessage,
        TextBlock=MockTextBlock,
    )


# ─── is_sdk_available ────────────────────────────────────────────────────────


class TestSDKAvailability:
    def test_sdk_available(self):
        import cclaw.sdk_client as module

        module._sdk_available = None
        with patch.dict("sys.modules", {"claude_agent_sdk": MagicMock()}):
            assert is_sdk_available() is True
        module._sdk_available = None

    def test_sdk_not_available(self):
        import cclaw.sdk_client as module

        module._sdk_available = None
        with patch.dict("sys.modules", {"claude_agent_sdk": None}):
            with patch("builtins.__import__", side_effect=ImportError("not found")):
                assert is_sdk_available() is False
        module._sdk_available = None

    def test_sdk_available_cached(self):
        import cclaw.sdk_client as module

        module._sdk_available = True
        assert is_sdk_available() is True
        module._sdk_available = None


# ─── _build_options ──────────────────────────────────────────────────────────


class TestBuildOptions:
    def test_minimal_options(self):
        options = _build_options(working_directory="/tmp/test")
        assert str(options.cwd) == "/tmp/test"
        assert options.permission_mode == "acceptEdits"
        assert options.setting_sources == ["project"]

    def test_with_model(self):
        options = _build_options(working_directory="/tmp/test", model="opus")
        assert options.model == "opus"

    def test_with_allowed_tools(self):
        tools = ["Read", "Write", "Bash"]
        options = _build_options(working_directory="/tmp/test", allowed_tools=tools)
        assert options.allowed_tools == tools

    def test_with_resume_session(self):
        options = _build_options(
            working_directory="/tmp/test",
            session_id="session-abc",
            resume_session=True,
        )
        assert options.resume == "session-abc"
        assert options.continue_conversation is True

    def test_without_resume_ignores_session_id(self):
        options = _build_options(
            working_directory="/tmp/test",
            session_id="session-abc",
            resume_session=False,
        )
        assert options.resume is None

    def test_with_environment_variables(self):
        env = {"API_KEY": "test-key"}
        options = _build_options(working_directory="/tmp/test", environment_variables=env)
        assert options.env["API_KEY"] == "test-key"

    def test_with_system_prompt(self):
        options = _build_options(
            working_directory="/tmp/test",
            system_prompt="You are a helpful assistant.",
        )
        assert options.system_prompt == "You are a helpful assistant."


# ─── sdk_query ───────────────────────────────────────────────────────────────


class TestSDKQuery:
    @pytest.mark.asyncio
    async def test_query_success(self):
        messages = [
            MockResultMessage(result="Hello!", session_id="sess-123", total_cost_usd=0.01),
        ]

        with _sdk_patches(_mock_query_generator(messages)):
            result = await sdk_query(
                session_key="bot1:chat_1",
                prompt="hi",
                working_directory="/tmp/test",
            )

        assert result.text == "Hello!"
        assert result.session_id == "sess-123"
        assert result.cost_usd == 0.01

    @pytest.mark.asyncio
    async def test_query_with_assistant_message(self):
        messages = [
            MockAssistantMessage(content=[MockTextBlock(text="Hello world")]),
            MockResultMessage(result="Hello world", session_id="sess-456"),
        ]

        with _sdk_patches(_mock_query_generator(messages)):
            result = await sdk_query(
                session_key="bot1:chat_1",
                prompt="hi",
                working_directory="/tmp/test",
            )

        assert result.text == "Hello world"
        assert result.session_id == "sess-456"

    @pytest.mark.asyncio
    async def test_query_result_overrides_accumulated_text(self):
        """ResultMessage.result takes precedence over accumulated AssistantMessage text."""
        messages = [
            MockAssistantMessage(content=[MockTextBlock(text="partial")]),
            MockResultMessage(result="Final answer", session_id="sess-789"),
        ]

        with _sdk_patches(_mock_query_generator(messages)):
            result = await sdk_query(
                session_key="bot1:chat_1",
                prompt="hi",
                working_directory="/tmp/test",
            )

        assert result.text == "Final answer"

    @pytest.mark.asyncio
    async def test_query_with_model(self):
        messages = [
            MockResultMessage(result="response", session_id="sess-1"),
        ]
        mock_query = MagicMock(return_value=_mock_query_generator(messages))

        with patch.multiple(
            "claude_agent_sdk",
            query=mock_query,
            AssistantMessage=MockAssistantMessage,
            ResultMessage=MockResultMessage,
            TextBlock=MockTextBlock,
        ):
            await sdk_query(
                session_key="bot1:chat_1",
                prompt="hi",
                working_directory="/tmp/test",
                model="opus",
            )

        call_kwargs = mock_query.call_args[1]
        assert call_kwargs["options"].model == "opus"

    @pytest.mark.asyncio
    async def test_query_with_resume(self):
        messages = [
            MockResultMessage(result="continued", session_id="sess-1"),
        ]
        mock_query = MagicMock(return_value=_mock_query_generator(messages))

        with patch.multiple(
            "claude_agent_sdk",
            query=mock_query,
            AssistantMessage=MockAssistantMessage,
            ResultMessage=MockResultMessage,
            TextBlock=MockTextBlock,
        ):
            await sdk_query(
                session_key="bot1:chat_1",
                prompt="follow up",
                working_directory="/tmp/test",
                session_id="sess-1",
                resume_session=True,
            )

        call_kwargs = mock_query.call_args[1]
        assert call_kwargs["options"].resume == "sess-1"
        assert call_kwargs["options"].continue_conversation is True

    @pytest.mark.asyncio
    async def test_query_timeout(self):
        async def slow_generator():
            await asyncio.sleep(10)
            yield MockResultMessage(result="late", session_id="x")

        with _sdk_patches(slow_generator()):
            with pytest.raises(TimeoutError, match="timed out"):
                await sdk_query(
                    session_key="bot1:chat_1",
                    prompt="hi",
                    working_directory="/tmp/test",
                    timeout=0,
                )

    @pytest.mark.asyncio
    async def test_query_no_result_raises(self):
        with _sdk_patches(_mock_query_generator([])):
            with pytest.raises(RuntimeError, match="no result"):
                await sdk_query(
                    session_key="bot1:chat_1",
                    prompt="hi",
                    working_directory="/tmp/test",
                )

    @pytest.mark.asyncio
    async def test_query_sdk_error_propagates(self):
        async def error_generator():
            raise RuntimeError("SDK internal error")
            yield  # makes this an async generator

        with _sdk_patches(error_generator()):
            with pytest.raises(RuntimeError, match="SDK internal error"):
                await sdk_query(
                    session_key="bot1:chat_1",
                    prompt="hi",
                    working_directory="/tmp/test",
                )


# ─── sdk_query_streaming ────────────────────────────────────────────────────


class TestSDKQueryStreaming:
    @pytest.mark.asyncio
    async def test_streaming_text_chunks(self):
        messages = [
            MockAssistantMessage(content=[MockTextBlock(text="Hello ")]),
            MockAssistantMessage(content=[MockTextBlock(text="Hello world!")]),
            MockResultMessage(result="Hello world!", session_id="sess-s1"),
        ]

        received_chunks: list[str] = []

        def on_chunk(text: str) -> None:
            received_chunks.append(text)

        with _sdk_patches(_mock_query_generator(messages)):
            result = await sdk_query_streaming(
                session_key="bot1:chat_1",
                prompt="hi",
                working_directory="/tmp/test",
                on_text_chunk=on_chunk,
            )

        assert result.text == "Hello world!"
        assert result.session_id == "sess-s1"
        assert received_chunks == ["Hello ", "world!"]

    @pytest.mark.asyncio
    async def test_streaming_final_result(self):
        messages = [
            MockAssistantMessage(content=[MockTextBlock(text="partial")]),
            MockResultMessage(result="Final text", session_id="sess-s2", total_cost_usd=0.05),
        ]

        with _sdk_patches(_mock_query_generator(messages)):
            result = await sdk_query_streaming(
                session_key="bot1:chat_1",
                prompt="hi",
                working_directory="/tmp/test",
            )

        assert result.text == "Final text"
        assert result.cost_usd == 0.05

    @pytest.mark.asyncio
    async def test_streaming_callback_error_continues(self):
        messages = [
            MockAssistantMessage(content=[MockTextBlock(text="Hello")]),
            MockResultMessage(result="Hello", session_id="sess-s3"),
        ]

        def bad_callback(text: str) -> None:
            raise ValueError("callback boom")

        with _sdk_patches(_mock_query_generator(messages)):
            result = await sdk_query_streaming(
                session_key="bot1:chat_1",
                prompt="hi",
                working_directory="/tmp/test",
                on_text_chunk=bad_callback,
            )

        assert result.text == "Hello"

    @pytest.mark.asyncio
    async def test_streaming_async_callback(self):
        messages = [
            MockAssistantMessage(content=[MockTextBlock(text="chunk1")]),
            MockResultMessage(result="chunk1", session_id="sess-s4"),
        ]

        received: list[str] = []

        async def async_callback(text: str) -> None:
            received.append(text)

        with _sdk_patches(_mock_query_generator(messages)):
            await sdk_query_streaming(
                session_key="bot1:chat_1",
                prompt="hi",
                working_directory="/tmp/test",
                on_text_chunk=async_callback,
            )

        assert received == ["chunk1"]

    @pytest.mark.asyncio
    async def test_streaming_no_callback(self):
        messages = [
            MockAssistantMessage(content=[MockTextBlock(text="response")]),
            MockResultMessage(result="response", session_id="sess-s5"),
        ]

        with _sdk_patches(_mock_query_generator(messages)):
            result = await sdk_query_streaming(
                session_key="bot1:chat_1",
                prompt="hi",
                working_directory="/tmp/test",
                on_text_chunk=None,
            )

        assert result.text == "response"

    @pytest.mark.asyncio
    async def test_streaming_timeout(self):
        async def slow_generator():
            await asyncio.sleep(10)
            yield MockResultMessage(result="late", session_id="x")

        with _sdk_patches(slow_generator()):
            with pytest.raises(TimeoutError, match="timed out"):
                await sdk_query_streaming(
                    session_key="bot1:chat_1",
                    prompt="hi",
                    working_directory="/tmp/test",
                    timeout=0,
                )


# ─── SDKQueryResult ──────────────────────────────────────────────────────────


class TestSDKQueryResult:
    def test_result_is_frozen(self):
        result = SDKQueryResult(text="hello", session_id="s1")
        with pytest.raises(AttributeError):
            result.text = "modified"

    def test_result_default_cost(self):
        result = SDKQueryResult(text="hello", session_id="s1")
        assert result.cost_usd is None

    def test_result_with_cost(self):
        result = SDKQueryResult(text="hello", session_id="s1", cost_usd=0.03)
        assert result.cost_usd == 0.03


# ─── SDKClientPool ──────────────────────────────────────────────────────────


class MockClient:
    """Lightweight mock for ClaudeSDKClient."""

    def __init__(self, responses: list | None = None) -> None:
        self.responses = responses or []
        self.queries: list[str] = []
        self.interrupted = False
        self.entered = False
        self.exited = False

    async def __aenter__(self):
        self.entered = True
        return self

    async def __aexit__(self, *args):
        self.exited = True

    async def query(self, prompt: str) -> None:
        self.queries.append(prompt)

    async def receive_response(self):
        for message in self.responses:
            yield message

    async def interrupt(self) -> None:
        self.interrupted = True


def _pool_patches(mock_client: MockClient):
    """Patch SDK imports so SDKClientPool creates our MockClient."""
    mock_options_class = MagicMock()
    mock_client_class = MagicMock(return_value=mock_client)

    return patch.multiple(
        "claude_agent_sdk",
        ClaudeSDKClient=mock_client_class,
        ClaudeAgentOptions=mock_options_class,
        AssistantMessage=MockAssistantMessage,
        ResultMessage=MockResultMessage,
        TextBlock=MockTextBlock,
    )


class TestSDKClientPool:
    @pytest.mark.asyncio
    async def test_query_creates_client_and_returns_result(self):
        """Pool creates a client on first query and returns the result."""
        responses = [
            MockResultMessage(result="pool response", session_id="pool-sess-1"),
        ]
        mock_client = MockClient(responses)

        pool = SDKClientPool()
        with _pool_patches(mock_client):
            result = await pool.query(
                "bot:1",
                "hello",
                working_directory="/tmp/test",
            )

        assert result.text == "pool response"
        assert result.session_id == "pool-sess-1"
        assert mock_client.entered is True
        assert mock_client.queries == ["hello"]
        assert pool.has_session("bot:1")

    @pytest.mark.asyncio
    async def test_query_reuses_existing_client(self):
        """Pool reuses the same client for subsequent queries."""
        responses_1 = [
            MockResultMessage(result="first", session_id="sess-1"),
        ]
        responses_2 = [
            MockResultMessage(result="second", session_id="sess-1"),
        ]
        client_1 = MockClient(responses_1)
        client_2 = MockClient(responses_2)

        pool = SDKClientPool()

        # First query creates client_1
        with _pool_patches(client_1):
            result_1 = await pool.query("bot:1", "first", working_directory="/tmp/test")

        assert result_1.text == "first"

        # Second query reuses client_1 (client_2 is never created)
        # We need to update client_1's responses for the second call
        client_1.responses = responses_2
        with _pool_patches(client_2):
            result_2 = await pool.query("bot:1", "second", working_directory="/tmp/test")

        assert result_2.text == "second"
        assert client_1.queries == ["first", "second"]
        assert client_2.entered is False  # client_2 was never used

    @pytest.mark.asyncio
    async def test_interrupt_existing_session(self):
        """Pool interrupts a running client."""
        responses = [
            MockResultMessage(result="ok", session_id="sess-1"),
        ]
        mock_client = MockClient(responses)
        pool = SDKClientPool()

        with _pool_patches(mock_client):
            await pool.query("bot:1", "hello", working_directory="/tmp/test")

        result = await pool.interrupt("bot:1")
        assert result is True
        assert mock_client.interrupted is True

    @pytest.mark.asyncio
    async def test_interrupt_nonexistent_session(self):
        """Pool returns False when interrupting a session that doesn't exist."""
        pool = SDKClientPool()
        result = await pool.interrupt("bot:999")
        assert result is False

    @pytest.mark.asyncio
    async def test_close_session(self):
        """Pool closes a specific session's client."""
        responses = [
            MockResultMessage(result="ok", session_id="sess-1"),
        ]
        mock_client = MockClient(responses)
        pool = SDKClientPool()

        with _pool_patches(mock_client):
            await pool.query("bot:1", "hello", working_directory="/tmp/test")

        assert pool.has_session("bot:1")
        await pool.close_session("bot:1")
        assert not pool.has_session("bot:1")
        assert mock_client.exited is True

    @pytest.mark.asyncio
    async def test_close_all(self):
        """Pool closes all clients."""
        responses = [
            MockResultMessage(result="ok", session_id="sess-1"),
        ]
        client_a = MockClient(responses)
        client_b = MockClient(responses)

        pool = SDKClientPool()

        with _pool_patches(client_a):
            await pool.query("bot:1", "hello", working_directory="/tmp/test")

        # Manually inject a second client
        pool._clients["bot:2"] = client_b
        client_b.entered = True

        await pool.close_all()
        assert not pool.has_session("bot:1")
        assert not pool.has_session("bot:2")
        assert client_a.exited is True
        assert client_b.exited is True

    @pytest.mark.asyncio
    async def test_has_session(self):
        """has_session returns correct state."""
        pool = SDKClientPool()
        assert not pool.has_session("bot:1")

        responses = [
            MockResultMessage(result="ok", session_id="sess-1"),
        ]
        mock_client = MockClient(responses)

        with _pool_patches(mock_client):
            await pool.query("bot:1", "hello", working_directory="/tmp/test")

        assert pool.has_session("bot:1")

    @pytest.mark.asyncio
    async def test_query_timeout(self):
        """Pool raises TimeoutError on slow queries."""

        class SlowClient(MockClient):
            async def receive_response(self):
                await asyncio.sleep(10)
                yield MockResultMessage(result="late", session_id="x")

        slow_client = SlowClient()
        pool = SDKClientPool()

        with _pool_patches(slow_client):
            with pytest.raises(TimeoutError, match="timed out"):
                await pool.query(
                    "bot:1",
                    "hello",
                    working_directory="/tmp/test",
                    timeout=0,
                )

    @pytest.mark.asyncio
    async def test_query_streaming_with_chunks(self):
        """Pool streaming calls on_text_chunk for each delta."""
        responses = [
            MockAssistantMessage(content=[MockTextBlock(text="Hello ")]),
            MockAssistantMessage(content=[MockTextBlock(text="Hello world!")]),
            MockResultMessage(result="Hello world!", session_id="sess-s1"),
        ]
        mock_client = MockClient(responses)
        pool = SDKClientPool()
        received_chunks: list[str] = []

        with _pool_patches(mock_client):
            result = await pool.query_streaming(
                "bot:1",
                "hello",
                on_text_chunk=lambda t: received_chunks.append(t),
                working_directory="/tmp/test",
            )

        assert result.text == "Hello world!"
        assert received_chunks == ["Hello ", "world!"]

    @pytest.mark.asyncio
    async def test_close_nonexistent_session_is_safe(self):
        """Closing a session that doesn't exist does not raise."""
        pool = SDKClientPool()
        await pool.close_session("bot:nonexistent")  # should not raise


# ─── Module-level pool singleton ────────────────────────────────────────────


class TestPoolSingleton:
    def test_get_pool_creates_singleton(self):
        import cclaw.sdk_client as module

        module._pool = None
        pool = get_pool()
        assert pool is not None
        assert get_pool() is pool  # same instance
        module._pool = None

    @pytest.mark.asyncio
    async def test_close_pool_clears_singleton(self):
        import cclaw.sdk_client as module

        module._pool = None
        pool = get_pool()
        assert module._pool is pool

        await close_pool()
        assert module._pool is None

    @pytest.mark.asyncio
    async def test_close_pool_when_none(self):
        import cclaw.sdk_client as module

        module._pool = None
        await close_pool()  # should not raise
        assert module._pool is None
