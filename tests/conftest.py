"""Global test fixtures for cclaw."""

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
