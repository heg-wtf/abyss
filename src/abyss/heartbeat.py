"""Heartbeat (periodic situation awareness) for abyss bots."""

from __future__ import annotations

import asyncio
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from abyss.config import bot_directory, load_bot_config, save_bot_config

logger = logging.getLogger(__name__)

HEARTBEAT_OK_MARKER = "HEARTBEAT_OK"

DEFAULT_HEARTBEAT_CONFIG: dict[str, Any] = {
    "enabled": False,
    "interval_minutes": 30,
    "active_hours": {
        "start": "07:00",
        "end": "23:00",
    },
}


# --- Config CRUD ---


def get_heartbeat_config(bot_name: str) -> dict[str, Any]:
    """Read the heartbeat section from bot.yaml."""
    bot_config = load_bot_config(bot_name)
    if not bot_config:
        return dict(DEFAULT_HEARTBEAT_CONFIG)
    return bot_config.get("heartbeat", dict(DEFAULT_HEARTBEAT_CONFIG))


def save_heartbeat_config(bot_name: str, heartbeat_config: dict[str, Any]) -> None:
    """Save the heartbeat section to bot.yaml."""
    bot_config = load_bot_config(bot_name)
    if not bot_config:
        return
    bot_config["heartbeat"] = heartbeat_config
    save_bot_config(bot_name, bot_config)


def enable_heartbeat(bot_name: str) -> bool:
    """Enable heartbeat for a bot.

    Creates default HEARTBEAT.md if missing. Returns True if successful.
    """
    bot_config = load_bot_config(bot_name)
    if not bot_config:
        return False
    heartbeat_config = bot_config.get("heartbeat", dict(DEFAULT_HEARTBEAT_CONFIG))
    heartbeat_config["enabled"] = True
    bot_config["heartbeat"] = heartbeat_config
    save_bot_config(bot_name, bot_config)

    # Create default HEARTBEAT.md if it doesn't exist
    session_directory = heartbeat_session_directory(bot_name)
    heartbeat_md_path = session_directory / "HEARTBEAT.md"
    if not heartbeat_md_path.exists():
        heartbeat_md_path.write_text(default_heartbeat_content())

    return True


def disable_heartbeat(bot_name: str) -> bool:
    """Disable heartbeat for a bot. Returns True if successful."""
    bot_config = load_bot_config(bot_name)
    if not bot_config:
        return False
    heartbeat_config = bot_config.get("heartbeat", dict(DEFAULT_HEARTBEAT_CONFIG))
    heartbeat_config["enabled"] = False
    bot_config["heartbeat"] = heartbeat_config
    save_bot_config(bot_name, bot_config)
    return True


# --- Utilities ---


def is_within_active_hours(active_hours: dict[str, str], now: datetime | None = None) -> bool:
    """Check if the current time is within the active hours range.

    Uses config.yaml timezone. Supports overnight ranges (e.g. start=22:00, end=06:00).

    Args:
        active_hours: Dict with 'start' and 'end' keys in HH:MM format.
        now: Optional datetime for testing. Uses config timezone if None.
    """
    if now is None:
        from zoneinfo import ZoneInfo

        from abyss.config import get_timezone

        timezone_name = get_timezone()
        try:
            timezone_info = ZoneInfo(timezone_name)
        except (KeyError, ValueError):
            timezone_info = None
        now = datetime.now(timezone_info)

    start_str = active_hours.get("start", "00:00")
    end_str = active_hours.get("end", "23:59")

    start_hour, start_minute = map(int, start_str.split(":"))
    end_hour, end_minute = map(int, end_str.split(":"))

    current_minutes = now.hour * 60 + now.minute
    start_minutes = start_hour * 60 + start_minute
    end_minutes = end_hour * 60 + end_minute

    if start_minutes <= end_minutes:
        # Normal range (e.g. 07:00 - 23:00)
        return start_minutes <= current_minutes <= end_minutes
    else:
        # Overnight range (e.g. 22:00 - 06:00)
        return current_minutes >= start_minutes or current_minutes <= end_minutes


def heartbeat_session_directory(bot_name: str) -> Path:
    """Return the heartbeat session directory, ensuring it exists.

    Creates the directory and copies bot's CLAUDE.md if not present.
    """
    directory = bot_directory(bot_name) / "heartbeat_sessions"
    directory.mkdir(parents=True, exist_ok=True)

    # Create workspace subdirectory
    workspace = directory / "workspace"
    workspace.mkdir(exist_ok=True)

    # Copy bot's CLAUDE.md if not present
    bot_claude_md = bot_directory(bot_name) / "CLAUDE.md"
    session_claude_md = directory / "CLAUDE.md"
    if not session_claude_md.exists() and bot_claude_md.exists():
        shutil.copy2(bot_claude_md, session_claude_md)

    return directory


# --- HEARTBEAT.md management ---


def default_heartbeat_content() -> str:
    """Return the default HEARTBEAT.md template."""
    return """# Heartbeat Checklist

실행할 항목이 없으면 HEARTBEAT_OK만 출력하세요.

## 확인 항목

- workspace/에 미완성 작업이 있는지 확인
- 마지막 대화 이후 8시간 이상 지났으면 가벼운 안부

## 규칙

- 긴급하지 않으면 메시지 보내지 말 것
- HEARTBEAT_OK는 반드시 응답 마지막에 포함할 것
"""


def load_heartbeat_markdown(bot_name: str) -> str:
    """Load the HEARTBEAT.md content for a bot."""
    directory = heartbeat_session_directory(bot_name)
    heartbeat_md_path = directory / "HEARTBEAT.md"
    if not heartbeat_md_path.exists():
        return ""
    return heartbeat_md_path.read_text()


def save_heartbeat_markdown(bot_name: str, content: str) -> None:
    """Save HEARTBEAT.md content for a bot."""
    directory = heartbeat_session_directory(bot_name)
    heartbeat_md_path = directory / "HEARTBEAT.md"
    heartbeat_md_path.write_text(content)


# --- Execution ---


async def execute_heartbeat(
    bot_name: str,
    bot_config: dict[str, Any],
    send_message_callback: Callable,
) -> None:
    """Execute a heartbeat check and notify users if needed.

    1. Prepare heartbeat session directory
    2. Read HEARTBEAT.md and compose prompt
    3. Run Claude with the prompt
    4. If response contains HEARTBEAT_OK → log only, no message
    5. If response does NOT contain HEARTBEAT_OK → send to allowed_users

    Args:
        bot_name: Name of the bot.
        bot_config: The bot's configuration.
        send_message_callback: Async callable(chat_id, text, ...) to send messages.
    """
    from abyss.config import DEFAULT_MODEL
    from abyss.llm import LLMRequest, get_or_create
    from abyss.utils import markdown_to_telegram_html, split_message

    model = bot_config.get("model", DEFAULT_MODEL)
    attached_skills = bot_config.get("skills", [])
    command_timeout = bot_config.get("command_timeout", 300)

    working_directory = str(heartbeat_session_directory(bot_name))

    # Load HEARTBEAT.md
    heartbeat_content = load_heartbeat_markdown(bot_name)
    if not heartbeat_content:
        logger.warning("Heartbeat for '%s': no HEARTBEAT.md found, skipping", bot_name)
        return

    from abyss.session import load_bot_memory, load_global_memory

    prompt_parts: list[str] = []

    global_memory = load_global_memory()
    if global_memory:
        prompt_parts.append(
            "아래는 글로벌 메모리입니다. 참고하세요 (수정 불가):\n\n" + global_memory
        )

    bot_memory = load_bot_memory(bot_directory(bot_name))
    if bot_memory:
        prompt_parts.append("아래는 장기 메모리입니다. 참고하세요:\n\n" + bot_memory)

    prompt_parts.append(f"다음 체크리스트를 확인하고 결과를 알려주세요.\n\n{heartbeat_content}")

    message = "\n\n---\n\n".join(prompt_parts)

    logger.info("Executing heartbeat for bot '%s'", bot_name)

    try:
        heartbeat_bot_config = {
            **bot_config,
            "model": model,
            "skills": attached_skills,
        }
        backend = get_or_create(bot_name, heartbeat_bot_config)
        request = LLMRequest(
            bot_name=bot_name,
            bot_path=bot_directory(bot_name),
            session_directory=Path(working_directory),
            working_directory=working_directory,
            bot_config=heartbeat_bot_config,
            user_prompt=message,
            timeout=command_timeout,
            session_key=f"heartbeat:{bot_name}",
        )
        result = await backend.run(request)
        response = result.text
    except Exception as error:
        response = f"Heartbeat failed: {error}"
        logger.error("Heartbeat for '%s' failed: %s", bot_name, error)

    # Persist the run to ``conversation-*.md`` so the mobile Routines
    # tab can render heartbeat history. Best-effort; failures must
    # never block notification delivery downstream. HEARTBEAT_OK runs
    # are logged too — silence is itself a meaningful data point when
    # debugging "did this bot run at all today?".
    try:
        from abyss.session import log_conversation as _log_conversation

        session_dir = Path(working_directory)
        _log_conversation(session_dir, "user", message)
        _log_conversation(session_dir, "assistant", response)
    except Exception as log_error:  # noqa: BLE001
        logger.warning("Heartbeat for '%s' conversation log skipped: %s", bot_name, log_error)

    # Check for HEARTBEAT_OK marker
    if HEARTBEAT_OK_MARKER in response:
        logger.info("Heartbeat for '%s': HEARTBEAT_OK, no notification needed", bot_name)
        return

    # Web Push delivery (coexists with the Telegram callback below).
    # ``send_push`` no-ops when there are no subscriptions, so this is
    # safe on freshly-installed dashboards. Failures here must never
    # break the Telegram path.
    from contextlib import suppress as _suppress

    with _suppress(Exception):
        from abyss.web_push import send_push as _send_push

        preview = response.replace("\n", " ").strip()
        if len(preview) > 120:
            preview = preview[:117] + "…"
        display_name = (
            bot_config.get("display_name") or bot_config.get("telegram_botname") or bot_name
        )
        await _send_push(
            title=f"💓 {display_name}",
            body=preview or "Heartbeat check ran.",
            bot=bot_name,
        )

    # Send notification to all allowed users (fallback to session chat IDs)
    allowed_users = bot_config.get("allowed_users", [])
    if not allowed_users:
        from abyss.session import collect_session_chat_ids

        bot_path = bot_directory(bot_name)
        allowed_users = collect_session_chat_ids(bot_path)
        if allowed_users:
            logger.info(
                "Heartbeat for '%s': no allowed_users configured, using %d session chat ID(s)",
                bot_name,
                len(allowed_users),
            )
        else:
            logger.warning(
                "Heartbeat for '%s': no allowed_users and no session chat IDs, skipping send",
                bot_name,
            )
            return

    header = f"[heartbeat: {bot_name}]\n\n"
    html_response = markdown_to_telegram_html(header + response)
    chunks = split_message(html_response)

    for user_id in allowed_users:
        for chunk in chunks:
            try:
                await send_message_callback(chat_id=user_id, text=chunk, parse_mode="HTML")
            except Exception:
                try:
                    await send_message_callback(chat_id=user_id, text=chunk)
                except Exception as send_error:
                    logger.error(
                        "Failed to send heartbeat result to user %d: %s",
                        user_id,
                        send_error,
                    )


# --- Scheduler ---


async def run_heartbeat_scheduler(
    bot_name: str,
    bot_config: dict[str, Any],
    application: Any,
    stop_event: asyncio.Event,
) -> None:
    """Run the heartbeat scheduler loop for a bot.

    Repeats at interval_minutes intervals:
    1. Check stop_event → exit if set
    2. Check is_within_active_hours() → skip if outside range
    3. Call execute_heartbeat()
    4. Sleep for interval_minutes

    Args:
        bot_name: Name of the bot.
        bot_config: The bot's configuration.
        application: The telegram Application instance.
        stop_event: Event that signals shutdown.
    """
    heartbeat_config = bot_config.get("heartbeat", {})
    interval_minutes = heartbeat_config.get("interval_minutes", 30)
    active_hours = heartbeat_config.get("active_hours", {"start": "07:00", "end": "23:00"})
    interval_seconds = interval_minutes * 60

    logger.info(
        "Heartbeat scheduler started for bot '%s' (interval: %dm, active: %s-%s)",
        bot_name,
        interval_minutes,
        active_hours.get("start", "07:00"),
        active_hours.get("end", "23:00"),
    )

    while not stop_event.is_set():
        try:
            # Re-read config to pick up changes (enabled/disabled, active_hours, etc.)
            current_bot_config = load_bot_config(bot_name) or bot_config
            current_heartbeat_config = current_bot_config.get("heartbeat", {})

            if not current_heartbeat_config.get("enabled", False):
                logger.debug("Heartbeat for '%s' is disabled, skipping", bot_name)
            else:
                current_active_hours = current_heartbeat_config.get("active_hours", active_hours)
                if is_within_active_hours(current_active_hours):
                    await execute_heartbeat(
                        bot_name=bot_name,
                        bot_config=current_bot_config,
                        send_message_callback=application.bot.send_message,
                    )
                else:
                    logger.debug("Heartbeat for '%s': outside active hours, skipping", bot_name)

            # Update interval from latest config
            interval_minutes = current_heartbeat_config.get("interval_minutes", 30)
            interval_seconds = interval_minutes * 60

        except Exception as error:
            logger.error("Heartbeat scheduler error for bot '%s': %s", bot_name, error)

        # Wait for the next interval or stop
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
            break  # stop_event was set
        except asyncio.TimeoutError:
            pass  # Continue loop

    logger.info("Heartbeat scheduler stopped for bot '%s'", bot_name)
