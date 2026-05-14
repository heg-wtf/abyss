"""Rich-powered checklist UI for the ``abyss start`` boot sequence.

Used by ``abyss start`` / ``abyss restart`` to render bot prep, API
server boot, dashboard build / install / start, and scheduler attach as
an in-place updated checklist instead of streaming raw subprocess output.

Each step renders one line:

    ✓ Stop existing process            0.3s
    ✓ Locate dashboard                 abysscope/
    ⠋ Build dashboard                  running
    · Start server                     pending

Heavy subprocess output (npm install, next build) is captured to a log file
under ``~/.abyss/logs/`` so the user can still inspect failures, but the
terminal stays a tight summary.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Iterator

from rich.console import Console, Group, RenderableType
from rich.live import Live
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


_GLYPHS: dict[StepStatus, tuple[str, str]] = {
    StepStatus.PENDING: ("·", "dim"),
    StepStatus.SUCCESS: ("✓", "green"),
    StepStatus.FAILED: ("✗", "red"),
    StepStatus.SKIPPED: ("∘", "dim cyan"),
    # RUNNING is rendered with a spinner instead of a static glyph.
}

NAME_COLUMN_WIDTH = 32


@dataclass
class BuildStep:
    """One row in the build checklist."""

    name: str
    status: StepStatus = StepStatus.PENDING
    detail: str = ""
    started_at: float = 0.0
    finished_at: float = 0.0

    @property
    def duration(self) -> float:
        if self.started_at and self.finished_at:
            return self.finished_at - self.started_at
        if self.started_at and self.status is StepStatus.RUNNING:
            return time.monotonic() - self.started_at
        return 0.0

    def render(self) -> RenderableType:
        """Return a single-row Rich Table for this step.

        Rich's :class:`Spinner` cannot be inlined into ``Text.assemble``,
        so each row is a borderless three-column table: indicator,
        name (padded), detail.
        """
        if self.status is StepStatus.RUNNING:
            indicator: RenderableType = Spinner("dots", style="cyan")
        else:
            glyph, color = _GLYPHS[self.status]
            indicator = Text(glyph, style=color)

        table = Table.grid(padding=(0, 2))
        table.add_column(width=2, no_wrap=True)
        table.add_column(width=NAME_COLUMN_WIDTH, no_wrap=True)
        table.add_column(no_wrap=True, overflow="fold")
        table.add_row(indicator, Text(self.name), self._detail_text())
        return table

    def _detail_text(self) -> Text:
        if self.status is StepStatus.RUNNING:
            elapsed = self.duration
            label = self.detail or "running"
            elapsed_str = f"  ({elapsed:.1f}s)" if elapsed > 0 else ""
            return Text(f"{label}{elapsed_str}", style="cyan")
        if self.status is StepStatus.SUCCESS:
            duration = f"  {self.duration:.1f}s" if self.duration >= 0.05 else ""
            detail = self.detail
            return Text(f"{detail}{duration}".strip(), style="dim")
        if self.status is StepStatus.FAILED:
            return Text(self.detail or "failed", style="red")
        if self.status is StepStatus.SKIPPED:
            return Text(self.detail or "skipped", style="dim")
        return Text(self.detail or "pending", style="dim")


@dataclass
class BuildProgress:
    """Stateful checklist driven by ``with progress.step(...)`` blocks."""

    title: str
    steps: list[BuildStep]
    console: Console = field(default_factory=Console)
    _live: Live | None = None

    def __post_init__(self) -> None:
        self._step_index = {step.name: step for step in self.steps}

    def render(self) -> RenderableType:
        rows: list[RenderableType] = [Text(self.title, style="bold")]
        rows.extend(step.render() for step in self.steps)
        return Group(*rows)

    @contextmanager
    def live(self) -> Iterator[BuildProgress]:
        """Render the checklist in place until the block exits."""
        self._live = Live(
            self.render(),
            console=self.console,
            refresh_per_second=12,
            transient=False,
        )
        with self._live:
            try:
                yield self
            finally:
                self._live.update(self.render())

    def refresh(self) -> None:
        """Re-render the checklist (e.g. after mutating step state directly)."""
        if self._live is not None:
            self._live.update(self.render())

    def _refresh(self) -> None:  # backwards-compat alias
        self.refresh()

    def get(self, name: str) -> BuildStep:
        return self._step_index[name]

    @contextmanager
    def step(self, name: str) -> Iterator[BuildStep]:
        """Context manager that flips a step to ``RUNNING`` and finalizes it.

        On clean exit the step becomes ``SUCCESS`` (unless the caller
        already marked it ``SKIPPED``). On exception, ``FAILED`` with the
        exception message preserved as detail, and the exception is
        re-raised so callers can decide how to abort.
        """
        target = self.get(name)
        if target.status is not StepStatus.SKIPPED:
            target.status = StepStatus.RUNNING
            target.started_at = time.monotonic()
        self._refresh()
        try:
            yield target
        except Exception as error:
            target.status = StepStatus.FAILED
            # Surface the failure reason. Prefer the exception message over the
            # transient "running…" detail set while the step was in flight.
            error_message = str(error) or error.__class__.__name__
            target.detail = error_message
            target.finished_at = time.monotonic()
            self._refresh()
            raise
        else:
            target.finished_at = time.monotonic()
            if target.status is StepStatus.RUNNING:
                target.status = StepStatus.SUCCESS
            self._refresh()


# ---------------------------------------------------------------------------
# Build log file helpers
# ---------------------------------------------------------------------------


def open_build_log(home: Path) -> Path:
    """Return a fresh log path under ``<home>/logs/`` for build output capture."""
    logs_dir = home / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return logs_dir / f"dashboard-build-{timestamp}.log"


def tail(path: Path, lines: int = 40) -> str:
    """Return up to ``lines`` of trailing content from ``path`` as a string."""
    if not path.exists():
        return ""
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return ""
    chunks = text.splitlines()
    return "\n".join(chunks[-lines:])
