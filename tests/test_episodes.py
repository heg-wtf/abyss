"""Unit tests for ``abyss.episodes`` (Phase 4 storage layer)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest


@pytest.fixture
def abyss_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ABYSS_HOME", str(tmp_path))
    bot_dir = tmp_path / "bots" / "anne"
    bot_dir.mkdir(parents=True)
    return tmp_path


# --- Dataclass validation -----------------------------------------------------


def test_episode_rejects_unknown_kind() -> None:
    from abyss.episodes import Episode

    with pytest.raises(ValueError, match="invalid episode kind"):
        Episode(ts="2026-06-02T00:00:00", date="2026-06-02", kind="rumor", summary="x")


def test_episode_accepts_all_canonical_kinds() -> None:
    from abyss.episodes import EPISODE_KINDS, Episode

    for kind in EPISODE_KINDS:
        Episode(ts="2026-06-02T00:00:00", date="2026-06-02", kind=kind, summary="x")


def test_fact_rejects_out_of_range_confidence() -> None:
    from abyss.episodes import Fact

    with pytest.raises(ValueError, match="confidence"):
        Fact(subject="s", claim="c", confidence=1.5)
    with pytest.raises(ValueError, match="confidence"):
        Fact(subject="s", claim="c", confidence=-0.1)


def test_fact_rejects_unknown_status() -> None:
    from abyss.episodes import Fact

    with pytest.raises(ValueError, match="status"):
        Fact(subject="s", claim="c", confidence=0.5, status="hearsay")


def test_fact_rejects_empty_subject_or_claim() -> None:
    from abyss.episodes import Fact

    with pytest.raises(ValueError, match="subject"):
        Fact(subject="   ", claim="c", confidence=0.5)
    with pytest.raises(ValueError, match="claim"):
        Fact(subject="s", claim="", confidence=0.5)


# --- episodes.jsonl roundtrip -------------------------------------------------


def test_append_episode_creates_file_and_one_line(abyss_home: Path) -> None:
    from abyss.episodes import Episode, append_episode, episodes_path

    ep = Episode(
        ts="2026-06-02T00:00:00+00:00",
        date="2026-06-01",
        kind="decision",
        summary="ship phase 4",
        source_turn="conversation-260601.md#turn-12",
    )
    path = append_episode("anne", ep)
    assert path == episodes_path("anne")
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    loaded = json.loads(lines[0])
    assert loaded["kind"] == "decision"
    assert loaded["summary"] == "ship phase 4"


def test_iter_episodes_orders_newest_first_with_filters(abyss_home: Path) -> None:
    from abyss.episodes import Episode, append_episode, iter_episodes

    for date, summary in [
        ("2026-05-30", "old fact"),
        ("2026-06-01", "newer decision"),
        ("2026-05-29", "ancient change"),
    ]:
        kind = "fact" if "fact" in summary else "decision" if "decision" in summary else "change"
        append_episode(
            "anne",
            Episode(
                ts=f"{date}T12:00:00+00:00",
                date=date,
                kind=kind,
                summary=summary,
            ),
        )
    rows = list(iter_episodes("anne"))
    assert [r.date for r in rows] == ["2026-06-01", "2026-05-30", "2026-05-29"]

    since = list(iter_episodes("anne", since="2026-05-30"))
    assert {r.date for r in since} == {"2026-05-30", "2026-06-01"}

    decisions = list(iter_episodes("anne", kinds=("decision",)))
    assert len(decisions) == 1
    assert decisions[0].summary == "newer decision"

    limited = list(iter_episodes("anne", limit=2))
    assert len(limited) == 2


def test_iter_episodes_skips_malformed_lines(abyss_home: Path) -> None:
    from abyss.episodes import episodes_path, iter_episodes

    path = episodes_path("anne")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                '{"ts":"2026-06-01T00:00:00","date":"2026-06-01","kind":"fact",'
                '"summary":"valid","source_turn":"","meta":{}}',
                "not even json",
                '{"ts":"2026-06-02","date":"2026-06-02","kind":"bogus","summary":"x",'
                '"source_turn":"","meta":{}}',  # invalid kind triggers ValueError
            ]
        ),
        encoding="utf-8",
    )
    rows = list(iter_episodes("anne"))
    assert len(rows) == 1
    assert rows[0].summary == "valid"


def test_iter_episodes_missing_file_returns_nothing(abyss_home: Path) -> None:
    from abyss.episodes import iter_episodes

    assert list(iter_episodes("anne")) == []


# --- facts.db roundtrip -------------------------------------------------------


def test_init_facts_db_creates_schema(abyss_home: Path) -> None:
    from abyss.episodes import facts_db_path, init_facts_db

    path = init_facts_db("anne")
    assert path == facts_db_path("anne")
    with sqlite3.connect(path) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "facts" in tables


def test_upsert_fact_inserts_then_updates_confidence(abyss_home: Path) -> None:
    from abyss.episodes import Fact, query_facts, upsert_fact

    first_id = upsert_fact(
        "anne",
        Fact(subject="release", claim="v2026.06.02 shipped", confidence=0.6),
    )
    second_id = upsert_fact(
        "anne",
        Fact(subject="release", claim="v2026.06.02 shipped", confidence=0.9),
    )
    assert first_id == second_id  # dedup on (subject, claim)
    rows = query_facts("anne", subject="release")
    assert len(rows) == 1
    assert rows[0]["confidence"] == pytest.approx(0.9)


def test_upsert_fact_does_not_lower_confidence(abyss_home: Path) -> None:
    from abyss.episodes import Fact, query_facts, upsert_fact

    upsert_fact("anne", Fact(subject="s", claim="c", confidence=0.8))
    upsert_fact("anne", Fact(subject="s", claim="c", confidence=0.3))
    rows = query_facts("anne", subject="s")
    assert rows[0]["confidence"] == pytest.approx(0.8)


def test_query_facts_filters_by_status_and_confidence(abyss_home: Path) -> None:
    from abyss.episodes import Fact, query_facts, retract_fact, upsert_fact

    upsert_fact("anne", Fact(subject="a", claim="ca", confidence=0.9))
    upsert_fact("anne", Fact(subject="b", claim="cb", confidence=0.4))
    bad_id = upsert_fact("anne", Fact(subject="c", claim="cc", confidence=0.95))
    assert retract_fact("anne", bad_id) is True

    active = query_facts("anne")
    subjects = {r["subject"] for r in active}
    assert subjects == {"a", "b"}

    high = query_facts("anne", min_confidence=0.5)
    assert [r["subject"] for r in high] == ["a"]

    with_retracted = query_facts("anne", statuses=("active", "retracted"), min_confidence=0.0)
    assert {r["subject"] for r in with_retracted} == {"a", "b", "c"}


def test_retract_unknown_id_returns_false(abyss_home: Path) -> None:
    from abyss.episodes import Fact, retract_fact, upsert_fact

    upsert_fact("anne", Fact(subject="s", claim="c", confidence=0.5))
    assert retract_fact("anne", 999) is False


def test_retract_missing_db_returns_false(abyss_home: Path) -> None:
    from abyss.episodes import retract_fact

    # facts.db has not been created yet for this bot.
    assert retract_fact("anne", 1) is False


def test_query_facts_orders_by_confidence_then_recency(abyss_home: Path) -> None:
    from abyss.episodes import Fact, query_facts, upsert_fact

    upsert_fact("anne", Fact(subject="x", claim="low", confidence=0.4))
    upsert_fact("anne", Fact(subject="x", claim="mid", confidence=0.7))
    upsert_fact("anne", Fact(subject="x", claim="high", confidence=0.9))
    rows = query_facts("anne", subject="x")
    assert [r["claim"] for r in rows] == ["high", "mid", "low"]


# --- record_extraction atomic write -------------------------------------------


def test_record_extraction_writes_both_stores(abyss_home: Path) -> None:
    from abyss.episodes import (
        Episode,
        Fact,
        episodes_path,
        iter_episodes,
        query_facts,
        record_extraction,
    )

    episodes = [
        Episode(
            ts="2026-06-01T22:00:00+00:00",
            date="2026-06-01",
            kind="decision",
            summary="ship phase 4",
            source_turn="conversation-260601.md#turn-12",
        ),
    ]
    facts_by_idx = {
        0: [
            Fact(
                subject="phase 4",
                claim="extracted to episodes.jsonl + facts.db",
                confidence=0.85,
                source_turn="conversation-260601.md#turn-12",
            )
        ]
    }
    episode_ids, fact_ids = record_extraction("anne", episodes, facts_by_idx)
    assert episode_ids == [0]
    assert len(fact_ids) == 1
    assert episodes_path("anne").exists()
    timeline = list(iter_episodes("anne"))
    assert len(timeline) == 1
    facts_rows = query_facts("anne", subject="phase 4")
    assert len(facts_rows) == 1
    assert facts_rows[0]["source_turn"] == "conversation-260601.md#turn-12"


def test_record_extraction_skips_out_of_range_facts(
    abyss_home: Path, caplog: pytest.LogCaptureFixture
) -> None:
    from abyss.episodes import Episode, Fact, record_extraction

    episodes = [
        Episode(
            ts="2026-06-01T22:00:00+00:00",
            date="2026-06-01",
            kind="fact",
            summary="only one episode",
        ),
    ]
    facts_by_idx = {
        0: [Fact(subject="ok", claim="claim", confidence=0.5)],
        5: [Fact(subject="bad", claim="claim", confidence=0.5)],
    }
    with caplog.at_level("WARNING"):
        _, fact_ids = record_extraction("anne", episodes, facts_by_idx)
    assert len(fact_ids) == 1
    assert any("out-of-range episode" in r.message for r in caplog.records)


def test_record_extraction_empty_inputs_noop(abyss_home: Path) -> None:
    from abyss.episodes import episodes_path, facts_db_path, record_extraction

    episode_ids, fact_ids = record_extraction("anne", [], {})
    assert episode_ids == []
    assert fact_ids == []
    # Neither file should exist when there's nothing to write.
    assert not episodes_path("anne").exists()
    assert not facts_db_path("anne").exists()
