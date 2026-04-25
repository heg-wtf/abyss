"""Tests for abyss.session module."""

import pytest

from abyss.session import (
    clear_bot_memory,
    clear_claude_session_id,
    collect_session_chat_ids,
    conversation_status_summary,
    ensure_session,
    get_claude_session_id,
    list_workspace_files,
    load_bot_memory,
    load_conversation_history,
    log_conversation,
    memory_file_path,
    reset_all_session,
    reset_session,
    save_bot_memory,
    save_claude_session_id,
    session_directory,
)


@pytest.fixture
def bot_path(tmp_path):
    """Create a fake bot directory with CLAUDE.md."""
    bot_directory = tmp_path / "bots" / "test-bot"
    bot_directory.mkdir(parents=True)
    (bot_directory / "CLAUDE.md").write_text("# test-bot\n\nBot instructions.")
    (bot_directory / "sessions").mkdir()
    return bot_directory


def test_session_directory(bot_path):
    """session_directory returns expected path."""
    result = session_directory(bot_path, 12345)
    assert result == bot_path / "sessions" / "chat_12345"


def test_ensure_session_creates_directory(bot_path):
    """ensure_session creates session dir, workspace, and copies CLAUDE.md."""
    directory = ensure_session(bot_path, 12345)

    assert directory.exists()
    assert (directory / "workspace").exists()
    assert (directory / "CLAUDE.md").exists()
    assert (directory / "CLAUDE.md").read_text() == "# test-bot\n\nBot instructions."


def test_ensure_session_idempotent(bot_path):
    """ensure_session can be called multiple times without error."""
    directory1 = ensure_session(bot_path, 12345)
    (directory1 / "CLAUDE.md").write_text("modified content")

    directory2 = ensure_session(bot_path, 12345)
    assert directory1 == directory2
    assert (directory2 / "CLAUDE.md").read_text() == "modified content"


def test_reset_session(bot_path):
    """reset_session deletes all conversation files but keeps workspace."""
    directory = ensure_session(bot_path, 12345)

    log_conversation(directory, "user", "Hello")

    workspace_file = directory / "workspace" / "test.txt"
    workspace_file.write_text("workspace content")

    # Verify conversation file was created
    dated_files = list(directory.glob("conversation-*.md"))
    assert len(dated_files) == 1

    reset_session(bot_path, 12345)

    assert not list(directory.glob("conversation-*.md"))
    assert workspace_file.exists()
    assert (directory / "CLAUDE.md").exists()


def test_reset_session_no_conversation(bot_path):
    """reset_session doesn't error if conversation.md doesn't exist."""
    ensure_session(bot_path, 12345)
    reset_session(bot_path, 12345)


def test_reset_all_session(bot_path):
    """reset_all_session deletes the entire session directory."""
    directory = ensure_session(bot_path, 12345)
    (directory / "workspace" / "test.txt").write_text("data")
    log_conversation(directory, "user", "chat")

    reset_all_session(bot_path, 12345)

    assert not directory.exists()


def test_reset_all_session_nonexistent(bot_path):
    """reset_all_session doesn't error if session doesn't exist."""
    reset_all_session(bot_path, 99999)


def test_log_conversation(bot_path):
    """log_conversation appends entries to dated conversation file."""
    directory = ensure_session(bot_path, 12345)

    log_conversation(directory, "user", "Hello")
    log_conversation(directory, "assistant", "Hi there!")

    dated_files = list(directory.glob("conversation-*.md"))
    assert len(dated_files) == 1
    content = dated_files[0].read_text()
    assert "## user" in content
    assert "Hello" in content
    assert "## assistant" in content
    assert "Hi there!" in content


def test_list_workspace_files(bot_path):
    """list_workspace_files returns files in workspace."""
    directory = ensure_session(bot_path, 12345)
    workspace = directory / "workspace"

    (workspace / "file1.txt").write_text("content1")
    (workspace / "file2.py").write_text("content2")

    sub_directory = workspace / "subdir"
    sub_directory.mkdir()
    (sub_directory / "file3.md").write_text("content3")

    files = list_workspace_files(directory)
    assert len(files) == 3
    assert "file1.txt" in files
    assert "file2.py" in files
    assert "subdir/file3.md" in files


def test_list_workspace_files_empty(bot_path):
    """list_workspace_files returns empty list for empty workspace."""
    directory = ensure_session(bot_path, 12345)
    files = list_workspace_files(directory)
    assert files == []


def test_list_workspace_files_no_workspace(tmp_path):
    """list_workspace_files returns empty list if workspace doesn't exist."""
    files = list_workspace_files(tmp_path / "nonexistent")
    assert files == []


# --- Claude session ID tests ---


def test_get_claude_session_id_none(tmp_path):
    """get_claude_session_id returns None when file doesn't exist."""
    assert get_claude_session_id(tmp_path) is None


def test_save_and_get_claude_session_id(tmp_path):
    """save_claude_session_id and get_claude_session_id round-trip."""
    save_claude_session_id(tmp_path, "abc-123-def")
    assert get_claude_session_id(tmp_path) == "abc-123-def"


def test_clear_claude_session_id(tmp_path):
    """clear_claude_session_id removes the session ID file."""
    save_claude_session_id(tmp_path, "abc-123")
    clear_claude_session_id(tmp_path)
    assert get_claude_session_id(tmp_path) is None


def test_clear_claude_session_id_missing(tmp_path):
    """clear_claude_session_id doesn't error when file is missing."""
    clear_claude_session_id(tmp_path)  # should not raise


# --- Conversation history tests ---


def test_load_conversation_history_empty(tmp_path):
    """load_conversation_history returns None when conversation.md doesn't exist."""
    assert load_conversation_history(tmp_path) is None


def test_load_conversation_history_empty_file(bot_path):
    """load_conversation_history returns None when conversation file is empty."""
    directory = ensure_session(bot_path, 12345)
    from abyss.session import _conversation_file_for_today

    _conversation_file_for_today(directory).write_text("")
    assert load_conversation_history(directory) is None


def test_load_conversation_history_full(bot_path):
    """load_conversation_history returns all turns when under max_turns."""
    directory = ensure_session(bot_path, 12345)
    log_conversation(directory, "user", "Hello")
    log_conversation(directory, "assistant", "Hi there!")
    log_conversation(directory, "user", "How are you?")
    log_conversation(directory, "assistant", "I'm good!")

    history = load_conversation_history(directory)
    assert history is not None
    assert "Hello" in history
    assert "Hi there!" in history
    assert "How are you?" in history
    assert "I'm good!" in history


def test_load_conversation_history_truncates(bot_path):
    """load_conversation_history returns only last max_turns entries."""
    directory = ensure_session(bot_path, 12345)

    # Write 25 turns (more than default 20)
    for i in range(25):
        role = "user" if i % 2 == 0 else "assistant"
        log_conversation(directory, role, f"Message {i}")

    history = load_conversation_history(directory, max_turns=20)
    assert history is not None
    # First 5 messages should be truncated
    assert "Message 0" not in history
    assert "Message 4" not in history
    # Last 20 should be present
    assert "Message 5" in history
    assert "Message 24" in history


# --- Reset clears session ID tests ---


def test_reset_session_clears_session_id(bot_path):
    """reset_session also clears the stored Claude session ID."""
    directory = ensure_session(bot_path, 12345)
    save_claude_session_id(directory, "test-session-id")
    log_conversation(directory, "user", "some conversation")

    reset_session(bot_path, 12345)

    assert get_claude_session_id(directory) is None


def test_reset_all_session_clears_session_id(bot_path):
    """reset_all_session removes the entire directory including session ID."""
    directory = ensure_session(bot_path, 12345)
    save_claude_session_id(directory, "test-session-id")

    reset_all_session(bot_path, 12345)

    # Directory is gone, so session ID is gone too
    assert not directory.exists()
    assert get_claude_session_id(directory) is None


# --- Bot memory tests ---


def test_memory_file_path(bot_path):
    """memory_file_path returns expected path."""
    result = memory_file_path(bot_path)
    assert result == bot_path / "MEMORY.md"


def test_load_bot_memory_none(bot_path):
    """load_bot_memory returns None when MEMORY.md doesn't exist."""
    assert load_bot_memory(bot_path) is None


def test_load_bot_memory_empty(bot_path):
    """load_bot_memory returns None when MEMORY.md is empty."""
    (bot_path / "MEMORY.md").write_text("")
    assert load_bot_memory(bot_path) is None


def test_load_bot_memory_whitespace_only(bot_path):
    """load_bot_memory returns None when MEMORY.md is whitespace only."""
    (bot_path / "MEMORY.md").write_text("   \n\n  ")
    assert load_bot_memory(bot_path) is None


def test_save_and_load_bot_memory(bot_path):
    """save_bot_memory and load_bot_memory round-trip."""
    save_bot_memory(bot_path, "# Memory\n\n- User likes Python")
    content = load_bot_memory(bot_path)
    assert content == "# Memory\n\n- User likes Python"


def test_clear_bot_memory(bot_path):
    """clear_bot_memory removes the MEMORY.md file."""
    save_bot_memory(bot_path, "some memory")
    clear_bot_memory(bot_path)
    assert load_bot_memory(bot_path) is None
    assert not (bot_path / "MEMORY.md").exists()


def test_clear_bot_memory_missing(bot_path):
    """clear_bot_memory doesn't error when file is missing."""
    clear_bot_memory(bot_path)  # should not raise


# --- collect_session_chat_ids tests ---


def test_collect_session_chat_ids(bot_path):
    """collect_session_chat_ids returns chat IDs from session directories."""
    ensure_session(bot_path, 111)
    ensure_session(bot_path, 222)
    ensure_session(bot_path, 333)

    chat_ids = collect_session_chat_ids(bot_path)
    assert chat_ids == [111, 222, 333]


def test_collect_session_chat_ids_empty(bot_path):
    """collect_session_chat_ids returns empty list when no sessions exist."""
    chat_ids = collect_session_chat_ids(bot_path)
    assert chat_ids == []


def test_collect_session_chat_ids_no_sessions_directory(tmp_path):
    """collect_session_chat_ids returns empty list when sessions dir doesn't exist."""
    chat_ids = collect_session_chat_ids(tmp_path / "nonexistent")
    assert chat_ids == []


def test_collect_session_chat_ids_ignores_non_chat_directories(bot_path):
    """collect_session_chat_ids ignores directories that don't match chat_<id> pattern."""
    ensure_session(bot_path, 111)
    (bot_path / "sessions" / "not_a_chat").mkdir()
    (bot_path / "sessions" / "chat_abc").mkdir()  # non-numeric

    chat_ids = collect_session_chat_ids(bot_path)
    assert chat_ids == [111]


# --- Daily conversation rotation tests ---


def test_log_conversation_creates_dated_file(bot_path):
    """log_conversation creates a conversation-YYMMDD.md file."""
    directory = ensure_session(bot_path, 12345)
    log_conversation(directory, "user", "Hello")

    dated_files = list(directory.glob("conversation-*.md"))
    assert len(dated_files) == 1
    assert dated_files[0].name.startswith("conversation-")
    assert dated_files[0].name.endswith(".md")
    # No legacy conversation.md should be created
    assert not (directory / "conversation.md").exists()


def test_load_conversation_history_legacy_fallback(tmp_path):
    """load_conversation_history falls back to legacy conversation.md."""
    (tmp_path / "conversation.md").write_text(
        "\n## user (2026-02-25 10:00:00 UTC)\n\nHello\n"
        "\n## assistant (2026-02-25 10:00:01 UTC)\n\nHi!\n"
    )
    history = load_conversation_history(tmp_path)
    assert history is not None
    assert "Hello" in history
    assert "Hi!" in history


def test_load_conversation_history_spans_multiple_days(bot_path):
    """load_conversation_history reads across multiple dated files."""
    directory = ensure_session(bot_path, 12345)

    # Create an older dated file manually
    (directory / "conversation-260224.md").write_text(
        "\n## user (2026-02-24 23:00:00 UTC)\n\nYesterday message\n"
    )

    # Log to today's file
    log_conversation(directory, "user", "Today message")

    history = load_conversation_history(directory)
    assert "Yesterday message" in history
    assert "Today message" in history


def test_reset_session_deletes_all_dated_files(bot_path):
    """reset_session deletes all conversation-YYMMDD.md files and legacy."""
    directory = ensure_session(bot_path, 12345)

    (directory / "conversation-260224.md").write_text("day 1")
    (directory / "conversation-260225.md").write_text("day 2")
    (directory / "conversation.md").write_text("legacy")

    reset_session(bot_path, 12345)

    assert not list(directory.glob("conversation-*.md"))
    assert not (directory / "conversation.md").exists()


def test_conversation_status_summary_no_files(bot_path):
    """conversation_status_summary returns 'No conversation yet' when empty."""
    directory = ensure_session(bot_path, 12345)
    assert conversation_status_summary(directory) == "No conversation yet"


def test_conversation_status_summary_with_files(bot_path):
    """conversation_status_summary returns file count and total size."""
    directory = ensure_session(bot_path, 12345)
    log_conversation(directory, "user", "Hello")

    summary = conversation_status_summary(directory)
    assert "bytes" in summary
    assert "1 files" in summary


def test_conversation_status_summary_multiple_files(bot_path):
    """conversation_status_summary counts multiple dated files."""
    directory = ensure_session(bot_path, 12345)

    (directory / "conversation-260224.md").write_text("day 1")
    (directory / "conversation-260225.md").write_text("day 2")

    summary = conversation_status_summary(directory)
    assert "2 files" in summary


def test_load_conversation_history_truncates_across_files(bot_path):
    """load_conversation_history respects max_turns across multiple files."""
    directory = ensure_session(bot_path, 12345)

    # Write 15 turns to an older file
    older_entries = ""
    for i in range(15):
        role = "user" if i % 2 == 0 else "assistant"
        older_entries += f"\n## {role} (2026-02-24 {10 + i}:00:00 UTC)\n\nOld message {i}\n"
    (directory / "conversation-260224.md").write_text(older_entries)

    # Write 10 turns to today's file
    for i in range(10):
        role = "user" if i % 2 == 0 else "assistant"
        log_conversation(directory, role, f"New message {i}")

    history = load_conversation_history(directory, max_turns=20)
    assert history is not None
    # Should have last 20 turns: 5 old + 10 new (from total 25)
    assert "Old message 0" not in history
    assert "Old message 4" not in history
    assert "Old message 5" in history
    assert "New message 9" in history


# --- Global memory tests ---


@pytest.fixture
def abyss_home(tmp_path, monkeypatch):
    """Set ABYSS_HOME to a temporary directory."""
    home = tmp_path / ".abyss"
    home.mkdir()
    monkeypatch.setenv("ABYSS_HOME", str(home))
    return home


def test_global_memory_file_path(abyss_home):
    """global_memory_file_path returns expected path."""
    from abyss.session import global_memory_file_path

    result = global_memory_file_path()
    assert result == abyss_home / "GLOBAL_MEMORY.md"


def test_load_global_memory_none(abyss_home):
    """load_global_memory returns None when file doesn't exist."""
    from abyss.session import load_global_memory

    assert load_global_memory() is None


def test_load_global_memory_empty(abyss_home):
    """load_global_memory returns None when file is empty."""
    from abyss.session import load_global_memory

    (abyss_home / "GLOBAL_MEMORY.md").write_text("")
    assert load_global_memory() is None


def test_load_global_memory_whitespace_only(abyss_home):
    """load_global_memory returns None when file is whitespace only."""
    from abyss.session import load_global_memory

    (abyss_home / "GLOBAL_MEMORY.md").write_text("   \n\n  ")
    assert load_global_memory() is None


def test_save_and_load_global_memory(abyss_home):
    """save_global_memory and load_global_memory round-trip."""
    from abyss.session import load_global_memory, save_global_memory

    save_global_memory("# Global\n\n- Timezone: Asia/Seoul")
    content = load_global_memory()
    assert content == "# Global\n\n- Timezone: Asia/Seoul"


def test_clear_global_memory(abyss_home):
    """clear_global_memory removes the GLOBAL_MEMORY.md file."""
    from abyss.session import clear_global_memory, load_global_memory, save_global_memory

    save_global_memory("some global memory")
    clear_global_memory()
    assert load_global_memory() is None
    assert not (abyss_home / "GLOBAL_MEMORY.md").exists()


# ─── conversation_index integration ────────────────────────────────────────


def test_log_conversation_indexes_into_bot_db(bot_path):
    """log_conversation appends to the bot's FTS5 index in addition to markdown."""
    from abyss import conversation_index
    from abyss.session import ensure_session, log_conversation

    chat_id = 4242
    session_dir = ensure_session(bot_path, chat_id)
    log_conversation(session_dir, "user", "강남 카페에서 미팅")
    log_conversation(session_dir, "assistant", "어느 카페였나요?")

    db_path = bot_path / "conversation.db"
    assert db_path.exists(), "log_conversation should create the FTS5 DB"
    hits = conversation_index.search(db_path, query="강남")
    assert len(hits) == 1
    assert hits[0].chat_id == f"chat_{chat_id}"
    assert hits[0].role == "user"
    assert "강남" in hits[0].content


def test_log_conversation_failure_does_not_break_markdown(bot_path, monkeypatch):
    """If indexing fails, markdown still persists."""
    from abyss.session import ensure_session, log_conversation

    chat_id = 5151
    session_dir = ensure_session(bot_path, chat_id)

    def _broken_append(*args, **kwargs):
        raise RuntimeError("simulated index failure")

    monkeypatch.setattr("abyss.conversation_index.append", _broken_append)

    # Should not raise — log_conversation must swallow the index error.
    log_conversation(session_dir, "user", "should still be written to markdown")

    md_files = list(session_dir.glob("conversation-*.md"))
    assert len(md_files) == 1
    assert "should still be written" in md_files[0].read_text(encoding="utf-8")
