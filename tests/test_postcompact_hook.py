"""Tests for ``hooks/postcompact_hook`` — Phase 8.0 drift alert."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest
import yaml


@pytest.fixture
def abyss_home_with_bot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    monkeypatch.setenv("ABYSS_HOME", str(tmp_path))
    monkeypatch.setenv("AI_AGENT", "abyss")
    (tmp_path / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "bots": [{"name": "anne", "path": str(tmp_path / "bots" / "anne")}],
                "settings": {"language": "english", "timezone": "UTC"},
            }
        )
    )
    bot_dir = tmp_path / "bots" / "anne"
    session_dir = bot_dir / "sessions" / "chat_test"
    session_dir.mkdir(parents=True)
    bot_dir.joinpath("bot.yaml").write_text(
        yaml.safe_dump({"display_name": "Anne", "personality": "p", "role": "r"})
    )
    monkeypatch.chdir(session_dir)
    return tmp_path, bot_dir


def _run_hook(monkeypatch: pytest.MonkeyPatch, payload: dict | None = None) -> int:
    """Drive the hook entry point with a synthetic stdin payload.

    The hook resolves the bot from ``payload['cwd']`` first, ``PWD`` second.
    Always pass ``cwd`` explicitly so the test doesn't depend on the
    real shell's PWD (which monkeypatch.chdir does not sync).
    """
    import os

    payload = dict(payload or {})
    payload.setdefault("cwd", os.getcwd())
    raw = json.dumps(payload)
    monkeypatch.setattr(sys, "stdin", io.StringIO(raw))
    from abyss.hooks import postcompact_hook

    return postcompact_hook.main()


def test_hook_aborts_when_not_abyss(abyss_home_with_bot, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AI_AGENT", raising=False)
    # Should NOT take a snapshot.
    monkeypatch.setattr(
        "abyss.persona_drift.take_snapshot",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("must not snapshot")),
    )
    assert _run_hook(monkeypatch) == 0


def test_hook_first_snapshot_no_alert(abyss_home_with_bot, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("abyss.persona_drift._compose_for_bot", lambda _bot: "## A\nfirst body\n")
    sent: list = []
    monkeypatch.setattr(
        "abyss.web_push.send_push",
        lambda **kwargs: sent.append(kwargs),
    )
    assert _run_hook(monkeypatch) == 0
    # First-ever snapshot — nothing to compare against, no push.
    assert sent == []


def test_hook_alerts_on_shrinkage(abyss_home_with_bot, monkeypatch: pytest.MonkeyPatch) -> None:
    from abyss.persona_drift import take_snapshot

    # Plant a large baseline snapshot.
    monkeypatch.setattr(
        "abyss.persona_drift._compose_for_bot",
        lambda _bot: "## A\n" + ("big " * 200) + "\n",
    )
    take_snapshot("anne", event="manual")
    # Now compose shrinks dramatically.
    monkeypatch.setattr("abyss.persona_drift._compose_for_bot", lambda _bot: "## A\ntiny\n")
    pushes: list[dict] = []

    async def fake_push(**kwargs):
        pushes.append(kwargs)

    monkeypatch.setattr("abyss.web_push.send_push", fake_push)
    assert _run_hook(monkeypatch) == 0
    assert pushes, "expected a Web Push for shrinkage"
    assert "persona drift" in pushes[0]["title"].lower()


def test_hook_no_alert_when_growing(abyss_home_with_bot, monkeypatch: pytest.MonkeyPatch) -> None:
    from abyss.persona_drift import take_snapshot

    monkeypatch.setattr("abyss.persona_drift._compose_for_bot", lambda _bot: "## A\nsmall\n")
    take_snapshot("anne", event="manual")
    monkeypatch.setattr(
        "abyss.persona_drift._compose_for_bot",
        lambda _bot: "## A\n" + ("big " * 200) + "\n",
    )
    pushes: list[dict] = []
    monkeypatch.setattr(
        "abyss.web_push.send_push",
        lambda **kwargs: pushes.append(kwargs),
    )
    assert _run_hook(monkeypatch) == 0
    assert pushes == []


def test_hook_bails_outside_bot_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_AGENT", "abyss")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "abyss.persona_drift.take_snapshot",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("must not snapshot")),
    )
    assert _run_hook(monkeypatch) == 0


def test_hook_swallows_internal_errors(
    abyss_home_with_bot, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_a, **_k):
        raise RuntimeError("anything")

    monkeypatch.setattr("abyss.persona_drift.take_snapshot", boom)
    assert _run_hook(monkeypatch) == 0
