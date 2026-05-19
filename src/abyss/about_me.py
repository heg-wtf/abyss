"""ABOUT_ME — shared user knowledge base read by every bot.

Phase 2a of the co-evolution roadmap. See
``docs/plan-about-me-2026-05-19.md`` for the full design.

Layout::

    ~/.abyss/ABOUT_ME/
    ├── INDEX.md            # one-line summary per category (injected into CLAUDE.md)
    ├── identity.md         # name, birthday, job, location
    ├── relationships.md    # family, colleagues, friends
    ├── preferences.md      # likes / dislikes
    ├── routines.md         # daily / weekly rhythms
    ├── current_focus.md    # what's top of mind right now
    ├── health.md           # health status / meds / habits
    └── values.md           # principles, decision rules

Each category file is a sequence of entries delimited by YAML
frontmatter blocks (``---`` fences). Phase 2a is **read-only from the
bot's perspective** — only the CLI (and ``migrate``) writes to disk.
Phase 2b will add an MCP-backed ``propose`` flow.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from abyss.config import abyss_home

logger = logging.getLogger(__name__)

ABOUT_ME_DIRNAME = "ABOUT_ME"
INDEX_FILE_NAME = "INDEX.md"

ABOUT_ME_CATEGORIES: tuple[str, ...] = (
    "identity",
    "relationships",
    "preferences",
    "routines",
    "current_focus",
    "health",
    "values",
)

CATEGORY_HEADINGS: dict[str, str] = {
    "identity": "Identity",
    "relationships": "Relationships",
    "preferences": "Preferences",
    "routines": "Routines",
    "current_focus": "Current Focus",
    "health": "Health",
    "values": "Values",
}

VALID_STATUSES = ("confirmed", "propose")
VALID_CONFIDENCE = ("high", "medium", "low")

INDEX_HEADER = "# About Me — Index"
INDEX_PREAMBLE = (
    "_한줄 요약. 봇이 CLAUDE.md 로 자동 참조한다. "
    "수정은 카테고리 파일에서 (`abyss about-me edit <category>`)._"
)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


def about_me_directory() -> Path:
    """Return ``~/.abyss/ABOUT_ME``."""
    return abyss_home() / ABOUT_ME_DIRNAME


def about_me_file(category: str) -> Path:
    """Return the markdown file for a category. Raises on unknown."""
    _validate_category(category)
    return about_me_directory() / f"{category}.md"


def index_file() -> Path:
    return about_me_directory() / INDEX_FILE_NAME


def _validate_category(category: str) -> None:
    if category not in ABOUT_ME_CATEGORIES:
        raise ValueError(
            f"unknown ABOUT_ME category: {category!r}. Valid: {', '.join(ABOUT_ME_CATEGORIES)}"
        )


# ---------------------------------------------------------------------------
# Entry model
# ---------------------------------------------------------------------------


@dataclass
class AboutEntry:
    """A single fact about the user.

    ``key`` is unique within a category and acts as the identifier for
    upserts. ``body`` is the markdown that follows the frontmatter
    block; it can be empty.
    """

    key: str
    value: str = ""
    confidence: str = "high"
    source: str = "manual"
    added: str = ""
    last_confirmed: str = ""
    status: str = "confirmed"
    body: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: dict[str, Any], body: str = "") -> AboutEntry:
        known = {
            "key",
            "value",
            "confidence",
            "source",
            "added",
            "last_confirmed",
            "status",
        }
        extra = {k: v for k, v in data.items() if k not in known}
        return cls(
            key=str(data.get("key", "")).strip(),
            value=str(data.get("value", "")),
            confidence=str(data.get("confidence", "high")),
            source=str(data.get("source", "manual")),
            added=str(data.get("added", "")),
            last_confirmed=str(data.get("last_confirmed", "")),
            status=str(data.get("status", "confirmed")),
            body=body.strip(),
            extra=extra,
        )

    def to_frontmatter(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "key": self.key,
            "value": self.value,
            "confidence": self.confidence,
            "source": self.source,
            "added": self.added,
            "last_confirmed": self.last_confirmed,
            "status": self.status,
        }
        payload.update(self.extra)
        return payload


# ---------------------------------------------------------------------------
# Scaffolding
# ---------------------------------------------------------------------------


def ensure_about_me_scaffold() -> Path:
    """Create the directory + empty category files + INDEX. Idempotent.

    Returns the ABOUT_ME directory path.
    """
    directory = about_me_directory()
    directory.mkdir(parents=True, exist_ok=True)
    for category in ABOUT_ME_CATEGORIES:
        path = directory / f"{category}.md"
        if not path.exists():
            heading = CATEGORY_HEADINGS[category]
            path.write_text(f"# {heading}\n\n_아직 항목 없음._\n")
    if not index_file().exists():
        rebuild_index()
    return directory


# ---------------------------------------------------------------------------
# Parsing / serialization
# ---------------------------------------------------------------------------


def _split_frontmatter_blocks(text: str) -> list[tuple[dict[str, Any], str]]:
    """Split a markdown file into ``(frontmatter, body)`` blocks.

    Each block starts with ``---`` on its own line, contains YAML
    until the next ``---``, then markdown body until the next ``---``
    or EOF. The leading "# Heading" preamble is ignored.
    """
    lines = text.splitlines()
    blocks: list[tuple[dict[str, Any], str]] = []
    i = 0
    while i < len(lines):
        if lines[i].strip() == "---":
            yaml_start = i + 1
            yaml_end = yaml_start
            while yaml_end < len(lines) and lines[yaml_end].strip() != "---":
                yaml_end += 1
            if yaml_end >= len(lines):
                # Unterminated frontmatter — skip.
                logger.warning("unterminated frontmatter in ABOUT_ME at line %d", i + 1)
                break
            yaml_text = "\n".join(lines[yaml_start:yaml_end])
            try:
                parsed = yaml.safe_load(yaml_text) or {}
            except yaml.YAMLError as exc:
                logger.warning("invalid frontmatter at line %d: %s", i + 1, exc)
                i = yaml_end + 1
                continue
            body_start = yaml_end + 1
            body_end = body_start
            while body_end < len(lines) and lines[body_end].strip() != "---":
                body_end += 1
            body = "\n".join(lines[body_start:body_end]).strip()
            if isinstance(parsed, dict):
                blocks.append((parsed, body))
            i = body_end
        else:
            i += 1
    return blocks


def load_category(category: str) -> list[AboutEntry]:
    """Return entries for a category. Empty list when file missing."""
    _validate_category(category)
    path = about_me_file(category)
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    entries: list[AboutEntry] = []
    for data, body in _split_frontmatter_blocks(text):
        if not isinstance(data, dict):
            continue
        key = str(data.get("key", "")).strip()
        if not key:
            logger.warning("skipping ABOUT_ME entry without key in %s", path)
            continue
        entries.append(AboutEntry.from_mapping(data, body))
    return entries


def save_category(category: str, entries: list[AboutEntry]) -> None:
    """Write entries back, preserving the category heading."""
    _validate_category(category)
    heading = CATEGORY_HEADINGS[category]
    path = about_me_file(category)
    path.parent.mkdir(parents=True, exist_ok=True)

    chunks: list[str] = [f"# {heading}", ""]
    if not entries:
        chunks.append("_아직 항목 없음._")
        chunks.append("")
    else:
        for entry in entries:
            payload = entry.to_frontmatter()
            yaml_text = yaml.safe_dump(
                payload,
                allow_unicode=True,
                sort_keys=False,
            ).rstrip()
            chunks.append("---")
            chunks.append(yaml_text)
            chunks.append("---")
            if entry.body:
                chunks.append("")
                chunks.append(entry.body)
            chunks.append("")

    path.write_text("\n".join(chunks).rstrip() + "\n", encoding="utf-8")
    rebuild_index()


def upsert_entry(category: str, entry: AboutEntry) -> None:
    """Insert a new entry or replace an existing one with the same key."""
    _validate_category(category)
    if not entry.key.strip():
        raise ValueError("entry.key required")
    if entry.status not in VALID_STATUSES:
        raise ValueError(f"invalid status: {entry.status!r}")
    if entry.confidence not in VALID_CONFIDENCE:
        raise ValueError(f"invalid confidence: {entry.confidence!r}")

    today = date.today().isoformat()
    if not entry.added:
        entry.added = today
    if not entry.last_confirmed and entry.status == "confirmed":
        entry.last_confirmed = today

    entries = load_category(category)
    for index, existing in enumerate(entries):
        if existing.key == entry.key:
            entries[index] = entry
            break
    else:
        entries.append(entry)
    save_category(category, entries)


def list_entries(category: str | None = None) -> dict[str, list[AboutEntry]]:
    """Return ``{category: [entries]}``. ``None`` returns every category."""
    if category is None:
        return {cat: load_category(cat) for cat in ABOUT_ME_CATEGORIES}
    _validate_category(category)
    return {category: load_category(category)}


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------


_INDEX_MAX_VALUE_LEN = 60


def _summarize_entry(entry: AboutEntry) -> str:
    value = entry.value.strip()
    if not value:
        return entry.key
    if len(value) > _INDEX_MAX_VALUE_LEN:
        value = value[:_INDEX_MAX_VALUE_LEN].rstrip() + "…"
    return f"{entry.key}={value}"


def rebuild_index() -> None:
    """Regenerate ``INDEX.md`` from every category file.

    Format::

        # About Me — Index

        - identity: key1=v1, key2=v2
        - relationships: ...
    """
    directory = about_me_directory()
    directory.mkdir(parents=True, exist_ok=True)

    lines = [INDEX_HEADER, "", INDEX_PREAMBLE, ""]
    for category in ABOUT_ME_CATEGORIES:
        entries = load_category(category)
        confirmed = [entry for entry in entries if entry.status == "confirmed"]
        if not confirmed:
            lines.append(f"- {category}: _(empty)_")
            continue
        summary = ", ".join(_summarize_entry(entry) for entry in confirmed)
        lines.append(f"- {category}: {summary}")
    lines.append("")

    index_file().write_text("\n".join(lines), encoding="utf-8")


def load_index() -> str:
    """Return INDEX.md content. Empty string when missing."""
    path = index_file()
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def has_any_entries() -> bool:
    """True when at least one confirmed entry exists across categories."""
    for category in ABOUT_ME_CATEGORIES:
        for entry in load_category(category):
            if entry.status == "confirmed":
                return True
    return False


# ---------------------------------------------------------------------------
# Propose / approve / reject (Phase 2b)
# ---------------------------------------------------------------------------


AUTO_CONFIRM_THRESHOLD = 2


def _find_entry(entries: list[AboutEntry], key: str) -> AboutEntry | None:
    for entry in entries:
        if entry.key == key:
            return entry
    return None


def _allocate_conflict_key(entries: list[AboutEntry], base_key: str) -> str:
    """Return ``<base_key>__conflict_<n>`` where ``n`` is unique."""
    existing_keys = {entry.key for entry in entries}
    index = 1
    while True:
        candidate = f"{base_key}__conflict_{index}"
        if candidate not in existing_keys:
            return candidate
        index += 1


@dataclass
class ProposeResult:
    """Outcome of a ``propose_entry`` call.

    ``action`` is one of:
      - ``"created"`` — new propose entry added
      - ``"updated"`` — existing propose value replaced
      - ``"reinforced"`` — same value proposed again, count incremented
      - ``"auto_confirmed"`` — count reached threshold, promoted to confirmed
      - ``"already_confirmed"`` — same value matches existing confirmed entry
      - ``"conflict"`` — different value vs an existing confirmed entry
    """

    action: str
    category: str
    key: str
    propose_count: int = 1
    conflict_with: str | None = None


def propose_entry(
    category: str,
    key: str,
    value: str,
    *,
    body: str = "",
    confidence: str = "high",
    source: str = "conversation",
) -> ProposeResult:
    """Propose a new fact about the user.

    Behaviour:
    - First propose for ``key`` → status ``propose``, count 1
    - Same value re-proposed → count +=1, auto-confirm at threshold
    - Different value while still ``propose`` → replace value, reset count
    - Same value as existing ``confirmed`` → bump ``last_confirmed``
    - Different value vs ``confirmed`` → add a new ``__conflict_N`` entry,
      record ``conflicts_with`` so the user can resolve it
    """
    _validate_category(category)
    if not key.strip():
        raise ValueError("key required")
    if confidence not in VALID_CONFIDENCE:
        raise ValueError(f"invalid confidence: {confidence!r}")

    today = date.today().isoformat()
    entries = load_category(category)
    existing = _find_entry(entries, key)

    if existing is None:
        entry = AboutEntry(
            key=key,
            value=value,
            body=body,
            confidence=confidence,
            source=source,
            added=today,
            last_confirmed="",
            status="propose",
            extra={"propose_count": 1},
        )
        entries.append(entry)
        save_category(category, entries)
        return ProposeResult(action="created", category=category, key=key, propose_count=1)

    if existing.status == "propose":
        if existing.value.strip() == value.strip():
            count = int(existing.extra.get("propose_count", 1)) + 1
            existing.extra["propose_count"] = count
            existing.source = source
            if count >= AUTO_CONFIRM_THRESHOLD:
                existing.status = "confirmed"
                existing.last_confirmed = today
                existing.extra.pop("propose_count", None)
                save_category(category, entries)
                return ProposeResult(
                    action="auto_confirmed",
                    category=category,
                    key=key,
                    propose_count=count,
                )
            save_category(category, entries)
            return ProposeResult(
                action="reinforced",
                category=category,
                key=key,
                propose_count=count,
            )
        # value differs — replace propose with the newest assertion
        existing.value = value
        existing.body = body
        existing.confidence = confidence
        existing.source = source
        existing.extra["propose_count"] = 1
        save_category(category, entries)
        return ProposeResult(action="updated", category=category, key=key, propose_count=1)

    # existing.status == "confirmed"
    if existing.value.strip() == value.strip():
        existing.last_confirmed = today
        save_category(category, entries)
        return ProposeResult(action="already_confirmed", category=category, key=key)

    conflict_key = _allocate_conflict_key(entries, key)
    entries.append(
        AboutEntry(
            key=conflict_key,
            value=value,
            body=body,
            confidence=confidence,
            source=source,
            added=today,
            last_confirmed="",
            status="propose",
            extra={"propose_count": 1, "conflicts_with": key},
        )
    )
    save_category(category, entries)
    return ProposeResult(
        action="conflict",
        category=category,
        key=conflict_key,
        propose_count=1,
        conflict_with=key,
    )


def approve_entry(category: str, key: str) -> bool:
    """Promote a propose entry to confirmed. Returns False when not found."""
    _validate_category(category)
    entries = load_category(category)
    for entry in entries:
        if entry.key == key:
            entry.status = "confirmed"
            entry.last_confirmed = date.today().isoformat()
            entry.extra.pop("propose_count", None)
            save_category(category, entries)
            return True
    return False


def reject_entry(category: str, key: str) -> bool:
    """Remove an entry (typically a propose) from a category."""
    _validate_category(category)
    entries = load_category(category)
    new_entries = [entry for entry in entries if entry.key != key]
    if len(new_entries) == len(entries):
        return False
    save_category(category, new_entries)
    return True


def update_entry(
    category: str,
    key: str,
    *,
    value: str | None = None,
    body: str | None = None,
    confidence: str | None = None,
) -> bool:
    """Patch an existing entry's value / body / confidence in place."""
    _validate_category(category)
    if confidence is not None and confidence not in VALID_CONFIDENCE:
        raise ValueError(f"invalid confidence: {confidence!r}")

    entries = load_category(category)
    for entry in entries:
        if entry.key == key:
            if value is not None:
                entry.value = value
            if body is not None:
                entry.body = body
            if confidence is not None:
                entry.confidence = confidence
            save_category(category, entries)
            return True
    return False


def count_proposals() -> int:
    """Total entries across all categories with status == 'propose'."""
    total = 0
    for category in ABOUT_ME_CATEGORIES:
        for entry in load_category(category):
            if entry.status == "propose":
                total += 1
    return total


def category_counts() -> dict[str, dict[str, int]]:
    """Return ``{category: {"confirmed": n, "propose": m, "total": k}}``."""
    counts: dict[str, dict[str, int]] = {}
    for category in ABOUT_ME_CATEGORIES:
        entries = load_category(category)
        confirmed = sum(1 for entry in entries if entry.status == "confirmed")
        propose = sum(1 for entry in entries if entry.status == "propose")
        counts[category] = {
            "confirmed": confirmed,
            "propose": propose,
            "total": confirmed + propose,
        }
    return counts


# ---------------------------------------------------------------------------
# Migration from GLOBAL_MEMORY.md
# ---------------------------------------------------------------------------


MIGRATION_PROMPT = """You are migrating a free-form personal memory file
into a structured categorized knowledge base.

The seven valid categories are:
- identity (name, birthday, job, location, contact)
- relationships (family, friends, colleagues)
- preferences (likes, dislikes, communication style)
- routines (daily / weekly rhythms, sleep, exercise)
- current_focus (active projects, what is top of mind right now)
- health (conditions, medications, exercise patterns)
- values (principles, decision-making criteria)

Read the GLOBAL_MEMORY content below and emit a JSON object with the
following shape (use double quotes only; no trailing commas):

{{
  "identity": [{{"key": "kebab-case-id", "value": "concise fact",
                 "body": "optional longer markdown explanation"}}, ...],
  "relationships": [...],
  ...all seven categories...
}}

Rules:
1. Every fact must land in exactly one category. When in doubt, prefer
   ``current_focus``.
2. ``key`` should be a short kebab-case identifier (e.g. "name",
   "wife-name", "morning-routine").
3. ``value`` is the most important short fact — keep it under 80
   characters. ``body`` (optional) holds longer explanation in
   plain markdown.
4. Skip vague meta-comments ("this file is read by every bot",
   "I will update this later"). Keep only durable user facts.
5. If a category has nothing applicable, emit an empty array.
6. Output ONLY the JSON object. No prose, no markdown fences.

GLOBAL_MEMORY content:
---
{content}
---
"""


async def classify_global_memory(
    content: str,
    *,
    model: str = "haiku",
) -> dict[str, list[dict[str, Any]]]:
    """Ask Claude to split free-form GLOBAL_MEMORY into categories.

    Returns a dict ``{category: [{key, value, body}]}``. Raises
    ``ValueError`` if Claude's output can't be parsed.
    """
    import json
    import re
    import tempfile

    from abyss.claude_runner import run_claude

    prompt = MIGRATION_PROMPT.format(content=content.strip())
    with tempfile.TemporaryDirectory() as working_directory:
        response = await run_claude(
            working_directory=working_directory,
            message=prompt,
            timeout=60,
            model=model,
        )

    response = response.strip()
    if "```" in response:
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", response, re.DOTALL)
        if match:
            response = match.group(1).strip()

    try:
        payload = json.loads(response)
    except json.JSONDecodeError as exc:
        raise ValueError(f"failed to parse migration JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError("migration JSON must be an object")

    cleaned: dict[str, list[dict[str, Any]]] = {}
    for category in ABOUT_ME_CATEGORIES:
        items = payload.get(category, [])
        if not isinstance(items, list):
            continue
        cleaned[category] = [item for item in items if isinstance(item, dict)]
    return cleaned


async def migrate_from_global_memory(
    *,
    dry_run: bool = False,
    model: str = "haiku",
) -> dict[str, list[dict[str, Any]]]:
    """Classify ``GLOBAL_MEMORY.md`` into ABOUT_ME categories.

    When ``dry_run`` is True, classification is returned without
    touching disk. Otherwise the result is upserted into category
    files. ``GLOBAL_MEMORY.md`` is left in place.
    """
    from abyss.session import load_global_memory

    content = load_global_memory()
    if not content or not content.strip():
        raise ValueError("GLOBAL_MEMORY.md is empty or missing")

    classification = await classify_global_memory(content, model=model)

    if dry_run:
        return classification

    ensure_about_me_scaffold()
    today = date.today().isoformat()
    for category, items in classification.items():
        for item in items:
            key = str(item.get("key", "")).strip()
            value = str(item.get("value", "")).strip()
            body = str(item.get("body", "")).strip()
            if not key or not value:
                continue
            entry = AboutEntry(
                key=key,
                value=value,
                body=body,
                source="migration:GLOBAL_MEMORY.md",
                added=today,
                last_confirmed=today,
            )
            upsert_entry(category, entry)
    return classification
