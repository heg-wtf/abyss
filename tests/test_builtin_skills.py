"""Tests for built-in skill registry and installation."""

from __future__ import annotations

import pytest
import yaml

from abyss.builtin_skills import (
    builtin_skills_directory,
    get_builtin_skill_path,
    is_builtin_skill,
    list_builtin_skills,
)
from abyss.skill import (
    check_skill_requirements,
    install_builtin_skill,
    is_skill,
    list_skills,
    load_skill_config,
    save_skill_config,
    skill_status,
)


@pytest.fixture
def temp_abyss_home(tmp_path, monkeypatch):
    """Set ABYSS_HOME to a temporary directory."""
    home = tmp_path / ".abyss"
    monkeypatch.setenv("ABYSS_HOME", str(home))
    return home


# --- Registry Tests ---


def test_builtin_skills_directory_exists():
    """builtin_skills_directory returns a real directory."""
    directory = builtin_skills_directory()
    assert directory.exists()
    assert directory.is_dir()


def test_list_builtin_skills_returns_imessage():
    """list_builtin_skills includes the imessage skill."""
    skills = list_builtin_skills()
    names = [skill["name"] for skill in skills]
    assert "imessage" in names

    imessage = next(skill for skill in skills if skill["name"] == "imessage")
    assert imessage["description"] != ""
    assert imessage["path"].is_dir()


def test_get_builtin_skill_path_exists():
    """get_builtin_skill_path returns path for existing skill."""
    path = get_builtin_skill_path("imessage")
    assert path is not None
    assert (path / "SKILL.md").exists()
    assert (path / "skill.yaml").exists()


def test_get_builtin_skill_path_nonexistent():
    """get_builtin_skill_path returns None for unknown skill."""
    assert get_builtin_skill_path("nonexistent_skill_xyz") is None


def test_is_builtin_skill():
    """is_builtin_skill returns True for imessage, False for unknown."""
    assert is_builtin_skill("imessage") is True
    assert is_builtin_skill("nonexistent_skill_xyz") is False


# --- Installation Tests ---


def test_install_builtin_skill_creates_directory(temp_abyss_home):
    """install_builtin_skill creates the skill directory."""
    directory = install_builtin_skill("imessage")
    assert directory.exists()
    assert directory.is_dir()
    assert directory == temp_abyss_home / "skills" / "imessage"


def test_install_builtin_skill_copies_files(temp_abyss_home):
    """install_builtin_skill copies SKILL.md and skill.yaml."""
    directory = install_builtin_skill("imessage")
    assert (directory / "SKILL.md").exists()
    assert (directory / "skill.yaml").exists()

    # Verify content is actually copied (not empty)
    skill_md_content = (directory / "SKILL.md").read_text()
    assert "imsg" in skill_md_content

    with open(directory / "skill.yaml") as file:
        config = yaml.safe_load(file)
    assert config["name"] == "imessage"
    assert config["type"] == "cli"


def test_install_builtin_skill_already_exists(temp_abyss_home):
    """install_builtin_skill raises FileExistsError when already installed."""
    install_builtin_skill("imessage")

    with pytest.raises(FileExistsError):
        install_builtin_skill("imessage")


def test_install_builtin_skill_unknown_name(temp_abyss_home):
    """install_builtin_skill raises ValueError for unknown skill name."""
    with pytest.raises(ValueError):
        install_builtin_skill("nonexistent_skill_xyz")


def test_installed_skill_appears_in_list_skills(temp_abyss_home):
    """Installed built-in skill shows up in list_skills()."""
    install_builtin_skill("imessage")

    skills = list_skills()
    names = [skill["name"] for skill in skills]
    assert "imessage" in names


def test_installed_skill_starts_inactive(temp_abyss_home):
    """Installed built-in skill starts with inactive status."""
    install_builtin_skill("imessage")
    assert skill_status("imessage") == "inactive"


def test_installed_skill_is_recognized(temp_abyss_home):
    """Installed built-in skill is recognized by is_skill()."""
    install_builtin_skill("imessage")
    assert is_skill("imessage") is True


def test_installed_skill_config_matches_template(temp_abyss_home):
    """Installed skill config matches the template values."""
    install_builtin_skill("imessage")
    config = load_skill_config("imessage")
    assert config is not None
    assert config["name"] == "imessage"
    assert config["type"] == "cli"
    assert "imsg" in config["required_commands"]
    assert "allowed_tools" in config
    assert "Bash(imsg:*)" in config["allowed_tools"]


def test_installed_skill_requirements_check_with_missing_command(temp_abyss_home):
    """check_skill_requirements reports missing commands with install hint."""
    install_builtin_skill("imessage")

    # Override required_commands to a command that definitely doesn't exist
    config = load_skill_config("imessage")
    config["required_commands"] = ["nonexistent_command_xyz"]
    config["install_hints"] = {"nonexistent_command_xyz": "Download from https://example.com"}

    save_skill_config("imessage", config)

    errors = check_skill_requirements("imessage")
    assert len(errors) == 1
    assert "nonexistent_command_xyz" in errors[0]
    assert "Install:" in errors[0]
    assert "https://example.com" in errors[0]


# --- Reminders Built-in Skill Tests ---


def test_list_builtin_skills_returns_reminders():
    """list_builtin_skills includes the reminders skill."""
    skills = list_builtin_skills()
    names = [skill["name"] for skill in skills]
    assert "reminders" in names

    reminders = next(skill for skill in skills if skill["name"] == "reminders")
    assert reminders["description"] != ""
    assert reminders["path"].is_dir()


def test_get_builtin_skill_path_reminders():
    """get_builtin_skill_path returns path for reminders skill."""
    path = get_builtin_skill_path("reminders")
    assert path is not None
    assert (path / "SKILL.md").exists()
    assert (path / "skill.yaml").exists()


def test_is_builtin_skill_reminders():
    """is_builtin_skill returns True for reminders."""
    assert is_builtin_skill("reminders") is True


def test_install_builtin_skill_reminders(temp_abyss_home):
    """install_builtin_skill creates the reminders skill directory with files."""
    directory = install_builtin_skill("reminders")
    assert directory.exists()
    assert directory == temp_abyss_home / "skills" / "reminders"
    assert (directory / "SKILL.md").exists()
    assert (directory / "skill.yaml").exists()

    # Verify SKILL.md content
    skill_md_content = (directory / "SKILL.md").read_text()
    assert "reminders" in skill_md_content

    # Verify skill.yaml content
    with open(directory / "skill.yaml") as file:
        config = yaml.safe_load(file)
    assert config["name"] == "reminders"
    assert config["type"] == "cli"
    assert "reminders" in config["required_commands"]
    assert "allowed_tools" in config
    assert "Bash(reminders:*)" in config["allowed_tools"]


def test_installed_reminders_skill_starts_inactive(temp_abyss_home):
    """Installed reminders skill starts with inactive status."""
    install_builtin_skill("reminders")
    assert skill_status("reminders") == "inactive"


# --- Image Built-in Skill Tests ---


def test_list_builtin_skills_returns_image():
    """list_builtin_skills includes the image skill."""
    skills = list_builtin_skills()
    names = [skill["name"] for skill in skills]
    assert "image" in names

    image = next(skill for skill in skills if skill["name"] == "image")
    assert image["description"] != ""
    assert image["path"].is_dir()


def test_get_builtin_skill_path_image():
    """get_builtin_skill_path returns path for image skill."""
    path = get_builtin_skill_path("image")
    assert path is not None
    assert (path / "SKILL.md").exists()
    assert (path / "skill.yaml").exists()


def test_is_builtin_skill_image():
    """is_builtin_skill returns True for image."""
    assert is_builtin_skill("image") is True


def test_install_builtin_skill_image(temp_abyss_home):
    """install_builtin_skill creates the image skill directory with files."""
    directory = install_builtin_skill("image")
    assert directory.exists()
    assert directory == temp_abyss_home / "skills" / "image"
    assert (directory / "SKILL.md").exists()
    assert (directory / "skill.yaml").exists()

    # Verify SKILL.md content
    skill_md_content = (directory / "SKILL.md").read_text()
    assert "slimg" in skill_md_content

    # Verify skill.yaml content
    with open(directory / "skill.yaml") as file:
        config = yaml.safe_load(file)
    assert config["name"] == "image"
    assert config["type"] == "cli"
    assert "slimg" in config["required_commands"]
    assert "allowed_tools" in config
    assert "Bash(slimg:*)" in config["allowed_tools"]


def test_installed_image_skill_starts_inactive(temp_abyss_home):
    """Installed image skill starts with inactive status."""
    install_builtin_skill("image")
    assert skill_status("image") == "inactive"


# --- Supabase Built-in Skill Tests ---


def test_list_builtin_skills_returns_supabase():
    """list_builtin_skills includes the supabase skill."""
    skills = list_builtin_skills()
    names = [skill["name"] for skill in skills]
    assert "supabase" in names

    supabase = next(skill for skill in skills if skill["name"] == "supabase")
    assert supabase["description"] != ""
    assert supabase["path"].is_dir()


def test_get_builtin_skill_path_supabase():
    """get_builtin_skill_path returns path for supabase skill."""
    path = get_builtin_skill_path("supabase")
    assert path is not None
    assert (path / "SKILL.md").exists()
    assert (path / "skill.yaml").exists()
    assert (path / "mcp.json").exists()


def test_is_builtin_skill_supabase():
    """is_builtin_skill returns True for supabase."""
    assert is_builtin_skill("supabase") is True


def test_install_builtin_skill_supabase(temp_abyss_home):
    """install_builtin_skill creates the supabase skill directory with files."""
    directory = install_builtin_skill("supabase")
    assert directory.exists()
    assert directory == temp_abyss_home / "skills" / "supabase"
    assert (directory / "SKILL.md").exists()
    assert (directory / "skill.yaml").exists()
    assert (directory / "mcp.json").exists()

    # Verify SKILL.md content contains safety guardrails
    skill_md_content = (directory / "SKILL.md").read_text()
    assert "NEVER DELETE" in skill_md_content
    assert "DELETE FROM" in skill_md_content
    assert "DROP TABLE" in skill_md_content
    assert "TRUNCATE" in skill_md_content
    assert "execute_sql" in skill_md_content

    # Verify skill.yaml content
    with open(directory / "skill.yaml") as file:
        config = yaml.safe_load(file)
    assert config["name"] == "supabase"
    assert config["type"] == "mcp"
    assert "npx" in config["required_commands"]
    assert "SUPABASE_ACCESS_TOKEN" in config["environment_variables"]
    assert "allowed_tools" in config
    assert "mcp__supabase__execute_sql" in config["allowed_tools"]
    assert "mcp__supabase__list_tables" in config["allowed_tools"]

    # Verify destructive tools are NOT in allowed_tools
    assert "mcp__supabase__delete_branch" not in config["allowed_tools"]
    assert "mcp__supabase__reset_branch" not in config["allowed_tools"]
    assert "mcp__supabase__pause_project" not in config["allowed_tools"]

    # Verify mcp.json content
    import json

    with open(directory / "mcp.json") as file:
        mcp_config = json.load(file)
    assert "mcpServers" in mcp_config
    assert "supabase" in mcp_config["mcpServers"]


def test_installed_supabase_skill_starts_inactive(temp_abyss_home):
    """Installed supabase skill starts with inactive status."""
    install_builtin_skill("supabase")
    assert skill_status("supabase") == "inactive"


def test_supabase_mcp_config_merges(temp_abyss_home):
    """Supabase mcp.json integrates with merge_mcp_configs."""
    from abyss.skill import load_skill_mcp_config, merge_mcp_configs

    install_builtin_skill("supabase")

    # Verify MCP config loads
    mcp_config = load_skill_mcp_config("supabase")
    assert mcp_config is not None
    assert "supabase" in mcp_config["mcpServers"]

    # Verify merge works
    merged = merge_mcp_configs(["supabase"])
    assert merged is not None
    assert "supabase" in merged["mcpServers"]


# --- Gmail Built-in Skill Tests ---


def test_list_builtin_skills_returns_gmail():
    """list_builtin_skills includes the gmail skill."""
    skills = list_builtin_skills()
    names = [skill["name"] for skill in skills]
    assert "gmail" in names

    gmail = next(skill for skill in skills if skill["name"] == "gmail")
    assert gmail["description"] != ""
    assert gmail["path"].is_dir()


def test_get_builtin_skill_path_gmail():
    """get_builtin_skill_path returns path for gmail skill."""
    path = get_builtin_skill_path("gmail")
    assert path is not None
    assert (path / "SKILL.md").exists()
    assert (path / "skill.yaml").exists()


def test_is_builtin_skill_gmail():
    """is_builtin_skill returns True for gmail."""
    assert is_builtin_skill("gmail") is True


def test_install_builtin_skill_gmail(temp_abyss_home):
    """install_builtin_skill creates the gmail skill directory with files."""
    directory = install_builtin_skill("gmail")
    assert directory.exists()
    assert directory == temp_abyss_home / "skills" / "gmail"
    assert (directory / "SKILL.md").exists()
    assert (directory / "skill.yaml").exists()

    # Verify SKILL.md content
    skill_md_content = (directory / "SKILL.md").read_text()
    assert "gog gmail" in skill_md_content
    assert "confirm" in skill_md_content.lower()

    # Verify skill.yaml content
    with open(directory / "skill.yaml") as file:
        config = yaml.safe_load(file)
    assert config["name"] == "gmail"
    assert config["type"] == "cli"
    assert "gog" in config["required_commands"]
    assert "GOG_ACCOUNT" in config["environment_variables"]
    assert "Bash(gog:*)" in config["allowed_tools"]


def test_installed_gmail_skill_starts_inactive(temp_abyss_home):
    """Installed gmail skill starts with inactive status."""
    install_builtin_skill("gmail")
    assert skill_status("gmail") == "inactive"


# --- Google Calendar Built-in Skill Tests ---


def test_list_builtin_skills_returns_gcalendar():
    """list_builtin_skills includes the gcalendar skill."""
    skills = list_builtin_skills()
    names = [skill["name"] for skill in skills]
    assert "gcalendar" in names

    gcalendar = next(skill for skill in skills if skill["name"] == "gcalendar")
    assert gcalendar["description"] != ""
    assert gcalendar["path"].is_dir()


def test_get_builtin_skill_path_gcalendar():
    """get_builtin_skill_path returns path for gcalendar skill."""
    path = get_builtin_skill_path("gcalendar")
    assert path is not None
    assert (path / "SKILL.md").exists()
    assert (path / "skill.yaml").exists()


def test_is_builtin_skill_gcalendar():
    """is_builtin_skill returns True for gcalendar."""
    assert is_builtin_skill("gcalendar") is True


def test_install_builtin_skill_gcalendar(temp_abyss_home):
    """install_builtin_skill creates the gcalendar skill directory with files."""
    directory = install_builtin_skill("gcalendar")
    assert directory.exists()
    assert directory == temp_abyss_home / "skills" / "gcalendar"
    assert (directory / "SKILL.md").exists()
    assert (directory / "skill.yaml").exists()

    # Verify SKILL.md content
    skill_md_content = (directory / "SKILL.md").read_text()
    assert "gog calendar" in skill_md_content
    assert "confirm" in skill_md_content.lower()

    # Verify skill.yaml content
    with open(directory / "skill.yaml") as file:
        config = yaml.safe_load(file)
    assert config["name"] == "gcalendar"
    assert config["type"] == "cli"
    assert "gog" in config["required_commands"]
    assert "GOG_ACCOUNT" in config["environment_variables"]
    assert "Bash(gog:*)" in config["allowed_tools"]


def test_installed_gcalendar_skill_starts_inactive(temp_abyss_home):
    """Installed gcalendar skill starts with inactive status."""
    install_builtin_skill("gcalendar")
    assert skill_status("gcalendar") == "inactive"


# --- Twitter Built-in Skill Tests ---


def test_list_builtin_skills_returns_twitter():
    """list_builtin_skills includes the twitter skill."""
    skills = list_builtin_skills()
    names = [skill["name"] for skill in skills]
    assert "twitter" in names

    twitter = next(skill for skill in skills if skill["name"] == "twitter")
    assert twitter["description"] != ""
    assert twitter["path"].is_dir()


def test_get_builtin_skill_path_twitter():
    """get_builtin_skill_path returns path for twitter skill."""
    path = get_builtin_skill_path("twitter")
    assert path is not None
    assert (path / "SKILL.md").exists()
    assert (path / "skill.yaml").exists()
    assert (path / "mcp.json").exists()


def test_is_builtin_skill_twitter():
    """is_builtin_skill returns True for twitter."""
    assert is_builtin_skill("twitter") is True


def test_install_builtin_skill_twitter(temp_abyss_home):
    """install_builtin_skill creates the twitter skill directory with files."""
    directory = install_builtin_skill("twitter")
    assert directory.exists()
    assert directory == temp_abyss_home / "skills" / "twitter"
    assert (directory / "SKILL.md").exists()
    assert (directory / "skill.yaml").exists()
    assert (directory / "mcp.json").exists()

    # Verify SKILL.md content contains safety rules
    skill_md_content = (directory / "SKILL.md").read_text()
    assert "confirm" in skill_md_content.lower()
    assert "280" in skill_md_content
    assert "post_tweet" in skill_md_content.lower() or "Post Tweet" in skill_md_content

    # Verify skill.yaml content
    with open(directory / "skill.yaml") as file:
        config = yaml.safe_load(file)
    assert config["name"] == "twitter"
    assert config["type"] == "mcp"
    assert "npx" in config["required_commands"]
    assert "TWITTER_API_KEY" in config["environment_variables"]
    assert "TWITTER_API_SECRET_KEY" in config["environment_variables"]
    assert "TWITTER_ACCESS_TOKEN" in config["environment_variables"]
    assert "TWITTER_ACCESS_TOKEN_SECRET" in config["environment_variables"]
    assert "allowed_tools" in config
    assert "mcp__twitter__post_tweet" in config["allowed_tools"]
    assert "mcp__twitter__search_tweets" in config["allowed_tools"]

    # Verify mcp.json content
    import json

    with open(directory / "mcp.json") as file:
        mcp_config = json.load(file)
    assert "mcpServers" in mcp_config
    assert "twitter" in mcp_config["mcpServers"]


def test_installed_twitter_skill_starts_inactive(temp_abyss_home):
    """Installed twitter skill starts with inactive status."""
    install_builtin_skill("twitter")
    assert skill_status("twitter") == "inactive"


def test_twitter_mcp_config_merges(temp_abyss_home):
    """Twitter mcp.json integrates with merge_mcp_configs."""
    from abyss.skill import load_skill_mcp_config, merge_mcp_configs

    install_builtin_skill("twitter")

    # Verify MCP config loads
    mcp_config = load_skill_mcp_config("twitter")
    assert mcp_config is not None
    assert "twitter" in mcp_config["mcpServers"]

    # Verify merge works
    merged = merge_mcp_configs(["twitter"])
    assert merged is not None
    assert "twitter" in merged["mcpServers"]


def test_twitter_and_supabase_mcp_configs_merge(temp_abyss_home):
    """Twitter and Supabase MCP configs merge without conflict."""
    from abyss.skill import merge_mcp_configs

    install_builtin_skill("twitter")
    install_builtin_skill("supabase")

    merged = merge_mcp_configs(["twitter", "supabase"])
    assert merged is not None
    assert "twitter" in merged["mcpServers"]
    assert "supabase" in merged["mcpServers"]


# --- Jira Built-in Skill Tests ---


def test_list_builtin_skills_returns_jira():
    """list_builtin_skills includes the jira skill."""
    skills = list_builtin_skills()
    names = [skill["name"] for skill in skills]
    assert "jira" in names

    jira = next(skill for skill in skills if skill["name"] == "jira")
    assert jira["description"] != ""
    assert jira["path"].is_dir()


def test_get_builtin_skill_path_jira():
    """get_builtin_skill_path returns path for jira skill."""
    path = get_builtin_skill_path("jira")
    assert path is not None
    assert (path / "SKILL.md").exists()
    assert (path / "skill.yaml").exists()
    assert (path / "mcp.json").exists()


def test_is_builtin_skill_jira():
    """is_builtin_skill returns True for jira."""
    assert is_builtin_skill("jira") is True


def test_install_builtin_skill_jira(temp_abyss_home):
    """install_builtin_skill creates the jira skill directory with files."""
    directory = install_builtin_skill("jira")
    assert directory.exists()
    assert directory == temp_abyss_home / "skills" / "jira"
    assert (directory / "SKILL.md").exists()
    assert (directory / "skill.yaml").exists()
    assert (directory / "mcp.json").exists()

    # Verify SKILL.md content contains safety rules
    skill_md_content = (directory / "SKILL.md").read_text()
    assert "confirm" in skill_md_content.lower()
    assert "jira_search" in skill_md_content
    assert "jira_create_issue" in skill_md_content

    # Verify skill.yaml content
    with open(directory / "skill.yaml") as file:
        config = yaml.safe_load(file)
    assert config["name"] == "jira"
    assert config["type"] == "mcp"
    assert "uvx" in config["required_commands"]
    assert "JIRA_URL" in config["environment_variables"]
    assert "JIRA_USERNAME" in config["environment_variables"]
    assert "JIRA_API_TOKEN" in config["environment_variables"]
    assert "allowed_tools" in config
    assert "mcp__jira__jira_search" in config["allowed_tools"]
    assert "mcp__jira__jira_get_issue" in config["allowed_tools"]
    assert "mcp__jira__jira_create_issue" in config["allowed_tools"]
    assert "mcp__jira__jira_update_issue" in config["allowed_tools"]
    assert "mcp__jira__jira_transition_issue" in config["allowed_tools"]

    # Verify mcp.json content
    import json

    with open(directory / "mcp.json") as file:
        mcp_config = json.load(file)
    assert "mcpServers" in mcp_config
    assert "jira" in mcp_config["mcpServers"]
    assert mcp_config["mcpServers"]["jira"]["command"] == "uvx"


def test_installed_jira_skill_starts_inactive(temp_abyss_home):
    """Installed jira skill starts with inactive status."""
    install_builtin_skill("jira")
    assert skill_status("jira") == "inactive"


def test_jira_mcp_config_merges(temp_abyss_home):
    """Jira mcp.json integrates with merge_mcp_configs."""
    from abyss.skill import load_skill_mcp_config, merge_mcp_configs

    install_builtin_skill("jira")

    # Verify MCP config loads
    mcp_config = load_skill_mcp_config("jira")
    assert mcp_config is not None
    assert "jira" in mcp_config["mcpServers"]

    # Verify merge works
    merged = merge_mcp_configs(["jira"])
    assert merged is not None
    assert "jira" in merged["mcpServers"]


# --- Translate Skill Tests ---


def test_list_builtin_skills_returns_translate():
    """list_builtin_skills includes the translate skill."""
    skills = list_builtin_skills()
    names = [skill["name"] for skill in skills]
    assert "translate" in names

    translate = next(skill for skill in skills if skill["name"] == "translate")
    assert translate["description"] != ""
    assert translate["path"].is_dir()


def test_get_builtin_skill_path_translate():
    """get_builtin_skill_path returns path for translate skill."""
    path = get_builtin_skill_path("translate")
    assert path is not None
    assert (path / "SKILL.md").exists()
    assert (path / "skill.yaml").exists()


def test_is_builtin_skill_translate():
    """is_builtin_skill returns True for translate."""
    assert is_builtin_skill("translate") is True


def test_install_builtin_skill_translate(temp_abyss_home):
    """install_builtin_skill creates the translate skill directory with files."""
    directory = install_builtin_skill("translate")
    assert directory.exists()
    assert directory == temp_abyss_home / "skills" / "translate"
    assert (directory / "SKILL.md").exists()
    assert (directory / "skill.yaml").exists()

    skill_md_content = (directory / "SKILL.md").read_text()
    assert "translatecli" in skill_md_content
    assert "--sttcli" in skill_md_content

    with open(directory / "skill.yaml") as file:
        config = yaml.safe_load(file)
    assert config["name"] == "translate"
    assert config["type"] == "cli"
    assert "translatecli" in config["required_commands"]
    assert "GEMINI_API_KEY" in config["environment_variables"]
    assert "Bash(translatecli:*)" in config["allowed_tools"]


def test_installed_translate_skill_starts_inactive(temp_abyss_home):
    """Installed translate skill starts with inactive status."""
    install_builtin_skill("translate")
    assert skill_status("translate") == "inactive"


# --- code_review skill (Phase 6) ---


def test_list_builtin_skills_includes_code_review():
    """The code_review builtin skill is registered."""
    skills = list_builtin_skills()
    names = [skill["name"] for skill in skills]
    assert "code_review" in names

    skill = next(s for s in skills if s["name"] == "code_review")
    assert skill["description"]
    assert skill["path"].is_dir()
    assert (skill["path"] / "SKILL.md").exists()
    assert (skill["path"] / "skill.yaml").exists()


def test_code_review_skill_md_references_effort_template():
    """SKILL.md exposes ${CLAUDE_EFFORT} so the template is hot."""
    path = get_builtin_skill_path("code_review")
    assert path is not None
    contents = (path / "SKILL.md").read_text()
    assert "${CLAUDE_EFFORT}" in contents
    assert "claude ultrareview" in contents


def test_code_review_skill_yaml_locks_bash_to_ultrareview():
    """allowed_tools whitelists only ``claude ultrareview`` invocations
    so an attached bot cannot use this skill to run other shell commands.
    """
    import yaml

    path = get_builtin_skill_path("code_review")
    assert path is not None
    with open(path / "skill.yaml") as file:
        config = yaml.safe_load(file)

    assert config["type"] == "cli"
    assert "claude" in config["required_commands"]
    assert config["allowed_tools"] == ["Bash(claude ultrareview:*)"]


def test_installed_code_review_skill_starts_inactive(temp_abyss_home):
    """Installed code_review skill starts with inactive status."""
    install_builtin_skill("code_review")
    assert skill_status("code_review") == "inactive"
