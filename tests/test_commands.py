"""Tests for ``abyss.commands`` — platform-independent slash commands."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from abyss import commands
from abyss.session import ensure_session, save_bot_memory


@pytest.fixture
def abyss_home(tmp_path, monkeypatch):
    home = tmp_path / ".abyss"
    home.mkdir()
    monkeypatch.setenv("ABYSS_HOME", str(home))
    return home


@pytest.fixture
def bot_path(abyss_home) -> Path:
    bot_directory = abyss_home / "bots" / "testbot"
    (bot_directory / "sessions").mkdir(parents=True)
    (bot_directory / "CLAUDE.md").write_text("# testbot\n")
    (bot_directory / "bot.yaml").write_text(
        "name: testbot\n"
        "token: dummy\n"
        "display_name: Test Bot\n"
        "personality: helpful\n"
        "role: assistant\n"
        "goal: pass tests\n"
        "model: sonnet\n"
        "streaming: true\n"
        "skills: []\n"
    )
    return bot_directory


@pytest.fixture
def bot_config() -> dict[str, Any]:
    return {
        "display_name": "Test Bot",
        "personality": "helpful",
        "role": "assistant",
        "goal": "pass tests",
        "model": "sonnet",
        "streaming": True,
        "skills": [],
    }


def make_context(
    bot_path: Path,
    bot_config: dict[str, Any],
    *,
    chat_id: int | str = 12345,
    args: list[str] | None = None,
) -> commands.CommandContext:
    return commands.CommandContext(
        bot_name="testbot",
        bot_path=bot_path,
        bot_config=bot_config,
        chat_id=chat_id,
        args=args or [],
    )


# ---------------------------------------------------------------------------
# Pure / read-only commands
# ---------------------------------------------------------------------------


class TestStart:
    @pytest.mark.asyncio
    async def test_uses_display_name(self, bot_path, bot_config):
        result = await commands.cmd_start(make_context(bot_path, bot_config))
        assert "Test Bot" in result.text
        assert "helpful" in result.text
        assert "assistant" in result.text
        assert "pass tests" in result.text

    @pytest.mark.asyncio
    async def test_falls_back_to_bot_name(self, bot_path):
        config = {"personality": "p", "role": "r"}
        result = await commands.cmd_start(make_context(bot_path, config))
        assert "testbot" in result.text

    @pytest.mark.asyncio
    async def test_omits_goal_when_empty(self, bot_path):
        config = {"personality": "p", "role": "r", "goal": ""}
        result = await commands.cmd_start(make_context(bot_path, config))
        assert "Goal:" not in result.text


class TestHelp:
    @pytest.mark.asyncio
    async def test_lists_all_commands(self, bot_path, bot_config):
        result = await commands.cmd_help(make_context(bot_path, bot_config))
        for cmd in ("/start", "/help", "/reset", "/files", "/cron", "/heartbeat"):
            assert cmd in result.text


class TestVersion:
    @pytest.mark.asyncio
    async def test_returns_version_string(self, bot_path, bot_config):
        from abyss import __version__

        result = await commands.cmd_version(make_context(bot_path, bot_config))
        assert __version__ in result.text
        assert result.parse_mode is None


class TestStatus:
    @pytest.mark.asyncio
    async def test_includes_chat_id_and_bot_name(self, bot_path, bot_config):
        result = await commands.cmd_status(
            make_context(bot_path, bot_config, chat_id=99)
        )
        assert "testbot" in result.text
        assert "99" in result.text
        assert "Workspace files: 0" in result.text


class TestFiles:
    @pytest.mark.asyncio
    async def test_empty_workspace(self, bot_path, bot_config):
        result = await commands.cmd_files(make_context(bot_path, bot_config))
        assert "No files" in result.text

    @pytest.mark.asyncio
    async def test_lists_files(self, bot_path, bot_config):
        session_directory = ensure_session(bot_path, 42)
        (session_directory / "workspace" / "notes.md").write_text("hi")
        (session_directory / "workspace" / "data.txt").write_text("data")
        result = await commands.cmd_files(
            make_context(bot_path, bot_config, chat_id=42)
        )
        assert "notes.md" in result.text
        assert "data.txt" in result.text


class TestMemory:
    @pytest.mark.asyncio
    async def test_no_memory(self, bot_path, bot_config):
        result = await commands.cmd_memory(make_context(bot_path, bot_config))
        assert "No memories" in result.text

    @pytest.mark.asyncio
    async def test_show_memory(self, bot_path, bot_config):
        save_bot_memory(bot_path, "# Memories\n- something\n")
        result = await commands.cmd_memory(make_context(bot_path, bot_config))
        assert "something" in result.text
        assert result.parse_mode == "HTML"

    @pytest.mark.asyncio
    async def test_clear_memory(self, bot_path, bot_config):
        save_bot_memory(bot_path, "stuff")
        result = await commands.cmd_memory(
            make_context(bot_path, bot_config, args=["clear"])
        )
        assert "cleared" in result.text.lower()
        # Subsequent read returns empty.
        from abyss.session import load_bot_memory

        assert not load_bot_memory(bot_path)

    @pytest.mark.asyncio
    async def test_invalid_subcommand(self, bot_path, bot_config):
        result = await commands.cmd_memory(
            make_context(bot_path, bot_config, args=["delete"])
        )
        assert not result.success


class TestResetAll:
    @pytest.mark.asyncio
    async def test_deletes_session_directory(self, bot_path, bot_config):
        directory = ensure_session(bot_path, 7)
        (directory / "workspace" / "trash.md").write_text("x")
        assert directory.exists()
        result = await commands.cmd_resetall(
            make_context(bot_path, bot_config, chat_id=7)
        )
        assert "reset" in result.text.lower()
        assert not directory.exists()


class TestReset:
    @pytest.mark.asyncio
    async def test_dm_resets_conversation_keeps_workspace(
        self, bot_path, bot_config
    ):
        directory = ensure_session(bot_path, 11)
        (directory / "workspace" / "keep.md").write_text("keep me")
        (directory / "conversation-260513.md").write_text("user: hi\n")
        outcome = await commands.cmd_reset(
            make_context(bot_path, bot_config, chat_id=11)
        )
        assert outcome.is_group is False
        assert "reset" in outcome.result.text.lower()
        assert (directory / "workspace" / "keep.md").exists()
        assert not (directory / "conversation-260513.md").exists()
        assert outcome.affected_bots == ["testbot"]


class TestModel:
    @pytest.mark.asyncio
    async def test_show_current_model(self, bot_path, bot_config):
        result = await commands.cmd_model(make_context(bot_path, bot_config))
        assert "Current model" in result.text
        # bot_config left untouched
        assert bot_config["model"] == "sonnet"

    @pytest.mark.asyncio
    async def test_change_model(self, bot_path, bot_config, monkeypatch):
        from abyss import config as abyss_config

        saved: dict[str, Any] = {}

        def fake_save(name: str, cfg: dict[str, Any]) -> None:
            saved["name"] = name
            saved["cfg"] = dict(cfg)

        monkeypatch.setattr(abyss_config, "save_bot_config", fake_save)
        monkeypatch.setattr(commands, "save_bot_config", fake_save)

        result = await commands.cmd_model(
            make_context(bot_path, bot_config, args=["opus"])
        )
        assert result.success
        assert bot_config["model"] == "opus"
        assert saved["name"] == "testbot"
        assert saved["cfg"]["model"] == "opus"

    @pytest.mark.asyncio
    async def test_invalid_model(self, bot_path, bot_config, monkeypatch):
        monkeypatch.setattr(commands, "save_bot_config", lambda *a, **kw: None)
        result = await commands.cmd_model(
            make_context(bot_path, bot_config, args=["banana"])
        )
        assert not result.success
        assert bot_config["model"] == "sonnet"


class TestStreaming:
    @pytest.mark.asyncio
    async def test_show_status(self, bot_path, bot_config):
        result = await commands.cmd_streaming(make_context(bot_path, bot_config))
        assert "on" in result.text

    @pytest.mark.asyncio
    async def test_disable(self, bot_path, bot_config, monkeypatch):
        monkeypatch.setattr(commands, "save_bot_config", lambda *a, **kw: None)
        result = await commands.cmd_streaming(
            make_context(bot_path, bot_config, args=["off"])
        )
        assert result.success
        assert bot_config["streaming"] is False

    @pytest.mark.asyncio
    async def test_enable(self, bot_path, bot_config, monkeypatch):
        bot_config["streaming"] = False
        monkeypatch.setattr(commands, "save_bot_config", lambda *a, **kw: None)
        result = await commands.cmd_streaming(
            make_context(bot_path, bot_config, args=["on"])
        )
        assert result.success
        assert bot_config["streaming"] is True

    @pytest.mark.asyncio
    async def test_invalid_value(self, bot_path, bot_config):
        result = await commands.cmd_streaming(
            make_context(bot_path, bot_config, args=["maybe"])
        )
        assert not result.success


class TestSend:
    @pytest.mark.asyncio
    async def test_no_args_lists_files(self, bot_path, bot_config):
        directory = ensure_session(bot_path, 3)
        (directory / "workspace" / "report.md").write_text("hi")
        result = await commands.cmd_send(
            make_context(bot_path, bot_config, chat_id=3)
        )
        assert not result.success
        assert "report.md" in result.text

    @pytest.mark.asyncio
    async def test_no_args_no_files(self, bot_path, bot_config):
        ensure_session(bot_path, 4)
        result = await commands.cmd_send(
            make_context(bot_path, bot_config, chat_id=4)
        )
        assert not result.success
        assert "No files" in result.text

    @pytest.mark.asyncio
    async def test_file_found(self, bot_path, bot_config):
        directory = ensure_session(bot_path, 5)
        target = directory / "workspace" / "good.txt"
        target.write_text("payload")
        result = await commands.cmd_send(
            make_context(bot_path, bot_config, chat_id=5, args=["good.txt"])
        )
        assert result.success
        assert result.file_path == target.resolve()

    @pytest.mark.asyncio
    async def test_file_missing(self, bot_path, bot_config):
        ensure_session(bot_path, 6)
        result = await commands.cmd_send(
            make_context(bot_path, bot_config, chat_id=6, args=["nope.txt"])
        )
        assert not result.success
        assert "not found" in result.text.lower()

    @pytest.mark.asyncio
    async def test_path_traversal_rejected(self, bot_path, bot_config):
        ensure_session(bot_path, 8)
        # Sneaky filename trying to escape the workspace.
        result = await commands.cmd_send(
            make_context(
                bot_path,
                bot_config,
                chat_id=8,
                args=["../../escape.txt"],
            )
        )
        assert not result.success


# ---------------------------------------------------------------------------
# Cancel — caller passes the cancel primitive
# ---------------------------------------------------------------------------


class TestCancel:
    @pytest.mark.asyncio
    async def test_dm_cancel_success(self, bot_path, bot_config):
        seen: list[tuple[str, str]] = []

        async def cancel_for(target_bot: str, key: str) -> bool:
            seen.append((target_bot, key))
            return True

        outcome = await commands.cmd_cancel(
            make_context(bot_path, bot_config, chat_id=10),
            cancel_for=cancel_for,
        )
        assert outcome.result.success
        assert outcome.cancelled_bots == ["testbot"]
        assert seen == [("testbot", "testbot:10")]

    @pytest.mark.asyncio
    async def test_dm_nothing_to_cancel(self, bot_path, bot_config):
        async def cancel_for(target_bot: str, key: str) -> bool:
            return False

        outcome = await commands.cmd_cancel(
            make_context(bot_path, bot_config, chat_id=10),
            cancel_for=cancel_for,
        )
        assert "No running process" in outcome.result.text
