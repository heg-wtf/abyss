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


# ---------------------------------------------------------------------------
# Attachment upload / serve / chat integration
# ---------------------------------------------------------------------------


# Smallest legal PNG (1x1 transparent) — passes magic byte check.
_MINIMAL_PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c63000100000005000183b76148000000004945"
    "4e44ae426082"
)
_MINIMAL_PDF_BYTES = b"%PDF-1.4\n%fake\n1 0 obj<</Type/Catalog>>endobj\n%%EOF\n"


def _multipart_form(parts: list[tuple[str, bytes, str | None]]) -> tuple[bytes, str]:
    """Build a basic multipart/form-data body for aiohttp test client."""
    boundary = "----abyss-test-boundary"
    out = bytearray()
    for name, content, content_type in parts:
        out += f"--{boundary}\r\n".encode()
        if content_type is None:
            out += f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
            out += content
        else:
            out += (f'Content-Disposition: form-data; name="file"; filename="{name}"\r\n').encode()
            out += f"Content-Type: {content_type}\r\n\r\n".encode()
            out += content
        out += b"\r\n"
    out += f"--{boundary}--\r\n".encode()
    return bytes(out), f"multipart/form-data; boundary={boundary}"


async def _new_session(client) -> str:
    create = await client.post("/chat/sessions", json={"bot": "alpha"})
    return (await create.json())["id"]


@pytest.mark.asyncio
async def test_upload_png_succeeds(client, abyss_home):
    sid = await _new_session(client)
    body, ctype = _multipart_form(
        [
            ("bot", b"alpha", None),
            ("session_id", sid.encode(), None),
            ("photo.png", _MINIMAL_PNG_BYTES, "image/png"),
        ]
    )
    resp = await client.post("/chat/upload", data=body, headers={"Content-Type": ctype})
    assert resp.status == 200, await resp.text()
    payload = await resp.json()
    assert payload["display_name"] == "photo.png"
    assert payload["mime"] == "image/png"
    assert payload["size"] == len(_MINIMAL_PNG_BYTES)
    assert payload["path"].startswith("uploads/")
    saved = abyss_home / "bots" / "alpha" / "sessions" / sid / "workspace" / payload["path"]
    assert saved.is_file()
    assert saved.read_bytes() == _MINIMAL_PNG_BYTES


@pytest.mark.asyncio
async def test_upload_pdf_succeeds(client, abyss_home):
    sid = await _new_session(client)
    body, ctype = _multipart_form(
        [
            ("bot", b"alpha", None),
            ("session_id", sid.encode(), None),
            ("doc.pdf", _MINIMAL_PDF_BYTES, "application/pdf"),
        ]
    )
    resp = await client.post("/chat/upload", data=body, headers={"Content-Type": ctype})
    assert resp.status == 200
    payload = await resp.json()
    assert payload["mime"] == "application/pdf"


@pytest.mark.asyncio
async def test_upload_rejects_invalid_mime(client):
    sid = await _new_session(client)
    body, ctype = _multipart_form(
        [
            ("bot", b"alpha", None),
            ("session_id", sid.encode(), None),
            ("note.txt", b"plain text", "text/plain"),
        ]
    )
    resp = await client.post("/chat/upload", data=body, headers={"Content-Type": ctype})
    assert resp.status == 400
    assert (await resp.json())["error"] == "invalid_mime"


@pytest.mark.asyncio
async def test_upload_rejects_mime_spoof(client):
    """A text payload claiming to be PNG must be rejected by magic byte check."""
    sid = await _new_session(client)
    body, ctype = _multipart_form(
        [
            ("bot", b"alpha", None),
            ("session_id", sid.encode(), None),
            ("fake.png", b"not really a png " * 10, "image/png"),
        ]
    )
    resp = await client.post("/chat/upload", data=body, headers={"Content-Type": ctype})
    assert resp.status == 400


@pytest.mark.asyncio
async def test_upload_rejects_oversize(client, abyss_home, monkeypatch):
    from abyss import chat_server

    monkeypatch.setattr(chat_server, "MAX_UPLOAD_BYTES", 1024)
    # Re-create the server with the patched limit so the inner check fires.
    sid = await _new_session(client)
    body, ctype = _multipart_form(
        [
            ("bot", b"alpha", None),
            ("session_id", sid.encode(), None),
            ("big.png", _MINIMAL_PNG_BYTES + b"\x00" * 4096, "image/png"),
        ]
    )
    resp = await client.post("/chat/upload", data=body, headers={"Content-Type": ctype})
    assert resp.status in (400, 413)


@pytest.mark.asyncio
async def test_upload_session_count_cap(client, abyss_home, monkeypatch):
    from abyss import chat_server

    monkeypatch.setattr(chat_server, "MAX_UPLOADS_PER_SESSION", 1)
    sid = await _new_session(client)
    body, ctype = _multipart_form(
        [
            ("bot", b"alpha", None),
            ("session_id", sid.encode(), None),
            ("a.png", _MINIMAL_PNG_BYTES, "image/png"),
        ]
    )
    first = await client.post("/chat/upload", data=body, headers={"Content-Type": ctype})
    assert first.status == 200
    body2, ctype2 = _multipart_form(
        [
            ("bot", b"alpha", None),
            ("session_id", sid.encode(), None),
            ("b.png", _MINIMAL_PNG_BYTES, "image/png"),
        ]
    )
    second = await client.post("/chat/upload", data=body2, headers={"Content-Type": ctype2})
    assert second.status == 429


@pytest.mark.asyncio
async def test_serve_uploaded_file(client, abyss_home):
    sid = await _new_session(client)
    body, ctype = _multipart_form(
        [
            ("bot", b"alpha", None),
            ("session_id", sid.encode(), None),
            ("photo.png", _MINIMAL_PNG_BYTES, "image/png"),
        ]
    )
    resp = await client.post("/chat/upload", data=body, headers={"Content-Type": ctype})
    name = (await resp.json())["path"][len("uploads/") :]
    served = await client.get(f"/chat/sessions/alpha/{sid}/file/{name}")
    assert served.status == 200
    assert served.headers["Content-Type"] == "image/png"
    assert await served.read() == _MINIMAL_PNG_BYTES


@pytest.mark.asyncio
async def test_serve_rejects_traversal(client):
    sid = await _new_session(client)
    resp = await client.get(f"/chat/sessions/alpha/{sid}/file/..%2Fetc%2Fpasswd")
    assert resp.status == 400


@pytest.mark.asyncio
async def test_chat_with_attachments_threads_paths(client, abyss_home, patch_backend):
    """A chat call with attachments propagates File: lines + log marker."""
    sid = await _new_session(client)
    body, ctype = _multipart_form(
        [
            ("bot", b"alpha", None),
            ("session_id", sid.encode(), None),
            ("hello.png", _MINIMAL_PNG_BYTES, "image/png"),
        ]
    )
    upload = await client.post("/chat/upload", data=body, headers={"Content-Type": ctype})
    saved_path = (await upload.json())["path"]

    chat_resp = await client.post(
        "/chat",
        json={
            "bot": "alpha",
            "session_id": sid,
            "message": "describe please",
            "attachments": [saved_path],
        },
    )
    # Drain SSE
    async for _ in chat_resp.content.iter_any():
        pass

    msgs = await client.get(f"/chat/sessions/alpha/{sid}/messages")
    body_msgs = (await msgs.json())["messages"]
    user_turn = next(m for m in body_msgs if m["role"] == "user")
    assert "describe please" in user_turn["content"]
    assert "attachments" in user_turn
    assert user_turn["attachments"][0]["display_name"] == "hello.png"
    assert user_turn["attachments"][0]["mime"] == "image/png"
    assert user_turn["attachments"][0]["url"].startswith(f"/api/chat/sessions/alpha/{sid}/file/")


@pytest.mark.asyncio
async def test_chat_rejects_invalid_attachment_path(client):
    sid = await _new_session(client)
    resp = await client.post(
        "/chat",
        json={
            "bot": "alpha",
            "session_id": sid,
            "message": "hi",
            "attachments": ["../../etc/passwd"],
        },
    )
    assert resp.status == 400


@pytest.mark.asyncio
async def test_upload_count_cap_holds_under_concurrency(client, abyss_home, monkeypatch):
    """Concurrent uploads must not exceed MAX_UPLOADS_PER_SESSION even when
    the count → check → write window is squeezed."""
    import asyncio as _asyncio

    from abyss import chat_server

    monkeypatch.setattr(chat_server, "MAX_UPLOADS_PER_SESSION", 2)
    sid = await _new_session(client)

    async def upload_one(suffix: bytes) -> int:
        body, ctype = _multipart_form(
            [
                ("bot", b"alpha", None),
                ("session_id", sid.encode(), None),
                (f"x{suffix.decode()}.png", _MINIMAL_PNG_BYTES, "image/png"),
            ]
        )
        resp = await client.post("/chat/upload", data=body, headers={"Content-Type": ctype})
        return resp.status

    statuses = await _asyncio.gather(
        upload_one(b"1"),
        upload_one(b"2"),
        upload_one(b"3"),
        upload_one(b"4"),
    )
    assert statuses.count(200) == 2
    assert statuses.count(429) == 2
    upload_dir = abyss_home / "bots" / "alpha" / "sessions" / sid / "workspace" / "uploads"
    assert sum(1 for _ in upload_dir.iterdir()) == 2


@pytest.mark.asyncio
async def test_chat_rejects_too_many_attachments(client):
    from abyss.chat_server import MAX_UPLOADS_PER_MESSAGE

    sid = await _new_session(client)
    resp = await client.post(
        "/chat",
        json={
            "bot": "alpha",
            "session_id": sid,
            "message": "hi",
            "attachments": [
                f"uploads/abc__file{i}.png" for i in range(MAX_UPLOADS_PER_MESSAGE + 1)
            ],
        },
    )
    assert resp.status == 400
