"""Tests for ``abyss.chat_core``."""

from __future__ import annotations

import pytest

from abyss import chat_core
from abyss.session import ensure_session, log_conversation


@pytest.fixture
def abyss_home(tmp_path, monkeypatch):
    home = tmp_path / ".abyss"
    home.mkdir()
    monkeypatch.setenv("ABYSS_HOME", str(home))
    return home


@pytest.fixture
def bot(abyss_home):
    bot_path = abyss_home / "bots" / "testbot"
    (bot_path / "sessions").mkdir(parents=True)
    (bot_path / "CLAUDE.md").write_text("# testbot\n")
    return {
        "name": "testbot",
        "path": bot_path,
        "config": {
            "display_name": "testbot",
            "personality": "neutral",
            "role": "tester",
        },
    }


class _FakeBackend:
    """Records the LLMRequest sent to it and emits canned chunks."""

    def __init__(self, chunks=("hello ", "world"), session_id="sess-1"):
        self._chunks = chunks
        self._session_id = session_id
        self.last_request = None

    async def run(self, request):  # pragma: no cover - unused
        from abyss.llm.base import LLMResult

        self.last_request = request
        return LLMResult(
            text="".join(self._chunks),
            input_tokens=1,
            output_tokens=2,
            session_id=self._session_id,
        )

    async def run_streaming(self, request, on_chunk):
        from abyss.llm.base import LLMResult

        self.last_request = request
        for chunk in self._chunks:
            await on_chunk(chunk)
        return LLMResult(
            text="".join(self._chunks),
            input_tokens=1,
            output_tokens=2,
            session_id=self._session_id,
        )

    async def cancel(self, _key):  # pragma: no cover - unused
        return True

    async def close(self):  # pragma: no cover - unused
        return None


@pytest.fixture
def fake_backend(monkeypatch):
    backend = _FakeBackend()
    monkeypatch.setattr(chat_core, "get_or_create", lambda *args, **kwargs: backend)
    return backend


@pytest.mark.asyncio
async def test_process_chat_message_streams_and_logs(bot, fake_backend):
    received: list[str] = []

    async def on_chunk(chunk):
        received.append(chunk)

    text = await chat_core.process_chat_message(
        bot_name=bot["name"],
        bot_path=bot["path"],
        bot_config=bot["config"],
        chat_id="chat_web_abc123",
        user_message="hi there",
        on_chunk=on_chunk,
    )

    assert text == "hello world"
    assert received == ["hello ", "world"]

    session_dir = bot["path"] / "sessions" / "chat_web_abc123"
    assert session_dir.is_dir()
    assert (session_dir / "workspace").is_dir()

    convo_files = sorted(session_dir.glob("conversation-*.md"))
    assert len(convo_files) == 1
    body = convo_files[0].read_text()
    assert "## user" in body
    assert "hi there" in body
    assert "## assistant" in body
    assert "hello world" in body


@pytest.mark.asyncio
async def test_process_chat_message_persists_claude_session_id(bot, fake_backend):
    await chat_core.process_chat_message(
        bot_name=bot["name"],
        bot_path=bot["path"],
        bot_config=bot["config"],
        chat_id="chat_web_session2",
        user_message="hello",
        on_chunk=None,
    )
    sess_id_file = bot["path"] / "sessions" / "chat_web_session2" / ".claude_session_id"
    assert sess_id_file.exists()
    assert sess_id_file.read_text().strip() == "sess-1"


@pytest.mark.asyncio
async def test_resume_fallback_when_runtime_error(bot, monkeypatch):
    """Second turn resumes; if backend raises RuntimeError, we re-bootstrap."""

    class FlakyBackend(_FakeBackend):
        def __init__(self):
            super().__init__()
            self.calls = 0

        async def run_streaming(self, request, on_chunk):
            from abyss.llm.base import LLMResult

            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("session expired")
            await on_chunk("recovered")
            return LLMResult(text="recovered", session_id="new-sess")

    backend = FlakyBackend()
    monkeypatch.setattr(chat_core, "get_or_create", lambda *args, **kwargs: backend)

    chat_id = "chat_web_resume"
    # Pre-seed a session id so the first call is a resume
    session_dir = ensure_session(bot["path"], chat_id, bot_name=bot["name"])
    (session_dir / ".claude_session_id").write_text("stale-id")

    received: list[str] = []

    text = await chat_core.process_chat_message(
        bot_name=bot["name"],
        bot_path=bot["path"],
        bot_config=bot["config"],
        chat_id=chat_id,
        user_message="hi",
        on_chunk=lambda c: received.append(c) or _noop(),
    )
    # The fallback path retried with bootstrap and produced a new session id
    assert text == "recovered"
    assert received == ["recovered"]
    assert backend.calls == 2
    assert (session_dir / ".claude_session_id").read_text().strip() == "new-sess"


async def _noop():
    return None


@pytest.mark.asyncio
async def test_existing_session_resumes_with_raw_user_message(bot, fake_backend):
    chat_id = "chat_web_resume2"
    session_dir = ensure_session(bot["path"], chat_id, bot_name=bot["name"])
    (session_dir / ".claude_session_id").write_text("existing-id")
    log_conversation(session_dir, "user", "earlier")
    log_conversation(session_dir, "assistant", "earlier reply")

    await chat_core.process_chat_message(
        bot_name=bot["name"],
        bot_path=bot["path"],
        bot_config=bot["config"],
        chat_id=chat_id,
        user_message="next msg",
        on_chunk=None,
    )
    # On resume we send the raw user message, NOT the bootstrap prompt
    assert fake_backend.last_request.user_prompt == "next msg"
    assert fake_backend.last_request.resume_session is True


@pytest.mark.asyncio
async def test_bootstrap_includes_history_and_memory(bot, fake_backend):
    from abyss.session import save_bot_memory, save_global_memory

    save_global_memory("global notes")
    save_bot_memory(bot["path"], "bot notes")

    chat_id = "chat_web_bootstrap"
    session_dir = ensure_session(bot["path"], chat_id, bot_name=bot["name"])
    log_conversation(session_dir, "user", "hi")
    log_conversation(session_dir, "assistant", "hello")

    await chat_core.process_chat_message(
        bot_name=bot["name"],
        bot_path=bot["path"],
        bot_config=bot["config"],
        chat_id=chat_id,
        user_message="follow-up",
        on_chunk=None,
    )

    sent = fake_backend.last_request.user_prompt
    assert "global notes" in sent
    assert "bot notes" in sent
    assert "follow-up" in sent
    assert fake_backend.last_request.resume_session is False
