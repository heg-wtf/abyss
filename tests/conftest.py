"""Global test fixtures for abyss."""

from __future__ import annotations

import shutil

import pytest


@pytest.fixture(autouse=True)
def disable_qmd_auto_inject(monkeypatch):
    """Disable QMD auto-injection in tests.

    QMD auto-injection fires when `shutil.which("qmd")` returns a path.
    On dev machines where qmd is installed, this causes unexpected side effects
    in tests that don't expect QMD config. QMD-specific tests in test_qmd.py
    override this by patching explicitly.
    """
    original_which = shutil.which

    def _which_without_qmd(name, *args, **kwargs):
        if name == "qmd":
            return None
        return original_which(name, *args, **kwargs)

    monkeypatch.setattr(shutil, "which", _which_without_qmd)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "enable_conversation_search: opt-in to the real "
        "conversation_search auto-injection (FTS5 stays enabled).",
    )


@pytest.fixture(autouse=True)
def clear_llm_backend_cache():
    """Reset cached LLM backend instances between tests.

    The ``abyss.llm.registry`` cache persists ``ClaudeCodeBackend``
    instances per bot for the lifetime of the process. Tests that
    exercise the same bot name with different configs must start from a
    clean slate.
    """
    from abyss.llm import registry

    yield
    registry._INSTANCES.clear()


@pytest.fixture(autouse=True)
def disable_conversation_search_auto_inject(request, monkeypatch):
    """Disable conversation_search auto-injection in tests by default.

    The real ``is_fts5_available()`` returns True on every modern Python
    build, which would cause the auto-injected SKILL.md and MCP server
    to leak into tests that pre-date this feature. Tests that exercise
    the feature opt back in with ``@pytest.mark.enable_conversation_search``.
    """
    if "enable_conversation_search" in request.keywords:
        return
    monkeypatch.setattr("abyss.conversation_index.is_fts5_available", lambda: False)
