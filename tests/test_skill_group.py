"""Tests for group context in compose_claude_md and compose_group_context."""

from __future__ import annotations

import pytest
import yaml

from cclaw.group import bind_group, create_group
from cclaw.session import ensure_session
from cclaw.skill import compose_claude_md, compose_group_context


@pytest.fixture()
def temp_cclaw_home(tmp_path, monkeypatch):
    """Set CCLAW_HOME to a temporary directory with config and bots."""
    home = tmp_path / ".cclaw"
    home.mkdir()
    monkeypatch.setenv("CCLAW_HOME", str(home))

    config = {
        "bots": [
            {"name": "dev_lead", "path": str(home / "bots" / "dev_lead")},
            {"name": "coder", "path": str(home / "bots" / "coder")},
            {"name": "tester", "path": str(home / "bots" / "tester")},
        ],
        "timezone": "Asia/Seoul",
        "language": "Korean",
    }
    with open(home / "config.yaml", "w") as file:
        yaml.dump(config, file, default_flow_style=False, allow_unicode=True)

    bots = [
        {
            "name": "dev_lead",
            "telegram_token": "fake-token-dev-lead",
            "telegram_username": "@dev_lead_bot",
            "display_name": "Dev Lead",
            "personality": "Technical leader",
            "role": "Team lead",
            "goal": "Manage team",
        },
        {
            "name": "coder",
            "telegram_token": "fake-token-coder",
            "telegram_username": "@coder_bot",
            "display_name": "Coder",
            "personality": "Senior developer",
            "role": "Write code",
            "goal": "Clean code",
        },
        {
            "name": "tester",
            "telegram_token": "fake-token-tester",
            "telegram_username": "@tester_bot",
            "display_name": "Tester",
            "personality": "QA engineer",
            "role": "Write tests",
            "goal": "Bug-free code",
        },
    ]
    for bot in bots:
        bot_directory = home / "bots" / bot["name"]
        bot_directory.mkdir(parents=True, exist_ok=True)
        (bot_directory / "CLAUDE.md").write_text(f"# {bot['name']}")
        (bot_directory / "sessions").mkdir()
        bot_config = {k: v for k, v in bot.items() if k != "name"}
        with open(bot_directory / "bot.yaml", "w") as file:
            yaml.dump(bot_config, file, default_flow_style=False, allow_unicode=True)

    return home


@pytest.fixture()
def dev_team_group(temp_cclaw_home):
    """Create a dev_team group."""
    create_group(name="dev_team", orchestrator="dev_lead", members=["coder", "tester"])
    return "dev_team"


# --- compose_group_context ---


def test_compose_group_context_orchestrator(temp_cclaw_home, dev_team_group):
    """Orchestrator context includes 'orchestrator' and team member info."""
    from cclaw.group import load_group_config

    group_config = load_group_config("dev_team")
    assert group_config is not None

    context = compose_group_context("dev_lead", group_config)

    assert "orchestrator" in context
    assert "Group: dev_team" in context
    # Team members listed with their info
    assert "@coder_bot" in context
    assert "@tester_bot" in context
    assert "Senior developer" in context
    assert "QA engineer" in context


def test_compose_group_context_orchestrator_clarification_rules(temp_cclaw_home, dev_team_group):
    """Orchestrator context includes clarification question rule."""
    from cclaw.group import load_group_config

    group_config = load_group_config("dev_team")
    assert group_config is not None

    context = compose_group_context("dev_lead", group_config)

    assert "ambiguous" in context or "clarifying" in context


def test_compose_group_context_orchestrator_workspace(temp_cclaw_home, dev_team_group):
    """Orchestrator context includes shared workspace path."""
    from cclaw.group import load_group_config

    group_config = load_group_config("dev_team")
    assert group_config is not None

    context = compose_group_context("dev_lead", group_config)

    assert "workspace" in context.lower()
    assert "dev_team" in context


def test_compose_group_context_member(temp_cclaw_home, dev_team_group):
    """Member context includes 'member' and orchestrator @username."""
    from cclaw.group import load_group_config

    group_config = load_group_config("dev_team")
    assert group_config is not None

    context = compose_group_context("coder", group_config)

    assert "member" in context
    assert "Group: dev_team" in context
    assert "@dev_lead_bot" in context
    assert "Only respond when @mentioned" in context


def test_compose_group_context_member_workspace(temp_cclaw_home, dev_team_group):
    """Member context includes shared workspace path."""
    from cclaw.group import load_group_config

    group_config = load_group_config("dev_team")
    assert group_config is not None

    context = compose_group_context("coder", group_config)

    assert "workspace" in context.lower()
    assert "dev_team" in context


def test_compose_group_context_not_in_group(temp_cclaw_home, dev_team_group):
    """Bot not in group gets empty context."""
    from cclaw.group import load_group_config

    group_config = load_group_config("dev_team")
    assert group_config is not None

    context = compose_group_context("unknown_bot", group_config)

    assert context == ""


# --- compose_claude_md with group_context ---


def test_compose_claude_md_without_group(temp_cclaw_home):
    """compose_claude_md without group_context produces standard output."""
    content = compose_claude_md(
        bot_name="coder",
        personality="Senior developer",
        role="Write code",
        goal="Clean code",
    )

    assert "# coder" in content
    assert "Senior developer" in content
    assert "Group:" not in content


def test_compose_claude_md_with_group_orchestrator(temp_cclaw_home, dev_team_group):
    """compose_claude_md with group_context appends orchestrator group section."""
    from cclaw.group import load_group_config

    group_config = load_group_config("dev_team")

    content = compose_claude_md(
        bot_name="dev_lead",
        personality="Technical leader",
        role="Team lead",
        goal="Manage team",
        group_context=group_config,
    )

    # Standard sections present
    assert "# dev_lead" in content
    assert "Technical leader" in content
    # Group section appended
    assert "Group: dev_team" in content
    assert "orchestrator" in content
    assert "@coder_bot" in content
    assert "@tester_bot" in content


def test_compose_claude_md_with_group_member(temp_cclaw_home, dev_team_group):
    """compose_claude_md with group_context appends member group section."""
    from cclaw.group import load_group_config

    group_config = load_group_config("dev_team")

    content = compose_claude_md(
        bot_name="coder",
        personality="Senior developer",
        role="Write code",
        goal="Clean code",
        group_context=group_config,
    )

    assert "# coder" in content
    assert "Senior developer" in content
    assert "Group: dev_team" in content
    assert "member" in content
    assert "@dev_lead_bot" in content


# --- ensure_session with group context ---


def test_ensure_session_dm_no_group_context(temp_cclaw_home):
    """DM session generates standard CLAUDE.md (no group context)."""
    bot_path = temp_cclaw_home / "bots" / "coder"

    session_dir = ensure_session(bot_path, 222, bot_name="coder")
    claude_md = (session_dir / "CLAUDE.md").read_text()

    assert "# coder" in claude_md
    assert "Group:" not in claude_md


def test_ensure_session_group_orchestrator(temp_cclaw_home, dev_team_group):
    """Group session for orchestrator generates CLAUDE.md with orchestrator context."""
    bind_group("dev_team", -12345)
    bot_path = temp_cclaw_home / "bots" / "dev_lead"

    session_dir = ensure_session(bot_path, -12345, bot_name="dev_lead")
    claude_md = (session_dir / "CLAUDE.md").read_text()

    assert "# dev_lead" in claude_md
    assert "Group: dev_team" in claude_md
    assert "orchestrator" in claude_md
    assert "@coder_bot" in claude_md


def test_ensure_session_group_member(temp_cclaw_home, dev_team_group):
    """Group session for member generates CLAUDE.md with member context."""
    bind_group("dev_team", -12345)
    bot_path = temp_cclaw_home / "bots" / "coder"

    session_dir = ensure_session(bot_path, -12345, bot_name="coder")
    claude_md = (session_dir / "CLAUDE.md").read_text()

    assert "# coder" in claude_md
    assert "Group: dev_team" in claude_md
    assert "member" in claude_md
    assert "@dev_lead_bot" in claude_md


def test_ensure_session_same_bot_different_groups(temp_cclaw_home):
    """Same bot in different groups gets different CLAUDE.md per session."""
    create_group(name="team_a", orchestrator="dev_lead", members=["coder"])
    create_group(name="team_b", orchestrator="coder", members=["tester"])
    bind_group("team_a", -11111)
    bind_group("team_b", -22222)

    bot_path = temp_cclaw_home / "bots" / "coder"

    # Group A: coder is a member
    session_a = ensure_session(bot_path, -11111, bot_name="coder")
    claude_md_a = (session_a / "CLAUDE.md").read_text()

    # Group B: coder is the orchestrator
    session_b = ensure_session(bot_path, -22222, bot_name="coder")
    claude_md_b = (session_b / "CLAUDE.md").read_text()

    assert "member" in claude_md_a
    assert "Group: team_a" in claude_md_a

    assert "orchestrator" in claude_md_b
    assert "Group: team_b" in claude_md_b


def test_ensure_session_same_bot_dm_and_group(temp_cclaw_home, dev_team_group):
    """Same bot has group context in group session but not in DM."""
    bind_group("dev_team", -12345)
    bot_path = temp_cclaw_home / "bots" / "coder"

    # DM session
    session_dm = ensure_session(bot_path, 222, bot_name="coder")
    claude_md_dm = (session_dm / "CLAUDE.md").read_text()

    # Group session
    session_group = ensure_session(bot_path, -12345, bot_name="coder")
    claude_md_group = (session_group / "CLAUDE.md").read_text()

    assert "Group:" not in claude_md_dm
    assert "Group: dev_team" in claude_md_group


def test_ensure_session_without_bot_name_uses_copy(temp_cclaw_home, dev_team_group):
    """ensure_session without bot_name falls back to copying bot's CLAUDE.md."""
    bind_group("dev_team", -12345)
    bot_path = temp_cclaw_home / "bots" / "coder"

    # Without bot_name — legacy behavior
    session_dir = ensure_session(bot_path, -12345)
    claude_md = (session_dir / "CLAUDE.md").read_text()

    # Should just be the copied bot CLAUDE.md, not group-aware
    assert claude_md == "# coder"
