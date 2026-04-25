"""Tests for group-related handler logic in abyss.handlers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from abyss.group import bind_group, create_group, load_group_config
from abyss.handlers import _is_mentioned, make_handlers


@pytest.fixture()
def temp_abyss_home(tmp_path, monkeypatch):
    """Set ABYSS_HOME to a temporary directory with config and bots."""
    home = tmp_path / ".abyss"
    home.mkdir()
    monkeypatch.setenv("ABYSS_HOME", str(home))

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
def dev_team_group(temp_abyss_home):
    """Create and bind a dev_team group."""
    create_group(name="dev_team", orchestrator="dev_lead", members=["coder", "tester"])
    bind_group("dev_team", -12345)
    return "dev_team"


def _make_bot_handlers(temp_abyss_home, bot_name: str) -> list:
    """Create handlers for a specific bot."""
    bot_directory = temp_abyss_home / "bots" / bot_name
    bot_yaml = bot_directory / "bot.yaml"
    with open(bot_yaml) as file:
        bot_config = yaml.safe_load(file)
    bot_config.setdefault("allowed_users", [])
    bot_config.setdefault("claude_args", [])
    bot_config.setdefault("command_timeout", 30)
    bot_config["streaming"] = False
    return make_handlers(bot_name, bot_directory, bot_config)


def _mock_update_for_group(
    chat_id: int,
    text: str,
    user_id: int = 99999,
    is_bot: bool = False,
    username: str = "human_user",
) -> MagicMock:
    """Create a mock Update for group chat testing."""
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


# --- _is_mentioned helper ---


def test_is_mentioned_with_at_prefix():
    """_is_mentioned detects @username in message text."""
    message = MagicMock()
    message.text = "Hey @coder_bot please do this"
    assert _is_mentioned(message, "@coder_bot") is True


def test_is_mentioned_without_at_prefix():
    """_is_mentioned works when bot_username has no @ prefix."""
    message = MagicMock()
    message.text = "Hey @coder_bot please do this"
    assert _is_mentioned(message, "coder_bot") is True


def test_is_mentioned_not_found():
    """_is_mentioned returns False when bot is not mentioned."""
    message = MagicMock()
    message.text = "Hey @tester_bot please do this"
    assert _is_mentioned(message, "@coder_bot") is False


def test_is_mentioned_empty_text():
    """_is_mentioned handles None/empty text."""
    message = MagicMock()
    message.text = None
    assert _is_mentioned(message, "@coder_bot") is False


# --- /bind handler ---


BIND_HANDLER_INDEX = 16
UNBIND_HANDLER_INDEX = 17
MESSAGE_HANDLER_INDEX = 19


@pytest.mark.asyncio
async def test_bind_handler_orchestrator_success(temp_abyss_home):
    """/bind by orchestrator bot binds the group and sends confirmation."""
    create_group(name="dev_team", orchestrator="dev_lead", members=["coder", "tester"])

    handlers = _make_bot_handlers(temp_abyss_home, "dev_lead")
    bind_handler = handlers[BIND_HANDLER_INDEX]

    update = _mock_update_for_group(chat_id=-12345, text="/bind dev_team")
    mock_context = MagicMock()
    mock_context.args = ["dev_team"]

    await bind_handler.callback(update, mock_context)

    update.message.reply_text.assert_called_once()
    call_text = update.message.reply_text.call_args[0][0]
    assert "dev_team" in call_text
    assert "activated" in call_text
    assert "dev_lead" in call_text

    # Verify binding persisted
    config = load_group_config("dev_team")
    assert config is not None
    assert config["telegram_chat_id"] == -12345


@pytest.mark.asyncio
async def test_bind_handler_member_ignores(temp_abyss_home):
    """/bind by member bot is silently ignored."""
    create_group(name="dev_team", orchestrator="dev_lead", members=["coder", "tester"])

    handlers = _make_bot_handlers(temp_abyss_home, "coder")
    bind_handler = handlers[BIND_HANDLER_INDEX]

    update = _mock_update_for_group(chat_id=-12345, text="/bind dev_team")
    mock_context = MagicMock()
    mock_context.args = ["dev_team"]

    await bind_handler.callback(update, mock_context)

    # Member should NOT reply
    update.message.reply_text.assert_not_called()

    # Group should NOT be bound
    config = load_group_config("dev_team")
    assert config is not None
    assert config["telegram_chat_id"] is None


@pytest.mark.asyncio
async def test_bind_handler_nonexistent_group(temp_abyss_home):
    """/bind with nonexistent group name shows error."""
    handlers = _make_bot_handlers(temp_abyss_home, "dev_lead")
    bind_handler = handlers[BIND_HANDLER_INDEX]

    update = _mock_update_for_group(chat_id=-12345, text="/bind nonexistent")
    mock_context = MagicMock()
    mock_context.args = ["nonexistent"]

    await bind_handler.callback(update, mock_context)

    call_text = update.message.reply_text.call_args[0][0]
    assert "not found" in call_text


@pytest.mark.asyncio
async def test_bind_handler_already_bound_overwrites(temp_abyss_home):
    """/bind overwrites existing binding for the same group."""
    create_group(name="dev_team", orchestrator="dev_lead", members=["coder"])
    bind_group("dev_team", -11111)

    handlers = _make_bot_handlers(temp_abyss_home, "dev_lead")
    bind_handler = handlers[BIND_HANDLER_INDEX]

    update = _mock_update_for_group(chat_id=-22222, text="/bind dev_team")
    mock_context = MagicMock()
    mock_context.args = ["dev_team"]

    await bind_handler.callback(update, mock_context)

    call_text = update.message.reply_text.call_args[0][0]
    assert "activated" in call_text

    config = load_group_config("dev_team")
    assert config is not None
    assert config["telegram_chat_id"] == -22222


@pytest.mark.asyncio
async def test_bind_handler_no_args(temp_abyss_home):
    """/bind with no arguments shows usage."""
    handlers = _make_bot_handlers(temp_abyss_home, "dev_lead")
    bind_handler = handlers[BIND_HANDLER_INDEX]

    update = _mock_update_for_group(chat_id=-12345, text="/bind")
    mock_context = MagicMock()
    mock_context.args = []

    await bind_handler.callback(update, mock_context)

    call_text = update.message.reply_text.call_args[0][0]
    assert "Usage" in call_text


# --- /unbind handler ---


@pytest.mark.asyncio
async def test_unbind_handler_orchestrator_success(temp_abyss_home, dev_team_group):
    """/unbind by orchestrator unbinds the group."""
    handlers = _make_bot_handlers(temp_abyss_home, "dev_lead")
    unbind_handler = handlers[UNBIND_HANDLER_INDEX]

    update = _mock_update_for_group(chat_id=-12345, text="/unbind")
    mock_context = MagicMock()
    mock_context.args = []

    await unbind_handler.callback(update, mock_context)

    call_text = update.message.reply_text.call_args[0][0]
    assert "unbound" in call_text
    assert "dev_team" in call_text

    config = load_group_config("dev_team")
    assert config is not None
    assert config["telegram_chat_id"] is None


@pytest.mark.asyncio
async def test_unbind_handler_member_ignores(temp_abyss_home, dev_team_group):
    """/unbind by member bot is silently ignored."""
    handlers = _make_bot_handlers(temp_abyss_home, "coder")
    unbind_handler = handlers[UNBIND_HANDLER_INDEX]

    update = _mock_update_for_group(chat_id=-12345, text="/unbind")
    mock_context = MagicMock()
    mock_context.args = []

    await unbind_handler.callback(update, mock_context)

    update.message.reply_text.assert_not_called()

    # Group should still be bound
    config = load_group_config("dev_team")
    assert config is not None
    assert config["telegram_chat_id"] == -12345


@pytest.mark.asyncio
async def test_unbind_handler_no_binding(temp_abyss_home):
    """/unbind when no group is bound shows error."""
    handlers = _make_bot_handlers(temp_abyss_home, "dev_lead")
    unbind_handler = handlers[UNBIND_HANDLER_INDEX]

    update = _mock_update_for_group(chat_id=-99999, text="/unbind")
    mock_context = MagicMock()
    mock_context.args = []

    await unbind_handler.callback(update, mock_context)

    call_text = update.message.reply_text.call_args[0][0]
    assert "No group" in call_text


# --- Group message branching ---


@pytest.mark.asyncio
async def test_group_message_user_to_orchestrator(temp_abyss_home, dev_team_group):
    """User message in bound group is processed by orchestrator."""
    handlers = _make_bot_handlers(temp_abyss_home, "dev_lead")
    msg_handler = handlers[MESSAGE_HANDLER_INDEX]

    update = _mock_update_for_group(
        chat_id=-12345, text="Build a crawler", is_bot=False, username="boss"
    )

    with patch("abyss.claude_runner.run_claude_with_sdk", new_callable=AsyncMock) as mock_claude:
        mock_claude.return_value = "Mission accepted."
        mock_context = MagicMock()
        await msg_handler.callback(update, mock_context)

    # Orchestrator should have called Claude
    mock_claude.assert_called_once()


@pytest.mark.asyncio
async def test_group_message_user_to_member_ignored(temp_abyss_home, dev_team_group):
    """User message in bound group is NOT processed by member bot (no @mention)."""
    handlers = _make_bot_handlers(temp_abyss_home, "coder")
    msg_handler = handlers[MESSAGE_HANDLER_INDEX]

    update = _mock_update_for_group(
        chat_id=-12345, text="Build a crawler", is_bot=False, username="boss"
    )

    with patch("abyss.claude_runner.run_claude_with_sdk", new_callable=AsyncMock) as mock_claude:
        mock_context = MagicMock()
        await msg_handler.callback(update, mock_context)

    # Member should NOT call Claude
    mock_claude.assert_not_called()


@pytest.mark.asyncio
async def test_group_message_orchestrator_mentions_member(temp_abyss_home, dev_team_group):
    """Bot @mention of member triggers member's Claude processing."""
    handlers = _make_bot_handlers(temp_abyss_home, "coder")
    msg_handler = handlers[MESSAGE_HANDLER_INDEX]

    # Orchestrator bot sends @coder_bot mention
    update = _mock_update_for_group(
        chat_id=-12345,
        text="@coder_bot Write a scraper.",
        is_bot=True,
        username="dev_lead_bot",
        user_id=10001,
    )

    with patch("abyss.claude_runner.run_claude_with_sdk", new_callable=AsyncMock) as mock_claude:
        mock_claude.return_value = "Scraper done."
        mock_context = MagicMock()
        await msg_handler.callback(update, mock_context)

    # Member should have called Claude
    mock_claude.assert_called_once()


@pytest.mark.asyncio
async def test_group_message_user_mentions_member_ignored(temp_abyss_home, dev_team_group):
    """User directly @mentioning a member is ignored by member (orchestrator bypass)."""
    handlers = _make_bot_handlers(temp_abyss_home, "coder")
    msg_handler = handlers[MESSAGE_HANDLER_INDEX]

    # Human user mentions @coder_bot directly
    update = _mock_update_for_group(
        chat_id=-12345,
        text="@coder_bot Fix this bug",
        is_bot=False,
        username="boss",
    )

    with patch("abyss.claude_runner.run_claude_with_sdk", new_callable=AsyncMock) as mock_claude:
        mock_context = MagicMock()
        await msg_handler.callback(update, mock_context)

    # Member should NOT call Claude — only bot @mentions trigger member
    mock_claude.assert_not_called()


@pytest.mark.asyncio
async def test_group_message_member_no_mention_ignored(temp_abyss_home, dev_team_group):
    """Member ignores messages without @mention even from orchestrator bot."""
    handlers = _make_bot_handlers(temp_abyss_home, "coder")
    msg_handler = handlers[MESSAGE_HANDLER_INDEX]

    # Orchestrator bot sends message without @coder_bot
    update = _mock_update_for_group(
        chat_id=-12345,
        text="@tester_bot Write tests.",
        is_bot=True,
        username="dev_lead_bot",
        user_id=10001,
    )

    with patch("abyss.claude_runner.run_claude_with_sdk", new_callable=AsyncMock) as mock_claude:
        mock_context = MagicMock()
        await msg_handler.callback(update, mock_context)

    # Coder should NOT respond — it wasn't @mentioned
    mock_claude.assert_not_called()


@pytest.mark.asyncio
async def test_group_message_bot_report_to_orchestrator(temp_abyss_home, dev_team_group):
    """Member bot report is processed by orchestrator."""
    handlers = _make_bot_handlers(temp_abyss_home, "dev_lead")
    msg_handler = handlers[MESSAGE_HANDLER_INDEX]

    # Coder bot sends a report
    update = _mock_update_for_group(
        chat_id=-12345,
        text="@dev_lead_bot Scraper done. workspace/scraper.py",
        is_bot=True,
        username="coder_bot",
        user_id=10002,
    )

    with patch("abyss.claude_runner.run_claude_with_sdk", new_callable=AsyncMock) as mock_claude:
        mock_claude.return_value = "Good work."
        mock_context = MagicMock()
        await msg_handler.callback(update, mock_context)

    # Orchestrator should process member bot's report
    mock_claude.assert_called_once()


@pytest.mark.asyncio
async def test_group_message_unbound_chat_uses_individual(temp_abyss_home):
    """Unbound chat_id falls through to individual (DM) handling."""
    create_group(name="dev_team", orchestrator="dev_lead", members=["coder"])
    # NOT bound — no bind_group call

    handlers = _make_bot_handlers(temp_abyss_home, "dev_lead")
    msg_handler = handlers[MESSAGE_HANDLER_INDEX]

    update = _mock_update_for_group(
        chat_id=-99999, text="Hello from DM", is_bot=False, username="boss"
    )

    with patch("abyss.claude_runner.run_claude_with_sdk", new_callable=AsyncMock) as mock_claude:
        mock_claude.return_value = "Hi from DM."
        mock_context = MagicMock()
        await msg_handler.callback(update, mock_context)

    # Individual mode — should process
    mock_claude.assert_called_once()


@pytest.mark.asyncio
async def test_group_message_dm_not_affected(temp_abyss_home, dev_team_group):
    """DM (positive chat_id) is not affected by group bindings."""
    handlers = _make_bot_handlers(temp_abyss_home, "coder")
    msg_handler = handlers[MESSAGE_HANDLER_INDEX]

    # DM has positive chat_id
    update = _mock_update_for_group(
        chat_id=222, text="Help me with something", is_bot=False, username="boss"
    )

    with patch("abyss.claude_runner.run_claude_with_sdk", new_callable=AsyncMock) as mock_claude:
        mock_claude.return_value = "Sure, I can help."
        mock_context = MagicMock()
        await msg_handler.callback(update, mock_context)

    # DM — should process normally
    mock_claude.assert_called_once()


# --- Shared conversation log in group ---


@pytest.mark.asyncio
async def test_group_message_logged_to_shared_conversation(temp_abyss_home, dev_team_group):
    """All group messages are logged to shared conversation."""
    from abyss.group import load_shared_conversation

    handlers = _make_bot_handlers(temp_abyss_home, "dev_lead")
    msg_handler = handlers[MESSAGE_HANDLER_INDEX]

    update = _mock_update_for_group(
        chat_id=-12345, text="Build a crawler", is_bot=False, username="boss"
    )

    with patch("abyss.claude_runner.run_claude_with_sdk", new_callable=AsyncMock) as mock_claude:
        mock_claude.return_value = "Mission accepted."
        mock_context = MagicMock()
        await msg_handler.callback(update, mock_context)

    conversation = load_shared_conversation("dev_team")
    assert "user: Build a crawler" in conversation


@pytest.mark.asyncio
async def test_group_message_bot_message_logged(temp_abyss_home, dev_team_group):
    """Bot messages in group are logged with @username prefix."""
    from abyss.group import load_shared_conversation

    handlers = _make_bot_handlers(temp_abyss_home, "dev_lead")
    msg_handler = handlers[MESSAGE_HANDLER_INDEX]

    # Bot message from coder_bot
    update = _mock_update_for_group(
        chat_id=-12345,
        text="@dev_lead_bot Done.",
        is_bot=True,
        username="coder_bot",
        user_id=10002,
    )

    with patch("abyss.claude_runner.run_claude_with_sdk", new_callable=AsyncMock) as mock_claude:
        mock_claude.return_value = "Good."
        mock_context = MagicMock()
        await msg_handler.callback(update, mock_context)

    conversation = load_shared_conversation("dev_team")
    assert "@coder_bot: @dev_lead_bot Done." in conversation


@pytest.mark.asyncio
async def test_group_message_ignored_still_logged(temp_abyss_home, dev_team_group):
    """Messages that a member ignores are still logged to shared conversation."""
    from abyss.group import load_shared_conversation

    handlers = _make_bot_handlers(temp_abyss_home, "coder")
    msg_handler = handlers[MESSAGE_HANDLER_INDEX]

    # User message — member ignores but should still log
    update = _mock_update_for_group(
        chat_id=-12345, text="General instruction", is_bot=False, username="boss"
    )

    with patch("abyss.claude_runner.run_claude_with_sdk", new_callable=AsyncMock) as mock_claude:
        mock_context = MagicMock()
        await msg_handler.callback(update, mock_context)

    # Not processed by member
    mock_claude.assert_not_called()

    # But still logged
    conversation = load_shared_conversation("dev_team")
    assert "user: General instruction" in conversation


# --- Member response logging ---


@pytest.mark.asyncio
async def test_group_message_member_response_logged(temp_abyss_home, dev_team_group):
    """Member bot response in group is logged with @username prefix."""
    from abyss.group import load_shared_conversation

    handlers = _make_bot_handlers(temp_abyss_home, "coder")
    msg_handler = handlers[MESSAGE_HANDLER_INDEX]

    # Orchestrator bot sends @coder_bot mention
    update = _mock_update_for_group(
        chat_id=-12345,
        text="@coder_bot Write a scraper.",
        is_bot=True,
        username="dev_lead_bot",
        user_id=10001,
    )

    with patch("abyss.claude_runner.run_claude_with_sdk", new_callable=AsyncMock) as mock_claude:
        mock_claude.return_value = "Scraper done."
        mock_context = MagicMock()
        await msg_handler.callback(update, mock_context)

    conversation = load_shared_conversation("dev_team")
    assert "@dev_lead_bot: @coder_bot Write a scraper." in conversation


# --- Claude response logging ---


@pytest.mark.asyncio
async def test_group_claude_response_logged_to_shared_conversation(temp_abyss_home, dev_team_group):
    """Claude response is logged to shared conversation with @bot_name prefix."""
    from abyss.group import load_shared_conversation

    handlers = _make_bot_handlers(temp_abyss_home, "dev_lead")
    msg_handler = handlers[MESSAGE_HANDLER_INDEX]

    update = _mock_update_for_group(
        chat_id=-12345, text="Implement group_status", is_bot=False, username="boss"
    )

    with patch("abyss.claude_runner.run_claude_with_sdk", new_callable=AsyncMock) as mock_claude:
        mock_claude.return_value = "group_status command implemented successfully."
        mock_context = MagicMock()
        await msg_handler.callback(update, mock_context)

    conversation = load_shared_conversation("dev_team")
    assert "user: Implement group_status" in conversation
    assert "@dev_lead: group_status command implemented successfully." in conversation


@pytest.mark.asyncio
async def test_group_claude_response_logged_for_member(temp_abyss_home, dev_team_group):
    """Member bot's Claude response is also logged to shared conversation."""
    from abyss.group import load_shared_conversation

    handlers = _make_bot_handlers(temp_abyss_home, "coder")
    msg_handler = handlers[MESSAGE_HANDLER_INDEX]

    # Orchestrator mentions coder
    update = _mock_update_for_group(
        chat_id=-12345,
        text="@coder_bot Build a scraper.",
        is_bot=True,
        username="dev_lead_bot",
        user_id=10001,
    )

    with patch("abyss.claude_runner.run_claude_with_sdk", new_callable=AsyncMock) as mock_claude:
        mock_claude.return_value = "Scraper implementation complete."
        mock_context = MagicMock()
        await msg_handler.callback(update, mock_context)

    conversation = load_shared_conversation("dev_team")
    assert "@coder: Scraper implementation complete." in conversation


# --- Bot authorization bypass in groups ---


@pytest.mark.asyncio
async def test_group_bot_message_bypasses_allowed_users(temp_abyss_home, dev_team_group):
    """Bot messages in group bypass allowed_users check."""
    bot_directory = temp_abyss_home / "bots" / "coder"
    with open(bot_directory / "bot.yaml") as file:
        bot_config = yaml.safe_load(file)
    # Set allowed_users to only allow a specific human user
    bot_config["allowed_users"] = [11111]
    bot_config.setdefault("claude_args", [])
    bot_config.setdefault("command_timeout", 30)
    bot_config["streaming"] = False
    handlers = make_handlers("coder", bot_directory, bot_config)
    msg_handler = handlers[MESSAGE_HANDLER_INDEX]

    # Orchestrator bot sends @coder_bot mention (bot user_id NOT in allowed_users)
    update = _mock_update_for_group(
        chat_id=-12345,
        text="@coder_bot Write tests.",
        is_bot=True,
        username="dev_lead_bot",
        user_id=10001,
    )

    with patch("abyss.claude_runner.run_claude_with_sdk", new_callable=AsyncMock) as mock_claude:
        mock_claude.return_value = "Tests written."
        mock_context = MagicMock()
        await msg_handler.callback(update, mock_context)

    # Bot message should be processed despite allowed_users restriction
    mock_claude.assert_called_once()


@pytest.mark.asyncio
async def test_group_unauthorized_human_still_blocked(temp_abyss_home, dev_team_group):
    """Human users not in allowed_users are still blocked in group mode."""
    bot_directory = temp_abyss_home / "bots" / "dev_lead"
    with open(bot_directory / "bot.yaml") as file:
        bot_config = yaml.safe_load(file)
    bot_config["allowed_users"] = [11111]
    bot_config.setdefault("claude_args", [])
    bot_config.setdefault("command_timeout", 30)
    bot_config["streaming"] = False
    handlers = make_handlers("dev_lead", bot_directory, bot_config)
    msg_handler = handlers[MESSAGE_HANDLER_INDEX]

    # Human user (not in allowed_users) sends message in group
    update = _mock_update_for_group(
        chat_id=-12345,
        text="Do something",
        is_bot=False,
        username="stranger",
        user_id=99999,
    )

    with patch("abyss.claude_runner.run_claude_with_sdk", new_callable=AsyncMock) as mock_claude:
        mock_context = MagicMock()
        await msg_handler.callback(update, mock_context)

    # Unauthorized human should be blocked
    mock_claude.assert_not_called()
    update.effective_message.reply_text.assert_called_with("Unauthorized.")


# --- Infinite loop prevention ---


@pytest.mark.asyncio
async def test_group_message_self_message_ignored(temp_abyss_home, dev_team_group):
    """Bot ignores its own messages (bot.id == from_user.id)."""
    handlers = _make_bot_handlers(temp_abyss_home, "dev_lead")
    msg_handler = handlers[MESSAGE_HANDLER_INDEX]

    # Simulate the bot's own message (user_id matches bot.id)
    update = _mock_update_for_group(
        chat_id=-12345,
        text="Mission accepted.",
        is_bot=True,
        username="dev_lead_bot",
        user_id=10001,
    )
    # Make effective_user.id match message.from_user.id (self message check is in authorization)
    # The actual self-message check is that the bot won't trigger itself via _should_handle
    # Orchestrator only handles user messages or member bot messages, not its own.
    # dev_lead_bot is the orchestrator, not a member, so its own message is not a member message.

    with patch("abyss.claude_runner.run_claude_with_sdk", new_callable=AsyncMock) as mock_claude:
        mock_context = MagicMock()
        await msg_handler.callback(update, mock_context)

    # Orchestrator should NOT process its own bot message (it's not a member)
    mock_claude.assert_not_called()


@pytest.mark.asyncio
async def test_group_message_member_to_member_no_reaction(temp_abyss_home, dev_team_group):
    """Member bot does not react to another member bot's message (no @mention)."""
    handlers = _make_bot_handlers(temp_abyss_home, "tester")
    msg_handler = handlers[MESSAGE_HANDLER_INDEX]

    # Coder bot sends a message without @mentioning tester
    update = _mock_update_for_group(
        chat_id=-12345,
        text="@dev_lead_bot Scraper done.",
        is_bot=True,
        username="coder_bot",
        user_id=10002,
    )

    with patch("abyss.claude_runner.run_claude_with_sdk", new_callable=AsyncMock) as mock_claude:
        mock_context = MagicMock()
        await msg_handler.callback(update, mock_context)

    # Tester should NOT react — no @tester_bot mention
    mock_claude.assert_not_called()


@pytest.mark.asyncio
async def test_group_message_orchestrator_self_response_no_retrigger(
    temp_abyss_home, dev_team_group
):
    """Orchestrator's own response does not re-trigger orchestrator processing."""
    handlers = _make_bot_handlers(temp_abyss_home, "dev_lead")
    msg_handler = handlers[MESSAGE_HANDLER_INDEX]

    # Orchestrator bot's own message appears in group
    update = _mock_update_for_group(
        chat_id=-12345,
        text="@coder_bot Please write the crawler.",
        is_bot=True,
        username="dev_lead_bot",
        user_id=10001,
    )

    with patch("abyss.claude_runner.run_claude_with_sdk", new_callable=AsyncMock) as mock_claude:
        mock_context = MagicMock()
        await msg_handler.callback(update, mock_context)

    # Orchestrator should NOT process its own message
    # dev_lead_bot is orchestrator, not a member, so sender is not a member bot
    mock_claude.assert_not_called()


# --- Non-group bot in group ---


@pytest.mark.asyncio
async def test_group_message_unrelated_bot_ignored(temp_abyss_home, dev_team_group):
    """A bot not in the group ignores group messages."""
    # tester is in the group, but let's test with a bot_name that isn't
    # We'll create a handler with bot_name "unknown_bot"
    bot_directory = temp_abyss_home / "bots" / "dev_lead"
    bot_config = {
        "telegram_token": "fake-token",
        "telegram_username": "@unknown_bot",
        "personality": "Unknown",
        "role": "Unknown",
        "goal": "Unknown",
        "allowed_users": [],
        "claude_args": [],
        "command_timeout": 30,
    }
    handlers = make_handlers("unknown_bot", bot_directory, bot_config)
    msg_handler = handlers[MESSAGE_HANDLER_INDEX]

    update = _mock_update_for_group(
        chat_id=-12345, text="Hello everyone", is_bot=False, username="boss"
    )

    with patch("abyss.claude_runner.run_claude_with_sdk", new_callable=AsyncMock) as mock_claude:
        mock_context = MagicMock()
        await msg_handler.callback(update, mock_context)

    # Bot not in group — should still log but NOT process
    mock_claude.assert_not_called()


# --- Orchestrator ignores non-member bot messages ---


@pytest.mark.asyncio
async def test_group_message_non_member_bot_ignored_by_orchestrator(
    temp_abyss_home, dev_team_group
):
    """Orchestrator ignores bot messages from non-member bots."""
    handlers = _make_bot_handlers(temp_abyss_home, "dev_lead")
    msg_handler = handlers[MESSAGE_HANDLER_INDEX]

    # A bot that is NOT a member of the group sends a message
    update = _mock_update_for_group(
        chat_id=-12345,
        text="I'm a random bot",
        is_bot=True,
        username="random_bot",
        user_id=99999,
    )

    with patch("abyss.claude_runner.run_claude_with_sdk", new_callable=AsyncMock) as mock_claude:
        mock_context = MagicMock()
        await msg_handler.callback(update, mock_context)

    # Orchestrator should ignore non-member bot messages
    mock_claude.assert_not_called()
