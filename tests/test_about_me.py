"""Unit tests for ``abyss.about_me``."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def abyss_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ABYSS_HOME", str(tmp_path))
    return tmp_path


def test_ensure_scaffold_creates_files(abyss_home: Path) -> None:
    from abyss.about_me import (
        ABOUT_ME_CATEGORIES,
        ensure_about_me_scaffold,
        index_file,
    )

    directory = ensure_about_me_scaffold()
    assert directory == abyss_home / "ABOUT_ME"
    for category in ABOUT_ME_CATEGORIES:
        assert (directory / f"{category}.md").exists()
    assert index_file().exists()


def test_ensure_scaffold_is_idempotent(abyss_home: Path) -> None:
    from abyss.about_me import ensure_about_me_scaffold

    ensure_about_me_scaffold()
    identity = abyss_home / "ABOUT_ME" / "identity.md"
    identity.write_text("# Identity\n\ncustom content\n")
    ensure_about_me_scaffold()
    assert identity.read_text() == "# Identity\n\ncustom content\n"


def test_upsert_and_load_entry(abyss_home: Path) -> None:
    from abyss.about_me import AboutEntry, load_category, upsert_entry

    upsert_entry(
        "identity",
        AboutEntry(key="name", value="ash84"),
    )
    upsert_entry(
        "identity",
        AboutEntry(key="email", value="ash84@payhere.in"),
    )

    entries = load_category("identity")
    assert [entry.key for entry in entries] == ["name", "email"]
    assert entries[0].value == "ash84"
    assert entries[0].status == "confirmed"
    assert entries[0].added  # auto-stamped
    assert entries[0].last_confirmed


def test_upsert_replaces_existing_key(abyss_home: Path) -> None:
    from abyss.about_me import AboutEntry, load_category, upsert_entry

    upsert_entry("identity", AboutEntry(key="name", value="old"))
    upsert_entry("identity", AboutEntry(key="name", value="new"))

    entries = load_category("identity")
    assert len(entries) == 1
    assert entries[0].value == "new"


def test_upsert_rejects_invalid_category(abyss_home: Path) -> None:
    from abyss.about_me import AboutEntry, upsert_entry

    with pytest.raises(ValueError):
        upsert_entry("not_a_category", AboutEntry(key="x", value="y"))


def test_upsert_rejects_empty_key(abyss_home: Path) -> None:
    from abyss.about_me import AboutEntry, upsert_entry

    with pytest.raises(ValueError):
        upsert_entry("identity", AboutEntry(key="", value="y"))


def test_upsert_rejects_invalid_status_or_confidence(abyss_home: Path) -> None:
    from abyss.about_me import AboutEntry, upsert_entry

    with pytest.raises(ValueError):
        upsert_entry("identity", AboutEntry(key="x", status="weird"))
    with pytest.raises(ValueError):
        upsert_entry("identity", AboutEntry(key="x", confidence="extreme"))


def test_round_trip_preserves_body(abyss_home: Path) -> None:
    from abyss.about_me import AboutEntry, load_category, upsert_entry

    body = "본명 사용자명. 모든 봇이 호칭으로 사용."
    upsert_entry(
        "identity",
        AboutEntry(key="name", value="ash84", body=body),
    )
    entries = load_category("identity")
    assert entries[0].body == body


def test_load_category_returns_empty_for_missing(abyss_home: Path) -> None:
    from abyss.about_me import load_category

    assert load_category("identity") == []


def test_load_category_skips_malformed_blocks(abyss_home: Path, caplog) -> None:
    from abyss.about_me import about_me_directory, ensure_about_me_scaffold, load_category

    ensure_about_me_scaffold()
    path = about_me_directory() / "identity.md"
    path.write_text(
        "# Identity\n\n"
        "---\nkey: name\nvalue: ash84\n---\n\nbody one\n\n"
        "---\nnot: yaml: oops\n---\n\n"  # invalid yaml
        "---\nno_key_here: true\n---\n\n"  # missing key
        "---\nkey: email\nvalue: x@y\n---\n"
    )
    with caplog.at_level("WARNING"):
        entries = load_category("identity")
    keys = [entry.key for entry in entries]
    # The invalid-yaml block is dropped entirely; the no-key block is
    # warned about and skipped; valid blocks survive.
    assert "name" in keys
    assert "email" in keys
    assert all(key != "" for key in keys)


def test_list_entries_all_or_one(abyss_home: Path) -> None:
    from abyss.about_me import AboutEntry, list_entries, upsert_entry

    upsert_entry("identity", AboutEntry(key="name", value="ash84"))
    upsert_entry("preferences", AboutEntry(key="lang", value="ko"))

    all_entries = list_entries()
    assert set(all_entries.keys()) >= {"identity", "preferences"}
    assert [entry.key for entry in all_entries["identity"]] == ["name"]
    assert [entry.key for entry in all_entries["preferences"]] == ["lang"]

    only_identity = list_entries("identity")
    assert list(only_identity.keys()) == ["identity"]


def test_rebuild_index_summarizes_confirmed_only(abyss_home: Path) -> None:
    from abyss.about_me import AboutEntry, load_index, rebuild_index, upsert_entry

    upsert_entry("identity", AboutEntry(key="name", value="ash84"))
    upsert_entry(
        "identity",
        AboutEntry(key="secret", value="hush", status="propose"),
    )
    rebuild_index()
    content = load_index()
    assert "name=ash84" in content
    # Propose status excluded from the index summary.
    assert "secret" not in content
    # Other categories are listed as empty.
    assert "health: _(empty)_" in content


def test_rebuild_index_truncates_long_values(abyss_home: Path) -> None:
    from abyss.about_me import AboutEntry, load_index, upsert_entry

    long_value = "x" * 200
    upsert_entry("values", AboutEntry(key="manifesto", value=long_value))
    content = load_index()
    assert "manifesto=" in content
    # 60-char cap + ellipsis
    assert "x" * 60 in content
    assert "…" in content


def test_has_any_entries(abyss_home: Path) -> None:
    from abyss.about_me import AboutEntry, has_any_entries, upsert_entry

    assert has_any_entries() is False
    upsert_entry("identity", AboutEntry(key="name", value="ash84"))
    assert has_any_entries() is True


def test_about_me_file_validates_category(abyss_home: Path) -> None:
    from abyss.about_me import about_me_file

    with pytest.raises(ValueError):
        about_me_file("../etc/passwd")


# ---------------------------------------------------------------------------
# Propose / approve / reject state machine
# ---------------------------------------------------------------------------


def test_propose_creates_new_entry(abyss_home: Path) -> None:
    from abyss.about_me import load_category, propose_entry

    result = propose_entry("identity", "name", "ash84")
    assert result.action == "created"
    assert result.propose_count == 1

    entries = load_category("identity")
    assert len(entries) == 1
    assert entries[0].key == "name"
    assert entries[0].status == "propose"
    assert entries[0].extra.get("propose_count") == 1


def test_propose_same_value_twice_auto_confirms(abyss_home: Path) -> None:
    from abyss.about_me import load_category, propose_entry

    first = propose_entry("identity", "name", "ash84")
    assert first.action == "created"
    second = propose_entry("identity", "name", "ash84")
    assert second.action == "auto_confirmed"
    assert second.propose_count >= 2

    entries = load_category("identity")
    assert len(entries) == 1
    entry = entries[0]
    assert entry.status == "confirmed"
    assert entry.last_confirmed != ""
    # propose_count is dropped once promoted
    assert "propose_count" not in entry.extra


def test_propose_different_value_while_pending_replaces(abyss_home: Path) -> None:
    from abyss.about_me import load_category, propose_entry

    propose_entry("identity", "city", "Seoul")
    result = propose_entry("identity", "city", "Busan")
    assert result.action == "updated"

    entries = load_category("identity")
    assert len(entries) == 1
    assert entries[0].value == "Busan"
    assert entries[0].status == "propose"
    assert entries[0].extra.get("propose_count") == 1


def test_propose_same_as_confirmed_only_bumps_last_confirmed(abyss_home: Path) -> None:
    from abyss.about_me import AboutEntry, load_category, propose_entry, upsert_entry

    upsert_entry(
        "identity",
        AboutEntry(key="name", value="ash84", last_confirmed="2020-01-01"),
    )
    result = propose_entry("identity", "name", "ash84")
    assert result.action == "already_confirmed"

    entries = load_category("identity")
    assert len(entries) == 1
    assert entries[0].last_confirmed != "2020-01-01"
    assert entries[0].status == "confirmed"


def test_propose_conflict_against_confirmed_adds_propose(abyss_home: Path) -> None:
    from abyss.about_me import AboutEntry, load_category, propose_entry, upsert_entry

    upsert_entry("identity", AboutEntry(key="city", value="Seoul"))
    result = propose_entry("identity", "city", "Busan")
    assert result.action == "conflict"
    assert result.conflict_with == "city"
    assert result.key.startswith("city__conflict_")

    entries = load_category("identity")
    assert len(entries) == 2
    confirmed = next(entry for entry in entries if entry.status == "confirmed")
    pending = next(entry for entry in entries if entry.status == "propose")
    assert confirmed.value == "Seoul"
    assert pending.value == "Busan"
    assert pending.extra.get("conflicts_with") == "city"


def test_propose_multiple_conflicts_get_unique_suffix(abyss_home: Path) -> None:
    from abyss.about_me import AboutEntry, load_category, propose_entry, upsert_entry

    upsert_entry("identity", AboutEntry(key="city", value="Seoul"))
    propose_entry("identity", "city", "Busan")
    propose_entry("identity", "city", "Daejeon")

    entries = load_category("identity")
    keys = sorted(entry.key for entry in entries)
    assert keys == ["city", "city__conflict_1", "city__conflict_2"]


def test_approve_entry_promotes_propose(abyss_home: Path) -> None:
    from abyss.about_me import approve_entry, load_category, propose_entry

    propose_entry("identity", "name", "ash84")
    assert approve_entry("identity", "name") is True

    entries = load_category("identity")
    assert entries[0].status == "confirmed"
    assert entries[0].last_confirmed != ""
    assert "propose_count" not in entries[0].extra


def test_approve_entry_returns_false_for_unknown(abyss_home: Path) -> None:
    from abyss.about_me import approve_entry

    assert approve_entry("identity", "ghost") is False


def test_reject_entry_removes_propose(abyss_home: Path) -> None:
    from abyss.about_me import load_category, propose_entry, reject_entry

    propose_entry("identity", "name", "ash84")
    assert reject_entry("identity", "name") is True
    assert load_category("identity") == []


def test_update_entry_patches_value(abyss_home: Path) -> None:
    from abyss.about_me import AboutEntry, load_category, update_entry, upsert_entry

    upsert_entry("identity", AboutEntry(key="job", value="engineer"))
    assert update_entry("identity", "job", value="cto") is True

    entries = load_category("identity")
    assert entries[0].value == "cto"


def test_update_entry_rejects_invalid_confidence(abyss_home: Path) -> None:
    from abyss.about_me import update_entry

    with pytest.raises(ValueError):
        update_entry("identity", "x", confidence="off-the-charts")


def test_count_proposals_and_category_counts(abyss_home: Path) -> None:
    from abyss.about_me import (
        AboutEntry,
        category_counts,
        count_proposals,
        propose_entry,
        upsert_entry,
    )

    upsert_entry("identity", AboutEntry(key="name", value="ash84"))
    propose_entry("preferences", "lang", "ko")
    propose_entry("preferences", "tone", "terse")

    assert count_proposals() == 2
    counts = category_counts()
    assert counts["identity"] == {"confirmed": 1, "propose": 0, "total": 1}
    assert counts["preferences"] == {"confirmed": 0, "propose": 2, "total": 2}
