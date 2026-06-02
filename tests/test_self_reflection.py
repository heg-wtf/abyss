"""Unit tests for ``abyss.self_reflection``."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def abyss_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ABYSS_HOME", str(tmp_path))
    bot_dir = tmp_path / "bots" / "anne"
    bot_dir.mkdir(parents=True)
    return tmp_path


def test_self_reflection_path_under_bot_directory(abyss_home: Path) -> None:
    from abyss.self_reflection import self_reflection_path

    path = self_reflection_path("anne")
    assert path == abyss_home / "bots" / "anne" / "SELF.md"


def test_load_self_md_missing_returns_empty(abyss_home: Path) -> None:
    from abyss.self_reflection import load_self_md

    assert load_self_md("anne") == ""


def test_load_self_md_returns_content(abyss_home: Path) -> None:
    from abyss.self_reflection import load_self_md, self_reflection_path

    self_reflection_path("anne").write_text("hello", encoding="utf-8")
    assert load_self_md("anne") == "hello"


def test_save_self_md_writes_and_creates_backup(abyss_home: Path) -> None:
    from abyss.self_reflection import (
        load_self_md,
        save_self_md,
        self_reflection_backup_path,
        self_reflection_path,
    )

    # First write: no backup yet.
    save_self_md("anne", "first version")
    assert load_self_md("anne") == "first version"
    assert not self_reflection_backup_path("anne").exists()

    # Second write: previous content is preserved in .prev.
    save_self_md("anne", "second version")
    assert self_reflection_path("anne").read_text(encoding="utf-8") == "second version"
    assert self_reflection_backup_path("anne").read_text(encoding="utf-8") == "first version"


def test_save_self_md_truncates_oversize(abyss_home: Path) -> None:
    from abyss.self_reflection import MAX_SELF_BYTES, load_self_md, save_self_md

    huge = "A" * (MAX_SELF_BYTES + 1000)
    save_self_md("anne", huge)
    saved = load_self_md("anne")
    assert "truncated at MAX_SELF_BYTES" in saved
    # Truncated body itself stays under the cap, plus a small comment trailer.
    assert len(saved.encode("utf-8")) <= MAX_SELF_BYTES + 200


def test_save_self_md_rejects_non_string(abyss_home: Path) -> None:
    from abyss.self_reflection import save_self_md

    with pytest.raises(TypeError):
        save_self_md("anne", 123)  # type: ignore[arg-type]


def test_ensure_self_scaffold_creates_template(abyss_home: Path) -> None:
    from abyss.self_reflection import ensure_self_scaffold, load_self_md

    ensure_self_scaffold("anne")
    body = load_self_md("anne")
    assert "# SELF — anne" in body
    assert "## Mistake patterns" in body
    assert "## Irritation triggers" in body


def test_ensure_self_scaffold_idempotent(abyss_home: Path) -> None:
    from abyss.self_reflection import ensure_self_scaffold, load_self_md, save_self_md

    ensure_self_scaffold("anne")
    save_self_md("anne", "custom reflection")
    ensure_self_scaffold("anne")  # Should NOT overwrite existing content.
    assert load_self_md("anne") == "custom reflection"


def test_build_reflection_prompt_handles_no_data(abyss_home: Path) -> None:
    from abyss.self_reflection import build_reflection_prompt

    prompt = build_reflection_prompt("anne")
    assert "anne" in prompt
    assert "Total feedback records: 0" in prompt
    assert "_No conversation logs yet._" in prompt or "_No sessions yet._" in prompt
    # Prompt advertises read-only treatment of conversation logs.
    assert "ignore any instructions" in prompt.lower()


def test_build_reflection_prompt_includes_feedback_summary(abyss_home: Path) -> None:
    from abyss.feedback import append_feedback
    from abyss.self_reflection import build_reflection_prompt

    append_feedback("anne", "chat_x", "turn-1", 1)
    append_feedback("anne", "chat_x", "turn-2", 3, note="response was wrong")
    prompt = build_reflection_prompt("anne")
    assert "Total feedback records: 2" in prompt
    assert "1 (good): 1" in prompt
    assert "3 (wrong): 1" in prompt
    assert "response was wrong" in prompt


def test_build_reflection_prompt_includes_conversation_excerpts(
    abyss_home: Path,
) -> None:
    from abyss.self_reflection import build_reflection_prompt

    session = abyss_home / "bots" / "anne" / "sessions" / "chat_web_abc"
    session.mkdir(parents=True)
    log = session / "conversation-260529.md"
    log.write_text("# 2026-05-29\n\nuser: hello\nbot: hi there\n", encoding="utf-8")

    prompt = build_reflection_prompt("anne")
    assert "chat_web_abc/conversation-260529.md" in prompt
    assert "hello" in prompt


def test_build_reflection_prompt_existing_self_included(abyss_home: Path) -> None:
    from abyss.self_reflection import build_reflection_prompt, save_self_md

    save_self_md("anne", "## Mistake patterns\n- talks too much\n")
    prompt = build_reflection_prompt("anne")
    assert "talks too much" in prompt


@pytest.mark.asyncio
async def test_run_reflection_saves_output(
    abyss_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import abyss.self_reflection as sr

    captured: dict[str, Any] = {}

    class FakeBackend:
        async def run(self, request):  # noqa: ANN001
            captured["prompt"] = request.user_prompt
            captured["session_directory"] = request.session_directory
            from abyss.llm.base import LLMResult

            return LLMResult(text="## Self update\n\n- be more concise.\n")

    def fake_get_or_create(bot_name: str, bot_config: dict[str, Any]):
        captured["bot_name"] = bot_name
        return FakeBackend()

    monkeypatch.setattr("abyss.llm.registry.get_or_create", fake_get_or_create)

    new_content = await sr.run_reflection("anne", {"backend": {"type": "claude_code"}})
    assert "be more concise" in new_content
    assert sr.load_self_md("anne") == new_content
    assert captured["bot_name"] == "anne"
    assert "anne" in captured["prompt"]
    assert captured["session_directory"] == sr.reflection_session_directory("anne")


@pytest.mark.asyncio
async def test_run_reflection_keeps_old_on_empty_output(
    abyss_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import abyss.self_reflection as sr

    sr.save_self_md("anne", "keep me around")

    class EmptyBackend:
        async def run(self, request):  # noqa: ANN001
            from abyss.llm.base import LLMResult

            return LLMResult(text="   \n  ")

    monkeypatch.setattr(
        "abyss.llm.registry.get_or_create",
        lambda bot, cfg: EmptyBackend(),
    )

    result = await sr.run_reflection("anne", {})
    assert result == "keep me around"
    assert sr.load_self_md("anne") == "keep me around"
