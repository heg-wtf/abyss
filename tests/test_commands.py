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
        result = await commands.cmd_status(make_context(bot_path, bot_config, chat_id=99))
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
        result = await commands.cmd_files(make_context(bot_path, bot_config, chat_id=42))
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
        result = await commands.cmd_memory(make_context(bot_path, bot_config, args=["clear"]))
        assert "cleared" in result.text.lower()
        # Subsequent read returns empty.
        from abyss.session import load_bot_memory

        assert not load_bot_memory(bot_path)

    @pytest.mark.asyncio
    async def test_invalid_subcommand(self, bot_path, bot_config):
        result = await commands.cmd_memory(make_context(bot_path, bot_config, args=["delete"]))
        assert not result.success


class TestResetAll:
    @pytest.mark.asyncio
    async def test_deletes_session_directory(self, bot_path, bot_config):
        directory = ensure_session(bot_path, 7)
        (directory / "workspace" / "trash.md").write_text("x")
        assert directory.exists()
        result = await commands.cmd_resetall(make_context(bot_path, bot_config, chat_id=7))
        assert "reset" in result.text.lower()
        assert not directory.exists()


class TestReset:
    @pytest.mark.asyncio
    async def test_dm_resets_conversation_keeps_workspace(self, bot_path, bot_config):
        directory = ensure_session(bot_path, 11)
        (directory / "workspace" / "keep.md").write_text("keep me")
        (directory / "conversation-260513.md").write_text("user: hi\n")
        outcome = await commands.cmd_reset(make_context(bot_path, bot_config, chat_id=11))
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

        result = await commands.cmd_model(make_context(bot_path, bot_config, args=["opus"]))
        assert result.success
        assert bot_config["model"] == "opus"
        assert saved["name"] == "testbot"
        assert saved["cfg"]["model"] == "opus"

    @pytest.mark.asyncio
    async def test_invalid_model(self, bot_path, bot_config, monkeypatch):
        monkeypatch.setattr(commands, "save_bot_config", lambda *a, **kw: None)
        result = await commands.cmd_model(make_context(bot_path, bot_config, args=["banana"]))
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
        result = await commands.cmd_streaming(make_context(bot_path, bot_config, args=["off"]))
        assert result.success
        assert bot_config["streaming"] is False

    @pytest.mark.asyncio
    async def test_enable(self, bot_path, bot_config, monkeypatch):
        bot_config["streaming"] = False
        monkeypatch.setattr(commands, "save_bot_config", lambda *a, **kw: None)
        result = await commands.cmd_streaming(make_context(bot_path, bot_config, args=["on"]))
        assert result.success
        assert bot_config["streaming"] is True

    @pytest.mark.asyncio
    async def test_invalid_value(self, bot_path, bot_config):
        result = await commands.cmd_streaming(make_context(bot_path, bot_config, args=["maybe"]))
        assert not result.success


class TestSend:
    @pytest.mark.asyncio
    async def test_no_args_lists_files(self, bot_path, bot_config):
        directory = ensure_session(bot_path, 3)
        (directory / "workspace" / "report.md").write_text("hi")
        result = await commands.cmd_send(make_context(bot_path, bot_config, chat_id=3))
        assert not result.success
        assert "report.md" in result.text

    @pytest.mark.asyncio
    async def test_no_args_no_files(self, bot_path, bot_config):
        ensure_session(bot_path, 4)
        result = await commands.cmd_send(make_context(bot_path, bot_config, chat_id=4))
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


# ---------------------------------------------------------------------------
# Bind / Unbind (Telegram-only)
# ---------------------------------------------------------------------------


class TestBind:
    @pytest.mark.asyncio
    async def test_dashboard_session_rejected(self, bot_path, bot_config):
        # String chat_id = dashboard session, not a Telegram chat.
        result = await commands.cmd_bind(
            make_context(bot_path, bot_config, chat_id="chat_web_abcdef", args=["team"])
        )
        assert not result.success
        assert "Telegram" in result.text

    @pytest.mark.asyncio
    async def test_no_args(self, bot_path, bot_config):
        result = await commands.cmd_bind(make_context(bot_path, bot_config))
        assert not result.success
        assert "Usage" in result.text

    @pytest.mark.asyncio
    async def test_group_not_found(self, bot_path, bot_config, monkeypatch):
        monkeypatch.setattr(commands, "load_group_config", lambda name: None)
        result = await commands.cmd_bind(make_context(bot_path, bot_config, args=["ghost"]))
        assert not result.success
        assert "not found" in result.text

    @pytest.mark.asyncio
    async def test_non_orchestrator_silent(self, bot_path, bot_config, monkeypatch):
        monkeypatch.setattr(
            commands,
            "load_group_config",
            lambda name: {"name": "team", "orchestrator": "boss", "members": ["m1"]},
        )
        monkeypatch.setattr(commands, "get_my_role", lambda *a, **kw: "member")
        result = await commands.cmd_bind(make_context(bot_path, bot_config, args=["team"]))
        assert result.silent

    @pytest.mark.asyncio
    async def test_orchestrator_binds(self, bot_path, bot_config, monkeypatch):
        monkeypatch.setattr(
            commands,
            "load_group_config",
            lambda name: {"name": "team", "orchestrator": "testbot", "members": ["m1"]},
        )
        monkeypatch.setattr(commands, "get_my_role", lambda *a, **kw: "orchestrator")
        bound: dict = {}

        def fake_bind(name: str, cid: int) -> None:
            bound["name"] = name
            bound["chat_id"] = cid

        monkeypatch.setattr(commands, "bind_group", fake_bind)
        result = await commands.cmd_bind(make_context(bot_path, bot_config, args=["team"]))
        assert result.success
        assert bound == {"name": "team", "chat_id": 12345}


class TestUnbind:
    @pytest.mark.asyncio
    async def test_dashboard_session_rejected(self, bot_path, bot_config):
        result = await commands.cmd_unbind(make_context(bot_path, bot_config, chat_id="chat_web_x"))
        assert not result.success

    @pytest.mark.asyncio
    async def test_no_binding(self, bot_path, bot_config, monkeypatch):
        monkeypatch.setattr(commands, "find_group_by_chat_id", lambda cid: None)
        result = await commands.cmd_unbind(make_context(bot_path, bot_config))
        assert not result.success
        assert "No group" in result.text

    @pytest.mark.asyncio
    async def test_orchestrator_unbinds(self, bot_path, bot_config, monkeypatch):
        monkeypatch.setattr(
            commands,
            "find_group_by_chat_id",
            lambda cid: {"name": "team", "orchestrator": "testbot", "members": []},
        )
        monkeypatch.setattr(commands, "get_my_role", lambda *a, **kw: "orchestrator")
        unbound: dict = {}
        monkeypatch.setattr(commands, "unbind_group", lambda name: unbound.update({"name": name}))
        result = await commands.cmd_unbind(make_context(bot_path, bot_config))
        assert result.success
        assert unbound["name"] == "team"


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------


class TestSkills:
    @pytest.mark.asyncio
    async def test_no_skills_anywhere(self, bot_path, bot_config, monkeypatch):
        monkeypatch.setattr("abyss.skill.list_skills", lambda: [], raising=False)
        monkeypatch.setattr("abyss.builtin_skills.list_builtin_skills", lambda: [], raising=False)
        result = await commands.cmd_skills(make_context(bot_path, bot_config))
        assert "No skills" in result.text

    @pytest.mark.asyncio
    async def test_list_lists_attached(self, bot_path, bot_config):
        bot_config["skills"] = ["alpha", "beta"]
        result = await commands.cmd_skills(make_context(bot_path, bot_config, args=["list"]))
        assert "alpha" in result.text
        assert "beta" in result.text

    @pytest.mark.asyncio
    async def test_attach_unknown_skill(self, bot_path, bot_config, monkeypatch):
        bot_config["skills"] = []
        monkeypatch.setattr("abyss.skill.is_skill", lambda name: False, raising=False)
        result = await commands.cmd_skills(
            make_context(bot_path, bot_config, args=["attach", "nope"])
        )
        assert not result.success

    @pytest.mark.asyncio
    async def test_attach_inactive(self, bot_path, bot_config, monkeypatch):
        bot_config["skills"] = []
        monkeypatch.setattr("abyss.skill.is_skill", lambda name: True, raising=False)
        monkeypatch.setattr("abyss.skill.skill_status", lambda name: "inactive", raising=False)
        result = await commands.cmd_skills(make_context(bot_path, bot_config, args=["attach", "x"]))
        assert not result.success
        assert "inactive" in result.text

    @pytest.mark.asyncio
    async def test_attach_already(self, bot_path, bot_config, monkeypatch):
        bot_config["skills"] = ["x"]
        monkeypatch.setattr("abyss.skill.is_skill", lambda name: True, raising=False)
        monkeypatch.setattr("abyss.skill.skill_status", lambda name: "active", raising=False)
        result = await commands.cmd_skills(make_context(bot_path, bot_config, args=["attach", "x"]))
        assert not result.success
        assert "already" in result.text

    @pytest.mark.asyncio
    async def test_attach_success(self, bot_path, bot_config, monkeypatch):
        bot_config["skills"] = []
        monkeypatch.setattr("abyss.skill.is_skill", lambda name: True, raising=False)
        monkeypatch.setattr("abyss.skill.skill_status", lambda name: "active", raising=False)
        attached: dict = {}
        monkeypatch.setattr(
            "abyss.skill.attach_skill_to_bot",
            lambda b, s: attached.update({"bot": b, "skill": s}),
            raising=False,
        )
        result = await commands.cmd_skills(make_context(bot_path, bot_config, args=["attach", "x"]))
        assert result.success
        assert "x" in bot_config["skills"]
        assert attached["skill"] == "x"

    @pytest.mark.asyncio
    async def test_detach_not_attached(self, bot_path, bot_config):
        bot_config["skills"] = []
        result = await commands.cmd_skills(make_context(bot_path, bot_config, args=["detach", "x"]))
        assert not result.success

    @pytest.mark.asyncio
    async def test_detach_success(self, bot_path, bot_config, monkeypatch):
        bot_config["skills"] = ["x", "y"]
        detached: dict = {}
        monkeypatch.setattr(
            "abyss.skill.detach_skill_from_bot",
            lambda b, s: detached.update({"bot": b, "skill": s}),
            raising=False,
        )
        result = await commands.cmd_skills(make_context(bot_path, bot_config, args=["detach", "x"]))
        assert result.success
        assert bot_config["skills"] == ["y"]


# ---------------------------------------------------------------------------
# Heartbeat
# ---------------------------------------------------------------------------


class TestHeartbeat:
    @pytest.mark.asyncio
    async def test_status_no_args(self, bot_path, bot_config, monkeypatch):
        monkeypatch.setattr(
            "abyss.heartbeat.get_heartbeat_config",
            lambda b: {
                "enabled": True,
                "interval_minutes": 15,
                "active_hours": {"start": "08:00", "end": "22:00"},
            },
            raising=False,
        )
        result = await commands.cmd_heartbeat(make_context(bot_path, bot_config))
        assert "on" in result.text
        assert "15m" in result.text
        assert "08:00" in result.text

    @pytest.mark.asyncio
    async def test_enable(self, bot_path, bot_config, monkeypatch):
        monkeypatch.setattr("abyss.heartbeat.enable_heartbeat", lambda b: True, raising=False)
        result = await commands.cmd_heartbeat(make_context(bot_path, bot_config, args=["on"]))
        assert result.success
        assert "enabled" in result.text

    @pytest.mark.asyncio
    async def test_disable(self, bot_path, bot_config, monkeypatch):
        monkeypatch.setattr("abyss.heartbeat.disable_heartbeat", lambda b: True, raising=False)
        result = await commands.cmd_heartbeat(make_context(bot_path, bot_config, args=["off"]))
        assert result.success
        assert "disabled" in result.text

    @pytest.mark.asyncio
    async def test_run_not_supported_here(self, bot_path, bot_config):
        # The ``run`` subcommand is platform-specific; commands.py
        # returns a clear "not supported on this surface" marker so
        # adapters can branch.
        result = await commands.cmd_heartbeat(make_context(bot_path, bot_config, args=["run"]))
        assert not result.success
        assert "not supported" in result.text

    @pytest.mark.asyncio
    async def test_unknown_subcommand(self, bot_path, bot_config):
        result = await commands.cmd_heartbeat(make_context(bot_path, bot_config, args=["maybe"]))
        assert not result.success


# ---------------------------------------------------------------------------
# Compact
# ---------------------------------------------------------------------------


class TestCompact:
    @pytest.mark.asyncio
    async def test_preview_no_targets(self, bot_path, bot_config, monkeypatch):
        monkeypatch.setattr(
            "abyss.token_compact.collect_compact_targets",
            lambda b: [],
            raising=False,
        )
        preview = await commands.cmd_compact_preview(make_context(bot_path, bot_config))
        assert preview.targets == []
        assert "No compactable" in preview.text

    @pytest.mark.asyncio
    async def test_preview_lists_targets(self, bot_path, bot_config, monkeypatch):
        class _T:
            def __init__(self, label):
                self.label = label
                self.line_count = 100
                self.token_count = 1000

        monkeypatch.setattr(
            "abyss.token_compact.collect_compact_targets",
            lambda b: [_T("MEMORY.md"), _T("SKILL.md")],
            raising=False,
        )
        preview = await commands.cmd_compact_preview(make_context(bot_path, bot_config))
        assert len(preview.targets) == 2
        assert "MEMORY.md" in preview.text
        assert "Compacting" in preview.text

    @pytest.mark.asyncio
    async def test_run_success(self, bot_path, bot_config, monkeypatch):
        class _R:
            def __init__(self, error=None):
                self.error = error

        async def fake_run(name, model=None):
            return [_R()]

        monkeypatch.setattr("abyss.token_compact.run_compact", fake_run, raising=False)
        monkeypatch.setattr(
            "abyss.token_compact.format_compact_report",
            lambda bot, results: "Report",
            raising=False,
        )
        monkeypatch.setattr(
            "abyss.token_compact.save_compact_results",
            lambda results: None,
            raising=False,
        )
        monkeypatch.setattr(
            "abyss.skill.regenerate_bot_claude_md",
            lambda b: None,
            raising=False,
        )
        monkeypatch.setattr(
            "abyss.skill.update_session_claude_md",
            lambda p: None,
            raising=False,
        )

        result = await commands.cmd_compact_run(make_context(bot_path, bot_config))
        assert result.success
        assert "Report" in result.text
        assert "saved" in result.text.lower()

    @pytest.mark.asyncio
    async def test_run_error(self, bot_path, bot_config, monkeypatch):
        async def fake_run(name, model=None):
            raise RuntimeError("boom")

        monkeypatch.setattr("abyss.token_compact.run_compact", fake_run, raising=False)
        result = await commands.cmd_compact_run(make_context(bot_path, bot_config))
        assert not result.success
        assert "boom" in result.text
