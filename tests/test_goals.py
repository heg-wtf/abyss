"""Unit tests for ``abyss.goals`` (Phase 6 storage + digest)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml


@pytest.fixture
def abyss_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ABYSS_HOME", str(tmp_path))
    (tmp_path / "bots" / "anne").mkdir(parents=True)
    return tmp_path


# --- Dataclass validation -----------------------------------------------------


def test_goal_requires_id_and_title() -> None:
    from abyss.goals import Goal

    with pytest.raises(ValueError, match="id"):
        Goal(id="", title="anything")
    with pytest.raises(ValueError, match="title"):
        Goal(id="ok", title="   ")


def test_goal_rejects_invalid_status() -> None:
    from abyss.goals import Goal

    with pytest.raises(ValueError, match="status"):
        Goal(id="x", title="t", status="wishful")


def test_slugify_strips_special_chars() -> None:
    from abyss.goals import slugify

    assert slugify("Ship the Blog launcher! 🚀") == "ship-the-blog-launcher"
    assert slugify("") == "goal"


# --- add_goal -----------------------------------------------------------------


def test_add_goal_writes_yaml(abyss_home: Path) -> None:
    from abyss.goals import add_goal, goals_path

    goal = add_goal("anne", "Ship blog launcher", kpi="PR merged", target="2026-06-15")
    assert goal.id == "ship-blog-launcher"
    contents = yaml.safe_load(goals_path("anne").read_text())
    assert isinstance(contents, list) and len(contents) == 1
    assert contents[0]["kpi"] == "PR merged"
    assert contents[0]["target"] == "2026-06-15"


def test_add_goal_rejects_duplicate_id(abyss_home: Path) -> None:
    from abyss.goals import add_goal

    add_goal("anne", "Ship blog launcher")
    with pytest.raises(ValueError, match="already exists"):
        add_goal("anne", "Ship blog launcher")


def test_add_goal_accepts_explicit_id(abyss_home: Path) -> None:
    from abyss.goals import add_goal

    goal = add_goal("anne", "Anything", goal_id="custom-id")
    assert goal.id == "custom-id"


# --- list_goals + filter ------------------------------------------------------


def test_list_goals_filters_by_status(abyss_home: Path) -> None:
    from abyss.goals import add_goal, list_goals, mark_done

    add_goal("anne", "Goal A")
    b = add_goal("anne", "Goal B")
    mark_done("anne", b.id)
    active = list_goals("anne", status="active")
    assert [g.title for g in active] == ["Goal A"]
    done = list_goals("anne", status="done")
    assert [g.title for g in done] == ["Goal B"]


def test_list_goals_returns_empty_when_file_missing(abyss_home: Path) -> None:
    from abyss.goals import list_goals

    assert list_goals("anne") == []


def test_list_goals_skips_malformed_rows(abyss_home: Path) -> None:
    from abyss.goals import goals_path, list_goals

    path = goals_path("anne")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            [
                {"id": "", "title": "bad id"},  # empty id
                {"id": "ok", "title": "good"},
            ]
        ),
        encoding="utf-8",
    )
    rows = list_goals("anne")
    assert [g.id for g in rows] == ["ok"]


def test_list_goals_handles_malformed_yaml(abyss_home: Path) -> None:
    from abyss.goals import goals_path, list_goals

    path = goals_path("anne")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("nope: nope: nope:", encoding="utf-8")
    assert list_goals("anne") == []


# --- update / delete / lifecycle ---------------------------------------------


def test_update_goal_changes_fields(abyss_home: Path) -> None:
    from abyss.goals import add_goal, get_goal, update_goal

    g = add_goal("anne", "Old", kpi="x")
    updated = update_goal("anne", g.id, title="New", kpi="y")
    assert updated.title == "New"
    assert get_goal("anne", g.id).kpi == "y"


def test_update_goal_rejects_blank_title(abyss_home: Path) -> None:
    from abyss.goals import add_goal, update_goal

    g = add_goal("anne", "Old")
    with pytest.raises(ValueError, match="title"):
        update_goal("anne", g.id, title="  ")


def test_update_goal_rejects_invalid_status(abyss_home: Path) -> None:
    from abyss.goals import add_goal, update_goal

    g = add_goal("anne", "Old")
    with pytest.raises(ValueError, match="status"):
        update_goal("anne", g.id, status="wishful")


def test_update_goal_unknown_id_returns_none(abyss_home: Path) -> None:
    from abyss.goals import update_goal

    assert update_goal("anne", "ghost", title="x") is None


def test_delete_goal_removes_row(abyss_home: Path) -> None:
    from abyss.goals import add_goal, delete_goal, list_goals

    a = add_goal("anne", "A")
    add_goal("anne", "B")
    assert delete_goal("anne", a.id) is True
    assert [g.title for g in list_goals("anne")] == ["B"]


def test_delete_goal_unknown_id_returns_false(abyss_home: Path) -> None:
    from abyss.goals import delete_goal

    assert delete_goal("anne", "ghost") is False


def test_mark_done_and_archived(abyss_home: Path) -> None:
    from abyss.goals import add_goal, get_goal, mark_archived, mark_done

    g = add_goal("anne", "G")
    mark_done("anne", g.id)
    assert get_goal("anne", g.id).status == "done"
    mark_archived("anne", g.id)
    assert get_goal("anne", g.id).status == "archived"


# --- record_progress ----------------------------------------------------------


def test_record_progress_appends_to_timeline(abyss_home: Path) -> None:
    from abyss.goals import add_goal, get_goal, record_progress

    g = add_goal("anne", "Ship")
    record_progress("anne", g.id, "drafted plan")
    record_progress("anne", g.id, "addressed review", value=1)
    timeline = get_goal("anne", g.id).progress
    assert [p.note for p in timeline] == ["drafted plan", "addressed review"]
    assert timeline[1].value == 1


def test_record_progress_unknown_goal_returns_none(abyss_home: Path) -> None:
    from abyss.goals import record_progress

    assert record_progress("anne", "ghost", "note") is None


def test_record_progress_rejects_empty_note(abyss_home: Path) -> None:
    from abyss.goals import add_goal, record_progress

    g = add_goal("anne", "G")
    with pytest.raises(ValueError, match="note"):
        record_progress("anne", g.id, "   ")


def test_record_progress_omits_value_when_none(abyss_home: Path) -> None:
    """``value=None`` should not appear in the yaml — keeps the file clean."""
    from abyss.goals import add_goal, goals_path, record_progress

    g = add_goal("anne", "G")
    record_progress("anne", g.id, "qualitative note")
    rows = yaml.safe_load(goals_path("anne").read_text())
    assert "value" not in rows[0]["progress"][0]


# --- digest -------------------------------------------------------------------


def test_build_digest_prompt_lists_recent_progress(abyss_home: Path) -> None:
    from abyss.goals import add_goal, build_digest_prompt, record_progress

    g = add_goal("anne", "Ship blog", kpi="PR merged")
    # Recent progress.
    record_progress("anne", g.id, "drafted plan")
    # Old progress (outside window).
    old_ts = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat(timespec="seconds")
    record_progress("anne", g.id, "ancient note", ts=old_ts)

    prompt = build_digest_prompt("anne", lookback_days=7)
    assert "Ship blog" in prompt
    assert "drafted plan" in prompt
    assert "ancient note" not in prompt


def test_build_digest_prompt_when_no_goals(abyss_home: Path) -> None:
    from abyss.goals import build_digest_prompt

    prompt = build_digest_prompt("anne")
    assert "no active goals" in prompt.lower()


def test_build_digest_prompt_marks_quiet_goals(abyss_home: Path) -> None:
    from abyss.goals import add_goal, build_digest_prompt

    add_goal("anne", "Silent goal")
    prompt = build_digest_prompt("anne", lookback_days=7)
    assert "quiet" in prompt.lower()
