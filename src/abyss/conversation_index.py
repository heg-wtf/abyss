"""SQLite FTS5 index for cross-session conversation search.

Markdown conversation logs (``conversation-YYMMDD.md`` for bots,
``YYMMDD.md`` for groups) remain the source of truth. This module
maintains a parallel SQLite FTS5 index that lets Claude (via the
``conversation_search`` MCP server) recall past messages by keyword.

Design points:

* One DB per scope: ``~/.abyss/bots/<name>/conversation.db`` and
  (Group databases used to live alongside the bot ones; that
  surface was removed with the Telegram + group teardown.)
* Schema is a single virtual table with a BM25-rankable ``content``
  column plus unindexed metadata (``chat_id``, ``role``, ``ts``,
  ``date_key``).
* Append is best-effort — markdown is canonical, so an index failure
  logs a warning but never blocks message handling.
* ``reindex_session_dir`` and ``reindex_group_dir`` rebuild the index
  from markdown when the DB is missing or out of sync.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

# Per-process cache of DB paths already initialised. Avoids running
# ``CREATE TABLE IF NOT EXISTS`` on every ``append`` call once a DB has
# been seen. Reset on process exit.
_initialised: set[str] = set()

# Header line written by ``session.log_conversation``:
#     ## user (2026-04-25 09:30:15 UTC)
SESSION_HEADER_RE = re.compile(
    r"^##\s+(?P<role>user|assistant)\s+"
    r"\((?P<ts>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+UTC\)\s*$"
)

# Group log entries used to use this same one-line format:
#     [09:30:15] @bot_name: hello world
GROUP_LINE_RE = re.compile(
    r"^\[(?P<time>\d{2}:\d{2}:\d{2})\]\s+(?P<sender>[^:]+):\s?(?P<content>.*)$"
)


@dataclass(frozen=True, slots=True)
class SearchHit:
    """A single search result row."""

    chat_id: str
    role: str
    ts: str
    snippet: str
    score: float
    content: str
    date_key: str


def is_fts5_available() -> bool:
    """Return True when the bundled SQLite supports the FTS5 extension."""
    try:
        with sqlite3.connect(":memory:") as conn:
            conn.execute("CREATE VIRTUAL TABLE _probe USING fts5(x)")
        return True
    except sqlite3.OperationalError:
        return False


def db_path_for_bot(bot_name: str) -> Path:
    """Return the FTS5 DB path for a given bot."""
    from abyss.config import bot_directory

    return bot_directory(bot_name) / "conversation.db"


@contextmanager
def _open(db_path: Path) -> Iterator[sqlite3.Connection]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        yield conn
        conn.commit()
    finally:
        conn.close()


def ensure_schema(db_path: Path) -> None:
    """Create the messages table if missing. Idempotent."""
    with _open(db_path) as conn:
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS messages USING fts5(
                content,
                chat_id UNINDEXED,
                role UNINDEXED,
                ts UNINDEXED,
                date_key UNINDEXED,
                tokenize='unicode61 remove_diacritics 2'
            )
            """
        )
        conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)")
        conn.execute(
            "INSERT OR IGNORE INTO schema_version (version) VALUES (?)",
            (SCHEMA_VERSION,),
        )
    _initialised.add(str(db_path.resolve()))


def _lazy_ensure(db_path: Path) -> None:
    """Run ``ensure_schema`` once per DB path per process."""
    key = str(db_path.resolve()) if db_path.exists() else str(db_path.absolute())
    if key in _initialised:
        return
    ensure_schema(db_path)


def append(
    db_path: Path,
    *,
    chat_id: str,
    role: str,
    content: str,
    ts: datetime | None = None,
) -> bool:
    """Insert a message into the index. Returns True on success.

    Markdown is the source of truth — failures here log and return False
    rather than raising, so message handling never breaks because of an
    index hiccup.
    """
    if not content.strip():
        return False
    if ts is None:
        ts = datetime.now(timezone.utc)
    ts_str = ts.strftime("%Y-%m-%d %H:%M:%S UTC")
    date_key = ts.strftime("%Y-%m-%d")

    sql = "INSERT INTO messages (content, chat_id, role, ts, date_key) VALUES (?, ?, ?, ?, ?)"
    params = (content, chat_id, role, ts_str, date_key)
    try:
        _lazy_ensure(db_path)
        with _open(db_path) as conn:
            conn.execute(sql, params)
        return True
    except sqlite3.OperationalError as exc:
        # Schema may have been wiped externally — try once with a fresh
        # ``ensure_schema`` and retry.
        if "no such table" in str(exc).lower():
            try:
                ensure_schema(db_path)
                with _open(db_path) as conn:
                    conn.execute(sql, params)
                return True
            except sqlite3.Error as exc2:
                logger.warning("conversation_index append retry failed (%s): %s", db_path, exc2)
                return False
        logger.warning("conversation_index append failed (%s): %s", db_path, exc)
        return False
    except sqlite3.Error as exc:
        logger.warning("conversation_index append failed (%s): %s", db_path, exc)
        return False


def search(
    db_path: Path,
    *,
    query: str,
    since: datetime | None = None,
    until: datetime | None = None,
    chat_id: str | None = None,
    role: str | None = None,
    limit: int = 20,
) -> list[SearchHit]:
    """Run a BM25-ranked FTS5 search. Empty/invalid inputs return [].

    Args:
        db_path: Path to the FTS5 database.
        query: User-supplied search expression. Passed through as a
            parameterized FTS5 ``MATCH`` value.
        since: Inclusive lower bound on the message date.
        until: Inclusive upper bound on the message date.
        chat_id: Restrict to a specific chat directory key
            (``chat_<id>``) when provided.
        role: Restrict to ``user`` / ``assistant`` (or any group sender
            string) when provided.
        limit: Maximum hits to return; values < 1 yield ``[]``.
    """
    if not db_path.exists():
        return []
    if not query.strip():
        return []
    if limit < 1:
        return []

    where: list[str] = ["messages MATCH ?"]
    params: list = [query]
    if since is not None:
        where.append("date_key >= ?")
        params.append(since.strftime("%Y-%m-%d"))
    if until is not None:
        where.append("date_key <= ?")
        params.append(until.strftime("%Y-%m-%d"))
    if chat_id is not None:
        where.append("chat_id = ?")
        params.append(chat_id)
    if role is not None:
        where.append("role = ?")
        params.append(role)

    sql = (
        "SELECT chat_id, role, ts, content, date_key, "
        "snippet(messages, 0, '<<', '>>', '...', 32) AS snippet, "
        "bm25(messages) AS score "
        "FROM messages "
        f"WHERE {' AND '.join(where)} "
        "ORDER BY score "
        "LIMIT ?"
    )
    params.append(limit)

    try:
        with _open(db_path) as conn:
            rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error as exc:
        logger.warning("conversation_index search failed (%s): %s", db_path, exc)
        return []

    return [
        SearchHit(
            chat_id=row[0],
            role=row[1],
            ts=row[2],
            content=row[3],
            date_key=row[4],
            snippet=row[5],
            score=row[6],
        )
        for row in rows
    ]


def reindex_session_dir(db_path: Path, sessions_root: Path) -> int:
    """Rebuild the bot index from ``sessions/chat_*/conversation-*.md``.

    Wipes existing rows in a single transaction, then bulk-inserts.
    Returns the number of messages inserted. When ``sessions_root`` is
    missing the index is still wiped (zero rows inserted) so a stale
    DB does not survive deletion of its source markdown.
    """
    ensure_schema(db_path)

    rows: list[tuple] = []
    if sessions_root.exists():
        for chat_dir in sorted(sessions_root.iterdir()):
            if not chat_dir.is_dir() or not chat_dir.name.startswith("chat_"):
                continue
            chat_id = chat_dir.name
            for md_file in sorted(chat_dir.glob("conversation-*.md")):
                for role, ts_str, content, date_key in _iter_session_messages(md_file):
                    rows.append((content, chat_id, role, ts_str, date_key))

    return _replace_rows(db_path, rows)


def reindex_group_dir(db_path: Path, conversation_dir: Path) -> int:
    """Rebuild the group index from ``groups/<name>/conversation/YYMMDD.md``.

    Wipes existing rows even when ``conversation_dir`` is missing so a
    deleted source directory does not leave stale searchable rows.
    """
    ensure_schema(db_path)

    rows: list[tuple] = []
    if conversation_dir.exists():
        for md_file in sorted(conversation_dir.glob("[0-9][0-9][0-9][0-9][0-9][0-9].md")):
            try:
                date_key = datetime.strptime(md_file.stem, "%y%m%d").strftime("%Y-%m-%d")
            except ValueError:
                continue
            for sender, ts_str, content in _iter_group_messages(md_file, date_key):
                rows.append((content, "group", sender, ts_str, date_key))

    return _replace_rows(db_path, rows)


def _replace_rows(db_path: Path, rows: list[tuple]) -> int:
    """Wipe ``messages`` and bulk-insert ``rows``. Returns insert count."""
    try:
        with _open(db_path) as conn:
            conn.execute("DELETE FROM messages")
            if rows:
                conn.executemany(
                    "INSERT INTO messages (content, chat_id, role, ts, date_key) "
                    "VALUES (?, ?, ?, ?, ?)",
                    rows,
                )
        return len(rows)
    except sqlite3.Error as exc:
        logger.warning("conversation_index reindex failed (%s): %s", db_path, exc)
        return 0


def _iter_session_messages(md_file: Path) -> Iterator[tuple[str, str, str, str]]:
    """Yield ``(role, ts_str, content, date_key)`` per message in a session log."""
    try:
        text = md_file.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("could not read %s: %s", md_file, exc)
        return

    role: str | None = None
    ts: str | None = None
    date_key: str | None = None
    buffer: list[str] = []

    def flush() -> tuple[str, str, str, str] | None:
        if role and ts and date_key:
            content = "\n".join(buffer).strip()
            if content:
                return (role, f"{ts} UTC", content, date_key)
        return None

    for line in text.splitlines():
        match = SESSION_HEADER_RE.match(line)
        if match:
            done = flush()
            if done:
                yield done
            role = match.group("role")
            ts = match.group("ts")
            date_key = ts.split(" ", 1)[0]
            buffer = []
            continue
        if role is not None:
            buffer.append(line)

    done = flush()
    if done:
        yield done


def _iter_group_messages(md_file: Path, date_key: str) -> Iterator[tuple[str, str, str]]:
    """Yield ``(sender, ts_str, content)`` per line in a group conversation log."""
    try:
        text = md_file.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("could not read %s: %s", md_file, exc)
        return

    for line in text.splitlines():
        match = GROUP_LINE_RE.match(line)
        if not match:
            continue
        time_str = match.group("time")
        sender = match.group("sender").strip()
        content = match.group("content").strip()
        if not content:
            continue
        yield (sender, f"{date_key} {time_str} UTC", content)
