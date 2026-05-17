"""Cron schedule automation for abyss bots."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml
from croniter import croniter

from abyss.config import bot_directory

logger = logging.getLogger(__name__)

CRON_CHECK_INTERVAL_SECONDS = 30


def resolve_job_timezone(job: dict[str, Any]) -> ZoneInfo | timezone:
    """Resolve the timezone for a cron job.

    Priority: job-level timezone -> config.yaml timezone -> UTC.
    Returns ZoneInfo for named timezones (e.g., 'Asia/Seoul'),
    or timezone.utc as fallback.
    """
    timezone_name = job.get("timezone")
    if timezone_name:
        try:
            return ZoneInfo(timezone_name)
        except (KeyError, ValueError):
            logger.warning("Invalid timezone '%s' in job, trying config timezone", timezone_name)

    # Fall back to config.yaml timezone
    from abyss.config import get_timezone

    config_timezone = get_timezone()
    if config_timezone and config_timezone != "UTC":
        try:
            return ZoneInfo(config_timezone)
        except (KeyError, ValueError):
            logger.warning("Invalid config timezone '%s', falling back to UTC", config_timezone)

    return timezone.utc


# --- Data structures & CRUD ---


def cron_config_path(bot_name: str) -> Path:
    """Return the path to a bot's cron.yaml."""
    return bot_directory(bot_name) / "cron.yaml"


def load_cron_config(bot_name: str) -> dict[str, Any]:
    """Load a bot's cron.yaml. Returns empty config if it doesn't exist."""
    path = cron_config_path(bot_name)
    if not path.exists():
        return {"jobs": []}
    with open(path) as file:
        data = yaml.safe_load(file)
    if not data or "jobs" not in data:
        return {"jobs": []}
    return data


def save_cron_config(bot_name: str, config: dict[str, Any]) -> None:
    """Save a bot's cron.yaml."""
    path = cron_config_path(bot_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as file:
        yaml.dump(config, file, default_flow_style=False, allow_unicode=True)


def list_cron_jobs(bot_name: str) -> list[dict[str, Any]]:
    """Return the list of cron jobs for a bot."""
    config = load_cron_config(bot_name)
    return config.get("jobs", [])


def get_cron_job(bot_name: str, job_name: str) -> dict[str, Any] | None:
    """Get a specific cron job by name."""
    for job in list_cron_jobs(bot_name):
        if job.get("name") == job_name:
            return job
    return None


def add_cron_job(bot_name: str, job: dict[str, Any]) -> None:
    """Add a cron job to a bot's configuration.

    If the job has an 'at' field with a relative duration (e.g., '10m', '2h'),
    it is converted to an absolute ISO datetime at add time so that the
    scheduler can correctly detect when the time has passed.
    """
    config = load_cron_config(bot_name)
    existing_names = {j["name"] for j in config["jobs"]}
    if job["name"] in existing_names:
        raise ValueError(f"Job '{job['name']}' already exists")

    # Convert relative duration to absolute ISO datetime
    if "at" in job:
        at_value = job["at"]
        duration_match = re.match(r"^(\d+)([mhd])$", str(at_value).strip())
        if duration_match:
            at_time = parse_one_shot_time(at_value)
            if at_time:
                job["at"] = at_time.isoformat()
                logger.info(
                    "Converted relative 'at' value '%s' to absolute '%s'",
                    at_value,
                    job["at"],
                )

    config["jobs"].append(job)
    save_cron_config(bot_name, config)


def remove_cron_job(bot_name: str, job_name: str) -> bool:
    """Remove a cron job by name. Returns True if found and removed."""
    config = load_cron_config(bot_name)
    original_count = len(config["jobs"])
    config["jobs"] = [j for j in config["jobs"] if j.get("name") != job_name]
    if len(config["jobs"]) == original_count:
        return False
    save_cron_config(bot_name, config)
    return True


def enable_cron_job(bot_name: str, job_name: str) -> bool:
    """Enable a cron job. Returns True if found."""
    config = load_cron_config(bot_name)
    for job in config["jobs"]:
        if job.get("name") == job_name:
            job["enabled"] = True
            save_cron_config(bot_name, config)
            return True
    return False


def disable_cron_job(bot_name: str, job_name: str) -> bool:
    """Disable a cron job. Returns True if found."""
    config = load_cron_config(bot_name)
    for job in config["jobs"]:
        if job.get("name") == job_name:
            job["enabled"] = False
            save_cron_config(bot_name, config)
            return True
    return False


def edit_cron_job_message(bot_name: str, job_name: str, new_message: str) -> bool:
    """Edit the message of a cron job. Returns True if found."""
    config = load_cron_config(bot_name)
    for job in config["jobs"]:
        if job.get("name") == job_name:
            job["message"] = new_message
            save_cron_config(bot_name, config)
            return True
    return False


# --- Natural language parsing ---

CRON_PARSE_PROMPT = (
    "You are a cron schedule parser. "
    "Parse the following natural language input into a cron job definition.\n"
    "The input can be in ANY language (Korean, English, Japanese, Chinese, etc.).\n"
    "\n"
    "Current local time: {current_time}\n"
    "Timezone: {timezone}\n"
    "\n"
    "Rules:\n"
    '- Determine if this is "recurring" (repeating) or "oneshot" (one-time)\n'
    "- For recurring: generate a standard cron expression (5 fields)\n"
    "- For oneshot: generate an ISO 8601 datetime string in the given timezone\n"
    "- Extract the task message (WHAT to do, not WHEN)\n"
    "  - Keep the message in the ORIGINAL language of the input\n"
    "- Generate a short kebab-case name (English, 2-3 words)\n"
    "\n"
    "Respond ONLY with JSON, no other text:\n"
    '{{"type": "recurring or oneshot", '
    '"schedule": "cron expression (recurring only)", '
    '"at": "ISO datetime (oneshot only)", '
    '"message": "task description in original language", '
    '"name": "short-kebab-name-in-english"}}\n'
    "\n"
    "Input: {user_input}"
)


def resolve_default_timezone() -> str:
    """Resolve the default timezone for cron job creation.

    Uses config.yaml timezone as the single source of truth.
    """
    from abyss.config import get_timezone

    return get_timezone()


def generate_unique_job_name(
    bot_name: str,
    desired_name: str,
) -> str:
    """Generate a unique job name, appending suffix if needed."""
    existing_names = {j["name"] for j in list_cron_jobs(bot_name)}
    if desired_name not in existing_names:
        return desired_name

    counter = 2
    while f"{desired_name}-{counter}" in existing_names:
        counter += 1
    return f"{desired_name}-{counter}"


async def parse_natural_language_schedule(
    user_input: str,
    timezone_name: str,
) -> dict[str, Any]:
    """Parse natural language into a cron job definition using Claude.

    Returns a dict with keys: type, schedule/at, message, name.
    Raises ValueError if parsing fails.
    """
    import json

    from abyss.claude_runner import run_claude

    tz_info = ZoneInfo(timezone_name) if timezone_name != "UTC" else timezone.utc
    current_time = datetime.now(tz_info).strftime("%Y-%m-%d %H:%M (%A)")

    prompt = CRON_PARSE_PROMPT.format(
        current_time=current_time,
        timezone=timezone_name,
        user_input=user_input,
    )

    import tempfile

    with tempfile.TemporaryDirectory() as temporary_directory:
        response = await run_claude(
            working_directory=temporary_directory,
            message=prompt,
            timeout=30,
            model="haiku",
        )

    response = response.strip()
    # Extract JSON from response (handle markdown code blocks)
    if "```" in response:
        json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", response, re.DOTALL)
        if json_match:
            response = json_match.group(1).strip()

    try:
        result = json.loads(response)
    except json.JSONDecodeError as error:
        raise ValueError(f"Failed to parse schedule: {error}") from error

    if "type" not in result or "message" not in result or "name" not in result:
        raise ValueError("Incomplete parsing result")

    if result["type"] == "recurring" and "schedule" not in result:
        raise ValueError("Missing schedule for recurring job")

    if result["type"] == "oneshot" and "at" not in result:
        raise ValueError("Missing 'at' for oneshot job")

    if result["type"] == "recurring" and not validate_cron_schedule(result["schedule"]):
        raise ValueError(f"Invalid cron expression: {result['schedule']}")

    return result


# --- Validation ---


def validate_cron_schedule(schedule: str) -> bool:
    """Validate a cron expression using croniter."""
    return croniter.is_valid(schedule)


def parse_one_shot_time(at_value: str) -> datetime | None:
    """Parse a one-shot time value.

    Supports:
    - ISO 8601 datetime: "2026-02-20T15:00:00"
    - Duration shorthand: "30m", "2h", "1d"

    Returns a timezone-aware datetime or None if parsing fails.
    """
    # Try duration shorthand first
    duration_match = re.match(r"^(\d+)([mhd])$", at_value.strip())
    if duration_match:
        amount = int(duration_match.group(1))
        unit = duration_match.group(2)
        now = datetime.now(timezone.utc)
        if unit == "m":
            return now + timedelta(minutes=amount)
        elif unit == "h":
            return now + timedelta(hours=amount)
        elif unit == "d":
            return now + timedelta(days=amount)

    # Try ISO 8601 datetime
    try:
        parsed = datetime.fromisoformat(at_value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


def next_run_time(job: dict[str, Any]) -> datetime | None:
    """Calculate the next run time for a job.

    Returns None if the job has no valid schedule.
    The returned datetime is timezone-aware in the job's configured timezone.
    """
    if "at" in job:
        at_time = parse_one_shot_time(job["at"])
        return at_time

    schedule = job.get("schedule")
    if not schedule or not validate_cron_schedule(schedule):
        return None

    job_timezone = resolve_job_timezone(job)
    now = datetime.now(job_timezone)
    cron = croniter(schedule, now)
    return cron.get_next(datetime).replace(tzinfo=job_timezone)


# --- Cron session directory ---


def cron_session_directory(bot_name: str, job_name: str) -> Path:
    """Return the cron session directory for a job, ensuring it exists."""
    directory = bot_directory(bot_name) / "cron_sessions" / job_name
    directory.mkdir(parents=True, exist_ok=True)

    # Copy bot's CLAUDE.md if not present
    bot_claude_md = bot_directory(bot_name) / "CLAUDE.md"
    session_claude_md = directory / "CLAUDE.md"
    if not session_claude_md.exists() and bot_claude_md.exists():
        import shutil

        shutil.copy2(bot_claude_md, session_claude_md)

    return directory


# --- Scheduler ---


async def execute_cron_job(
    bot_name: str,
    job: dict[str, Any],
    bot_config: dict[str, Any],
) -> None:
    """Execute a single cron job.

    Delivery surfaces (in order):
    1. ``conversation-*.md`` under the cron session — picked up by
       the mobile Routines tab + FTS5 conversation index.
    2. Web Push notification via ``web_push.send_push`` — no-op when
       no PWA subscriptions are registered (e.g. when the dashboard
       has never been served over HTTPS).

    Args:
        bot_name: Name of the bot.
        job: The cron job configuration dict.
        bot_config: The bot's configuration.
    """
    from abyss.config import DEFAULT_MODEL
    from abyss.llm import LLMRequest, get_or_create

    job_name = job["name"]
    raw_message = job.get("message", "")
    model = job.get("model") or bot_config.get("model", DEFAULT_MODEL)
    job_skills = job.get("skills") or bot_config.get("skills", [])
    command_timeout = bot_config.get("command_timeout", 300)

    working_directory = str(cron_session_directory(bot_name, job_name))

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

    prompt_parts.append(raw_message)

    message = "\n\n---\n\n".join(prompt_parts)

    logger.info("Executing cron job '%s' for bot '%s'", job_name, bot_name)

    try:
        cron_bot_config = {
            **bot_config,
            "model": model,
            "skills": job_skills,
        }
        backend = get_or_create(bot_name, cron_bot_config)
        request = LLMRequest(
            bot_name=bot_name,
            bot_path=bot_directory(bot_name),
            session_directory=Path(working_directory),
            working_directory=working_directory,
            bot_config=cron_bot_config,
            user_prompt=message,
            timeout=command_timeout,
            session_key=f"cron:{bot_name}:{job_name}",
        )
        result = await backend.run(request)
        response = result.text
    except Exception as error:
        response = f"Cron job '{job_name}' failed: {error}"
        logger.exception("Cron job '%s' failed", job_name)

    # Persist the run to ``conversation-*.md`` so the mobile Routines
    # tab and any future history surface have something to render.
    # Best-effort: a logging failure must never block delivery, so we
    # swallow exceptions just like the Web Push branch below.
    try:
        from abyss.session import log_conversation as _log_conversation

        # Only the assistant reply lands in the conversation log. The
        # "user" side of a cron run is the trigger prompt from
        # ``cron.yaml`` (e.g. system memory + checklist), which is
        # noisy and unhelpful when surfaced in the mobile Routines
        # transcript. Real user replies typed into the routine
        # detail screen still log normally via the chat server.
        session_dir = Path(working_directory)
        _log_conversation(session_dir, "assistant", response)
    except Exception as log_error:  # noqa: BLE001
        logger.warning("Cron job '%s' conversation log skipped: %s", job_name, log_error)

    # Web Push delivery — best-effort. ``send_push`` no-ops when no
    # PWA subscriptions exist (e.g. fresh install, no HTTPS yet), so
    # the call is safe to make every run.
    from contextlib import suppress

    with suppress(Exception):
        from abyss.web_push import send_push as _send_push

        preview = response.replace("\n", " ").strip()
        if len(preview) > 120:
            preview = preview[:117] + "…"
        display_name = bot_config.get("display_name") or bot_name
        await _send_push(
            title=f"⏰ {display_name}: {job_name}",
            body=preview or f"Cron job '{job_name}' finished.",
            bot=bot_name,
        )

    # Telegram delivery is gone — the markdown log + Web Push above
    # are the only fan-out paths now. Anything that wants the result
    # reads it from the mobile Routines tab, the dashboard, or via
    # ``conversation_search`` MCP.


def _log_task_exception(bot_name: str, job_name: str) -> Callable[[asyncio.Task], None]:
    """Return a done-callback that surfaces fire-and-forget task errors.

    ``asyncio.create_task`` without an awaited future loses exceptions
    unless someone calls ``task.exception()``. The done-callback runs
    that check + logs anything found so a broken cron job is visible
    in the daemon log instead of disappearing.
    """

    def _cb(task: asyncio.Task) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc is None:
            return
        logger.error(
            "Cron job '%s' (bot=%s) raised: %s",
            job_name,
            bot_name,
            exc,
            exc_info=exc,
        )

    return _cb


async def run_cron_scheduler(
    bot_name: str,
    bot_config: dict[str, Any],
    stop_event: asyncio.Event,
) -> None:
    """Run the cron scheduler loop for a bot.

    Checks every 30 seconds for jobs that need to run. Delivery is
    handled inside ``execute_cron_job`` (markdown log + Web Push) —
    no Telegram callback is plumbed any more.

    Args:
        bot_name: Name of the bot.
        bot_config: The bot's configuration.
        stop_event: Event that signals shutdown.
    """
    last_run_times: dict[str, datetime] = {}

    logger.info("Cron scheduler started for bot '%s'", bot_name)

    while not stop_event.is_set():
        try:
            jobs = list_cron_jobs(bot_name)

            for job in jobs:
                job_name = job.get("name")
                if not job_name:
                    continue

                if not job.get("enabled", True):
                    continue

                should_run = False

                if "at" in job:
                    # One-shot job (always evaluated in UTC)
                    now = datetime.now(timezone.utc)
                    at_time = parse_one_shot_time(job["at"])
                    if at_time and at_time <= now:
                        last_run = last_run_times.get(job_name)
                        if last_run is None:
                            should_run = True
                            last_run_times[job_name] = now
                elif "schedule" in job:
                    schedule = job["schedule"]
                    if validate_cron_schedule(schedule):
                        # Evaluate cron expression in the job's timezone
                        job_timezone = resolve_job_timezone(job)
                        now_in_timezone = datetime.now(job_timezone)
                        current_minute = now_in_timezone.replace(
                            second=0, microsecond=0, tzinfo=None
                        )

                        cron = croniter(schedule, current_minute - timedelta(seconds=1))
                        previous_fire = cron.get_next(datetime)
                        previous_fire_minute = previous_fire.replace(second=0, microsecond=0)

                        if previous_fire_minute == current_minute:
                            # Use UTC for last_run tracking
                            now_utc = datetime.now(timezone.utc).replace(second=0, microsecond=0)
                            last_run = last_run_times.get(job_name)
                            if last_run is None or last_run < now_utc:
                                should_run = True
                                last_run_times[job_name] = now_utc

                if should_run:
                    task = asyncio.create_task(
                        execute_cron_job(
                            bot_name=bot_name,
                            job=job,
                            bot_config=bot_config,
                        )
                    )
                    # Fire-and-forget tasks swallow exceptions
                    # silently — surface them through the logger so a
                    # broken cron job is debuggable.
                    task.add_done_callback(_log_task_exception(bot_name, job_name))

                    # Handle one-shot cleanup
                    if "at" in job:
                        if job.get("delete_after_run", False):
                            remove_cron_job(bot_name, job_name)
                            logger.info("One-shot job '%s' deleted after run", job_name)
                        else:
                            disable_cron_job(bot_name, job_name)
                            logger.info("One-shot job '%s' disabled after run", job_name)

        except Exception as error:
            logger.error("Cron scheduler error for bot '%s': %s", bot_name, error)

        # Wait for the next check interval or stop
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=CRON_CHECK_INTERVAL_SECONDS)
            break  # stop_event was set
        except asyncio.TimeoutError:
            pass  # Continue loop

    logger.info("Cron scheduler stopped for bot '%s'", bot_name)
