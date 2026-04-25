"""Tests for abyss.handlers module."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from abyss.handlers import _is_user_allowed, make_handlers
from abyss.utils import split_message

MOCK_CANCEL = "abyss.handlers.cancel_process"
MOCK_IS_RUNNING = "abyss.handlers.is_process_running"


@pytest.fixture
def bot_path(tmp_path):
    """Create a bot directory."""
    bot_directory = tmp_path / "bots" / "test-bot"
    bot_directory.mkdir(parents=True)
    (bot_directory / "CLAUDE.md").write_text("# test-bot")
    (bot_directory / "sessions").mkdir()
    return bot_directory


@pytest.fixture
def bot_config():
    """Return a test bot config."""
    return {
        "telegram_token": "fake-token",
        "telegram_username": "@test_bot",
        "telegram_botname": "Test Bot",
        "personality": "Helpful assistant",
        "description": "General help",
        "allowed_users": [],
        "claude_args": [],
        "command_timeout": 30,
    }


def test_make_handlers_returns_handlers(bot_path, bot_config):
    """make_handlers returns a list of handlers."""
    handlers = make_handlers("test-bot", bot_path, bot_config)
    assert len(handlers) == 20


def test_is_user_allowed_empty_list():
    """Empty allowed_users means all users allowed."""
    assert _is_user_allowed(12345, [])


def test_is_user_allowed_in_list():
    """User in allowed list is allowed."""
    assert _is_user_allowed(12345, [12345, 67890])


def test_is_user_allowed_not_in_list():
    """User not in allowed list is denied."""
    assert not _is_user_allowed(12345, [67890])


def test_split_message_short():
    """Short messages are not split."""
    chunks = split_message("Hello world")
    assert len(chunks) == 1
    assert chunks[0] == "Hello world"


def test_split_message_long():
    """Long messages are split at newlines."""
    text = "\n".join(f"Line {i}" for i in range(1000))
    chunks = split_message(text, limit=100)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 100


def test_split_message_no_newlines():
    """Messages without newlines are split at limit."""
    text = "x" * 200
    chunks = split_message(text, limit=100)
    assert len(chunks) == 2
    assert chunks[0] == "x" * 100
    assert chunks[1] == "x" * 100


def test_split_message_exact_limit():
    """Message exactly at limit is not split."""
    text = "x" * 4096
    chunks = split_message(text)
    assert len(chunks) == 1


@pytest.fixture
def mock_update():
    """Create a mock Telegram Update."""
    update = MagicMock()
    update.effective_user.id = 12345
    update.effective_chat.id = 67890
    update.message.text = "Hello Claude"
    update.message.reply_text = AsyncMock()
    update.message.chat.send_action = AsyncMock()
    update.effective_message = update.message
    return update


@pytest.mark.asyncio
async def test_start_handler(bot_path, bot_config, mock_update):
    """Start handler sends bot introduction."""
    handlers = make_handlers("test-bot", bot_path, bot_config)
    start_handler = handlers[0]

    await start_handler.callback(mock_update, MagicMock())

    mock_update.message.reply_text.assert_called_once()
    call_text = mock_update.message.reply_text.call_args[0][0]
    assert "test-bot" in call_text


@pytest.mark.asyncio
async def test_help_handler(bot_path, bot_config, mock_update):
    """Help handler sends command list."""
    handlers = make_handlers("test-bot", bot_path, bot_config)
    help_handler = handlers[1]

    await help_handler.callback(mock_update, MagicMock())

    call_text = mock_update.message.reply_text.call_args[0][0]
    assert "/start" in call_text
    assert "/reset" in call_text


@pytest.mark.asyncio
async def test_reset_handler(bot_path, bot_config, mock_update):
    """Reset handler calls reset_session."""
    handlers = make_handlers("test-bot", bot_path, bot_config)
    reset_handler = handlers[2]

    with patch("abyss.handlers.reset_session") as mock_reset:
        await reset_handler.callback(mock_update, MagicMock())
        mock_reset.assert_called_once_with(bot_path, 67890)


@pytest.mark.asyncio
async def test_message_handler_calls_claude(bot_path, bot_config, mock_update):
    """Message handler forwards to Claude and replies."""
    bot_config["streaming"] = False
    handlers = make_handlers("test-bot", bot_path, bot_config)
    message_handler = handlers[19]

    with patch("abyss.claude_runner.run_claude_with_sdk", new_callable=AsyncMock) as mock_claude:
        mock_claude.return_value = "Claude response"
        mock_context = MagicMock()
        await message_handler.callback(mock_update, mock_context)

    mock_update.message.reply_text.assert_called()
    reply_text = mock_update.message.reply_text.call_args[0][0]
    assert "Claude response" in reply_text


@pytest.mark.asyncio
async def test_message_handler_unauthorized(bot_path, bot_config, mock_update):
    """Message handler rejects unauthorized users."""
    bot_config["allowed_users"] = [99999]
    handlers = make_handlers("test-bot", bot_path, bot_config)
    message_handler = handlers[6]

    await message_handler.callback(mock_update, MagicMock())

    mock_update.message.reply_text.assert_called_with("Unauthorized.")


@pytest.mark.asyncio
async def test_cancel_handler_no_process(bot_path, bot_config, mock_update):
    """Cancel handler replies when no process is running."""
    handlers = make_handlers("test-bot", bot_path, bot_config)
    cancel_handler = handlers[9]

    with patch(MOCK_IS_RUNNING, return_value=False):
        await cancel_handler.callback(mock_update, MagicMock())

    call_text = mock_update.message.reply_text.call_args[0][0]
    assert "No running process" in call_text


@pytest.mark.asyncio
async def test_cancel_handler_kills_process(bot_path, bot_config, mock_update):
    """Cancel handler kills running process."""
    handlers = make_handlers("test-bot", bot_path, bot_config)
    cancel_handler = handlers[9]

    with patch(MOCK_IS_RUNNING, return_value=True), patch(MOCK_CANCEL, return_value=True):
        await cancel_handler.callback(mock_update, MagicMock())

    call_text = mock_update.message.reply_text.call_args[0][0]
    assert "cancelled" in call_text.lower() or "\u26d4" in call_text


@pytest.mark.asyncio
async def test_send_handler_no_args(bot_path, bot_config, mock_update):
    """Send handler shows usage when no filename provided."""
    handlers = make_handlers("test-bot", bot_path, bot_config)
    send_handler = handlers[5]

    mock_context = MagicMock()
    mock_context.args = []
    await send_handler.callback(mock_update, mock_context)

    call_text = mock_update.message.reply_text.call_args[0][0]
    assert "Usage" in call_text or "No files" in call_text


@pytest.mark.asyncio
async def test_send_handler_file_not_found(bot_path, bot_config, mock_update):
    """Send handler replies when file not found."""
    handlers = make_handlers("test-bot", bot_path, bot_config)
    send_handler = handlers[5]

    mock_context = MagicMock()
    mock_context.args = ["nonexistent.txt"]
    await send_handler.callback(mock_update, mock_context)

    call_text = mock_update.message.reply_text.call_args[0][0]
    assert "not found" in call_text.lower()


@pytest.mark.asyncio
async def test_send_handler_sends_file(bot_path, bot_config, mock_update):
    """Send handler sends an existing workspace file."""
    handlers = make_handlers("test-bot", bot_path, bot_config)
    send_handler = handlers[5]

    # Create a session with a file in workspace
    session_dir = bot_path / "sessions" / "chat_67890"
    session_dir.mkdir(parents=True, exist_ok=True)
    workspace = session_dir / "workspace"
    workspace.mkdir(exist_ok=True)
    test_file = workspace / "test.txt"
    test_file.write_text("hello")

    mock_context = MagicMock()
    mock_context.args = ["test.txt"]
    mock_update.message.reply_document = AsyncMock()

    await send_handler.callback(mock_update, mock_context)

    mock_update.message.reply_document.assert_called_once()


@pytest.mark.asyncio
async def test_model_handler_show_current(bot_path, bot_config, mock_update):
    """Model handler shows current model when no args."""
    handlers = make_handlers("test-bot", bot_path, bot_config)
    model_handler = handlers[7]

    mock_context = MagicMock()
    mock_context.args = []
    await model_handler.callback(mock_update, mock_context)

    call_text = mock_update.message.reply_text.call_args[0][0]
    assert "sonnet" in call_text


@pytest.mark.asyncio
async def test_model_handler_change_model(bot_path, bot_config, mock_update):
    """Model handler changes model and saves to bot.yaml."""
    handlers = make_handlers("test-bot", bot_path, bot_config)
    model_handler = handlers[7]

    mock_context = MagicMock()
    mock_context.args = ["opus"]

    with patch("abyss.handlers.save_bot_config") as mock_save:
        await model_handler.callback(mock_update, mock_context)
        mock_save.assert_called_once()
        saved_config = mock_save.call_args[0][1]
        assert saved_config["model"] == "opus"

    call_text = mock_update.message.reply_text.call_args[0][0]
    assert "opus" in call_text


@pytest.mark.asyncio
async def test_model_handler_invalid_model(bot_path, bot_config, mock_update):
    """Model handler rejects invalid model names."""
    handlers = make_handlers("test-bot", bot_path, bot_config)
    model_handler = handlers[7]

    mock_context = MagicMock()
    mock_context.args = ["gpt4"]
    await model_handler.callback(mock_update, mock_context)

    call_text = mock_update.message.reply_text.call_args[0][0]
    assert "Invalid" in call_text


@pytest.mark.asyncio
async def test_message_handler_passes_model(bot_path, bot_config, mock_update):
    """Message handler passes model to run_claude."""
    bot_config["model"] = "opus"
    bot_config["streaming"] = False
    handlers = make_handlers("test-bot", bot_path, bot_config)
    message_handler = handlers[19]

    with patch("abyss.claude_runner.run_claude_with_sdk", new_callable=AsyncMock) as mock_claude:
        mock_claude.return_value = "response"
        mock_context = MagicMock()
        await message_handler.callback(mock_update, mock_context)

    call_kwargs = mock_claude.call_args[1]
    assert call_kwargs["model"] == "opus"


@pytest.mark.asyncio
async def test_files_handler_empty(bot_path, bot_config, mock_update):
    """Files handler shows empty message when no files."""
    handlers = make_handlers("test-bot", bot_path, bot_config)
    files_handler = handlers[4]

    await files_handler.callback(mock_update, MagicMock())

    call_text = mock_update.message.reply_text.call_args[0][0]
    assert "No files" in call_text


@pytest.mark.asyncio
async def test_skills_handler_empty(bot_path, bot_config, mock_update):
    """Skills handler shows empty message when no skills exist."""
    handlers = make_handlers("test-bot", bot_path, bot_config)
    skills_handler = handlers[12]

    mock_context = MagicMock()
    mock_context.args = []

    with (
        patch("abyss.skill.list_skills", return_value=[]),
        patch("abyss.builtin_skills.list_builtin_skills", return_value=[]),
    ):
        await skills_handler.callback(mock_update, mock_context)

    call_text = mock_update.message.reply_text.call_args[0][0]
    assert "No skills available" in call_text


@pytest.mark.asyncio
async def test_skills_handler_lists_all(bot_path, bot_config, mock_update):
    """Skills handler shows bot's own attached and available skills."""
    bot_config["skills"] = ["attached-skill"]
    handlers = make_handlers("test-bot", bot_path, bot_config)
    skills_handler = handlers[12]

    mock_skills = [
        {"name": "attached-skill", "type": "cli", "status": "active", "description": "A tool"},
        {"name": "unattached-skill", "type": None, "status": "active", "description": "Markdown"},
    ]

    mock_context = MagicMock()
    mock_context.args = []

    with (
        patch("abyss.skill.list_skills", return_value=mock_skills),
        patch("abyss.builtin_skills.list_builtin_skills", return_value=[]),
    ):
        await skills_handler.callback(mock_update, mock_context)

    call_text = mock_update.message.reply_text.call_args[0][0]
    assert "Used Skills" in call_text
    assert "attached-skill" in call_text
    assert "\u2705" in call_text  # attached skill has checkmark
    assert "unattached-skill" in call_text
    assert "Available" in call_text


@pytest.mark.asyncio
async def test_skills_handler_list_attached_empty(bot_path, bot_config, mock_update):
    """Skills handler list subcommand shows empty when no skills attached."""
    handlers = make_handlers("test-bot", bot_path, bot_config)
    skills_handler = handlers[12]

    mock_context = MagicMock()
    mock_context.args = ["list"]
    await skills_handler.callback(mock_update, mock_context)

    call_text = mock_update.message.reply_text.call_args[0][0]
    assert "No skills attached" in call_text


@pytest.mark.asyncio
async def test_skills_handler_attach(bot_path, bot_config, mock_update):
    """Skills handler attach adds a skill."""
    handlers = make_handlers("test-bot", bot_path, bot_config)
    skills_handler = handlers[12]

    mock_context = MagicMock()
    mock_context.args = ["attach", "test-skill"]

    with (
        patch("abyss.skill.is_skill", return_value=True),
        patch("abyss.skill.skill_status", return_value="active"),
        patch("abyss.skill.attach_skill_to_bot") as mock_attach,
    ):
        bot_config["skills"] = ["test-skill"]
        await skills_handler.callback(mock_update, mock_context)
        mock_attach.assert_called_once_with("test-bot", "test-skill")

    call_text = mock_update.message.reply_text.call_args[0][0]
    assert "attached" in call_text


@pytest.mark.asyncio
async def test_skills_handler_attach_not_found(bot_path, bot_config, mock_update):
    """Skills handler attach rejects nonexistent skill."""
    handlers = make_handlers("test-bot", bot_path, bot_config)
    skills_handler = handlers[12]

    mock_context = MagicMock()
    mock_context.args = ["attach", "nonexistent"]

    with patch("abyss.skill.is_skill", return_value=False):
        await skills_handler.callback(mock_update, mock_context)

    call_text = mock_update.message.reply_text.call_args[0][0]
    assert "not found" in call_text


@pytest.mark.asyncio
async def test_skills_handler_detach(bot_path, bot_config, mock_update):
    """Skills handler detach removes a skill."""
    bot_config["skills"] = ["test-skill"]
    handlers = make_handlers("test-bot", bot_path, bot_config)
    skills_handler = handlers[12]

    mock_context = MagicMock()
    mock_context.args = ["detach", "test-skill"]

    with patch("abyss.skill.detach_skill_from_bot") as mock_detach:
        bot_config["skills"] = []
        await skills_handler.callback(mock_update, mock_context)
        mock_detach.assert_called_once_with("test-bot", "test-skill")

    call_text = mock_update.message.reply_text.call_args[0][0]
    assert "detached" in call_text


@pytest.mark.asyncio
async def test_message_handler_passes_skill_names(bot_path, bot_config, mock_update):
    """Message handler passes skill_names to run_claude when skills are attached."""
    bot_config["skills"] = ["my-skill"]
    bot_config["streaming"] = False
    handlers = make_handlers("test-bot", bot_path, bot_config)
    message_handler = handlers[19]

    with patch("abyss.claude_runner.run_claude_with_sdk", new_callable=AsyncMock) as mock_claude:
        mock_claude.return_value = "response"
        mock_context = MagicMock()
        await message_handler.callback(mock_update, mock_context)

    call_kwargs = mock_claude.call_args[1]
    assert call_kwargs["skill_names"] == ["my-skill"]


@pytest.mark.asyncio
async def test_message_handler_no_skill_names(bot_path, bot_config, mock_update):
    """Message handler passes None for skill_names when no skills attached."""
    bot_config["streaming"] = False
    handlers = make_handlers("test-bot", bot_path, bot_config)
    message_handler = handlers[19]

    with patch("abyss.claude_runner.run_claude_with_sdk", new_callable=AsyncMock) as mock_claude:
        mock_claude.return_value = "response"
        mock_context = MagicMock()
        await message_handler.callback(mock_update, mock_context)

    call_kwargs = mock_claude.call_args[1]
    assert call_kwargs["skill_names"] is None


@pytest.mark.asyncio
async def test_heartbeat_handler_no_args(bot_path, bot_config, mock_update):
    """Heartbeat handler shows status when no args."""
    handlers = make_handlers("test-bot", bot_path, bot_config)
    heartbeat_handler = handlers[14]

    mock_context = MagicMock()
    mock_context.args = []

    with patch(
        "abyss.heartbeat.get_heartbeat_config",
        return_value={
            "enabled": False,
            "interval_minutes": 30,
            "active_hours": {"start": "07:00", "end": "23:00"},
        },
    ):
        await heartbeat_handler.callback(mock_update, mock_context)

    call_text = mock_update.message.reply_text.call_args[0][0]
    assert "Heartbeat" in call_text
    assert "off" in call_text


@pytest.mark.asyncio
async def test_heartbeat_handler_on(bot_path, bot_config, mock_update):
    """Heartbeat handler enables heartbeat."""
    handlers = make_handlers("test-bot", bot_path, bot_config)
    heartbeat_handler = handlers[14]

    mock_context = MagicMock()
    mock_context.args = ["on"]

    with patch("abyss.heartbeat.enable_heartbeat", return_value=True):
        await heartbeat_handler.callback(mock_update, mock_context)

    call_text = mock_update.message.reply_text.call_args[0][0]
    assert "enabled" in call_text


@pytest.mark.asyncio
async def test_heartbeat_handler_off(bot_path, bot_config, mock_update):
    """Heartbeat handler disables heartbeat."""
    handlers = make_handlers("test-bot", bot_path, bot_config)
    heartbeat_handler = handlers[14]

    mock_context = MagicMock()
    mock_context.args = ["off"]

    with patch("abyss.heartbeat.disable_heartbeat", return_value=True):
        await heartbeat_handler.callback(mock_update, mock_context)

    call_text = mock_update.message.reply_text.call_args[0][0]
    assert "disabled" in call_text


@pytest.mark.asyncio
async def test_streaming_handler_show_status(bot_path, bot_config, mock_update):
    """Streaming handler shows current status when no args."""
    handlers = make_handlers("test-bot", bot_path, bot_config)
    streaming_handler = handlers[10]

    mock_context = MagicMock()
    mock_context.args = []
    await streaming_handler.callback(mock_update, mock_context)

    call_text = mock_update.message.reply_text.call_args[0][0]
    assert "Streaming" in call_text
    assert "on" in call_text


@pytest.mark.asyncio
async def test_streaming_handler_on(bot_path, bot_config, mock_update):
    """Streaming handler enables streaming."""
    bot_config["streaming"] = False
    handlers = make_handlers("test-bot", bot_path, bot_config)
    streaming_handler = handlers[10]

    mock_context = MagicMock()
    mock_context.args = ["on"]

    with patch("abyss.handlers.save_bot_config") as mock_save:
        await streaming_handler.callback(mock_update, mock_context)
        mock_save.assert_called_once()
        saved_config = mock_save.call_args[0][1]
        assert saved_config["streaming"] is True

    call_text = mock_update.message.reply_text.call_args[0][0]
    assert "enabled" in call_text


@pytest.mark.asyncio
async def test_streaming_handler_off(bot_path, bot_config, mock_update):
    """Streaming handler disables streaming."""
    bot_config["streaming"] = True
    handlers = make_handlers("test-bot", bot_path, bot_config)
    streaming_handler = handlers[10]

    mock_context = MagicMock()
    mock_context.args = ["off"]

    with patch("abyss.handlers.save_bot_config") as mock_save:
        await streaming_handler.callback(mock_update, mock_context)
        mock_save.assert_called_once()
        saved_config = mock_save.call_args[0][1]
        assert saved_config["streaming"] is False

    call_text = mock_update.message.reply_text.call_args[0][0]
    assert "disabled" in call_text


@pytest.mark.asyncio
async def test_message_handler_non_streaming(bot_path, bot_config, mock_update):
    """Message handler uses run_claude (non-streaming) when streaming is off."""
    bot_config["streaming"] = False
    handlers = make_handlers("test-bot", bot_path, bot_config)
    message_handler = handlers[19]

    with patch("abyss.claude_runner.run_claude_with_sdk", new_callable=AsyncMock) as mock_claude:
        mock_claude.return_value = "Non-streaming response"
        mock_context = MagicMock()
        await message_handler.callback(mock_update, mock_context)

    mock_claude.assert_called_once()
    mock_update.message.reply_text.assert_called()
    reply_text = mock_update.message.reply_text.call_args[0][0]
    assert "Non-streaming response" in reply_text


@pytest.mark.asyncio
async def test_streaming_uses_send_message_draft(bot_path, bot_config, mock_update):
    """Streaming mode uses sendMessageDraft for real-time draft updates."""
    bot_config["streaming"] = True
    handlers = make_handlers("test-bot", bot_path, bot_config)
    message_handler = handlers[19]

    async def fake_streaming(**kwargs):
        on_text_chunk = kwargs.get("on_text_chunk")
        if on_text_chunk:
            # Send enough text to trigger draft (>= STREAM_MIN_CHARS_BEFORE_SEND)
            await on_text_chunk("Hello, this is a streaming response from Claude!")
        return "Hello, this is a streaming response from Claude!"

    with patch(
        "abyss.claude_runner.run_claude_streaming_with_sdk", new_callable=AsyncMock
    ) as mock_stream:
        mock_stream.side_effect = fake_streaming
        mock_context = MagicMock()
        mock_context.bot.send_message_draft = AsyncMock()
        await message_handler.callback(mock_update, mock_context)

    # sendMessageDraft should have been called during streaming
    assert mock_context.bot.send_message_draft.call_count >= 2  # streaming + clear
    # First call is the streaming draft with cursor marker
    first_call_kwargs = mock_context.bot.send_message_draft.call_args_list[0][1]
    assert first_call_kwargs["chat_id"] == 67890
    assert first_call_kwargs["draft_id"] == 1
    assert "\u258c" in first_call_kwargs["text"]  # cursor marker


@pytest.mark.asyncio
async def test_streaming_draft_clears_before_final(bot_path, bot_config, mock_update):
    """Draft is cleared with empty text before sending final message."""
    bot_config["streaming"] = True
    handlers = make_handlers("test-bot", bot_path, bot_config)
    message_handler = handlers[19]

    async def fake_streaming(**kwargs):
        on_text_chunk = kwargs.get("on_text_chunk")
        if on_text_chunk:
            await on_text_chunk("Draft streaming response text")
        return "Draft streaming response text"

    with patch(
        "abyss.claude_runner.run_claude_streaming_with_sdk", new_callable=AsyncMock
    ) as mock_stream:
        mock_stream.side_effect = fake_streaming
        mock_context = MagicMock()
        mock_context.bot.send_message_draft = AsyncMock()
        await message_handler.callback(mock_update, mock_context)

    # Last send_message_draft call should clear the draft (empty text)
    last_call = mock_context.bot.send_message_draft.call_args_list[-1]
    assert last_call[1]["text"] == ""

    # Final response should be sent via reply_text
    mock_update.message.reply_text.assert_called()


@pytest.mark.asyncio
async def test_streaming_fallback_to_edit_message(bot_path, bot_config, mock_update):
    """Falls back to editMessageText when sendMessageDraft fails."""
    bot_config["streaming"] = True
    handlers = make_handlers("test-bot", bot_path, bot_config)
    message_handler = handlers[19]

    async def fake_streaming(**kwargs):
        on_text_chunk = kwargs.get("on_text_chunk")
        if on_text_chunk:
            await on_text_chunk("Fallback streaming response text")
        return "Fallback streaming response text"

    with patch(
        "abyss.claude_runner.run_claude_streaming_with_sdk", new_callable=AsyncMock
    ) as mock_stream:
        mock_stream.side_effect = fake_streaming
        mock_context = MagicMock()
        # sendMessageDraft fails -> triggers fallback
        mock_context.bot.send_message_draft = AsyncMock(
            side_effect=Exception("TEXTDRAFT_PEER_INVALID")
        )
        mock_context.bot.edit_message_text = AsyncMock()
        sent_message = MagicMock()
        sent_message.message_id = 999
        mock_update.message.reply_text = AsyncMock(return_value=sent_message)
        await message_handler.callback(mock_update, mock_context)

    # sendMessageDraft was attempted but failed
    mock_context.bot.send_message_draft.assert_called()
    # Fallback: reply_text was used to create initial message
    mock_update.message.reply_text.assert_called()


@pytest.mark.asyncio
async def test_streaming_short_response_no_draft(bot_path, bot_config, mock_update):
    """Short responses below threshold don't trigger draft updates."""
    bot_config["streaming"] = True
    handlers = make_handlers("test-bot", bot_path, bot_config)
    message_handler = handlers[19]

    async def fake_streaming(**kwargs):
        on_text_chunk = kwargs.get("on_text_chunk")
        if on_text_chunk:
            await on_text_chunk("Hi")  # Too short for STREAM_MIN_CHARS_BEFORE_SEND
        return "Hi"

    with patch(
        "abyss.claude_runner.run_claude_streaming_with_sdk", new_callable=AsyncMock
    ) as mock_stream:
        mock_stream.side_effect = fake_streaming
        mock_context = MagicMock()
        mock_context.bot.send_message_draft = AsyncMock()
        await message_handler.callback(mock_update, mock_context)

    # sendMessageDraft should NOT be called for short responses
    mock_context.bot.send_message_draft.assert_not_called()
    # Final response should still be sent
    mock_update.message.reply_text.assert_called()


# --- Session continuity tests ---


@pytest.mark.asyncio
async def test_message_handler_first_message_bootstraps(bot_path, bot_config, mock_update):
    """First message creates session_id and uses --session-id (not --resume)."""
    bot_config["streaming"] = False
    handlers = make_handlers("test-bot", bot_path, bot_config)
    message_handler = handlers[19]

    with patch("abyss.claude_runner.run_claude_with_sdk", new_callable=AsyncMock) as mock_claude:
        mock_claude.return_value = "response"
        mock_context = MagicMock()
        mock_context.bot.edit_message_text = AsyncMock()
        mock_context.bot.delete_message = AsyncMock()
        await message_handler.callback(mock_update, mock_context)

    call_kwargs = mock_claude.call_args[1]
    # First message should NOT resume
    assert call_kwargs["resume_session"] is False
    # Should have a session ID
    assert call_kwargs["claude_session_id"] is not None
    assert len(call_kwargs["claude_session_id"]) > 0

    # Verify session ID was saved to disk
    from abyss.session import get_claude_session_id, session_directory

    session_dir = session_directory(bot_path, 67890)
    saved_id = get_claude_session_id(session_dir)
    assert saved_id == call_kwargs["claude_session_id"]


@pytest.mark.asyncio
async def test_message_handler_resume_session(bot_path, bot_config, mock_update):
    """Second message uses --resume with existing session_id."""
    from abyss.session import ensure_session, save_claude_session_id

    # Pre-create session with a saved session ID
    session_dir = ensure_session(bot_path, 67890)
    save_claude_session_id(session_dir, "existing-session-id")

    bot_config["streaming"] = False
    handlers = make_handlers("test-bot", bot_path, bot_config)
    message_handler = handlers[19]

    with patch("abyss.claude_runner.run_claude_with_sdk", new_callable=AsyncMock) as mock_claude:
        mock_claude.return_value = "response"
        mock_context = MagicMock()
        mock_context.bot.edit_message_text = AsyncMock()
        mock_context.bot.delete_message = AsyncMock()
        await message_handler.callback(mock_update, mock_context)

    call_kwargs = mock_claude.call_args[1]
    assert call_kwargs["resume_session"] is True
    assert call_kwargs["claude_session_id"] == "existing-session-id"


@pytest.mark.asyncio
async def test_message_handler_resume_fallback(bot_path, bot_config, mock_update):
    """When --resume fails with RuntimeError, falls back to bootstrap."""
    from abyss.session import ensure_session, get_claude_session_id, save_claude_session_id

    session_dir = ensure_session(bot_path, 67890)
    save_claude_session_id(session_dir, "expired-session-id")

    bot_config["streaming"] = False
    handlers = make_handlers("test-bot", bot_path, bot_config)
    message_handler = handlers[19]

    call_count = 0

    async def side_effect(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First call (resume) fails
            raise RuntimeError("Session not found")
        # Second call (bootstrap) succeeds
        return "fallback response"

    with patch("abyss.claude_runner.run_claude_with_sdk", new_callable=AsyncMock) as mock_claude:
        mock_claude.side_effect = side_effect
        mock_context = MagicMock()
        mock_context.bot.edit_message_text = AsyncMock()
        mock_context.bot.delete_message = AsyncMock()
        await message_handler.callback(mock_update, mock_context)

    # Should have been called twice: first resume, then bootstrap
    assert mock_claude.call_count == 2

    # First call should have been resume
    first_call_kwargs = mock_claude.call_args_list[0][1]
    assert first_call_kwargs["resume_session"] is True
    assert first_call_kwargs["claude_session_id"] == "expired-session-id"

    # Second call should NOT be resume
    second_call_kwargs = mock_claude.call_args_list[1][1]
    assert second_call_kwargs["resume_session"] is False
    assert second_call_kwargs["claude_session_id"] != "expired-session-id"

    # New session ID should be saved
    new_id = get_claude_session_id(session_dir)
    assert new_id is not None
    assert new_id != "expired-session-id"


@pytest.mark.asyncio
async def test_message_handler_first_message_with_history(bot_path, bot_config, mock_update):
    """First message with existing conversation.md bootstraps with history context."""
    from abyss.session import ensure_session, log_conversation

    session_dir = ensure_session(bot_path, 67890)
    log_conversation(session_dir, "user", "Previous question")
    log_conversation(session_dir, "assistant", "Previous answer")

    bot_config["streaming"] = False
    handlers = make_handlers("test-bot", bot_path, bot_config)
    message_handler = handlers[19]

    with patch("abyss.claude_runner.run_claude_with_sdk", new_callable=AsyncMock) as mock_claude:
        mock_claude.return_value = "response"
        mock_context = MagicMock()
        mock_context.bot.edit_message_text = AsyncMock()
        mock_context.bot.delete_message = AsyncMock()
        await message_handler.callback(mock_update, mock_context)

    call_kwargs = mock_claude.call_args[1]
    prompt = call_kwargs["message"]
    assert "이전 대화 기록" in prompt
    assert "Previous question" in prompt
    assert "Previous answer" in prompt
    assert "Hello Claude" in prompt


# --- Memory handler tests ---


@pytest.mark.asyncio
async def test_memory_handler_show_empty(bot_path, bot_config, mock_update):
    """Memory handler shows empty message when no memories saved."""
    handlers = make_handlers("test-bot", bot_path, bot_config)
    memory_handler = handlers[11]

    mock_context = MagicMock()
    mock_context.args = []
    await memory_handler.callback(mock_update, mock_context)

    call_text = mock_update.message.reply_text.call_args[0][0]
    assert "No memories" in call_text


@pytest.mark.asyncio
async def test_memory_handler_show_content(bot_path, bot_config, mock_update):
    """Memory handler displays MEMORY.md content."""
    from abyss.session import save_bot_memory

    save_bot_memory(bot_path, "# Memory\n\n- User likes Python")

    handlers = make_handlers("test-bot", bot_path, bot_config)
    memory_handler = handlers[11]

    mock_context = MagicMock()
    mock_context.args = []
    await memory_handler.callback(mock_update, mock_context)

    mock_update.message.reply_text.assert_called()
    call_text = mock_update.message.reply_text.call_args[0][0]
    assert "Python" in call_text


@pytest.mark.asyncio
async def test_memory_handler_clear(bot_path, bot_config, mock_update):
    """Memory handler clears memory on /memory clear."""
    from abyss.session import load_bot_memory, save_bot_memory

    save_bot_memory(bot_path, "some memory")

    handlers = make_handlers("test-bot", bot_path, bot_config)
    memory_handler = handlers[11]

    mock_context = MagicMock()
    mock_context.args = ["clear"]
    await memory_handler.callback(mock_update, mock_context)

    assert load_bot_memory(bot_path) is None
    call_text = mock_update.message.reply_text.call_args[0][0]
    assert "cleared" in call_text.lower()


@pytest.mark.asyncio
async def test_message_handler_bootstrap_includes_memory(bot_path, bot_config, mock_update):
    """First message bootstrap includes bot memory in the prompt."""
    from abyss.session import save_bot_memory

    save_bot_memory(bot_path, "# Memory\n\n- User prefers Korean")

    bot_config["streaming"] = False
    handlers = make_handlers("test-bot", bot_path, bot_config)
    message_handler = handlers[19]

    with patch("abyss.claude_runner.run_claude_with_sdk", new_callable=AsyncMock) as mock_claude:
        mock_claude.return_value = "response"
        mock_context = MagicMock()
        mock_context.bot.edit_message_text = AsyncMock()
        mock_context.bot.delete_message = AsyncMock()
        await message_handler.callback(mock_update, mock_context)

    call_kwargs = mock_claude.call_args[1]
    prompt = call_kwargs["message"]
    assert "장기 메모리" in prompt
    assert "User prefers Korean" in prompt
    assert "Hello Claude" in prompt


@pytest.mark.asyncio
async def test_message_handler_bootstrap_memory_and_history(bot_path, bot_config, mock_update):
    """First message bootstrap includes both memory and conversation history."""
    from abyss.session import ensure_session, log_conversation, save_bot_memory

    save_bot_memory(bot_path, "# Memory\n\n- Name is Kim")

    session_dir = ensure_session(bot_path, 67890)
    log_conversation(session_dir, "user", "Previous question")
    log_conversation(session_dir, "assistant", "Previous answer")

    bot_config["streaming"] = False
    handlers = make_handlers("test-bot", bot_path, bot_config)
    message_handler = handlers[19]

    with patch("abyss.claude_runner.run_claude_with_sdk", new_callable=AsyncMock) as mock_claude:
        mock_claude.return_value = "response"
        mock_context = MagicMock()
        mock_context.bot.edit_message_text = AsyncMock()
        mock_context.bot.delete_message = AsyncMock()
        await message_handler.callback(mock_update, mock_context)

    call_kwargs = mock_claude.call_args[1]
    prompt = call_kwargs["message"]
    # Memory should come before history
    assert "장기 메모리" in prompt
    assert "Name is Kim" in prompt
    assert "이전 대화 기록" in prompt
    assert "Previous question" in prompt
    assert "Hello Claude" in prompt
    # Memory section should appear before history section
    memory_position = prompt.index("장기 메모리")
    history_position = prompt.index("이전 대화 기록")
    assert memory_position < history_position


# --- Cron handler tests ---

CRON_HANDLER_INDEX = 13


@pytest.mark.asyncio
async def test_cron_handler_no_args(bot_path, bot_config, mock_update):
    """cron_handler shows help when no args."""
    handlers = make_handlers("test-bot", bot_path, bot_config)
    cron_handler = handlers[CRON_HANDLER_INDEX]

    mock_context = MagicMock()
    mock_context.args = []

    await cron_handler.callback(mock_update, mock_context)

    text = mock_update.message.reply_text.call_args[0][0]
    assert "/cron add" in text
    assert "/cron remove" in text


@pytest.mark.asyncio
async def test_cron_handler_add_no_description(bot_path, bot_config, mock_update):
    """cron add with no description shows usage."""
    handlers = make_handlers("test-bot", bot_path, bot_config)
    cron_handler = handlers[CRON_HANDLER_INDEX]

    mock_context = MagicMock()
    mock_context.args = ["add"]

    await cron_handler.callback(mock_update, mock_context)

    text = mock_update.message.reply_text.call_args_list[-1][0][0]
    assert "Usage" in text


@pytest.mark.asyncio
async def test_cron_handler_add_recurring(bot_path, bot_config, mock_update):
    """cron add creates a recurring job from natural language."""
    handlers = make_handlers("test-bot", bot_path, bot_config)
    cron_handler = handlers[CRON_HANDLER_INDEX]

    mock_context = MagicMock()
    mock_context.args = ["add", "매일", "아침", "9시에", "이메일", "요약"]

    with (
        patch(
            "abyss.cron.parse_natural_language_schedule",
            new_callable=AsyncMock,
            return_value={
                "type": "recurring",
                "schedule": "0 9 * * *",
                "message": "이메일 요약",
                "name": "email-summary",
            },
        ),
        patch("abyss.cron.resolve_default_timezone", return_value="Asia/Seoul"),
        patch("abyss.cron.add_cron_job"),
        patch(
            "abyss.cron.generate_unique_job_name",
            return_value="email-summary",
        ),
        patch("abyss.cron.next_run_time", return_value=None),
    ):
        await cron_handler.callback(mock_update, mock_context)

    last_text = mock_update.message.reply_text.call_args_list[-1][0][0]
    assert "email-summary" in last_text
    assert "0 9 * * *" in last_text


@pytest.mark.asyncio
async def test_cron_handler_add_parse_failure(bot_path, bot_config, mock_update):
    """cron add shows error when parsing fails."""
    handlers = make_handlers("test-bot", bot_path, bot_config)
    cron_handler = handlers[CRON_HANDLER_INDEX]

    mock_context = MagicMock()
    mock_context.args = ["add", "gibberish"]

    with (
        patch(
            "abyss.cron.parse_natural_language_schedule",
            new_callable=AsyncMock,
            side_effect=ValueError("Failed to parse"),
        ),
        patch("abyss.cron.resolve_default_timezone", return_value="UTC"),
    ):
        await cron_handler.callback(mock_update, mock_context)

    last_text = mock_update.message.reply_text.call_args_list[-1][0][0]
    assert "Failed to parse" in last_text


@pytest.mark.asyncio
async def test_cron_handler_remove_success(bot_path, bot_config, mock_update):
    """cron remove deletes a job."""
    handlers = make_handlers("test-bot", bot_path, bot_config)
    cron_handler = handlers[CRON_HANDLER_INDEX]

    mock_context = MagicMock()
    mock_context.args = ["remove", "my-job"]

    with patch("abyss.cron.remove_cron_job", return_value=True):
        await cron_handler.callback(mock_update, mock_context)

    text = mock_update.message.reply_text.call_args_list[-1][0][0]
    assert "my-job" in text
    assert "removed" in text


@pytest.mark.asyncio
async def test_cron_handler_remove_not_found(bot_path, bot_config, mock_update):
    """cron remove shows error when job not found."""
    handlers = make_handlers("test-bot", bot_path, bot_config)
    cron_handler = handlers[CRON_HANDLER_INDEX]

    mock_context = MagicMock()
    mock_context.args = ["remove", "nonexistent"]

    with patch("abyss.cron.remove_cron_job", return_value=False):
        await cron_handler.callback(mock_update, mock_context)

    text = mock_update.message.reply_text.call_args_list[-1][0][0]
    assert "not found" in text


@pytest.mark.asyncio
async def test_cron_handler_enable(bot_path, bot_config, mock_update):
    """cron enable enables a job."""
    handlers = make_handlers("test-bot", bot_path, bot_config)
    cron_handler = handlers[CRON_HANDLER_INDEX]

    mock_context = MagicMock()
    mock_context.args = ["enable", "my-job"]

    with patch("abyss.cron.enable_cron_job", return_value=True):
        await cron_handler.callback(mock_update, mock_context)

    text = mock_update.message.reply_text.call_args_list[-1][0][0]
    assert "my-job" in text
    assert "enabled" in text


@pytest.mark.asyncio
async def test_cron_handler_disable(bot_path, bot_config, mock_update):
    """cron disable disables a job."""
    handlers = make_handlers("test-bot", bot_path, bot_config)
    cron_handler = handlers[CRON_HANDLER_INDEX]

    mock_context = MagicMock()
    mock_context.args = ["disable", "my-job"]

    with patch("abyss.cron.disable_cron_job", return_value=True):
        await cron_handler.callback(mock_update, mock_context)

    text = mock_update.message.reply_text.call_args_list[-1][0][0]
    assert "my-job" in text
    assert "disabled" in text
