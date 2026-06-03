"""Phase 5 — Skill Autonomy.

The bot may notice it lacks a tool (e.g. while trying to fulfil a
request the user just made). It then calls the ``propose_skill`` MCP
tool, which lands in this module's append/upsert store at
``bots/<name>/skill_proposals.yaml``. A human reviews the queue from
the dashboard or CLI and either approves (which triggers
``import_skill_from_github`` + ``attach_skill_to_bot`` + CLAUDE.md
regenerate) or rejects.

Storage shape (yaml list):

```
- id: <uuid4 hex>
  bot: anne
  candidate_url: https://github.com/owner/repo
  reasons:
    - "needed a stripe invoice fetcher (cron job 'daily-finance')"
    - "asked again on 2026-06-04"
  alternative_urls:
    - https://github.com/other/alt
  proposed_at: 2026-06-03T10:00:00+00:00
  resolved_at: null
  status: pending  # pending | approved | rejected
```

Dedup key is ``candidate_url``: re-proposing the same URL appends a
new ``reasons`` line and refreshes ``proposed_at`` instead of creating
a second row. ``status`` only moves forward (a rejected URL re-proposed
stays rejected — the bot was told "no" and should learn).
"""

from __future__ import annotations

import logging
import os
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from abyss.config import bot_directory

logger = logging.getLogger(__name__)

PROPOSALS_FILENAME = "skill_proposals.yaml"
VALID_STATUSES: tuple[str, ...] = ("pending", "approved", "rejected")


# --- Dataclass ----------------------------------------------------------------


@dataclass
class Proposal:
    """One skill proposal row.

    ``id`` is generated when omitted (callers pass it only when
    re-reading from disk). ``reasons`` accumulates one entry per
    ``add_proposal`` call so a human can see why the bot kept asking.
    """

    bot: str
    candidate_url: str
    reasons: list[str] = field(default_factory=list)
    alternative_urls: list[str] = field(default_factory=list)
    proposed_at: str = ""
    resolved_at: str | None = None
    status: str = "pending"
    id: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            self.id = uuid.uuid4().hex
        if not self.proposed_at:
            self.proposed_at = _iso_now()
        if self.status not in VALID_STATUSES:
            raise ValueError(f"invalid status: {self.status!r}")
        if not self.candidate_url.strip():
            raise ValueError("candidate_url must not be empty")


# --- Paths --------------------------------------------------------------------


def proposals_path(bot_name: str) -> Path:
    """Return the yaml store path for ``bot_name``."""
    return bot_directory(bot_name) / PROPOSALS_FILENAME


# --- Read / Write -------------------------------------------------------------


def _load_raw(bot_name: str) -> list[dict[str, Any]]:
    path = proposals_path(bot_name)
    if not path.exists():
        return []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        logger.warning("skill_proposals.yaml malformed for %s: %s", bot_name, exc)
        return []
    if not isinstance(data, list):
        if data is None:
            return []
        logger.warning(
            "skill_proposals.yaml for %s is not a list (got %s); ignoring",
            bot_name,
            type(data).__name__,
        )
        return []
    return [row for row in data if isinstance(row, dict)]


def _write_atomic(bot_name: str, rows: list[dict[str, Any]]) -> Path:
    path = proposals_path(bot_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f"{PROPOSALS_FILENAME}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            yaml.safe_dump(rows, fh, allow_unicode=True, sort_keys=False)
        os.replace(tmp_name, path)
    except Exception:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    return path


def list_proposals(bot_name: str, *, status: str | None = None) -> list[Proposal]:
    """Return all proposals, optionally filtered by status, newest-first."""
    raw_rows = _load_raw(bot_name)
    proposals: list[Proposal] = []
    for raw in raw_rows:
        try:
            proposal = _row_to_proposal(raw, default_bot=bot_name)
        except ValueError as exc:
            logger.warning("skill_proposals.yaml skip bad row for %s: %s", bot_name, exc)
            continue
        if status is not None and proposal.status != status:
            continue
        proposals.append(proposal)
    proposals.sort(key=lambda proposal: proposal.proposed_at, reverse=True)
    return proposals


def get_proposal(bot_name: str, proposal_id: str) -> Proposal | None:
    """Look up one proposal by id."""
    for proposal in list_proposals(bot_name):
        if proposal.id == proposal_id:
            return proposal
    return None


def add_proposal(
    bot_name: str,
    candidate_url: str,
    reason: str,
    *,
    alternative_urls: list[str] | None = None,
) -> Proposal:
    """Append (or merge into existing) a proposal for ``candidate_url``.

    Dedup logic:

    - URL already present and ``status='pending'``: append ``reason``
      to ``reasons``, merge new alternatives, refresh ``proposed_at``.
    - URL already present and ``status='approved'``: log + return the
      existing row unchanged (the bot already has the skill).
    - URL already present and ``status='rejected'``: log + return the
      existing row unchanged (the bot was told no).
    - URL not present: create a fresh row.
    """
    raw_rows = _load_raw(bot_name)
    candidate = candidate_url.strip()
    if not candidate:
        raise ValueError("candidate_url must not be empty")
    reason = reason.strip()
    alts = [url.strip() for url in (alternative_urls or []) if url.strip()]

    for index, row in enumerate(raw_rows):
        if row.get("candidate_url", "").strip() != candidate:
            continue
        existing = _row_to_proposal(row, default_bot=bot_name)
        if existing.status != "pending":
            logger.info(
                "propose_skill dedup: %s is %s for %s",
                candidate,
                existing.status,
                bot_name,
            )
            return existing
        # Merge into the existing pending row.
        merged_reasons = list(existing.reasons)
        if reason and reason not in merged_reasons:
            merged_reasons.append(reason)
        merged_alts = list(existing.alternative_urls)
        for url in alts:
            if url not in merged_alts:
                merged_alts.append(url)
        existing.reasons = merged_reasons
        existing.alternative_urls = merged_alts
        existing.proposed_at = _iso_now()
        raw_rows[index] = asdict(existing)
        _write_atomic(bot_name, raw_rows)
        return existing

    proposal = Proposal(
        bot=bot_name,
        candidate_url=candidate,
        reasons=[reason] if reason else [],
        alternative_urls=alts,
    )
    raw_rows.append(asdict(proposal))
    _write_atomic(bot_name, raw_rows)
    return proposal


def update_status(bot_name: str, proposal_id: str, status: str) -> Proposal | None:
    """Move a proposal to ``approved`` or ``rejected``.

    Returns the updated proposal, or ``None`` if the id was unknown.
    Does not change anything outside the yaml file — callers that need
    side effects (import / attach) should run those first and then
    call this to record the decision.
    """
    if status not in {"approved", "rejected"}:
        raise ValueError(f"status must be approved|rejected, got {status!r}")
    raw_rows = _load_raw(bot_name)
    for index, row in enumerate(raw_rows):
        if row.get("id") != proposal_id:
            continue
        try:
            proposal = _row_to_proposal(row, default_bot=bot_name)
        except ValueError as exc:
            logger.warning("update_status: malformed row %s for %s: %s", proposal_id, bot_name, exc)
            return None
        proposal.status = status
        proposal.resolved_at = _iso_now()
        raw_rows[index] = asdict(proposal)
        _write_atomic(bot_name, raw_rows)
        return proposal
    return None


# --- Approve flow -------------------------------------------------------------


def approve(bot_name: str, proposal_id: str) -> dict[str, Any]:
    """Import the proposed skill, attach it to the bot, and mark approved.

    Returns a dict describing the outcome:

    - ``{"ok": True, "skill_name": "<name>", "proposal": Proposal}``
    - ``{"ok": False, "error": "<message>", "stage": "<lookup|import|attach>"}``

    Does not raise — the dashboard and CLI both want a structured
    failure so they can surface it without crashing.
    """
    from abyss.skill import attach_skill_to_bot, import_skill_from_github

    proposal = get_proposal(bot_name, proposal_id)
    if proposal is None:
        return {"ok": False, "error": "proposal not found", "stage": "lookup"}
    if proposal.status == "approved":
        return {"ok": True, "skill_name": None, "proposal": proposal, "noop": True}
    if proposal.status == "rejected":
        return {
            "ok": False,
            "error": "proposal was previously rejected",
            "stage": "lookup",
            "proposal": proposal,
        }
    try:
        skill_path = import_skill_from_github(proposal.candidate_url)
    except Exception as exc:  # noqa: BLE001 — surface to caller
        logger.exception("skill import failed for %s", proposal.candidate_url)
        return {"ok": False, "error": str(exc), "stage": "import"}
    skill_name = skill_path.name
    try:
        attach_skill_to_bot(bot_name, skill_name)
    except Exception as exc:  # noqa: BLE001
        logger.exception("attach_skill failed for %s -> %s", skill_name, bot_name)
        return {
            "ok": False,
            "error": str(exc),
            "stage": "attach",
            "skill_name": skill_name,
        }
    updated = update_status(bot_name, proposal_id, "approved")
    return {
        "ok": True,
        "skill_name": skill_name,
        "skill_path": str(skill_path),
        "proposal": updated,
    }


def reject(bot_name: str, proposal_id: str) -> Proposal | None:
    """Mark the proposal rejected. Returns the updated row or ``None``."""
    return update_status(bot_name, proposal_id, "rejected")


# --- Helpers ------------------------------------------------------------------


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _row_to_proposal(raw: dict[str, Any], *, default_bot: str) -> Proposal:
    """Coerce a yaml-loaded dict back into a Proposal dataclass."""
    return Proposal(
        bot=str(raw.get("bot", default_bot)),
        candidate_url=str(raw.get("candidate_url", "")).strip(),
        reasons=[str(reason) for reason in (raw.get("reasons") or []) if reason],
        alternative_urls=[str(url) for url in (raw.get("alternative_urls") or []) if url],
        proposed_at=str(raw.get("proposed_at") or "") or _iso_now(),
        resolved_at=(str(raw["resolved_at"]) if raw.get("resolved_at") else None),
        status=str(raw.get("status") or "pending"),
        id=str(raw.get("id") or ""),
    )
