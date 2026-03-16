"""Telegram handler factory for cclaw bots."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from contextlib import suppress
from pathlib import Path
from typing import Any

from telegram import BotCommand, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from cclaw.claude_runner import (
    STREAMING_CURSOR,
    cancel_process,
    cancel_sdk_session,
    is_process_running,
    run_claude_streaming_with_sdk,
    run_claude_with_sdk,
)
from cclaw.config import (
    DEFAULT_MODEL,
    DEFAULT_STREAMING,
    VALID_MODELS,
    is_valid_model,
    model_display_name,
    save_bot_config,
)
from cclaw.group import (
    bind_group,
    clear_shared_conversation,
    find_group_by_chat_id,
    get_my_role,
    load_group_config,
    log_to_shared_conversation,
    unbind_group,
)
from cclaw.session import (
    clear_bot_memory,
    clear_claude_session_id,
    conversation_status_summary,
    ensure_session,
    get_claude_session_id,
    list_workspace_files,
    load_bot_memory,
    load_conversation_history,
    log_conversation,
    reset_all_session,
    reset_session,
    save_claude_session_id,
)
from cclaw.utils import markdown_to_telegram_html, split_message

logger = logging.getLogger(__name__)

SESSION_LOCKS: dict[str, asyncio.Lock] = {}
MAX_QUEUE_SIZE = 5

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


def make_handlers(bot_name: str, bot_path: Path, bot_config: dict[str, Any]) -> list:
    """Create Telegram handlers for a bot.

    Returns a list of handler instances to add to the Application.
    """
    allowed_users = bot_config.get("allowed_users", [])
    personality = bot_config.get("personality", "")
    display_name = bot_config.get("display_name", "")
    role = bot_config.get("role", bot_config.get("description", ""))
    goal = bot_config.get("goal", "")
    claude_arguments = bot_config.get("claude_args", [])
    command_timeout = bot_config.get("command_timeout", 300)
    current_model = bot_config.get("model", DEFAULT_MODEL)
    streaming_enabled = bot_config.get("streaming", DEFAULT_STREAMING)
    attached_skills = bot_config.get("skills", [])
    bot_username = bot_config.get("telegram_username", "")

    async def check_authorization(update: Update) -> bool:
        """Check if the user is authorized."""
        if not _is_user_allowed(update.effective_user.id, allowed_users):
            await update.effective_message.reply_text("Unauthorized.")
            return False
        return True

    async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command - introduce the bot."""
        if not await check_authorization(update):
            return

        name_display = display_name or bot_name
        text = (
            f"\U0001f916 *{name_display}*\n\n"
            f"\U0001f3ad *Personality:* {personality}\n"
            f"\U0001f4bc *Role:* {role}\n"
        )
        if goal:
            text += f"\U0001f3af *Goal:* {goal}\n"
        text += (
            "\n\U0001f4ac Send me a message to start chatting!\n"
            "\U00002753 Type /help for available commands."
        )
        await update.effective_message.reply_text(text, parse_mode="Markdown")

    async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command."""
        if not await check_authorization(update):
            return

        text = (
            "\U0001f4cb *Available Commands:*\n\n"
            "\U0001f44b /start - Bot introduction\n"
            "\U0001f504 /reset - Clear conversation (keep workspace)\n"
            "\U0001f5d1 /resetall - Delete entire session\n"
            "\U0001f4c2 /files - List workspace files\n"
            "\U0001f4e4 /send - Send workspace file\n"
            "\U0001f4ca /status - Session status\n"
            "\U0001f9e0 /model - Show or change model\n"
            "\U0001f4e1 /streaming - Toggle streaming mode\n"
            "\U0001f9e0 /memory - Show or clear memory\n"
            "\U0001f9e9 /skills - Skill management\n"
            "\u23f0 /cron - Cron job management\n"
            "\U0001f493 /heartbeat - Heartbeat management\n"
            "\U0001f4e6 /compact - Compact MD files\n"
            "\u26d4 /cancel - Stop running process\n"
            "\U00002139 /version - Show version\n"
            "\U00002753 /help - Show this message"
        )
        await update.effective_message.reply_text(text, parse_mode="Markdown")

    async def reset_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /reset command.

        In group mode, only the orchestrator handles /reset:
        - Resets all bots' group sessions (orchestrator + members)
        - Clears shared conversation log
        - Preserves shared workspace files
        In DM mode, resets only this bot's session.
        """
        if not await check_authorization(update):
            return

        chat_id = update.effective_chat.id
        group_config = find_group_by_chat_id(chat_id)

        # Close pool sessions so fresh clients are created after reset
        from cclaw.sdk_client import get_pool, is_sdk_available

        if group_config is not None:
            my_role = get_my_role(group_config, bot_name)
            if my_role != "orchestrator":
                return  # Only orchestrator handles group /reset

            from cclaw.config import bot_directory as get_bot_directory

            # Reset orchestrator's own session
            reset_session(bot_path, chat_id)
            if is_sdk_available():
                await get_pool().close_session(f"{bot_name}:{chat_id}")

            # Reset all member bots' sessions for this chat_id
            for member_name in group_config.get("members", []):
                member_path = get_bot_directory(member_name)
                reset_session(member_path, chat_id)
                if is_sdk_available():
                    await get_pool().close_session(f"{member_name}:{chat_id}")

            # Clear shared conversation log
            clear_shared_conversation(group_config["name"])

            message = (
                "\U0001f504 Group session reset. Shared conversation cleared. Workspace preserved."
            )
        else:
            reset_session(bot_path, chat_id)
            if is_sdk_available():
                await get_pool().close_session(f"{bot_name}:{chat_id}")
            message = "\U0001f504 Conversation reset. Workspace files preserved."

        await update.effective_message.reply_text(message)

    async def resetall_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /resetall command."""
        if not await check_authorization(update):
            return

        chat_id = update.effective_chat.id
        reset_all_session(bot_path, chat_id)
        # Close pool session
        from cclaw.sdk_client import get_pool, is_sdk_available

        if is_sdk_available():
            await get_pool().close_session(f"{bot_name}:{chat_id}")
        await update.effective_message.reply_text("\U0001f5d1 Session completely reset.")

    async def files_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /files command."""
        if not await check_authorization(update):
            return

        chat_id = update.effective_chat.id
        session_directory = ensure_session(bot_path, chat_id)
        files = list_workspace_files(session_directory)

        if not files:
            await update.effective_message.reply_text("\U0001f4c2 No files in workspace.")
            return

        file_list = "\n".join(f"  {f}" for f in files)
        text = f"\U0001f4c2 *Workspace files:*\n```\n{file_list}\n```"
        await update.effective_message.reply_text(text, parse_mode="Markdown")

    async def status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /status command."""
        if not await check_authorization(update):
            return

        chat_id = update.effective_chat.id
        session_directory = ensure_session(bot_path, chat_id)

        conversation_status = conversation_status_summary(session_directory)

        files = list_workspace_files(session_directory)

        text = (
            f"\U0001f4ca *Session Status*\n\n"
            f"\U0001f916 Bot: {bot_name}\n"
            f"\U0001f4ac Chat ID: {chat_id}\n"
            f"\U0001f4dd Conversation: {conversation_status}\n"
            f"\U0001f4c2 Workspace files: {len(files)}"
        )
        await update.effective_message.reply_text(text, parse_mode="Markdown")

    async def send_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /send command - send a workspace file to the user."""
        if not await check_authorization(update):
            return

        chat_id = update.effective_chat.id
        session_directory = ensure_session(bot_path, chat_id)
        workspace = session_directory / "workspace"

        if not context.args:
            files = list_workspace_files(session_directory)
            if not files:
                await update.effective_message.reply_text("\U0001f4c2 No files in workspace.")
                return
            file_list = "\n".join(f"  {f}" for f in files)
            text = f"\U0001f4e4 Usage: `/send filename`\n\nAvailable files:\n```\n{file_list}\n```"
            await update.effective_message.reply_text(text, parse_mode="Markdown")
            return

        filename = " ".join(context.args)
        file_path = workspace / filename

        if not file_path.exists():
            await update.effective_message.reply_text(
                f"File not found: `{filename}`", parse_mode="Markdown"
            )
            return

        if not file_path.is_file():
            await update.effective_message.reply_text(
                f"Not a file: `{filename}`", parse_mode="Markdown"
            )
            return

        try:
            await update.effective_message.reply_document(
                document=open(file_path, "rb"),
                filename=file_path.name,
            )
        except Exception as error:
            await update.effective_message.reply_text(f"Failed to send file: {error}")
            logger.error("Failed to send file %s: %s", filename, error)

    async def model_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /model command - show or change the Claude model."""
        nonlocal current_model
        if not await check_authorization(update):
            return

        if not context.args:
            model_list = " / ".join(
                f"*{model_display_name(m)}*" if m == current_model else model_display_name(m)
                for m in VALID_MODELS
            )
            text = (
                f"\U0001f9e0 Current model: *{model_display_name(current_model)}*\n\n"
                f"Available: {model_list}\n"
                "Usage: `/model sonnet`"
            )
            await update.effective_message.reply_text(text, parse_mode="Markdown")
            return

        new_model = context.args[0].lower()
        if not is_valid_model(new_model):
            await update.effective_message.reply_text(
                f"Invalid model: `{new_model}`\nAvailable: {', '.join(VALID_MODELS)}",
                parse_mode="Markdown",
            )
            return

        current_model = new_model
        bot_config["model"] = new_model
        save_bot_config(bot_name, bot_config)
        await update.effective_message.reply_text(
            f"\U0001f9e0 Model changed to *{model_display_name(new_model)}*",
            parse_mode="Markdown",
        )

    async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /cancel command - stop running Claude Code process.

        In group mode, only the orchestrator handles /cancel:
        - Cancels all bots' running processes for this group chat
        - Does not affect DM processes
        In DM mode, cancels only this bot's process.
        """
        if not await check_authorization(update):
            return

        chat_id = update.effective_chat.id
        group_config = find_group_by_chat_id(chat_id)

        if group_config is not None:
            my_role = get_my_role(group_config, bot_name)
            if my_role != "orchestrator":
                return  # Only orchestrator handles group /cancel

            cancelled_bots: list[str] = []

            # Cancel orchestrator's own process (SDK first, then subprocess)
            orchestrator_key = f"{bot_name}:{chat_id}"
            if await cancel_sdk_session(orchestrator_key):
                cancelled_bots.append(bot_name)
            elif is_process_running(orchestrator_key) and cancel_process(orchestrator_key):
                cancelled_bots.append(bot_name)

            # Cancel all member bots' processes
            for member_name in group_config.get("members", []):
                member_key = f"{member_name}:{chat_id}"
                if await cancel_sdk_session(member_key):
                    cancelled_bots.append(member_name)
                elif is_process_running(member_key) and cancel_process(member_key):
                    cancelled_bots.append(member_name)

            if cancelled_bots:
                names = ", ".join(cancelled_bots)
                await update.effective_message.reply_text(f"\u26d4 Cancelled: {names}")
            else:
                await update.effective_message.reply_text("No running processes in group.")
            return

        session_key = f"{bot_name}:{chat_id}"

        # Try SDK interrupt first, then subprocess fallback
        sdk_cancelled = await cancel_sdk_session(session_key)
        if sdk_cancelled:
            await update.effective_message.reply_text("\u26d4 Execution cancelled.")
            return

        if not is_process_running(session_key):
            await update.effective_message.reply_text("No running process to cancel.")
            return

        cancelled = cancel_process(session_key)
        if cancelled:
            await update.effective_message.reply_text("\u26d4 Execution cancelled.")
        else:
            await update.effective_message.reply_text("No running process to cancel.")

    async def streaming_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /streaming command - toggle streaming mode on/off."""
        nonlocal streaming_enabled
        if not await check_authorization(update):
            return

        if not context.args:
            status_text = "on" if streaming_enabled else "off"
            text = (
                f"\U0001f4e1 Streaming: *{status_text}*\n\n"
                "Usage: `/streaming on` or `/streaming off`"
            )
            await update.effective_message.reply_text(text, parse_mode="Markdown")
            return

        value = context.args[0].lower()
        if value == "on":
            streaming_enabled = True
            bot_config["streaming"] = True
            save_bot_config(bot_name, bot_config)
            await update.effective_message.reply_text(
                "\U0001f4e1 Streaming enabled.", parse_mode="Markdown"
            )
        elif value == "off":
            streaming_enabled = False
            bot_config["streaming"] = False
            save_bot_config(bot_name, bot_config)
            await update.effective_message.reply_text(
                "\U0001f4e1 Streaming disabled.", parse_mode="Markdown"
            )
        else:
            await update.effective_message.reply_text(
                "Usage: `/streaming on` or `/streaming off`",
                parse_mode="Markdown",
            )

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

        try:
            response = await run_claude_with_sdk(
                working_directory=working_directory,
                message=prompt,
                extra_arguments=claude_arguments if claude_arguments else None,
                timeout=command_timeout,
                session_key=lock_key,
                model=current_model,
                skill_names=attached_skills if attached_skills else None,
                claude_session_id=claude_session_id,
                resume_session=resume_session,
                session_directory=session_directory,
            )
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

        async def on_text_chunk(chunk: str) -> None:
            nonlocal accumulated_text, last_draft_time, draft_started
            nonlocal draft_failed, fallback_message_id, stream_stopped

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
                # Primary: sendMessageDraft
                try:
                    await context.bot.send_message_draft(
                        chat_id=chat_id,
                        draft_id=DRAFT_ID,
                        text=display + STREAMING_CURSOR,
                    )
                    draft_started = True
                    last_draft_time = now
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

        response = await run_claude_streaming_with_sdk(
            working_directory=working_directory,
            message=prompt,
            on_text_chunk=on_text_chunk,
            extra_arguments=claude_arguments if claude_arguments else None,
            timeout=command_timeout,
            session_key=lock_key,
            model=current_model,
            skill_names=attached_skills if attached_skills else None,
            claude_session_id=claude_session_id,
            resume_session=resume_session,
            session_directory=session_directory,
        )

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
        from cclaw.session import load_global_memory

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
            from cclaw.sdk_client import get_pool, is_sdk_available

            if is_sdk_available():
                pool = get_pool()
                await pool.close_session(lock_key)

            new_session_id = str(uuid.uuid4())

            from cclaw.session import load_global_memory

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
        """Determine if this bot should process a group message.

        Group branching rules:
        - Orchestrator: handles user (non-bot) messages and member bot messages
        - Member: only handles messages where it is @mentioned by a bot (not user)
        - If the bot is not in the group, it should not handle the message

        Returns True if this bot should process the message.
        """
        my_role = get_my_role(group_config, bot_name)
        if my_role is None:
            return False

        from_user = update.effective_message.from_user
        sender_is_bot = getattr(from_user, "is_bot", False)

        if my_role == "orchestrator":
            if not sender_is_bot:
                # User (boss) message -> orchestrator handles
                return True
            # Bot message -> orchestrator checks if sender is a group member
            sender_username = getattr(from_user, "username", "") or ""
            members = group_config.get("members", [])
            for member_name in members:
                from cclaw.config import load_bot_config

                member_config = load_bot_config(member_name)
                if member_config:
                    member_username = member_config.get("telegram_username", "").lstrip("@")
                    if member_username and member_username == sender_username:
                        return True
            return False

        if my_role == "member":
            # Member only responds when @mentioned by a bot (orchestrator)
            if sender_is_bot and _is_mentioned(update.effective_message, bot_username):
                return True
            return False

        return False

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

        from cclaw import __version__

        await update.effective_message.reply_text(f"\U00002139 cclaw v{__version__}")

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

        if not context.args:
            memory_content = load_bot_memory(bot_path)
            if not memory_content:
                await update.effective_message.reply_text("\U0001f9e0 No memories saved yet.")
                return
            html = markdown_to_telegram_html(memory_content)
            chunks = split_message(html)
            for chunk in chunks:
                try:
                    await update.effective_message.reply_text(chunk, parse_mode="HTML")
                except Exception:
                    await update.effective_message.reply_text(chunk)
            return

        subcommand = context.args[0].lower()

        if subcommand == "clear":
            clear_bot_memory(bot_path)
            await update.effective_message.reply_text("\U0001f9e0 Memory cleared.")
        else:
            await update.effective_message.reply_text(
                "Usage: `/memory` (show) or `/memory clear`",
                parse_mode="Markdown",
            )

    async def skills_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /skills command - list, attach, or detach skills."""
        nonlocal attached_skills
        if not await check_authorization(update):
            return

        if not context.args:
            from cclaw.builtin_skills import list_builtin_skills
            from cclaw.skill import bots_using_skill, list_skills

            installed_skills = list_skills()
            installed_names = {skill["name"] for skill in installed_skills}
            builtin_skills = list_builtin_skills()
            not_installed_builtins = [
                skill for skill in builtin_skills if skill["name"] not in installed_names
            ]

            if not installed_skills and not not_installed_builtins:
                await update.effective_message.reply_text("\U0001f9e9 No skills available.")
                return

            builtin_names = {skill["name"] for skill in builtin_skills}

            lines = ["\U0001f9e9 *All Skills:*\n"]
            for skill in installed_skills:
                type_display = "builtin" if skill["name"] in builtin_names else "custom"
                if skill["status"] == "active":
                    status_icon = "\u2705"
                else:
                    status_icon = "\U0001f6d1"
                connected_bots = bots_using_skill(skill["name"])
                attached_label = f" \u2190 {', '.join(connected_bots)}" if connected_bots else ""
                lines.append(f"{status_icon} `{skill['name']}` ({type_display}){attached_label}")

            for skill in not_installed_builtins:
                lines.append(f"\U0001f4e6 `{skill['name']}` (builtin, not installed)")

            lines.append("")
            lines.append("`/skills attach <name>` | `/skills detach <name>`")

            await update.effective_message.reply_text("\n".join(lines), parse_mode="Markdown")
            return

        subcommand = context.args[0].lower()

        if subcommand == "list":
            if not attached_skills:
                await update.effective_message.reply_text(
                    "\U0001f9e9 No skills attached to this bot."
                )
                return
            skill_list = "\n".join(f"  - {s}" for s in attached_skills)
            await update.effective_message.reply_text(
                f"\U0001f9e9 *Attached Skills:*\n```\n{skill_list}\n```",
                parse_mode="Markdown",
            )

        elif subcommand == "attach":
            if len(context.args) < 2:
                await update.effective_message.reply_text(
                    "Usage: `/skills attach <name>`", parse_mode="Markdown"
                )
                return

            from cclaw.skill import attach_skill_to_bot, is_skill, skill_status

            skill_name = context.args[1]
            if not is_skill(skill_name):
                await update.effective_message.reply_text(f"Skill '{skill_name}' not found.")
                return

            status = skill_status(skill_name)
            if status == "inactive":
                await update.effective_message.reply_text(
                    f"Skill '{skill_name}' is inactive. "
                    f"Run `cclaw skills setup {skill_name}` first.",
                    parse_mode="Markdown",
                )
                return

            if skill_name in attached_skills:
                await update.effective_message.reply_text(
                    f"Skill '{skill_name}' is already attached."
                )
                return

            attach_skill_to_bot(bot_name, skill_name)
            bot_config.setdefault("skills", [])
            if skill_name not in bot_config["skills"]:
                bot_config["skills"].append(skill_name)
            attached_skills = bot_config["skills"]
            await update.effective_message.reply_text(f"\U0001f9e9 Skill '{skill_name}' attached.")

        elif subcommand == "detach":
            if len(context.args) < 2:
                await update.effective_message.reply_text(
                    "Usage: `/skills detach <name>`", parse_mode="Markdown"
                )
                return

            from cclaw.skill import detach_skill_from_bot

            skill_name = context.args[1]
            if skill_name not in attached_skills:
                await update.effective_message.reply_text(f"Skill '{skill_name}' is not attached.")
                return

            detach_skill_from_bot(bot_name, skill_name)
            if skill_name in bot_config.get("skills", []):
                bot_config["skills"].remove(skill_name)
            attached_skills = bot_config.get("skills", [])
            await update.effective_message.reply_text(f"\U0001f9e9 Skill '{skill_name}' detached.")

        else:
            await update.effective_message.reply_text(
                "Unknown subcommand. Use: list, attach, detach",
            )

    async def cron_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /cron command - list or run cron jobs."""
        if not await check_authorization(update):
            return

        from cclaw.cron import (
            add_cron_job,
            disable_cron_job,
            enable_cron_job,
            execute_cron_job,
            generate_unique_job_name,
            get_cron_job,
            list_cron_jobs,
            next_run_time,
            parse_natural_language_schedule,
            remove_cron_job,
            resolve_default_timezone,
        )

        if not context.args:
            text = (
                "\u23f0 *Cron Commands:*\n\n"
                "`/cron list` - Show cron jobs\n"
                "`/cron add <description>` - Create a job\n"
                "`/cron run <name>` - Run a job now\n"
                "`/cron remove <name>` - Remove a job\n"
                "`/cron enable <name>` - Enable a job\n"
                "`/cron disable <name>` - Disable a job"
            )
            await update.effective_message.reply_text(text, parse_mode="Markdown")
            return

        subcommand = context.args[0].lower()

        if subcommand == "list":
            jobs = list_cron_jobs(bot_name)
            if not jobs:
                await update.effective_message.reply_text("\u23f0 No cron jobs configured.")
                return

            lines = ["\u23f0 *Cron Jobs:*\n"]
            for job in jobs:
                enabled = job.get("enabled", True)
                status_icon = "\u2705" if enabled else "\U0001f6d1"
                schedule_display = job.get("schedule") or f"at: {job.get('at', 'N/A')}"
                timezone_label = job.get("timezone", resolve_default_timezone())
                next_time = next_run_time(job) if enabled else None
                next_display = next_time.strftime("%m-%d %H:%M") if next_time else "-"
                message_preview = job.get("message", "")[:30]
                lines.append(
                    f"{status_icon} `{job['name']}` (`{schedule_display}` {timezone_label})\n"
                    f"   Next: {next_display} | {message_preview}"
                )
            await update.effective_message.reply_text("\n".join(lines), parse_mode="Markdown")

        elif subcommand == "run":
            if len(context.args) < 2:
                await update.effective_message.reply_text(
                    "Usage: `/cron run <name>`", parse_mode="Markdown"
                )
                return

            job_name = context.args[1]
            cron_job = get_cron_job(bot_name, job_name)
            if not cron_job:
                await update.effective_message.reply_text(f"Job '{job_name}' not found.")
                return

            await update.effective_message.reply_text(f"\u23f0 Running job '{job_name}'...")

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

        elif subcommand == "add":
            if len(context.args) < 2:
                await update.effective_message.reply_text(
                    "Usage: `/cron add <description>`\n"
                    "Example: `/cron add 매일 아침 9시에 이메일 요약해줘`",
                    parse_mode="Markdown",
                )
                return

            user_input = " ".join(context.args[1:])
            await update.effective_message.reply_text("\u23f0 Parsing schedule...")

            try:
                timezone_name = resolve_default_timezone()
                parsed = await parse_natural_language_schedule(
                    user_input,
                    timezone_name,
                )
            except (ValueError, RuntimeError) as error:
                await update.effective_message.reply_text(
                    f"Failed to parse: {error}\n\n"
                    "Example: `/cron add 매일 아침 9시에 이메일 요약해줘`",
                    parse_mode="Markdown",
                )
                return

            job_name = generate_unique_job_name(bot_name, parsed["name"])

            job: dict[str, Any] = {
                "name": job_name,
                "message": parsed["message"],
                "timezone": timezone_name,
                "enabled": True,
            }

            if parsed["type"] == "recurring":
                job["schedule"] = parsed["schedule"]
            else:
                job["at"] = parsed["at"]
                job["delete_after_run"] = True

            try:
                add_cron_job(bot_name, job)
            except ValueError as error:
                await update.effective_message.reply_text(f"Failed: {error}")
                return

            from cclaw.cron import next_run_time as compute_next_run

            next_time = compute_next_run(job)
            next_display = next_time.strftime("%m-%d %H:%M") if next_time else "-"

            if parsed["type"] == "recurring":
                schedule_line = f"Schedule: `{parsed['schedule']}` ({timezone_name})"
            else:
                schedule_line = f"Run at: {parsed['at']} ({timezone_name})"

            await update.effective_message.reply_text(
                f"\u23f0 *Cron job created:*\n\n"
                f"  Name: `{job_name}`\n"
                f"  {schedule_line}\n"
                f"  Message: {parsed['message']}\n"
                f"  Next: {next_display}",
                parse_mode="Markdown",
            )

        elif subcommand == "remove":
            if len(context.args) < 2:
                await update.effective_message.reply_text(
                    "Usage: `/cron remove <name>`",
                    parse_mode="Markdown",
                )
                return

            job_name = context.args[1]
            if remove_cron_job(bot_name, job_name):
                await update.effective_message.reply_text(
                    f"\u23f0 Job `{job_name}` removed.",
                    parse_mode="Markdown",
                )
            else:
                await update.effective_message.reply_text(f"Job '{job_name}' not found.")

        elif subcommand == "enable":
            if len(context.args) < 2:
                await update.effective_message.reply_text(
                    "Usage: `/cron enable <name>`",
                    parse_mode="Markdown",
                )
                return

            job_name = context.args[1]
            if enable_cron_job(bot_name, job_name):
                await update.effective_message.reply_text(
                    f"\u2705 Job `{job_name}` enabled.",
                    parse_mode="Markdown",
                )
            else:
                await update.effective_message.reply_text(f"Job '{job_name}' not found.")

        elif subcommand == "disable":
            if len(context.args) < 2:
                await update.effective_message.reply_text(
                    "Usage: `/cron disable <name>`",
                    parse_mode="Markdown",
                )
                return

            job_name = context.args[1]
            if disable_cron_job(bot_name, job_name):
                await update.effective_message.reply_text(
                    f"\U0001f6d1 Job `{job_name}` disabled.",
                    parse_mode="Markdown",
                )
            else:
                await update.effective_message.reply_text(f"Job '{job_name}' not found.")

        else:
            await update.effective_message.reply_text(
                "Unknown subcommand. Use: list, add, run, remove, enable, disable",
            )

    async def heartbeat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /heartbeat command - manage heartbeat settings."""
        if not await check_authorization(update):
            return

        from cclaw.heartbeat import (
            disable_heartbeat,
            enable_heartbeat,
            execute_heartbeat,
            get_heartbeat_config,
        )

        if not context.args:
            heartbeat_config = get_heartbeat_config(bot_name)
            enabled = heartbeat_config.get("enabled", False)
            interval = heartbeat_config.get("interval_minutes", 30)
            active_hours = heartbeat_config.get("active_hours", {})
            start = active_hours.get("start", "07:00")
            end = active_hours.get("end", "23:00")
            status_text = "on" if enabled else "off"
            text = (
                f"\U0001f493 *Heartbeat Status*\n\n"
                f"Status: *{status_text}*\n"
                f"Interval: {interval}m\n"
                f"Active hours: {start} - {end}\n\n"
                "`/heartbeat on` - Enable\n"
                "`/heartbeat off` - Disable\n"
                "`/heartbeat run` - Run now"
            )
            await update.effective_message.reply_text(text, parse_mode="Markdown")
            return

        subcommand = context.args[0].lower()

        if subcommand == "on":
            if enable_heartbeat(bot_name):
                await update.effective_message.reply_text("\U0001f493 Heartbeat enabled.")
            else:
                await update.effective_message.reply_text("Failed to enable heartbeat.")

        elif subcommand == "off":
            if disable_heartbeat(bot_name):
                await update.effective_message.reply_text("\U0001f493 Heartbeat disabled.")
            else:
                await update.effective_message.reply_text("Failed to disable heartbeat.")

        elif subcommand == "run":
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

        else:
            await update.effective_message.reply_text(
                "Unknown subcommand. Use: on, off, run",
            )

    async def compact_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /compact command — compress MD files to save tokens."""
        if not await check_authorization(update):
            return

        from cclaw.token_compact import (
            collect_compact_targets,
            format_compact_report,
            run_compact,
            save_compact_results,
        )

        targets = collect_compact_targets(bot_name)
        if not targets:
            await update.effective_message.reply_text("No compactable files found.")
            return

        target_list = "\n".join(
            f"  - {t.label} ({t.line_count} lines, ~{t.token_count:,} tokens)" for t in targets
        )
        await update.effective_message.reply_text(
            f"\U0001f4e6 Found {len(targets)} file(s) to compact:\n{target_list}\n\nCompacting..."
        )

        async def send_typing_periodically() -> None:
            try:
                while True:
                    await update.effective_message.chat.send_action("typing")
                    await asyncio.sleep(4)
            except asyncio.CancelledError:
                pass

        typing_task = asyncio.create_task(send_typing_periodically())

        try:
            results = await run_compact(bot_name, model=current_model)
            report = format_compact_report(bot_name, results)

            for chunk in split_message(report):
                await update.effective_message.reply_text(chunk)

            successful = [r for r in results if r.error is None]
            if successful:
                save_compact_results(results)

                from cclaw.skill import regenerate_bot_claude_md, update_session_claude_md

                regenerate_bot_claude_md(bot_name)
                update_session_claude_md(bot_path)
                await update.effective_message.reply_text("\u2705 Compacted files saved.")
            else:
                await update.effective_message.reply_text("No files were successfully compacted.")
        except Exception as error:
            await update.effective_message.reply_text(f"Compact failed: {error}")
        finally:
            typing_task.cancel()

    async def bind_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /bind command — bind a group to a Telegram chat.

        Only the orchestrator bot of the specified group processes this command.
        Other bots in the group silently ignore it.
        """
        if not await check_authorization(update):
            return

        if not context.args:
            await update.effective_message.reply_text(
                "Usage: `/bind <group_name>`", parse_mode="Markdown"
            )
            return

        group_name = context.args[0]
        group_config = load_group_config(group_name)

        if group_config is None:
            await update.effective_message.reply_text(f"Group '{group_name}' not found.")
            return

        my_role = get_my_role(group_config, bot_name)
        if my_role != "orchestrator":
            # Not the orchestrator — silently ignore
            return

        chat_id = update.effective_chat.id
        try:
            bind_group(group_name, chat_id)
        except ValueError as error:
            await update.effective_message.reply_text(f"Bind failed: {error}")
            return

        # Build member list display
        members_display = ", ".join(group_config.get("members", []))
        await update.effective_message.reply_text(
            f"Group '{group_name}' activated.\nOrchestrator: {bot_name}\nMembers: {members_display}"
        )

    async def unbind_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /unbind command — remove group binding from this chat.

        Only the orchestrator of the bound group processes this command.
        """
        if not await check_authorization(update):
            return

        chat_id = update.effective_chat.id
        group_config = find_group_by_chat_id(chat_id)

        if group_config is None:
            await update.effective_message.reply_text("No group is bound to this chat.")
            return

        my_role = get_my_role(group_config, bot_name)
        if my_role != "orchestrator":
            # Not the orchestrator — silently ignore
            return

        group_name = group_config["name"]
        unbind_group(group_name)
        await update.effective_message.reply_text(f"Group '{group_name}' unbound from this chat.")

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
