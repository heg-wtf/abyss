"""Phase 5: Integration tests for multi-bot group collaboration.

Covers verification sections 6-12 from the group mission plan.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from cclaw.group import (
    bind_group,
    clear_shared_conversation,
    create_group,
    find_group_by_chat_id,
    load_shared_conversation,
    log_to_shared_conversation,
    shared_workspace_path,
)
from cclaw.handlers import make_handlers
from cclaw.session import ensure_session

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def temp_cclaw_home(tmp_path, monkeypatch):
    """Set CCLAW_HOME with 4 registered bots."""
    home = tmp_path / ".cclaw"
    home.mkdir()
    monkeypatch.setenv("CCLAW_HOME", str(home))

    bot_definitions = [
        {
            "name": "dev_lead",
            "telegram_username": "@dev_lead_bot",
            "personality": "Technical leader",
            "role": "Team lead",
            "goal": "Manage team",
        },
        {
            "name": "coder",
            "telegram_username": "@coder_bot",
            "personality": "Senior developer",
            "role": "Write code",
            "goal": "Clean code",
        },
        {
            "name": "tester",
            "telegram_username": "@tester_bot",
            "personality": "QA engineer",
            "role": "Write tests",
            "goal": "Bug-free code",
        },
        {
            "name": "analyst",
            "telegram_username": "@analyst_bot",
            "personality": "Data analyst",
            "role": "Analyze data",
            "goal": "Accurate insights",
        },
    ]

    config = {
        "bots": [
            {"name": b["name"], "path": str(home / "bots" / b["name"])} for b in bot_definitions
        ],
        "timezone": "Asia/Seoul",
        "language": "Korean",
    }
    with open(home / "config.yaml", "w") as file:
        yaml.dump(config, file, default_flow_style=False, allow_unicode=True)

    for bot in bot_definitions:
        bot_directory = home / "bots" / bot["name"]
        bot_directory.mkdir(parents=True, exist_ok=True)
        (bot_directory / "CLAUDE.md").write_text(f"# {bot['name']}")
        (bot_directory / "sessions").mkdir()
        bot_config = {
            "telegram_token": f"fake-token-{bot['name']}",
            "telegram_username": bot["telegram_username"],
            "display_name": bot["name"],
            "personality": bot["personality"],
            "role": bot["role"],
            "goal": bot["goal"],
        }
        with open(bot_directory / "bot.yaml", "w") as file:
            yaml.dump(bot_config, file, default_flow_style=False, allow_unicode=True)

    return home


# Handler indices
RESET_HANDLER_INDEX = 2
MESSAGE_HANDLER_INDEX = 19


def _make_handlers(temp_cclaw_home, bot_name: str) -> list:
    """Create handlers for a bot with streaming disabled."""
    bot_directory = temp_cclaw_home / "bots" / bot_name
    with open(bot_directory / "bot.yaml") as file:
        bot_config = yaml.safe_load(file)
    bot_config.setdefault("allowed_users", [])
    bot_config.setdefault("claude_args", [])
    bot_config.setdefault("command_timeout", 30)
    bot_config["streaming"] = False
    return make_handlers(bot_name, bot_directory, bot_config)


def _mock_update(
    chat_id: int,
    text: str,
    user_id: int = 99999,
    is_bot: bool = False,
    username: str = "human_user",
) -> MagicMock:
    """Create a mock Update for testing."""
    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_chat.id = chat_id
    update.message.text = text
    update.message.from_user.id = user_id
    update.message.from_user.is_bot = is_bot
    update.message.from_user.username = username
    update.message.reply_text = AsyncMock()
    update.message.chat.send_action = AsyncMock()
    update.effective_message = update.message
    return update


# ===========================================================================
# Section 6: Multi-group membership tests
# ===========================================================================


@pytest.mark.asyncio
async def test_bot_member_in_two_groups(temp_cclaw_home):
    """Bot as member in 2 groups reacts independently per group chat_id."""
    create_group(name="team_a", orchestrator="dev_lead", members=["coder"])
    create_group(name="team_b", orchestrator="analyst", members=["coder"])
    bind_group("team_a", -11111)
    bind_group("team_b", -22222)

    coder_handlers = _make_handlers(temp_cclaw_home, "coder")
    msg_handler = coder_handlers[MESSAGE_HANDLER_INDEX]

    # @mention in team_a
    update_a = _mock_update(
        chat_id=-11111,
        text="@coder_bot Write scraper.",
        is_bot=True,
        username="dev_lead_bot",
        user_id=10001,
    )

    with patch("cclaw.handlers.run_claude_with_bridge", new_callable=AsyncMock) as mock_claude:
        mock_claude.return_value = "Done in team_a."
        await msg_handler.callback(update_a, MagicMock())
        mock_claude.assert_called_once()

    # @mention in team_b
    update_b = _mock_update(
        chat_id=-22222,
        text="@coder_bot Analyze data.",
        is_bot=True,
        username="analyst_bot",
        user_id=10002,
    )

    with patch("cclaw.handlers.run_claude_with_bridge", new_callable=AsyncMock) as mock_claude:
        mock_claude.return_value = "Done in team_b."
        await msg_handler.callback(update_b, MagicMock())
        mock_claude.assert_called_once()


@pytest.mark.asyncio
async def test_bot_orchestrator_and_member_different_groups(temp_cclaw_home):
    """Bot as orchestrator in group A and member in group B."""
    create_group(name="team_a", orchestrator="coder", members=["tester"])
    create_group(name="team_b", orchestrator="dev_lead", members=["coder"])
    bind_group("team_a", -11111)
    bind_group("team_b", -22222)

    coder_handlers = _make_handlers(temp_cclaw_home, "coder")
    msg_handler = coder_handlers[MESSAGE_HANDLER_INDEX]

    # In team_a: coder is orchestrator → handles user message
    update_orch = _mock_update(chat_id=-11111, text="Do something", is_bot=False, username="boss")
    with patch("cclaw.handlers.run_claude_with_bridge", new_callable=AsyncMock) as mock_claude:
        mock_claude.return_value = "Got it."
        await msg_handler.callback(update_orch, MagicMock())
        mock_claude.assert_called_once()

    # In team_b: coder is member → only responds to @mention from bot
    update_mem = _mock_update(
        chat_id=-22222, text="General instruction", is_bot=False, username="boss"
    )
    with patch("cclaw.handlers.run_claude_with_bridge", new_callable=AsyncMock) as mock_claude:
        await msg_handler.callback(update_mem, MagicMock())
        mock_claude.assert_not_called()  # Member ignores user messages


@pytest.mark.asyncio
async def test_bot_member_plus_dm_coexist(temp_cclaw_home):
    """Bot works as member in group and personal assistant in DM."""
    create_group(name="team_a", orchestrator="dev_lead", members=["coder"])
    bind_group("team_a", -11111)

    coder_handlers = _make_handlers(temp_cclaw_home, "coder")
    msg_handler = coder_handlers[MESSAGE_HANDLER_INDEX]

    # DM: processes normally
    update_dm = _mock_update(chat_id=222, text="Help me with Python", is_bot=False)
    with patch("cclaw.handlers.run_claude_with_bridge", new_callable=AsyncMock) as mock_claude:
        mock_claude.return_value = "Sure!"
        await msg_handler.callback(update_dm, MagicMock())
        mock_claude.assert_called_once()

    # Group: ignores user message (member role)
    update_group = _mock_update(chat_id=-11111, text="Help me with Python", is_bot=False)
    with patch("cclaw.handlers.run_claude_with_bridge", new_callable=AsyncMock) as mock_claude:
        await msg_handler.callback(update_group, MagicMock())
        mock_claude.assert_not_called()


def test_find_group_by_chat_id_correct_group(temp_cclaw_home):
    """find_group_by_chat_id returns the correct group among multiple."""
    create_group(name="team_a", orchestrator="dev_lead", members=["coder"])
    create_group(name="team_b", orchestrator="analyst", members=["tester"])
    bind_group("team_a", -11111)
    bind_group("team_b", -22222)

    result_a = find_group_by_chat_id(-11111)
    result_b = find_group_by_chat_id(-22222)
    result_none = find_group_by_chat_id(-99999)

    assert result_a is not None and result_a["name"] == "team_a"
    assert result_b is not None and result_b["name"] == "team_b"
    assert result_none is None


# ===========================================================================
# Section 7: Integration scenarios
# ===========================================================================


@pytest.mark.asyncio
async def test_integration_mission_flow(temp_cclaw_home):
    """7-1: Full mission flow — user → orchestrator → member → orchestrator."""
    create_group(name="dev_team", orchestrator="dev_lead", members=["coder", "tester"])
    bind_group("dev_team", -12345)

    dev_lead_handlers = _make_handlers(temp_cclaw_home, "dev_lead")
    coder_handlers = _make_handlers(temp_cclaw_home, "coder")

    dev_lead_msg = dev_lead_handlers[MESSAGE_HANDLER_INDEX]
    coder_msg = coder_handlers[MESSAGE_HANDLER_INDEX]

    # Step 1: User sends mission → orchestrator processes
    update_user = _mock_update(
        chat_id=-12345, text="Build a crawler", is_bot=False, username="boss"
    )
    with patch("cclaw.handlers.run_claude_with_bridge", new_callable=AsyncMock) as mock_claude:
        mock_claude.return_value = "@coder_bot Write a web scraper."
        await dev_lead_msg.callback(update_user, MagicMock())
        mock_claude.assert_called_once()

    # Step 2: Orchestrator's response → coder detects @mention
    update_orch_response = _mock_update(
        chat_id=-12345,
        text="@coder_bot Write a web scraper.",
        is_bot=True,
        username="dev_lead_bot",
        user_id=10001,
    )
    with patch("cclaw.handlers.run_claude_with_bridge", new_callable=AsyncMock) as mock_claude:
        mock_claude.return_value = "@dev_lead_bot Scraper done. workspace/scraper.py"
        await coder_msg.callback(update_orch_response, MagicMock())
        mock_claude.assert_called_once()

    # Step 3: Coder's report → orchestrator processes member report
    update_coder_report = _mock_update(
        chat_id=-12345,
        text="@dev_lead_bot Scraper done. workspace/scraper.py",
        is_bot=True,
        username="coder_bot",
        user_id=10002,
    )
    with patch("cclaw.handlers.run_claude_with_bridge", new_callable=AsyncMock) as mock_claude:
        mock_claude.return_value = "Mission complete."
        await dev_lead_msg.callback(update_coder_report, MagicMock())
        mock_claude.assert_called_once()

    # Verify shared conversation log has all messages
    conversation = load_shared_conversation("dev_team")
    assert "user: Build a crawler" in conversation
    assert "@dev_lead_bot: @coder_bot Write a web scraper." in conversation
    assert "@coder_bot: @dev_lead_bot Scraper done." in conversation


@pytest.mark.asyncio
async def test_integration_member_not_mentioned_stays_silent(temp_cclaw_home):
    """7-1 verification: member does not respond without @mention."""
    create_group(name="dev_team", orchestrator="dev_lead", members=["coder", "tester"])
    bind_group("dev_team", -12345)

    tester_handlers = _make_handlers(temp_cclaw_home, "tester")
    tester_msg = tester_handlers[MESSAGE_HANDLER_INDEX]

    # Orchestrator mentions only @coder_bot, not @tester_bot
    update = _mock_update(
        chat_id=-12345,
        text="@coder_bot Write scraper.",
        is_bot=True,
        username="dev_lead_bot",
        user_id=10001,
    )
    with patch("cclaw.handlers.run_claude_with_bridge", new_callable=AsyncMock) as mock_claude:
        await tester_msg.callback(update, MagicMock())
        mock_claude.assert_not_called()


@pytest.mark.asyncio
async def test_integration_direction_change(temp_cclaw_home):
    """7-2: User changes direction mid-mission → orchestrator handles both."""
    create_group(name="dev_team", orchestrator="dev_lead", members=["coder"])
    bind_group("dev_team", -12345)

    dev_lead_handlers = _make_handlers(temp_cclaw_home, "dev_lead")
    coder_handlers = _make_handlers(temp_cclaw_home, "coder")
    dev_lead_msg = dev_lead_handlers[MESSAGE_HANDLER_INDEX]
    coder_msg = coder_handlers[MESSAGE_HANDLER_INDEX]

    # Initial mission
    update1 = _mock_update(chat_id=-12345, text="Build a crawler", is_bot=False, username="boss")
    with patch("cclaw.handlers.run_claude_with_bridge", new_callable=AsyncMock) as mock_claude:
        mock_claude.return_value = "@coder_bot Write crawler."
        await dev_lead_msg.callback(update1, MagicMock())

    # Coder receives initial delegation (logs orchestrator's message)
    update_orch1 = _mock_update(
        chat_id=-12345,
        text="@coder_bot Write crawler.",
        is_bot=True,
        username="dev_lead_bot",
        user_id=10001,
    )
    with patch("cclaw.handlers.run_claude_with_bridge", new_callable=AsyncMock) as mock_claude:
        mock_claude.return_value = "Working on it."
        await coder_msg.callback(update_orch1, MagicMock())

    # Direction change from user
    update2 = _mock_update(
        chat_id=-12345, text="Actually use API instead", is_bot=False, username="boss"
    )
    with patch("cclaw.handlers.run_claude_with_bridge", new_callable=AsyncMock) as mock_claude:
        mock_claude.return_value = "@coder_bot Switch to API."
        await dev_lead_msg.callback(update2, MagicMock())
        mock_claude.assert_called_once()

    # Coder receives updated delegation (logs orchestrator's new message)
    update_orch2 = _mock_update(
        chat_id=-12345,
        text="@coder_bot Switch to API.",
        is_bot=True,
        username="dev_lead_bot",
        user_id=10001,
    )
    with patch("cclaw.handlers.run_claude_with_bridge", new_callable=AsyncMock) as mock_claude:
        mock_claude.return_value = "Switching to API."
        await coder_msg.callback(update_orch2, MagicMock())

    conversation = load_shared_conversation("dev_team")
    assert "user: Build a crawler" in conversation
    assert "user: Actually use API instead" in conversation
    assert "@dev_lead_bot: @coder_bot Switch to API." in conversation


@pytest.mark.asyncio
async def test_integration_member_failure_report(temp_cclaw_home):
    """7-3: Member reports failure → orchestrator receives and processes."""
    create_group(name="dev_team", orchestrator="dev_lead", members=["coder"])
    bind_group("dev_team", -12345)

    dev_lead_handlers = _make_handlers(temp_cclaw_home, "dev_lead")
    dev_lead_msg = dev_lead_handlers[MESSAGE_HANDLER_INDEX]

    # Coder reports failure
    update = _mock_update(
        chat_id=-12345,
        text="@dev_lead_bot Cloudflare blocked. Cannot crawl.",
        is_bot=True,
        username="coder_bot",
        user_id=10002,
    )
    with patch("cclaw.handlers.run_claude_with_bridge", new_callable=AsyncMock) as mock_claude:
        mock_claude.return_value = "Understood. Trying alternative approach."
        await dev_lead_msg.callback(update, MagicMock())
        mock_claude.assert_called_once()


def test_session_restoration_after_restart(temp_cclaw_home):
    """7-4: After restart, group.yaml binding and conversation log persist."""
    create_group(name="dev_team", orchestrator="dev_lead", members=["coder"])
    bind_group("dev_team", -12345)
    log_to_shared_conversation("dev_team", "user", "Build a crawler")
    log_to_shared_conversation("dev_team", "@dev_lead_bot", "Mission accepted.")

    workspace = shared_workspace_path("dev_team")
    (workspace / "scraper.py").write_text("print('hello')")

    # Simulate restart: re-read everything from disk
    group_config = find_group_by_chat_id(-12345)
    assert group_config is not None
    assert group_config["name"] == "dev_team"
    assert group_config["telegram_chat_id"] == -12345

    conversation = load_shared_conversation("dev_team")
    assert "Build a crawler" in conversation
    assert "Mission accepted." in conversation

    assert (workspace / "scraper.py").exists()


def test_ensure_session_regenerates_group_claude_md(temp_cclaw_home):
    """7-4: ensure_session regenerates group-aware CLAUDE.md after restart."""
    create_group(name="dev_team", orchestrator="dev_lead", members=["coder"])
    bind_group("dev_team", -12345)

    bot_path = temp_cclaw_home / "bots" / "dev_lead"
    session_dir = ensure_session(bot_path, -12345, bot_name="dev_lead")
    claude_md = (session_dir / "CLAUDE.md").read_text()

    assert "orchestrator" in claude_md
    assert "coder" in claude_md

    # Delete CLAUDE.md to simulate restart
    (session_dir / "CLAUDE.md").unlink()

    # Re-call ensure_session — should regenerate
    session_dir2 = ensure_session(bot_path, -12345, bot_name="dev_lead")
    claude_md2 = (session_dir2 / "CLAUDE.md").read_text()
    assert "orchestrator" in claude_md2


# ===========================================================================
# Section 8: Group slash command tests
# ===========================================================================


@pytest.mark.asyncio
async def test_reset_group_orchestrator_resets_all(temp_cclaw_home):
    """/reset in group: orchestrator resets all bots' sessions."""
    create_group(name="dev_team", orchestrator="dev_lead", members=["coder", "tester"])
    bind_group("dev_team", -12345)

    # Create sessions for all bots
    for name in ["dev_lead", "coder", "tester"]:
        bot_path = temp_cclaw_home / "bots" / name
        session_dir = ensure_session(bot_path, -12345, bot_name=name)
        # Write a conversation file
        (session_dir / "conversation-260313.md").write_text("test conversation")

    # Add shared conversation
    log_to_shared_conversation("dev_team", "user", "Hello")

    handlers = _make_handlers(temp_cclaw_home, "dev_lead")
    reset_handler = handlers[RESET_HANDLER_INDEX]

    update = _mock_update(chat_id=-12345, text="/reset")
    await reset_handler.callback(update, MagicMock())

    call_text = update.message.reply_text.call_args[0][0]
    assert "Group session reset" in call_text
    assert "Workspace preserved" in call_text

    # All bots' conversation files should be cleared
    for name in ["dev_lead", "coder", "tester"]:
        bot_path = temp_cclaw_home / "bots" / name
        session_dir = bot_path / "sessions" / "chat_-12345"
        conversation_files = list(session_dir.glob("conversation-*.md"))
        assert len(conversation_files) == 0, f"{name} still has conversation files"

    # Shared conversation should be cleared
    assert load_shared_conversation("dev_team") == ""


@pytest.mark.asyncio
async def test_reset_group_preserves_dm_session(temp_cclaw_home):
    """/reset in group does NOT affect DM sessions."""
    create_group(name="dev_team", orchestrator="dev_lead", members=["coder"])
    bind_group("dev_team", -12345)

    bot_path = temp_cclaw_home / "bots" / "coder"

    # Create DM session
    dm_session = ensure_session(bot_path, 222)
    (dm_session / "conversation-260313.md").write_text("DM conversation")

    # Create group session
    group_session = ensure_session(bot_path, -12345, bot_name="coder")
    (group_session / "conversation-260313.md").write_text("Group conversation")

    # Orchestrator resets group
    handlers = _make_handlers(temp_cclaw_home, "dev_lead")
    reset_handler = handlers[RESET_HANDLER_INDEX]
    update = _mock_update(chat_id=-12345, text="/reset")
    await reset_handler.callback(update, MagicMock())

    # DM session should be untouched
    assert (dm_session / "conversation-260313.md").exists()
    assert (dm_session / "conversation-260313.md").read_text() == "DM conversation"


@pytest.mark.asyncio
async def test_reset_group_preserves_workspace(temp_cclaw_home):
    """/reset in group preserves shared workspace files."""
    create_group(name="dev_team", orchestrator="dev_lead", members=["coder"])
    bind_group("dev_team", -12345)

    workspace = shared_workspace_path("dev_team")
    (workspace / "result.py").write_text("print('result')")

    handlers = _make_handlers(temp_cclaw_home, "dev_lead")
    reset_handler = handlers[RESET_HANDLER_INDEX]
    update = _mock_update(chat_id=-12345, text="/reset")
    await reset_handler.callback(update, MagicMock())

    assert (workspace / "result.py").exists()
    assert (workspace / "result.py").read_text() == "print('result')"


@pytest.mark.asyncio
async def test_reset_group_member_ignored(temp_cclaw_home):
    """/reset by member in group is silently ignored."""
    create_group(name="dev_team", orchestrator="dev_lead", members=["coder"])
    bind_group("dev_team", -12345)

    log_to_shared_conversation("dev_team", "user", "Hello")

    handlers = _make_handlers(temp_cclaw_home, "coder")
    reset_handler = handlers[RESET_HANDLER_INDEX]
    update = _mock_update(chat_id=-12345, text="/reset")
    await reset_handler.callback(update, MagicMock())

    # Member's /reset should be ignored
    update.message.reply_text.assert_not_called()

    # Shared conversation should NOT be cleared
    assert load_shared_conversation("dev_team") != ""


@pytest.mark.asyncio
async def test_reset_dm_unchanged(temp_cclaw_home):
    """/reset in DM works as before (no group logic)."""
    bot_path = temp_cclaw_home / "bots" / "coder"
    session_dir = ensure_session(bot_path, 222)
    (session_dir / "conversation-260313.md").write_text("DM conversation")

    handlers = _make_handlers(temp_cclaw_home, "coder")
    reset_handler = handlers[RESET_HANDLER_INDEX]
    update = _mock_update(chat_id=222, text="/reset")
    await reset_handler.callback(update, MagicMock())

    call_text = update.message.reply_text.call_args[0][0]
    assert "Conversation reset" in call_text
    assert "Group" not in call_text


# ===========================================================================
# Section 9: Shared workspace tests
# ===========================================================================


def test_workspace_flat_structure(temp_cclaw_home):
    """Workspace uses flat structure without per-bot subdirectories."""
    create_group(name="dev_team", orchestrator="dev_lead", members=["coder", "tester"])
    workspace = shared_workspace_path("dev_team")

    (workspace / "scraper.py").write_text("# by coder")
    (workspace / "test_scraper.py").write_text("# by tester")

    files = sorted(f.name for f in workspace.iterdir() if f.is_file())
    assert files == ["scraper.py", "test_scraper.py"]
    # No subdirectories
    subdirs = [f for f in workspace.iterdir() if f.is_dir()]
    assert subdirs == []


def test_workspace_cross_member_read(temp_cclaw_home):
    """One member can read another member's workspace file."""
    create_group(name="dev_team", orchestrator="dev_lead", members=["coder", "tester"])
    workspace = shared_workspace_path("dev_team")

    # Coder writes
    (workspace / "scraper.py").write_text("def scrape(): pass")

    # Tester reads
    content = (workspace / "scraper.py").read_text()
    assert content == "def scrape(): pass"


def test_workspace_file_listing(temp_cclaw_home):
    """Orchestrator can list workspace files."""
    from cclaw.group import list_workspace_files

    create_group(name="dev_team", orchestrator="dev_lead", members=["coder"])
    workspace = shared_workspace_path("dev_team")

    (workspace / "a.py").write_text("")
    (workspace / "b.py").write_text("")

    files = list_workspace_files("dev_team")
    assert sorted(files) == ["a.py", "b.py"]


def test_workspace_preserved_after_conversation_clear(temp_cclaw_home):
    """Clearing conversation log does not affect workspace."""
    create_group(name="dev_team", orchestrator="dev_lead", members=["coder"])
    workspace = shared_workspace_path("dev_team")
    (workspace / "result.txt").write_text("data")

    log_to_shared_conversation("dev_team", "user", "test")
    clear_shared_conversation("dev_team")

    assert (workspace / "result.txt").exists()
    assert load_shared_conversation("dev_team") == ""


# ===========================================================================
# Section 10: Parallel task tests
# ===========================================================================


@pytest.mark.asyncio
async def test_dual_mention_both_bots_react(temp_cclaw_home):
    """Orchestrator @mentions 2 bots in one message — both react."""
    create_group(name="dev_team", orchestrator="dev_lead", members=["coder", "tester"])
    bind_group("dev_team", -12345)

    coder_handlers = _make_handlers(temp_cclaw_home, "coder")
    tester_handlers = _make_handlers(temp_cclaw_home, "tester")

    # Orchestrator mentions both
    text = "@coder_bot Write scraper. @tester_bot Write tests."
    update_coder = _mock_update(
        chat_id=-12345, text=text, is_bot=True, username="dev_lead_bot", user_id=10001
    )
    update_tester = _mock_update(
        chat_id=-12345, text=text, is_bot=True, username="dev_lead_bot", user_id=10001
    )

    with patch("cclaw.handlers.run_claude_with_bridge", new_callable=AsyncMock) as mock_claude:
        mock_claude.return_value = "Done."
        await coder_handlers[MESSAGE_HANDLER_INDEX].callback(update_coder, MagicMock())
        mock_claude.assert_called_once()

    with patch("cclaw.handlers.run_claude_with_bridge", new_callable=AsyncMock) as mock_claude:
        mock_claude.return_value = "Tests done."
        await tester_handlers[MESSAGE_HANDLER_INDEX].callback(update_tester, MagicMock())
        mock_claude.assert_called_once()


@pytest.mark.asyncio
async def test_concurrent_workspace_writes(temp_cclaw_home):
    """Two bots writing different files to workspace simultaneously."""
    import asyncio

    create_group(name="dev_team", orchestrator="dev_lead", members=["coder", "tester"])
    workspace = shared_workspace_path("dev_team")

    async def write_file(name: str, content: str) -> None:
        path = workspace / name
        path.write_text(content)
        await asyncio.sleep(0)  # yield

    await asyncio.gather(
        write_file("scraper.py", "# by coder"),
        write_file("test_scraper.py", "# by tester"),
    )

    assert (workspace / "scraper.py").read_text() == "# by coder"
    assert (workspace / "test_scraper.py").read_text() == "# by tester"


# ===========================================================================
# Section 11: Orchestrator question handling
# ===========================================================================


@pytest.mark.asyncio
async def test_member_question_to_orchestrator(temp_cclaw_home):
    """Member's @mention question to orchestrator is processed."""
    create_group(name="dev_team", orchestrator="dev_lead", members=["coder"])
    bind_group("dev_team", -12345)

    dev_lead_handlers = _make_handlers(temp_cclaw_home, "dev_lead")
    msg = dev_lead_handlers[MESSAGE_HANDLER_INDEX]

    update = _mock_update(
        chat_id=-12345,
        text="@dev_lead_bot Should I use UTF-8?",
        is_bot=True,
        username="coder_bot",
        user_id=10002,
    )
    with patch("cclaw.handlers.run_claude_with_bridge", new_callable=AsyncMock) as mock_claude:
        mock_claude.return_value = "@coder_bot Yes, use UTF-8 without BOM."
        await msg.callback(update, MagicMock())
        mock_claude.assert_called_once()


# ===========================================================================
# Section 12: Edge case tests
# ===========================================================================


@pytest.mark.asyncio
async def test_orchestrator_alone_processes_user_message(temp_cclaw_home):
    """Orchestrator with no members present still processes user messages."""
    create_group(name="solo_team", orchestrator="dev_lead", members=["coder"])
    bind_group("solo_team", -12345)

    handlers = _make_handlers(temp_cclaw_home, "dev_lead")
    msg = handlers[MESSAGE_HANDLER_INDEX]

    update = _mock_update(chat_id=-12345, text="Do everything yourself", is_bot=False)
    with patch("cclaw.handlers.run_claude_with_bridge", new_callable=AsyncMock) as mock_claude:
        mock_claude.return_value = "I'll handle it."
        await msg.callback(update, MagicMock())
        mock_claude.assert_called_once()


@pytest.mark.asyncio
async def test_user_general_message_orchestrator_only(temp_cclaw_home):
    """User general message (no @mention) → only orchestrator responds."""
    create_group(name="dev_team", orchestrator="dev_lead", members=["coder"])
    bind_group("dev_team", -12345)

    orch_handlers = _make_handlers(temp_cclaw_home, "dev_lead")
    member_handlers = _make_handlers(temp_cclaw_home, "coder")

    update = _mock_update(chat_id=-12345, text="What is the status?", is_bot=False)

    with patch("cclaw.handlers.run_claude_with_bridge", new_callable=AsyncMock) as mock_claude:
        mock_claude.return_value = "Status: all good."
        await orch_handlers[MESSAGE_HANDLER_INDEX].callback(update, MagicMock())
        mock_claude.assert_called_once()

    update2 = _mock_update(chat_id=-12345, text="What is the status?", is_bot=False)
    with patch("cclaw.handlers.run_claude_with_bridge", new_callable=AsyncMock) as mock_claude:
        await member_handlers[MESSAGE_HANDLER_INDEX].callback(update2, MagicMock())
        mock_claude.assert_not_called()


def test_same_chat_id_double_bind_rejected(temp_cclaw_home):
    """Same chat_id cannot be bound to two different groups."""
    create_group(name="team_a", orchestrator="dev_lead", members=["coder"])
    create_group(name="team_b", orchestrator="analyst", members=["tester"])

    bind_group("team_a", -12345)

    with pytest.raises(ValueError, match="already bound"):
        bind_group("team_b", -12345)


def test_group_name_with_korean(temp_cclaw_home):
    """Group with Korean name in group.yaml is handled safely."""
    create_group(name="개발팀", orchestrator="dev_lead", members=["coder"])

    config = find_group_by_chat_id(-12345)
    assert config is None  # Not bound yet

    bind_group("개발팀", -12345)
    config = find_group_by_chat_id(-12345)
    assert config is not None
    assert config["name"] == "개발팀"


def test_group_name_with_special_characters(temp_cclaw_home):
    """Group with hyphens and underscores works."""
    create_group(name="dev-team_2026", orchestrator="dev_lead", members=["coder"])
    bind_group("dev-team_2026", -12345)

    config = find_group_by_chat_id(-12345)
    assert config is not None
    assert config["name"] == "dev-team_2026"


def test_clear_shared_conversation(temp_cclaw_home):
    """clear_shared_conversation removes all conversation files."""
    create_group(name="dev_team", orchestrator="dev_lead", members=["coder"])
    log_to_shared_conversation("dev_team", "user", "Message 1")
    log_to_shared_conversation("dev_team", "user", "Message 2")

    assert load_shared_conversation("dev_team") != ""

    clear_shared_conversation("dev_team")
    assert load_shared_conversation("dev_team") == ""


def test_clear_shared_conversation_empty_is_safe(temp_cclaw_home):
    """clear_shared_conversation on empty group does not error."""
    create_group(name="dev_team", orchestrator="dev_lead", members=["coder"])
    clear_shared_conversation("dev_team")  # Should not raise


# ===========================================================================
# Section 8 (continued): Group /cancel tests
# ===========================================================================

CANCEL_HANDLER_INDEX = 9


@pytest.mark.asyncio
async def test_cancel_group_orchestrator_cancels_all(temp_cclaw_home):
    """/cancel in group: orchestrator cancels all bots' processes."""
    create_group(name="dev_team", orchestrator="dev_lead", members=["coder", "tester"])
    bind_group("dev_team", -12345)

    handlers = _make_handlers(temp_cclaw_home, "dev_lead")
    cancel_handler = handlers[CANCEL_HANDLER_INDEX]

    update = _mock_update(chat_id=-12345, text="/cancel")

    with (
        patch("cclaw.handlers.is_process_running") as mock_running,
        patch("cclaw.handlers.cancel_process") as mock_cancel,
    ):
        # dev_lead and coder are running, tester is not
        def running_side_effect(key):
            return key in ("dev_lead:-12345", "coder:-12345")

        mock_running.side_effect = running_side_effect
        mock_cancel.return_value = True

        await cancel_handler.callback(update, MagicMock())

    call_text = update.message.reply_text.call_args[0][0]
    assert "dev_lead" in call_text
    assert "coder" in call_text
    assert "tester" not in call_text


@pytest.mark.asyncio
async def test_cancel_group_no_running_processes(temp_cclaw_home):
    """/cancel in group with no running processes."""
    create_group(name="dev_team", orchestrator="dev_lead", members=["coder"])
    bind_group("dev_team", -12345)

    handlers = _make_handlers(temp_cclaw_home, "dev_lead")
    cancel_handler = handlers[CANCEL_HANDLER_INDEX]

    update = _mock_update(chat_id=-12345, text="/cancel")

    with patch("cclaw.handlers.is_process_running", return_value=False):
        await cancel_handler.callback(update, MagicMock())

    call_text = update.message.reply_text.call_args[0][0]
    assert "No running processes" in call_text


@pytest.mark.asyncio
async def test_cancel_group_member_ignored(temp_cclaw_home):
    """/cancel by member in group is silently ignored."""
    create_group(name="dev_team", orchestrator="dev_lead", members=["coder"])
    bind_group("dev_team", -12345)

    handlers = _make_handlers(temp_cclaw_home, "coder")
    cancel_handler = handlers[CANCEL_HANDLER_INDEX]

    update = _mock_update(chat_id=-12345, text="/cancel")

    with patch("cclaw.handlers.is_process_running", return_value=True):
        await cancel_handler.callback(update, MagicMock())

    update.message.reply_text.assert_not_called()


@pytest.mark.asyncio
async def test_cancel_group_dm_process_unaffected(temp_cclaw_home):
    """/cancel in group does NOT affect DM processes."""
    create_group(name="dev_team", orchestrator="dev_lead", members=["coder"])
    bind_group("dev_team", -12345)

    handlers = _make_handlers(temp_cclaw_home, "dev_lead")
    cancel_handler = handlers[CANCEL_HANDLER_INDEX]

    update = _mock_update(chat_id=-12345, text="/cancel")

    cancelled_keys: list[str] = []

    def cancel_side_effect(key):
        cancelled_keys.append(key)
        return True

    with (
        patch("cclaw.handlers.is_process_running", return_value=True),
        patch("cclaw.handlers.cancel_process", side_effect=cancel_side_effect),
    ):
        await cancel_handler.callback(update, MagicMock())

    # Only group keys should be cancelled, not DM keys
    for key in cancelled_keys:
        assert ":-12345" in key
    assert "dev_lead:222" not in cancelled_keys
    assert "coder:222" not in cancelled_keys


@pytest.mark.asyncio
async def test_cancel_dm_unchanged(temp_cclaw_home):
    """/cancel in DM works as before (no group logic)."""
    handlers = _make_handlers(temp_cclaw_home, "coder")
    cancel_handler = handlers[CANCEL_HANDLER_INDEX]

    update = _mock_update(chat_id=222, text="/cancel")

    with (
        patch("cclaw.handlers.is_process_running", return_value=True),
        patch("cclaw.handlers.cancel_process", return_value=True),
    ):
        await cancel_handler.callback(update, MagicMock())

    call_text = update.message.reply_text.call_args[0][0]
    assert "Execution cancelled" in call_text


# ===========================================================================
# Section 12 (continued): Remaining edge cases
# ===========================================================================


@pytest.mark.asyncio
async def test_concurrent_bots_same_message(temp_cclaw_home):
    """Two bots processing the same group message don't interfere."""
    import asyncio

    create_group(name="dev_team", orchestrator="dev_lead", members=["coder"])
    bind_group("dev_team", -12345)

    dev_lead_handlers = _make_handlers(temp_cclaw_home, "dev_lead")
    coder_handlers = _make_handlers(temp_cclaw_home, "coder")

    # User message — orchestrator should process, member should not
    update_dev = _mock_update(chat_id=-12345, text="Build something", is_bot=False)
    update_coder = _mock_update(chat_id=-12345, text="Build something", is_bot=False)

    mock_claude = AsyncMock(return_value="Orchestrator response.")

    with patch("cclaw.handlers.run_claude_with_bridge", mock_claude):
        await asyncio.gather(
            dev_lead_handlers[MESSAGE_HANDLER_INDEX].callback(update_dev, MagicMock()),
            coder_handlers[MESSAGE_HANDLER_INDEX].callback(update_coder, MagicMock()),
        )

    # Only orchestrator should have called Claude (once)
    mock_claude.assert_called_once()


def test_long_message_split(temp_cclaw_home):
    """Messages over 4096 chars are properly split by split_message."""
    from cclaw.utils import split_message

    long_text = "A" * 5000
    parts = split_message(long_text)
    assert len(parts) >= 2
    assert all(len(p) <= 4096 for p in parts)
    assert "".join(parts) == long_text
