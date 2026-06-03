"""Unit tests for ``abyss.persona_drift`` (Phase 8.0 storage + drift)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml


@pytest.fixture
def abyss_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ABYSS_HOME", str(tmp_path))
    (tmp_path / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "bots": [{"name": "anne", "path": str(tmp_path / "bots" / "anne")}],
                "settings": {"language": "english", "timezone": "UTC"},
            }
        )
    )
    bot_dir = tmp_path / "bots" / "anne"
    bot_dir.mkdir(parents=True)
    bot_dir.joinpath("bot.yaml").write_text(
        yaml.safe_dump({"display_name": "Anne", "personality": "p", "role": "r"})
    )
    return tmp_path


# --- Section parsing ----------------------------------------------------------


def test_section_sizes_preamble_only() -> None:
    from abyss.persona_drift import PREAMBLE_KEY, _section_sizes

    text = "# Anne\nintro text without any ## section"
    sizes = _section_sizes(text)
    assert sizes == {PREAMBLE_KEY: len(text.encode("utf-8"))}


def test_section_sizes_parses_headers() -> None:
    from abyss.persona_drift import PREAMBLE_KEY, _section_sizes

    text = "# Anne\nintro\n## Personality\ncalm\n## Role\nhelper\n"
    sizes = _section_sizes(text)
    assert PREAMBLE_KEY in sizes
    assert "Personality" in sizes
    assert "Role" in sizes
    assert sum(sizes.values()) == len(text.encode("utf-8"))


def test_section_sizes_emoji_header_preserved() -> None:
    from abyss.persona_drift import _section_sizes

    text = "## 🪞 Self Reflection\nbody\n## Goals\nmore body\n"
    sizes = _section_sizes(text)
    assert "🪞 Self Reflection" in sizes
    assert "Goals" in sizes


def test_section_sizes_duplicate_headers_summed() -> None:
    from abyss.persona_drift import _section_sizes

    text = "## A\nfirst\n## A\nsecond\n"
    sizes = _section_sizes(text)
    assert "A" in sizes
    assert sizes["A"] == len(text.encode("utf-8"))


def test_section_sizes_empty_text() -> None:
    from abyss.persona_drift import _section_sizes

    assert _section_sizes("") == {}


# --- Snapshot validation ------------------------------------------------------


def test_snapshot_rejects_invalid_event() -> None:
    from abyss.persona_drift import PersonaSnapshot

    with pytest.raises(ValueError, match="event"):
        PersonaSnapshot(
            ts="2026-06-03T00:00:00+00:00",
            hash="0" * 64,
            total_bytes=10,
            event="midnight",
        )


# --- take_snapshot ------------------------------------------------------------


def _fake_compose(monkeypatch, text: str) -> None:
    monkeypatch.setattr("abyss.persona_drift._compose_for_bot", lambda _bot: text)


def test_take_snapshot_appends_one_line(abyss_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from abyss.persona_drift import snapshots_path, take_snapshot

    _fake_compose(monkeypatch, "# Anne\n## Personality\ncalm\n")
    snap = take_snapshot("anne")
    assert snap.event == "daily"
    lines = snapshots_path("anne").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1


def test_take_snapshot_records_hash_and_sizes(
    abyss_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from abyss.persona_drift import take_snapshot

    _fake_compose(
        monkeypatch,
        "# Anne\n## Personality\ncalm\n## Role\nhelper\n",
    )
    snap = take_snapshot("anne", event="manual")
    assert len(snap.hash) == 64
    assert snap.event == "manual"
    assert snap.total_bytes > 0
    assert "Personality" in snap.section_sizes
    assert sum(snap.section_sizes.values()) == snap.total_bytes


def test_iter_snapshots_orders_newest_first(
    abyss_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from abyss.persona_drift import iter_snapshots, take_snapshot

    _fake_compose(monkeypatch, "## A\nx\n")
    older = take_snapshot("anne")
    # Force a deterministic newer timestamp.
    monkeypatch.setattr("abyss.persona_drift._iso_now", lambda: "2099-01-01T00:00:00+00:00")
    newer = take_snapshot("anne")
    rows = list(iter_snapshots("anne"))
    assert rows[0].ts == newer.ts
    assert rows[-1].ts == older.ts


def test_iter_snapshots_skips_malformed_lines(abyss_home: Path) -> None:
    from abyss.persona_drift import iter_snapshots, snapshots_path

    path = snapshots_path("anne")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                '{"ts":"2026-06-01T00:00:00+00:00","hash":"x","total_bytes":1,'
                '"section_sizes":{"A":1},"event":"daily"}',
                "not even json",
                '{"ts":"2026-06-02","hash":"y","total_bytes":2,'
                '"section_sizes":{},"event":"midnight"}',  # bad event
            ]
        ),
        encoding="utf-8",
    )
    rows = list(iter_snapshots("anne"))
    assert len(rows) == 1


def test_iter_snapshots_missing_file_returns_nothing(abyss_home: Path) -> None:
    from abyss.persona_drift import iter_snapshots

    assert list(iter_snapshots("anne")) == []


def test_iter_snapshots_respects_limit(abyss_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from abyss.persona_drift import iter_snapshots, take_snapshot

    _fake_compose(monkeypatch, "## A\nx\n")
    for index in range(3):
        monkeypatch.setattr(
            "abyss.persona_drift._iso_now",
            lambda i=index: f"2026-06-0{1 + i}T00:00:00+00:00",
        )
        take_snapshot("anne")
    rows = list(iter_snapshots("anne", limit=2))
    assert len(rows) == 2


# --- compute_drift ------------------------------------------------------------


def test_compute_drift_none_when_no_snapshots(abyss_home: Path) -> None:
    from abyss.persona_drift import compute_drift

    assert compute_drift("anne") is None


def test_compute_drift_none_with_only_one_snapshot(
    abyss_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from abyss.persona_drift import compute_drift, take_snapshot

    _fake_compose(monkeypatch, "## A\nx\n")
    take_snapshot("anne")
    assert compute_drift("anne") is None


def test_compute_drift_detects_shrinkage(abyss_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from abyss.persona_drift import compute_drift, take_snapshot

    # Baseline snapshot — large.
    monkeypatch.setattr(
        "abyss.persona_drift._iso_now",
        lambda: (datetime.now(timezone.utc) - timedelta(days=10)).isoformat(timespec="seconds"),
    )
    _fake_compose(
        monkeypatch,
        "## Personality\n" + ("calm " * 100) + "\n## Role\nhelper\n",
    )
    take_snapshot("anne")
    # Latest snapshot — much smaller (simulates compact wiping personality).
    monkeypatch.setattr(
        "abyss.persona_drift._iso_now",
        lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    _fake_compose(monkeypatch, "## Personality\ncalm\n## Role\nhelper\n")
    take_snapshot("anne")
    report = compute_drift("anne", window_days=7)
    assert report is not None
    assert report.total_delta_bytes < 0
    assert report.shrinkage_alert is True
    assert report.section_deltas["Personality"] < 0


def test_compute_drift_no_shrinkage_when_small(
    abyss_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from abyss.persona_drift import compute_drift, take_snapshot

    monkeypatch.setattr(
        "abyss.persona_drift._iso_now",
        lambda: (datetime.now(timezone.utc) - timedelta(days=10)).isoformat(timespec="seconds"),
    )
    _fake_compose(monkeypatch, "## A\n" + ("body " * 100) + "\n")
    take_snapshot("anne")
    monkeypatch.setattr(
        "abyss.persona_drift._iso_now",
        lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    # Lose just 1%, well below threshold.
    _fake_compose(monkeypatch, "## A\n" + ("body " * 99) + "\n")
    take_snapshot("anne")
    report = compute_drift("anne", window_days=7)
    assert report is not None
    assert report.shrinkage_alert is False


def test_compute_drift_falls_back_to_oldest_when_no_window_match(
    abyss_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two snapshots both inside the window → still produce a report
    using the older snapshot as baseline."""
    from abyss.persona_drift import compute_drift, take_snapshot

    _fake_compose(monkeypatch, "## A\nx\n")
    monkeypatch.setattr(
        "abyss.persona_drift._iso_now",
        lambda: "2026-06-02T00:00:00+00:00",
    )
    take_snapshot("anne")
    monkeypatch.setattr(
        "abyss.persona_drift._iso_now",
        lambda: "2026-06-03T00:00:00+00:00",
    )
    _fake_compose(monkeypatch, "## A\ny\n")
    take_snapshot("anne")
    report = compute_drift("anne", window_days=7)
    assert report is not None
    assert report.baseline_ts == "2026-06-02T00:00:00+00:00"


def test_compare_snapshots_direct() -> None:
    from abyss.persona_drift import PersonaSnapshot, compare_snapshots

    earlier = PersonaSnapshot(
        ts="2026-06-01",
        hash="a",
        total_bytes=1000,
        section_sizes={"A": 600, "B": 400},
    )
    later = PersonaSnapshot(
        ts="2026-06-02",
        hash="b",
        total_bytes=800,
        section_sizes={"A": 500, "B": 300},
    )
    report = compare_snapshots(earlier, later)
    assert report.section_deltas == {"A": -100, "B": -100}
    assert report.total_delta_bytes == -200
    assert report.shrinkage_alert is True


# --- Digest prompt ------------------------------------------------------------


def test_build_drift_digest_prompt_no_history(abyss_home: Path) -> None:
    from abyss.persona_drift import build_drift_digest_prompt

    prompt = build_drift_digest_prompt("anne")
    assert "not yet enough snapshot history" in prompt


def test_build_drift_digest_prompt_includes_deltas(
    abyss_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from abyss.persona_drift import build_drift_digest_prompt, take_snapshot

    monkeypatch.setattr(
        "abyss.persona_drift._iso_now",
        lambda: "2026-05-27T00:00:00+00:00",
    )
    _fake_compose(monkeypatch, "## A\nbig\n## B\nbig\n")
    take_snapshot("anne")
    monkeypatch.setattr(
        "abyss.persona_drift._iso_now",
        lambda: "2026-06-03T00:00:00+00:00",
    )
    _fake_compose(monkeypatch, "## A\nsmall\n## B\nbig\n")
    take_snapshot("anne")
    prompt = build_drift_digest_prompt("anne", window_days=7)
    assert "Persona drift digest" in prompt
    assert "A:" in prompt
    assert "Korean" in prompt
