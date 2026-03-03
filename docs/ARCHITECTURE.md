# Architecture

## Overall Structure

```
Telegram <-> python-telegram-bot (Long Polling) <-> handlers.py <-> claude_runner.py <-> Claude Code CLI
                                                       |                 |
                                                  session.py         skill.py
                                                       |                 |
                                              ~/.cclaw/bots/      ~/.cclaw/skills/
```

## Core Design Decisions

### 1. Claude Code Subprocess Delegation

Instead of calling the LLM API directly, we run the `claude -p` CLI as a subprocess.

- Leverages Claude Code's agent capabilities (file manipulation, code execution) as-is
- No API key management needed (Claude Code handles its own authentication)
- Sets session directory as working directory via subprocess `cwd` parameter
- Model selection via `--model` flag (sonnet/opus/haiku)

### 2. File-Based Sessions

Sessions are managed via directory structure without a database.

- Each chat is a `chat_<id>/` directory
- `CLAUDE.md`: System prompt read by Claude Code
- `conversation-YYMMDD.md`: Daily conversation log (UTC date rotation, markdown append). Legacy `conversation.md` supported as read fallback
- `workspace/`: File storage for Claude Code outputs

### 3. Multi-Bot Architecture

Multiple Telegram bots run simultaneously in a single process.

- Independent `Application` instance per bot
- Concurrent polling via `asyncio`
- Per-bot independent configuration (token, personality, role, permissions, model)
- Individual bot errors are isolated from other bots

### 4. Per-Session Concurrency Control

Sequential processing when multiple messages arrive in the same chat.

- `asyncio.Lock` managed by `{bot_name}:{chat_id}` key
- When lock is held, sends "Message queued" notification then waits (message queuing)

### 5. Process Tracking

Running Claude Code subprocesses are tracked per session.

- `_running_processes` dictionary maps `{bot_name}:{chat_id}` to subprocess
- `/cancel` command kills running process with SIGKILL
- `returncode == -9` raises `asyncio.CancelledError`

### 6. Model Selection

Per-bot Claude model configuration with runtime changes.

- Stored in `bot.yaml`'s `model` field (default: sonnet)
- Runtime change via Telegram `/model` command (immediately saved to bot.yaml)
- Also changeable via CLI `cclaw bot model <name> <model>`
- Valid models: sonnet (4.5), opus (4.6), haiku (3.5) — `/model` shows version alongside name

### 7. Skill System

Extends bot capabilities by linking tools/knowledge. Skills are classified by origin:

- **Built-in skills** (`builtin`): Pre-packaged with cclaw, installable via `cclaw skills install <name>`
- **Custom skills** (`custom`): User-created via `cclaw skills add`

Internally, skills have different tool configurations:

- Minimum skill unit: folder + single `SKILL.md`
- **Markdown-only skills**: Just `SKILL.md` makes it immediately active. Adds knowledge/instructions to bot
- **Tool-based skills**: `skill.yaml` defines tool type (cli/mcp/browser), required commands, environment variables. Activated via `cclaw skill setup`
- On skill attachment, `compose_claude_md()` merges bot prompt + skill content to regenerate CLAUDE.md
- MCP skills: Auto-generates `.mcp.json` in session directory. Environment variables injected via subprocess env
- CLI skills: Environment variables auto-injected during subprocess execution
- **Dual-layer permission defense**: `allowed_tools` in skill.yaml controls hard auto-approval (tools not listed are blocked in `-p` mode). SKILL.md provides soft guardrails for tools that are allowed but can be used destructively (e.g., `execute_sql` with DELETE statements)

### 8. Cron Schedule Automation

Automatically runs Claude Code at scheduled times and sends results via Telegram.

- Job list defined in `cron.yaml` (schedule or at)
- **Recurring jobs**: Standard cron expressions (`0 9 * * *` = daily at 9 AM)
- **One-shot jobs**: ISO datetime or duration (`30m`, `2h`, `1d`) in `at` field. Relative durations are converted to absolute ISO datetime at `add_cron_job()` time
- **Per-job timezone**: Optional `timezone` field (e.g., `Asia/Seoul`). Defaults to UTC. Cron expressions are evaluated in the job's timezone via `resolve_job_timezone()` using `zoneinfo.ZoneInfo`
- `croniter` library for cron expression validation and matching
- Scheduler loop: checks current time against job schedules every 30 seconds
- Duplicate prevention: records last run time in UTC, prevents re-execution within same minute
- Result delivery: sends Telegram DM to all `allowed_users` in `bot.yaml`. Falls back to session chat IDs (`collect_session_chat_ids()`) when `allowed_users` is empty
- Isolated working directory: Claude Code runs in `cron_sessions/{job_name}/`
- One-shot jobs: auto-deleted after execution when `delete_after_run=true`, auto-disabled when `delete_after_run=false`
- Inherits bot's skills/model settings, overridable at job level

### 9. Heartbeat (Periodic Situation Awareness)

Proactive agent feature that periodically wakes Claude Code to run HEARTBEAT.md checklist and only sends Telegram messages when there's something to report.

- Configured in `bot.yaml`'s `heartbeat` section (one per bot)
- **interval_minutes**: Execution interval (default 30 minutes)
- **active_hours**: Active time range (HH:MM, local time, midnight-crossing supported)
- `HEARTBEAT.md`: User-editable checklist template
- **HEARTBEAT_OK detection**: When response contains `HEARTBEAT_OK` marker, only logs without notification
- Sends Telegram DM to all `allowed_users` when HEARTBEAT_OK is absent. Falls back to session chat IDs when `allowed_users` is empty
- Uses all skills linked to the bot (no separate skill list for heartbeat)
- Scheduler loop re-reads `bot.yaml` every cycle for runtime config changes
- Isolated working directory: Claude Code runs in `heartbeat_sessions/`

### 10. Built-in Skill System

Frequently used skills are bundled as templates inside the package, installable via `cclaw skills install`.

- Skill templates stored in `src/cclaw/builtin_skills/` directory (SKILL.md, skill.yaml, etc.)
- `builtin_skills/__init__.py` scans subdirectories to provide a registry
- `install_builtin_skill()` copies template files to `~/.cclaw/skills/<name>/`
- After installation: requirement check -> auto-activate on pass, stays inactive with guidance on fail
- `skill.yaml`'s `install_hints` field provides installation instructions for missing tools
- Built-in skills: iMessage (`imsg` CLI), Apple Reminders (`reminders-cli`), Naver Map (knowledge type, web URL based), Image Processing (`slimg` CLI), Best Price (knowledge type, web search based), Supabase (MCP type, DB/Storage/Edge Functions with no-deletion guardrails), Gmail (`gogcli`), Google Calendar (`gogcli`), Twitter/X (MCP type, tweet posting/search via `@enescinar/twitter-mcp`), Jira (MCP type, issue management via `mcp-atlassian`), Naver Search (`naver-cli`, 6-type search), Kakao Local (`kakao-cli`, address/coordinate/keyword search), DART (`dartcli`, corporate disclosure/finance/filings), Translate (`translatecli`, Gemini-powered text/transcript translation), Daiso (`daiso-cli`, Daiso Mall product search)
- `cclaw skills` command shows all skills with origin type (builtin/custom), including uninstalled builtins
- Telegram `/skills` handler also shows origin type (builtin/custom) and uninstalled builtins

### 11. Session Continuity

Each message runs `claude -p` as a new process, but maintains conversation context.

- **First message**: Starts new Claude Code session with `--session-id <uuid>`
  - Bootstrap prompt order: global memory -> bot memory -> last 20 turns from conversation files -> new message
- **Subsequent messages**: Continues session with `--resume <session_id>`
- **Fallback**: Auto-retries with bootstrap when `--resume` fails (session expired). Fallback uses same bootstrap order (global memory -> bot memory -> conversation history -> message)
- **Reset**: `/reset`, `/resetall` also delete session ID
- Session ID stored as UUID in `sessions/chat_<id>/.claude_session_id`
- `_prepare_session_context()`: Decides resume/bootstrap
- `_call_with_resume_fallback()`: Handles fallback on resume failure
- Cron and heartbeat: one-shot executions with global memory + bot memory injected into prompt

### 12. Bot-Level Long-Term Memory

When user requests "remember this", the bot saves to `MEMORY.md` and injects it into the prompt on new session bootstrap for persistent memory.

- `MEMORY.md` managed per bot (`~/.cclaw/bots/<name>/MEMORY.md`). All chat sessions share the same memory
- **Save mechanism**: `compose_claude_md()` includes memory instructions + MEMORY.md absolute path in CLAUDE.md -> Claude Code writes to MEMORY.md directly via file write tool
- **Load mechanism**: `_prepare_session_context()` reads `load_global_memory()` + `load_bot_memory()` during bootstrap -> prompt injection (global memory -> bot memory -> conversation history -> new message order)
- `--resume` sessions don't inject memory separately (Claude Code session maintains its own context)
- Management: Telegram `/memory` (show), `/memory clear` (reset), CLI `cclaw memory show|edit|clear`
- CRUD functions in `session.py`: `memory_file_path()`, `load_bot_memory()`, `save_bot_memory()`, `clear_bot_memory()`

### 13. Global Memory

Shared read-only memory accessible by all bots, managed via CLI only.

- `GLOBAL_MEMORY.md` stored at `~/.cclaw/GLOBAL_MEMORY.md`
- Stores timezone, user preferences, and other information all bots should reference
- **CLAUDE.md injection**: `compose_claude_md()` inserts a "Global Memory (Read-Only)" section without the file path, preventing Claude from modifying it. Placed before bot Memory section
- **Bootstrap injection**: `_prepare_session_context()` and `_call_with_resume_fallback()` inject global memory before bot memory (global memory -> bot memory -> conversation history -> message)
- **Cron/Heartbeat injection**: `execute_cron_job()` and `execute_heartbeat()` inject global memory + bot memory into prompt before execution
- **CLI management**: `cclaw global-memory show|edit|clear`. Editing or clearing regenerates all bots' CLAUDE.md and propagates to sessions
- Not editable via Telegram (no file path exposed, no Telegram command)
- CRUD functions in `session.py`: `global_memory_file_path()`, `load_global_memory()`, `save_global_memory()`, `clear_global_memory()`

### 14. Streaming Response

Delivers Claude Code output to Telegram in real-time. User-toggleable on/off.

- Controlled by `streaming` field in `bot.yaml` (default: `DEFAULT_STREAMING = False`)
- Runtime toggle via Telegram `/streaming on|off` or CLI `cclaw bot streaming <name> on|off`
- **Streaming mode** (`_send_streaming_response`):
  - `run_claude_streaming()`: Runs with `--output-format stream-json --verbose --include-partial-messages`
  - Extracts `text_delta` from stream-json `content_block_delta` events for per-token streaming
  - `on_text_chunk` callback delivers text fragments to handler
  - Real-time Telegram message editing. Cursor marker (`▌`) shows progress
  - Throttling (0.5s) to avoid Telegram API rate limits
  - On completion, replaces with Markdown-to-HTML converted final text
  - Fallback: Uses accumulated streaming text or `assistant` turn text if no `result` event
- **Non-streaming mode** (`_send_non_streaming_response`):
  - `run_claude()`: Sends typing action every 4 seconds -> Markdown-to-HTML conversion on completion -> batch send
  - Same pattern as cron and heartbeat (Phase 3 approach)

### 15. Token Compact

Compresses bot MD files (MEMORY.md, user-created SKILL.md, HEARTBEAT.md) via one-shot `claude -p` calls to reduce token costs.

- **Targets**: MEMORY.md, user-created SKILL.md (builtins excluded via `is_builtin_skill()`), HEARTBEAT.md
- **Execution**: Sequential per-target with error isolation — individual failures don't stop remaining targets
- **Working directory**: Each compaction runs in a `tempfile.TemporaryDirectory()` (no session state needed)
- **Token estimation**: `chars // 4` heuristic for relative before/after comparison
- **Post-save**: After saving compacted files, `regenerate_bot_claude_md()` + `update_session_claude_md()` propagate changes
- **CLI**: `cclaw bot compact <name>` with `--yes/-y` skip confirmation
- **Telegram**: `/compact` auto-saves on success

### 16. Encrypted Backup

Full backup of `~/.cclaw/` directory to an AES-256 encrypted zip file.

- `cclaw backup` generates `YYMMDD-cclaw.zip` in the current working directory
- Password input via `getpass.getpass()` (masked, confirmed twice)
- Encryption via `pyzipper` (AES-256, WZ_AES mode)
- Excludes runtime artifacts: `cclaw.pid`, `__pycache__/`
- Same-day backup prompts for overwrite confirmation

## Module Dependencies

```
cli.py
├── onboarding.py -> config.py
├── bot_manager.py
│   ├── config.py
│   ├── skill.py (regenerate_bot_claude_md)
│   ├── cron.py (list_cron_jobs, run_cron_scheduler)
│   ├── heartbeat.py (run_heartbeat_scheduler)
│   ├── handlers.py
│   │   ├── claude_runner.py
│   │   │   └── skill.py (merge_mcp_configs, collect_skill_environment_variables)
│   │   ├── cron.py (list_cron_jobs, get_cron_job, execute_cron_job, next_run_time, resolve_job_timezone)
│   │   ├── heartbeat.py (get/enable/disable_heartbeat, execute_heartbeat)
│   │   ├── skill.py (attach/detach, is_skill, skill_status)
│   │   ├── builtin_skills (list_builtin_skills)
│   │   ├── token_compact.py (collect_compact_targets, run_compact, format_compact_report, save_compact_results)
│   │   ├── session.py (ensure_session, reset_session, get/save/clear_claude_session_id, load_conversation_history, load_bot_memory, clear_bot_memory, load_global_memory)
│   │   ├── config.py (save_bot_config, VALID_MODELS)
│   │   └── utils.py
│   └── utils.py
├── cron.py -> config.py, claude_runner.py, session.py (load_global_memory, load_bot_memory), utils.py
├── heartbeat.py -> config.py, claude_runner.py, session.py (load_global_memory, load_bot_memory), utils.py
├── backup.py -> (standalone: pathlib, pyzipper)
├── token_compact.py -> config.py, skill.py (skill_directory), builtin_skills (is_builtin_skill), claude_runner.py (run_claude)
├── skill.py -> config.py, builtin_skills (circular reference: config.py -> skill.py resolved via lazy import)
├── builtin_skills -> (internal package templates, no external dependencies)
└── config.py
```

## Process Management

- **Foreground**: `cclaw start` -> `asyncio.run()` -> Ctrl+C to quit
- **Daemon**: `cclaw start --daemon` -> Creates launchd plist -> `launchctl load`
- **PID file**: Records current process ID in `~/.cclaw/cclaw.pid`
- **Graceful Shutdown**: SIGINT/SIGTERM -> `cancel_all_processes()` kills all running Claude subprocesses first -> cancel cron/heartbeat tasks -> `application.stop()` for each bot. Without killing subprocesses first, `application.stop()` would wait for running handlers (up to `command_timeout` seconds)

## Message Processing Flow

### Text Messages
```
Receive -> Permission check -> Session Lock (queuing) -> ensure_session -> _prepare_session_context (resume/bootstrap decision, inject global memory+bot memory+history on bootstrap)
  -> _call_with_resume_fallback -> streaming_enabled branch
    -> (streaming on) run_claude_streaming (--resume or --session-id) -> per-token message edit -> Markdown->HTML conversion -> final message replace/split send
    -> (streaming off) typing action every 4s -> run_claude (--resume or --session-id) -> Markdown->HTML conversion -> batch send
  -> (on resume failure) clear_session_id -> retry with bootstrap
```

### Files (Photos/Documents)
```
Receive -> Permission check -> Session Lock (queuing) -> Download to workspace -> Pass caption + file path to Claude -> Send response
```

### /cancel Command
```
Receive -> Permission check -> Look up process in _running_processes -> process.kill() -> "Execution cancelled" response
```

### /send Command
```
Receive -> Permission check -> Look up workspace file -> reply_document() to send
```

### /skills Command
```
Receive -> Permission check -> Args branch
  -> (none or "list"): list_skills() -> bots_using_skill() for link status -> list_builtin_skills() for uninstalled builtins -> full skill list response
  -> "attach <name>": is_skill() -> skill_status() == "active" check -> attach_skill_to_bot() -> sync in-memory bot_config -> response
  -> "detach <name>": detach_skill_from_bot() -> sync in-memory bot_config -> response
```

### Cron Scheduler
```
Bot start -> Load cron.yaml -> asyncio.create_task(run_cron_scheduler) -> 30-second loop
  -> Match current time against schedule -> execute_cron_job -> inject global memory + bot memory -> run_claude -> Send results to allowed_users
```

### /cron run Command
```
Receive -> Permission check -> get_cron_job() -> execute_cron_job() -> Send results
```

### Heartbeat Scheduler
```
Bot start -> Check heartbeat.enabled -> asyncio.create_task(run_heartbeat_scheduler) -> interval_minutes loop
  -> Check active_hours range -> Skip if outside range
  -> Load HEARTBEAT.md -> inject global memory + bot memory -> run_claude -> Check for HEARTBEAT_OK in response
  -> If HEARTBEAT_OK present: log only
  -> If HEARTBEAT_OK absent: send to allowed_users via Telegram
```

### /memory Command
```
Receive -> Permission check -> Args branch
  -> (none): load_bot_memory() -> Show contents (or "No memories" message)
  -> clear: clear_bot_memory() -> "Memory cleared" response
```

### /compact Command
```
Receive -> Permission check -> collect_compact_targets() -> Show target list
  -> typing action -> run_compact() (sequential, per-target error isolation)
  -> format_compact_report() -> split_message() + send
  -> save_compact_results() (success only) -> regenerate_bot_claude_md() + update_session_claude_md()
```

### /streaming Command
```
Receive -> Permission check -> Args branch
  -> (none): Show current streaming_enabled status
  -> on: streaming_enabled = True, save to bot.yaml
  -> off: streaming_enabled = False, save to bot.yaml
```

### /heartbeat Command
```
Receive -> Permission check -> Subcommand branch
  -> (none): get_heartbeat_config() -> Show status
  -> on: enable_heartbeat() -> Enable (auto-creates HEARTBEAT.md)
  -> off: disable_heartbeat() -> Disable
  -> run: execute_heartbeat() -> Run immediately
```
