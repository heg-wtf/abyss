# cclaw Development Guide

Personal AI assistant: Telegram + Claude Code. Runs locally on Mac.

## Tech Stack

- Python >= 3.11, uv package manager
- Typer (CLI), Rich (output), python-telegram-bot v21+ (async), PyYAML (config), croniter (cron)
- Runs Claude Code CLI as subprocess (`claude -p`), with Python Agent SDK for session continuity

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
- async/await for Telegram handlers and Claude runner
- `CCLAW_HOME` env var overrides `~/.cclaw/` in tests
- Always use `pathlib.Path` and absolute paths. Use `config.py` helpers (`bot_directory()`, `cclaw_home()`)
- Line length limit: 100 characters (ruff)

## Test Rules

- Every module has `tests/test_*.py`
- Mock all Telegram API calls
- Filesystem isolation: `tmp_path` + `monkeypatch.setenv("CCLAW_HOME", ...)`
- Async tests: `@pytest.mark.asyncio`
- `tests/evaluation/`: Real Claude API calls, excluded from CI (`--ignore=tests/evaluation`)

## Code Structure

### Core Modules

| File | Role |
|------|------|
| `cli.py` | Typer entry point, all subcommand definitions |
| `config.py` | Config YAML CRUD, timezone (`get_timezone()`), language (`get_language()`), model mapping |
| `onboarding.py` | `cclaw init` (env check + timezone + language), `cclaw bot add` (token + profile) |
| `claude_runner.py` | `claude -p` subprocess (async), model/skill/MCP injection, `DEFAULT_ALLOWED_TOOLS` (WebFetch/WebSearch/Bash/Read/Write/Edit/Glob/Grep/Agent always allowed), streaming, `--resume` session continuity, SDK-aware wrappers |
| `sdk_client.py` | Python Agent SDK client (`claude-agent-sdk`), `SDKClientPool` (persistent `ClaudeSDKClient` per session, avoids process re-spawn), `get_pool()` / `close_pool()` singleton, legacy `sdk_query()` / `sdk_query_streaming()` |
| `session.py` | Session directories, conversation logs (`conversation-YYMMDD.md`), Claude session ID (`--resume`), memory CRUD (bot + global) |
| `handlers.py` | Telegram handler factory: messages, files, slash commands, streaming, session continuity, group-aware routing |
| `group.py` | Group CRUD (create/delete/list/bind/unbind), shared conversation log, shared workspace, role detection |
| `bot_manager.py` | Multi-bot polling, CLAUDE.md regeneration on start, SDK/QMD lifecycle, cron/heartbeat schedulers, dashboard status (port fallback), graceful shutdown |
| `skill.py` | Skill discovery/linking, `compose_claude_md()` (merges personality + skills + memory + rules), MCP/env injection, QMD auto-injection, `import_skill_from_github()` / `parse_github_url()` (GitHub import) |
| `cron.py` | Cron scheduling (croniter), natural language parsing via Claude haiku, per-job timezone, one-shot support, `edit_cron_job_message()` (message-only edit) |
| `heartbeat.py` | Periodic situation awareness, active hours check, HEARTBEAT_OK detection |
| `token_compact.py` | Compress MEMORY.md/SKILL.md/HEARTBEAT.md via `claude -p` one-shot |
| `backup.py` | AES-256 encrypted zip of `~/.cclaw/` |
| `utils.py` | Message splitting, Markdown-to-HTML conversion, logging, IME-compatible CLI input |

### Built-in Skills

`src/cclaw/builtin_skills/` contains skill templates (SKILL.md + skill.yaml + optional mcp.json). Each subdirectory is one skill. `__init__.py` scans subdirectories as a registry. All follow the same pattern -- adding a new builtin means creating a new subdirectory.

## Key Architecture Patterns

### CLAUDE.md Composition

`compose_claude_md()` in `skill.py` builds the bot's CLAUDE.md from multiple sources:
1. Bot personality, role, goal (from `bot.yaml`)
2. Global memory content (read-only, no file path exposed)
3. Skill instructions (each attached skill's SKILL.md content)
4. QMD skill instructions (auto-injected when `qmd` CLI is available)
5. Memory instructions (file path to MEMORY.md for Claude to read/write)
6. Rules (response language from `config.yaml`, no tables, file save location)
7. Group context (orchestrator: team roster + rules; member: role + shared conversation history)

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

For each bot on `cclaw start`:
1. Regenerate CLAUDE.md (picks up config/skill changes)
2. Check SDK availability, start QMD daemon, then polling

### Streaming

- `bot.yaml` `streaming` field (default: `True`)
- On: `sendMessageDraft` (Bot API 9.3) with cursor marker, 0.5s throttle
- Off: typing action every 4s, batch send on completion
- Fallback: `sendMessageDraft` failure -> `editMessageText`

### Timezone and Language

- `config.yaml` is the single source of truth for both
- `get_timezone()` and `get_language()` are the only accessors (validate, fallback to UTC / Korean)
- Cron jobs: per-job timezone -> config timezone -> UTC
- Heartbeat active hours: uses config timezone

### Group Collaboration

Multi-bot collaboration via Telegram groups using an orchestrator pattern:
- One orchestrator per group manages missions, delegates to members via @mention
- Members execute tasks and report back via @mention to orchestrator
- `group.py`: Group CRUD, `find_group_by_chat_id()`, `bind_group()`, `log_to_shared_conversation()`, shared workspace
- `handlers.py`: Group-aware message routing (orchestrator receives user msgs + member @mentions, members receive orchestrator @mentions)
- `skill.py`: `compose_group_claude_md()` injects team roster for orchestrator, role context for members
- `session.py`: `group_session_directory()` for per-chat group sessions
- `/reset` in group: orchestrator resets all bots' sessions + clears shared conversation, preserves workspace
- `/cancel` in group: orchestrator cancels all bots' running processes
- `/bind <group>` and `/unbind`: associate Telegram chat with a group config
- BotFather Group Privacy must be OFF for bots to receive group messages

### Telegram Message Rules

- Markdown -> HTML via `markdown_to_telegram_html()` before sending
- Falls back to plain text if HTML fails
- Auto-splits at 4096 chars via `split_message()`
- **No markdown tables** -- Telegram cannot render them. Use emoji + text lists instead

## Runtime Data Structure

```
~/.cclaw/
├── config.yaml               # timezone, language, bot list, settings
├── GLOBAL_MEMORY.md          # Shared read-only memory (CLI-managed)
├── bots/<name>/
│   ├── bot.yaml              # token, display_name, personality, role, goal, model, streaming, skills, heartbeat
│   ├── CLAUDE.md             # Generated system prompt (do not edit manually)
│   ├── MEMORY.md             # Bot long-term memory (read/written by Claude Code)
│   ├── cron.yaml             # Cron jobs (schedule, timezone, message)
│   ├── cron_sessions/<job>/  # Cron working directory
│   ├── heartbeat_sessions/   # Heartbeat working directory (HEARTBEAT.md, workspace/)
│   └── sessions/chat_<id>/   # Per-chat session (CLAUDE.md, conversation-YYMMDD.md, workspace/)
├── groups/<name>/
│   ├── group.yaml            # Group config (name, orchestrator, members, telegram_chat_id)
│   ├── conversation/         # Shared conversation logs (YYMMDD.md, date-based)
│   └── workspace/            # Shared workspace (persistent across resets)
├── skills/<name>/            # Skills (SKILL.md required, skill.yaml + mcp.json optional)
└── logs/                     # Daily rotating logs
```

## Release

- **Calendar versioning**: `YYYY.MM.DD` format (e.g., `2026.03.07`). **Two files must be updated together**:
  - `pyproject.toml` → `version = "YYYY.MM.DD"`
  - `src/cclaw/__init__.py` → `__version__ = "YYYY.MM.DD"`
- **Version bump commit**: `🔧 config: bump version to YYYY.MM.DD`
- **Git tag**: `vYYYY.MM.DD` (e.g., `v2026.03.07`). Create after pushing the release commit
- **Release notes**: Write in English
- **Tweet draft**: Multi-line format, one feature per line with emoji. Example:
  ```
  🚀 cclaw v2026.03.07

  ⚡ Node.js bridge for faster Claude queries
  📚 system-wide QMD search
  🌏 timezone/language config
  🗜️ startup auto-compact
  ```

## Engineering Mindset

- Pursue sound engineering, but break boundaries between languages and technologies
- Planning is good, but never hesitate. Conclusions come only from execution, tests, and data
- Always strive to build great products, hype products. We are engineers and influencers

## ClawHouse (Web Dashboard)

`clawhouse/` directory contains the Next.js web dashboard. Tech: Next.js 16 + shadcn/ui + Tailwind CSS + js-yaml.

- Reads/writes `~/.cclaw/` directly via `lib/cclaw.ts` (no database)
- Server components for data pages, client components for editors
- API routes in `src/app/api/` as thin wrappers over `lib/cclaw.ts`
- `cclaw dashboard start/stop/restart/status` subcommands, PID file at `~/.cclaw/clawhouse.pid`
- Status detection: PID file first, then port 3847 fallback (detects externally started dashboards)
- `cclaw status` includes dashboard info (local + network URL)
- `--daemon` for background mode, `--port` for custom port (default 3847)
- Bundled in wheel via `force-include` (clawhouse_data/), works after `pip install`
- Skills split: `BUILTIN_SKILL_NAMES` Set in `lib/cclaw.ts` classifies built-in vs custom
- See **[docs/PLAN-26-0311-CLAWHOUSE.md](docs/PLAN-26-0311-CLAWHOUSE.md)** for full plan and implementation status

## Essential References

Read these docs when working on related areas. They contain critical implementation details not duplicated here.

- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** -- System architecture, module dependency graph, Mermaid flow diagrams (message processing, cron, heartbeat, group routing, shutdown), bot.yaml schema, all 20 design decisions with rationale
- **[docs/TECHNICAL-NOTES.md](docs/TECHNICAL-NOTES.md)** -- Deep implementation details per feature: Claude Code execution modes, Python Agent SDK integration, streaming event parsing, skill MCP config merging, cron scheduler behavior, session continuity (bootstrap/resume/fallback), memory save/load mechanism, QMD auto-injection, group collaboration (orchestrator pattern, auth bypass, shared conversation), IME input handling, emoji width fixes
- **[docs/SECURITY.md](docs/SECURITY.md)** -- Security audit: 35 findings (path traversal, token storage, rate limiting, env var injection, workspace limits). Check before adding file handling, user input, or subprocess code
- **[docs/PLAN-26-0313-GROUP-MISSION.md](docs/PLAN-26-0313-GROUP-MISSION.md)** -- Group collaboration implementation plan: orchestrator pattern, shared conversation/workspace, CLAUDE.md composition, group-aware handlers
