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
