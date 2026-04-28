"""Internal HTTP/SSE server for dashboard chat.

Runs on localhost:3849 (ABYSS_CHAT_PORT) inside the same asyncio event loop
as the Telegram bots. The Abysscope Next.js dashboard proxies to this server
for real-time chat with bots.

Endpoints:
  POST /bots/{name}/chat    — send a message, returns SSE stream of chunks
  GET  /bots/{name}/stream  — persistent SSE subscription for all events
  GET  /bots/{name}/history — recent conversation history (JSON)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aiohttp import web

logger = logging.getLogger(__name__)

CHAT_SERVER_HOST = "127.0.0.1"
CHAT_SERVER_PORT = int(os.environ.get("ABYSS_CHAT_PORT", "3849"))

_DASHBOARD_SESSION_NAME = "chat_dashboard"


class ChatEventBus:
    """Per-bot event bus delivering real-time messages to SSE subscribers."""

    def __init__(self) -> None:
        self._queues: dict[str, list[asyncio.Queue[dict]]] = {}

    def subscribe(self, bot_name: str) -> asyncio.Queue[dict]:
        queue: asyncio.Queue[dict] = asyncio.Queue()
        self._queues.setdefault(bot_name, []).append(queue)
        return queue

    def unsubscribe(self, bot_name: str, queue: asyncio.Queue[dict]) -> None:
        bucket = self._queues.get(bot_name)
        if bucket:
            with suppress(ValueError):
                bucket.remove(queue)

    async def publish(self, bot_name: str, event: dict) -> None:
        for queue in list(self._queues.get(bot_name, [])):
            with suppress(Exception):
                queue.put_nowait(event)


# Module-level singletons imported by bot_manager and handlers
event_bus = ChatEventBus()


def _make_event(role: str, content: str, source: str) -> dict:
    return {
        "type": "message",
        "role": role,
        "content": content,
        "source": source,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


class ChatServer:
    """aiohttp HTTP server managing dashboard chat for all running bots."""

    def __init__(self) -> None:
        self._bots: dict[str, tuple[Path, dict[str, Any], Any]] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._app = web.Application()
        self._runner: web.AppRunner | None = None
        self._app.router.add_post("/bots/{name}/chat", self._handle_chat)
        self._app.router.add_get("/bots/{name}/stream", self._handle_stream)
        self._app.router.add_get("/bots/{name}/history", self._handle_history)

    def register_bot(
        self,
        name: str,
        bot_path: Path,
        bot_config: dict[str, Any],
        application: Any,
    ) -> None:
        self._bots[name] = (bot_path, bot_config, application)
        self._locks[name] = asyncio.Lock()

    async def start(self) -> None:
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, CHAT_SERVER_HOST, CHAT_SERVER_PORT)
        await site.start()
        logger.info("Chat server started on %s:%d", CHAT_SERVER_HOST, CHAT_SERVER_PORT)

    async def stop(self) -> None:
        if self._runner:
            with suppress(Exception):
                await self._runner.cleanup()

    # ------------------------------------------------------------------
    # Route handlers
    # ------------------------------------------------------------------

    async def _handle_chat(self, request: web.Request) -> web.StreamResponse:
        name = request.match_info["name"]
        if name not in self._bots:
            return web.json_response({"error": "Bot not found"}, status=404)

        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON"}, status=400)

        user_message = (body.get("message") or "").strip()
        if not user_message:
            return web.json_response({"error": "message required"}, status=400)

        bot_path, _cached_config, application = self._bots[name]
        # Reload from disk so primary_chat_id set after registration is visible
        from abyss.config import load_bot_config

        bot_config = load_bot_config(name) or _cached_config

        response = web.StreamResponse(
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Access-Control-Allow-Origin": "*",
            }
        )
        await response.prepare(request)

        lock = self._locks[name]
        async with lock:
            full_response = await self._run_chat(
                name=name,
                bot_path=bot_path,
                bot_config=bot_config,
                application=application,
                user_message=user_message,
                sse_response=response,
            )

        await _sse_write(response, {"type": "done", "content": full_response})
        return response

    async def _handle_stream(self, request: web.Request) -> web.StreamResponse:
        name = request.match_info["name"]
        if name not in self._bots:
            return web.json_response({"error": "Bot not found"}, status=404)

        response = web.StreamResponse(
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Access-Control-Allow-Origin": "*",
            }
        )
        await response.prepare(request)

        queue = event_bus.subscribe(name)
        try:
            while True:
                if request.transport and request.transport.is_closing():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=25.0)
                    await _sse_write(response, event)
                except asyncio.TimeoutError:
                    # Keepalive ping so proxy doesn't close the connection
                    await response.write(b": ping\n\n")
        except ConnectionResetError:
            # expected when browser closes the tab or connection
            pass
        except Exception:
            logger.debug("SSE stream error for bot %s", name, exc_info=True)
        finally:
            event_bus.unsubscribe(name, queue)

        return response

    async def _handle_history(self, request: web.Request) -> web.Response:
        name = request.match_info["name"]
        if name not in self._bots:
            return web.json_response({"error": "Bot not found"}, status=404)

        bot_path, bot_config, _ = self._bots[name]
        session_dir = _resolve_session_directory(bot_path, bot_config)

        from abyss.session import load_conversation_history

        history = load_conversation_history(session_dir)
        return web.json_response({"history": history or ""})

    # ------------------------------------------------------------------
    # Core chat logic
    # ------------------------------------------------------------------

    async def _run_chat(
        self,
        name: str,
        bot_path: Path,
        bot_config: dict[str, Any],
        application: Any,
        user_message: str,
        sse_response: web.StreamResponse,
    ) -> str:
        from abyss.llm import get_or_create
        from abyss.llm.base import make_request
        from abyss.session import (
            get_claude_session_id,
            log_conversation,
            save_claude_session_id,
        )

        session_dir = _resolve_session_directory(bot_path, bot_config)
        session_dir.mkdir(parents=True, exist_ok=True)

        lock_key = f"{name}:dashboard"

        log_conversation(session_dir, "user", user_message)
        # Dashboard-origin messages are rendered locally; only broadcast Telegram events

        # Sync user message to Telegram
        primary_chat_id = bot_config.get("primary_chat_id")
        if primary_chat_id and application:
            with suppress(Exception):
                await application.bot.send_message(
                    chat_id=int(primary_chat_id),
                    text=f"[Dashboard] {user_message}",
                )

        claude_session_id = get_claude_session_id(session_dir)
        resume_session = bool(claude_session_id)

        accumulated_chunks: list[str] = []

        async def on_chunk(chunk: str) -> None:
            accumulated_chunks.append(chunk)
            with suppress(Exception):
                await _sse_write(sse_response, {"type": "chunk", "content": chunk})

        try:
            backend = get_or_create(name, bot_config)
            req = make_request(
                bot_name=name,
                bot_path=bot_path,
                session_directory=session_dir,
                working_directory=str(session_dir),
                bot_config=bot_config,
                user_prompt=user_message,
                session_key=lock_key,
                claude_session_id=claude_session_id,
                resume_session=resume_session,
            )
            result = await backend.run_streaming(req, on_chunk)
            full_response = result.text

            if result.session_id:
                save_claude_session_id(session_dir, result.session_id)

        except Exception as error:
            logger.error("Dashboard chat error for bot %s: %s", name, error)
            full_response = f"Error: {error}"
            with suppress(Exception):
                await _sse_write(sse_response, {"type": "chunk", "content": full_response})

        log_conversation(session_dir, "assistant", full_response)
        # Dashboard-origin responses are rendered via the POST SSE stream, not event bus

        # Sync bot response to Telegram
        if primary_chat_id and application:
            with suppress(Exception):
                from abyss.utils import markdown_to_telegram_html, split_message

                html = markdown_to_telegram_html(full_response)
                for chunk in split_message(html):
                    try:
                        await application.bot.send_message(
                            chat_id=int(primary_chat_id),
                            text=chunk,
                            parse_mode="HTML",
                        )
                    except Exception:
                        await application.bot.send_message(
                            chat_id=int(primary_chat_id),
                            text=chunk,
                        )

        return full_response


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _resolve_session_directory(bot_path: Path, bot_config: dict[str, Any]) -> Path:
    """Return the session directory for dashboard chat.

    Uses the primary_chat_id Telegram session when available so the
    dashboard shares conversation history with the Telegram DM.
    Falls back to a dedicated 'chat_dashboard' session.
    """
    primary_chat_id = bot_config.get("primary_chat_id")
    if primary_chat_id:
        from abyss.session import session_directory

        return session_directory(bot_path, int(primary_chat_id))

    dashboard_dir = bot_path / "sessions" / _DASHBOARD_SESSION_NAME
    dashboard_dir.mkdir(parents=True, exist_ok=True)
    return dashboard_dir


async def _sse_write(response: web.StreamResponse, event: dict) -> None:
    data = json.dumps(event, ensure_ascii=False)
    await response.write(f"data: {data}\n\n".encode())


# ------------------------------------------------------------------
# Module-level server instance
# ------------------------------------------------------------------

_server: ChatServer | None = None


def get_server() -> ChatServer:
    global _server
    if _server is None:
        _server = ChatServer()
    return _server
