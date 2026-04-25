"""Tests for conversation_index.py — SQLite FTS5 cross-session search."""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from abyss import conversation_index as ci


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "conversation.db"


@pytest.fixture
def initialized_db(db_path: Path) -> Path:
    ci.ensure_schema(db_path)
    return db_path


def _utc(year: int, month: int, day: int, hour: int = 12, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


# ─── Phase 1.6 / case 13 ────────────────────────────────────────────────────


@pytest.mark.enable_conversation_search
def test_fts5_available_in_current_runtime() -> None:
    assert ci.is_fts5_available()


# ─── case 1: ensure_schema is idempotent ────────────────────────────────────


def test_ensure_schema_idempotent(db_path: Path) -> None:
    ci.ensure_schema(db_path)
    ci.ensure_schema(db_path)
    with sqlite3.connect(db_path) as conn:
        version = conn.execute("SELECT version FROM schema_version").fetchone()
    assert version == (ci.SCHEMA_VERSION,)


# ─── case 2: append + search Korean ────────────────────────────────────────


def test_append_search_roundtrip_korean(initialized_db: Path) -> None:
    ci.append(
        initialized_db,
        chat_id="chat_1",
        role="user",
        content="지난주 토요일에 강남 카페에서 미팅했어",
    )
    hits = ci.search(initialized_db, query="강남")
    assert len(hits) == 1
    assert "강남" in hits[0].content
    assert hits[0].chat_id == "chat_1"
    assert hits[0].role == "user"


# ─── case 3: append + search English ───────────────────────────────────────


def test_append_search_roundtrip_english(initialized_db: Path) -> None:
    ci.append(
        initialized_db,
        chat_id="chat_1",
        role="assistant",
        content="The meeting at the Gangnam cafe was productive.",
    )
    hits = ci.search(initialized_db, query="meeting")
    assert len(hits) == 1
    assert "meeting" in hits[0].content.lower()


# ─── case 4: emoji content ─────────────────────────────────────────────────


def test_append_search_with_emoji(initialized_db: Path) -> None:
    ci.append(
        initialized_db,
        chat_id="chat_1",
        role="user",
        content="🦞 lobster lunch was great 👍",
    )
    hits = ci.search(initialized_db, query="lobster")
    assert len(hits) == 1
    assert "🦞" in hits[0].content


# ─── case 5: BM25 ranking ──────────────────────────────────────────────────


def test_search_bm25_ranking_prefers_more_relevant(initialized_db: Path) -> None:
    ci.append(
        initialized_db,
        chat_id="chat_1",
        role="user",
        content="짬뽕 짬뽕 짬뽕은 정말 맛있다",
    )
    ci.append(
        initialized_db,
        chat_id="chat_1",
        role="user",
        content="저녁에 짬뽕 먹었음",
    )
    ci.append(
        initialized_db,
        chat_id="chat_1",
        role="user",
        content="냉면이 좋다",
    )
    hits = ci.search(initialized_db, query="짬뽕")
    assert len(hits) == 2
    # BM25 in SQLite returns negative numbers; lower (more negative) = more relevant
    assert "짬뽕 짬뽕 짬뽕" in hits[0].content
    assert hits[0].score <= hits[1].score


# ─── case 6: date filter ───────────────────────────────────────────────────


def test_search_since_until_filters(initialized_db: Path) -> None:
    ci.append(
        initialized_db,
        chat_id="chat_1",
        role="user",
        content="apple yesterday",
        ts=_utc(2026, 4, 20),
    )
    ci.append(
        initialized_db,
        chat_id="chat_1",
        role="user",
        content="apple today",
        ts=_utc(2026, 4, 25),
    )
    ci.append(
        initialized_db,
        chat_id="chat_1",
        role="user",
        content="apple tomorrow",
        ts=_utc(2026, 4, 30),
    )

    hits = ci.search(
        initialized_db,
        query="apple",
        since=_utc(2026, 4, 22),
        until=_utc(2026, 4, 28),
    )
    contents = {h.content for h in hits}
    assert contents == {"apple today"}


# ─── case 7: chat_id filter ────────────────────────────────────────────────


def test_search_chat_id_filter(initialized_db: Path) -> None:
    ci.append(initialized_db, chat_id="chat_1", role="user", content="apple chat one")
    ci.append(initialized_db, chat_id="chat_2", role="user", content="apple chat two")
    hits = ci.search(initialized_db, query="apple", chat_id="chat_1")
    assert len(hits) == 1
    assert hits[0].chat_id == "chat_1"


# ─── case 8: limit ─────────────────────────────────────────────────────────


def test_search_limit(initialized_db: Path) -> None:
    for index in range(5):
        ci.append(
            initialized_db,
            chat_id="chat_1",
            role="user",
            content=f"apple {index}",
        )
    hits = ci.search(initialized_db, query="apple", limit=3)
    assert len(hits) == 3


def test_search_limit_zero_or_negative(initialized_db: Path) -> None:
    ci.append(initialized_db, chat_id="chat_1", role="user", content="apple")
    assert ci.search(initialized_db, query="apple", limit=0) == []
    assert ci.search(initialized_db, query="apple", limit=-1) == []


# ─── case 9: empty result ──────────────────────────────────────────────────


def test_search_no_match_returns_empty(initialized_db: Path) -> None:
    ci.append(initialized_db, chat_id="chat_1", role="user", content="apple")
    assert ci.search(initialized_db, query="banana") == []


def test_search_db_missing_returns_empty(tmp_path: Path) -> None:
    assert ci.search(tmp_path / "missing.db", query="apple") == []


def test_search_blank_query_returns_empty(initialized_db: Path) -> None:
    ci.append(initialized_db, chat_id="chat_1", role="user", content="apple")
    assert ci.search(initialized_db, query="   ") == []


# ─── case 10: SQL injection defense ────────────────────────────────────────


def test_search_query_with_sql_metacharacters_safe(initialized_db: Path) -> None:
    ci.append(initialized_db, chat_id="chat_1", role="user", content="benign content")
    # Query containing characters that would be dangerous if naively interpolated.
    # FTS5 will reject these as bad MATCH syntax — we expect empty results, not crash.
    hits = ci.search(initialized_db, query="' OR 1=1 --")
    assert hits == []
    hits = ci.search(initialized_db, query="benign'; DROP TABLE messages; --")
    # The DROP must NOT have executed.
    assert hits == []
    follow_up = ci.search(initialized_db, query="benign")
    assert len(follow_up) == 1


# ─── case 11: reindex from session markdown ────────────────────────────────


def test_reindex_session_dir_from_markdown(tmp_path: Path) -> None:
    sessions_root = tmp_path / "sessions"
    chat_dir = sessions_root / "chat_42"
    chat_dir.mkdir(parents=True)
    md = chat_dir / "conversation-260425.md"
    md.write_text(
        "\n## user (2026-04-25 09:30:15 UTC)\n\n"
        "어제 강남 카페에서 미팅\n"
        "\n## assistant (2026-04-25 09:30:16 UTC)\n\n"
        "네, 어떤 카페였나요?\n"
        "\n## user (2026-04-25 09:31:00 UTC)\n\n"
        "Blue Bottle 강남점\n",
        encoding="utf-8",
    )
    db = tmp_path / "conversation.db"
    inserted = ci.reindex_session_dir(db, sessions_root)
    assert inserted == 3
    hits = ci.search(db, query="Bottle")
    assert len(hits) == 1
    assert hits[0].chat_id == "chat_42"
    assert hits[0].role == "user"


# ─── case 12: reindex tolerates malformed lines ────────────────────────────


def test_reindex_session_dir_ignores_malformed_headers(tmp_path: Path) -> None:
    sessions_root = tmp_path / "sessions"
    chat_dir = sessions_root / "chat_1"
    chat_dir.mkdir(parents=True)
    (chat_dir / "conversation-260425.md").write_text(
        "garbage line at the top\n"
        "## bogus header without timestamp\n"
        "\n## user (2026-04-25 09:30:15 UTC)\n\n"
        "valid message\n"
        "## stranger (some weird format)\n"
        "trailing junk\n",
        encoding="utf-8",
    )
    db = tmp_path / "conversation.db"
    inserted = ci.reindex_session_dir(db, sessions_root)
    assert inserted == 1


# ─── reindex group dir ─────────────────────────────────────────────────────


def test_reindex_group_dir_from_markdown(tmp_path: Path) -> None:
    conv_dir = tmp_path / "conversation"
    conv_dir.mkdir(parents=True)
    (conv_dir / "260425.md").write_text(
        "[09:30:15] user: 미션 시작\n"
        "[09:30:20] @orchestrator_bot: 알겠습니다, 분배합니다.\n"
        "[09:31:00] @member_bot_a: Done\n",
        encoding="utf-8",
    )
    db = tmp_path / "conversation.db"
    inserted = ci.reindex_group_dir(db, conv_dir)
    assert inserted == 3
    hits = ci.search(db, query="미션")
    assert len(hits) == 1
    assert hits[0].role == "user"
    bot_hits = ci.search(db, query="알겠습니다")
    assert len(bot_hits) == 1
    assert bot_hits[0].role == "@orchestrator_bot"


def test_reindex_session_dir_replaces_existing(tmp_path: Path) -> None:
    sessions_root = tmp_path / "sessions"
    (sessions_root / "chat_1").mkdir(parents=True)
    md = sessions_root / "chat_1" / "conversation-260425.md"
    md.write_text(
        "\n## user (2026-04-25 09:30:15 UTC)\n\nfirst content\n",
        encoding="utf-8",
    )
    db = tmp_path / "conversation.db"
    ci.reindex_session_dir(db, sessions_root)

    md.write_text(
        "\n## user (2026-04-25 09:30:15 UTC)\n\nsecond content\n",
        encoding="utf-8",
    )
    inserted = ci.reindex_session_dir(db, sessions_root)
    assert inserted == 1
    hits = ci.search(db, query="content")
    assert len(hits) == 1
    assert "second" in hits[0].content
    # First content must be gone.
    assert ci.search(db, query="first") == []


def test_reindex_session_dir_missing_returns_zero(tmp_path: Path) -> None:
    db = tmp_path / "conversation.db"
    assert ci.reindex_session_dir(db, tmp_path / "nonexistent") == 0
    # ensure_schema still produced a valid DB.
    assert db.exists()


# ─── case 14: concurrent appends (WAL) ─────────────────────────────────────


def test_concurrent_appends_no_loss(tmp_path: Path) -> None:
    db = tmp_path / "conversation.db"
    ci.ensure_schema(db)

    async def insert_many(prefix: str) -> None:
        await asyncio.sleep(0)  # let event loop schedule
        for index in range(20):
            ci.append(
                db,
                chat_id="chat_1",
                role="user",
                content=f"{prefix}-{index}",
            )

    async def runner() -> None:
        await asyncio.gather(insert_many("alpha"), insert_many("beta"))

    asyncio.run(runner())

    with sqlite3.connect(db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    assert count == 40


# ─── case 15: very long content ────────────────────────────────────────────


def test_append_large_content(initialized_db: Path) -> None:
    big = "huge " * 50_000  # ~250 KB
    ok = ci.append(
        initialized_db,
        chat_id="chat_1",
        role="user",
        content=big,
    )
    assert ok is True
    hits = ci.search(initialized_db, query="huge")
    assert len(hits) == 1
    # Snippet should be bounded.
    assert len(hits[0].snippet) < 1000


# ─── role filter ───────────────────────────────────────────────────────────


def test_search_role_filter(initialized_db: Path) -> None:
    ci.append(initialized_db, chat_id="chat_1", role="user", content="apple user")
    ci.append(
        initialized_db,
        chat_id="chat_1",
        role="assistant",
        content="apple assistant",
    )
    user_hits = ci.search(initialized_db, query="apple", role="user")
    assert len(user_hits) == 1
    assert user_hits[0].role == "user"


# ─── empty content rejection ───────────────────────────────────────────────


def test_append_blank_content_rejected(initialized_db: Path) -> None:
    assert ci.append(initialized_db, chat_id="chat_1", role="user", content="") is False
    assert ci.append(initialized_db, chat_id="chat_1", role="user", content="   ") is False
    with sqlite3.connect(initialized_db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    assert count == 0


# ─── path helpers ──────────────────────────────────────────────────────────


def test_db_path_for_bot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ABYSS_HOME", str(tmp_path))
    expected = tmp_path / "bots" / "alpha" / "conversation.db"
    assert ci.db_path_for_bot("alpha") == expected


def test_db_path_for_group(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ABYSS_HOME", str(tmp_path))
    expected = tmp_path / "groups" / "team_one" / "conversation.db"
    assert ci.db_path_for_group("team_one") == expected
