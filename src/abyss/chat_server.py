"""Internal HTTP/SSE server for the abysscope dashboard chat.

Runs inside the same asyncio event loop as the Telegram bots (bot_manager).
Bound to ``127.0.0.1:${ABYSS_CHAT_PORT:-3848}`` (loopback only). The Next.js
dashboard at port 3847 proxies requests here.

Sessions are stored under ``~/.abyss/bots/<bot>/sessions/chat_web_<uuid>/``,
fully separate from Telegram chats — there is no sync.

Endpoints
---------
``POST /chat``
    Body: ``{"bot": str, "session_id": str, "message": str}``. Returns
    ``text/event-stream`` with ``chunk``/``done``/``error`` events.

``POST /chat/cancel``
    Body: ``{"bot": str, "session_id": str}``. Cancels the in-flight backend
    call for that session.

``GET /chat/bots``
    Returns ``{"bots": [{"name", "display_name", "type"}, ...]}``.

``GET /chat/sessions?bot=<name>``
    Returns ``{"sessions": [{"id", "bot", "updated_at", "preview"}, ...]}``
    sorted by updated_at desc.

``POST /chat/sessions``
    Body: ``{"bot": str, "title"?: str}``. Creates a new ``chat_web_*`` session.

``DELETE /chat/sessions/<bot>/<session_id>``
    Removes the session directory.

``GET /chat/sessions/<bot>/<session_id>/messages``
    Returns ``{"messages": [{"role", "content", "timestamp"}, ...]}``.

``GET /healthz``
    Always 200.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import uuid
from collections.abc import Callable
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aiohttp import web

from abyss.chat_core import process_chat_message
from abyss.config import abyss_home, bot_directory, load_bot_config, load_config
from abyss.llm import get_or_create
from abyss.session import (
    WEB_SESSION_PREFIX,
    collect_web_session_ids,
)
from abyss.session import (
    session_directory as build_session_directory,
)

logger = logging.getLogger(__name__)

CHAT_SERVER_HOST = "127.0.0.1"
CHAT_SERVER_PORT = int(os.environ.get("ABYSS_CHAT_PORT", "3848"))

ALLOWED_ORIGINS = {
    "http://127.0.0.1:3847",
    "http://localhost:3847",
    # Allow the user to override (e.g. dashboard on a custom port).
    *(
        origin.strip()
        for origin in os.environ.get("ABYSS_CHAT_ALLOWED_ORIGINS", "").split(",")
        if origin.strip()
    ),
}

_BOT_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
_SESSION_ID_PATTERN = re.compile(rf"^{re.escape(WEB_SESSION_PREFIX)}[a-f0-9]{{6,32}}$")
_ATTACHMENT_NAME_PATTERN = re.compile(
    r"^[a-zA-Z0-9_-]{1,16}__[\w가-힣\-]{1,80}\.(png|jpg|jpeg|webp|gif|pdf)$"
)

MAX_MESSAGE_BYTES = 32 * 1024
SESSION_PREVIEW_CHARS = 80

# Attachment limits (see docs/plan-chat-attachments-2026-05-03.md §3)
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_UPLOADS_PER_MESSAGE = 5
MAX_UPLOADS_PER_SESSION = 50

ALLOWED_UPLOAD_MIMES: dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "application/pdf": ".pdf",
}

# Magic byte signatures used to defeat MIME spoofing on upload.
_MAGIC_SIGNATURES: tuple[tuple[str, bytes], ...] = (
    ("image/png", b"\x89PNG\r\n\x1a\n"),
    ("image/jpeg", b"\xff\xd8\xff"),
    ("image/gif", b"GIF87a"),
    ("image/gif", b"GIF89a"),
    ("application/pdf", b"%PDF-"),
)


def _basename_safe(name: str) -> str:
    """Return a sanitized stem suitable for embedding in a stored filename.

    Drops directory parts, keeps Korean letters / ASCII alnum / underscore /
    hyphen, replaces every other rune with ``_``, truncates to 60 chars,
    falls back to ``"file"`` when the result is empty.
    """
    stem = Path(name).stem
    cleaned = re.sub(r"[^A-Za-z0-9_\-가-힣]+", "_", stem).strip("_")
    cleaned = cleaned[:60]
    return cleaned or "file"


def _uploads_dir(session_dir: Path) -> Path:
    target = session_dir / "workspace" / "uploads"
    target.mkdir(parents=True, exist_ok=True)
    return target


def _is_path_under(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _detect_mime(prefix: bytes, declared_mime: str) -> str | None:
    """Confirm a multipart upload's content matches its declared MIME.

    For WebP, the standard magic check needs both the ``RIFF`` prefix and a
    ``WEBP`` marker further into the header.
    """
    if declared_mime == "image/webp":
        if prefix.startswith(b"RIFF") and prefix[8:12] == b"WEBP":
            return "image/webp"
        return None
    for mime, signature in _MAGIC_SIGNATURES:
        if prefix.startswith(signature):
            return mime
    return None


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _origin_allowed(request: web.Request) -> bool:
    origin = request.headers.get("Origin")
    if origin is None:
        # Same-origin / curl with no Origin header — accept on loopback.
        return True
    return origin in ALLOWED_ORIGINS


def _validate_bot_name(name: str) -> str:
    if not _BOT_NAME_PATTERN.match(name):
        raise web.HTTPBadRequest(reason="invalid bot name")
    return name


def _validate_session_id(session_id: str) -> str:
    if not _SESSION_ID_PATTERN.match(session_id):
        raise web.HTTPBadRequest(reason="invalid session id")
    return session_id


def _resolve_session_dir(bot_name: str, session_id: str) -> Path:
    bot_path = bot_directory(_validate_bot_name(bot_name))
    if not bot_path.exists():
        raise web.HTTPNotFound(reason="bot not found")
    session_dir = build_session_directory(bot_path, _validate_session_id(session_id))
    home = abyss_home().resolve()
    try:
        session_dir.resolve().relative_to(home)
    except ValueError as exc:
        raise web.HTTPBadRequest(reason="path traversal") from exc
    return session_dir


# ---------------------------------------------------------------------------
# CORS / preflight middleware
# ---------------------------------------------------------------------------


@web.middleware
async def _cors_middleware(
    request: web.Request, handler: Callable[[web.Request], Any]
) -> web.StreamResponse:
    if request.method == "OPTIONS":
        response = web.Response(status=204)
    else:
        if not _origin_allowed(request):
            return web.json_response({"error": "origin not allowed"}, status=403)
        response = await handler(request)
    origin = request.headers.get("Origin")
    if origin and origin in ALLOWED_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


# ---------------------------------------------------------------------------
# SSE writer
# ---------------------------------------------------------------------------


async def _sse_write(response: web.StreamResponse, event: dict[str, Any]) -> None:
    payload = json.dumps(event, ensure_ascii=False)
    await response.write(f"data: {payload}\n\n".encode())


# ---------------------------------------------------------------------------
# Conversation file parsing (for /messages endpoint)
# ---------------------------------------------------------------------------


_SECTION_PATTERN = re.compile(
    r"##\s+(user|assistant)\s+\(([^)]+)\)\s*\n+(.*?)(?=\n##\s+(?:user|assistant)\s+\(|\Z)",
    re.DOTALL,
)


_ATTACHMENT_LINE_PATTERN = re.compile(
    r"^\[file:\s*(?P<entries>[^\]]+)\]\s*\n?(?P<rest>.*)$",
    re.DOTALL,
)
_ATTACHMENT_ENTRY_PATTERN = re.compile(r"(?P<display>[^,()]+?)\((?P<real>[^,()]+)\)")


def _split_attachment_marker(
    body: str, bot_name: str, session_id: str
) -> tuple[str, list[dict[str, str]]]:
    """Strip a ``[file: a.png(uuid__a.png), ...]`` marker from a user log body.

    Returns ``(text_without_marker, attachments)``. ``attachments`` is empty
    when no marker is present or the marker is malformed.
    """
    match = _ATTACHMENT_LINE_PATTERN.match(body)
    if not match:
        return body, []
    entries = list(_ATTACHMENT_ENTRY_PATTERN.finditer(match.group("entries")))
    if not entries:
        return body, []
    attachments: list[dict[str, str]] = []
    for entry in entries:
        display = entry.group("display").strip()
        real = entry.group("real").strip()
        if not _ATTACHMENT_NAME_PATTERN.match(real):
            continue
        ext = Path(real).suffix.lower()
        mime = next(
            (
                m
                for m, e in ALLOWED_UPLOAD_MIMES.items()
                if e == ext or (ext == ".jpeg" and e == ".jpg")
            ),
            "application/octet-stream",
        )
        attachments.append(
            {
                "display_name": display,
                "real_name": real,
                "mime": mime,
                "url": f"/api/chat/sessions/{bot_name}/{session_id}/file/{real}",
            }
        )
    return match.group("rest").strip(), attachments


def _parse_conversation_messages(
    session_dir: Path, bot_name: str = "", session_id: str = ""
) -> list[dict[str, Any]]:
    files = sorted(session_dir.glob("conversation-*.md"))
    if not files:
        legacy = session_dir / "conversation.md"
        if legacy.exists():
            files = [legacy]
    if not files:
        return []
    messages: list[dict[str, Any]] = []
    for path in files:
        try:
            content = path.read_text()
        except OSError:
            continue
        for match in _SECTION_PATTERN.finditer(content):
            role, timestamp, body = match.group(1), match.group(2), match.group(3).strip()
            entry: dict[str, Any] = {
                "role": role,
                "content": body,
                "timestamp": timestamp.strip(),
            }
            if role == "user":
                stripped, attachments = _split_attachment_marker(body, bot_name, session_id)
                if attachments:
                    entry["content"] = stripped
                    entry["attachments"] = attachments
            messages.append(entry)
    return messages


def _bot_display_name(bot_name: str) -> str:
    cfg = load_bot_config(bot_name) or {}
    return cfg.get("display_name") or bot_name


def _session_metadata(
    bot_name: str,
    session_dir: Path,
    bot_display_name: str | None = None,
) -> dict[str, Any]:
    files = sorted(session_dir.glob("conversation-*.md"))
    if not files:
        legacy = session_dir / "conversation.md"
        if legacy.exists():
            files = [legacy]

    preview = ""
    if files:
        try:
            content = files[-1].read_text()
            sections = list(_SECTION_PATTERN.finditer(content))
            if sections:
                last = sections[-1].group(3).strip()
                preview = last.replace("\n", " ")[:SESSION_PREVIEW_CHARS]
        except OSError:
            pass

    try:
        mtime = session_dir.stat().st_mtime
    except OSError:
        mtime = 0.0

    return {
        "id": session_dir.name,
        "bot": bot_name,
        "bot_display_name": bot_display_name or _bot_display_name(bot_name),
        "updated_at": datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat(),
        "preview": preview,
    }


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------


class ChatServer:
    """aiohttp server hosting the dashboard chat API."""

    def __init__(self, host: str = CHAT_SERVER_HOST, port: int = CHAT_SERVER_PORT) -> None:
        self._host = host
        self._port = port
        # client_max_size guards multipart uploads. Slightly above the per-file
        # 10 MB cap to leave room for multipart envelope overhead; the per-part
        # streaming check enforces the precise limit.
        self._app = web.Application(
            middlewares=[_cors_middleware],
            client_max_size=MAX_UPLOAD_BYTES + 256 * 1024,
        )
        self._runner: web.AppRunner | None = None
        self._site: web.BaseSite | None = None
        self._locks: dict[str, asyncio.Lock] = {}
        # Separate lock keyed by ``bot:session`` for the upload critical
        # section (count → cap check → reserve slot). Without this, two
        # concurrent uploads can both observe a count below the cap and
        # both proceed, exceeding ``MAX_UPLOADS_PER_SESSION``.
        self._upload_locks: dict[str, asyncio.Lock] = {}
        self._register_routes()

    @property
    def port(self) -> int:
        return self._port

    @property
    def host(self) -> str:
        return self._host

    def _register_routes(self) -> None:
        router = self._app.router
        router.add_post("/chat", self._handle_chat)
        router.add_post("/chat/cancel", self._handle_cancel)
        router.add_get("/chat/bots", self._handle_list_bots)
        router.add_get("/chat/sessions", self._handle_list_sessions)
        router.add_post("/chat/sessions", self._handle_create_session)
        router.add_delete("/chat/sessions/{bot}/{session_id}", self._handle_delete_session)
        router.add_get("/chat/sessions/{bot}/{session_id}/messages", self._handle_get_messages)
        router.add_post("/chat/upload", self._handle_upload)
        router.add_get("/chat/sessions/{bot}/{session_id}/file/{name}", self._handle_get_file)
        router.add_get("/healthz", self._handle_health)

    async def start(self) -> None:
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self._host, self._port)
        await self._site.start()
        logger.info("Chat server listening on http://%s:%d", self._host, self._port)

    async def stop(self) -> None:
        if self._runner:
            with suppress(Exception):
                await self._runner.cleanup()
        self._runner = None
        self._site = None

    # ------------------------------------------------------------------
    # Locks
    # ------------------------------------------------------------------

    def _lock_for(self, bot: str, session_id: str) -> asyncio.Lock:
        key = f"{bot}:{session_id}"
        lock = self._locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[key] = lock
        return lock

    def _upload_lock_for(self, bot: str, session_id: str) -> asyncio.Lock:
        key = f"{bot}:{session_id}"
        lock = self._upload_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._upload_locks[key] = lock
        return lock

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    async def _handle_health(self, _request: web.Request) -> web.Response:
        return web.json_response({"status": "ok", "port": self._port})

    async def _handle_list_bots(self, _request: web.Request) -> web.Response:
        config = load_config() or {}
        out: list[dict[str, Any]] = []
        for entry in config.get("bots") or []:
            name = entry.get("name")
            if not name:
                continue
            cfg = load_bot_config(name) or {}
            backend_cfg = cfg.get("backend") or {}
            out.append(
                {
                    "name": name,
                    "display_name": cfg.get("display_name") or name,
                    "type": backend_cfg.get("type", "claude_code"),
                }
            )
        return web.json_response({"bots": out})

    async def _handle_list_sessions(self, request: web.Request) -> web.Response:
        bot_name = request.query.get("bot", "").strip()
        if not bot_name:
            return web.json_response({"error": "bot required"}, status=400)
        _validate_bot_name(bot_name)
        bot_path = bot_directory(bot_name)
        if not bot_path.exists():
            return web.json_response({"error": "bot not found"}, status=404)

        display = _bot_display_name(bot_name)
        sessions = []
        for sid in collect_web_session_ids(bot_path):
            session_dir = bot_path / "sessions" / sid
            sessions.append(_session_metadata(bot_name, session_dir, display))
        sessions.sort(key=lambda s: s["updated_at"], reverse=True)
        return web.json_response({"sessions": sessions})

    async def _handle_create_session(self, request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)
        bot_name = (body.get("bot") or "").strip()
        if not bot_name:
            return web.json_response({"error": "bot required"}, status=400)
        _validate_bot_name(bot_name)
        bot_path = bot_directory(bot_name)
        if not bot_path.exists():
            return web.json_response({"error": "bot not found"}, status=404)

        session_id = f"{WEB_SESSION_PREFIX}{uuid.uuid4().hex[:12]}"
        session_dir = bot_path / "sessions" / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / "workspace").mkdir(exist_ok=True)
        return web.json_response(
            {
                "id": session_id,
                "bot": bot_name,
                "bot_display_name": _bot_display_name(bot_name),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "preview": "",
            }
        )

    async def _handle_delete_session(self, request: web.Request) -> web.Response:
        bot_name = request.match_info["bot"]
        session_id = request.match_info["session_id"]
        session_dir = _resolve_session_dir(bot_name, session_id)
        if not session_dir.exists():
            return web.json_response({"error": "session not found"}, status=404)
        with suppress(Exception):
            shutil.rmtree(session_dir)
        return web.json_response({"deleted": True})

    async def _handle_get_messages(self, request: web.Request) -> web.Response:
        bot_name = request.match_info["bot"]
        session_id = request.match_info["session_id"]
        session_dir = _resolve_session_dir(bot_name, session_id)
        if not session_dir.exists():
            return web.json_response({"messages": []})
        messages = _parse_conversation_messages(session_dir, bot_name, session_id)
        return web.json_response({"messages": messages})

    async def _handle_cancel(self, request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)
        bot_name = (body.get("bot") or "").strip()
        session_id = (body.get("session_id") or "").strip()
        _validate_bot_name(bot_name)
        _validate_session_id(session_id)
        bot_config = load_bot_config(bot_name)
        if bot_config is None:
            return web.json_response({"error": "bot not found"}, status=404)
        backend = get_or_create(bot_name, bot_config)
        ok = await backend.cancel(f"{bot_name}:{session_id}")
        return web.json_response({"cancelled": bool(ok)})

    async def _handle_chat(self, request: web.Request) -> web.StreamResponse:
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)

        bot_name = (body.get("bot") or "").strip()
        session_id = (body.get("session_id") or "").strip()
        message = (body.get("message") or "").strip()
        raw_attachments = body.get("attachments") or []

        try:
            _validate_bot_name(bot_name)
            _validate_session_id(session_id)
        except web.HTTPBadRequest as exc:
            return web.json_response({"error": exc.reason}, status=400)

        if len(message.encode("utf-8")) > MAX_MESSAGE_BYTES:
            return web.json_response({"error": "message too large"}, status=413)

        if not isinstance(raw_attachments, list):
            return web.json_response({"error": "attachments must be a list"}, status=400)
        if len(raw_attachments) > MAX_UPLOADS_PER_MESSAGE:
            return web.json_response({"error": "too_many_uploads_in_message"}, status=400)
        if not message and not raw_attachments:
            return web.json_response({"error": "message required"}, status=400)

        bot_config = load_bot_config(bot_name)
        if bot_config is None:
            return web.json_response({"error": "bot not found"}, status=404)

        bot_path = bot_directory(bot_name)
        if not bot_path.exists():
            return web.json_response({"error": "bot path missing"}, status=404)

        # Ensure session directory exists (may be a brand-new chat)
        session_dir = bot_path / "sessions" / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / "workspace").mkdir(exist_ok=True)

        try:
            attachment_paths = self._resolve_attachments(session_dir, raw_attachments)
        except web.HTTPException as exc:
            return web.json_response({"error": exc.reason}, status=exc.status)

        sse = web.StreamResponse(
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            }
        )
        await sse.prepare(request)

        async def on_chunk(chunk: str) -> None:
            with suppress(Exception):
                await _sse_write(sse, {"type": "chunk", "text": chunk})

        lock = self._lock_for(bot_name, session_id)
        full_text = ""
        try:
            async with lock:
                full_text = await process_chat_message(
                    bot_name=bot_name,
                    bot_path=bot_path,
                    bot_config=bot_config,
                    chat_id=session_id,
                    user_message=message,
                    on_chunk=on_chunk,
                    session_key=f"{bot_name}:{session_id}",
                    attachments=attachment_paths,
                )
            await _sse_write(sse, {"type": "done", "text": full_text})
        except Exception as error:  # noqa: BLE001 — propagate to client cleanly
            logger.error(
                "chat_server: chat failed bot=%s session=%s: %s", bot_name, session_id, error
            )
            with suppress(Exception):
                await _sse_write(sse, {"type": "error", "message": str(error)})
        return sse

    # ------------------------------------------------------------------
    # Attachments
    # ------------------------------------------------------------------

    def _resolve_attachments(self, session_dir: Path, raw: list[Any]) -> tuple[Path, ...]:
        """Validate ``attachments`` JSON array and return absolute Paths.

        Each element must be a relative ``"uploads/<filename>"`` string
        produced by ``POST /chat/upload``. Anything else — wrong type,
        path traversal, missing file — raises ``web.HTTPBadRequest`` /
        ``web.HTTPNotFound`` with a stable reason code.
        """
        uploads_root = _uploads_dir(session_dir)
        resolved: list[Path] = []
        for item in raw:
            if not isinstance(item, str):
                raise web.HTTPBadRequest(reason="invalid_attachment_entry")
            if not item.startswith("uploads/"):
                raise web.HTTPBadRequest(reason="invalid_attachment_path")
            name = item[len("uploads/") :]
            if not _ATTACHMENT_NAME_PATTERN.match(name):
                raise web.HTTPBadRequest(reason="invalid_attachment_name")
            candidate = (uploads_root / name).resolve()
            if not _is_path_under(candidate, uploads_root):
                raise web.HTTPBadRequest(reason="path_traversal")
            if not candidate.is_file():
                raise web.HTTPNotFound(reason="attachment_missing")
            resolved.append(candidate)
        return tuple(resolved)

    async def _handle_upload(self, request: web.Request) -> web.Response:
        """Accept a single multipart-uploaded file and return its stored path.

        Form fields: ``bot``, ``session_id``, ``file``.
        Enforces MIME whitelist + magic byte sniff + ``MAX_UPLOAD_BYTES``
        + per-session count cap (``MAX_UPLOADS_PER_SESSION``).
        """
        try:
            reader = await request.multipart()
        except Exception:
            return web.json_response({"error": "invalid_multipart"}, status=400)

        bot_name = ""
        session_id = ""
        file_part = None

        async for part in reader:
            if part.name == "bot":
                bot_name = (await part.text()).strip()
            elif part.name == "session_id":
                session_id = (await part.text()).strip()
            elif part.name == "file":
                file_part = part
                break  # leave file streaming for the body below

        try:
            _validate_bot_name(bot_name)
            _validate_session_id(session_id)
        except web.HTTPBadRequest as exc:
            return web.json_response({"error": exc.reason}, status=400)

        if file_part is None:
            return web.json_response({"error": "file_field_missing"}, status=400)

        bot_path = bot_directory(bot_name)
        if not bot_path.exists():
            return web.json_response({"error": "bot not found"}, status=404)
        session_dir = bot_path / "sessions" / session_id
        if not session_dir.exists():
            return web.json_response({"error": "session not found"}, status=404)

        declared_mime = (file_part.headers.get("Content-Type") or "").split(";")[0].strip()
        if declared_mime not in ALLOWED_UPLOAD_MIMES:
            return web.json_response({"error": "invalid_mime"}, status=400)

        uploads_root = _uploads_dir(session_dir)
        original_name = file_part.filename or f"file{ALLOWED_UPLOAD_MIMES[declared_mime]}"
        safe_stem = _basename_safe(original_name)
        ext = ALLOWED_UPLOAD_MIMES[declared_mime]
        stored_name = f"{uuid.uuid4().hex[:8]}__{safe_stem}{ext}"
        stored_path = uploads_root / stored_name

        # Reserve a slot atomically: count the existing files, check the cap,
        # and create the destination as a 0-byte placeholder — all under the
        # per-session upload lock. Without this, two concurrent uploads can
        # both observe ``count < cap`` and exceed ``MAX_UPLOADS_PER_SESSION``.
        async with self._upload_lock_for(bot_name, session_id):
            existing = sum(1 for _ in uploads_root.iterdir())
            if existing >= MAX_UPLOADS_PER_SESSION:
                return web.json_response({"error": "too_many_uploads"}, status=429)
            try:
                stored_path.touch(exist_ok=False)
            except FileExistsError:
                # Astronomical odds, but salvage with a fresh suffix.
                stored_name = f"{uuid.uuid4().hex[:8]}__{safe_stem}{ext}"
                stored_path = uploads_root / stored_name
                stored_path.touch(exist_ok=False)

        # Stream the file to disk while enforcing the size cap. Defer magic
        # byte verification until we have the first 16 bytes.
        size = 0
        magic_buffer = b""
        magic_verified = False
        try:
            with stored_path.open("wb") as out:
                while True:
                    chunk = await file_part.read_chunk(64 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > MAX_UPLOAD_BYTES:
                        raise web.HTTPRequestEntityTooLarge(
                            max_size=MAX_UPLOAD_BYTES, actual_size=size
                        )
                    if not magic_verified:
                        magic_buffer += chunk
                        if len(magic_buffer) >= 12:
                            detected = _detect_mime(magic_buffer[:16], declared_mime)
                            if detected != declared_mime:
                                raise web.HTTPBadRequest(reason="mime_mismatch")
                            magic_verified = True
                    out.write(chunk)
            if not magic_verified:
                # File ended before we collected enough bytes for sniffing.
                detected = _detect_mime(magic_buffer[:16], declared_mime)
                if detected != declared_mime:
                    raise web.HTTPBadRequest(reason="mime_mismatch")
        except web.HTTPException:
            with suppress(FileNotFoundError):
                stored_path.unlink()
            raise
        except Exception as error:
            logger.exception("upload failed for bot=%s session=%s", bot_name, session_id)
            with suppress(FileNotFoundError):
                stored_path.unlink()
            return web.json_response({"error": "upload_failed", "detail": str(error)}, status=500)

        return web.json_response(
            {
                "path": f"uploads/{stored_name}",
                "display_name": original_name,
                "mime": declared_mime,
                "size": size,
            }
        )

    async def _handle_get_file(self, request: web.Request) -> web.StreamResponse:
        """Serve a previously uploaded file inline.

        Path traversal and content-type spoofing are blocked by validating
        the filename against ``_ATTACHMENT_NAME_PATTERN`` and pinning the
        response Content-Type to the upload's MIME mapping.
        """
        bot_name = request.match_info["bot"]
        session_id = request.match_info["session_id"]
        name = request.match_info["name"]

        try:
            _validate_bot_name(bot_name)
            _validate_session_id(session_id)
        except web.HTTPBadRequest as exc:
            return web.json_response({"error": exc.reason}, status=400)

        if not _ATTACHMENT_NAME_PATTERN.match(name):
            return web.json_response({"error": "invalid_attachment_name"}, status=400)

        bot_path = bot_directory(bot_name)
        if not bot_path.exists():
            return web.json_response({"error": "bot not found"}, status=404)
        session_dir = bot_path / "sessions" / session_id
        if not session_dir.exists():
            return web.json_response({"error": "session not found"}, status=404)
        uploads_root = _uploads_dir(session_dir)
        candidate = (uploads_root / name).resolve()
        if not _is_path_under(candidate, uploads_root) or not candidate.is_file():
            return web.json_response({"error": "attachment_missing"}, status=404)

        ext = candidate.suffix.lower()
        mime = next(
            (
                m
                for m, e in ALLOWED_UPLOAD_MIMES.items()
                if e == ext or (ext == ".jpeg" and e == ".jpg")
            ),
            "application/octet-stream",
        )
        headers = {
            "Content-Type": mime,
            "Cache-Control": "private, max-age=300",
            "X-Content-Type-Options": "nosniff",
        }
        if mime == "application/pdf":
            headers["Content-Disposition"] = f'inline; filename="{candidate.name}"'
        return web.FileResponse(candidate, headers=headers)


# ---------------------------------------------------------------------------
# Module-level singleton (used by bot_manager)
# ---------------------------------------------------------------------------


_server: ChatServer | None = None


def get_server() -> ChatServer:
    global _server
    if _server is None:
        _server = ChatServer()
    return _server


async def reset_server_for_testing() -> None:
    """Reset module-level singleton — tests only."""
    global _server
    if _server is not None:
        await _server.stop()
    _server = None
