"""Tests for ``abyss.chat_server`` HTTP/SSE endpoints."""

from __future__ import annotations

import json

import pytest
import pytest_asyncio
import yaml
from aiohttp.test_utils import TestClient, TestServer

from abyss import chat_core, chat_server
from abyss.chat_server import _SECTION_PATTERN, ChatServer
from abyss.llm.base import LLMResult


@pytest.fixture
def abyss_home(tmp_path, monkeypatch):
    home = tmp_path / ".abyss"
    home.mkdir()
    monkeypatch.setenv("ABYSS_HOME", str(home))
    # Minimal global config + one bot
    (home / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "bots": [{"name": "alpha", "path": str(home / "bots" / "alpha")}],
                "settings": {"language": "english", "timezone": "UTC"},
            }
        )
    )
    bot_dir = home / "bots" / "alpha"
    (bot_dir / "sessions").mkdir(parents=True)
    bot_dir.joinpath("CLAUDE.md").write_text("# alpha\n")
    bot_dir.joinpath("bot.yaml").write_text(
        yaml.safe_dump(
            {
                "telegram_token": "x",
                "display_name": "Alpha",
                "personality": "neutral",
                "role": "tester",
            }
        )
    )
    return home


class _FakeBackend:
    async def run(self, request):
        return LLMResult(text="ok", session_id="s1")

    async def run_streaming(self, request, on_chunk):
        for chunk in ("hi ", "there"):
            await on_chunk(chunk)
        return LLMResult(text="hi there", session_id="s1")

    async def cancel(self, _key):
        return True

    async def close(self):
        return None


@pytest.fixture
def patch_backend(monkeypatch):
    backend = _FakeBackend()
    monkeypatch.setattr(chat_core, "get_or_create", lambda *a, **kw: backend)
    monkeypatch.setattr(chat_server, "get_or_create", lambda *a, **kw: backend)
    return backend


@pytest_asyncio.fixture
async def client(abyss_home, patch_backend):
    server = ChatServer()
    test_server = TestServer(server._app)
    test_client = TestClient(test_server)
    await test_client.start_server()
    try:
        yield test_client
    finally:
        await test_client.close()


@pytest.mark.asyncio
async def test_healthz(client):
    resp = await client.get("/healthz")
    assert resp.status == 200
    body = await resp.json()
    assert body["status"] == "ok"


@pytest.mark.asyncio
async def test_list_bots(client, abyss_home):
    resp = await client.get("/chat/bots")
    assert resp.status == 200
    body = await resp.json()
    names = [b["name"] for b in body["bots"]]
    assert names == ["alpha"]
    assert body["bots"][0]["display_name"] == "Alpha"


@pytest.mark.asyncio
async def test_create_list_delete_session(client, abyss_home):
    create = await client.post("/chat/sessions", json={"bot": "alpha"})
    assert create.status == 200
    created = await create.json()
    sid = created["id"]
    assert sid.startswith("chat_web_")
    assert (abyss_home / "bots" / "alpha" / "sessions" / sid).is_dir()

    listing = await client.get("/chat/sessions", params={"bot": "alpha"})
    assert listing.status == 200
    body = await listing.json()
    assert any(s["id"] == sid for s in body["sessions"])

    delete = await client.delete(f"/chat/sessions/alpha/{sid}")
    assert delete.status == 200
    assert (await delete.json())["deleted"] is True
    assert not (abyss_home / "bots" / "alpha" / "sessions" / sid).exists()


@pytest.mark.asyncio
async def test_create_session_unknown_bot(client):
    resp = await client.post("/chat/sessions", json={"bot": "ghost"})
    assert resp.status == 404


@pytest.mark.asyncio
async def test_create_session_invalid_name(client):
    resp = await client.post("/chat/sessions", json={"bot": "../etc"})
    assert resp.status == 400


@pytest.mark.asyncio
async def test_chat_invalid_session_id(client):
    resp = await client.post(
        "/chat",
        json={"bot": "alpha", "session_id": "chat_123", "message": "hi"},
    )
    assert resp.status == 400


@pytest.mark.asyncio
async def test_chat_streams_sse(client, abyss_home, patch_backend):
    create = await client.post("/chat/sessions", json={"bot": "alpha"})
    sid = (await create.json())["id"]

    resp = await client.post(
        "/chat",
        json={"bot": "alpha", "session_id": sid, "message": "hello"},
    )
    assert resp.status == 200
    assert resp.headers["Content-Type"].startswith("text/event-stream")

    body_bytes = b""
    async for chunk in resp.content.iter_any():
        body_bytes += chunk
    text = body_bytes.decode()
    events = [
        json.loads(line[len("data: ") :]) for line in text.splitlines() if line.startswith("data: ")
    ]
    types = [e["type"] for e in events]
    assert "chunk" in types
    assert types[-1] == "done"
    chunks = [e["text"] for e in events if e["type"] == "chunk"]
    assert chunks == ["hi ", "there"]

    # Verify the conversation log was written
    convo_files = list((abyss_home / "bots" / "alpha" / "sessions" / sid).glob("conversation-*.md"))
    assert len(convo_files) == 1
    body = convo_files[0].read_text()
    assert "hello" in body
    assert "hi there" in body


@pytest.mark.asyncio
async def test_chat_origin_rejected(client):
    create = await client.post("/chat/sessions", json={"bot": "alpha"})
    sid = (await create.json())["id"]
    resp = await client.post(
        "/chat",
        json={"bot": "alpha", "session_id": sid, "message": "hi"},
        headers={"Origin": "http://evil.example.com"},
    )
    assert resp.status == 403


@pytest.mark.asyncio
async def test_messages_endpoint_returns_history(client, abyss_home, patch_backend):
    create = await client.post("/chat/sessions", json={"bot": "alpha"})
    sid = (await create.json())["id"]

    sse = await client.post(
        "/chat",
        json={"bot": "alpha", "session_id": sid, "message": "hello"},
    )
    # Drain the SSE response so the conversation log is fully written
    async for _ in sse.content.iter_any():
        pass

    msgs = await client.get(f"/chat/sessions/alpha/{sid}/messages")
    assert msgs.status == 200
    body = await msgs.json()
    assert len(body["messages"]) == 2
    assert body["messages"][0]["role"] == "user"
    assert "hello" in body["messages"][0]["content"]
    assert body["messages"][1]["role"] == "assistant"
    assert "hi there" in body["messages"][1]["content"]


def test_section_pattern_parses_user_assistant():
    sample = (
        "## user (2026-05-03 10:00:00 UTC)\n\n"
        "first message\n\n"
        "## assistant (2026-05-03 10:00:01 UTC)\n\n"
        "first reply\n"
    )
    matches = list(_SECTION_PATTERN.finditer(sample))
    assert [(m.group(1), m.group(3).strip()) for m in matches] == [
        ("user", "first message"),
        ("assistant", "first reply"),
    ]


@pytest.mark.asyncio
async def test_cancel_endpoint(client, abyss_home, patch_backend):
    resp = await client.post(
        "/chat/cancel",
        json={"bot": "alpha", "session_id": "chat_web_abc123"},
    )
    assert resp.status == 200
    assert (await resp.json())["cancelled"] is True
