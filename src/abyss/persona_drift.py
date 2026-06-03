"""Phase 8.0 — persona drift detection.

Tracks how a bot's *composed CLAUDE.md* (personality + role + goal +
SELF + ABOUT_ME index + memory pointer + goals + skill instructions +
rules + ...) changes over time. Daily cron + post-compact hook take a
snapshot, hash it, and record per-section byte counts. A weekly LLM
digest summarises drift; an automatic alert fires if compact-induced
shrinkage exceeds a threshold.

What we record (not the full text — privacy + disk):

- ``ts`` — ISO-8601 UTC timestamp
- ``hash`` — sha256 of the entire composed CLAUDE.md
- ``total_bytes`` — len(text.encode("utf-8"))
- ``section_sizes`` — ``{section_name: bytes}`` parsed from ``## ...`` headers
- ``event`` — ``daily | post-compact | manual``

Section header parsing uses the canonical ``## Section Title`` form
that ``compose_claude_md`` already emits. Pre-section content (the
``# Bot Name`` heading + intro lines) goes into a synthetic
``__preamble__`` section so we never silently lose bytes.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

from abyss.config import bot_directory

logger = logging.getLogger(__name__)

SNAPSHOTS_FILENAME = "persona_snapshots.jsonl"
PERSONA_DAILY_JOB_NAME = "persona_snapshot"
PERSONA_DIGEST_JOB_NAME = "persona_digest"

VALID_EVENTS: tuple[str, ...] = ("daily", "post-compact", "manual")

DEFAULT_SHRINKAGE_ALERT_THRESHOLD = 0.10  # 10% total bytes lost
PREAMBLE_KEY = "__preamble__"

_SECTION_HEADER_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


# --- Dataclass ----------------------------------------------------------------


@dataclass
class PersonaSnapshot:
    """One row in ``persona_snapshots.jsonl``."""

    ts: str
    hash: str
    total_bytes: int
    section_sizes: dict[str, int] = field(default_factory=dict)
    event: str = "daily"

    def __post_init__(self) -> None:
        if self.event not in VALID_EVENTS:
            raise ValueError(f"invalid event: {self.event!r}")


# --- Paths --------------------------------------------------------------------


def snapshots_path(bot_name: str) -> Path:
    """Return the per-bot snapshots jsonl path."""
    return bot_directory(bot_name) / SNAPSHOTS_FILENAME


# --- Composition helpers ------------------------------------------------------


def _compose_for_bot(bot_name: str) -> str:
    """Return the composed CLAUDE.md text for ``bot_name``.

    Uses the same surface ``bot_manager`` uses on ``abyss start`` so
    drift tracks what the bot actually sees.
    """
    from abyss.config import load_bot_config
    from abyss.skill import compose_claude_md

    bot_config = load_bot_config(bot_name)
    if bot_config is None:
        raise ValueError(f"bot not found: {bot_name}")
    return compose_claude_md(
        bot_name=bot_name,
        personality=bot_config.get("personality", ""),
        role=bot_config.get("role", ""),
        goal=bot_config.get("goal", ""),
        skill_names=bot_config.get("skills") or [],
        bot_path=bot_directory(bot_name),
    )


def _section_sizes(text: str) -> dict[str, int]:
    """Return ``{section_name: bytes}`` parsed from ``## Section Title`` headers.

    The text before the first ``##`` (the ``# Bot Name`` block + any
    intro paragraphs) is bucketed into ``__preamble__`` so the totals
    in this dict sum to ``len(text.encode("utf-8"))``.

    Section names are kept verbatim from the header so the dashboard
    can render emoji-prefixed sections like ``🪞 Self Reflection``
    unchanged.
    """
    if not text:
        return {}

    matches = list(_SECTION_HEADER_RE.finditer(text))
    if not matches:
        return {PREAMBLE_KEY: len(text.encode("utf-8"))}

    sizes: dict[str, int] = {}
    first_start = matches[0].start()
    if first_start > 0:
        sizes[PREAMBLE_KEY] = len(text[:first_start].encode("utf-8"))

    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        name = match.group(1).strip()
        chunk = text[start:end]
        # Sum so a CLAUDE.md that accidentally repeats a section name
        # (rare but possible) doesn't silently drop bytes.
        sizes[name] = sizes.get(name, 0) + len(chunk.encode("utf-8"))
    return sizes


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --- Snapshot read / write ----------------------------------------------------


def take_snapshot(bot_name: str, *, event: str = "daily") -> PersonaSnapshot:
    """Compose the bot's CLAUDE.md, hash + measure it, append one jsonl row.

    Returns the new snapshot so callers can chain a drift check.
    """
    text = _compose_for_bot(bot_name)
    sizes = _section_sizes(text)
    snapshot = PersonaSnapshot(
        ts=_iso_now(),
        hash=_hash_text(text),
        total_bytes=len(text.encode("utf-8")),
        section_sizes=sizes,
        event=event,
    )
    path = snapshots_path(bot_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(snapshot), ensure_ascii=False, sort_keys=True) + "\n")
    return snapshot


def iter_snapshots(
    bot_name: str,
    *,
    since: str | None = None,
    limit: int | None = None,
) -> Iterator[PersonaSnapshot]:
    """Stream snapshots newest-first with optional filters.

    Malformed rows are logged and skipped — the jsonl is best-effort.
    """
    path = snapshots_path(bot_name)
    if not path.exists():
        return
    rows: list[PersonaSnapshot] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
            snap = PersonaSnapshot(
                ts=str(data.get("ts", "")),
                hash=str(data.get("hash", "")),
                total_bytes=int(data.get("total_bytes", 0)),
                section_sizes={
                    str(k): int(v) for k, v in (data.get("section_sizes") or {}).items()
                },
                event=str(data.get("event", "daily")),
            )
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.warning("persona snapshot skip malformed line for %s: %s", bot_name, exc)
            continue
        if since is not None and snap.ts < since:
            continue
        rows.append(snap)
    rows.sort(key=lambda snap: snap.ts, reverse=True)
    if limit is not None:
        rows = rows[:limit]
    yield from rows


# --- Drift compute ------------------------------------------------------------


@dataclass
class DriftReport:
    """Result of comparing two snapshots."""

    latest_ts: str
    baseline_ts: str
    latest_bytes: int
    baseline_bytes: int
    total_delta_bytes: int
    total_delta_pct: float
    hash_changed: bool
    section_deltas: dict[str, int]  # section_name → byte delta
    shrinkage_alert: bool  # True when shrinkage exceeds threshold


def compute_drift(
    bot_name: str,
    *,
    window_days: int = 7,
    threshold: float = DEFAULT_SHRINKAGE_ALERT_THRESHOLD,
) -> DriftReport | None:
    """Compare the newest snapshot against the closest one ≥ ``window_days`` ago.

    Returns ``None`` when there is no baseline old enough to compare —
    e.g. the bot just started snapshotting.
    """
    snapshots = list(iter_snapshots(bot_name))
    if not snapshots:
        return None
    latest = snapshots[0]
    cutoff = (datetime.fromisoformat(latest.ts) - timedelta(days=window_days)).isoformat(
        timespec="seconds"
    )
    baseline: PersonaSnapshot | None = None
    for snap in snapshots[1:]:
        if snap.ts <= cutoff:
            baseline = snap
            break
    if baseline is None:
        # Fall back to oldest snapshot so the dashboard always has
        # *something* to render once a second snapshot exists.
        if len(snapshots) < 2:
            return None
        baseline = snapshots[-1]

    keys = set(latest.section_sizes) | set(baseline.section_sizes)
    section_deltas = {
        key: latest.section_sizes.get(key, 0) - baseline.section_sizes.get(key, 0) for key in keys
    }
    total_delta = latest.total_bytes - baseline.total_bytes
    pct = total_delta / max(1, baseline.total_bytes)
    shrinkage = pct <= -abs(threshold)
    return DriftReport(
        latest_ts=latest.ts,
        baseline_ts=baseline.ts,
        latest_bytes=latest.total_bytes,
        baseline_bytes=baseline.total_bytes,
        total_delta_bytes=total_delta,
        total_delta_pct=pct,
        hash_changed=latest.hash != baseline.hash,
        section_deltas=section_deltas,
        shrinkage_alert=shrinkage,
    )


def compare_snapshots(earlier: PersonaSnapshot, later: PersonaSnapshot) -> DriftReport:
    """Build a DriftReport directly from two in-memory snapshots.

    Used by the post-compact hook where we just took both snapshots
    and don't want to round-trip through the jsonl.
    """
    keys = set(later.section_sizes) | set(earlier.section_sizes)
    section_deltas = {
        key: later.section_sizes.get(key, 0) - earlier.section_sizes.get(key, 0) for key in keys
    }
    total_delta = later.total_bytes - earlier.total_bytes
    pct = total_delta / max(1, earlier.total_bytes)
    return DriftReport(
        latest_ts=later.ts,
        baseline_ts=earlier.ts,
        latest_bytes=later.total_bytes,
        baseline_bytes=earlier.total_bytes,
        total_delta_bytes=total_delta,
        total_delta_pct=pct,
        hash_changed=later.hash != earlier.hash,
        section_deltas=section_deltas,
        shrinkage_alert=pct <= -DEFAULT_SHRINKAGE_ALERT_THRESHOLD,
    )


# --- Digest prompt ------------------------------------------------------------


def build_drift_digest_prompt(bot_name: str, *, window_days: int = 7) -> str:
    """Build the LLM prompt for the weekly drift digest cron."""
    report = compute_drift(bot_name, window_days=window_days)
    if report is None:
        return (
            f"Persona drift digest for '{bot_name}'.\n\n"
            "There is not yet enough snapshot history to compute drift. "
            "Reply briefly that drift tracking is too new and suggest "
            "the human keep using the bot so daily snapshots accumulate."
        )
    moved = [
        (name, delta)
        for name, delta in sorted(
            report.section_deltas.items(), key=lambda kv: abs(kv[1]), reverse=True
        )
        if delta != 0
    ][:6]
    lines = [
        f"Persona drift digest for bot '{bot_name}'.",
        f"Comparing latest snapshot ({report.latest_ts}) against baseline ({report.baseline_ts}).",
        "",
        f"- Total bytes: {report.baseline_bytes} → {report.latest_bytes} "
        f"(delta {report.total_delta_bytes:+d}, {report.total_delta_pct:+.1%})",
        f"- Hash changed: {report.hash_changed}",
        f"- Shrinkage alert: {report.shrinkage_alert}",
        "",
        "Section deltas (top 6 by magnitude):",
    ]
    if moved:
        for name, delta in moved:
            lines.append(f"  - {name}: {delta:+d} bytes")
    else:
        lines.append("  - (no per-section changes)")
    lines.extend(
        [
            "",
            "Write a concise digest (under 300 words, Korean by default). "
            "For each meaningful section delta: 1) state what changed in "
            "neutral language, 2) hypothesise the cause (compact / SELF.md "
            "rewrite / new goal / ...), 3) note whether this looks like "
            "drift the human should investigate. End with a one-line "
            "headline about the week's biggest persona movement.",
        ]
    )
    return "\n".join(lines)


# --- Helpers ------------------------------------------------------------------


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def shrinkage_threshold_pct() -> float:
    """Public accessor so other modules (alerts) stay consistent."""
    return DEFAULT_SHRINKAGE_ALERT_THRESHOLD
