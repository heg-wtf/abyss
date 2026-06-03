"""Phase 6 — per-bot goal tracking.

Each bot may keep a structured `bots/<name>/goals.yaml` describing
sub-goals (title + KPI + target), their lifecycle status, and an
append-only timeline of `progress` entries the bot logged via the
``record_progress`` MCP tool (or the human via CLI / dashboard).

Storage shape:

```yaml
- id: ship-blog
  title: Ship the blog launcher PR
  kpi: PR merged to main
  target: 2026-06-15
  status: active   # active | done | archived
  created_at: 2026-06-03T09:00:00+00:00
  progress:
    - ts: 2026-06-03T10:00:00+00:00
      note: "drafted plan, opened PR"
    - ts: 2026-06-04T20:00:00+00:00
      note: "addressed review, CI green"
      value: 1
```

Design notes:

- Single file (not goal-def + progress-jsonl split). Volume per bot
  is small (tens of goals, dozens of progress rows each), so the
  simplicity of one human-editable yaml wins over append-perf.
- ``id`` is a kebab-case slug — assigned by the caller, or generated
  from ``title`` when omitted. Uniqueness is enforced per bot.
- Progress is intentionally NOT deduped — the timeline is the truth.
- ``status`` only moves forward via dedicated helpers (``mark_done``,
  ``mark_archived``) so the dashboard can render lifecycle clearly.
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from abyss.config import bot_directory

logger = logging.getLogger(__name__)

GOALS_FILENAME = "goals.yaml"
GOAL_DIGEST_JOB_NAME = "goal_digest"

VALID_STATUSES: tuple[str, ...] = ("active", "done", "archived")

_SLUG_RE = re.compile(r"[^a-z0-9]+")


# --- Dataclasses --------------------------------------------------------------


@dataclass
class ProgressEntry:
    """One row of a goal's append-only timeline."""

    ts: str
    note: str
    value: float | None = None


@dataclass
class Goal:
    """One sub-goal owned by a bot.

    ``kpi`` is free text — what "done" looks like ("MRR $10k", "blog
    landing page live"). ``target`` is a free-form deadline / value
    string (we don't enforce date parsing because some bots track
    qualitative goals).
    """

    id: str
    title: str
    kpi: str = ""
    target: str = ""
    status: str = "active"
    created_at: str = ""
    progress: list[ProgressEntry] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("id must not be empty")
        if not self.title.strip():
            raise ValueError("title must not be empty")
        if self.status not in VALID_STATUSES:
            raise ValueError(f"invalid status: {self.status!r}")
        if not self.created_at:
            self.created_at = _iso_now()


# --- Paths --------------------------------------------------------------------


def goals_path(bot_name: str) -> Path:
    """Return the yaml store path for ``bot_name``."""
    return bot_directory(bot_name) / GOALS_FILENAME


# --- Slug + timestamp helpers -------------------------------------------------


def slugify(title: str) -> str:
    """Turn a free-form title into a kebab-case slug, capped at 60 chars."""
    lowered = title.lower().strip()
    slug = _SLUG_RE.sub("-", lowered).strip("-")
    return slug[:60] or "goal"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --- Read / Write -------------------------------------------------------------


def _load_raw(bot_name: str) -> list[dict[str, Any]]:
    path = goals_path(bot_name)
    if not path.exists():
        return []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        logger.warning("goals.yaml malformed for %s: %s", bot_name, exc)
        return []
    if data is None:
        return []
    if not isinstance(data, list):
        logger.warning(
            "goals.yaml for %s is not a list (got %s); ignoring",
            bot_name,
            type(data).__name__,
        )
        return []
    return [row for row in data if isinstance(row, dict)]


def _row_to_goal(raw: dict[str, Any]) -> Goal:
    progress_rows = raw.get("progress") or []
    progress: list[ProgressEntry] = []
    if isinstance(progress_rows, list):
        for row in progress_rows:
            if not isinstance(row, dict):
                continue
            try:
                progress.append(
                    ProgressEntry(
                        ts=str(row.get("ts") or ""),
                        note=str(row.get("note") or "").strip(),
                        value=(float(row["value"]) if row.get("value") is not None else None),
                    )
                )
            except (TypeError, ValueError):
                continue
    return Goal(
        id=str(raw.get("id", "")).strip(),
        title=str(raw.get("title", "")).strip(),
        kpi=str(raw.get("kpi", "")).strip(),
        target=str(raw.get("target", "")).strip(),
        status=str(raw.get("status", "active") or "active"),
        created_at=str(raw.get("created_at") or _iso_now()),
        progress=progress,
    )


def _write_atomic(bot_name: str, rows: list[dict[str, Any]]) -> Path:
    path = goals_path(bot_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f"{GOALS_FILENAME}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            yaml.safe_dump(rows, fh, allow_unicode=True, sort_keys=False)
        os.replace(tmp_name, path)
    except Exception:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    return path


# --- CRUD ---------------------------------------------------------------------


def list_goals(bot_name: str, *, status: str | None = None) -> list[Goal]:
    """Return every goal, optionally filtered by status.

    Sorted: active first (by created_at ascending so older goals stay
    on top), then done, then archived. Inside the same status group
    the order matches the on-disk yaml order — humans expect editing
    to preserve their layout.
    """
    rows = _load_raw(bot_name)
    goals: list[Goal] = []
    for raw in rows:
        try:
            goal = _row_to_goal(raw)
        except ValueError as exc:
            logger.warning("goals.yaml skip bad row for %s: %s", bot_name, exc)
            continue
        if status is not None and goal.status != status:
            continue
        goals.append(goal)
    return goals


def get_goal(bot_name: str, goal_id: str) -> Goal | None:
    """Look up one goal by id, or ``None`` when missing."""
    for goal in list_goals(bot_name):
        if goal.id == goal_id:
            return goal
    return None


def add_goal(
    bot_name: str,
    title: str,
    *,
    goal_id: str | None = None,
    kpi: str = "",
    target: str = "",
) -> Goal:
    """Create a fresh goal. ``id`` is auto-slugified from ``title`` when omitted.

    Raises ``ValueError`` if the id already exists for this bot (per-bot
    uniqueness keeps the dashboard sane).
    """
    rows = _load_raw(bot_name)
    desired_id = (goal_id or slugify(title)).strip()
    existing_ids = {row.get("id") for row in rows}
    if desired_id in existing_ids:
        raise ValueError(f"goal id already exists for {bot_name}: {desired_id!r}")
    goal = Goal(id=desired_id, title=title.strip(), kpi=kpi.strip(), target=target.strip())
    rows.append(_goal_to_row(goal))
    _write_atomic(bot_name, rows)
    return goal


def update_goal(
    bot_name: str,
    goal_id: str,
    *,
    title: str | None = None,
    kpi: str | None = None,
    target: str | None = None,
    status: str | None = None,
) -> Goal | None:
    """Apply non-``None`` fields to the matching goal. Returns the updated goal."""
    rows = _load_raw(bot_name)
    for index, row in enumerate(rows):
        if row.get("id") != goal_id:
            continue
        goal = _row_to_goal(row)
        if title is not None:
            if not title.strip():
                raise ValueError("title must not be empty")
            goal.title = title.strip()
        if kpi is not None:
            goal.kpi = kpi.strip()
        if target is not None:
            goal.target = target.strip()
        if status is not None:
            if status not in VALID_STATUSES:
                raise ValueError(f"invalid status: {status!r}")
            goal.status = status
        rows[index] = _goal_to_row(goal)
        _write_atomic(bot_name, rows)
        return goal
    return None


def delete_goal(bot_name: str, goal_id: str) -> bool:
    """Remove a goal entirely. Returns True if a row was deleted."""
    rows = _load_raw(bot_name)
    filtered = [row for row in rows if row.get("id") != goal_id]
    if len(filtered) == len(rows):
        return False
    _write_atomic(bot_name, filtered)
    return True


def mark_done(bot_name: str, goal_id: str) -> Goal | None:
    """Shortcut for ``update_goal(status='done')``."""
    return update_goal(bot_name, goal_id, status="done")


def mark_archived(bot_name: str, goal_id: str) -> Goal | None:
    """Shortcut for ``update_goal(status='archived')``."""
    return update_goal(bot_name, goal_id, status="archived")


# --- Progress -----------------------------------------------------------------


def record_progress(
    bot_name: str,
    goal_id: str,
    note: str,
    *,
    value: float | None = None,
    ts: str | None = None,
) -> ProgressEntry | None:
    """Append one progress entry. Returns the new entry, or ``None`` if the
    goal id is unknown (so callers can branch without an exception)."""
    rows = _load_raw(bot_name)
    cleaned_note = note.strip()
    if not cleaned_note:
        raise ValueError("note must not be empty")
    for index, row in enumerate(rows):
        if row.get("id") != goal_id:
            continue
        goal = _row_to_goal(row)
        entry = ProgressEntry(ts=ts or _iso_now(), note=cleaned_note, value=value)
        goal.progress.append(entry)
        rows[index] = _goal_to_row(goal)
        _write_atomic(bot_name, rows)
        return entry
    return None


# --- Helpers ------------------------------------------------------------------


def _goal_to_row(goal: Goal) -> dict[str, Any]:
    row = asdict(goal)
    # asdict turns ProgressEntry into nested dicts already; trim value=None
    # so the yaml stays clean for purely qualitative goals.
    pruned: list[dict[str, Any]] = []
    for entry in row["progress"]:
        if entry.get("value") is None:
            entry = {key: value for key, value in entry.items() if key != "value"}
        pruned.append(entry)
    row["progress"] = pruned
    return row


# --- Weekly digest prompt -----------------------------------------------------


def build_digest_prompt(bot_name: str, *, lookback_days: int = 7) -> str:
    """Compose the weekly digest LLM prompt for ``bot_name``.

    Includes every active goal and any progress within the lookback
    window. The LLM is asked to summarise progress, surface stalled
    goals, and propose next steps. The output lands in the cron's
    ``conversation-YYMMDD.md`` like any other cron job.
    """
    from datetime import timedelta

    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    cutoff_iso = cutoff.isoformat(timespec="seconds")

    active_goals = list_goals(bot_name, status="active")
    if not active_goals:
        return (
            f"Weekly goal digest for bot '{bot_name}'.\n\n"
            "There are no active goals. Reply briefly that the goal "
            "list is empty and suggest adding a goal via the dashboard."
        )

    sections: list[str] = []
    for goal in active_goals:
        recent = [entry for entry in goal.progress if entry.ts >= cutoff_iso]
        sections.append(
            f"### {goal.title} (id={goal.id})\n"
            f"- KPI: {goal.kpi or '(none)'}\n"
            f"- Target: {goal.target or '(none)'}\n"
            f"- Progress in the last {lookback_days} days: "
            + (
                "\n  - "
                + "\n  - ".join(
                    f"{entry.ts}: {entry.note}"
                    + (f" (value={entry.value})" if entry.value is not None else "")
                    for entry in recent
                )
                if recent
                else "(none — goal has been quiet)"
            )
        )
    body = "\n\n".join(sections)
    return (
        f"Weekly goal digest for bot '{bot_name}'.\n"
        f"Time window: last {lookback_days} days.\n\n"
        f"Active goals + recent progress:\n\n{body}\n\n"
        "Write a concise digest (under 400 words) in Korean by default. "
        "For each goal: 1) what progressed this week, 2) what stalled "
        "and why, 3) one concrete next step. End with a one-line "
        "headline that captures the week's biggest move (or biggest "
        "miss)."
    )
