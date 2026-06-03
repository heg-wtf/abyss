"""Unit tests for ``abyss.skill_proposals`` (Phase 5 storage + approve flow)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml


@pytest.fixture
def abyss_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ABYSS_HOME", str(tmp_path))
    (tmp_path / "bots" / "anne").mkdir(parents=True)
    return tmp_path


# --- Dataclass validation -----------------------------------------------------


def test_proposal_generates_id_and_timestamp() -> None:
    from abyss.skill_proposals import Proposal

    p = Proposal(bot="anne", candidate_url="https://github.com/x/y")
    assert p.id
    assert p.proposed_at
    assert p.status == "pending"


def test_proposal_rejects_empty_url() -> None:
    from abyss.skill_proposals import Proposal

    with pytest.raises(ValueError, match="candidate_url"):
        Proposal(bot="anne", candidate_url="  ")


def test_proposal_rejects_bad_status() -> None:
    from abyss.skill_proposals import Proposal

    with pytest.raises(ValueError, match="status"):
        Proposal(bot="anne", candidate_url="https://x", status="lol")


# --- add_proposal -------------------------------------------------------------


def test_add_proposal_creates_yaml_file(abyss_home: Path) -> None:
    from abyss.skill_proposals import add_proposal, proposals_path

    p = add_proposal("anne", "https://github.com/owner/repo", "needs stripe fetcher")
    assert proposals_path("anne").exists()
    contents = yaml.safe_load(proposals_path("anne").read_text())
    assert isinstance(contents, list) and len(contents) == 1
    assert contents[0]["candidate_url"] == "https://github.com/owner/repo"
    assert contents[0]["reasons"] == ["needs stripe fetcher"]
    assert contents[0]["id"] == p.id


def test_add_proposal_dedups_pending_url(abyss_home: Path) -> None:
    from abyss.skill_proposals import add_proposal, list_proposals

    first = add_proposal("anne", "https://github.com/x/y", "first reason")
    second = add_proposal("anne", "https://github.com/x/y", "second reason")
    assert first.id == second.id
    rows = list_proposals("anne")
    assert len(rows) == 1
    assert rows[0].reasons == ["first reason", "second reason"]


def test_add_proposal_skips_duplicate_reasons(abyss_home: Path) -> None:
    from abyss.skill_proposals import add_proposal, list_proposals

    add_proposal("anne", "https://github.com/x/y", "same reason")
    add_proposal("anne", "https://github.com/x/y", "same reason")
    rows = list_proposals("anne")
    assert rows[0].reasons == ["same reason"]


def test_add_proposal_does_not_revive_rejected(abyss_home: Path) -> None:
    from abyss.skill_proposals import add_proposal, list_proposals, update_status

    proposal = add_proposal("anne", "https://github.com/x/y", "r1")
    update_status("anne", proposal.id, "rejected")
    returned = add_proposal("anne", "https://github.com/x/y", "r2")
    assert returned.status == "rejected"
    rows = list_proposals("anne", status="pending")
    assert rows == []


def test_add_proposal_does_not_duplicate_approved(abyss_home: Path) -> None:
    from abyss.skill_proposals import add_proposal, list_proposals, update_status

    proposal = add_proposal("anne", "https://github.com/x/y", "r")
    update_status("anne", proposal.id, "approved")
    returned = add_proposal("anne", "https://github.com/x/y", "again")
    assert returned.status == "approved"
    assert len(list_proposals("anne")) == 1


def test_add_proposal_rejects_empty_url(abyss_home: Path) -> None:
    from abyss.skill_proposals import add_proposal

    with pytest.raises(ValueError, match="candidate_url"):
        add_proposal("anne", "   ", "reason")


def test_add_proposal_merges_alternative_urls(abyss_home: Path) -> None:
    from abyss.skill_proposals import add_proposal, list_proposals

    add_proposal(
        "anne",
        "https://github.com/x/y",
        "r1",
        alternative_urls=["https://github.com/alt/one"],
    )
    add_proposal(
        "anne",
        "https://github.com/x/y",
        "r2",
        alternative_urls=["https://github.com/alt/two", "https://github.com/alt/one"],
    )
    row = list_proposals("anne")[0]
    assert row.alternative_urls == [
        "https://github.com/alt/one",
        "https://github.com/alt/two",
    ]


# --- list / get / update_status ----------------------------------------------


def test_list_proposals_filters_by_status(abyss_home: Path) -> None:
    from abyss.skill_proposals import add_proposal, list_proposals, update_status

    a = add_proposal("anne", "https://github.com/a/a", "r")
    b = add_proposal("anne", "https://github.com/b/b", "r")
    update_status("anne", a.id, "approved")
    pending = list_proposals("anne", status="pending")
    assert [p.id for p in pending] == [b.id]


def test_list_proposals_returns_empty_when_file_missing(abyss_home: Path) -> None:
    from abyss.skill_proposals import list_proposals

    assert list_proposals("anne") == []


def test_list_proposals_skips_malformed_rows(abyss_home: Path) -> None:
    from abyss.skill_proposals import list_proposals, proposals_path

    path = proposals_path("anne")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            [
                {"bot": "anne", "candidate_url": "", "id": "bad"},  # empty url
                {"bot": "anne", "candidate_url": "https://github.com/x/y", "id": "ok"},
            ]
        ),
        encoding="utf-8",
    )
    rows = list_proposals("anne")
    assert [r.id for r in rows] == ["ok"]


def test_list_proposals_handles_malformed_yaml(abyss_home: Path) -> None:
    from abyss.skill_proposals import list_proposals, proposals_path

    path = proposals_path("anne")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not: a: list:", encoding="utf-8")
    assert list_proposals("anne") == []


def test_update_status_unknown_id_returns_none(abyss_home: Path) -> None:
    from abyss.skill_proposals import update_status

    assert update_status("anne", "ghost-id", "approved") is None


def test_update_status_rejects_invalid_status(abyss_home: Path) -> None:
    from abyss.skill_proposals import add_proposal, update_status

    p = add_proposal("anne", "https://github.com/x/y", "r")
    with pytest.raises(ValueError, match="status"):
        update_status("anne", p.id, "ghosted")


def test_get_proposal_round_trip(abyss_home: Path) -> None:
    from abyss.skill_proposals import add_proposal, get_proposal

    p = add_proposal("anne", "https://github.com/x/y", "r")
    fetched = get_proposal("anne", p.id)
    assert fetched is not None and fetched.id == p.id


# --- approve flow -------------------------------------------------------------


def test_approve_runs_import_and_attach(abyss_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from abyss import skill_proposals
    from abyss.skill_proposals import add_proposal, approve

    proposal = add_proposal("anne", "https://github.com/owner/cool-skill", "r")

    import_calls: list[str] = []
    attach_calls: list[tuple[str, str]] = []

    def fake_import(url: str, name: str | None = None) -> Path:
        import_calls.append(url)
        path = abyss_home / "skills" / "cool-skill"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def fake_attach(bot: str, skill: str) -> None:
        attach_calls.append((bot, skill))

    monkeypatch.setattr("abyss.skill.import_skill_from_github", fake_import)
    monkeypatch.setattr("abyss.skill.attach_skill_to_bot", fake_attach)

    result = approve("anne", proposal.id)
    assert result["ok"] is True
    assert result["skill_name"] == "cool-skill"
    assert import_calls == ["https://github.com/owner/cool-skill"]
    assert attach_calls == [("anne", "cool-skill")]
    assert skill_proposals.get_proposal("anne", proposal.id).status == "approved"


def test_approve_unknown_proposal(abyss_home: Path) -> None:
    from abyss.skill_proposals import approve

    result = approve("anne", "ghost-id")
    assert result == {"ok": False, "error": "proposal not found", "stage": "lookup"}


def test_approve_already_approved_is_noop(
    abyss_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from abyss.skill_proposals import add_proposal, approve, update_status

    p = add_proposal("anne", "https://github.com/x/y", "r")
    update_status("anne", p.id, "approved")
    # Import should not be called for a noop.
    monkeypatch.setattr(
        "abyss.skill.import_skill_from_github",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("must not import")),
    )
    result = approve("anne", p.id)
    assert result["ok"] is True
    assert result.get("noop") is True


def test_approve_rejected_blocks_import(abyss_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from abyss.skill_proposals import add_proposal, approve, update_status

    p = add_proposal("anne", "https://github.com/x/y", "r")
    update_status("anne", p.id, "rejected")
    monkeypatch.setattr(
        "abyss.skill.import_skill_from_github",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("must not import")),
    )
    result = approve("anne", p.id)
    assert result["ok"] is False
    assert "rejected" in result["error"]


def test_approve_import_failure_returns_structured_error(
    abyss_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from abyss.skill_proposals import add_proposal, approve, get_proposal

    p = add_proposal("anne", "https://github.com/x/y", "r")

    def fake_import(*_a: Any, **_k: Any) -> Path:
        raise RuntimeError("git clone exploded")

    monkeypatch.setattr("abyss.skill.import_skill_from_github", fake_import)
    result = approve("anne", p.id)
    assert result == {"ok": False, "error": "git clone exploded", "stage": "import"}
    # Status stays pending so the user can retry after fixing the URL.
    assert get_proposal("anne", p.id).status == "pending"


def test_approve_attach_failure_returns_structured_error(
    abyss_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from abyss.skill_proposals import add_proposal, approve, get_proposal

    p = add_proposal("anne", "https://github.com/x/y", "r")

    def fake_import(*_a: Any, **_k: Any) -> Path:
        path = abyss_home / "skills" / "x"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def fake_attach(*_a: Any, **_k: Any) -> None:
        raise RuntimeError("bot.yaml write failed")

    monkeypatch.setattr("abyss.skill.import_skill_from_github", fake_import)
    monkeypatch.setattr("abyss.skill.attach_skill_to_bot", fake_attach)
    result = approve("anne", p.id)
    assert result["ok"] is False
    assert result["stage"] == "attach"
    assert get_proposal("anne", p.id).status == "pending"


# --- reject -------------------------------------------------------------------


def test_reject_sets_status(abyss_home: Path) -> None:
    from abyss.skill_proposals import add_proposal, get_proposal, reject

    p = add_proposal("anne", "https://github.com/x/y", "r")
    updated = reject("anne", p.id)
    assert updated is not None and updated.status == "rejected"
    assert get_proposal("anne", p.id).status == "rejected"
    assert get_proposal("anne", p.id).resolved_at is not None


def test_reject_unknown_id_returns_none(abyss_home: Path) -> None:
    from abyss.skill_proposals import reject

    assert reject("anne", "ghost") is None
