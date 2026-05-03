"""Tests for ``abyss.dashboard_ui`` checklist UI."""

from __future__ import annotations

import io

import pytest
from rich.console import Console

from abyss.dashboard_ui import (
    BuildProgress,
    BuildStep,
    StepStatus,
    open_build_log,
    tail,
)


def _make_progress(*names: str) -> tuple[BuildProgress, io.StringIO]:
    buffer = io.StringIO()
    console = Console(file=buffer, force_terminal=False, color_system=None, width=120)
    progress = BuildProgress(
        title="Test",
        steps=[BuildStep(name) for name in names],
        console=console,
    )
    return progress, buffer


def test_clean_step_marks_success_and_records_duration():
    progress, _ = _make_progress("alpha")
    with progress.live():
        with progress.step("alpha") as step:
            step.detail = "ok"
    finalized = progress.get("alpha")
    assert finalized.status is StepStatus.SUCCESS
    assert finalized.detail == "ok"
    assert finalized.duration >= 0.0


def _trigger_failing_step(progress: BuildProgress) -> None:
    """Helper that always raises inside the progress block — kept as a
    standalone function so static analyzers don't flag the test body
    after ``pytest.raises`` as unreachable.
    """
    with progress.live():
        with progress.step("alpha"):
            raise RuntimeError("boom")


def test_failing_step_marks_failed_and_reraises():
    progress, _ = _make_progress("alpha")
    with pytest.raises(RuntimeError, match="boom"):
        _trigger_failing_step(progress)
    finalized = progress.get("alpha")
    assert finalized.status is StepStatus.FAILED
    assert finalized.detail == "boom"


def test_skipped_step_keeps_skipped_status():
    progress, _ = _make_progress("alpha")
    with progress.live():
        with progress.step("alpha") as step:
            step.status = StepStatus.SKIPPED
            step.detail = "cached"
    finalized = progress.get("alpha")
    assert finalized.status is StepStatus.SKIPPED
    assert finalized.detail == "cached"


def test_render_includes_title_and_step_glyphs():
    progress, buffer = _make_progress("alpha", "beta")
    progress.steps[0].status = StepStatus.SUCCESS
    progress.steps[0].detail = "ready"
    progress.steps[1].status = StepStatus.PENDING
    Console(file=buffer, force_terminal=False, color_system=None, width=120).print(
        progress.render()
    )
    output = buffer.getvalue()
    assert "Test" in output
    assert "alpha" in output
    assert "beta" in output
    assert "✓" in output


def test_open_build_log_creates_logs_dir(tmp_path):
    log_path = open_build_log(tmp_path)
    assert log_path.parent.exists()
    assert log_path.parent.name == "logs"
    assert log_path.suffix == ".log"
    assert log_path.name.startswith("dashboard-build-")


def test_tail_returns_last_lines(tmp_path):
    target = tmp_path / "build.log"
    target.write_text("\n".join(f"line-{i}" for i in range(1, 11)))
    out = tail(target, lines=3)
    assert out.splitlines() == ["line-8", "line-9", "line-10"]


def test_tail_handles_missing_file(tmp_path):
    assert tail(tmp_path / "nope.log") == ""


def test_running_step_renders_spinner_and_detail():
    """A step in RUNNING state should not show a static glyph and should
    surface its detail text in the rendered output."""
    progress, buffer = _make_progress("alpha")
    target = progress.get("alpha")
    target.status = StepStatus.RUNNING
    target.detail = "next build"
    target.started_at = 0  # avoid a flaky elapsed counter in the snapshot

    Console(file=buffer, force_terminal=False, color_system=None, width=120).print(target.render())
    output = buffer.getvalue()
    assert "alpha" in output
    assert "next build" in output
    # ✓/✗/· glyphs are reserved for non-RUNNING states.
    for glyph in ("✓", "✗", "·"):
        assert glyph not in output


def test_step_unknown_name_raises_keyerror():
    progress, _ = _make_progress("alpha")
    with progress.live():
        with pytest.raises(KeyError):
            with progress.step("does-not-exist"):
                pass


def test_open_build_log_returns_unique_paths(tmp_path):
    """Successive calls produce distinct log paths so concurrent restarts
    don't trample each other's output."""
    import time

    a = open_build_log(tmp_path)
    time.sleep(1.05)  # the timestamp is second-precision
    b = open_build_log(tmp_path)
    assert a != b
    assert a.parent == b.parent


def test_tail_returns_full_text_when_file_smaller_than_limit(tmp_path):
    target = tmp_path / "build.log"
    target.write_text("only-line")
    assert tail(target, lines=50) == "only-line"


def test_tail_handles_unreadable_file(tmp_path):
    """Permission errors during read are swallowed (best-effort tail)."""
    import os
    import sys

    if sys.platform == "win32":
        pytest.skip("chmod is not meaningful on Windows")
    target = tmp_path / "build.log"
    target.write_text("hidden")
    target.chmod(0o000)
    try:
        result = tail(target, lines=10)
    finally:
        target.chmod(0o644)
    if os.geteuid() == 0:  # pragma: no cover - root cannot be denied
        assert result == "hidden"
    else:
        assert result == ""
