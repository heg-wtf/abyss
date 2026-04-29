"""Tests for abyss.skill module."""

from __future__ import annotations

import json

import pytest
import yaml

from abyss.skill import (
    VALID_SKILL_TYPES,
    activate_skill,
    attach_skill_to_bot,
    bots_using_skill,
    check_skill_requirements,
    collect_skill_allowed_tools,
    collect_skill_environment_variables,
    compose_claude_md,
    create_skill_directory,
    default_skill_yaml,
    detach_skill_from_bot,
    generate_skill_markdown,
    get_bot_skills,
    is_skill,
    is_valid_skill_type,
    list_skills,
    load_skill_config,
    load_skill_markdown,
    load_skill_mcp_config,
    merge_mcp_configs,
    regenerate_bot_claude_md,
    remove_skill,
    save_skill_config,
    skill_directory,
    skill_status,
    skill_type,
    skills_directory,
    update_session_claude_md,
)


@pytest.fixture
def temp_abyss_home(tmp_path, monkeypatch):
    """Set ABYSS_HOME to a temporary directory."""
    home = tmp_path / ".abyss"
    monkeypatch.setenv("ABYSS_HOME", str(home))
    return home


@pytest.fixture
def setup_skill(temp_abyss_home):
    """Create a sample skill."""
    directory = temp_abyss_home / "skills" / "test-skill"
    directory.mkdir(parents=True)
    (directory / "SKILL.md").write_text("# test-skill\n\nA test skill.")
    return directory


@pytest.fixture
def setup_tool_skill(temp_abyss_home):
    """Create a tool-based skill with skill.yaml."""
    directory = temp_abyss_home / "skills" / "tool-skill"
    directory.mkdir(parents=True)
    (directory / "SKILL.md").write_text("# tool-skill\n\nA CLI tool skill.")
    config = {
        "name": "tool-skill",
        "description": "Tool skill",
        "status": "inactive",
        "type": "cli",
        "required_commands": ["git"],
    }
    with open(directory / "skill.yaml", "w") as file:
        yaml.dump(config, file)
    return directory


@pytest.fixture
def setup_bot(temp_abyss_home):
    """Create a sample bot."""
    from abyss.config import add_bot_to_config, save_bot_config

    bot_config = {
        "telegram_token": "fake-token",
        "telegram_username": "@test_bot",
        "personality": "Helpful",
        "description": "Test bot",
        "allowed_users": [],
        "claude_args": [],
        "skills": [],
    }
    save_bot_config("test-bot", bot_config)
    add_bot_to_config("test-bot")
    return bot_config


# --- Directory Helpers ---


def test_skills_directory(temp_abyss_home):
    """skills_directory returns correct path."""
    assert skills_directory() == temp_abyss_home / "skills"


def test_skill_directory(temp_abyss_home):
    """skill_directory returns correct path for a skill."""
    assert skill_directory("my-skill") == temp_abyss_home / "skills" / "my-skill"


# --- Valid Types ---


def test_valid_skill_types():
    """VALID_SKILL_TYPES contains expected types."""
    assert "cli" in VALID_SKILL_TYPES
    assert "mcp" in VALID_SKILL_TYPES
    assert "browser" in VALID_SKILL_TYPES


def test_is_valid_skill_type():
    """is_valid_skill_type checks correctly."""
    assert is_valid_skill_type("cli") is True
    assert is_valid_skill_type("mcp") is True
    assert is_valid_skill_type("unknown") is False


# --- Recognition & Loading ---


def test_list_skills_empty(temp_abyss_home):
    """list_skills returns empty list when no skills exist."""
    assert list_skills() == []


def test_list_skills_with_skills(setup_skill):
    """list_skills returns skills with SKILL.md."""
    skills = list_skills()
    assert len(skills) == 1
    assert skills[0]["name"] == "test-skill"
    assert skills[0]["status"] == "active"  # No skill.yaml = always active
    assert skills[0]["type"] is None  # No skill.yaml = markdown-only


def test_is_skill_true(setup_skill):
    """is_skill returns True for valid skill."""
    assert is_skill("test-skill") is True


def test_is_skill_false(temp_abyss_home):
    """is_skill returns False for nonexistent skill."""
    assert is_skill("nonexistent") is False


def test_is_skill_no_skill_md(temp_abyss_home):
    """is_skill returns False when directory exists but no SKILL.md."""
    directory = temp_abyss_home / "skills" / "no-md"
    directory.mkdir(parents=True)
    assert is_skill("no-md") is False


def test_load_skill_config_none(setup_skill):
    """load_skill_config returns None for markdown-only skill."""
    assert load_skill_config("test-skill") is None


def test_load_skill_config_exists(setup_tool_skill):
    """load_skill_config returns config dict for tool skill."""
    config = load_skill_config("tool-skill")
    assert config is not None
    assert config["name"] == "tool-skill"
    assert config["type"] == "cli"
    assert config["status"] == "inactive"


def test_save_skill_config(setup_skill):
    """save_skill_config writes skill.yaml."""
    save_skill_config("test-skill", {"name": "test-skill", "status": "active"})
    config = load_skill_config("test-skill")
    assert config["status"] == "active"


def test_load_skill_markdown(setup_skill):
    """load_skill_markdown returns SKILL.md content."""
    markdown = load_skill_markdown("test-skill")
    assert markdown is not None
    assert "# test-skill" in markdown


def test_load_skill_markdown_missing(temp_abyss_home):
    """load_skill_markdown returns None for missing skill."""
    assert load_skill_markdown("nonexistent") is None


def test_skill_status_not_found(temp_abyss_home):
    """skill_status returns not_found for missing skill."""
    assert skill_status("nonexistent") == "not_found"


def test_skill_status_active_markdown_only(setup_skill):
    """Markdown-only skill is always active."""
    assert skill_status("test-skill") == "active"


def test_skill_status_inactive_tool(setup_tool_skill):
    """Tool skill starts as inactive."""
    assert skill_status("tool-skill") == "inactive"


def test_skill_type_none_markdown(setup_skill):
    """Markdown-only skill type is None."""
    assert skill_type("test-skill") is None


def test_skill_type_cli(setup_tool_skill):
    """Tool skill returns its type."""
    assert skill_type("tool-skill") == "cli"


# --- Creation & Deletion ---


def test_create_skill_directory(temp_abyss_home):
    """create_skill_directory creates the directory."""
    directory = create_skill_directory("new-skill")
    assert directory.exists()
    assert directory == temp_abyss_home / "skills" / "new-skill"


def test_generate_skill_markdown():
    """generate_skill_markdown produces expected markdown."""
    result = generate_skill_markdown("test", "A test skill")
    assert "# test" in result
    assert "A test skill" in result


def test_default_skill_yaml():
    """default_skill_yaml returns expected structure."""
    config = default_skill_yaml(
        name="test",
        description="A test",
        skill_type="cli",
        required_commands=["git", "npm"],
        environment_variables=["API_KEY"],
    )
    assert config["name"] == "test"
    assert config["description"] == "A test"
    assert config["type"] == "cli"
    assert config["status"] == "inactive"
    assert "git" in config["required_commands"]
    assert "API_KEY" in config["environment_variables"]


def test_default_skill_yaml_minimal():
    """default_skill_yaml works with minimal args."""
    config = default_skill_yaml(name="simple")
    assert config["name"] == "simple"
    assert "type" not in config
    assert "required_commands" not in config


def test_remove_skill(setup_skill):
    """remove_skill deletes the skill directory."""
    assert is_skill("test-skill") is True
    result = remove_skill("test-skill")
    assert result is True
    assert is_skill("test-skill") is False


def test_remove_skill_not_found(temp_abyss_home):
    """remove_skill returns False for missing skill."""
    assert remove_skill("nonexistent") is False


def test_remove_skill_detaches_from_bots(setup_skill, setup_bot, temp_abyss_home):
    """remove_skill detaches from all bots."""
    attach_skill_to_bot("test-bot", "test-skill")
    assert "test-skill" in get_bot_skills("test-bot")

    remove_skill("test-skill")
    assert "test-skill" not in get_bot_skills("test-bot")


# --- Setup & Activation ---


def test_check_skill_requirements_markdown(setup_skill):
    """Markdown-only skills have no requirements."""
    errors = check_skill_requirements("test-skill")
    assert errors == []


def test_check_skill_requirements_met(setup_tool_skill):
    """check_skill_requirements returns empty when commands are found."""
    # git should be available in most environments
    errors = check_skill_requirements("tool-skill")
    assert errors == []


def test_check_skill_requirements_missing_command(temp_abyss_home):
    """check_skill_requirements reports missing commands."""
    directory = temp_abyss_home / "skills" / "bad-skill"
    directory.mkdir(parents=True)
    (directory / "SKILL.md").write_text("# bad-skill")
    config = {
        "name": "bad-skill",
        "status": "inactive",
        "type": "cli",
        "required_commands": ["nonexistent_command_xyz123"],
    }
    with open(directory / "skill.yaml", "w") as file:
        yaml.dump(config, file)

    errors = check_skill_requirements("bad-skill")
    assert len(errors) == 1
    assert "nonexistent_command_xyz123" in errors[0]


def test_activate_skill(setup_tool_skill):
    """activate_skill sets status to active."""
    assert skill_status("tool-skill") == "inactive"
    activate_skill("tool-skill")
    assert skill_status("tool-skill") == "active"


def test_activate_skill_markdown_only(setup_skill):
    """activate_skill is no-op for markdown-only skill (no skill.yaml)."""
    activate_skill("test-skill")
    # Should not crash; markdown-only remains active by convention


# --- Bot-Skill Connection ---


def test_get_bot_skills_empty(setup_bot):
    """get_bot_skills returns empty list for bot without skills."""
    assert get_bot_skills("test-bot") == []


def test_get_bot_skills_nonexistent():
    """get_bot_skills returns empty list for nonexistent bot."""
    assert get_bot_skills("nonexistent") == []


def test_attach_skill_to_bot(setup_skill, setup_bot):
    """attach_skill_to_bot adds skill to bot config."""
    attach_skill_to_bot("test-bot", "test-skill")
    skills = get_bot_skills("test-bot")
    assert "test-skill" in skills


def test_attach_skill_idempotent(setup_skill, setup_bot):
    """attach_skill_to_bot does not duplicate."""
    attach_skill_to_bot("test-bot", "test-skill")
    attach_skill_to_bot("test-bot", "test-skill")
    skills = get_bot_skills("test-bot")
    assert skills.count("test-skill") == 1


def test_detach_skill_from_bot(setup_skill, setup_bot):
    """detach_skill_from_bot removes skill from bot config."""
    attach_skill_to_bot("test-bot", "test-skill")
    detach_skill_from_bot("test-bot", "test-skill")
    assert "test-skill" not in get_bot_skills("test-bot")


def test_detach_skill_not_attached(setup_bot):
    """detach_skill_from_bot is no-op when skill not attached."""
    detach_skill_from_bot("test-bot", "nonexistent")
    assert get_bot_skills("test-bot") == []


def test_bots_using_skill(setup_skill, setup_bot):
    """bots_using_skill returns bots with the skill attached."""
    assert bots_using_skill("test-skill") == []
    attach_skill_to_bot("test-bot", "test-skill")
    assert "test-bot" in bots_using_skill("test-skill")


# --- CLAUDE.md Composition ---


def test_compose_claude_md_no_skills():
    """compose_claude_md without skills matches generate_claude_md output pattern."""
    result = compose_claude_md(
        bot_name="my-bot",
        personality="Friendly",
        role="Helper",
        skill_names=[],
    )
    assert "# my-bot" in result
    assert "Friendly" in result
    assert "Helper" in result
    assert "Korean" in result
    assert "Available Skills" not in result


def test_compose_claude_md_isolation_directive():
    """compose_claude_md includes isolation directive to ignore parent CLAUDE.md files."""
    result = compose_claude_md(
        bot_name="my-bot",
        personality="Friendly",
        role="Helper",
    )
    lines = result.split("\n")
    # Isolation directive should appear before Personality section
    isolation_index = None
    personality_index = None
    for index, line in enumerate(lines):
        if "Ignore any instructions from ~/.claude/CLAUDE.md" in line:
            isolation_index = index
        if "## Personality" in line:
            personality_index = index
    assert isolation_index is not None, "Isolation directive not found"
    assert personality_index is not None, "Personality section not found"
    assert isolation_index < personality_index, "Isolation directive must appear before Personality"
    assert "Follow ONLY the instructions in this file" in result


def test_compose_claude_md_with_skills(setup_skill):
    """compose_claude_md includes skill content."""
    result = compose_claude_md(
        bot_name="my-bot",
        personality="Friendly",
        role="Helper",
        skill_names=["test-skill"],
    )
    assert "Available Skills" in result
    assert "## test-skill" in result
    assert "A test skill" in result


def test_compose_claude_md_nonexistent_skill():
    """compose_claude_md skips skills that don't exist."""
    result = compose_claude_md(
        bot_name="my-bot",
        personality="Friendly",
        role="Helper",
        skill_names=["nonexistent"],
    )
    assert "Available Skills" not in result


def test_compose_claude_md_with_global_memory(temp_abyss_home):
    """compose_claude_md includes global memory section when present."""
    from abyss.session import save_global_memory

    save_global_memory("- Timezone: Asia/Seoul\n- Language: Korean")

    result = compose_claude_md(
        bot_name="my-bot",
        personality="Friendly",
        role="Helper",
    )
    assert "## Global Memory (Read-Only)" in result
    assert "Timezone: Asia/Seoul" in result
    assert "수정하지 마라" in result


def test_compose_claude_md_no_global_memory(temp_abyss_home):
    """compose_claude_md omits global memory section when not present."""
    result = compose_claude_md(
        bot_name="my-bot",
        personality="Friendly",
        role="Helper",
    )
    assert "Global Memory" not in result


def test_compose_claude_md_global_memory_before_bot_memory(temp_abyss_home):
    """compose_claude_md places global memory before bot memory."""
    from abyss.session import save_global_memory

    save_global_memory("- Global setting")

    bot_path = temp_abyss_home / "bots" / "my-bot"
    bot_path.mkdir(parents=True)

    result = compose_claude_md(
        bot_name="my-bot",
        personality="Friendly",
        role="Helper",
        bot_path=bot_path,
    )
    global_memory_index = result.index("Global Memory (Read-Only)")
    bot_memory_index = result.index("## Memory")
    assert global_memory_index < bot_memory_index


def test_regenerate_bot_claude_md(setup_skill, setup_bot, temp_abyss_home):
    """regenerate_bot_claude_md updates CLAUDE.md."""
    from abyss.config import bot_directory

    attach_skill_to_bot("test-bot", "test-skill")
    regenerate_bot_claude_md("test-bot")

    claude_md = (bot_directory("test-bot") / "CLAUDE.md").read_text()
    assert "Available Skills" in claude_md
    assert "test-skill" in claude_md


def test_regenerate_bot_claude_md_nonexistent():
    """regenerate_bot_claude_md is no-op for missing bot."""
    regenerate_bot_claude_md("nonexistent")  # Should not crash


def test_update_session_claude_md(temp_abyss_home):
    """update_session_claude_md propagates to all sessions."""
    bot_path = temp_abyss_home / "bots" / "test-bot"
    bot_path.mkdir(parents=True)
    (bot_path / "CLAUDE.md").write_text("# Updated content")

    sessions = bot_path / "sessions"
    for i in range(3):
        session = sessions / f"chat_{i}"
        session.mkdir(parents=True)
        (session / "CLAUDE.md").write_text("# Old content")

    update_session_claude_md(bot_path)

    for i in range(3):
        session_claude_md = sessions / f"chat_{i}" / "CLAUDE.md"
        assert session_claude_md.read_text() == "# Updated content"


def test_update_session_claude_md_no_bot_claude_md(tmp_path):
    """update_session_claude_md is no-op when bot CLAUDE.md doesn't exist."""
    update_session_claude_md(tmp_path)  # Should not crash


# --- MCP / Environment Variables ---


def test_load_skill_mcp_config_missing(setup_skill):
    """load_skill_mcp_config returns None when no mcp.json."""
    assert load_skill_mcp_config("test-skill") is None


def test_load_skill_mcp_config_exists(setup_skill):
    """load_skill_mcp_config loads mcp.json."""
    mcp_config = {"mcpServers": {"test": {"command": "test-server"}}}
    mcp_path = skill_directory("test-skill") / "mcp.json"
    with open(mcp_path, "w") as file:
        json.dump(mcp_config, file)

    result = load_skill_mcp_config("test-skill")
    assert result is not None
    assert "test" in result["mcpServers"]


def test_merge_mcp_configs_empty():
    """merge_mcp_configs returns None for empty list."""
    assert merge_mcp_configs([]) is None


def test_merge_mcp_configs_no_mcp_skills(setup_skill):
    """merge_mcp_configs returns None when no skills have MCP config."""
    assert merge_mcp_configs(["test-skill"]) is None


def test_merge_mcp_configs_multiple(temp_abyss_home):
    """merge_mcp_configs merges multiple MCP configs."""
    for i, skill_name in enumerate(["skill-a", "skill-b"]):
        directory = temp_abyss_home / "skills" / skill_name
        directory.mkdir(parents=True)
        (directory / "SKILL.md").write_text(f"# {skill_name}")
        mcp_config = {"mcpServers": {f"server-{i}": {"command": f"cmd-{i}"}}}
        with open(directory / "mcp.json", "w") as file:
            json.dump(mcp_config, file)

    result = merge_mcp_configs(["skill-a", "skill-b"])
    assert result is not None
    assert "server-0" in result["mcpServers"]
    assert "server-1" in result["mcpServers"]


def test_collect_skill_environment_variables_empty():
    """collect_skill_environment_variables returns empty dict for no skills."""
    assert collect_skill_environment_variables([]) == {}


def test_collect_skill_environment_variables_no_config(setup_skill):
    """collect_skill_environment_variables returns empty for markdown-only skill."""
    assert collect_skill_environment_variables(["test-skill"]) == {}


def test_collect_skill_environment_variables_with_values(temp_abyss_home):
    """collect_skill_environment_variables collects from skill.yaml."""
    directory = temp_abyss_home / "skills" / "env-skill"
    directory.mkdir(parents=True)
    (directory / "SKILL.md").write_text("# env-skill")
    config = {
        "name": "env-skill",
        "status": "active",
        "environment_variable_values": {
            "API_KEY": "test-key",
            "SECRET": "test-secret",
        },
    }
    with open(directory / "skill.yaml", "w") as file:
        yaml.dump(config, file)

    result = collect_skill_environment_variables(["env-skill"])
    assert result["API_KEY"] == "test-key"
    assert result["SECRET"] == "test-secret"


# --- Allowed Tools ---


def test_collect_skill_allowed_tools_empty():
    """collect_skill_allowed_tools returns empty list for no skills."""
    assert collect_skill_allowed_tools([]) == []


def test_collect_skill_allowed_tools_no_config(setup_skill):
    """collect_skill_allowed_tools returns empty for markdown-only skill."""
    assert collect_skill_allowed_tools(["test-skill"]) == []


def test_collect_skill_allowed_tools(temp_abyss_home):
    """collect_skill_allowed_tools collects and merges from multiple skills."""
    for skill_name, tools in [
        ("skill-a", ["Bash(imsg:*)"]),
        ("skill-b", ["Bash(curl:*)", "Read(*)"]),
    ]:
        directory = temp_abyss_home / "skills" / skill_name
        directory.mkdir(parents=True)
        (directory / "SKILL.md").write_text(f"# {skill_name}")
        config = {
            "name": skill_name,
            "status": "active",
            "allowed_tools": tools,
        }
        with open(directory / "skill.yaml", "w") as file:
            yaml.dump(config, file)

    result = collect_skill_allowed_tools(["skill-a", "skill-b"])
    assert "Bash(imsg:*)" in result
    assert "Bash(curl:*)" in result
    assert "Read(*)" in result
    assert len(result) == 3


def test_collect_skill_allowed_tools_no_allowed_tools_field(setup_tool_skill):
    """collect_skill_allowed_tools returns empty for skill without allowed_tools."""
    assert collect_skill_allowed_tools(["tool-skill"]) == []


# ─── conversation_search auto-injection ───────────────────────────────────


@pytest.mark.enable_conversation_search
def test_compose_claude_md_auto_injects_conversation_search():
    """When FTS5 is available, the conversation_search SKILL.md is auto-included."""
    result = compose_claude_md(
        bot_name="my-bot",
        personality="Friendly",
        role="Helper",
        skill_names=[],
    )
    assert "Available Skills" in result
    assert "## conversation_search" in result
    assert "search_conversations" in result


@pytest.mark.enable_conversation_search
def test_compose_claude_md_no_duplicate_conversation_search():
    """If conversation_search is already in skill_names, it is not duplicated."""
    result = compose_claude_md(
        bot_name="my-bot",
        personality="Friendly",
        role="Helper",
        skill_names=["conversation_search"],
    )
    occurrences = result.count("## conversation_search")
    assert occurrences == 1


def test_compose_claude_md_skips_conversation_search_when_unavailable():
    """Without FTS5, the auto-inject is skipped."""
    # Default conftest fixture stubs is_fts5_available to False.
    result = compose_claude_md(
        bot_name="my-bot",
        personality="Friendly",
        role="Helper",
        skill_names=[],
    )
    assert "## conversation_search" not in result


# --- collect_skill_hooks tests (Phase 4) ---


def _write_skill_with_hooks(skills_root, name, hooks_yaml):
    """Helper: create a fake skill dir with the given hooks block."""
    import yaml

    from abyss.skill import skill_directory

    skill_path = skill_directory(name)
    skill_path.mkdir(parents=True, exist_ok=True)
    (skill_path / "SKILL.md").write_text(f"# {name}\nDoc.")
    (skill_path / "skill.yaml").write_text(yaml.safe_dump({"hooks": hooks_yaml}))


def test_collect_skill_hooks_returns_entries_for_event(tmp_path, monkeypatch):
    monkeypatch.setenv("ABYSS_HOME", str(tmp_path))

    from abyss.skill import collect_skill_hooks

    _write_skill_with_hooks(
        tmp_path,
        "guard",
        {
            "PostToolUse": [
                {
                    "matcher": "Bash",
                    "if": "tool_input.command =~ /rm -rf/",
                    "hooks": [{"type": "command", "command": "/bin/true"}],
                }
            ]
        },
    )

    entries = collect_skill_hooks(["guard"], "PostToolUse")
    assert len(entries) == 1
    assert entries[0]["matcher"] == "Bash"
    # ``if`` field is preserved verbatim for Claude Code 2.1.85 evaluation.
    assert entries[0]["if"] == "tool_input.command =~ /rm -rf/"


def test_collect_skill_hooks_unknown_event_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("ABYSS_HOME", str(tmp_path))

    from abyss.skill import collect_skill_hooks

    _write_skill_with_hooks(
        tmp_path,
        "guard",
        {"PostToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "x"}]}]},
    )
    assert collect_skill_hooks(["guard"], "NotAnEvent") == []


def test_collect_skill_hooks_skips_malformed_entries(tmp_path, monkeypatch):
    monkeypatch.setenv("ABYSS_HOME", str(tmp_path))

    from abyss.skill import collect_skill_hooks

    _write_skill_with_hooks(
        tmp_path,
        "guard",
        {
            "PostToolUse": [
                "not-a-dict",
                {"matcher": "Bash"},  # missing inner hooks list
                {
                    "matcher": "Read",
                    "hooks": [{"type": "command", "command": "/bin/true"}],
                },
            ]
        },
    )

    entries = collect_skill_hooks(["guard"], "PostToolUse")
    assert len(entries) == 1
    assert entries[0]["matcher"] == "Read"


def test_collect_skill_hooks_concatenates_across_skills(tmp_path, monkeypatch):
    monkeypatch.setenv("ABYSS_HOME", str(tmp_path))

    from abyss.skill import collect_skill_hooks

    _write_skill_with_hooks(
        tmp_path,
        "first",
        {"PostToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "a"}]}]},
    )
    _write_skill_with_hooks(
        tmp_path,
        "second",
        {"PostToolUse": [{"matcher": "Read", "hooks": [{"type": "command", "command": "b"}]}]},
    )

    entries = collect_skill_hooks(["first", "second"], "PostToolUse")
    matchers = [entry["matcher"] for entry in entries]
    assert matchers == ["Bash", "Read"]


# --- Untrusted skill flag (Phase 5) ---


def test_is_untrusted_skill_returns_false_for_missing_yaml(tmp_path, monkeypatch):
    monkeypatch.setenv("ABYSS_HOME", str(tmp_path))
    from abyss.skill import is_untrusted_skill, skill_directory

    skill_path = skill_directory("plain")
    skill_path.mkdir(parents=True)
    (skill_path / "SKILL.md").write_text("# plain\n")
    assert is_untrusted_skill("plain") is False


def test_is_untrusted_skill_reads_flag(tmp_path, monkeypatch):
    monkeypatch.setenv("ABYSS_HOME", str(tmp_path))

    import yaml

    from abyss.skill import is_untrusted_skill, skill_directory

    skill_path = skill_directory("imported")
    skill_path.mkdir(parents=True)
    (skill_path / "SKILL.md").write_text("# imported\n")
    (skill_path / "skill.yaml").write_text(yaml.safe_dump({"untrusted": True}))

    assert is_untrusted_skill("imported") is True


def test_has_untrusted_skill_aggregates(tmp_path, monkeypatch):
    monkeypatch.setenv("ABYSS_HOME", str(tmp_path))

    import yaml

    from abyss.skill import has_untrusted_skill, skill_directory

    safe = skill_directory("safe")
    safe.mkdir(parents=True)
    (safe / "SKILL.md").write_text("# safe\n")

    risky = skill_directory("risky")
    risky.mkdir(parents=True)
    (risky / "SKILL.md").write_text("# risky\n")
    (risky / "skill.yaml").write_text(yaml.safe_dump({"untrusted": True}))

    assert has_untrusted_skill(["safe"]) is False
    assert has_untrusted_skill(["safe", "risky"]) is True


def test_import_skill_from_github_marks_untrusted(tmp_path, monkeypatch):
    """import_skill_from_github writes untrusted: true into the skill.yaml.

    Mocks urllib.request.urlopen so the test runs offline.
    """
    monkeypatch.setenv("ABYSS_HOME", str(tmp_path))

    import io
    from unittest.mock import patch

    import yaml

    from abyss.skill import import_skill_from_github, is_untrusted_skill

    skill_md = b"# test-skill\n\nUseful tool."
    yaml_payload = b"description: imported helper\n"

    def fake_urlopen(url, *args, **kwargs):  # noqa: ARG001
        url_str = url if isinstance(url, str) else url.full_url
        if url_str.endswith("/SKILL.md"):
            return io.BytesIO(skill_md)
        if url_str.endswith("/skill.yaml"):
            return io.BytesIO(yaml_payload)
        # mcp.json absent
        from urllib.error import HTTPError

        raise HTTPError(url_str, 404, "not found", hdrs=None, fp=None)  # type: ignore[arg-type]

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        target = import_skill_from_github("https://github.com/example/test-skill", name="imported")

    assert (target / "SKILL.md").exists()
    yaml_data = yaml.safe_load((target / "skill.yaml").read_text())
    assert yaml_data["untrusted"] is True
    assert yaml_data["source"] == {
        "type": "github",
        "url": "https://github.com/example/test-skill",
    }
    # Original yaml fields preserved.
    assert yaml_data["description"] == "imported helper"
    assert is_untrusted_skill("imported") is True
