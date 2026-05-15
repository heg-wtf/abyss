"""Tests for ``abyss.chat_server`` HTTP/SSE endpoints."""

from __future__ import annotations

import json

import aiohttp
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
async def server_instance(abyss_home, patch_backend):
    from unittest.mock import MagicMock

    s = ChatServer()
    s._http_session = MagicMock()
    yield s


@pytest_asyncio.fixture
async def client(server_instance):
    test_server = TestServer(server_instance._app)
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
async def test_create_bot_writes_yaml_and_updates_config(client, abyss_home):
    """``POST /chat/bots`` mirrors ``abyss bot add`` byte-for-byte on disk."""
    resp = await client.post(
        "/chat/bots",
        json={
            "name": "newbot",
            "display_name": "New Bot",
            "personality": "calm and helpful",
            "role": "answer questions",
            "goal": "help the user",
        },
    )
    assert resp.status == 201
    body = await resp.json()
    assert body["ok"] is True
    assert body["name"] == "newbot"

    bot_yaml = abyss_home / "bots" / "newbot" / "bot.yaml"
    assert bot_yaml.exists()
    saved = yaml.safe_load(bot_yaml.read_text())
    assert saved["display_name"] == "New Bot"
    assert saved["personality"] == "calm and helpful"
    assert saved["role"] == "answer questions"
    assert saved["goal"] == "help the user"

    config = yaml.safe_load((abyss_home / "config.yaml").read_text())
    bot_names = [entry["name"] for entry in config["bots"]]
    assert "newbot" in bot_names

    listing = await client.get("/chat/bots")
    listed = await listing.json()
    assert "newbot" in [b["name"] for b in listed["bots"]]


@pytest.mark.asyncio
async def test_create_bot_rejects_duplicate_name(client, abyss_home):
    """A second create with an existing name returns 409 without overwriting."""
    resp = await client.post(
        "/chat/bots",
        json={
            "name": "alpha",
            "display_name": "Duplicate",
            "personality": "x",
            "role": "x",
        },
    )
    assert resp.status == 409
    body = await resp.json()
    assert "already exists" in body["error"]

    original = yaml.safe_load((abyss_home / "bots" / "alpha" / "bot.yaml").read_text())
    assert original["display_name"] == "Alpha"


@pytest.mark.asyncio
async def test_create_bot_normalizes_and_validates_name(client, abyss_home):
    """Spaces are hyphenated, uppercase is lowered; bad chars are rejected."""
    ok = await client.post(
        "/chat/bots",
        json={
            "name": "Casual Helper",
            "display_name": "Casual",
            "personality": "p",
            "role": "r",
        },
    )
    assert ok.status == 201
    assert (await ok.json())["name"] == "casual-helper"

    bad = await client.post(
        "/chat/bots",
        json={
            "name": "bot/with/slash",
            "display_name": "x",
            "personality": "p",
            "role": "r",
        },
    )
    assert bad.status == 400


@pytest.mark.asyncio
async def test_create_bot_requires_core_fields(client, abyss_home):
    for missing in ("display_name", "personality", "role"):
        payload = {
            "name": f"bot-missing-{missing.replace('_', '-')}",
            "display_name": "x",
            "personality": "p",
            "role": "r",
        }
        payload[missing] = ""
        resp = await client.post("/chat/bots", json=payload)
        assert resp.status == 400, f"missing {missing} should 400"
        body = await resp.json()
        assert missing in body["error"]


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
async def test_upload_missing_file_field(client, abyss_home):
    sid = await _new_session(client)
    body, ctype = _multipart_form(
        [
            ("bot", b"alpha", None),
            ("session_id", sid.encode(), None),
        ]
    )
    resp = await client.post("/chat/upload", data=body, headers={"Content-Type": ctype})
    assert resp.status == 400
    assert (await resp.json())["error"] == "file_field_missing"


@pytest.mark.asyncio
async def test_upload_invalid_multipart_body(client):
    """Server rejects payloads that aren't multipart with a 4xx + clear reason."""
    resp = await client.post(
        "/chat/upload",
        data=b"not multipart",
        headers={"Content-Type": "text/plain"},
    )
    assert resp.status == 400
    assert (await resp.json())["error"] == "invalid_multipart"


@pytest.mark.asyncio
async def test_upload_unknown_bot_or_session(client):
    body, ctype = _multipart_form(
        [
            ("bot", b"ghost", None),
            ("session_id", b"chat_web_abc12345", None),
            ("a.png", _MINIMAL_PNG_BYTES, "image/png"),
        ]
    )
    resp = await client.post("/chat/upload", data=body, headers={"Content-Type": ctype})
    assert resp.status == 404


@pytest.mark.asyncio
async def test_upload_unknown_session_for_known_bot(client, abyss_home):
    body, ctype = _multipart_form(
        [
            ("bot", b"alpha", None),
            ("session_id", b"chat_web_deadbeef", None),
            ("a.png", _MINIMAL_PNG_BYTES, "image/png"),
        ]
    )
    resp = await client.post("/chat/upload", data=body, headers={"Content-Type": ctype})
    assert resp.status == 404
    assert (await resp.json())["error"] == "session not found"


@pytest.mark.asyncio
async def test_serve_unknown_attachment_returns_404(client):
    sid = await _new_session(client)
    resp = await client.get(f"/chat/sessions/alpha/{sid}/file/abcd1234__missing.png")
    assert resp.status == 404


@pytest.mark.asyncio
async def test_serve_invalid_session_returns_404(client):
    resp = await client.get("/chat/sessions/alpha/chat_web_deadbeef/file/abcd1234__missing.png")
    assert resp.status == 404


@pytest.mark.asyncio
async def test_chat_with_attachments_missing_session_dir(client):
    """A valid session id whose directory was deleted out-of-band must surface
    as the matching session-level 404, not a path-traversal 400."""
    sid = "chat_web_deadbeef99"
    resp = await client.post(
        "/chat",
        json={
            "bot": "alpha",
            "session_id": sid,
            "message": "hi",
            "attachments": ["uploads/abcd1234__file.png"],
        },
    )
    assert resp.status == 404


@pytest.mark.asyncio
async def test_chat_with_invalid_attachment_field_type(client):
    sid = await _new_session(client)
    resp = await client.post(
        "/chat",
        json={
            "bot": "alpha",
            "session_id": sid,
            "message": "hi",
            "attachments": "uploads/should-be-list.png",
        },
    )
    assert resp.status == 400


@pytest.mark.asyncio
async def test_chat_with_attachment_not_under_uploads_prefix(client):
    sid = await _new_session(client)
    resp = await client.post(
        "/chat",
        json={
            "bot": "alpha",
            "session_id": sid,
            "message": "hi",
            "attachments": ["other/abc.png"],
        },
    )
    assert resp.status == 400


@pytest.mark.asyncio
async def test_chat_message_too_large(client):
    sid = await _new_session(client)
    resp = await client.post(
        "/chat",
        json={
            "bot": "alpha",
            "session_id": sid,
            "message": "x" * 33_000,  # > MAX_MESSAGE_BYTES (32 KiB)
        },
    )
    assert resp.status == 413


@pytest.mark.asyncio
async def test_chat_invalid_json_body(client):
    resp = await client.post(
        "/chat",
        data=b"not json",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status == 400
    assert (await resp.json())["error"] == "invalid JSON"


@pytest.mark.asyncio
async def test_cancel_invalid_json(client):
    resp = await client.post(
        "/chat/cancel",
        data=b"not json",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status == 400


@pytest.mark.asyncio
async def test_create_session_invalid_json(client):
    resp = await client.post(
        "/chat/sessions",
        data=b"not json",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status == 400


@pytest.mark.asyncio
async def test_list_sessions_missing_bot_param(client):
    resp = await client.get("/chat/sessions")
    assert resp.status == 400


@pytest.mark.asyncio
async def test_reset_server_singleton(monkeypatch):
    from abyss.chat_server import get_server, reset_server_for_testing

    server_a = get_server()
    await reset_server_for_testing()
    server_b = get_server()
    assert server_a is not server_b
    await reset_server_for_testing()


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


# ---------------------------------------------------------------------------
# /chat/transcribe
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transcribe_no_api_key(client, monkeypatch):
    monkeypatch.setattr(chat_server, "ELEVENLABS_API_KEY", "")
    resp = await client.post("/chat/transcribe")
    assert resp.status == 503


@pytest.mark.asyncio
async def test_transcribe_missing_audio_field(client, monkeypatch):
    monkeypatch.setattr(chat_server, "ELEVENLABS_API_KEY", "test-key")
    form_data = aiohttp.FormData()
    form_data.add_field("other", b"data", content_type="application/octet-stream")
    resp = await client.post("/chat/transcribe", data=form_data)
    assert resp.status == 400


@pytest.mark.asyncio
async def test_transcribe_audio_too_large(client, monkeypatch):
    monkeypatch.setattr(chat_server, "ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setattr(chat_server, "MAX_AUDIO_BYTES", 10)
    form_data = aiohttp.FormData()
    form_data.add_field("audio", b"x" * 11, filename="audio.webm", content_type="audio/webm")
    resp = await client.post("/chat/transcribe", data=form_data)
    assert resp.status == 413


@pytest.mark.asyncio
async def test_transcribe_filters_low_probability(client, server_instance, monkeypatch):
    from unittest.mock import AsyncMock, MagicMock

    monkeypatch.setattr(chat_server, "ELEVENLABS_API_KEY", "test-key")

    fake_response = AsyncMock()
    fake_response.status = 200
    fake_response.json = AsyncMock(
        return_value={"text": "자막 제공 및 광고를 포함하고 있습니다", "language_probability": 0.1}
    )
    fake_response.__aenter__ = AsyncMock(return_value=fake_response)
    fake_response.__aexit__ = AsyncMock(return_value=False)

    server_instance._http_session.post = MagicMock(return_value=fake_response)

    form_data = aiohttp.FormData()
    form_data.add_field("audio", b"audio_data", filename="audio.webm", content_type="audio/webm")
    resp = await client.post("/chat/transcribe", data=form_data)

    assert resp.status == 200
    data = await resp.json()
    assert data["text"] == ""


@pytest.mark.asyncio
async def test_transcribe_returns_text(client, server_instance, monkeypatch):
    from unittest.mock import AsyncMock, MagicMock

    monkeypatch.setattr(chat_server, "ELEVENLABS_API_KEY", "test-key")

    fake_response = AsyncMock()
    fake_response.status = 200
    fake_response.json = AsyncMock(
        return_value={"text": "안녕하세요", "language_probability": 0.95}
    )
    fake_response.__aenter__ = AsyncMock(return_value=fake_response)
    fake_response.__aexit__ = AsyncMock(return_value=False)

    server_instance._http_session.post = MagicMock(return_value=fake_response)

    form_data = aiohttp.FormData()
    form_data.add_field("audio", b"audio_data", filename="audio.webm", content_type="audio/webm")
    resp = await client.post("/chat/transcribe", data=form_data)

    assert resp.status == 200
    data = await resp.json()
    assert data["text"] == "안녕하세요"


# ---------------------------------------------------------------------------
# /chat/speak
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_speak_no_api_key(client, monkeypatch):
    monkeypatch.setattr(chat_server, "ELEVENLABS_API_KEY", "")
    resp = await client.post("/chat/speak", json={"text": "hello"})
    assert resp.status == 503


@pytest.mark.asyncio
async def test_speak_missing_text(client, monkeypatch):
    monkeypatch.setattr(chat_server, "ELEVENLABS_API_KEY", "test-key")
    resp = await client.post("/chat/speak", json={"text": ""})
    assert resp.status == 400


@pytest.mark.asyncio
async def test_speak_invalid_json(client, monkeypatch):
    monkeypatch.setattr(chat_server, "ELEVENLABS_API_KEY", "test-key")
    resp = await client.post(
        "/chat/speak",
        data=b"not json",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status == 400


@pytest.mark.asyncio
async def test_speak_streams_audio(client, server_instance, monkeypatch):
    from unittest.mock import AsyncMock, MagicMock

    monkeypatch.setattr(chat_server, "ELEVENLABS_API_KEY", "test-key")

    mp3_bytes = b"\xff\xfb\x90\x00" * 10

    async def fake_iter_chunked(_size):
        yield mp3_bytes

    fake_response = MagicMock()
    fake_response.status = 200
    fake_response.content = MagicMock()
    fake_response.content.iter_chunked = fake_iter_chunked
    fake_response.__aenter__ = AsyncMock(return_value=fake_response)
    fake_response.__aexit__ = AsyncMock(return_value=False)

    server_instance._http_session.post = MagicMock(return_value=fake_response)

    resp = await client.post("/chat/speak", json={"text": "안녕하세요"})

    assert resp.status == 200
    assert "audio/mpeg" in resp.headers["Content-Type"]
    body = await resp.read()
    assert len(body) > 0


# ---------------------------------------------------------------------------
# Slash command routing (Phase 1b)
# ---------------------------------------------------------------------------


async def _parse_sse_events(sse_response) -> list[dict]:
    """Collect SSE ``data: <json>`` events from a streamed response."""

    raw = b""
    async for chunk in sse_response.content.iter_any():
        raw += chunk
    events: list[dict] = []
    for line in raw.split(b"\n"):
        if line.startswith(b"data: "):
            events.append(json.loads(line[len(b"data: ") :].decode("utf-8")))
    return events


@pytest.mark.asyncio
async def test_list_commands_endpoint(client):
    resp = await client.get("/chat/commands")
    assert resp.status == 200
    body = await resp.json()
    names = [cmd["name"] for cmd in body["commands"]]
    assert "help" in names
    assert "status" in names
    assert "cron" in names
    # Each command has description + usage keys.
    for cmd in body["commands"]:
        assert "description" in cmd
        assert "usage" in cmd


@pytest.mark.asyncio
async def test_slash_help_returns_command_list(client, patch_backend):
    create = await client.post("/chat/sessions", json={"bot": "alpha"})
    sid = (await create.json())["id"]

    sse = await client.post(
        "/chat",
        json={"bot": "alpha", "session_id": sid, "message": "/help"},
    )
    events = await _parse_sse_events(sse)
    result_event = next(e for e in events if e["type"] == "command_result")
    assert result_event["command"] == "help"
    assert "/start" in result_event["text"]
    assert any(e["type"] == "done" for e in events)


@pytest.mark.asyncio
async def test_slash_status_uses_dashboard_session(client, patch_backend):
    create = await client.post("/chat/sessions", json={"bot": "alpha"})
    sid = (await create.json())["id"]
    sse = await client.post(
        "/chat",
        json={"bot": "alpha", "session_id": sid, "message": "/status"},
    )
    events = await _parse_sse_events(sse)
    result = next(e for e in events if e["type"] == "command_result")
    assert sid in result["text"]
    assert "alpha" in result["text"]


@pytest.mark.asyncio
async def test_slash_files_lists_workspace(client, abyss_home, patch_backend):
    create = await client.post("/chat/sessions", json={"bot": "alpha"})
    sid = (await create.json())["id"]
    workspace = abyss_home / "bots" / "alpha" / "sessions" / sid / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "report.md").write_text("hello")

    sse = await client.post(
        "/chat",
        json={"bot": "alpha", "session_id": sid, "message": "/files"},
    )
    events = await _parse_sse_events(sse)
    result = next(e for e in events if e["type"] == "command_result")
    assert "report.md" in result["text"]


@pytest.mark.asyncio
async def test_slash_unknown_returns_error(client, patch_backend):
    create = await client.post("/chat/sessions", json={"bot": "alpha"})
    sid = (await create.json())["id"]
    sse = await client.post(
        "/chat",
        json={"bot": "alpha", "session_id": sid, "message": "/banana"},
    )
    events = await _parse_sse_events(sse)
    assert any(e["type"] == "error" for e in events)


@pytest.mark.asyncio
async def test_slash_cron_usage(client, patch_backend):
    """``/cron`` with no args returns the usage / command list."""

    create = await client.post("/chat/sessions", json={"bot": "alpha"})
    sid = (await create.json())["id"]
    sse = await client.post(
        "/chat",
        json={"bot": "alpha", "session_id": sid, "message": "/cron"},
    )
    events = await _parse_sse_events(sse)
    result = next(e for e in events if e["type"] == "command_result")
    assert "/cron list" in result["text"]


@pytest.mark.asyncio
async def test_slash_cron_run_unknown_job(client, patch_backend):
    """``/cron run <job>`` returns a clear "not found" message when
    the job slug doesn't match anything in cron.yaml — without
    crashing the scheduler hook."""
    create = await client.post("/chat/sessions", json={"bot": "alpha"})
    sid = (await create.json())["id"]
    sse = await client.post(
        "/chat",
        json={"bot": "alpha", "session_id": sid, "message": "/cron run nope"},
    )
    events = await _parse_sse_events(sse)
    result = next(e for e in events if e["type"] == "command_result")
    assert "not found" in result["text"]


@pytest.mark.asyncio
async def test_slash_cron_run_missing_arg(client, patch_backend):
    """``/cron run`` without a job name surfaces the usage hint."""
    create = await client.post("/chat/sessions", json={"bot": "alpha"})
    sid = (await create.json())["id"]
    sse = await client.post(
        "/chat",
        json={"bot": "alpha", "session_id": sid, "message": "/cron run"},
    )
    events = await _parse_sse_events(sse)
    result = next(e for e in events if e["type"] == "command_result")
    assert "Usage" in result["text"]


@pytest.mark.asyncio
async def test_slash_cron_edit_falls_back(client, patch_backend):
    """``/cron edit`` requires multi-step prompting that the PWA
    chat doesn't yet support — surface a hint, not a crash."""
    create = await client.post("/chat/sessions", json={"bot": "alpha"})
    sid = (await create.json())["id"]
    sse = await client.post(
        "/chat",
        json={"bot": "alpha", "session_id": sid, "message": "/cron edit x"},
    )
    events = await _parse_sse_events(sse)
    result = next(e for e in events if e["type"] == "command_result")
    assert "not yet wired" in result["text"]


@pytest.mark.asyncio
async def test_slash_cron_list_empty(client, patch_backend, monkeypatch):
    monkeypatch.setattr("abyss.cron.list_cron_jobs", lambda b: [], raising=False)
    create = await client.post("/chat/sessions", json={"bot": "alpha"})
    sid = (await create.json())["id"]
    sse = await client.post(
        "/chat",
        json={"bot": "alpha", "session_id": sid, "message": "/cron list"},
    )
    events = await _parse_sse_events(sse)
    result = next(e for e in events if e["type"] == "command_result")
    assert "No cron jobs" in result["text"]


@pytest.mark.asyncio
async def test_slash_send_returns_file_metadata(client, abyss_home, patch_backend):
    create = await client.post("/chat/sessions", json={"bot": "alpha"})
    sid = (await create.json())["id"]
    workspace = abyss_home / "bots" / "alpha" / "sessions" / sid / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    target = workspace / "out.txt"
    target.write_text("payload")

    sse = await client.post(
        "/chat",
        json={"bot": "alpha", "session_id": sid, "message": "/send out.txt"},
    )
    events = await _parse_sse_events(sse)
    result = next(e for e in events if e["type"] == "command_result")
    assert "file" in result
    assert result["file"]["name"] == "out.txt"
    assert result["file"]["url"].endswith("/out.txt")


@pytest.mark.asyncio
async def test_slash_messages_endpoint_returns_logged_pair(client, abyss_home, patch_backend):
    """The slash exchange must come back through the standard
    ``/messages`` endpoint so a navigation away + return rebuilds the
    chat surface with the slash result intact. The opposite policy
    (skip logging) used to live here; we flipped it after users
    reported that slash replies vanished when they switched chats."""

    create = await client.post("/chat/sessions", json={"bot": "alpha"})
    sid = (await create.json())["id"]

    sse = await client.post(
        "/chat",
        json={"bot": "alpha", "session_id": sid, "message": "/help"},
    )
    async for _ in sse.content.iter_any():
        pass

    msgs = await client.get(f"/chat/sessions/alpha/{sid}/messages")
    assert msgs.status == 200
    body = await msgs.json()
    roles = [m["role"] for m in body["messages"]]
    assert roles == ["user", "assistant"]
    assert body["messages"][0]["content"] == "/help"
    assert "/start" in body["messages"][1]["content"]


@pytest.mark.asyncio
async def test_regular_message_still_streams(client, abyss_home, patch_backend):
    """Ensure the slash branch doesn't break ordinary chat flow."""

    create = await client.post("/chat/sessions", json={"bot": "alpha"})
    sid = (await create.json())["id"]
    sse = await client.post(
        "/chat",
        json={"bot": "alpha", "session_id": sid, "message": "hello"},
    )
    events = await _parse_sse_events(sse)
    assert any(e["type"] == "chunk" for e in events)
    assert any(e["type"] == "done" for e in events)


# ---------------------------------------------------------------------------
# Slash command routing — Phase 1c (skills / heartbeat / compact)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_slash_skills_lists_on_dashboard(client, patch_backend):
    create = await client.post("/chat/sessions", json={"bot": "alpha"})
    sid = (await create.json())["id"]
    sse = await client.post(
        "/chat",
        json={"bot": "alpha", "session_id": sid, "message": "/skills list"},
    )
    events = await _parse_sse_events(sse)
    result = next(e for e in events if e["type"] == "command_result")
    # Either "No skills attached" or a list — either is success for this test.
    assert "skill" in result["text"].lower()


@pytest.mark.asyncio
async def test_slash_heartbeat_status(client, patch_backend, monkeypatch):
    monkeypatch.setattr(
        "abyss.heartbeat.get_heartbeat_config",
        lambda b: {
            "enabled": False,
            "interval_minutes": 30,
            "active_hours": {"start": "07:00", "end": "23:00"},
        },
        raising=False,
    )
    create = await client.post("/chat/sessions", json={"bot": "alpha"})
    sid = (await create.json())["id"]
    sse = await client.post(
        "/chat",
        json={"bot": "alpha", "session_id": sid, "message": "/heartbeat"},
    )
    events = await _parse_sse_events(sse)
    result = next(e for e in events if e["type"] == "command_result")
    assert "Heartbeat" in result["text"]


@pytest.mark.asyncio
async def test_slash_heartbeat_run_fires(client, patch_backend, monkeypatch):
    """``/heartbeat run`` calls ``execute_heartbeat`` (same code path
    as the scheduler) and reports back. We stub the executor to keep
    the test deterministic; the real function is tested elsewhere."""
    from unittest.mock import AsyncMock

    called = AsyncMock()
    monkeypatch.setattr("abyss.heartbeat.execute_heartbeat", called)

    create = await client.post("/chat/sessions", json={"bot": "alpha"})
    sid = (await create.json())["id"]
    sse = await client.post(
        "/chat",
        json={"bot": "alpha", "session_id": sid, "message": "/heartbeat run"},
    )
    events = await _parse_sse_events(sse)
    result = next(e for e in events if e["type"] == "command_result")
    assert "Heartbeat fired" in result["text"]
    called.assert_called_once()


@pytest.mark.asyncio
async def test_slash_compact_no_targets(client, patch_backend, monkeypatch):
    monkeypatch.setattr(
        "abyss.token_compact.collect_compact_targets",
        lambda b: [],
        raising=False,
    )
    create = await client.post("/chat/sessions", json={"bot": "alpha"})
    sid = (await create.json())["id"]
    sse = await client.post(
        "/chat",
        json={"bot": "alpha", "session_id": sid, "message": "/compact"},
    )
    events = await _parse_sse_events(sse)
    result = next(e for e in events if e["type"] == "command_result")
    assert "No compactable" in result["text"]


@pytest.mark.asyncio
async def test_slash_bind_unbind_unknown_after_group_removal(client, patch_backend):
    """``/bind`` and ``/unbind`` were removed when the group surface
    was retired in v2026.05.14. The slash dispatcher should treat
    them as unknown commands so a fresh PWA-native group rewrite can
    re-introduce the names later without colliding with stubs."""
    create = await client.post("/chat/sessions", json={"bot": "alpha"})
    sid = (await create.json())["id"]
    for cmd in ("/bind team", "/unbind"):
        sse = await client.post(
            "/chat",
            json={"bot": "alpha", "session_id": sid, "message": cmd},
        )
        events = await _parse_sse_events(sse)
        # Unknown commands return an error event, not a command_result.
        types = [event["type"] for event in events]
        assert "error" in types or "command_result" not in types


# ---------------------------------------------------------------------------
# Session rename (Phase 3 — custom_name)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rename_session_sets_and_persists(client):
    create = await client.post("/chat/sessions", json={"bot": "alpha"})
    body = await create.json()
    assert body["custom_name"] is None
    sid = body["id"]

    rename = await client.post(
        f"/chat/sessions/alpha/{sid}/rename",
        json={"name": "경제질문"},
    )
    assert rename.status == 200
    rename_body = await rename.json()
    assert rename_body["custom_name"] == "경제질문"

    # Subsequent list reflects the new name.
    sessions = await client.get("/chat/sessions?bot=alpha")
    payload = await sessions.json()
    target = next(s for s in payload["sessions"] if s["id"] == sid)
    assert target["custom_name"] == "경제질문"


@pytest.mark.asyncio
async def test_rename_session_clears_with_empty_name(client):
    create = await client.post("/chat/sessions", json={"bot": "alpha"})
    sid = (await create.json())["id"]
    await client.post(
        f"/chat/sessions/alpha/{sid}/rename",
        json={"name": "first"},
    )
    cleared = await client.post(
        f"/chat/sessions/alpha/{sid}/rename",
        json={"name": "   "},
    )
    assert (await cleared.json())["custom_name"] is None


@pytest.mark.asyncio
async def test_rename_session_strips_control_chars(client):
    create = await client.post("/chat/sessions", json={"bot": "alpha"})
    sid = (await create.json())["id"]
    rename = await client.post(
        f"/chat/sessions/alpha/{sid}/rename",
        json={"name": "  hello\x00world\n  "},
    )
    body = await rename.json()
    assert body["custom_name"] == "helloworld"


@pytest.mark.asyncio
async def test_rename_session_caps_length(client):
    create = await client.post("/chat/sessions", json={"bot": "alpha"})
    sid = (await create.json())["id"]
    long_name = "x" * 200
    body = await (
        await client.post(
            f"/chat/sessions/alpha/{sid}/rename",
            json={"name": long_name},
        )
    ).json()
    # Cap from chat_server.MAX_CUSTOM_NAME_LENGTH.
    from abyss.chat_server import MAX_CUSTOM_NAME_LENGTH

    assert len(body["custom_name"]) == MAX_CUSTOM_NAME_LENGTH


@pytest.mark.asyncio
async def test_rename_session_not_found(client):
    resp = await client.post(
        "/chat/sessions/alpha/chat_web_deadbeef/rename",
        json={"name": "x"},
    )
    assert resp.status == 404


@pytest.mark.asyncio
async def test_rename_session_rejects_non_string(client):
    create = await client.post("/chat/sessions", json={"bot": "alpha"})
    sid = (await create.json())["id"]
    resp = await client.post(
        f"/chat/sessions/alpha/{sid}/rename",
        json={"name": 42},
    )
    assert resp.status == 400


@pytest.mark.asyncio
async def test_rename_metadata_survives_session_listing(client, abyss_home):
    """Custom name persists in the session directory and is restored on
    fresh server reads of /chat/sessions."""
    create = await client.post("/chat/sessions", json={"bot": "alpha"})
    sid = (await create.json())["id"]
    await client.post(
        f"/chat/sessions/alpha/{sid}/rename",
        json={"name": "starred"},
    )
    # Confirm the file exists on disk where we expect.
    meta_file = abyss_home / "bots" / "alpha" / "sessions" / sid / ".session_meta.json"
    assert meta_file.exists()
    import json as _json

    assert _json.loads(meta_file.read_text())["custom_name"] == "starred"


# ---------------------------------------------------------------------------
# Web Push routes + trigger (Phase 2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_push_vapid_key_endpoint_returns_public_key(client, abyss_home):
    resp = await client.get("/chat/push/vapid-key")
    assert resp.status == 200
    body = await resp.json()
    assert "publicKey" in body
    assert isinstance(body["publicKey"], str)
    assert len(body["publicKey"]) > 50


@pytest.mark.asyncio
async def test_push_subscribe_persists(client, abyss_home):
    sub = {
        "endpoint": "https://fcm.googleapis.com/fcm/send/test1",
        "keys": {"p256dh": "p256dh-stub", "auth": "auth-stub"},
        "device_id": "phone-1",
    }
    resp = await client.post("/chat/push/subscribe", json=sub)
    assert resp.status == 200
    assert (await resp.json()) == {"ok": True}

    from abyss import web_push as web_push_mod

    subs = web_push_mod.list_subscriptions()
    assert len(subs) == 1
    assert subs[0]["endpoint"] == sub["endpoint"]


@pytest.mark.asyncio
async def test_push_subscribe_requires_endpoint(client, abyss_home):
    resp = await client.post("/chat/push/subscribe", json={"keys": {}})
    assert resp.status == 400


@pytest.mark.asyncio
async def test_push_unsubscribe(client, abyss_home):
    sub = {
        "endpoint": "https://example/push/x",
        "keys": {"p256dh": "p", "auth": "a"},
        "device_id": "phone-1",
    }
    await client.post("/chat/push/subscribe", json=sub)
    resp = await client.request(
        "DELETE",
        "/chat/push/subscribe",
        json={"endpoint": sub["endpoint"]},
    )
    assert resp.status == 200
    from abyss import web_push as web_push_mod

    assert web_push_mod.list_subscriptions() == []


@pytest.mark.asyncio
async def test_push_visibility_marks_device(client, abyss_home):
    from abyss import web_push as web_push_mod

    web_push_mod._visible_devices.clear()

    resp = await client.post(
        "/chat/push/visibility",
        json={"deviceId": "phone-1", "visible": True},
    )
    assert resp.status == 200
    assert web_push_mod.is_device_visible("phone-1") is True

    await client.post(
        "/chat/push/visibility",
        json={"deviceId": "phone-1", "visible": False},
    )
    assert web_push_mod.is_device_visible("phone-1") is False


@pytest.mark.asyncio
async def test_push_visibility_requires_device_id(client, abyss_home):
    resp = await client.post("/chat/push/visibility", json={"visible": True})
    assert resp.status == 400


@pytest.mark.asyncio
async def test_chat_reply_triggers_push(client, abyss_home, patch_backend):
    """A completed chat reply pings ``web_push.send_push`` so subscribed
    devices receive a notification when the user is not actively
    looking at the dashboard."""
    from unittest.mock import AsyncMock
    from unittest.mock import patch as patch_fn

    create = await client.post("/chat/sessions", json={"bot": "alpha"})
    sid = (await create.json())["id"]

    with patch_fn("abyss.chat_server.web_push.send_push", new_callable=AsyncMock) as sender:
        sse = await client.post(
            "/chat",
            json={"bot": "alpha", "session_id": sid, "message": "hello"},
        )
        # Drain the SSE so the post-done push trigger runs.
        async for _ in sse.content.iter_any():
            pass

    sender.assert_awaited_once()
    kwargs = sender.call_args.kwargs
    assert kwargs["bot"] == "alpha"
    assert kwargs["session_id"] == sid
    assert kwargs["title"] == "Alpha"  # bot display_name
    assert "hi there" in kwargs["body"]  # reply preview includes the assistant text


@pytest.mark.asyncio
async def test_slash_reply_does_not_trigger_push(client, abyss_home, patch_backend):
    """Slash commands never invoke the LLM, so they should not page
    the user either — the response is synchronous to the same tab
    that fired it."""
    from unittest.mock import AsyncMock
    from unittest.mock import patch as patch_fn

    create = await client.post("/chat/sessions", json={"bot": "alpha"})
    sid = (await create.json())["id"]

    with patch_fn("abyss.chat_server.web_push.send_push", new_callable=AsyncMock) as sender:
        sse = await client.post(
            "/chat",
            json={"bot": "alpha", "session_id": sid, "message": "/help"},
        )
        async for _ in sse.content.iter_any():
            pass

    sender.assert_not_called()


@pytest.mark.asyncio
async def test_slash_command_logs_to_conversation_markdown(client, abyss_home, patch_backend):
    """Slash command results must persist to ``conversation-*.md`` so
    navigating away from a chat and returning does not silently drop
    the reply. Regular LLM messages get this through
    ``process_chat_message``; the dashboard slash path needs to mirror
    that contract so the message history reload after navigation
    surfaces the result."""

    create = await client.post("/chat/sessions", json={"bot": "alpha"})
    sid = (await create.json())["id"]

    sse = await client.post(
        "/chat",
        json={"bot": "alpha", "session_id": sid, "message": "/help"},
    )
    async for _ in sse.content.iter_any():
        pass

    session_dir = abyss_home / "bots" / "alpha" / "sessions" / sid
    convo_files = list(session_dir.glob("conversation-*.md"))
    assert len(convo_files) == 1
    body = convo_files[0].read_text()
    # User side records the literal slash command exactly as typed.
    assert "## user" in body
    assert "/help" in body
    # Assistant side records the rendered help text — ``/start`` is
    # the first entry in the command catalog and must appear.
    assert "## assistant" in body
    assert "/start" in body


@pytest.mark.asyncio
async def test_routines_endpoint_lists_cron_and_heartbeat(client, abyss_home):
    """``GET /chat/routines`` walks each bot's ``cron_sessions/*`` and
    ``heartbeat_sessions`` directories and returns a flat list with
    ``kind``, ``job_name``, ``preview``, and ``updated_at`` ready to
    render in the mobile Routines tab."""
    bot_dir = abyss_home / "bots" / "alpha"
    cron_dir = bot_dir / "cron_sessions" / "daily-weather"
    cron_dir.mkdir(parents=True)
    (cron_dir / "conversation-260514.md").write_text(
        "## user (2026-05-14 06:00:00 UTC)\n\nGet weather\n\n"
        "## assistant (2026-05-14 06:00:01 UTC)\n\nSunny 22C.\n"
    )
    heartbeat_dir = bot_dir / "heartbeat_sessions"
    heartbeat_dir.mkdir()
    (heartbeat_dir / "conversation-260514.md").write_text(
        "## user (2026-05-14 09:00:00 UTC)\n\nHB\n\n"
        "## assistant (2026-05-14 09:00:01 UTC)\n\nHEARTBEAT_OK\n"
    )

    resp = await client.get("/chat/routines")
    assert resp.status == 200
    body = await resp.json()
    routines = body["routines"]

    kinds = {(r["kind"], r["job_name"]) for r in routines}
    assert ("cron", "daily-weather") in kinds
    assert ("heartbeat", "heartbeat") in kinds

    weather = next(r for r in routines if r["kind"] == "cron" and r["job_name"] == "daily-weather")
    # Preview prefers the assistant reply over the trigger prompt.
    assert "Sunny 22C" in weather["preview"]
    assert weather["bot"] == "alpha"


@pytest.mark.asyncio
async def test_routine_messages_hide_legacy_user_trigger(client, abyss_home):
    """``GET /chat/routines/.../messages`` drops legacy ``## user``
    entries so the noisy cron / heartbeat trigger prompts left in
    older ``conversation-*.md`` files do not surface in the mobile
    Routines transcript. Real keyboard replies land as ``## human``
    and are re-tagged as ``user`` on the way out so the existing
    mobile bubble renderer keeps working.
    """
    cron_dir = abyss_home / "bots" / "alpha" / "cron_sessions" / "morning-brief"
    cron_dir.mkdir(parents=True)
    (cron_dir / "conversation-260514.md").write_text(
        "## user (2026-05-14 06:00:00 UTC)\n\nMorning summary\n\n"
        "## assistant (2026-05-14 06:00:01 UTC)\n\nHere's your brief.\n"
        "## human (2026-05-14 06:01:00 UTC)\n\nThanks!\n"
        "## assistant (2026-05-14 06:01:01 UTC)\n\nAnytime.\n"
    )

    resp = await client.get("/chat/routines/alpha/cron/morning-brief/messages")
    assert resp.status == 200
    body = await resp.json()
    roles = [m["role"] for m in body["messages"]]
    contents = [m["content"].strip() for m in body["messages"]]
    assert roles == ["assistant", "user", "assistant"]
    assert contents == ["Here's your brief.", "Thanks!", "Anytime."]


@pytest.mark.asyncio
async def test_routine_messages_rejects_unknown_kind(client, abyss_home):
    """Path-traversal hardening: ``kind`` is regex-pinned to
    ``cron|heartbeat``. Any other value short-circuits to an empty
    list rather than walking ``bot_dir / <kind>``."""
    resp = await client.get("/chat/routines/alpha/escape/x/messages")
    assert resp.status == 200
    body = await resp.json()
    assert body["messages"] == []
