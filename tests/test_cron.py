"""Tests for abyss.cron module."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from abyss.cron import (
    add_cron_job,
    cron_session_directory,
    disable_cron_job,
    edit_cron_job_message,
    enable_cron_job,
    generate_unique_job_name,
    get_cron_job,
    list_cron_jobs,
    load_cron_config,
    next_run_time,
    parse_natural_language_schedule,
    parse_one_shot_time,
    remove_cron_job,
    resolve_default_timezone,
    resolve_job_timezone,
    save_cron_config,
    validate_cron_schedule,
)


@pytest.fixture
def temp_abyss_home(tmp_path, monkeypatch):
    """Set ABYSS_HOME to a temporary directory."""
    home = tmp_path / ".abyss"
    monkeypatch.setenv("ABYSS_HOME", str(home))
    return home


@pytest.fixture
def bot_with_cron(temp_abyss_home):
    """Create a bot directory with a cron.yaml."""
    bot_directory = temp_abyss_home / "bots" / "test-bot"
    bot_directory.mkdir(parents=True)
    (bot_directory / "CLAUDE.md").write_text("# test-bot\n")
    return "test-bot"


# --- load/save tests ---


def test_load_cron_config_missing(bot_with_cron):
    """load_cron_config returns empty jobs when cron.yaml doesn't exist."""
    config = load_cron_config(bot_with_cron)
    assert config == {"jobs": []}


def test_save_and_load_cron_config(bot_with_cron):
    """save_cron_config creates cron.yaml that load_cron_config can read."""
    config = {
        "jobs": [
            {
                "name": "test-job",
                "schedule": "0 9 * * *",
                "message": "Hello",
                "enabled": True,
            }
        ]
    }
    save_cron_config(bot_with_cron, config)
    loaded = load_cron_config(bot_with_cron)
    assert len(loaded["jobs"]) == 1
    assert loaded["jobs"][0]["name"] == "test-job"
    assert loaded["jobs"][0]["schedule"] == "0 9 * * *"


# --- CRUD tests ---


def test_list_cron_jobs_empty(bot_with_cron):
    """list_cron_jobs returns empty list when no jobs configured."""
    assert list_cron_jobs(bot_with_cron) == []


def test_add_cron_job(bot_with_cron):
    """add_cron_job adds a job to the cron config."""
    job = {"name": "morning", "schedule": "0 9 * * *", "message": "Good morning", "enabled": True}
    add_cron_job(bot_with_cron, job)

    jobs = list_cron_jobs(bot_with_cron)
    assert len(jobs) == 1
    assert jobs[0]["name"] == "morning"


def test_add_cron_job_duplicate(bot_with_cron):
    """add_cron_job raises ValueError for duplicate names."""
    job = {"name": "morning", "schedule": "0 9 * * *", "message": "Hello", "enabled": True}
    add_cron_job(bot_with_cron, job)

    with pytest.raises(ValueError, match="already exists"):
        add_cron_job(bot_with_cron, job)


def test_get_cron_job(bot_with_cron):
    """get_cron_job returns the matching job or None."""
    job = {"name": "test", "schedule": "0 9 * * *", "message": "Hello", "enabled": True}
    add_cron_job(bot_with_cron, job)

    result = get_cron_job(bot_with_cron, "test")
    assert result is not None
    assert result["name"] == "test"

    assert get_cron_job(bot_with_cron, "nonexistent") is None


def test_remove_cron_job(bot_with_cron):
    """remove_cron_job removes a job and returns True."""
    job = {"name": "to-remove", "schedule": "0 9 * * *", "message": "Hello", "enabled": True}
    add_cron_job(bot_with_cron, job)

    assert remove_cron_job(bot_with_cron, "to-remove") is True
    assert list_cron_jobs(bot_with_cron) == []


def test_remove_cron_job_not_found(bot_with_cron):
    """remove_cron_job returns False when job doesn't exist."""
    assert remove_cron_job(bot_with_cron, "nonexistent") is False


def test_enable_cron_job(bot_with_cron):
    """enable_cron_job sets enabled to True."""
    job = {"name": "test", "schedule": "0 9 * * *", "message": "Hello", "enabled": False}
    add_cron_job(bot_with_cron, job)

    assert enable_cron_job(bot_with_cron, "test") is True
    result = get_cron_job(bot_with_cron, "test")
    assert result["enabled"] is True


def test_enable_cron_job_not_found(bot_with_cron):
    """enable_cron_job returns False when job doesn't exist."""
    assert enable_cron_job(bot_with_cron, "nonexistent") is False


def test_disable_cron_job(bot_with_cron):
    """disable_cron_job sets enabled to False."""
    job = {"name": "test", "schedule": "0 9 * * *", "message": "Hello", "enabled": True}
    add_cron_job(bot_with_cron, job)

    assert disable_cron_job(bot_with_cron, "test") is True
    result = get_cron_job(bot_with_cron, "test")
    assert result["enabled"] is False


def test_disable_cron_job_not_found(bot_with_cron):
    """disable_cron_job returns False when job doesn't exist."""
    assert disable_cron_job(bot_with_cron, "nonexistent") is False


def test_edit_cron_job_message(bot_with_cron):
    """edit_cron_job_message updates the message field."""
    job = {"name": "test", "schedule": "0 9 * * *", "message": "Hello"}
    add_cron_job(bot_with_cron, job)

    assert edit_cron_job_message(bot_with_cron, "test", "New message") is True
    result = get_cron_job(bot_with_cron, "test")
    assert result["message"] == "New message"


def test_edit_cron_job_message_not_found(bot_with_cron):
    """edit_cron_job_message returns False when job doesn't exist."""
    assert edit_cron_job_message(bot_with_cron, "nonexistent", "New") is False


def test_edit_cron_job_message_preserves_other_fields(bot_with_cron):
    """edit_cron_job_message only changes message, not other fields."""
    job = {
        "name": "test",
        "schedule": "0 9 * * *",
        "message": "Old",
        "enabled": True,
        "timezone": "Asia/Seoul",
    }
    add_cron_job(bot_with_cron, job)

    edit_cron_job_message(bot_with_cron, "test", "New")
    result = get_cron_job(bot_with_cron, "test")
    assert result["message"] == "New"
    assert result["name"] == "test"
    assert result["schedule"] == "0 9 * * *"
    assert result["enabled"] is True
    assert result["timezone"] == "Asia/Seoul"


# --- Validation tests ---


def test_validate_cron_schedule_valid():
    """validate_cron_schedule accepts valid cron expressions."""
    assert validate_cron_schedule("0 9 * * *") is True
    assert validate_cron_schedule("*/5 * * * *") is True
    assert validate_cron_schedule("0 0 1 * *") is True
    assert validate_cron_schedule("30 14 * * 1-5") is True


def test_validate_cron_schedule_invalid():
    """validate_cron_schedule rejects invalid expressions."""
    assert validate_cron_schedule("not a cron") is False
    assert validate_cron_schedule("") is False
    assert validate_cron_schedule("60 * * * *") is False


def test_parse_one_shot_time_duration():
    """parse_one_shot_time parses duration shorthand."""
    now = datetime.now(timezone.utc)

    result = parse_one_shot_time("30m")
    assert result is not None
    expected = now + timedelta(minutes=30)
    assert abs((result - expected).total_seconds()) < 2

    result = parse_one_shot_time("2h")
    assert result is not None
    expected = now + timedelta(hours=2)
    assert abs((result - expected).total_seconds()) < 2

    result = parse_one_shot_time("1d")
    assert result is not None
    expected = now + timedelta(days=1)
    assert abs((result - expected).total_seconds()) < 2


def test_parse_one_shot_time_iso():
    """parse_one_shot_time parses ISO 8601 datetime."""
    result = parse_one_shot_time("2026-02-20T15:00:00")
    assert result is not None
    assert result.year == 2026
    assert result.month == 2
    assert result.day == 20
    assert result.hour == 15


def test_parse_one_shot_time_invalid():
    """parse_one_shot_time returns None for invalid input."""
    assert parse_one_shot_time("invalid") is None
    assert parse_one_shot_time("abc123") is None


def test_next_run_time_schedule():
    """next_run_time calculates next run for cron schedule."""
    job = {"schedule": "0 9 * * *", "enabled": True}
    result = next_run_time(job)
    assert result is not None
    assert result > datetime.now(timezone.utc)


def test_next_run_time_one_shot():
    """next_run_time returns parsed time for one-shot jobs."""
    job = {"at": "2026-12-31T23:59:00", "enabled": True}
    result = next_run_time(job)
    assert result is not None
    assert result.year == 2026
    assert result.month == 12


def test_next_run_time_invalid_schedule():
    """next_run_time returns None for invalid schedule."""
    job = {"schedule": "invalid", "enabled": True}
    assert next_run_time(job) is None

    job_empty = {"enabled": True}
    assert next_run_time(job_empty) is None


# --- Timezone tests ---


def test_resolve_job_timezone_default_no_config(monkeypatch):
    """resolve_job_timezone returns UTC when no timezone specified and no config."""
    monkeypatch.setattr("abyss.config.load_config", lambda: None)
    job = {"schedule": "0 9 * * *"}
    result = resolve_job_timezone(job)
    assert result == timezone.utc


def test_resolve_job_timezone_falls_back_to_config(monkeypatch):
    """resolve_job_timezone uses config timezone when job has no timezone."""
    from zoneinfo import ZoneInfo

    monkeypatch.setattr(
        "abyss.config.load_config",
        lambda: {"timezone": "Asia/Tokyo"},
    )
    job = {"schedule": "0 9 * * *"}
    result = resolve_job_timezone(job)
    assert result == ZoneInfo("Asia/Tokyo")


def test_resolve_job_timezone_named():
    """resolve_job_timezone returns ZoneInfo for valid timezone name."""
    from zoneinfo import ZoneInfo

    job = {"schedule": "0 9 * * *", "timezone": "Asia/Seoul"}
    result = resolve_job_timezone(job)
    assert result == ZoneInfo("Asia/Seoul")


def test_resolve_job_timezone_invalid_falls_back_to_config(monkeypatch):
    """resolve_job_timezone falls back to config timezone for invalid job timezone."""
    from zoneinfo import ZoneInfo

    monkeypatch.setattr(
        "abyss.config.load_config",
        lambda: {"timezone": "Asia/Seoul"},
    )
    job = {"schedule": "0 9 * * *", "timezone": "Invalid/Timezone"}
    result = resolve_job_timezone(job)
    assert result == ZoneInfo("Asia/Seoul")


def test_resolve_job_timezone_invalid_no_config(monkeypatch):
    """resolve_job_timezone falls back to UTC when both job and config timezone are invalid."""
    monkeypatch.setattr("abyss.config.load_config", lambda: None)
    job = {"schedule": "0 9 * * *", "timezone": "Invalid/Timezone"}
    result = resolve_job_timezone(job)
    assert result == timezone.utc


def test_next_run_time_with_timezone():
    """next_run_time uses job timezone for calculation."""
    from zoneinfo import ZoneInfo

    job = {"schedule": "0 6 * * *", "timezone": "Asia/Seoul"}
    result = next_run_time(job)
    assert result is not None
    assert result.tzinfo == ZoneInfo("Asia/Seoul")
    assert result.hour == 6  # 6 AM in KST, not UTC


def test_next_run_time_utc_default(monkeypatch):
    """next_run_time uses UTC when no timezone specified and no config timezone."""
    monkeypatch.setattr("abyss.config.load_config", lambda: None)
    job = {"schedule": "0 9 * * *"}
    result = next_run_time(job)
    assert result is not None
    assert result.tzinfo == timezone.utc


# --- Cron session directory ---


def test_cron_session_directory(bot_with_cron, temp_abyss_home):
    """cron_session_directory creates and returns correct path."""
    directory = cron_session_directory(bot_with_cron, "test-job")
    assert directory.exists()
    assert directory.name == "test-job"
    assert "cron_sessions" in str(directory)

    # CLAUDE.md should be copied from bot
    claude_md = directory / "CLAUDE.md"
    assert claude_md.exists()


# --- add_cron_job ``at`` normalization ---


def test_add_cron_job_converts_relative_at_to_absolute(bot_with_cron):
    """add_cron_job converts relative duration (e.g., '10m') to absolute ISO datetime."""
    job = {
        "name": "relative-test",
        "at": "10m",
        "message": "Test message",
        "enabled": True,
    }
    before = datetime.now(timezone.utc)
    add_cron_job(bot_with_cron, job)
    after = datetime.now(timezone.utc)

    saved_job = get_cron_job(bot_with_cron, "relative-test")
    assert saved_job is not None

    # The 'at' value should now be an ISO datetime string, not '10m'
    assert saved_job["at"] != "10m"
    at_time = datetime.fromisoformat(saved_job["at"])

    # Should be approximately 10 minutes from now
    expected_min = before + timedelta(minutes=10)
    expected_max = after + timedelta(minutes=10)
    assert expected_min <= at_time <= expected_max


def test_add_cron_job_keeps_absolute_at_unchanged(bot_with_cron):
    """add_cron_job does not modify absolute ISO datetime 'at' values."""
    iso_time = "2026-12-25T15:00:00+00:00"
    job = {
        "name": "absolute-test",
        "at": iso_time,
        "message": "Test message",
        "enabled": True,
    }
    add_cron_job(bot_with_cron, job)

    saved_job = get_cron_job(bot_with_cron, "absolute-test")
    assert saved_job is not None
    assert saved_job["at"] == iso_time


# --- resolve_default_timezone tests ---


def test_resolve_default_timezone_from_config(monkeypatch):
    """resolve_default_timezone reads timezone from config.yaml."""
    monkeypatch.setattr(
        "abyss.config.load_config",
        lambda: {"timezone": "Asia/Seoul"},
    )
    assert resolve_default_timezone() == "Asia/Seoul"


def test_resolve_default_timezone_no_config(monkeypatch):
    """resolve_default_timezone returns UTC when no config."""
    monkeypatch.setattr("abyss.config.load_config", lambda: None)
    assert resolve_default_timezone() == "UTC"


def test_resolve_default_timezone_no_timezone_in_config(monkeypatch):
    """resolve_default_timezone returns UTC when config has no timezone."""
    monkeypatch.setattr(
        "abyss.config.load_config",
        lambda: {"bots": [], "settings": {}},
    )
    assert resolve_default_timezone() == "UTC"


# --- generate_unique_job_name tests ---


def test_generate_unique_job_name_no_conflict(bot_with_cron):
    """generate_unique_job_name returns the name as-is when no conflict."""
    assert generate_unique_job_name(bot_with_cron, "my-job") == "my-job"


def test_generate_unique_job_name_with_conflict(bot_with_cron):
    """generate_unique_job_name appends suffix on conflict."""
    add_cron_job(
        bot_with_cron,
        {
            "name": "my-job",
            "schedule": "0 9 * * *",
            "message": "test",
            "enabled": True,
        },
    )
    assert generate_unique_job_name(bot_with_cron, "my-job") == "my-job-2"


def test_generate_unique_job_name_multiple_conflicts(bot_with_cron):
    """generate_unique_job_name increments suffix on multiple conflicts."""
    for name in ["my-job", "my-job-2"]:
        add_cron_job(
            bot_with_cron,
            {
                "name": name,
                "schedule": "0 9 * * *",
                "message": "test",
                "enabled": True,
            },
        )
    assert generate_unique_job_name(bot_with_cron, "my-job") == "my-job-3"


# --- parse_natural_language_schedule tests ---


@pytest.mark.asyncio
async def test_parse_natural_language_schedule_recurring():
    """parse_natural_language_schedule parses recurring job."""
    import json

    mock_response = json.dumps(
        {
            "type": "recurring",
            "schedule": "0 9 * * *",
            "message": "이메일 요약해줘",
            "name": "email-summary",
        }
    )
    with patch(
        "abyss.claude_runner.run_claude",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await parse_natural_language_schedule(
            "매일 아침 9시에 이메일 요약해줘",
            "Asia/Seoul",
        )
    assert result["type"] == "recurring"
    assert result["schedule"] == "0 9 * * *"
    assert result["message"] == "이메일 요약해줘"
    assert result["name"] == "email-summary"


@pytest.mark.asyncio
async def test_parse_natural_language_schedule_oneshot():
    """parse_natural_language_schedule parses oneshot job."""
    import json

    mock_response = json.dumps(
        {
            "type": "oneshot",
            "at": "2026-03-06T14:00:00",
            "message": "보고서 확인",
            "name": "report-check",
        }
    )
    with patch(
        "abyss.claude_runner.run_claude",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await parse_natural_language_schedule(
            "내일 오후 2시에 보고서 확인",
            "Asia/Seoul",
        )
    assert result["type"] == "oneshot"
    assert result["at"] == "2026-03-06T14:00:00"
    assert result["message"] == "보고서 확인"


@pytest.mark.asyncio
async def test_parse_natural_language_schedule_json_in_code_block():
    """parse_natural_language_schedule handles JSON in code block."""
    import json

    inner = json.dumps(
        {
            "type": "recurring",
            "schedule": "0 9 * * *",
            "message": "test",
            "name": "test-job",
        }
    )
    mock_response = f"```json\n{inner}\n```"
    with patch(
        "abyss.claude_runner.run_claude",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await parse_natural_language_schedule(
            "every day at 9am test",
            "UTC",
        )
    assert result["type"] == "recurring"
    assert result["schedule"] == "0 9 * * *"


@pytest.mark.asyncio
async def test_parse_natural_language_schedule_invalid_json():
    """parse_natural_language_schedule raises ValueError on invalid JSON."""
    with patch("abyss.claude_runner.run_claude", new_callable=AsyncMock, return_value="not json"):
        with pytest.raises(ValueError, match="Failed to parse"):
            await parse_natural_language_schedule("gibberish", "UTC")


@pytest.mark.asyncio
async def test_parse_natural_language_schedule_missing_fields():
    """parse_natural_language_schedule raises ValueError on incomplete."""
    mock_response = '{"type": "recurring"}'
    with patch(
        "abyss.claude_runner.run_claude",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        with pytest.raises(ValueError, match="Incomplete"):
            await parse_natural_language_schedule("test", "UTC")


@pytest.mark.asyncio
async def test_parse_natural_language_schedule_invalid_cron():
    """parse_natural_language_schedule raises ValueError on bad cron."""
    import json

    mock_response = json.dumps(
        {
            "type": "recurring",
            "schedule": "invalid",
            "message": "test",
            "name": "test",
        }
    )
    with patch(
        "abyss.claude_runner.run_claude",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        with pytest.raises(ValueError, match="Invalid cron"):
            await parse_natural_language_schedule("test", "UTC")
