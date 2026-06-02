"""Unit tests for the Phase 4 extraction pipeline.

These tests live in a separate module from ``test_episodes.py`` because
they patch ``abyss.llm.registry`` and benefit from a slightly heavier
fixture (per-bot conversation logs on disk).
"""

from __future__ import annotations

import json
import textwrap
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def abyss_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ABYSS_HOME", str(tmp_path))
    bot_dir = tmp_path / "bots" / "anne"
    bot_dir.mkdir(parents=True)
    return tmp_path


# --- Helpers ------------------------------------------------------------------


def _write_log(home: Path, session_segment: str, yymmdd: str, body: str) -> Path:
    session_dir = home / "bots" / "anne" / session_segment
    session_dir.mkdir(parents=True, exist_ok=True)
    path = session_dir / f"conversation-{yymmdd}.md"
    path.write_text(body, encoding="utf-8")
    return path


# --- Conversation discovery + collection --------------------------------------


def test_find_conversation_logs_for_date_walks_all_session_kinds(abyss_home: Path) -> None:
    from abyss.episodes import find_conversation_logs_for_date

    chat = _write_log(abyss_home, "sessions/chat_web_abc", "260601", "chat body")
    cron = _write_log(abyss_home, "cron_sessions/daily", "260601", "cron body")
    heartbeat = _write_log(abyss_home, "heartbeat_sessions", "260601", "hb body")
    # Different date, ignored:
    _write_log(abyss_home, "sessions/chat_web_abc", "260602", "tomorrow body")

    found = find_conversation_logs_for_date("anne", "260601")
    assert set(found) == {chat, cron, heartbeat}


def test_collect_conversation_text_concatenates_with_headers(abyss_home: Path) -> None:
    from abyss.episodes import collect_conversation_text

    _write_log(abyss_home, "sessions/chat_web_a", "260601", "alpha body")
    _write_log(abyss_home, "sessions/chat_web_b", "260601", "beta body")

    blob, used = collect_conversation_text("anne", "260601")
    assert "alpha body" in blob and "beta body" in blob
    assert blob.count("===") == 4  # two file path delimiters, each wrapped in two ===
    assert len(used) == 2


def test_collect_conversation_text_respects_max_bytes(abyss_home: Path) -> None:
    from abyss.episodes import collect_conversation_text

    big = "x" * 5000
    _write_log(abyss_home, "sessions/chat_a", "260601", big)
    _write_log(abyss_home, "sessions/chat_b", "260601", big)
    blob, used = collect_conversation_text("anne", "260601", max_bytes=4000)
    assert len(blob.encode("utf-8")) <= 4000
    # We stopped before reading the second file in full.
    assert len(used) <= 2


def test_collect_conversation_text_missing_logs_returns_empty(abyss_home: Path) -> None:
    from abyss.episodes import collect_conversation_text

    blob, used = collect_conversation_text("anne", "260601")
    assert blob == ""
    assert used == []


# --- Response parsing ---------------------------------------------------------


VALID_RESPONSE = {
    "episodes": [
        {
            "kind": "decision",
            "summary": "ship phase 4",
            "source_turn": "conversation-260601.md#turn-12",
            "facts": [
                {
                    "subject": "phase 4",
                    "claim": "extraction pipeline approved",
                    "confidence": 0.85,
                }
            ],
        },
        {
            "kind": "event",
            "summary": "user paired with claude on docs",
            "source_turn": "conversation-260601.md#turn-2",
            "facts": [],
        },
    ]
}


def test_parse_extraction_response_happy_path() -> None:
    from abyss.episodes import parse_extraction_response

    episodes, facts_by_idx = parse_extraction_response(
        json.dumps(VALID_RESPONSE), date_iso="2026-06-01"
    )
    assert len(episodes) == 2
    assert episodes[0].kind == "decision"
    assert episodes[0].date == "2026-06-01"
    assert 0 in facts_by_idx and facts_by_idx[0][0].subject == "phase 4"
    # Episode 1 had no facts → not in the map.
    assert 1 not in facts_by_idx


def test_parse_extraction_response_strips_code_fence() -> None:
    from abyss.episodes import parse_extraction_response

    fenced = "```json\n" + json.dumps(VALID_RESPONSE) + "\n```"
    episodes, _ = parse_extraction_response(fenced, date_iso="2026-06-01")
    assert len(episodes) == 2


def test_parse_extraction_response_bad_json_returns_empty() -> None:
    from abyss.episodes import parse_extraction_response

    episodes, facts_by_idx = parse_extraction_response("not json", date_iso="2026-06-01")
    assert episodes == [] and facts_by_idx == {}


def test_parse_extraction_response_drops_invalid_kind() -> None:
    from abyss.episodes import parse_extraction_response

    payload = {
        "episodes": [
            {"kind": "rumor", "summary": "x", "source_turn": "", "facts": []},
            {"kind": "fact", "summary": "valid", "source_turn": "", "facts": []},
        ]
    }
    episodes, _ = parse_extraction_response(json.dumps(payload), date_iso="2026-06-01")
    assert [e.summary for e in episodes] == ["valid"]


def test_parse_extraction_response_drops_bad_facts_keeps_episode() -> None:
    from abyss.episodes import parse_extraction_response

    payload = {
        "episodes": [
            {
                "kind": "fact",
                "summary": "ok episode",
                "source_turn": "",
                "facts": [
                    {"subject": "", "claim": "empty subject is dropped", "confidence": 0.9},
                    {"subject": "ok", "claim": "ok claim", "confidence": 0.7},
                ],
            }
        ]
    }
    episodes, facts_by_idx = parse_extraction_response(json.dumps(payload), date_iso="2026-06-01")
    assert len(episodes) == 1
    assert len(facts_by_idx[0]) == 1
    assert facts_by_idx[0][0].subject == "ok"


# --- extract_yesterday end-to-end with a stub backend -------------------------


@dataclass
class _StubResult:
    text: str


class _StubBackend:
    """Returns a canned LLM response so the test never hits real Claude."""

    def __init__(self, response: str) -> None:
        self.response = response
        self.received_prompt: str | None = None

    async def run(self, request: Any) -> _StubResult:
        self.received_prompt = request.user_prompt
        return _StubResult(text=self.response)


@pytest.mark.asyncio
async def test_extract_yesterday_persists_episodes_and_facts(
    abyss_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from abyss import episodes
    from abyss.episodes import (
        extract_yesterday,
        iter_episodes,
        query_facts,
    )

    yymmdd = "260601"
    _write_log(
        abyss_home,
        "sessions/chat_web_x",
        yymmdd,
        textwrap.dedent(
            """\
            ## user
            shipping phase 4 today

            ## assistant
            confirmed, plan approved
            """
        ),
    )

    stub = _StubBackend(json.dumps(VALID_RESPONSE))
    monkeypatch.setattr("abyss.llm.registry.get_or_create", lambda *_args, **_kwargs: stub)

    episode_ids, fact_ids = await extract_yesterday("anne", {"name": "anne"}, yymmdd=yymmdd)
    assert episode_ids == [0, 1]
    assert len(fact_ids) == 1
    # Prompt was built with the right date.
    assert stub.received_prompt is not None and "2026-06-01" in stub.received_prompt

    # Persisted state.
    timeline = list(iter_episodes("anne"))
    assert {e.summary for e in timeline} == {
        "ship phase 4",
        "user paired with claude on docs",
    }
    facts = query_facts("anne", subject="phase 4")
    assert len(facts) == 1
    assert facts[0]["claim"] == "extraction pipeline approved"

    # Sentinel pull-through: extraction session dir was created.
    assert (abyss_home / "bots" / "anne" / "extract_sessions" / "episode_extract").exists()
    # Silence unused import warning.
    _ = episodes


@pytest.mark.asyncio
async def test_extract_yesterday_no_logs_returns_empty(
    abyss_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from abyss.episodes import extract_yesterday

    calls = {"n": 0}

    def _stub(*_a: Any, **_k: Any) -> None:
        calls["n"] += 1
        raise AssertionError("backend should not be called when there are no logs")

    monkeypatch.setattr("abyss.llm.registry.get_or_create", _stub)
    episode_ids, fact_ids = await extract_yesterday("anne", {"name": "anne"}, yymmdd="260601")
    assert episode_ids == [] and fact_ids == []
    assert calls["n"] == 0


@pytest.mark.asyncio
async def test_extract_yesterday_empty_llm_response(
    abyss_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from abyss.episodes import extract_yesterday

    _write_log(abyss_home, "sessions/chat_web_x", "260601", "anything")
    monkeypatch.setattr(
        "abyss.llm.registry.get_or_create",
        lambda *_a, **_k: _StubBackend(""),
    )
    episode_ids, fact_ids = await extract_yesterday("anne", {"name": "anne"}, yymmdd="260601")
    assert (episode_ids, fact_ids) == ([], [])


@pytest.mark.asyncio
async def test_extract_yesterday_bad_json_response(
    abyss_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from abyss.episodes import extract_yesterday

    _write_log(abyss_home, "sessions/chat_web_x", "260601", "anything")
    monkeypatch.setattr(
        "abyss.llm.registry.get_or_create",
        lambda *_a, **_k: _StubBackend("definitely not json"),
    )
    episode_ids, fact_ids = await extract_yesterday("anne", {"name": "anne"}, yymmdd="260601")
    assert (episode_ids, fact_ids) == ([], [])


def test_yesterday_yymmdd_defaults_to_today_minus_one() -> None:
    from abyss.episodes import _yesterday_yymmdd

    fixed_today = datetime(2026, 6, 2, 12, 0, tzinfo=timezone.utc)
    assert _yesterday_yymmdd(fixed_today) == "260601"
