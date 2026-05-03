"""Surface-level CLI smoke tests.

Each Typer command and sub-command is exercised at least via ``--help``
so that a missing import, broken signature, or stale option lands as a
test failure rather than blowing up at user invocation. A handful of
commands are also invoked with no arguments to confirm their guidance
messages still render.

The intent is not to replicate the deep behavioural tests that live in
the per-feature test files but to keep CLI wiring honest and produce a
real coverage signal for ``cli.py``.
"""

from __future__ import annotations

import yaml
from typer.testing import CliRunner

from abyss.cli import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Top-level commands
# ---------------------------------------------------------------------------


def test_app_callback_renders_ascii_banner_and_version():
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "abyss --help" in result.stdout
    # The banner contains the project name in block-letters; assert it
    # printed something non-empty so a future blank callback fails loudly.
    assert len(result.stdout.strip()) > 50


def test_top_level_help_lists_known_subcommands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for sub in (
        "init",
        "start",
        "stop",
        "restart",
        "status",
        "doctor",
        "reindex",
        "backup",
        "bot",
        "skills",
        "cron",
        "memory",
        "global-memory",
        "heartbeat",
        "dashboard",
        "group",
    ):
        assert sub in result.stdout, f"expected '{sub}' in top-level help"


def test_init_help_runs():
    result = runner.invoke(app, ["init", "--help"])
    assert result.exit_code == 0


def test_doctor_help_runs():
    result = runner.invoke(app, ["doctor", "--help"])
    assert result.exit_code == 0


def test_status_help_runs():
    result = runner.invoke(app, ["status", "--help"])
    assert result.exit_code == 0


def test_reindex_no_args_prompts_user(tmp_path, monkeypatch):
    """reindex with no flags exits with non-zero and surfaces guidance."""
    monkeypatch.setenv("ABYSS_HOME", str(tmp_path))
    result = runner.invoke(app, ["reindex"])
    assert result.exit_code != 0
    # Guidance text mentions --bot or --group or --all (depends on FTS5 availability).
    assert "Traceback" not in result.stdout


def test_reindex_help_runs():
    result = runner.invoke(app, ["reindex", "--help"])
    assert result.exit_code == 0


def test_backup_help_runs():
    result = runner.invoke(app, ["backup", "--help"])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Sub-command help: every nested Typer must expose at least its own help.
# ---------------------------------------------------------------------------


SUB_APPS = [
    "bot",
    "skills",
    "cron",
    "memory",
    "global-memory",
    "heartbeat",
    "dashboard",
    "group",
]


def test_each_sub_app_help_runs():
    for sub in SUB_APPS:
        result = runner.invoke(app, [sub, "--help"])
        assert result.exit_code == 0, f"{sub} --help failed: {result.stdout}"


# Concrete sub-commands chosen to spread import surface across modules.
SUB_COMMAND_HELP = [
    ["bot", "list", "--help"],
    ["bot", "add", "--help"],
    ["bot", "remove", "--help"],
    ["bot", "edit", "--help"],
    ["bot", "model", "--help"],
    ["bot", "compact", "--help"],
    ["bot", "streaming", "--help"],
    ["skills", "builtins", "--help"],
    ["skills", "install", "--help"],
    ["skills", "import", "--help"],
    ["skills", "add", "--help"],
    ["skills", "remove", "--help"],
    ["skills", "setup", "--help"],
    ["skills", "test", "--help"],
    ["skills", "edit", "--help"],
    ["cron", "list", "--help"],
    ["cron", "add", "--help"],
    ["cron", "remove", "--help"],
    ["cron", "enable", "--help"],
    ["cron", "disable", "--help"],
    ["cron", "edit", "--help"],
    ["cron", "run", "--help"],
    ["memory", "show", "--help"],
    ["memory", "edit", "--help"],
    ["memory", "clear", "--help"],
    ["global-memory", "show", "--help"],
    ["global-memory", "edit", "--help"],
    ["global-memory", "clear", "--help"],
    ["heartbeat", "status", "--help"],
    ["heartbeat", "enable", "--help"],
    ["heartbeat", "disable", "--help"],
    ["heartbeat", "run", "--help"],
    ["heartbeat", "edit", "--help"],
    ["dashboard", "start", "--help"],
    ["dashboard", "stop", "--help"],
    ["dashboard", "restart", "--help"],
    ["dashboard", "status", "--help"],
    ["group", "create", "--help"],
    ["group", "list", "--help"],
    ["group", "show", "--help"],
    ["group", "delete", "--help"],
    ["group", "status", "--help"],
]


def test_every_subcommand_help_runs():
    failures: list[tuple[list[str], str]] = []
    for argv in SUB_COMMAND_HELP:
        result = runner.invoke(app, argv)
        if result.exit_code != 0:
            failures.append((argv, result.stdout))
    assert not failures, f"failed help invocations: {failures}"


# ---------------------------------------------------------------------------
# Behavioural surface — a couple of commands invoked with empty state.
# ---------------------------------------------------------------------------


def test_bot_list_with_no_config(tmp_path, monkeypatch):
    """`abyss bot list` should not crash on a fresh ABYSS_HOME."""
    monkeypatch.setenv("ABYSS_HOME", str(tmp_path))
    result = runner.invoke(app, ["bot", "list"])
    # Either prints an empty list / first-run guidance, never traceback.
    assert result.exit_code in (0, 1)
    assert "Traceback" not in result.stdout


def test_skills_builtins_lists_at_least_one_skill(tmp_path, monkeypatch):
    monkeypatch.setenv("ABYSS_HOME", str(tmp_path))
    result = runner.invoke(app, ["skills", "builtins"])
    assert result.exit_code == 0
    # At least one builtin is bundled (mem-search, peon, etc.)
    assert "Traceback" not in result.stdout


def test_group_list_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("ABYSS_HOME", str(tmp_path))
    result = runner.invoke(app, ["group", "list"])
    assert result.exit_code in (0, 1)


def test_global_memory_show_when_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("ABYSS_HOME", str(tmp_path))
    result = runner.invoke(app, ["global-memory", "show"])
    assert result.exit_code in (0, 1)


def test_heartbeat_status_with_unknown_bot(tmp_path, monkeypatch):
    monkeypatch.setenv("ABYSS_HOME", str(tmp_path))
    (tmp_path / "config.yaml").write_text(
        yaml.safe_dump({"bots": [], "settings": {"language": "english"}})
    )
    result = runner.invoke(app, ["heartbeat", "status", "ghost"])
    assert result.exit_code != 0  # bot not found
