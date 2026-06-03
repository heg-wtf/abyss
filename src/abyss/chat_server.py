"""Internal HTTP/SSE server for the abysscope dashboard + mobile PWA.

Runs inside the same asyncio event loop as the per-bot cron / heartbeat
schedulers (see ``bot_manager.run_bots``). Bound to
``127.0.0.1:${ABYSS_CHAT_PORT:-3848}`` (loopback only). The Next.js
dashboard at port 3847 proxies requests here.

Sessions are stored under ``~/.abyss/bots/<bot>/sessions/chat_web_<uuid>/``;
each chat owns its own directory + Claude session id.

Endpoints
---------
``POST /chat``
    Body: ``{"bot": str, "session_id": str, "message": str}``. Returns
    ``text/event-stream`` with ``chunk``/``done``/``error`` events.
    Messages starting with ``/`` are routed through ``abyss.commands``
    instead of the LLM and emit a single ``command_result`` SSE event
    followed by ``done`` — see ``/chat/commands`` for the catalog.

``POST /chat/cancel``
    Body: ``{"bot": str, "session_id": str}``. Cancels the in-flight backend
    call for that session.

``GET /chat/bots``
    Returns ``{"bots": [{"name", "display_name", "type"}, ...]}``.

``GET /chat/commands``
    Returns ``{"commands": [{"name", "description", "usage"}, ...]}``
    — the slash-command catalog for autocomplete UIs.

``GET /chat/sessions?bot=<name>``
    Returns ``{"sessions": [{"id", "bot", "updated_at", "preview"}, ...]}``
    sorted by updated_at desc.

``POST /chat/sessions``
    Body: ``{"bot": str, "title"?: str}``. Creates a new ``chat_web_*`` session.

``DELETE /chat/sessions/<bot>/<session_id>``
    Removes the session directory.

``POST /chat/sessions/<bot>/<session_id>/rename``
    Body: ``{"name": str}``. Stores a user-facing name in
    ``<session_dir>/.session_meta.json``. Empty name clears the field.

``GET /chat/sessions/<bot>/<session_id>/messages``
    Returns ``{"messages": [{"role", "content", "timestamp"}, ...]}``.

``POST /chat/transcribe``
    Body: multipart/form-data with ``audio`` field (webm/ogg/wav, max 10 MB).
    Returns ``{"text": "..."}`` — empty string when audio is silence/noise.

``POST /chat/speak``
    Body: ``{"text": str, "voice_id"?: str}``. Streams ``audio/mpeg`` MP3.

``GET /chat/push/vapid-key``
    Returns the server's VAPID public key so the browser can call
    ``pushManager.subscribe``. The key is generated and cached at
    ``~/.abyss/vapid-keys.json`` on first use.

``POST /chat/push/subscribe``
    Body: ``PushSubscription.toJSON() + {"device_id": str}``. Upserts
    the subscription by endpoint.

``DELETE /chat/push/subscribe``
    Body: ``{"endpoint": str}``. Removes the subscription.

``POST /chat/push/visibility``
    Body: ``{"deviceId": str, "visible": bool}``. Marks a device's
    dashboard tab as active / inactive so push deliveries can skip it.
    TTL ~60s — a stale visibility ping does not silently block
    notifications.

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
import time
import uuid
from collections.abc import Callable
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiohttp
from aiohttp import web

from abyss import commands, web_push
from abyss.chat_core import process_chat_message
from abyss.claude_runner import (
    cancel_process,
    cancel_sdk_session,
    is_process_running,
)
from abyss.config import (
    abyss_home,
    bot_directory,
    get_elevenlabs_api_key,
    load_bot_config,
    load_config,
)
from abyss.llm import cached_backend, get_or_create
from abyss.session import (
    WEB_SESSION_PREFIX,
    collect_web_session_ids,
    log_conversation,
)
from abyss.session import (
    session_directory as build_session_directory,
)

logger = logging.getLogger(__name__)

CHAT_SERVER_HOST = "127.0.0.1"
CHAT_SERVER_PORT = int(os.environ.get("ABYSS_CHAT_PORT", "3848"))

ELEVENLABS_API_KEY = get_elevenlabs_api_key()
ELEVENLABS_STT_URL = "https://api.elevenlabs.io/v1/speech-to-text"
# ``/stream`` returns progressive SSE chunks so we can pipe bytes to
# the browser the moment ElevenLabs starts generating them — first
# audible byte drops from ~1s to ~150–250ms compared to the basic
# non-streaming endpoint. See
# https://elevenlabs.io/docs/eleven-api/guides/how-to/best-practices/latency-optimization
ELEVENLABS_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"
ELEVENLABS_DEFAULT_VOICE_ID = "8jHHF8rMqMlg8if2mOUe"
# Flash v2.5 ~75 ms inference, full multilingual support (32 langs
# incl. Korean). The previous ``eleven_multilingual_v2`` was the
# quality-tier model with 5–10× the latency, which dominated the
# total speak() time in voice mode.
ELEVENLABS_TTS_MODEL = "eleven_flash_v2_5"
ELEVENLABS_STT_MODEL = "scribe_v2"

MAX_AUDIO_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_TTS_TEXT_LENGTH = 5_000
MIN_STT_LANGUAGE_PROBABILITY = 0.5

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
# Cron job names land on disk as folder names under
# ``cron_sessions/``. The cron loader sanitises them, but we still
# guard the API path so a stray symlink or hand-edited folder cannot
# escape into another part of ``~/.abyss``.
_ROUTINE_JOB_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
_ROUTINE_KIND_PATTERN = re.compile(r"^(cron|heartbeat)$")
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
    r"##\s+(user|assistant|human)\s+\(([^)]+)\)\s*\n+(.*?)(?=\n##\s+(?:user|assistant|human)\s+\(|\Z)",
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
    """Resolve a bot's user-facing label. Priority: ``display_name`` → slug."""
    cfg = load_bot_config(bot_name) or {}
    return cfg.get("display_name") or bot_name


def _bot_alias(bot_name: str) -> str | None:
    """Resolve a bot's optional alias (role / job label).

    Returns ``None`` when the bot has no alias configured or the
    stored value is empty/whitespace-only. The UI uses this to render
    ``"<display_name> (<alias>)"`` everywhere except the chat message
    bubble + push notification title — those keep the bare display
    name to avoid label noise / iOS truncation.
    """
    cfg = load_bot_config(bot_name) or {}
    raw = cfg.get("alias")
    if not isinstance(raw, str):
        return None
    cleaned = raw.strip()
    return cleaned or None


# ---------------------------------------------------------------------------
# Per-session user metadata (custom name, …)
# ---------------------------------------------------------------------------

_SESSION_META_FILENAME = ".session_meta.json"
MAX_CUSTOM_NAME_LENGTH = 64
MAX_BOT_ALIAS_LENGTH = 30


def _sanitise_bot_alias(raw: str) -> str:
    """Trim + cap + strip control chars from a bot alias.

    Empty result means "remove the alias". Caller decides whether to
    delete the field or reject the request.
    """
    cleaned = "".join(ch for ch in raw if ch == " " or ch.isprintable())
    cleaned = cleaned.strip()
    if len(cleaned) > MAX_BOT_ALIAS_LENGTH:
        cleaned = cleaned[:MAX_BOT_ALIAS_LENGTH].rstrip()
    return cleaned


def _session_meta_path(session_dir: Path) -> Path:
    return session_dir / _SESSION_META_FILENAME


def _load_session_meta(session_dir: Path) -> dict[str, Any]:
    """Read the user-controlled per-session metadata.

    Currently only stores ``custom_name``; the file is small and lives
    inside the session directory so deleting the session also removes
    the name automatically.
    """
    meta_path = _session_meta_path(session_dir)
    if not meta_path.exists():
        return {}
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_session_meta(session_dir: Path, meta: dict[str, Any]) -> None:
    """Persist user metadata atomically (write tmp + rename)."""
    meta_path = _session_meta_path(session_dir)
    tmp = meta_path.with_suffix(".json.tmp")
    payload = json.dumps(meta, ensure_ascii=False, indent=2)
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(meta_path)


def _sanitise_custom_name(raw: str) -> str:
    """Trim whitespace + strip control characters; cap length.

    Empty result means "remove the custom name". The caller decides
    whether to delete the field or reject the request.
    """
    cleaned = "".join(ch for ch in raw if ch == " " or ch.isprintable())
    cleaned = cleaned.strip()
    if len(cleaned) > MAX_CUSTOM_NAME_LENGTH:
        cleaned = cleaned[:MAX_CUSTOM_NAME_LENGTH].rstrip()
    return cleaned


def _routine_metadata(
    *,
    bot_name: str,
    bot_display_name: str,
    kind: str,
    job_name: str,
    session_dir: Path,
) -> dict[str, Any]:
    """Build the JSON entry for a single routine (cron job / heartbeat).

    The shape intentionally overlaps with ``_session_metadata`` so the
    mobile Routines tab can use the same row component as Chats — the
    only extra fields are ``kind`` (``"cron"`` / ``"heartbeat"``) and
    ``job_name`` for the detail-page URL.
    """
    files = sorted(session_dir.glob("conversation-*.md"))
    preview = ""
    if files:
        try:
            content = files[-1].read_text()
            sections = list(_SECTION_PATTERN.finditer(content))
            if sections:
                # Assistant reply is what the user wants to see in the
                # list preview — for cron / heartbeat that's the
                # actual run output.
                last_assistant = next(
                    (m for m in reversed(sections) if m.group(1) == "assistant"),
                    sections[-1],
                )
                preview = last_assistant.group(3).strip().replace("\n", " ")[:SESSION_PREVIEW_CHARS]
        except OSError:
            pass

    # ``mtime`` of the session dir tracks the last run regardless of
    # whether a conversation file was written (e.g. older cron runs
    # that pre-date the markdown logging). For heartbeat we prefer the
    # newest conversation file's mtime because the directory itself
    # may have been created at install time.
    try:
        if files:
            mtime = max(f.stat().st_mtime for f in files)
        else:
            mtime = session_dir.stat().st_mtime
    except OSError:
        mtime = 0.0

    meta = _load_session_meta(session_dir)
    updated_at = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
    last_read_at = meta.get("last_read_at") or None
    return {
        "bot": bot_name,
        "bot_display_name": bot_display_name,
        "bot_alias": _bot_alias(bot_name),
        "kind": kind,
        "job_name": job_name,
        "updated_at": updated_at,
        "preview": preview,
        "last_read_at": last_read_at,
        "unread": _is_unread(updated_at, last_read_at),
    }


def _is_unread(updated_at: str, last_read_at: str | None) -> bool:
    """Return True iff the session has activity newer than the last read mark.

    ``last_read_at`` absent → ``False``: existing sessions (which
    never had a read mark) stay quiet at upgrade time. New activity
    after a mark flips this to True only when ``updated_at`` strictly
    exceeds ``last_read_at`` — strict ``>`` so the marker stamped at
    mount time does not loop into an immediate re-unread when the
    next list fetch arrives in the same second.
    """
    if not last_read_at:
        return False
    return updated_at > last_read_at


def _resolve_routine_dir(bot_name: str, kind: str, job_name: str) -> Path | None:
    """Resolve a ``(bot, kind, job)`` triple to a routine session dir.

    Returns ``None`` if any input fails validation, the bot is unknown,
    or the routine kind is not one we serve. Defensive against path
    traversal: every segment is regex-validated before joining.
    """
    if not _BOT_NAME_PATTERN.match(bot_name):
        return None
    if not _ROUTINE_KIND_PATTERN.match(kind):
        return None
    if not _ROUTINE_JOB_PATTERN.match(job_name):
        return None
    bot_path = bot_directory(bot_name)
    if not bot_path.exists():
        return None
    if kind == "cron":
        return bot_path / "cron_sessions" / job_name
    # ``heartbeat`` has a single, per-bot directory regardless of the
    # ``job_name`` slug — we still validated the slug above so a
    # mistyped URL doesn't escape the bot's directory.
    return bot_path / "heartbeat_sessions"


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

    # Prefer conversation-file mtimes over the session-dir mtime so
    # writes to ``.session_meta.json`` (e.g. mark-read) don't get
    # interpreted as "new activity" and immediately re-flip the
    # session back to unread.
    try:
        if files:
            mtime = max(f.stat().st_mtime for f in files)
        else:
            mtime = session_dir.stat().st_mtime
    except OSError:
        mtime = 0.0

    meta = _load_session_meta(session_dir)
    updated_at = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
    last_read_at = meta.get("last_read_at") or None
    return {
        "id": session_dir.name,
        "bot": bot_name,
        "bot_display_name": bot_display_name or _bot_display_name(bot_name),
        "bot_alias": _bot_alias(bot_name),
        "updated_at": updated_at,
        "preview": preview,
        "custom_name": meta.get("custom_name") or None,
        "last_read_at": last_read_at,
        "unread": _is_unread(updated_at, last_read_at),
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
        self._http_session: aiohttp.ClientSession | None = None
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
        router.add_post("/chat/bots", self._handle_create_bot)
        router.add_get("/chat/commands", self._handle_list_commands)
        router.add_get("/chat/sessions", self._handle_list_sessions)
        router.add_post("/chat/sessions", self._handle_create_session)
        router.add_delete("/chat/sessions/{bot}/{session_id}", self._handle_delete_session)
        router.add_post(
            "/chat/sessions/{bot}/{session_id}/rename",
            self._handle_rename_session,
        )
        router.add_get("/chat/sessions/{bot}/{session_id}/messages", self._handle_get_messages)
        router.add_post(
            "/chat/sessions/{bot}/{session_id}/read",
            self._handle_mark_session_read,
        )
        router.add_post(
            "/chat/sessions/{bot}/{session_id}/feedback",
            self._handle_log_feedback,
        )
        router.add_get("/chat/routines", self._handle_list_routines)
        router.add_get(
            "/chat/routines/{bot}/{kind}/{job}/messages",
            self._handle_get_routine_messages,
        )
        router.add_post(
            "/chat/routines/{bot}/{kind}/{job}/chat",
            self._handle_routine_chat,
        )
        router.add_post(
            "/chat/routines/{bot}/{kind}/{job}/read",
            self._handle_mark_routine_read,
        )
        router.add_post("/chat/upload", self._handle_upload)
        router.add_get("/chat/sessions/{bot}/{session_id}/file/{name}", self._handle_get_file)
        router.add_post("/chat/transcribe", self._handle_transcribe)
        router.add_post("/chat/speak", self._handle_speak)
        router.add_post("/chat/scribe-token", self._handle_scribe_token)
        router.add_post("/chat/log-stt", self._handle_log_stt)
        router.add_get("/chat/push/vapid-key", self._handle_push_vapid_key)
        router.add_post("/chat/push/subscribe", self._handle_push_subscribe)
        router.add_delete("/chat/push/subscribe", self._handle_push_unsubscribe)
        router.add_post("/chat/push/visibility", self._handle_push_visibility)
        router.add_get("/about-me/categories", self._handle_about_me_categories)
        router.add_get("/about-me/entries/{category}", self._handle_about_me_list_entries)
        router.add_post("/about-me/entries/{category}", self._handle_about_me_create_entry)
        router.add_patch("/about-me/entries/{category}/{key}", self._handle_about_me_update_entry)
        router.add_post(
            "/about-me/entries/{category}/{key}/approve",
            self._handle_about_me_approve,
        )
        router.add_post(
            "/about-me/entries/{category}/{key}/reject",
            self._handle_about_me_reject,
        )
        router.add_get("/self/{bot}", self._handle_self_get)
        router.add_put("/self/{bot}", self._handle_self_put)
        router.add_get("/episodes/{bot}", self._handle_episodes_get)
        router.add_get("/facts/{bot}", self._handle_facts_get)
        router.add_put("/facts/{bot}/{fact_id}", self._handle_facts_put)
        router.add_get("/skill-proposals/{bot}", self._handle_skill_proposals_get)
        router.add_post(
            "/skill-proposals/{bot}/{proposal_id}/approve",
            self._handle_skill_proposal_approve,
        )
        router.add_post(
            "/skill-proposals/{bot}/{proposal_id}/reject",
            self._handle_skill_proposal_reject,
        )
        router.add_get("/goals/{bot}", self._handle_goals_get)
        router.add_post("/goals/{bot}", self._handle_goals_post)
        router.add_put("/goals/{bot}/{goal_id}", self._handle_goals_put)
        router.add_delete("/goals/{bot}/{goal_id}", self._handle_goals_delete)
        router.add_post(
            "/goals/{bot}/{goal_id}/progress",
            self._handle_goal_progress_post,
        )
        router.add_get("/healthz", self._handle_health)

    async def start(self) -> None:
        self._http_session = aiohttp.ClientSession()
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self._host, self._port)
        await self._site.start()
        logger.info("Chat server listening on http://%s:%d", self._host, self._port)

    async def stop(self) -> None:
        if self._http_session:
            with suppress(Exception):
                await self._http_session.close()
            self._http_session = None
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

    # ------------------------------------------------------------------
    # Web Push (Phase 1 of the Telegram → PWA migration)
    # ------------------------------------------------------------------

    async def _handle_push_vapid_key(self, _request: web.Request) -> web.Response:
        """Return the server's VAPID public key so the browser can
        ``pushManager.subscribe`` with it.

        The key is generated on first call and cached on disk — the
        browser then forwards the resulting subscription back to
        ``POST /chat/push/subscribe``.
        """
        keys = web_push.load_vapid_keys()
        return web.json_response({"publicKey": keys.public_key})

    async def _handle_push_subscribe(self, request: web.Request) -> web.Response:
        """Upsert a Web Push subscription.

        Body is the JSON form of ``PushSubscription.toJSON()`` from
        the browser plus our own ``device_id`` so visibility tracking
        can skip the active tab.
        """
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)

        if not isinstance(body, dict) or not body.get("endpoint"):
            return web.json_response({"error": "subscription must include endpoint"}, status=400)

        try:
            await web_push.add_subscription(body)
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        return web.json_response({"ok": True})

    async def _handle_push_unsubscribe(self, request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)

        endpoint = (body or {}).get("endpoint")
        if not isinstance(endpoint, str) or not endpoint:
            return web.json_response({"error": "endpoint required"}, status=400)

        await web_push.remove_subscription(endpoint)
        return web.json_response({"ok": True})

    async def _handle_push_visibility(self, request: web.Request) -> web.Response:
        """Mark a device visible / hidden so ``send_push`` can skip it.

        The browser pings this endpoint when the dashboard tab gains
        / loses focus (and periodically while focused). The TTL is
        60s so a stale ping does not silently suppress pushes long
        after the user closed the tab.
        """
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)

        device_id = (body or {}).get("deviceId")
        if not isinstance(device_id, str) or not device_id:
            return web.json_response({"error": "deviceId required"}, status=400)
        if body.get("visible"):
            web_push.mark_device_visible(device_id)
        else:
            web_push.mark_device_hidden(device_id)
        return web.json_response({"ok": True})

    async def _handle_list_bots(self, _request: web.Request) -> web.Response:
        config = load_config() or {}
        out: list[dict[str, Any]] = []
        for entry in config.get("bots") or []:
            name = entry.get("name")
            if not name:
                continue
            cfg = load_bot_config(name) or {}
            backend_cfg = cfg.get("backend") or {}
            alias_raw = cfg.get("alias")
            alias = alias_raw.strip() if isinstance(alias_raw, str) and alias_raw.strip() else None
            out.append(
                {
                    "name": name,
                    "display_name": cfg.get("display_name") or name,
                    "type": backend_cfg.get("type", "claude_code"),
                    "alias": alias,
                }
            )
        return web.json_response({"bots": out})

    async def _handle_create_bot(self, request: web.Request) -> web.Response:
        """Programmatic bot creation, mirrors ``abyss bot add``.

        Body is the same shape ``onboarding.prompt_bot_profile``
        returns interactively. We re-use ``onboarding.create_bot`` so
        the on-disk layout (``bot.yaml`` + ``config.yaml`` entry)
        stays identical to the CLI flow.

        Cron + heartbeat schedulers are attached on daemon start, so a
        new bot is chattable through the dashboard immediately but
        won't fire scheduled jobs until the next ``abyss restart``.
        """
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)
        if not isinstance(body, dict):
            return web.json_response({"error": "body must be an object"}, status=400)

        raw_name = str(body.get("name") or "").strip().lower().replace(" ", "-")
        if not raw_name:
            return web.json_response({"error": "name required"}, status=400)
        if not _BOT_NAME_PATTERN.match(raw_name) or not raw_name.replace("-", "").isalnum():
            return web.json_response(
                {"error": ("name must be lowercase letters / digits / hyphens (1–64 chars)")},
                status=400,
            )

        from abyss.config import bot_exists
        from abyss.onboarding import create_bot

        if bot_exists(raw_name):
            return web.json_response(
                {"error": f"bot '{raw_name}' already exists"},
                status=409,
            )

        display_name = str(body.get("display_name") or "").strip()
        personality = str(body.get("personality") or "").strip()
        role = str(body.get("role") or "").strip()
        goal = str(body.get("goal") or "").strip()
        alias_raw = str(body.get("alias") or "")
        alias = _sanitise_bot_alias(alias_raw)

        if not display_name:
            return web.json_response({"error": "display_name required"}, status=400)
        if not personality:
            return web.json_response({"error": "personality required"}, status=400)
        if not role:
            return web.json_response({"error": "role required"}, status=400)
        if alias_raw and not alias:
            return web.json_response(
                {"error": f"alias must be 1-{MAX_BOT_ALIAS_LENGTH} printable chars"},
                status=400,
            )

        profile = {
            "name": raw_name,
            "display_name": display_name,
            "personality": personality,
            "role": role,
            "goal": goal,
        }
        if alias:
            profile["alias"] = alias

        try:
            await asyncio.to_thread(create_bot, profile, None)
        except Exception as error:  # noqa: BLE001 — surface to UI
            logger.exception("chat_server: bot creation failed: %s", raw_name)
            return web.json_response({"error": f"creation failed: {error}"}, status=500)

        return web.json_response(
            {
                "ok": True,
                "name": raw_name,
                "display_name": display_name,
            },
            status=201,
        )

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
                "custom_name": None,
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

    async def _handle_rename_session(self, request: web.Request) -> web.Response:
        """Set or clear a session's user-facing ``custom_name``.

        Body: ``{"name": str}``. An empty / whitespace-only ``name``
        clears the field so the UI falls back to the bot display name.
        """
        bot_name = request.match_info["bot"]
        session_id = request.match_info["session_id"]
        session_dir = _resolve_session_dir(bot_name, session_id)
        if not session_dir.exists():
            return web.json_response({"error": "session not found"}, status=404)

        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)

        raw_name = body.get("name")
        if not isinstance(raw_name, str):
            return web.json_response({"error": "name must be a string"}, status=400)

        cleaned = _sanitise_custom_name(raw_name)
        meta = _load_session_meta(session_dir)
        if cleaned:
            meta["custom_name"] = cleaned
        else:
            meta.pop("custom_name", None)
        _save_session_meta(session_dir, meta)

        return web.json_response(
            {
                "id": session_id,
                "bot": bot_name,
                "custom_name": meta.get("custom_name") or None,
            }
        )

    async def _handle_get_messages(self, request: web.Request) -> web.Response:
        bot_name = request.match_info["bot"]
        session_id = request.match_info["session_id"]
        session_dir = _resolve_session_dir(bot_name, session_id)
        if not session_dir.exists():
            return web.json_response({"messages": []})
        messages = _parse_conversation_messages(session_dir, bot_name, session_id)
        return web.json_response({"messages": messages})

    async def _handle_mark_session_read(self, request: web.Request) -> web.Response:
        """Stamp ``last_read_at = now()`` on a chat session.

        Idempotent. Mobile detail screens call this on mount so the
        list re-fetched after backing out shows ``unread=false`` for
        the session that was just viewed.
        """
        bot_name = request.match_info["bot"]
        session_id = request.match_info["session_id"]
        session_dir = _resolve_session_dir(bot_name, session_id)
        if not session_dir.exists():
            return web.json_response({"error": "session not found"}, status=404)
        now = datetime.now(tz=timezone.utc).isoformat()
        meta = _load_session_meta(session_dir)
        meta["last_read_at"] = now
        _save_session_meta(session_dir, meta)
        return web.json_response({"last_read_at": now})

    # ---- ABOUT_ME endpoints -------------------------------------------

    @staticmethod
    def _validate_about_me_category(category: str) -> str:
        from abyss.about_me import ABOUT_ME_CATEGORIES

        if category not in ABOUT_ME_CATEGORIES:
            raise web.HTTPBadRequest(reason="invalid category")
        return category

    @staticmethod
    def _validate_about_me_key(key: str) -> str:
        if not key or len(key) > 128:
            raise web.HTTPBadRequest(reason="invalid key")
        # Allow kebab-case + underscores + ``__conflict_N`` suffix.
        import re as _re

        if not _re.match(r"^[A-Za-z0-9_\-]+$", key):
            raise web.HTTPBadRequest(reason="invalid key")
        return key

    @staticmethod
    def _serialize_about_entry(entry: Any) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "key": entry.key,
            "value": entry.value,
            "confidence": entry.confidence,
            "source": entry.source,
            "added": entry.added,
            "last_confirmed": entry.last_confirmed,
            "status": entry.status,
            "body": entry.body,
        }
        for key, value in entry.extra.items():
            payload.setdefault(key, value)
        return payload

    async def _handle_about_me_categories(self, _request: web.Request) -> web.Response:
        from abyss.about_me import category_counts, count_proposals

        return web.json_response(
            {
                "categories": category_counts(),
                "pending_proposals": count_proposals(),
            }
        )

    async def _handle_about_me_list_entries(self, request: web.Request) -> web.Response:
        from abyss.about_me import load_category

        category = self._validate_about_me_category(request.match_info["category"])
        status_filter = request.query.get("status")
        entries = load_category(category)
        if status_filter in ("confirmed", "propose"):
            entries = [entry for entry in entries if entry.status == status_filter]
        return web.json_response(
            {
                "category": category,
                "entries": [self._serialize_about_entry(entry) for entry in entries],
            }
        )

    async def _handle_about_me_create_entry(self, request: web.Request) -> web.Response:
        from abyss.about_me import AboutEntry, upsert_entry

        category = self._validate_about_me_category(request.match_info["category"])
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)

        key = self._validate_about_me_key(str(body.get("key", "")).strip())
        value = str(body.get("value", "")).strip()
        if not value:
            return web.json_response({"error": "value required"}, status=400)
        status = str(body.get("status", "confirmed"))
        confidence = str(body.get("confidence", "high"))
        markdown_body = str(body.get("body", "")).strip()

        try:
            entry = AboutEntry(
                key=key,
                value=value,
                body=markdown_body,
                confidence=confidence,
                source="dashboard",
                status=status,
            )
            upsert_entry(category, entry)
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)

        return web.json_response({"ok": True, "key": key, "status": status})

    async def _handle_about_me_update_entry(self, request: web.Request) -> web.Response:
        from abyss.about_me import update_entry

        category = self._validate_about_me_category(request.match_info["category"])
        key = self._validate_about_me_key(request.match_info["key"])
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)

        value = body.get("value")
        markdown_body = body.get("body")
        confidence = body.get("confidence")

        try:
            ok = update_entry(
                category,
                key,
                value=str(value) if value is not None else None,
                body=str(markdown_body) if markdown_body is not None else None,
                confidence=str(confidence) if confidence is not None else None,
            )
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)

        if not ok:
            return web.json_response({"error": "entry not found"}, status=404)
        return web.json_response({"ok": True})

    async def _handle_about_me_approve(self, request: web.Request) -> web.Response:
        from abyss.about_me import approve_entry

        category = self._validate_about_me_category(request.match_info["category"])
        key = self._validate_about_me_key(request.match_info["key"])
        if not approve_entry(category, key):
            return web.json_response({"error": "entry not found"}, status=404)
        return web.json_response({"ok": True, "status": "confirmed"})

    async def _handle_about_me_reject(self, request: web.Request) -> web.Response:
        from abyss.about_me import reject_entry

        category = self._validate_about_me_category(request.match_info["category"])
        key = self._validate_about_me_key(request.match_info["key"])
        if not reject_entry(category, key):
            return web.json_response({"error": "entry not found"}, status=404)
        return web.json_response({"ok": True})

    async def _handle_self_get(self, request: web.Request) -> web.Response:
        """Return the bot's SELF.md text (empty string if file is missing)."""
        from abyss.self_reflection import load_self_md

        bot_name = _validate_bot_name(request.match_info["bot"])
        bot_path = bot_directory(bot_name)
        if not bot_path.exists():
            return web.json_response({"error": "bot not found"}, status=404)
        return web.json_response({"bot": bot_name, "content": load_self_md(bot_name)})

    async def _handle_self_put(self, request: web.Request) -> web.Response:
        """Overwrite the bot's SELF.md with the supplied markdown body.

        Body: ``{"content": "<markdown>"}``. Used by the dashboard SELF
        editor for manual edits / rollbacks. The reflection cron and
        ``abyss self reflect`` CLI go through ``run_reflection`` instead.
        """
        from abyss.self_reflection import save_self_md

        bot_name = _validate_bot_name(request.match_info["bot"])
        bot_path = bot_directory(bot_name)
        if not bot_path.exists():
            return web.json_response({"error": "bot not found"}, status=404)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)
        content = body.get("content") if isinstance(body, dict) else None
        if not isinstance(content, str):
            return web.json_response({"error": "content must be a string"}, status=400)
        save_self_md(bot_name, content)
        return web.json_response({"ok": True, "bot": bot_name})

    async def _handle_episodes_get(self, request: web.Request) -> web.Response:
        """Return episodes for ``bot`` newest-first.

        Query params: ``since=YYYY-MM-DD`` (inclusive lower bound),
        ``limit=N`` (default 50, max 500), ``kind=fact|event|...``.
        """
        from dataclasses import asdict

        from abyss.episodes import iter_episodes

        bot_name = _validate_bot_name(request.match_info["bot"])
        bot_path = bot_directory(bot_name)
        if not bot_path.exists():
            return web.json_response({"error": "bot not found"}, status=404)

        since = request.query.get("since")
        kind = request.query.get("kind")
        kinds = (kind,) if kind else None
        try:
            limit = min(max(1, int(request.query.get("limit", "50"))), 500)
        except ValueError:
            return web.json_response({"error": "invalid limit"}, status=400)
        rows = [asdict(ep) for ep in iter_episodes(bot_name, since=since, kinds=kinds, limit=limit)]
        return web.json_response({"bot": bot_name, "episodes": rows})

    async def _handle_facts_get(self, request: web.Request) -> web.Response:
        """Return facts for ``bot`` ordered by confidence desc.

        Query params: ``subject=<exact>``, ``min_confidence=<float>``,
        ``limit=N`` (default 50, max 500), ``include_retracted=true|false``.
        """
        from abyss.episodes import query_facts

        bot_name = _validate_bot_name(request.match_info["bot"])
        bot_path = bot_directory(bot_name)
        if not bot_path.exists():
            return web.json_response({"error": "bot not found"}, status=404)

        subject = request.query.get("subject") or None
        try:
            min_confidence = float(request.query.get("min_confidence", "0"))
        except ValueError:
            return web.json_response({"error": "invalid min_confidence"}, status=400)
        try:
            limit = min(max(1, int(request.query.get("limit", "50"))), 500)
        except ValueError:
            return web.json_response({"error": "invalid limit"}, status=400)
        include_retracted = request.query.get("include_retracted", "").lower() in (
            "1",
            "true",
            "yes",
        )
        statuses: tuple[str, ...] = (
            ("active", "retracted", "superseded") if include_retracted else ("active",)
        )
        rows = query_facts(
            bot_name,
            subject=subject,
            min_confidence=min_confidence,
            statuses=statuses,
            limit=limit,
        )
        return web.json_response({"bot": bot_name, "facts": rows})

    async def _handle_facts_put(self, request: web.Request) -> web.Response:
        """Update one fact — currently only ``retract`` is supported.

        Body: ``{"action": "retract"}``. Returns 404 when the fact id
        is unknown so the dashboard can disambiguate stale UI.
        """
        from abyss.episodes import retract_fact

        bot_name = _validate_bot_name(request.match_info["bot"])
        bot_path = bot_directory(bot_name)
        if not bot_path.exists():
            return web.json_response({"error": "bot not found"}, status=404)
        try:
            fact_id = int(request.match_info["fact_id"])
        except ValueError:
            return web.json_response({"error": "invalid fact_id"}, status=400)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)
        action = body.get("action") if isinstance(body, dict) else None
        if action != "retract":
            return web.json_response({"error": "unsupported action"}, status=400)
        if not retract_fact(bot_name, fact_id):
            return web.json_response({"error": "fact not found"}, status=404)
        return web.json_response({"ok": True, "bot": bot_name, "fact_id": fact_id})

    async def _handle_skill_proposals_get(self, request: web.Request) -> web.Response:
        """Return skill proposals for ``bot``, optionally filtered by status.

        Query params: ``status=pending|approved|rejected``.
        """
        from dataclasses import asdict

        from abyss.skill_proposals import list_proposals

        bot_name = _validate_bot_name(request.match_info["bot"])
        bot_path = bot_directory(bot_name)
        if not bot_path.exists():
            return web.json_response({"error": "bot not found"}, status=404)
        status_filter = request.query.get("status")
        rows = list_proposals(bot_name, status=status_filter)
        return web.json_response({"bot": bot_name, "proposals": [asdict(row) for row in rows]})

    async def _handle_skill_proposal_approve(self, request: web.Request) -> web.Response:
        """Approve a proposal — runs import + attach + status update."""
        from abyss.skill_proposals import approve

        bot_name = _validate_bot_name(request.match_info["bot"])
        bot_path = bot_directory(bot_name)
        if not bot_path.exists():
            return web.json_response({"error": "bot not found"}, status=404)
        proposal_id = request.match_info["proposal_id"]
        result = approve(bot_name, proposal_id)
        # Only "proposal not found" surfaces as 404 — every other
        # failure (import / attach error, previously rejected) returns
        # 200 with ``ok=false`` so the dashboard can render the stage
        # + error text without catching an HTTP exception.
        if not result.get("ok") and result.get("stage") == "lookup" and not result.get("proposal"):
            return web.json_response({"error": result["error"]}, status=404)
        proposal = result.get("proposal")
        payload: dict[str, Any] = {
            "ok": bool(result.get("ok")),
            "proposal_id": proposal_id,
        }
        if "skill_name" in result:
            payload["skill_name"] = result["skill_name"]
        if "skill_path" in result:
            payload["skill_path"] = result["skill_path"]
        if "stage" in result:
            payload["stage"] = result["stage"]
        if "error" in result:
            payload["error"] = result["error"]
        if proposal is not None and hasattr(proposal, "id"):
            from dataclasses import asdict

            payload["proposal"] = asdict(proposal)
        return web.json_response(payload)

    async def _handle_skill_proposal_reject(self, request: web.Request) -> web.Response:
        """Reject a proposal — flips status to ``rejected``."""
        from dataclasses import asdict

        from abyss.skill_proposals import reject

        bot_name = _validate_bot_name(request.match_info["bot"])
        bot_path = bot_directory(bot_name)
        if not bot_path.exists():
            return web.json_response({"error": "bot not found"}, status=404)
        proposal_id = request.match_info["proposal_id"]
        updated = reject(bot_name, proposal_id)
        if updated is None:
            return web.json_response({"error": "proposal not found"}, status=404)
        return web.json_response({"ok": True, "proposal": asdict(updated)})

    async def _handle_goals_get(self, request: web.Request) -> web.Response:
        """List goals for ``bot``, optionally filtered by status."""
        from dataclasses import asdict

        from abyss.goals import list_goals

        bot_name = _validate_bot_name(request.match_info["bot"])
        bot_path = bot_directory(bot_name)
        if not bot_path.exists():
            return web.json_response({"error": "bot not found"}, status=404)
        status_filter = request.query.get("status")
        rows = list_goals(bot_name, status=status_filter)
        return web.json_response({"bot": bot_name, "goals": [asdict(row) for row in rows]})

    async def _handle_goals_post(self, request: web.Request) -> web.Response:
        """Add a new goal. Body: ``{title, kpi?, target?, id?}``."""
        from dataclasses import asdict

        from abyss.goals import add_goal

        bot_name = _validate_bot_name(request.match_info["bot"])
        bot_path = bot_directory(bot_name)
        if not bot_path.exists():
            return web.json_response({"error": "bot not found"}, status=404)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)
        if not isinstance(body, dict):
            return web.json_response({"error": "body must be an object"}, status=400)
        title = (body.get("title") or "").strip()
        if not title:
            return web.json_response({"error": "title required"}, status=400)
        try:
            goal = add_goal(
                bot_name,
                title,
                goal_id=(body.get("id") or None),
                kpi=(body.get("kpi") or "").strip(),
                target=(body.get("target") or "").strip(),
            )
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        return web.json_response({"ok": True, "goal": asdict(goal)}, status=201)

    async def _handle_goals_put(self, request: web.Request) -> web.Response:
        """Update title/kpi/target/status of a goal."""
        from dataclasses import asdict

        from abyss.goals import update_goal

        bot_name = _validate_bot_name(request.match_info["bot"])
        bot_path = bot_directory(bot_name)
        if not bot_path.exists():
            return web.json_response({"error": "bot not found"}, status=404)
        goal_id = request.match_info["goal_id"]
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)
        if not isinstance(body, dict):
            return web.json_response({"error": "body must be an object"}, status=400)
        try:
            updated = update_goal(
                bot_name,
                goal_id,
                title=body.get("title"),
                kpi=body.get("kpi"),
                target=body.get("target"),
                status=body.get("status"),
            )
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        if updated is None:
            return web.json_response({"error": "goal not found"}, status=404)
        return web.json_response({"ok": True, "goal": asdict(updated)})

    async def _handle_goals_delete(self, request: web.Request) -> web.Response:
        from abyss.goals import delete_goal

        bot_name = _validate_bot_name(request.match_info["bot"])
        bot_path = bot_directory(bot_name)
        if not bot_path.exists():
            return web.json_response({"error": "bot not found"}, status=404)
        goal_id = request.match_info["goal_id"]
        if not delete_goal(bot_name, goal_id):
            return web.json_response({"error": "goal not found"}, status=404)
        return web.json_response({"ok": True, "goal_id": goal_id})

    async def _handle_goal_progress_post(self, request: web.Request) -> web.Response:
        """Human-side progress logger. Body: ``{note, value?}``."""
        from dataclasses import asdict

        from abyss.goals import record_progress

        bot_name = _validate_bot_name(request.match_info["bot"])
        bot_path = bot_directory(bot_name)
        if not bot_path.exists():
            return web.json_response({"error": "bot not found"}, status=404)
        goal_id = request.match_info["goal_id"]
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)
        if not isinstance(body, dict):
            return web.json_response({"error": "body must be an object"}, status=400)
        note = (body.get("note") or "").strip()
        if not note:
            return web.json_response({"error": "note required"}, status=400)
        value = body.get("value")
        if value is not None:
            try:
                value = float(value)
            except (TypeError, ValueError):
                return web.json_response({"error": "value must be a number"}, status=400)
        try:
            entry = record_progress(bot_name, goal_id, note, value=value)
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        if entry is None:
            return web.json_response({"error": "goal not found"}, status=404)
        return web.json_response({"ok": True, "entry": asdict(entry)})

    async def _handle_log_feedback(self, request: web.Request) -> web.Response:
        """Record a numeric feedback signal (1/2/3) for an assistant turn.

        Body: ``{"turn_id": "<assistant timestamp>", "signal": 1|2|3,
        "note"?: "..."}``. Records append to
        ``bots/<bot>/feedback.jsonl``. Same ``turn_id`` may be rated
        multiple times — aggregation uses latest-wins.
        """
        from abyss.feedback import (
            MAX_NOTE_LENGTH,
            VALID_SIGNALS,
            append_feedback,
        )

        bot_name = request.match_info["bot"]
        session_id = request.match_info["session_id"]
        session_dir = _resolve_session_dir(bot_name, session_id)
        if not session_dir.exists():
            return web.json_response({"error": "session not found"}, status=404)

        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)

        turn_id = body.get("turn_id")
        if not isinstance(turn_id, str) or not turn_id.strip():
            return web.json_response({"error": "turn_id required"}, status=400)
        turn_id = turn_id.strip()

        signal = body.get("signal")
        if not isinstance(signal, int) or signal not in VALID_SIGNALS:
            return web.json_response({"error": "signal must be 1, 2, or 3"}, status=400)

        note = body.get("note") or ""
        if not isinstance(note, str):
            return web.json_response({"error": "note must be a string"}, status=400)
        if len(note) > MAX_NOTE_LENGTH:
            return web.json_response({"error": "note too long"}, status=400)

        record = append_feedback(
            bot=bot_name,
            session_id=session_id,
            turn_id=turn_id,
            signal=signal,
            note=note,
        )
        return web.json_response({"ok": True, "ts": record["ts"]})

    async def _handle_mark_routine_read(self, request: web.Request) -> web.Response:
        """Stamp ``last_read_at = now()`` on a routine session dir.

        Reuses ``_resolve_routine_dir`` so cron / heartbeat regex
        validation + path-traversal guard apply uniformly with the
        existing routine GET endpoints.
        """
        bot_name = request.match_info["bot"]
        kind = request.match_info["kind"]
        job_name = request.match_info["job"]
        session_dir = _resolve_routine_dir(bot_name, kind, job_name)
        if session_dir is None or not session_dir.exists():
            return web.json_response({"error": "routine not found"}, status=404)
        now = datetime.now(tz=timezone.utc).isoformat()
        meta = _load_session_meta(session_dir)
        meta["last_read_at"] = now
        _save_session_meta(session_dir, meta)
        return web.json_response({"last_read_at": now})

    async def _handle_list_routines(self, _request: web.Request) -> web.Response:
        """List every cron job + heartbeat session across all bots.

        Each entry mirrors the ``_session_metadata`` shape used by the
        chat sessions endpoint so the mobile Routines tab can render
        rows with the same component as the Chats tab.
        """
        config = load_config() or {}
        out: list[dict[str, Any]] = []
        for entry in config.get("bots") or []:
            bot_name = entry.get("name")
            if not bot_name:
                continue
            try:
                _validate_bot_name(bot_name)
            except web.HTTPError:
                continue
            bot_path = bot_directory(bot_name)
            if not bot_path.exists():
                continue
            display = _bot_display_name(bot_name)

            cron_root = bot_path / "cron_sessions"
            if cron_root.is_dir():
                for job_dir in sorted(cron_root.iterdir()):
                    if not job_dir.is_dir():
                        continue
                    if not _ROUTINE_JOB_PATTERN.match(job_dir.name):
                        continue
                    out.append(
                        _routine_metadata(
                            bot_name=bot_name,
                            bot_display_name=display,
                            kind="cron",
                            job_name=job_dir.name,
                            session_dir=job_dir,
                        )
                    )

            heartbeat_dir = bot_path / "heartbeat_sessions"
            if heartbeat_dir.is_dir() and any(heartbeat_dir.iterdir()):
                out.append(
                    _routine_metadata(
                        bot_name=bot_name,
                        bot_display_name=display,
                        kind="heartbeat",
                        job_name="heartbeat",
                        session_dir=heartbeat_dir,
                    )
                )

        out.sort(key=lambda r: r["updated_at"], reverse=True)
        return web.json_response({"routines": out})

    async def _handle_get_routine_messages(self, request: web.Request) -> web.Response:
        bot_name = request.match_info["bot"]
        kind = request.match_info["kind"]
        job_name = request.match_info["job"]
        session_dir = _resolve_routine_dir(bot_name, kind, job_name)
        if session_dir is None or not session_dir.exists():
            return web.json_response({"messages": []})
        # Routines never carry uploads, so the attachment-aware bot /
        # session strings used by ``_parse_conversation_messages``
        # don't matter — pass empty placeholders.
        messages = _parse_conversation_messages(session_dir, "", "")
        # Filter out cron / heartbeat *trigger* user entries written
        # before the user-role split (role="user"). Real keyboard
        # replies via ``_handle_routine_chat`` log as role="human",
        # so dropping "user" here hides the noisy system prompts
        # without losing actual conversation. Assistant replies are
        # always shown. Re-tag ``human`` → ``user`` in the response
        # so the existing mobile bubble renderer (which checks
        # ``role === "user"``) keeps working.
        filtered: list[dict[str, Any]] = []
        for entry in messages:
            role = entry.get("role")
            if role == "user":
                # Pre-split trigger; hide.
                continue
            if role == "human":
                entry = {**entry, "role": "user"}
            filtered.append(entry)
        return web.json_response({"messages": filtered})

    async def _handle_routine_chat(self, request: web.Request) -> web.StreamResponse:
        """Reply to a cron / heartbeat routine from the mobile Routines tab.

        Mirrors ``_handle_chat`` but targets the routine's session
        directory (``cron_sessions/<job>`` or ``heartbeat_sessions``)
        instead of a ``chat_<id>`` session. The Claude session ID
        stored alongside the cron / heartbeat run gets resumed so the
        user's reply lands in the same conversation that the scheduled
        run produced — the original prompt context is preserved.
        """
        bot_name = request.match_info["bot"]
        kind = request.match_info["kind"]
        job_name = request.match_info["job"]

        session_dir = _resolve_routine_dir(bot_name, kind, job_name)
        if session_dir is None or not session_dir.exists():
            return web.json_response({"error": "routine not found"}, status=404)

        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)
        message = (body.get("message") or "").strip()
        if not message:
            return web.json_response({"error": "message required"}, status=400)
        if len(message.encode("utf-8")) > MAX_MESSAGE_BYTES:
            return web.json_response({"error": "message too large"}, status=413)

        bot_config = load_bot_config(bot_name)
        if bot_config is None:
            return web.json_response({"error": "bot not found"}, status=404)
        bot_path = bot_directory(bot_name)

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

        # Route the reply through ``chat_core.process_chat_message``
        # with an explicit session-dir override; ``session_key``
        # keeps the SDK pool entry separate from regular chats so a
        # routine reply doesn't collide with a same-bot dashboard
        # session that happens to be active.
        synthetic_chat_id = f"{kind}:{job_name}"
        session_key = f"{bot_name}:{kind}:{job_name}"
        full_text = ""
        try:
            full_text = await process_chat_message(
                bot_name=bot_name,
                bot_path=bot_path,
                bot_config=bot_config,
                chat_id=synthetic_chat_id,
                user_message=message,
                on_chunk=on_chunk,
                session_key=session_key,
                attachments=(),
                session_dir_override=session_dir,
                # ``human`` distinguishes a real keyboard reply from
                # the legacy ``user`` entries that cron / heartbeat
                # left in older conversation files. The Routines viewer
                # filters on this so the noisy trigger prompts that
                # predate the user-role split stay hidden.
                user_role="human",
            )
            await _sse_write(sse, {"type": "done", "text": full_text})
            # Web Push for routine replies — parity with chat. The SW
            # tag collapses by (kind, job_name) so a reply notification
            # replaces the cron run's notification instead of stacking.
            with suppress(Exception):
                await self._notify_routine_reply(
                    bot_name=bot_name,
                    bot_config=bot_config,
                    kind=kind,
                    job_name=job_name,
                    reply_text=full_text,
                )
        except Exception as error:  # noqa: BLE001
            logger.error(
                "routine chat failed bot=%s %s/%s: %s",
                bot_name,
                kind,
                job_name,
                error,
            )
            with suppress(Exception):
                await _sse_write(sse, {"type": "error", "message": str(error)})
        return sse

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
        voice_mode: bool = bool(body.get("voice_mode", False))

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

        # Slash commands bypass the LLM entirely.
        if message.startswith("/") and not raw_attachments:
            return await self._handle_slash_command(
                request=request,
                bot_name=bot_name,
                bot_path=bot_path,
                bot_config=bot_config,
                session_id=session_id,
                message=message,
            )

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

        async def on_reset() -> None:
            """Tell the client to discard any partial chunks streamed so far.

            ``chat_core`` invokes this between retries when the upstream
            API returned a retryable 5xx — the partial JSON error text
            already pushed to the client must not be concatenated onto
            the successful retry's reply.
            """
            with suppress(Exception):
                await _sse_write(sse, {"type": "reset_partial"})

        effective_message = message
        if voice_mode:
            effective_message += (
                "\n\n[응답 지침: 음성으로 전달됩니다. 자연스러운 구어체 한국어로 답변하세요. "
                '"없음" → "없어요", 마크다운/불릿/이모지 없이 말하듯 짧고 자연스럽게.]'
            )

        lock = self._lock_for(bot_name, session_id)
        full_text = ""
        try:
            async with lock:
                full_text = await process_chat_message(
                    bot_name=bot_name,
                    bot_path=bot_path,
                    bot_config=bot_config,
                    chat_id=session_id,
                    user_message=effective_message,
                    on_chunk=on_chunk,
                    on_reset=on_reset,
                    session_key=f"{bot_name}:{session_id}",
                    attachments=attachment_paths,
                )
            await _sse_write(sse, {"type": "done", "text": full_text})
            # Web Push notification — skipped for the device currently
            # viewing the dashboard. Failure must never break the SSE
            # response, so wrap broadly.
            with suppress(Exception):
                await self._notify_chat_reply(
                    bot_name=bot_name,
                    bot_config=bot_config,
                    session_id=session_id,
                    reply_text=full_text,
                )
        except Exception as error:  # noqa: BLE001 — propagate to client cleanly
            logger.error(
                "chat_server: chat failed bot=%s session=%s: %s", bot_name, session_id, error
            )
            with suppress(Exception):
                await _sse_write(sse, {"type": "error", "message": str(error)})
        return sse

    async def _notify_chat_reply(
        self,
        *,
        bot_name: str,
        bot_config: dict[str, Any],
        session_id: str,
        reply_text: str,
    ) -> None:
        """Send a Web Push notification for a completed chat reply.

        The body is a short preview (~120 chars) — the full transcript
        stays on the server, the notification click handler navigates
        the user to the live chat.
        """
        if not reply_text:
            return
        display_name = bot_config.get("display_name") or bot_name
        preview = reply_text.replace("\n", " ").strip()
        if len(preview) > 120:
            preview = preview[:117] + "…"
        await web_push.send_push(
            title=display_name,
            body=preview,
            bot=bot_name,
            session_id=session_id,
            kind="chat",
        )

    async def _notify_routine_reply(
        self,
        *,
        bot_name: str,
        bot_config: dict[str, Any],
        kind: str,
        job_name: str,
        reply_text: str,
    ) -> None:
        """Send a Web Push notification for a completed routine reply.

        Same shape as ``_notify_chat_reply`` but keyed by
        ``(kind, job_name)`` so the service worker routes the click to
        ``/mobile/routine/<bot>/<kind>/<job>`` and the tag collapses
        with the original cron / heartbeat notification.
        """
        if not reply_text:
            return
        display_name = bot_config.get("display_name") or bot_name
        preview = reply_text.replace("\n", " ").strip()
        if len(preview) > 120:
            preview = preview[:117] + "…"
        await web_push.send_push(
            title=display_name,
            body=preview,
            bot=bot_name,
            kind=kind,
            job_name=job_name,
        )

    # ------------------------------------------------------------------
    # Slash commands
    # ------------------------------------------------------------------

    async def _handle_list_commands(self, _request: web.Request) -> web.Response:
        """Expose the slash command catalog for dashboard autocomplete."""

        return web.json_response(
            {
                "commands": [
                    {
                        "name": spec.name,
                        "description": spec.description,
                        "usage": spec.usage,
                    }
                    for spec in commands.COMMAND_CATALOG
                ]
            }
        )

    async def _cancel_for_dashboard(self, target_bot: str, session_key: str) -> bool:
        """Cancel primitive shared by ``cmd_cancel`` and ``/chat/cancel``.

        Mirrors the Telegram adapter: backend.cancel → SDK session cancel
        → subprocess cancel, returning ``True`` when any path succeeds.
        """

        backend = cached_backend(target_bot)
        if backend is not None and await backend.cancel(session_key):
            return True
        if await cancel_sdk_session(session_key):
            return True
        if is_process_running(session_key) and cancel_process(session_key):
            return True
        return False

    async def _handle_slash_command(
        self,
        *,
        request: web.Request,
        bot_name: str,
        bot_path: Path,
        bot_config: dict[str, Any],
        session_id: str,
        message: str,
    ) -> web.StreamResponse:
        """Dispatch ``/<name> <args...>`` to ``abyss.commands``.

        The result is streamed back as a single SSE pair (``command_result``
        + ``done``) so the dashboard UI handles slash replies uniformly
        with regular streaming replies.
        """

        parts = message.split(maxsplit=1)
        command_name = parts[0][1:].lower()  # strip leading '/'
        args = parts[1].split() if len(parts) > 1 else []

        sse = web.StreamResponse(
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            }
        )
        await sse.prepare(request)

        ctx = commands.CommandContext(
            bot_name=bot_name,
            bot_path=bot_path,
            bot_config=bot_config,
            chat_id=session_id,
            args=args,
        )

        try:
            text, file_info = await self._run_dashboard_command(
                command_name, ctx, bot_name=bot_name, session_id=session_id
            )
            payload: dict[str, Any] = {
                "type": "command_result",
                "command": command_name,
                "text": text,
            }
            if file_info is not None:
                payload["file"] = file_info
            await _sse_write(sse, payload)
            await _sse_write(sse, {"type": "done", "text": text})
            # Persist the slash exchange to the conversation markdown
            # so navigating away + back, or reloading, doesn't drop
            # the reply. Regular messages get this through
            # ``process_chat_message``; the dashboard slash path
            # bypassed that until now, so users saw their /commands
            # vanish whenever they switched chats.
            try:
                session_dir = build_session_directory(bot_path, _validate_session_id(session_id))
                log_conversation(session_dir, "user", message)
                assistant_log = text or ""
                if file_info is not None:
                    file_name = file_info.get("name", "file")
                    file_url = file_info.get("url", "")
                    file_line = f"📎 [{file_name}]({file_url})"
                    assistant_log = (
                        f"{assistant_log}\n\n{file_line}" if assistant_log else file_line
                    )
                if assistant_log:
                    log_conversation(session_dir, "assistant", assistant_log)
            except Exception as log_error:  # noqa: BLE001
                logger.warning(
                    "chat_server: slash log skipped bot=%s session=%s: %s",
                    bot_name,
                    session_id,
                    log_error,
                )
        except Exception as error:  # noqa: BLE001
            logger.error(
                "chat_server: slash failed bot=%s session=%s cmd=%s: %s",
                bot_name,
                session_id,
                command_name,
                error,
            )
            with suppress(Exception):
                await _sse_write(sse, {"type": "error", "message": str(error)})
        return sse

    async def _run_dashboard_command(
        self,
        command_name: str,
        ctx: commands.CommandContext,
        *,
        bot_name: str,
        session_id: str,
    ) -> tuple[str, dict[str, Any] | None]:
        """Run a single slash command and return ``(text, file_info)``.

        Returns ``("", file_info)`` when the command produced a file
        (``/send``); the dashboard can then offer the file as a download
        link via ``/chat/sessions/{bot}/{session_id}/file/{name}``.
        Returns ``(text, None)`` for text-only commands.
        Unknown commands raise ``LookupError`` so the caller surfaces an
        error event.
        """

        # Read-only / trivial commands.
        if command_name == "start":
            result = await commands.cmd_start(ctx)
        elif command_name == "help":
            result = await commands.cmd_help(ctx)
        elif command_name == "version":
            result = await commands.cmd_version(ctx)
        elif command_name == "status":
            result = await commands.cmd_status(ctx)
        elif command_name == "files":
            result = await commands.cmd_files(ctx)
        elif command_name == "memory":
            result = await commands.cmd_memory(ctx)
        elif command_name == "model":
            result = await commands.cmd_model(ctx)
        elif command_name == "streaming":
            result = await commands.cmd_streaming(ctx)
        elif command_name == "reset":
            outcome = await commands.cmd_reset(ctx)
            await self._close_pool_sessions(outcome.affected_bots, session_id)
            result = outcome.result
        elif command_name == "resetall":
            result = await commands.cmd_resetall(ctx)
            await self._close_pool_sessions([bot_name], session_id)
        elif command_name == "cancel":
            outcome = await commands.cmd_cancel(ctx, cancel_for=self._cancel_for_dashboard)
            result = outcome.result
        elif command_name == "send":
            result = await commands.cmd_send(ctx)
            if result.file_path is not None:
                relative = result.file_path.relative_to(
                    ctx.bot_path / "sessions" / session_id / "workspace"
                )
                return "", {
                    "name": result.file_path.name,
                    "path": str(relative),
                    "url": (f"/chat/sessions/{bot_name}/{session_id}/file/{result.file_path.name}"),
                }
        elif command_name == "skills":
            result = await commands.cmd_skills(ctx)
        elif command_name == "heartbeat":
            # ``/heartbeat run`` triggers the same code path as the
            # scheduler; the result lands in
            # ``heartbeat_sessions/conversation-*.md`` and (when a
            # PWA subscription exists) a Web Push notification.
            if ctx.args and ctx.args[0].lower() == "run":
                from abyss.heartbeat import execute_heartbeat

                await execute_heartbeat(bot_name=ctx.bot_name, bot_config=ctx.bot_config)
                return (
                    "💓 Heartbeat fired. Check the Routines tab for the result.",
                    None,
                )
            result = await commands.cmd_heartbeat(ctx)
        elif command_name == "compact":
            preview = await commands.cmd_compact_preview(ctx)
            if not preview.targets:
                return preview.text, None
            run_result = await commands.cmd_compact_run(ctx)
            return f"{preview.text}\n\n{run_result.text}", None
        elif command_name == "cron":
            sub = ctx.args[0].lower() if ctx.args else ""
            if sub == "run":
                # ``/cron run <job>`` triggers the same function the
                # scheduler invokes — the result lands in the
                # routine's conversation log + (when subscribed) Web
                # Push.
                if len(ctx.args) < 2:
                    return "Usage: `/cron run <job_name>`", None
                from abyss.cron import execute_cron_job, get_cron_job

                job_name = ctx.args[1]
                cron_job = get_cron_job(ctx.bot_name, job_name)
                if cron_job is None:
                    return f"Cron job '{job_name}' not found.", None
                await execute_cron_job(
                    bot_name=ctx.bot_name,
                    job=cron_job,
                    bot_config=ctx.bot_config,
                )
                return (
                    f"⏰ Cron job '{job_name}' fired. Check the Routines tab.",
                    None,
                )
            if sub == "edit":
                return (
                    "⚠️ /cron edit (multi-step) is not yet wired into the PWA chat. "
                    "Use `abyss bot edit <bot>` to edit cron.yaml directly.",
                    None,
                )
            result = await commands.cmd_cron(ctx)
        else:
            raise LookupError(f"unknown command: /{command_name}")

        return result.text, None

    async def _close_pool_sessions(self, bot_names: list[str], session_id: str) -> None:
        """Close SDK pool sessions for the given bots after a reset.

        Mirrors the Telegram adapter's post-reset cleanup so dashboard
        users see a fresh Claude session next message.
        """

        from abyss.sdk_client import get_pool, is_sdk_available

        if not is_sdk_available():
            return
        pool = get_pool()
        for bot in bot_names:
            await pool.close_session(f"{bot}:{session_id}")

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
        except Exception:
            logger.exception("upload failed for bot=%s session=%s", bot_name, session_id)
            with suppress(FileNotFoundError):
                stored_path.unlink()
            # Detail kept generic — the underlying ``open`` / ``shutil``
            # error can leak filesystem paths and the daemon log has
            # the full trace anyway.
            return web.json_response(
                {"error": "upload_failed", "detail": "upload failed"}, status=500
            )

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

    async def _handle_transcribe(self, request: web.Request) -> web.Response:
        """Transcribe audio via ElevenLabs Scribe v2.

        Expects multipart/form-data with an ``audio`` field containing raw
        audio bytes (webm/ogg/wav).  Returns ``{"text": "..."}`` or
        ``{"text": ""}`` when the language probability is too low (silence /
        noise guard against Whisper-style hallucinations).
        """
        if not ELEVENLABS_API_KEY:
            return web.json_response({"error": "ELEVENLABS_API_KEY not set"}, status=503)

        try:
            reader = await request.multipart()
        except Exception:
            return web.json_response({"error": "invalid multipart"}, status=400)

        audio_bytes: bytes | None = None
        async for field in reader:
            if field.name == "audio":
                audio_bytes = await field.read(decode=True)
                break

        if not audio_bytes:
            return web.json_response({"error": "missing audio field"}, status=400)
        if len(audio_bytes) > MAX_AUDIO_BYTES:
            return web.json_response({"error": "audio too large"}, status=413)

        form = aiohttp.FormData()
        form.add_field("model_id", ELEVENLABS_STT_MODEL)
        form.add_field("language_code", "ko")
        form.add_field(
            "file",
            audio_bytes,
            filename="audio.webm",
            content_type="audio/webm",
        )

        logger.info(
            "ElevenLabs STT request: model=%s audio=%d bytes",
            ELEVENLABS_STT_MODEL,
            len(audio_bytes),
        )
        start = time.perf_counter()
        try:
            if self._http_session is None:
                raise RuntimeError(
                    "HTTP session not initialised — chat_server start() must run first"
                )
            async with self._http_session.post(
                ELEVENLABS_STT_URL,
                headers={"xi-api-key": ELEVENLABS_API_KEY},
                data=form,
            ) as response:
                if response.status != 200:
                    body = await response.text()
                    logger.warning(
                        "ElevenLabs STT error %d after %.0fms: %s",
                        response.status,
                        (time.perf_counter() - start) * 1000,
                        body[:300],
                    )
                    return web.json_response({"error": f"upstream {response.status}"}, status=502)
                data = await response.json()
        except Exception as exc:
            logger.exception(
                "ElevenLabs STT request failed after %.0fms", (time.perf_counter() - start) * 1000
            )
            return web.json_response({"error": str(exc)}, status=502)

        elapsed_ms = (time.perf_counter() - start) * 1000
        language_probability = data.get("language_probability", 1.0)
        text = data.get("text", "").strip()
        if language_probability < MIN_STT_LANGUAGE_PROBABILITY:
            logger.info(
                "ElevenLabs STT %.0fms: dropped low-confidence transcript "
                "(lang_prob=%.2f, chars=%d) → returning empty",
                elapsed_ms,
                language_probability,
                len(text),
            )
            text = ""
        else:
            logger.info(
                "ElevenLabs STT %.0fms: lang_prob=%.2f, chars=%d",
                elapsed_ms,
                language_probability,
                len(text),
            )

        return web.json_response({"text": text})

    async def _handle_log_stt(self, request: web.Request) -> web.Response:
        """Receive a structured STT event from the browser and log it.

        Scribe v2 realtime streams audio directly from the browser to
        ElevenLabs over WebSocket, bypassing our ``/chat/transcribe``
        endpoint — so the server never sees the transcript bytes or
        latency. The browser fires this fire-and-forget POST whenever
        it gets a useful event (connect, commit, error, disconnect)
        so we can correlate STT activity with the rest of the chat
        log on disk.

        Body shape (all optional except ``event``):
            ``{"event": "connect" | "commit" | "error" | "disconnect",
              "chars"?: int, "latency_ms"?: number,
              "language_code"?: str, "detail"?: str}``

        Bounded fields so a misbehaving client can't flood the log.
        """
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)
        if not isinstance(body, dict):
            return web.json_response({"error": "body must be an object"}, status=400)

        event = str(body.get("event") or "").strip().lower()
        if event not in {"connect", "commit", "error", "disconnect", "partial"}:
            return web.json_response({"error": "unknown event"}, status=400)

        chars_raw = body.get("chars")
        chars = int(chars_raw) if isinstance(chars_raw, (int, float)) else None
        latency_raw = body.get("latency_ms")
        latency_ms = float(latency_raw) if isinstance(latency_raw, (int, float)) else None
        language_code = str(body.get("language_code") or "").strip()[:8]
        detail = str(body.get("detail") or "").strip()[:300]

        parts = [f"event={event}"]
        if chars is not None:
            parts.append(f"chars={chars}")
        if latency_ms is not None:
            parts.append(f"latency={latency_ms:.0f}ms")
        if language_code:
            parts.append(f"lang={language_code}")
        if detail:
            parts.append(f"detail={detail!r}")
        logger.info("ElevenLabs STT (client): %s", " ".join(parts))
        return web.json_response({"ok": True})

    async def _handle_scribe_token(self, request: web.Request) -> web.Response:
        """Issue a single-use ElevenLabs Scribe realtime token for the browser."""
        if not ELEVENLABS_API_KEY:
            return web.json_response({"error": "ELEVENLABS_API_KEY not set"}, status=503)

        start = time.perf_counter()
        try:
            if self._http_session is None:
                raise RuntimeError(
                    "HTTP session not initialised — chat_server start() must run first"
                )
            async with self._http_session.post(
                "https://api.elevenlabs.io/v1/single-use-token/realtime_scribe",
                headers={"xi-api-key": ELEVENLABS_API_KEY},
            ) as response:
                elapsed_ms = (time.perf_counter() - start) * 1000
                if response.status != 200:
                    body = await response.text()
                    logger.warning(
                        "ElevenLabs scribe-token error %d after %.0fms: %s",
                        response.status,
                        elapsed_ms,
                        body[:300],
                    )
                    return web.json_response({"error": f"upstream {response.status}"}, status=502)
                data = await response.json()
                logger.info("ElevenLabs scribe-token issued in %.0fms", elapsed_ms)
                return web.json_response({"token": data["token"]})
        except Exception as exc:
            logger.exception(
                "ElevenLabs scribe-token request failed after %.0fms",
                (time.perf_counter() - start) * 1000,
            )
            return web.json_response({"error": str(exc)}, status=502)

    async def _handle_speak(self, request: web.Request) -> web.StreamResponse:
        """Synthesize speech via ElevenLabs TTS and stream MP3 bytes.

        Expects JSON body ``{"text": str, "voice_id"?: str}``.
        Streams ``audio/mpeg`` back so the browser can start playing early.
        """
        if not ELEVENLABS_API_KEY:
            return web.json_response({"error": "ELEVENLABS_API_KEY not set"}, status=503)

        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)

        text: str = body.get("text", "").strip()
        if not text:
            return web.json_response({"error": "text is required"}, status=400)
        if len(text) > MAX_TTS_TEXT_LENGTH:
            text = text[:MAX_TTS_TEXT_LENGTH]

        voice_id: str = body.get("voice_id") or ELEVENLABS_DEFAULT_VOICE_ID
        url = ELEVENLABS_TTS_URL.format(voice_id=voice_id)

        logger.info(
            "ElevenLabs TTS request: chars=%d voice=%s model=%s",
            len(text),
            voice_id,
            ELEVENLABS_TTS_MODEL,
        )
        start = time.perf_counter()
        bytes_streamed = 0
        try:
            if self._http_session is None:
                raise RuntimeError(
                    "HTTP session not initialised — chat_server start() must run first"
                )
            async with self._http_session.post(
                url,
                headers={
                    "xi-api-key": ELEVENLABS_API_KEY,
                    "Content-Type": "application/json",
                },
                json={
                    "text": text,
                    "model_id": ELEVENLABS_TTS_MODEL,
                    "output_format": "mp3_44100_128",
                    "voice_settings": {"speed": 1.1},
                },
            ) as upstream:
                if upstream.status != 200:
                    err_body = await upstream.text()
                    logger.warning(
                        "ElevenLabs TTS error %d after %.0fms: %s",
                        upstream.status,
                        (time.perf_counter() - start) * 1000,
                        err_body[:300],
                    )
                    return web.json_response({"error": f"upstream {upstream.status}"}, status=502)

                first_byte_ms: float | None = None
                stream_response = web.StreamResponse(
                    status=200,
                    headers={
                        "Content-Type": "audio/mpeg",
                        "Cache-Control": "no-store",
                    },
                )
                await stream_response.prepare(request)
                async for chunk in upstream.content.iter_chunked(8192):
                    if first_byte_ms is None:
                        first_byte_ms = (time.perf_counter() - start) * 1000
                    bytes_streamed += len(chunk)
                    await stream_response.write(chunk)
                await stream_response.write_eof()
                logger.info(
                    "ElevenLabs TTS streamed %d bytes (ttfb=%.0fms total=%.0fms)",
                    bytes_streamed,
                    first_byte_ms if first_byte_ms is not None else 0.0,
                    (time.perf_counter() - start) * 1000,
                )
                return stream_response
        except Exception as exc:
            logger.exception(
                "ElevenLabs TTS request failed after %.0fms (streamed=%d bytes)",
                (time.perf_counter() - start) * 1000,
                bytes_streamed,
            )
            return web.json_response({"error": str(exc)}, status=502)


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
