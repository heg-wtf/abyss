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

MAX_MESSAGE_BYTES = 32 * 1024
SESSION_PREVIEW_CHARS = 80


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


def _parse_conversation_messages(session_dir: Path) -> list[dict[str, str]]:
    files = sorted(session_dir.glob("conversation-*.md"))
    if not files:
        legacy = session_dir / "conversation.md"
        if legacy.exists():
            files = [legacy]
    if not files:
        return []
    messages: list[dict[str, str]] = []
    for path in files:
        try:
            content = path.read_text()
        except OSError:
            continue
        for match in _SECTION_PATTERN.finditer(content):
            role, timestamp, body = match.group(1), match.group(2), match.group(3).strip()
            messages.append({"role": role, "content": body, "timestamp": timestamp.strip()})
    return messages


def _session_metadata(bot_name: str, session_dir: Path) -> dict[str, Any]:
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
        self._app = web.Application(middlewares=[_cors_middleware])
        self._runner: web.AppRunner | None = None
        self._site: web.BaseSite | None = None
        self._locks: dict[str, asyncio.Lock] = {}
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

        sessions = []
        for sid in collect_web_session_ids(bot_path):
            session_dir = bot_path / "sessions" / sid
            sessions.append(_session_metadata(bot_name, session_dir))
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
        messages = _parse_conversation_messages(session_dir)
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

        try:
            _validate_bot_name(bot_name)
            _validate_session_id(session_id)
        except web.HTTPBadRequest as exc:
            return web.json_response({"error": exc.reason}, status=400)

        if not message:
            return web.json_response({"error": "message required"}, status=400)
        if len(message.encode("utf-8")) > MAX_MESSAGE_BYTES:
            return web.json_response({"error": "message too large"}, status=413)

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
                )
            await _sse_write(sse, {"type": "done", "text": full_text})
        except Exception as error:  # noqa: BLE001 — propagate to client cleanly
            logger.error(
                "chat_server: chat failed bot=%s session=%s: %s", bot_name, session_id, error
            )
            with suppress(Exception):
                await _sse_write(sse, {"type": "error", "message": str(error)})
        return sse


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
