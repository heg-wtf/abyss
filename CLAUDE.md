# abyss Development Guide

Personal AI assistant: PWA + Claude Code. Runs locally on Mac;
reached from the phone over Tailscale.

> **v2026.05.14** — Telegram + the group surface (orchestrator /
> member, `bot_to_bot_mode`, `markdown_to_telegram_html`,
> `allowed_users`, etc.) were removed. Sections below still mention
> them in their original wording; treat those as historical context
> until the per-section rewrite lands. The current surface is the
> mobile PWA + dashboard chat (`abyss.chat_server`), with cron and
> heartbeat results landing in `conversation-*.md` + Web Push.

## Tech Stack

- Python >= 3.11, uv package manager
- Typer (CLI), Rich (output), PyYAML (config), croniter (cron)
- LLM: Claude Code CLI (`claude -p`) + Python Agent SDK — single backend (full agent: tools, MCP, skills, `--resume`)
- Delivery: in-process `chat_server` (aiohttp HTTP/SSE on 127.0.0.1:3848) + Web Push via `pywebpush`

## Dev Commands

```bash
uv sync                              # Install dependencies
uv run pytest                        # Run tests
uv run pytest -v                     # Verbose
uv run pytest tests/test_config.py   # Single file
uv run ruff check --fix . && uv run ruff format .  # Lint + format
```

## Code Style

- No abbreviations. Use full words: `session_directory` not `sess_dir`, `bot_config` not `bc`
- Type hints with `from __future__ import annotations`
- async/await for chat handlers and Claude runner
- `ABYSS_HOME` env var overrides `~/.abyss/` in tests
- Always use `pathlib.Path` and absolute paths. Use `config.py` helpers (`bot_directory()`, `abyss_home()`)
- Line length limit: 100 characters (ruff)

## Test Rules

- Every module has `tests/test_*.py`
- Filesystem isolation: `tmp_path` + `monkeypatch.setenv("ABYSS_HOME", ...)`
- Async tests: `@pytest.mark.asyncio`
- `tests/evaluation/`: Real Claude API calls, excluded from CI (`--ignore=tests/evaluation`)

## Git

- Commit messages in English (gitmoji format, e.g., `🔥 remove: strip legacy cclaw paths`)
- Subject line ≤ 72 chars, body optional for non-obvious "why"

## Code Structure

### Core Modules

| File | Role |
|------|------|
| `cli.py` | Typer entry point, all subcommand definitions |
| `config.py` | Config YAML CRUD, timezone (`get_timezone()`), language (`get_language()`), model mapping |
| `onboarding.py` | `abyss init` (env check + timezone + language), `abyss bot add` (token + profile) |
| `claude_runner.py` | `claude -p` subprocess (async), model/skill/MCP injection, `DEFAULT_ALLOWED_TOOLS` (WebFetch/WebSearch/Bash/Read/Write/Edit/Glob/Grep/Agent always allowed), streaming, `--resume` session continuity, SDK-aware wrappers |
| `sdk_client.py` | Python Agent SDK client (`claude-agent-sdk`), `SDKClientPool` (persistent `ClaudeSDKClient` per session, avoids process re-spawn), `get_pool()` / `close_pool()` singleton, legacy `sdk_query()` / `sdk_query_streaming()` |
| `session.py` | Session directories, conversation logs (`conversation-YYMMDD.md`), Claude session ID (`--resume`), memory CRUD (bot + global) |
| `handlers.py` | Chat handler factory: messages, files, slash commands, streaming, session continuity |
| `group.py` | Group CRUD (create/delete/list), shared conversation log, shared workspace, role detection |
| `bot_manager.py` | Multi-bot lifecycle, CLAUDE.md regeneration on start, SDK/QMD lifecycle, cron/heartbeat schedulers, internal `ChatServer` lifecycle, dashboard status (port fallback), graceful shutdown |
| `chat_core.py` | Backend-agnostic chat orchestration shared by PWA handlers and the dashboard chat. `prepare_session_context` + `process_chat_message` (SDK pool first, subprocess + bootstrap fallback) |
| `chat_server.py` | Internal HTTP/SSE server (aiohttp) for the abysscope dashboard chat. Routes: `/bots`, `/sessions`, `/messages`, `/chat` (SSE), `/upload`, `/files/{id}`, `/transcribe` (ElevenLabs Scribe v2 STT proxy), `/speak` (ElevenLabs TTS streaming proxy), `/scribe-token` (ElevenLabs WebSocket auth token). Origin allowlist + CORS middleware, MIME sniffing, per-session asyncio locks. Shared `aiohttp.ClientSession` created in `start()`, closed in `stop()` |
| `dashboard.py` | abysscope subprocess lifecycle (locate / build / spawn / stop / PID-file tracking). Imported by `bot_manager` during `abyss start` |
| `dashboard_ui.py` | Rich-powered checklist UI (`BuildProgress`, `BuildStep`, `StepStatus`) for the `abyss start` / `abyss restart` boot sequence, plus `tail()` log helper |
| `tool_metrics.py` | Per-bot tool execution metrics — append jsonl events under `bots/<name>/tool_metrics/`, aggregate per-tool latency p50/p95/p99, daily rotation with retention |
| `skill.py` | Skill discovery/linking, `compose_claude_md()` (merges personality + skills + memory + rules), MCP/env injection, QMD auto-injection, `import_skill_from_github()` / `parse_github_url()` (GitHub import) |
| `cron.py` | Cron scheduling (croniter), natural language parsing via Claude haiku, per-job timezone, one-shot support, `edit_cron_job_message()` (message-only edit) |
| `heartbeat.py` | Periodic situation awareness, active hours check, HEARTBEAT_OK detection |
| `token_compact.py` | Compress MEMORY.md/SKILL.md/HEARTBEAT.md via `claude -p` one-shot |
| `backup.py` | AES-256 encrypted zip of `~/.abyss/` |
| `utils.py` | Message splitting, logging, IME-compatible CLI input |
| `conversation_index.py` | SQLite FTS5 index over conversation markdown logs. Per-bot DB at `bots/<name>/conversation.db`, per-group at `groups/<name>/conversation.db`. Markdown stays the source of truth |
| `mcp_servers/conversation_search.py` | stdio MCP server exposing `search_conversations` tool over the FTS5 index. Spawned automatically per Claude call when FTS5 is available |
| `hooks/log_tool_metrics.py` | Claude Code `PostToolUse` / `PostToolUseFailure` hook — reads JSON payload from stdin, resolves bot name from cwd, appends event via `tool_metrics.append_event` |
| `hooks/precompact_hook.py` | Claude Code `PreCompact` hook — runs `token_compact` for the active bot before host compaction, never blocks (always exits 0) |
| `llm/base.py` | `LLMBackend` Protocol, `LLMRequest`, `LLMResult`. Backend-agnostic envelope used by handlers / cron / heartbeat |
| `llm/registry.py` | `register`, `get_backend`, `get_or_create` (per-bot cache), `close_all` for shutdown |
| `llm/claude_code.py` | `ClaudeCodeBackend` wrapping `claude_runner` (subprocess + Agent SDK). Only registered backend |

### Built-in Skills

`src/abyss/builtin_skills/` contains skill templates (SKILL.md + skill.yaml + optional mcp.json). Each subdirectory is one skill. `__init__.py` scans subdirectories as a registry. All follow the same pattern -- adding a new builtin means creating a new subdirectory.

Two skills are special and not exposed as user-installable:
- `conversation_search/` — auto-injected MCP skill (`status: builtin`) when bundled SQLite supports FTS5. Backed by `mcp_servers/conversation_search.py`.
- `code_review/` — CLI skill that runs `claude ultrareview` on a PR or path, restricted to `Bash(claude ultrareview:*)`.

## Key Architecture Patterns

### CLAUDE.md Composition

`compose_claude_md()` in `skill.py` builds the bot's CLAUDE.md from multiple sources:
0. Isolation directive (ignore `~/.claude/CLAUDE.md` and parent CLAUDE.md files)
1. Bot personality, role, goal (from `bot.yaml`)
2. Global memory content (read-only, no file path exposed)
3. Skill instructions (each attached skill's SKILL.md content)
4. QMD skill instructions (auto-injected when `qmd` CLI is available)
5. Memory instructions (file path to MEMORY.md for Claude to read/write)
6. Rules (response language from `config.yaml`, no tables, file save location)

This is the only way to inject system instructions into `claude -p`, which auto-reads `CLAUDE.md` from its working directory.

### Session Continuity

- **SDK Pool mode (preferred)**: `SDKClientPool` keeps a persistent `ClaudeSDKClient` per session key (`bot:chat_id`). First message creates the client, subsequent messages reuse it (no process re-spawn, 1-2s faster). Pool auto-loads/saves `session_id` from `.claude_session_id` via `session_directory` param.
- **Subprocess fallback**: `--session-id <uuid>` for first message, `--resume <session_id>` for subsequent. Used when SDK is unavailable or pool query fails.
- Fallback: if resume fails, clears session ID, closes pool session, and retries with bootstrap
- `/cancel` tries `pool.interrupt()` first, then `cancel_process()` subprocess fallback
- `/reset` closes pool session so fresh client is created
- Session ID stored in `sessions/chat_<id>/.claude_session_id`
- Shutdown: `close_pool()` closes all persistent clients before killing subprocesses

### Startup Sequence

For each bot on `abyss start`:
1. Regenerate CLAUDE.md (picks up config/skill changes)
2. Check SDK availability, start QMD daemon, then start `ChatServer`

### Streaming

- `bot.yaml` `streaming` field (default: `True`)
- On: per-token SSE stream from SDK pool, 0.5s throttle on dashboard edits
- Off: batch send on completion

### Timezone and Language

- `config.yaml` is the single source of truth for both
- `get_timezone()` and `get_language()` are the only accessors (validate, fallback to UTC / Korean)
- Cron jobs: per-job timezone -> config timezone -> UTC
- Heartbeat active hours: uses config timezone

### LLM Backend Selection

`abyss.llm.LLMBackend` Protocol with a single registered backend:

- **claude_code** (only): wraps `claude_runner.run_claude_with_sdk` and `run_claude_streaming_with_sdk`. Full agent (tools, MCP, skills, `--resume`).

> v2026.05.15 — the OpenAI-compatible (`openai_compat` / `openrouter` / `minimax`) backends were removed. Bots that still set `backend.type` to one of those receive a clear migration error at startup. The `LLMBackend` Protocol + registry stay in place to make future full-agent backends drop-in.

Per-bot caching via `get_or_create(bot_name, bot_config)` shares SDK pools across handler / cron / heartbeat call sites. `bot_config` is refreshed in-place on cached returns; backend-type changes recreate the instance. `bot_manager.close_all()` on shutdown.

`/cancel` calls `cached_backend(bot_name).cancel(session_key)` and falls through to legacy Claude Code paths for cold bots.

### Conversation Search (FTS5)

Every bot and group has a SQLite FTS5 index at `bots/<name>/conversation.db` / `groups/<name>/conversation.db`. Markdown remains the source of truth — the index is a rebuildable cache.

- Append on `session.log_conversation` (best-effort, swallowed failures)
- Auto-injected as `mcp__conversation_search__search_conversations` when the bundled SQLite supports FTS5
- Bot dir resolution: `_resolve_bot_dir_from_working_directory` walks up parents until it finds a directory whose parent is named `bots`, so DM / cron / heartbeat working dirs all resolve to the same per-bot DB
- `abyss reindex --bot|--group|--all` wipes and rebuilds from markdown (also wipes when source dir is missing — no stale rows)
- `abyss doctor` reports FTS5 availability

## Runtime Data Structure

```
~/.abyss/
├── config.yaml               # timezone, language, bot list, settings
├── GLOBAL_MEMORY.md          # Shared read-only memory (CLI-managed)
├── bots/<name>/
│   ├── bot.yaml              # display_name, personality, role, goal, model, streaming, skills, heartbeat, backend
│   ├── CLAUDE.md             # Generated system prompt (do not edit manually)
│   ├── MEMORY.md             # Bot long-term memory (read/written by Claude Code)
│   ├── conversation.db       # SQLite FTS5 index (auto-built; rebuild via `abyss reindex --bot <name>`)
│   ├── cron.yaml             # Cron jobs (schedule, timezone, message)
│   ├── cron_sessions/<job>/  # Cron working directory
│   ├── heartbeat_sessions/   # Heartbeat working directory (HEARTBEAT.md, workspace/)
│   └── sessions/chat_<id>/   # Per-chat session (CLAUDE.md, conversation-YYMMDD.md, workspace/)
├── groups/<name>/
│   ├── group.yaml            # Group config (name, orchestrator, members)
│   ├── conversation/         # Shared conversation logs (YYMMDD.md, date-based)
│   ├── conversation.db       # Group FTS5 index (auto-built; rebuild via `abyss reindex --group <name>`)
│   └── workspace/            # Shared workspace (persistent across resets)
├── skills/<name>/            # Skills (SKILL.md required, skill.yaml + mcp.json optional)
└── logs/                     # Daily rotating logs
```

## Release

- **Calendar versioning**: `YYYY.MM.DD` format (e.g., `2026.03.07`). **Two files must be updated together**:
  - `pyproject.toml` → `version = "YYYY.MM.DD"`
  - `src/abyss/__init__.py` → `__version__ = "YYYY.MM.DD"`
- **Version bump commit**: `🔧 config: bump version to YYYY.MM.DD`
- **Git tag**: `vYYYY.MM.DD` (e.g., `v2026.03.07`). Create after pushing the release commit
- **Release notes**: Write in English
- **Tweet draft**: Multi-line format, one feature per line with emoji. Example:
  ```
  🚀 abyss v2026.03.07

  ⚡ Node.js bridge for faster Claude queries
  📚 system-wide QMD search
  🌏 timezone/language config
  🗜️ startup auto-compact
  ```
- **Landing page update**: After release, update `docs/landing/` for abyss.heg.wtf based on the released content

## Engineering Mindset

- Pursue sound engineering, but break boundaries between languages and technologies
- Planning is good, but never hesitate. Conclusions come only from execution, tests, and data
- Always strive to build great products, hype products. We are engineers and influencers

## Abysscope (Web Dashboard)

`abysscope/` directory contains the Next.js web dashboard. Tech: Next.js 16 + shadcn/ui + Tailwind CSS + js-yaml.

- Reads/writes `~/.abyss/` directly via `lib/abyss.ts` (no database)
- Server components for data pages, client components for editors
- API routes in `src/app/api/` as thin wrappers over `lib/abyss.ts`
- Started automatically as a child subprocess of `abyss start` (v2026.05.15 retired the standalone `abyss dashboard` subcommand). PID file at `~/.abyss/abysscope.pid`
- Status detection: PID file first, then port 3847 fallback (detects externally started dashboards)
- `abyss status` includes dashboard info (local + network URL)
- `abyss start --foreground` runs inline; `--port` overrides the dashboard port (default 3847)
- Bundled in wheel via `force-include` (abysscope_data/), works after `pip install`
- Cron editor: inline view/edit toggle in bot detail, supports recurring + one-shot jobs, skills picker
- Log management: view, filter, delete (single/bulk/by-age), daemon log truncate
- Settings: timezone/language Select dropdowns, Home directory with Finder open link, bot paths as relative links
- `PathLink` component: clickable paths that open Finder via `/api/open-finder`
- Skills: built-in (read-only) vs custom (full CRUD: add/edit/delete), classified by `isBuiltin` flag from API
- Session management: per-session delete in bot detail, per-conversation-file delete in conversation viewer
- Memory editor: markdown rendering in view mode (react-markdown + @tailwindcss/typography), raw edit mode
- Sidebar: collapsible Bots/Skills sections (localStorage-persisted), theme toggle with emoji icon
- Dashboard chat: in-browser chat UI talks to internal `ChatServer` (aiohttp, started by `bot_manager`). SSE token streaming via `/chat`, image + PDF uploads via `/upload`, served back via `/files/{id}`. Uses the SDK pool / session continuity via `chat_core`. Single entry point — sidebar `New` opens a base-ui `Menu` listing all bots; clicking one creates the session for that bot. The right-panel header shows the active session's bot avatar + display name + session ID. `display_name` falls back through `display_name → telegram_botname (legacy shim) → bot_name`, applied in both `/chat/bots` and `/chat/sessions` responses so the picker, session list, and message header stay consistent with the sidebar
- Voice mode: mic button in chat header opens a right sidebar with an animated Orb (ElevenLabs Orb component). `useVoiceMode` hook manages the STT→LLM→TTS cycle. ElevenLabs Scribe v2 WebSocket STT via `/api/chat/scribe-token` → `use-voice-mode.ts`. Transcribed text sent to `/api/chat` with `voice_mode: true`; Python `_handle_chat` appends a Korean spoken-style instruction to the message. TTS reply streamed from `/api/chat/speak` (ElevenLabs TTS proxy) and played via Web Audio API. Orb `colors` prop is theme-aware (`useTheme`): dark → white tones, light → black tones. Auto-restart loop: recording → processing → speaking → recording. Messenger-style timestamps shown on chat messages (`toLocaleTimeString("ko-KR")`)
- `abyss start` / `abyss restart` show a single Rich `BuildProgress` checklist covering prepare bots → SDK availability → QMD daemon → API server → install deps → build dashboard → start dashboard → cron / heartbeat scheduler attach, instead of streaming raw `next build` output

## Tool Metrics + Hooks

`tool_metrics.py` records each Claude Code tool call (latency, success/error). Wired through Claude Code hooks declared in the bot's CLAUDE.md / settings:

- `hooks/log_tool_metrics.py` — runs on `PostToolUse` and `PostToolUseFailure`. Resolves the active bot from `cwd`, writes `bots/<name>/tool_metrics/YYYY-MM-DD.jsonl`. `aggregate(bot_name)` returns per-tool count + p50/p95/p99 for the dashboard. Daily files rotate after `RETENTION_DAYS`
- `hooks/precompact_hook.py` — runs on `PreCompact`. Invokes `token_compact.run_compact` for the active bot before Claude Code compacts in-process. Always exits 0 so a slow / failing compact never blocks the host run

Both hooks resolve `bot_name` by walking parents of `cwd` until they find a directory whose parent is `bots/`, so DM / cron / heartbeat working dirs all map to the same bot.

## Essential References

Read these docs when working on related areas. They contain critical implementation details not duplicated here.

- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** -- System architecture, module dependency graph, Mermaid flow diagrams (message processing, cron, heartbeat, shutdown), bot.yaml schema, all design decisions with rationale
- **[docs/TECHNICAL-NOTES.md](docs/TECHNICAL-NOTES.md)** -- Deep implementation details per feature: Claude Code execution modes, Python Agent SDK integration, streaming event parsing, skill MCP config merging, cron scheduler behavior, session continuity (bootstrap/resume/fallback), memory save/load mechanism, QMD auto-injection, IME input handling, emoji width fixes
- **[docs/SECURITY.md](docs/SECURITY.md)** -- Security audit: 35 findings (path traversal, token storage, rate limiting, env var injection, workspace limits). Check before adding file handling, user input, or subprocess code
