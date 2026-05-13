"""Telegram handler factory for abyss bots."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from contextlib import suppress
from pathlib import Path
from typing import Any

from telegram import BotCommand, ForceReply, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from abyss import commands
from abyss.claude_runner import (
    STREAMING_CURSOR,
    cancel_process,
    cancel_sdk_session,
    is_process_running,
)
from abyss.config import (
    DEFAULT_MODEL,
    DEFAULT_STREAMING,
)
from abyss.group import (
    find_group_by_chat_id,
    get_my_role,
    log_to_shared_conversation,
)
from abyss.llm import LLMRequest, cached_backend, get_or_create
from abyss.session import (
    clear_claude_session_id,
    ensure_session,
    get_claude_session_id,
    load_bot_memory,
    load_conversation_history,
    log_conversation,
    save_claude_session_id,
)
from abyss.utils import markdown_to_telegram_html, split_message

logger = logging.getLogger(__name__)

SESSION_LOCKS: dict[str, asyncio.Lock] = {}
MAX_QUEUE_SIZE = 5


async def _send_command_result(
    update: Update,
    result: commands.CommandResult,
) -> None:
    """Render a ``CommandResult`` as one or more Telegram messages.

    Centralises the Markdown/HTML/file response logic so each handler
    can simply delegate to ``commands.cmd_*`` and call this helper.
    """

    if result.silent:
        return

    if result.file_path is not None:
        try:
            await update.effective_message.reply_document(
                document=open(result.file_path, "rb"),
                filename=result.file_path.name,
            )
        except Exception as error:
            await update.effective_message.reply_text(f"Failed to send file: {error}")
            logger.error("Failed to send file %s: %s", result.file_path, error)
        return

    if not result.text:
        return

    parse_mode = result.parse_mode
    if parse_mode == "HTML":
        # ``CommandResult.parse_mode == "HTML"`` signals "this text is
        # Markdown that needs Telegram-HTML conversion and chunking".
        html = markdown_to_telegram_html(result.text)
        for chunk in split_message(html):
            try:
                await update.effective_message.reply_text(chunk, parse_mode="HTML")
            except Exception:
                await update.effective_message.reply_text(chunk)
        return

    await update.effective_message.reply_text(result.text, parse_mode=parse_mode)


STREAM_THROTTLE_SECONDS = 0.5
STREAM_MIN_CHARS_BEFORE_SEND = 10
TELEGRAM_MESSAGE_LIMIT = 4096
STREAM_BUFFER_MARGIN = 100
DRAFT_ID = 1


def _get_session_lock(key: str) -> asyncio.Lock:
    """Get or create a session lock for the given key."""
    if key not in SESSION_LOCKS:
        SESSION_LOCKS[key] = asyncio.Lock()
    return SESSION_LOCKS[key]


def _is_user_allowed(user_id: int, allowed_users: list[int]) -> bool:
    """Check if user is allowed. Empty list means all users allowed."""
    if not allowed_users:
        return True
    return user_id in allowed_users


def _is_mentioned(message: Any, bot_username: str) -> bool:
    """Check if a bot is @mentioned in the message text.

    Args:
        message: Telegram message object.
        bot_username: Bot username with @ prefix (e.g., "@coder_bot").
    """
    text = getattr(message, "text", None) or ""
    username = bot_username.lstrip("@")
    return f"@{username}" in text


def _collect_mentioned_member_names(message_text: str, group_config: dict[str, Any]) -> list[str]:
    """Return the list of group member bot names @mentioned in the message text.

    Used by the orchestrator routing rule: when a user (or another bot) directly
    addresses one or more specific members, the orchestrator stays silent so the
    members can answer in-band.

    Args:
        message_text: Raw text of the inbound Telegram message.
        group_config: Group configuration dict (from group.yaml).
    """
    if not message_text:
        return []
    from abyss.config import load_bot_config

    mentioned: list[str] = []
    for member_name in group_config.get("members", []):
        member_config = load_bot_config(member_name)
        if not member_config:
            continue
        member_username = (member_config.get("telegram_username", "") or "").lstrip("@")
        if member_username and f"@{member_username}" in message_text:
            mentioned.append(member_name)
    return mentioned


def should_handle_group_message(
    update: Any,
    group_config: dict[str, Any],
    *,
    bot_name: str,
    bot_username: str,
) -> bool:
    """Direct-first group routing decision.

    Rules (Phase 1):
    - **Member**: respond to any @mention (user, orchestrator, or peer member).
    - **Orchestrator (user message)**: handle unless the user directly @mentioned
      one or more members without also mentioning the orchestrator. Without an
      @mention the orchestrator is the default responder.
    - **Orchestrator (bot message)**: only act when itself is @mentioned by a
      known group member — peer-to-peer member traffic no longer triggers an
      orchestrator Claude run (shared conversation still records it).

    Returns True if this bot should process the message.
    """

    my_role = get_my_role(group_config, bot_name)
    if my_role is None:
        return False

    message = update.effective_message
    message_text = getattr(message, "text", None) or ""
    from_user = message.from_user
    sender_is_bot = getattr(from_user, "is_bot", False)

    if my_role == "orchestrator":
        orchestrator_mentioned = _is_mentioned(message, bot_username)
        mentioned_members = _collect_mentioned_member_names(message_text, group_config)

        if not sender_is_bot:
            # User addresses specific members directly -> step aside.
            if mentioned_members and not orchestrator_mentioned:
                return False
            return True

        # Bot sender — only act if this orchestrator is explicitly @mentioned
        # AND the sender is a known group member (avoid responding to bots
        # outside the group that happen to share the chat).
        if not orchestrator_mentioned:
            return False
        sender_username = getattr(from_user, "username", "") or ""
        from abyss.config import load_bot_config

        for member_name in group_config.get("members", []):
            member_config = load_bot_config(member_name)
            if member_config:
                member_username = member_config.get("telegram_username", "").lstrip("@")
                if member_username and member_username == sender_username:
                    return True
        return False

    if my_role == "member":
        # Respond to @mention from anyone (user, orchestrator, peer member).
        return _is_mentioned(message, bot_username)

    return False


def make_handlers(bot_name: str, bot_path: Path, bot_config: dict[str, Any]) -> list:
    """Create Telegram handlers for a bot.

    Returns a list of handler instances to add to the Application.
    """
    allowed_users = bot_config.get("allowed_users", [])
    claude_arguments = bot_config.get("claude_args", [])
    command_timeout = bot_config.get("command_timeout", 300)
    current_model = bot_config.get("model", DEFAULT_MODEL)
    streaming_enabled = bot_config.get("streaming", DEFAULT_STREAMING)
    bot_username = bot_config.get("telegram_username", "")
    pending_cron_edits: dict[int, str] = {}  # chat_id -> job_name

    async def check_authorization(update: Update) -> bool:
        """Check if the user is authorized."""
        if not _is_user_allowed(update.effective_user.id, allowed_users):
            await update.effective_message.reply_text("Unauthorized.")
            return False
        return True

    def _make_context(update: Update, args: list[str] | None = None) -> commands.CommandContext:
        return commands.CommandContext(
            bot_name=bot_name,
            bot_path=bot_path,
            bot_config=bot_config,
            chat_id=update.effective_chat.id,
            args=args or [],
        )

    async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command - introduce the bot."""
        if not await check_authorization(update):
            return
        result = await commands.cmd_start(_make_context(update))
        await _send_command_result(update, result)

    async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command."""
        if not await check_authorization(update):
            return
        result = await commands.cmd_help(_make_context(update))
        await _send_command_result(update, result)

    async def reset_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /reset command.

        Pure reset logic lives in ``commands.cmd_reset``; this adapter
        closes the SDK pool sessions for every affected bot afterwards.
        """
        if not await check_authorization(update):
            return

        outcome = await commands.cmd_reset(_make_context(update))

        from abyss.sdk_client import get_pool, is_sdk_available

        if is_sdk_available():
            chat_id = update.effective_chat.id
            for affected in outcome.affected_bots:
                await get_pool().close_session(f"{affected}:{chat_id}")

        await _send_command_result(update, outcome.result)

    async def resetall_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /resetall command."""
        if not await check_authorization(update):
            return

        result = await commands.cmd_resetall(_make_context(update))

        from abyss.sdk_client import get_pool, is_sdk_available

        if is_sdk_available():
            chat_id = update.effective_chat.id
            await get_pool().close_session(f"{bot_name}:{chat_id}")

        await _send_command_result(update, result)

    async def files_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /files command."""
        if not await check_authorization(update):
            return
        result = await commands.cmd_files(_make_context(update))
        await _send_command_result(update, result)

    async def status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /status command."""
        if not await check_authorization(update):
            return
        result = await commands.cmd_status(_make_context(update))
        await _send_command_result(update, result)

    async def send_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /send command - send a workspace file to the user."""
        if not await check_authorization(update):
            return
        result = await commands.cmd_send(_make_context(update, context.args))
        await _send_command_result(update, result)

    async def model_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /model command - show or change the Claude model."""
        nonlocal current_model
        if not await check_authorization(update):
            return
        result = await commands.cmd_model(_make_context(update, context.args))
        # ``bot_config`` is the source of truth; re-sync the closure cache.
        current_model = bot_config.get("model", DEFAULT_MODEL)
        await _send_command_result(update, result)

    async def _cancel_for(target_bot: str, target_key: str) -> bool:
        """Cancel a bot's running task via its cached backend.

        Falls back to the legacy Claude Code cancel paths so bots
        that haven't yet talked to their backend (no cached
        instance) still get cancelled.
        """
        backend = cached_backend(target_bot)
        if backend is not None and await backend.cancel(target_key):
            return True
        if await cancel_sdk_session(target_key):
            return True
        if is_process_running(target_key) and cancel_process(target_key):
            return True
        return False

    async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /cancel command - stop running Claude Code process."""
        if not await check_authorization(update):
            return
        outcome = await commands.cmd_cancel(
            _make_context(update),
            cancel_for=_cancel_for,
        )
        await _send_command_result(update, outcome.result)

    async def streaming_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /streaming command - toggle streaming mode on/off."""
        nonlocal streaming_enabled
        if not await check_authorization(update):
            return
        result = await commands.cmd_streaming(_make_context(update, context.args))
        streaming_enabled = bot_config.get("streaming", DEFAULT_STREAMING)
        await _send_command_result(update, result)

    async def _send_non_streaming_response(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        working_directory: str,
        prompt: str,
        lock_key: str,
        claude_session_id: str | None = None,
        resume_session: bool = False,
        session_directory: Path | None = None,
    ) -> str:
        """Run Claude without streaming and send the response.

        Uses typing action + run_claude() + HTML conversion (Phase 3 style).
        Returns the final response text.
        """

        async def send_typing_periodically() -> None:
            try:
                while True:
                    await update.effective_message.chat.send_action("typing")
                    await asyncio.sleep(4)
            except asyncio.CancelledError:
                pass

        typing_task = asyncio.create_task(send_typing_periodically())

        backend = get_or_create(bot_name, bot_config)
        request = LLMRequest(
            bot_name=bot_name,
            bot_path=bot_path,
            session_directory=session_directory or working_directory,
            working_directory=working_directory,
            bot_config=bot_config,
            user_prompt=prompt,
            timeout=command_timeout,
            session_key=lock_key,
            extra_arguments=tuple(claude_arguments) if claude_arguments else (),
            claude_session_id=claude_session_id,
            resume_session=resume_session,
        )
        try:
            result = await backend.run(request)
            response = result.text
        finally:
            typing_task.cancel()

        html_response = markdown_to_telegram_html(response)
        chunks = split_message(html_response)
        for chunk in chunks:
            try:
                await update.effective_message.reply_text(chunk, parse_mode="HTML")
            except Exception:
                await update.effective_message.reply_text(chunk)

        return response

    async def _send_streaming_response(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        working_directory: str,
        prompt: str,
        lock_key: str,
        claude_session_id: str | None = None,
        resume_session: bool = False,
        session_directory: Path | None = None,
    ) -> str:
        """Run Claude with streaming via sendMessageDraft and send final response.

        Uses Telegram Bot API sendMessageDraft to stream partial text as a draft
        bubble while Claude generates. The draft disappears when the final message
        is sent. Falls back to editMessageText if sendMessageDraft fails.

        Returns the final response text.
        """
        chat_id = update.effective_chat.id
        accumulated_text = ""
        last_draft_time = 0.0
        draft_started = False
        draft_failed = False
        # Fallback state (editMessageText approach)
        fallback_message_id: int | None = None
        stream_stopped = False
        typing_task: asyncio.Task | None = None

        async def send_typing_until_draft() -> None:
            try:
                while True:
                    await update.effective_message.chat.send_action("typing")
                    await asyncio.sleep(4)
            except asyncio.CancelledError:
                pass

        async def on_text_chunk(chunk: str) -> None:
            nonlocal accumulated_text, last_draft_time, draft_started
            nonlocal draft_failed, fallback_message_id, stream_stopped, typing_task

            if stream_stopped:
                return

            accumulated_text += chunk
            now = time.monotonic()

            # Wait until enough text accumulated
            if len(accumulated_text) < STREAM_MIN_CHARS_BEFORE_SEND:
                return

            # Throttle updates
            if now - last_draft_time < STREAM_THROTTLE_SECONDS:
                return

            display = accumulated_text[: TELEGRAM_MESSAGE_LIMIT - 2]

            if not draft_failed:
                # Plain text during streaming; HTML-converting partial markdown causes flicker
                try:
                    await context.bot.send_message_draft(
                        chat_id=chat_id,
                        draft_id=DRAFT_ID,
                        text=display + STREAMING_CURSOR,
                    )
                    draft_started = True
                    last_draft_time = now
                    if typing_task is not None:
                        typing_task.cancel()
                    return
                except Exception as draft_error:
                    logger.debug("sendMessageDraft failed: %s", draft_error)
                    draft_failed = True
                # Fall through to editMessageText fallback

            # Fallback: editMessageText approach
            if len(accumulated_text) > TELEGRAM_MESSAGE_LIMIT - STREAM_BUFFER_MARGIN:
                stream_stopped = True
                return

            if fallback_message_id is None:
                try:
                    sent = await update.effective_message.reply_text(display + STREAMING_CURSOR)
                    fallback_message_id = sent.message_id
                    last_draft_time = now
                    if typing_task is not None:
                        typing_task.cancel()
                except Exception as send_error:
                    logger.debug("Stream fallback first send failed: %s", send_error)
                    stream_stopped = True
                return

            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=fallback_message_id,
                    text=display + STREAMING_CURSOR,
                )
                last_draft_time = now
            except Exception as edit_error:
                logger.debug("Stream fallback edit failed: %s", edit_error)
                stream_stopped = True

        backend = get_or_create(bot_name, bot_config)
        request = LLMRequest(
            bot_name=bot_name,
            bot_path=bot_path,
            session_directory=session_directory or working_directory,
            working_directory=working_directory,
            bot_config=bot_config,
            user_prompt=prompt,
            timeout=command_timeout,
            session_key=lock_key,
            extra_arguments=tuple(claude_arguments) if claude_arguments else (),
            claude_session_id=claude_session_id,
            resume_session=resume_session,
        )
        typing_task = asyncio.create_task(send_typing_until_draft())
        try:
            result = await backend.run_streaming(request, on_text_chunk)
        finally:
            typing_task.cancel()
        response = result.text

        # Clear the draft by sending an empty draft before final message
        if draft_started and not draft_failed:
            with suppress(Exception):
                await context.bot.send_message_draft(
                    chat_id=chat_id,
                    draft_id=DRAFT_ID,
                    text="",
                )

        # Send final formatted response
        html_response = markdown_to_telegram_html(response)
        chunks = split_message(html_response)

        if fallback_message_id is not None and not draft_started:
            # Fallback path: we used editMessageText during streaming
            if len(chunks) == 1 and len(chunks[0]) <= TELEGRAM_MESSAGE_LIMIT:
                try:
                    await context.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=fallback_message_id,
                        text=chunks[0],
                        parse_mode="HTML",
                    )
                except Exception:
                    with suppress(Exception):
                        await context.bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=fallback_message_id,
                            text=response,
                        )
            else:
                with suppress(Exception):
                    await context.bot.delete_message(
                        chat_id=chat_id,
                        message_id=fallback_message_id,
                    )
                for chunk in chunks:
                    try:
                        await update.effective_message.reply_text(chunk, parse_mode="HTML")
                    except Exception:
                        await update.effective_message.reply_text(chunk)
        else:
            # Draft path or no preview: send final message directly
            for chunk in chunks:
                try:
                    await update.effective_message.reply_text(chunk, parse_mode="HTML")
                except Exception:
                    await update.effective_message.reply_text(chunk)

        return response

    def _prepare_session_context(
        session_dir: Path, bot_path: Path, user_message: str
    ) -> tuple[str, str, bool]:
        """Prepare prompt with session continuity context.

        Returns (prompt, claude_session_id, resume_session).
        """
        claude_session_id = get_claude_session_id(session_dir)

        if claude_session_id:
            # Resume existing Claude Code session
            return user_message, claude_session_id, True

        # New session: bootstrap from global memory + bot memory + conversation.md
        from abyss.session import load_global_memory

        claude_session_id = str(uuid.uuid4())

        context_parts: list[str] = []

        global_memory = load_global_memory()
        if global_memory:
            context_parts.append(
                "아래는 글로벌 메모리입니다. 참고하세요 (수정 불가):\n\n" + global_memory
            )

        memory = load_bot_memory(bot_path)
        if memory:
            context_parts.append("아래는 장기 메모리입니다. 참고하세요:\n\n" + memory)

        history = load_conversation_history(session_dir)
        if history:
            context_parts.append("아래는 이전 대화 기록입니다. 맥락으로 활용하세요:\n\n" + history)

        if context_parts:
            prompt = "\n\n---\n\n".join(context_parts) + f"\n\n---\n\n새 메시지: {user_message}"
        else:
            prompt = user_message

        save_claude_session_id(session_dir, claude_session_id)
        return prompt, claude_session_id, False

    async def _call_with_resume_fallback(
        send_response_function,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        session_dir: Path,
        working_directory: str,
        prompt: str,
        lock_key: str,
        claude_session_id: str,
        resume_session: bool,
    ) -> str:
        """Call send_response with --resume fallback on failure."""
        try:
            return await send_response_function(
                update=update,
                context=context,
                working_directory=working_directory,
                prompt=prompt,
                lock_key=lock_key,
                claude_session_id=claude_session_id,
                resume_session=resume_session,
                session_directory=session_dir,
            )
        except RuntimeError:
            if not resume_session:
                raise
            # Session expired - fallback to bootstrap
            logger.warning(
                "Resume failed for session %s, falling back to bootstrap",
                claude_session_id,
            )
            clear_claude_session_id(session_dir)

            # Close broken pool session so a fresh client is created
            from abyss.sdk_client import get_pool, is_sdk_available

            if is_sdk_available():
                pool = get_pool()
                await pool.close_session(lock_key)

            new_session_id = str(uuid.uuid4())

            from abyss.session import load_global_memory

            fallback_parts: list[str] = []

            global_memory = load_global_memory()
            if global_memory:
                fallback_parts.append(
                    "아래는 글로벌 메모리입니다. 참고하세요 (수정 불가):\n\n" + global_memory
                )

            memory = load_bot_memory(bot_path)
            if memory:
                fallback_parts.append("아래는 장기 메모리입니다. 참고하세요:\n\n" + memory)

            history = load_conversation_history(session_dir)
            if history:
                fallback_parts.append(
                    "아래는 이전 대화 기록입니다. 맥락으로 활용하세요:\n\n" + history
                )

            if fallback_parts:
                # Original prompt was just the raw message for resume
                fallback_prompt = (
                    "\n\n---\n\n".join(fallback_parts) + f"\n\n---\n\n새 메시지: {prompt}"
                )
            else:
                fallback_prompt = prompt
            save_claude_session_id(session_dir, new_session_id)
            return await send_response_function(
                update=update,
                context=context,
                working_directory=working_directory,
                prompt=fallback_prompt,
                lock_key=lock_key,
                claude_session_id=new_session_id,
                resume_session=False,
                session_directory=session_dir,
            )

    def _should_handle_group_message(update: Update, group_config: dict[str, Any]) -> bool:
        """Closure delegating to module-level ``should_handle_group_message``."""
        return should_handle_group_message(
            update,
            group_config,
            bot_name=bot_name,
            bot_username=bot_username,
        )

    async def _process_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Core message processing logic — shared between individual and group modes."""
        chat_id = update.effective_chat.id
        user_message = update.effective_message.text
        lock_key = f"{bot_name}:{chat_id}"
        lock = _get_session_lock(lock_key)

        if lock.locked():
            await update.effective_message.reply_text(
                "\U0001f4e5 Message queued. Processing previous request..."
            )

        async with lock:
            session_dir = ensure_session(bot_path, chat_id, bot_name=bot_name)
            log_conversation(session_dir, "user", user_message)

            prompt, claude_session_id, resume_session = _prepare_session_context(
                session_dir, bot_path, user_message
            )

            send_response = (
                _send_streaming_response if streaming_enabled else _send_non_streaming_response
            )

            try:
                response = await _call_with_resume_fallback(
                    send_response_function=send_response,
                    update=update,
                    context=context,
                    session_dir=session_dir,
                    working_directory=str(session_dir),
                    prompt=prompt,
                    lock_key=lock_key,
                    claude_session_id=claude_session_id,
                    resume_session=resume_session,
                )
            except asyncio.CancelledError:
                response = "\u26d4 Execution was cancelled."
                logger.info("Claude cancelled for chat %d", chat_id)
                await update.effective_message.reply_text(response)
            except TimeoutError:
                response = "Request timed out. Please try a shorter request."
                logger.error("Claude timed out for chat %d", chat_id)
                await update.effective_message.reply_text(response)
            except RuntimeError as error:
                response = f"Error: {error}"
                logger.error("Claude error for chat %d: %s", chat_id, error)
                await update.effective_message.reply_text(response)

            log_conversation(session_dir, "assistant", response)

            # Log assistant response to shared group conversation
            group_config = find_group_by_chat_id(chat_id)
            if group_config is not None:
                log_to_shared_conversation(group_config["name"], f"@{bot_name}", response)

    async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle regular text messages - forward to Claude Code.

        Includes group branching logic:
        - If the chat is bound to a group, apply role-based filtering
        - Log all group messages to the shared conversation log
        - Otherwise, process as individual (DM) message
        """
        chat_id = update.effective_chat.id

        # Handle pending cron edit (ForceReply response)
        if chat_id in pending_cron_edits:
            if not await check_authorization(update):
                return
            job_name = pending_cron_edits.pop(chat_id)
            result = await commands.cmd_cron_edit_apply(
                _make_context(update),
                job_name,
                update.effective_message.text or "",
            )
            await _send_command_result(update, result)
            return

        group_config = find_group_by_chat_id(chat_id)

        if group_config is None:
            # No group binding — standard individual message handling
            if not await check_authorization(update):
                return
            await _process_message(update, context)
            return

        # --- Group mode ---
        user_message = update.effective_message.text or ""
        from_user = update.effective_message.from_user
        sender_is_bot = getattr(from_user, "is_bot", False)

        # In group mode, skip authorization for bot senders (orchestrator/member)
        # so that bot-to-bot @mention delegation works with allowed_users
        if not sender_is_bot and not await check_authorization(update):
            return

        # Log all group messages to shared conversation log
        if sender_is_bot:
            sender_display = f"@{getattr(from_user, 'username', 'unknown')}"
        else:
            sender_display = "user"
        log_to_shared_conversation(group_config["name"], sender_display, user_message)

        # Check if this bot should handle the message
        if not _should_handle_group_message(update, group_config):
            return

        await _process_message(update, context)

    async def version_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /version command."""
        if not await check_authorization(update):
            return
        result = await commands.cmd_version(_make_context(update))
        await _send_command_result(update, result)

    async def file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle photo/document messages - download to workspace and forward to Claude."""
        if not await check_authorization(update):
            return

        chat_id = update.effective_chat.id
        lock_key = f"{bot_name}:{chat_id}"
        lock = _get_session_lock(lock_key)

        if lock.locked():
            await update.effective_message.reply_text(
                "\U0001f4e5 Message queued. Processing previous request..."
            )

        async with lock:
            session_dir = ensure_session(bot_path, chat_id)
            workspace = session_dir / "workspace"

            # Determine file to download
            if update.effective_message.photo:
                photo = update.effective_message.photo[-1]  # largest size
                file = await photo.get_file()
                extension = ".jpg"
                filename = f"photo_{photo.file_unique_id}{extension}"
            elif update.effective_message.document:
                document = update.effective_message.document
                file = await document.get_file()
                filename = document.file_name or f"file_{document.file_unique_id}"
            else:
                return

            file_path = workspace / filename
            await file.download_to_drive(str(file_path))

            caption = update.effective_message.caption or ""
            if caption:
                user_prompt = f"{caption}\n\nFile: {file_path}"
            else:
                user_prompt = f"I sent a file: {file_path}"

            log_conversation(session_dir, "user", f"[file: {filename}] {caption}")

            prompt, claude_session_id, resume_session = _prepare_session_context(
                session_dir, bot_path, user_prompt
            )

            send_response = (
                _send_streaming_response if streaming_enabled else _send_non_streaming_response
            )

            try:
                response = await _call_with_resume_fallback(
                    send_response_function=send_response,
                    update=update,
                    context=context,
                    session_dir=session_dir,
                    working_directory=str(session_dir),
                    prompt=prompt,
                    lock_key=lock_key,
                    claude_session_id=claude_session_id,
                    resume_session=resume_session,
                )
            except asyncio.CancelledError:
                response = "\u26d4 Execution was cancelled."
                logger.info("Claude cancelled for chat %d", chat_id)
                await update.effective_message.reply_text(response)
            except TimeoutError:
                response = "Request timed out. Please try a shorter request."
                logger.error("Claude timed out for chat %d", chat_id)
                await update.effective_message.reply_text(response)
            except RuntimeError as error:
                response = f"Error: {error}"
                logger.error("Claude error for chat %d: %s", chat_id, error)
                await update.effective_message.reply_text(response)

            log_conversation(session_dir, "assistant", response)

    async def memory_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /memory command - show or clear bot memory."""
        if not await check_authorization(update):
            return
        result = await commands.cmd_memory(_make_context(update, context.args))
        await _send_command_result(update, result)

    async def skills_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /skills command - list, attach, or detach skills.

        ``cmd_skills`` mutates ``bot_config['skills']`` in place, so any
        downstream code reading ``bot_config`` (Claude prompt building,
        CLAUDE.md regen) picks up the change without a closure cache.
        """
        if not await check_authorization(update):
            return
        result = await commands.cmd_skills(_make_context(update, context.args))
        await _send_command_result(update, result)

    async def cron_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /cron command — list / add / remove / enable / disable / run / edit.

        Pure subcommands (list/add/remove/enable/disable) delegate to
        ``commands.cmd_cron``. ``run`` (Telegram ``send_message`` callback)
        and ``edit`` (ForceReply + ``pending_cron_edits``) stay here.
        """
        if not await check_authorization(update):
            return

        subcommand = context.args[0].lower() if context.args else ""

        if subcommand == "run":
            if len(context.args) < 2:
                await update.effective_message.reply_text(
                    "Usage: `/cron run <name>`", parse_mode="Markdown"
                )
                return

            from abyss.cron import execute_cron_job, get_cron_job

            job_name = context.args[1]
            cron_job = get_cron_job(bot_name, job_name)
            if not cron_job:
                await update.effective_message.reply_text(f"Job '{job_name}' not found.")
                return

            await update.effective_message.reply_text(f"⏰ Running job '{job_name}'...")

            async def send_typing_periodically() -> None:
                try:
                    while True:
                        await update.effective_message.chat.send_action("typing")
                        await asyncio.sleep(4)
                except asyncio.CancelledError:
                    pass

            typing_task = asyncio.create_task(send_typing_periodically())
            try:
                await execute_cron_job(
                    bot_name=bot_name,
                    job=cron_job,
                    bot_config=bot_config,
                    send_message_callback=context.bot.send_message,
                )
            except Exception as error:
                await update.effective_message.reply_text(f"Job failed: {error}")
            finally:
                typing_task.cancel()
            return

        if subcommand == "edit":
            if len(context.args) < 2:
                await update.effective_message.reply_text(
                    "Usage: `/cron edit <name>`", parse_mode="Markdown"
                )
                return
            job_name = context.args[1]
            outcome = await commands.cmd_cron_edit_start(_make_context(update), job_name)
            if isinstance(outcome, commands.CommandResult):
                await _send_command_result(update, outcome)
                return
            pending_cron_edits[update.effective_chat.id] = outcome.job_name
            await update.effective_message.reply_text(
                outcome.prompt_text,
                parse_mode="Markdown",
                reply_markup=ForceReply(selective=True),
            )
            return

        if subcommand == "add":
            # Pre-message keeps the original Telegram UX while the
            # Claude natural-language parse runs.
            await update.effective_message.reply_text("⏰ Parsing schedule...")

        result = await commands.cmd_cron(_make_context(update, context.args))
        await _send_command_result(update, result)

    async def heartbeat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /heartbeat command - manage heartbeat settings.

        ``status``/``on``/``off`` are delegated to ``commands.cmd_heartbeat``.
        ``run`` requires a Telegram-specific ``send_message`` callback so
        it stays in this adapter.
        """
        if not await check_authorization(update):
            return

        if context.args and context.args[0].lower() == "run":
            from abyss.heartbeat import execute_heartbeat

            await update.effective_message.reply_text("\U0001f493 Running heartbeat check...")

            async def send_typing_periodically() -> None:
                try:
                    while True:
                        await update.effective_message.chat.send_action("typing")
                        await asyncio.sleep(4)
                except asyncio.CancelledError:
                    pass

            typing_task = asyncio.create_task(send_typing_periodically())
            try:
                await execute_heartbeat(
                    bot_name=bot_name,
                    bot_config=bot_config,
                    send_message_callback=context.bot.send_message,
                )
                await update.effective_message.reply_text("\U0001f493 Heartbeat check completed.")
            except Exception as error:
                await update.effective_message.reply_text(f"Heartbeat failed: {error}")
            finally:
                typing_task.cancel()
            return

        result = await commands.cmd_heartbeat(_make_context(update, context.args))
        await _send_command_result(update, result)

    async def compact_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /compact command — compress MD files to save tokens.

        Pre-message + typing indicator stay here; the actual collect →
        run → save → regen pipeline lives in ``commands.cmd_compact_*``.
        """
        if not await check_authorization(update):
            return

        ctx = _make_context(update, context.args)
        preview = await commands.cmd_compact_preview(ctx)
        if not preview.targets:
            await update.effective_message.reply_text(preview.text)
            return
        await update.effective_message.reply_text(preview.text)

        async def send_typing_periodically() -> None:
            try:
                while True:
                    await update.effective_message.chat.send_action("typing")
                    await asyncio.sleep(4)
            except asyncio.CancelledError:
                pass

        typing_task = asyncio.create_task(send_typing_periodically())
        try:
            result = await commands.cmd_compact_run(ctx)
            for chunk in split_message(result.text):
                await update.effective_message.reply_text(chunk)
        finally:
            typing_task.cancel()

    async def bind_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /bind command — bind a group to a Telegram chat."""
        if not await check_authorization(update):
            return
        result = await commands.cmd_bind(_make_context(update, context.args))
        await _send_command_result(update, result)

    async def unbind_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /unbind command — remove group binding from this chat."""
        if not await check_authorization(update):
            return
        result = await commands.cmd_unbind(_make_context(update))
        await _send_command_result(update, result)

    handlers = [
        CommandHandler("start", start_handler),
        CommandHandler("help", help_handler),
        CommandHandler("reset", reset_handler),
        CommandHandler("resetall", resetall_handler),
        CommandHandler("files", files_handler),
        CommandHandler("send", send_handler),
        CommandHandler("status", status_handler),
        CommandHandler("model", model_handler),
        CommandHandler("version", version_handler),
        CommandHandler("cancel", cancel_handler),
        CommandHandler("streaming", streaming_handler),
        CommandHandler("memory", memory_handler),
        CommandHandler("skills", skills_handler),
        CommandHandler("cron", cron_handler),
        CommandHandler("heartbeat", heartbeat_handler),
        CommandHandler("compact", compact_handler),
        CommandHandler("bind", bind_handler),
        CommandHandler("unbind", unbind_handler),
        MessageHandler(filters.PHOTO | filters.Document.ALL, file_handler),
        MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler),
    ]

    return handlers


BOT_COMMANDS = [
    BotCommand("start", "\U0001f44b Bot introduction"),
    BotCommand("reset", "\U0001f504 Clear conversation"),
    BotCommand("resetall", "\U0001f5d1 Delete entire session"),
    BotCommand("files", "\U0001f4c2 List workspace files"),
    BotCommand("send", "\U0001f4e4 Send workspace file"),
    BotCommand("status", "\U0001f4ca Session status"),
    BotCommand("model", "\U0001f9e0 Show or change model"),
    BotCommand("memory", "\U0001f9e0 Show or clear memory"),
    BotCommand("skills", "\U0001f9e9 Skill management"),
    BotCommand("cron", "\u23f0 Cron job management"),
    BotCommand("heartbeat", "\U0001f493 Heartbeat management"),
    BotCommand("compact", "\U0001f4e6 Compact MD files"),
    BotCommand("streaming", "\U0001f4e1 Toggle streaming mode"),
    BotCommand("cancel", "\u26d4 Stop running process"),
    BotCommand("bind", "\U0001f517 Bind group to this chat"),
    BotCommand("unbind", "\U0001f517 Unbind group from this chat"),
    BotCommand("version", "\U00002139 Show version"),
    BotCommand("help", "\U00002753 Show commands"),
]


async def set_bot_commands(application: Application) -> None:
    """Register slash commands with Telegram (called after start_polling)."""
    await application.bot.set_my_commands(BOT_COMMANDS)
    logger.info("Registered %d bot commands with Telegram", len(BOT_COMMANDS))
