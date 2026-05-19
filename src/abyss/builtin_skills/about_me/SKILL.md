# About Me (Shared User Knowledge Base)

You have a structured, shared knowledge base about the user across
seven categories: `identity`, `relationships`, `preferences`,
`routines`, `current_focus`, `health`, `values`. A short index of
confirmed facts is already in your CLAUDE.md system prompt under the
**About Me (Shared, Read-Only)** section.

You have **four tools** to interact with this knowledge base:

- `about_me_propose` — propose a new fact you have just learned
- `about_me_get` — read every entry (confirmed + proposed) in a category
- `about_me_list_categories` — see counts per category
- `about_me_search` — find an entry by substring

## When to call `about_me_propose`

Call this **as soon as you learn a durable new fact** about the user
in conversation. Examples of facts worth proposing:

- Names of family members, colleagues, friends ("wife is 지혜")
- Preferences ("dislikes tables", "prefers short answers")
- Routines ("runs every morning at 6")
- Current projects or focus areas
- Health context the user mentions
- Values, principles, decision rules
- Anything the user explicitly says to remember

**Do not propose** fleeting context (today's weather, what they ate
for lunch), nor world facts unrelated to the user.

### Mechanism

- Same `(category, key, value)` proposed twice → **auto-confirmed**
- Different value while the propose is still pending → latest wins
- Different value vs an existing confirmed entry → **conflict** (a
  new propose is queued with a conflict flag; user resolves it)

### Key naming

Use stable, short kebab-case keys: `name`, `wife-name`, `job-title`,
`morning-routine`, `language-preference`. Treat the key like a
database primary key — re-use the same key when re-asserting the
same kind of fact.

### Inputs

- `category` — required, one of the seven categories
- `key` — required, kebab-case
- `value` — required, short fact (< 80 chars recommended)
- `body` — optional longer markdown explanation
- `confidence` — `high` / `medium` / `low` (default `medium`)

## When to call `about_me_get`

When the index summary doesn't have enough detail to answer well,
load the full category with `about_me_get`. Cheap (a single file read).

## When to call `about_me_search`

When you remember the user mentioned something but don't recall the
exact category — substring search across every entry.

## When to call `about_me_list_categories`

Rarely — when you need a quick overview of which categories have
content. The CLAUDE.md index normally covers this.

## What you CANNOT do

- You cannot directly write `confirmed` entries. Propose first; the
  user (or a second propose) confirms.
- You cannot delete entries. The user does that from the dashboard.
- You cannot edit confirmed values. Propose the new value — it'll
  show up as a conflict for the user to resolve.

## Style

Don't announce that you're "saving to memory" every time. Propose
silently in the background, and only mention it when the user asks
("기억해놓을게" is fine; a long preamble is not).
