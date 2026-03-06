# cclaw Development Guide

## Project Overview

Personal AI assistant powered by Telegram + Claude Code. A CLI tool that runs locally on Mac.

## Tech Stack

- Python >= 3.11, uv package management
- Typer (CLI), Rich (output), python-telegram-bot v21+ (async), PyYAML (config), croniter (cron scheduling)
- Runs Claude Code CLI as a subprocess (`claude -p`)

## Key Commands

```bash
uv sync                      # Install dependencies
uv run cclaw                 # Show ASCII art banner
uv run cclaw --help          # CLI help
uv run cclaw doctor          # Environment check
uv run cclaw init            # Onboarding
uv run cclaw start           # Run bots
uv run cclaw bot list        # List bots (with model info)
uv run cclaw bot model <name>       # Show current model
uv run cclaw bot model <name> opus  # Change model
uv run cclaw bot streaming <name>        # Show streaming status
uv run cclaw bot streaming <name> off    # Toggle streaming on/off
uv run cclaw skills                  # List all skills (installed + available builtins)
uv run cclaw skills add              # Create skill interactively
uv run cclaw skills setup <name>     # Setup/activate skill
uv run cclaw skills edit <name>      # Edit SKILL.md
uv run cclaw skills remove <name>    # Remove skill
uv run cclaw skills test <name>      # Test requirements
uv run cclaw skills builtins         # List built-in skills
uv run cclaw skills install          # List built-in skills (same as builtins)
uv run cclaw skills install <name>   # Install built-in skill
uv run cclaw cron list <bot>         # List cron jobs
uv run cclaw cron add <bot>          # Create cron job interactively
uv run cclaw cron remove <bot> <job> # Remove cron job
uv run cclaw cron enable <bot> <job> # Enable cron job
uv run cclaw cron disable <bot> <job> # Disable cron job
uv run cclaw cron run <bot> <job>    # Run cron job immediately (test)
uv run cclaw heartbeat status        # Show heartbeat status per bot
uv run cclaw heartbeat enable <bot>  # Enable heartbeat
uv run cclaw heartbeat disable <bot> # Disable heartbeat
uv run cclaw heartbeat run <bot>     # Run heartbeat immediately (test)
uv run cclaw heartbeat edit <bot>    # Edit HEARTBEAT.md
uv run cclaw bot compact <name>      # Compact MD files to save tokens
uv run cclaw bot compact <name> -y   # Compact without confirmation
uv run cclaw memory show <bot>       # Show memory contents
uv run cclaw memory edit <bot>       # Edit MEMORY.md
uv run cclaw memory clear <bot>      # Clear memory
uv run cclaw global-memory show      # Show global memory contents
uv run cclaw global-memory edit      # Edit GLOBAL_MEMORY.md (regenerates all bots)
uv run cclaw global-memory clear     # Clear global memory (regenerates all bots)
uv run cclaw logs            # Show today's log
uv run cclaw logs -f         # Tail mode
uv run cclaw logs clean              # Delete logs older than 7 days
uv run cclaw logs clean -d 30        # Delete logs older than 30 days
uv run cclaw logs clean --dry-run    # Preview deletions
uv run cclaw backup                  # Backup ~/.cclaw/ to encrypted zip
uv run pytest                # Run tests
uv run pytest -v             # Run tests (verbose)
uv run pytest tests/test_config.py  # Run individual test

# When installed via pip/pipx, run directly without uv run
cclaw --help
cclaw start
pytest
```

## Code Structure

- `src/cclaw/cli.py` - Typer app entry point, ASCII art banner, all command definitions (skills, bot, cron, heartbeat, memory, global-memory subcommands)
- `src/cclaw/config.py` - `~/.cclaw/` configuration management (YAML), model version mapping (`MODEL_VERSIONS`, `model_display_name()`)
- `src/cclaw/onboarding.py` - Environment check, token validation, bot creation wizard
- `src/cclaw/claude_runner.py` - `claude -p` subprocess execution (async, path resolution via `shutil.which`, process tracking + `cancel_all_processes()` for graceful shutdown, model selection, skill MCP/env injection via `_prepare_skill_config()`, streaming output, `--resume`/`--session-id` session continuity, bridge-aware wrappers `run_claude_with_bridge`/`run_claude_streaming_with_bridge`)
- `src/cclaw/bridge.py` - Node.js bridge client (Unix socket JSONL protocol, bridge process lifecycle start/stop/health, pipe draining threads, `bridge_query`/`bridge_query_streaming` functions, `_bridge_directory()` auto-install from package data)
- `src/cclaw/bridge_data/server.mjs` - Bridge server bundled with package (copied to `~/.cclaw/bridge/` at runtime)
- `bridge/server.mjs` - Bridge server source (development copy, synced to bridge_data and runtime)
- `src/cclaw/session.py` - Session directory/conversation log/workspace management, Claude session ID management (`get`/`save`/`clear_claude_session_id`), daily conversation rotation (`conversation-YYMMDD.md`, legacy `conversation.md` fallback), bot-level memory CRUD (`load_bot_memory`/`save_bot_memory`/`clear_bot_memory`), global memory CRUD (`load_global_memory`/`save_global_memory`/`clear_global_memory`), `collect_session_chat_ids()` for proactive message fallback
- `src/cclaw/handlers.py` - Telegram handler factory (slash commands + messages + file receive/send + model change (with version display) + process cancel + /skills unified management (list/attach/detach/builtins) + /cron management (list/add natural language/run/remove/enable/disable) + /heartbeat management + /memory management + /compact token compaction + streaming response + /streaming toggle + session continuity (`_prepare_session_context`, `_call_with_resume_fallback`) + `set_bot_commands` command menu registration)
- `src/cclaw/bot_manager.py` - Multi-bot polling, launchd daemon, per-bot error isolation, cron/heartbeat scheduler integration, graceful shutdown (`cancel_all_processes()` before `application.stop()`)
- `src/cclaw/heartbeat.py` - Heartbeat periodic situation awareness (config CRUD, active hours check, HEARTBEAT.md management, HEARTBEAT_OK detection, session chat ID fallback for result delivery, scheduler loop)
- `src/cclaw/cron.py` - Cron schedule automation (cron.yaml CRUD, croniter-based schedule matching, per-job timezone support via `resolve_job_timezone()`, one-shot support with auto-disable, session chat ID fallback for result delivery, scheduler loop, natural language parsing via `parse_natural_language_schedule()` using Claude haiku one-shot, `resolve_default_timezone()` from GLOBAL_MEMORY.md/system/UTC fallback, `generate_unique_job_name()` with conflict resolution)
- `src/cclaw/skill.py` - Skill management (discovery/loading/creation/deletion/builtin installation, bot-skill linking, CLAUDE.md composition (global memory + memory instructions + Telegram formatting rules), MCP/env variable merging, builtin/custom origin detection)
- `src/cclaw/builtin_skills/__init__.py` - Built-in skill registry (scans subdirectories for templates)
- `src/cclaw/builtin_skills/imessage/` - iMessage built-in skill template (SKILL.md, skill.yaml)
- `src/cclaw/builtin_skills/reminders/` - Apple Reminders built-in skill template (SKILL.md, skill.yaml)
- `src/cclaw/builtin_skills/naver-map/` - Naver Map built-in skill template (SKILL.md, skill.yaml, knowledge type, web URL based)
- `src/cclaw/builtin_skills/image/` - Image processing built-in skill template (SKILL.md, skill.yaml, slimg CLI)
- `src/cclaw/builtin_skills/best-price/` - Best price search built-in skill template (SKILL.md, skill.yaml, knowledge type, web search based)
- `src/cclaw/builtin_skills/supabase/` - Supabase MCP built-in skill template (SKILL.md, skill.yaml, mcp.json, DB/Storage/Edge Functions with no-deletion guardrails)
- `src/cclaw/builtin_skills/gmail/` - Gmail built-in skill template (SKILL.md, skill.yaml, gogcli-based search/read/send)
- `src/cclaw/builtin_skills/gcalendar/` - Google Calendar built-in skill template (SKILL.md, skill.yaml, gogcli-based events/scheduling)
- `src/cclaw/builtin_skills/twitter/` - Twitter/X MCP built-in skill template (SKILL.md, skill.yaml, mcp.json, tweet posting/search via @enescinar/twitter-mcp)
- `src/cclaw/builtin_skills/jira/` - Jira MCP built-in skill template (SKILL.md, skill.yaml, mcp.json, issue search/create/update/transition via mcp-atlassian)
- `src/cclaw/builtin_skills/naver-search/` - Naver Search built-in skill template (SKILL.md, skill.yaml, naver-cli based 6-type search: local/book/blog/cafe/news/shopping)
- `src/cclaw/builtin_skills/kakao-local/` - Kakao Local built-in skill template (SKILL.md, skill.yaml, kakao-cli based address/coordinate/keyword search)
- `src/cclaw/builtin_skills/dart/` - DART corporate disclosure built-in skill template (SKILL.md, skill.yaml, dartcli based company/finance/filing search)
- `src/cclaw/builtin_skills/translate/` - Translate built-in skill template (SKILL.md, skill.yaml, translatecli based Gemini translation with format preservation)
- `src/cclaw/builtin_skills/daiso/` - Daiso Mall built-in skill template (SKILL.md, skill.yaml, daiso-cli based product search)
- `src/cclaw/backup.py` - Encrypted backup (AES-256 zip via pyzipper, file collection with pid/pycache exclusion)
- `src/cclaw/token_compact.py` - Token compaction (estimate_token_count, collect_compact_targets for MEMORY.md/user SKILL.md/HEARTBEAT.md, compact_content via claude -p one-shot, run_compact sequential with error isolation, format_compact_report, save_compact_results)
- `src/cclaw/utils.py` - Message splitting, Markdown to HTML conversion, logging setup, IME-compatible CLI input (`prompt_input`, `prompt_multiline`)

## Code Style

- Avoid abbreviations. Use full text (e.g., `session_directory`, `bot_config`)
- Use type hints (`from __future__ import annotations`)
- async/await patterns (Telegram, Claude Runner)
- `CCLAW_HOME` environment variable for test path override
- Use absolute paths everywhere. Access bot directories via helper functions like `config.py`'s `bot_directory(name)`. Prefer `pathlib.Path`

## Test Rules

- Every module has a corresponding test file (`tests/test_*.py`)
- Mock all Telegram API calls
- Filesystem isolation via `tmp_path` + `monkeypatch`
- Async tests with `pytest-asyncio`
- **Evaluation tests** (`tests/evaluation/`): Real Claude API calls for quality assessment (excluded from CI via `--ignore=tests/evaluation`). Run manually: `uv run pytest tests/evaluation/ -v`

## Telegram Message Formatting

- Claude responses in Markdown are converted to HTML via `utils.markdown_to_telegram_html()` before sending
- Conversion targets: `**bold**`, `*italic*`, `` `code` ``, ` ```code blocks``` `, `## headings`, `[link](url)`
- Falls back to plain text if HTML send fails
- Auto-splits via `split_message()` when exceeding 4096 characters
- **Markdown tables are forbidden**: Telegram does not render tables, so `compose_claude_md()` Rules enforce "emoji + text list" format instead

## Telegram Command Menu

- `set_bot_commands()` registers the `BOT_COMMANDS` list with Telegram (called after `start_polling`)
- When users type `/`, an autocomplete menu of commands is displayed
- Automatically registered on every bot start, so adding/changing commands only requires a restart

## Streaming Response

- Controlled by the `streaming` field in `bot.yaml` (default: `DEFAULT_STREAMING = True`)
- Runtime toggle via Telegram `/streaming on|off` command or CLI `cclaw bot streaming <name> on|off`
- **Streaming mode (on)**: `run_claude_streaming()` -> `sendMessageDraft` (Bot API 9.3) -> draft bubble with cursor marker `▌` -> final `sendMessage`
- **Non-streaming mode (off)**: `run_claude()` -> typing action every 4 seconds -> batch send on completion
- **Draft streaming**: Uses `sendMessageDraft(chat_id, draft_id=DRAFT_ID, text)` to show real-time draft bubble while generating. Draft auto-clears before final message. Same `draft_id` ensures smooth animated transitions between updates
- **Fallback**: If `sendMessageDraft` fails (e.g., TEXTDRAFT_PEER_INVALID), automatically falls back to `editMessageText` approach
- Throttling: draft updates at 0.5 second intervals (`STREAM_THROTTLE_SECONDS`)
- First draft sent after at least 10 characters accumulated (`STREAM_MIN_CHARS_BEFORE_SEND`)

## Session Continuity

- Each message runs `claude -p` as a new process, but maintains conversation context via `--resume` / `--session-id` flags
- **First message**: Starts new session with `--session-id <uuid>`. Includes GLOBAL_MEMORY.md + MEMORY.md + last 20 turns from conversation files as bootstrap prompt
- **Subsequent messages**: Continues session with `--resume <session_id>`
- **Fallback**: If `--resume` fails (session expired, etc.), automatically deletes session_id and retries with bootstrap
- **Reset**: `/reset` or `/resetall` also deletes the `.claude_session_id` file
- Session ID stored in `sessions/chat_<id>/.claude_session_id`
- `_prepare_session_context()`: Determines resume/bootstrap (bootstrap order: global memory -> bot memory -> conversation history -> message)
- `_call_with_resume_fallback()`: Handles fallback on resume failure (same bootstrap order)

## Node.js Bridge

- **Purpose**: Runs Claude Code queries via the Agent SDK's v1 `query()` function inside a long-lived Node.js process, avoiding Python subprocess spawn overhead per message
- **Architecture**: Python (cclaw) → Unix socket (JSONL) → Node.js bridge (server.mjs) → Claude Agent SDK `query()` → Claude Code
- **Lifecycle**: `bot_manager.py` calls `start_bridge()` before polling, `stop_bridge()` on shutdown
- **Fallback**: If bridge is unavailable or errors, transparently falls back to `claude -p` subprocess
- **Session retry**: If a stale session ID causes an error, bridge automatically retries without session options
- **Logging**: Bridge logs to `/tmp/cclaw-bridge.log` (configurable via `CCLAW_BRIDGE_LOG`). Python drains stdout/stderr via background threads
- **Doctor**: `cclaw doctor` shows bridge process status, socket connectivity, and SDK version
- **Files**: `bridge/server.mjs` (source) → `src/cclaw/bridge_data/server.mjs` (packaged) → `~/.cclaw/bridge/server.mjs` (runtime, auto-overwritten on start)
- **SDK v2 preview**: `unstable_v2_createSession`/`unstable_v2_prompt` exist but do NOT support CLAUDE.md or Bash tools (alpha API, direct Anthropic API call). Will be reconsidered when v2 matures. See: https://platform.claude.com/docs/en/agent-sdk/typescript-v2-preview

## Bot-Level Long-Term Memory

- When user requests "remember this", the bot saves to `MEMORY.md`
- `MEMORY.md` is managed per bot (`~/.cclaw/bots/<name>/MEMORY.md`), shared across all chat sessions
- **Saving**: `compose_claude_md()` includes memory instructions + MEMORY.md absolute path in CLAUDE.md -> Claude Code directly appends to MEMORY.md via file write tool
- **Loading**: On new session bootstrap, GLOBAL_MEMORY.md + MEMORY.md + conversation history are injected into the prompt (global memory -> bot memory -> conversation history -> new message order)
- **Management**: Telegram `/memory` command (show contents, `/memory clear` to reset) + CLI `cclaw memory show|edit|clear <bot>`

## Global Memory

- `GLOBAL_MEMORY.md` is stored at `~/.cclaw/GLOBAL_MEMORY.md`, shared across all bots (read-only for bots)
- Stores timezone, user preferences, and other information all bots should reference
- **CLAUDE.md injection**: `compose_claude_md()` inserts a "Global Memory (Read-Only)" section without the file path, preventing Claude from modifying it
- **Bootstrap injection**: On new session bootstrap, global memory is injected before bot memory
- **Management**: CLI only (`cclaw global-memory show|edit|clear`). Not editable via Telegram
- Editing or clearing regenerates all bots' CLAUDE.md and propagates to sessions

## Runtime Data Structure

```
~/.cclaw/
├── config.yaml           # Global config (bot list, log_level, command_timeout)
├── cclaw.pid             # Running PID
├── GLOBAL_MEMORY.md      # Global memory (shared across all bots, read-only for bots, CLI-managed)
├── bots/<name>/
│   ├── bot.yaml          # Bot config (token, personality, role, allowed_users, model, streaming, skills, heartbeat)
│   ├── CLAUDE.md         # Bot system prompt (includes skills + memory instructions)
│   ├── MEMORY.md         # Bot long-term memory (read/written by Claude Code, shared across all sessions)
│   ├── cron.yaml         # Cron job config (schedule/at, timezone, message, skills, model)
│   ├── cron_sessions/<job_name>/  # Per-cron-job working directory
│   │   └── CLAUDE.md     # Copy of bot CLAUDE.md
│   ├── heartbeat_sessions/       # Heartbeat working directory
│   │   ├── CLAUDE.md     # Copy of bot CLAUDE.md
│   │   ├── HEARTBEAT.md  # Checklist (user-editable)
│   │   └── workspace/    # File storage
│   └── sessions/chat_<id>/
│       ├── CLAUDE.md              # Per-session context
│       ├── conversation-YYMMDD.md # Daily conversation log (UTC date rotation)
│       ├── .claude_session_id     # Claude Code session ID (for --resume)
│       └── workspace/             # File storage
├── bridge/
│   ├── server.mjs        # Bridge server (auto-copied from package data on start)
│   ├── package.json      # NPM package (depends on @anthropic-ai/claude-agent-sdk)
│   └── node_modules/     # NPM dependencies (auto-installed on first start)
├── skills/<name>/
│   ├── SKILL.md          # Skill instructions (required, composed into bot CLAUDE.md)
│   ├── skill.yaml        # Skill config (tool-based only: type, status, required_commands, install_hints, environment_variables)
│   └── mcp.json          # MCP server config (MCP skills only: mcpServers)
└── logs/                 # Daily rotating logs
```
