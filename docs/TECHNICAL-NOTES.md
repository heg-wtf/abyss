# Technical Notes

## CCLAW_HOME Environment Variable

The runtime data path defaults to `~/.cclaw/` and can be changed via the `CCLAW_HOME` environment variable.
In tests, isolation is achieved via `monkeypatch.setenv("CCLAW_HOME", str(tmp_path))`.

## Path Management Principles

All paths use absolute paths. The `bot_directory(name)` function in `config.py` returns the absolute path `cclaw_home() / "bots" / name`, and other modules access bot directories through this function. Absolute paths are also stored in bot entries in `config.yaml`. Avoid relative paths and use `pathlib.Path` for path composition.

## Telegram Message Limit

Telegram messages have a maximum of 4096 characters. `utils.split_message()` splits long responses for delivery.
It attempts to split at line break boundaries, and truncates at the limit when no suitable line break is found.

## Claude Code Execution

Two execution paths are supported, with SDK pool as the preferred mode:

- **SDK pool batch**: `run_claude_with_sdk()` -> `SDKClientPool.query()` -> `ClaudeSDKClient.query()` + `receive_response()` (preferred, persistent client)
- **SDK pool streaming**: `run_claude_streaming_with_sdk()` -> `SDKClientPool.query_streaming()` -> same, with `on_text_chunk` callback
- **Subprocess batch**: `claude -p "<message>" --output-format text` (fallback when SDK unavailable)
- **Subprocess streaming**: `claude -p "<message>" --output-format stream-json --verbose --include-partial-messages`

The working directory is set to the session directory via `cwd` parameter (subprocess) or `ClaudeAgentOptions(cwd=...)` (SDK).

- `shutil.which("claude")` resolves the full path to the Claude CLI. Works regardless of installation method (`uv run`, `pip install`, `pipx install`, etc.) by searching PATH. Raises `RuntimeError` with installation guidance if not found.
- `--output-format text`: Text output (not JSON)
- `--model <model>`: Model selection (sonnet/opus/haiku). Flag is omitted when `model` parameter is None.
- Additional arguments can be passed via the `claude_args` field in `bot.yaml`
- Default timeout: 300 seconds (`command_timeout` in `config.yaml`)

### Skill Config Preparation (`_prepare_skill_config`)

Shared function that handles skill-related file setup for both SDK pool and subprocess execution paths:

- Writes `.mcp.json` to working directory (merged MCP configs from all attached skills)
- Writes `.claude/settings.json` with `allowedTools` list
- Collects environment variables from all attached skills
- **QMD auto-injection**: When `shutil.which("qmd")` returns non-None, auto-appends QMD HTTP MCP server config and allowed tools regardless of skill attachment
- Returns `(allowed_tools, environment_variables)` tuple
- Used by `run_claude()`, `run_claude_streaming()`, `run_claude_with_sdk()`, `run_claude_streaming_with_sdk()`

## Python Agent SDK Client Pool

### Pool Architecture

`SDKClientPool` in `sdk_client.py` maintains persistent `ClaudeSDKClient` instances keyed by session (`bot:chat_id`). This avoids spawning a new Claude Code process per message — subsequent messages reuse the same client (~1-2s faster).

```
handlers.py -> claude_runner.py -> get_pool() -> SDKClientPool
                                                   ├── "bot1:chat_123" -> ClaudeSDKClient (persistent)
                                                   ├── "bot1:chat_456" -> ClaudeSDKClient (persistent)
                                                   └── "bot2:chat_789" -> ClaudeSDKClient (persistent)
```

### Pool Lifecycle

1. `get_pool()` creates the singleton `SDKClientPool` on first use (lazy)
2. First message for a session key: `_get_or_create_client()` creates `ClaudeSDKClient(options)`, calls `__aenter__()`, stores in `_clients` dict
3. Subsequent messages: reuses existing client via `client.query(prompt)` + `client.receive_response()`
4. `/reset`: `pool.close_session(key)` calls `__aexit__()` and removes from pool
5. Shutdown: `close_pool()` calls `close_all()` which closes every client, then sets `_pool = None`

### Session ID Persistence

`run_claude_with_sdk()` and `run_claude_streaming_with_sdk()` accept `session_directory: Path | None`:
- On client creation: loads saved session ID from `.claude_session_id` as `resume` option
- After successful query: saves `result.session_id` back to `.claude_session_id`
- On restart: pool creates a new client with the saved session ID, resuming the conversation

### Interrupt (/cancel)

`cancel_sdk_session(session_key)` in `claude_runner.py`:
1. Checks if pool has a session for the key
2. Calls `pool.interrupt(key)` which invokes `client.interrupt()`
3. Returns `True` if interrupted, `False` if no session found
4. `handlers.py` tries SDK interrupt first, falls back to subprocess `cancel_process()` (SIGKILL)

### Fallback Strategy

```
Pool query attempt
├─ Success → return text, save session_id
├─ ConnectionError/OSError → log warning, fall through to subprocess
└─ Other Exception → log warning, close broken session from pool, fall through to subprocess

Subprocess fallback (identical to pre-pool behavior)
├─ Success → return text
└─ Error → propagate to handler
```

### Resume Fallback in Handlers

`_call_with_resume_fallback()` handles stale sessions:
1. Calls `send_response()` with pool-backed runner
2. On `RuntimeError` (stale session): clears `.claude_session_id`, closes pool session, retries with bootstrap prompt

## Logging (RichHandler)

`setup_logging()` in `utils.py` configures two handlers on the root logger:

- **FileHandler**: Writes to `~/.cclaw/logs/cclaw-YYMMDD.log` with full format (`%(asctime)s [%(name)s] %(levelname)s: %(message)s`)
- **RichHandler**: Colorized console output via `rich.logging.RichHandler` (tracebacks enabled, show_path disabled)

Key detail: `logging.basicConfig()` is called with `force=True` to ensure it replaces any pre-existing handlers. Without `force=True`, if any library (e.g., `httpx`, `telegram`) configures logging before `setup_logging()` is called, `basicConfig()` would be a no-op and all logs would bypass RichHandler.

## Model Selection

- Valid models: `VALID_MODELS = ["sonnet", "opus", "haiku"]`, default: `DEFAULT_MODEL = "sonnet"`
- Model version mapping: `MODEL_VERSIONS = {"sonnet": "4.5", "opus": "4.6", "haiku": "3.5"}`
- `model_display_name()`: Appends version to model name (e.g., `opus 4.6`)
- `/model` command displays current model and list with version info
- Stored in `bot.yaml`'s `model` field. Runtime changeable via Telegram `/model` command.
- Runtime changes reflected via `nonlocal current_model` in handler closure.
- Model changes are immediately saved to bot.yaml via `save_bot_config()`.
- Also changeable via CLI `cclaw bot model <name> [model]`.

## Process Tracking (/cancel)

- `/cancel` first tries SDK pool interrupt via `cancel_sdk_session(session_key)` -> `pool.interrupt()` -> `client.interrupt()`
- If no SDK session, falls back to subprocess: `_running_processes` dictionary maps `{bot_name}:{chat_id}` to subprocess
- When `session_key` is passed to `run_claude()`, the process is automatically registered/deregistered
- Subprocess cancel calls `cancel_process()` which invokes `process.kill()` (SIGKILL)
- When process is killed: `returncode == -9` -> raises `asyncio.CancelledError`
- Handler catches `CancelledError` and sends "Execution was cancelled" message
- In group mode: orchestrator tries SDK interrupt + subprocess cancel for all member bots

## Graceful Shutdown

Shutdown sequence in `bot_manager.py`:

1. `close_pool()`: Closes all persistent SDK clients (`__aexit__()` on each), clears pool singleton
2. `cancel_all_processes()`: Iterates `_running_processes` and kills all running subprocesses (`returncode is None`), then clears the registry
3. Cancel cron/heartbeat tasks
4. Stop Telegram applications
5. Stop QMD daemon, remove PID file

Pool must be closed before killing subprocesses. Without this, `application.stop()` waits for running handler coroutines to complete, which blocks until the Claude subprocess finishes (up to `command_timeout`, default 300 seconds). By closing pool and killing subprocesses first, the handlers complete immediately and shutdown proceeds without delay.

## Session Lock and Message Queuing

Concurrent requests from the same chat are processed sequentially via `asyncio.Lock`.
When the lock is held, a "Message queued. Processing previous request..." notification is sent before waiting.
Lock key format: `{bot_name}:{chat_id}`.

## /send Command

Command to send workspace files via Telegram.
- `/send` (no args): Shows list of available files
- `/send <filename>`: Sends the file via `reply_document()`
- Returns "File not found" message if file doesn't exist

## launchd Daemon

`cclaw start --daemon` creates `~/Library/LaunchAgents/com.cclaw.daemon.plist` and runs `launchctl load`.
`KeepAlive` is enabled so the process auto-restarts on termination.
`cclaw stop` runs `launchctl unload` then deletes the plist.

## Bot Error Isolation

In `bot_manager.py`, individual bot configuration errors or startup failures don't affect other bots.
- Config load/token errors: Skips the bot and proceeds to the next
- Polling start failure: Only that bot is skipped, others run normally
- `started_applications` list tracks actually started bots for cleanup on shutdown

## Telegram API Mocking in Tests

`telegram.Bot` is imported inside functions, so it's mocked via `patch("telegram.Bot")`.
`AsyncMock` is used to mock async methods like `get_me()`.

## allowed_users

When `allowed_users` in `bot.yaml` is an empty list, all users are allowed for incoming messages.
To restrict access, add Telegram user IDs (integers) to the list.

For proactive messages (cron results, heartbeat notifications), `allowed_users` is needed as the target. When empty, `collect_session_chat_ids()` in `session.py` scans `sessions/chat_<id>/` directories as a fallback — sending results to users who have previously chatted with the bot.

## Daemon Auto-Restart on Bot Creation

When a new bot is created via `cclaw init` or `cclaw bot add` while the daemon is already running, the daemon is automatically restarted to pick up the new bot. This ensures the new bot's Telegram polling and command menu are registered immediately.

- `_is_daemon_running()` in `onboarding.py` checks if the launchd plist file exists
- `_restart_daemon()` calls `stop_bots()` then `start_bots(daemon=True)`
- If the daemon is not running, a message is shown: "Start the bot: cclaw start"
- If restart fails, a manual restart command is displayed as fallback

## Telegram Command Menu

The `BOT_COMMANDS` list is registered with Telegram via the `set_my_commands()` API.
Called after `start_polling()` completes on bot start (`bot_manager.py`). Command registration failure is caught and logged as a warning — it does not prevent the bot from running.
After registration, typing `/` displays the command autocomplete menu.
Adding/changing commands only requires a bot restart.

## Telegram Formatting Rules

The Rules section in `compose_claude_md()` includes a "No Markdown tables" rule.
Telegram doesn't render Markdown tables, so `| Header | Content |` format appears as raw text.
Instead, an "emoji + text list" format is enforced (e.g., `🌡 Low -2°C / High 7°C`).

## Markdown to Telegram HTML Conversion

Claude's Markdown responses are converted to Telegram HTML before sending (`utils.markdown_to_telegram_html()`).

- `[text](url)` -> `<a href="url">text</a>` (links extracted before HTML escaping to preserve URLs)
- `**bold**` -> `<b>bold</b>`
- `*italic*` -> `<i>italic</i>`
- `` `code` `` -> `<code>code</code>`
- ` ```code blocks``` ` -> `<pre>code blocks</pre>`
- `## heading` -> `<b>heading</b>` (Telegram has no heading support, so bold is used)
- Falls back to plain text if HTML send fails

## Streaming On/Off Toggle

- `bot.yaml`'s `streaming` field: `false` (default) or `true`
- Default constant: `DEFAULT_STREAMING = False` in `config.py`
- Runtime changes reflected via `nonlocal streaming_enabled` in handler closure.
- Runtime toggle via Telegram `/streaming on|off`, immediately saved via `save_bot_config()`.
- Also changeable via CLI `cclaw bot streaming <name> [on|off]`.
- `message_handler` and `file_handler` call `_send_streaming_response()` or `_send_non_streaming_response()` based on `streaming_enabled`.
- Non-streaming mode: typing action every 4 seconds + `run_claude()` + Markdown->HTML conversion + split send (restored Phase 3 pattern).

## Streaming Response

### Execution Mode

`run_claude_streaming()` runs Claude Code with `--output-format stream-json --verbose --include-partial-messages` flags.
Reads stdout line by line and parses JSON events.

### stream-json Event Parsing

Three event types are processed:

- `stream_event` + `content_block_delta` + `text_delta`: Per-token text (--verbose mode)
- `assistant` message `content` blocks: Turn-level text (fallback)
- `result`: Final complete text

The `result` event text is used first; if absent, accumulated streaming text is used.

### Telegram Message Editing Strategy

- First `reply_text()` sent after at least 10 characters (`STREAM_MIN_CHARS_BEFORE_SEND`) accumulated
- Subsequent `edit_message_text()` calls at 0.5 second (`STREAM_THROTTLE_SECONDS`) intervals
- Cursor marker `▌` (`STREAMING_CURSOR`) appended to text end to show progress
- Streaming preview stops when exceeding 4096 characters (`stream_stopped = True`)
- On completion: single chunk gets HTML-formatted message edit, multiple chunks get preview deletion + split send

### Typing Action

For non-streaming paths (cron, heartbeat) and streaming-off conversation messages, the typing action approach is used.
`send_action("typing")` sent every 4 seconds via `asyncio.create_task` for background execution.

## File Receiving

When photos/documents are received, they're downloaded to workspace then passed to Claude with the file path.
Photos use the largest size (`photo[-1]`).

## Skill System

### Skill Classification

Skills are classified by origin:

- **Built-in** (`builtin`): Pre-packaged with cclaw in `src/cclaw/builtin_skills/`. Installable via `cclaw skills install <name>`.
- **Custom** (`custom`): User-created via `cclaw skills add`. Can be markdown-only or tool-based.

Internally, `skill.yaml` has a `type` field (cli/mcp/browser/None) for tool configuration, but the display (CLI `cclaw skills` and Telegram `/skills`) shows origin-based classification (builtin/custom).

### CLAUDE.md Composition

`compose_claude_md()` merges bot profile + skill SKILL.md content into a single CLAUDE.md.
Without skills, output is identical to the existing `generate_claude_md()`.
CLAUDE.md is auto-regenerated when `save_bot_config()` is called.
On bot start, `regenerate_bot_claude_md()` reflects the latest skill state.

### Circular Reference Resolution

Bidirectional dependency exists between `config.py` and `skill.py`.
Resolved via lazy import: `from cclaw.skill import compose_claude_md` inside `save_bot_config()` in `config.py`.

### MCP Skills

MCP skills define `mcpServers` configuration in `mcp.json` files.
During `run_claude()`, `merge_mcp_configs()` merges all linked MCP skill configs
and creates `.mcp.json` in the session directory. Claude Code auto-detects this file.

### Default Allowed Tools

When any skill defines `allowed_tools`, the `--allowedTools` flag activates a whitelist — only listed tools are auto-approved. This blocks basic tools (WebFetch, WebSearch, Bash) that aren't skill-specific but are essential for general operation.

`DEFAULT_ALLOWED_TOOLS` in `claude_runner.py` solves this by always merging `WebFetch`, `WebSearch`, and `Bash` into the whitelist when it's active. Without this, attaching any tool-based skill would disable web access and shell execution.

### CLI Skill Environment Variables

CLI skills store values in `skill.yaml`'s `environment_variable_values`.
Environment variable values are collected during `cclaw skills setup`.
During `run_claude()`, `collect_skill_environment_variables()` gathers them
and injects into the subprocess `env` parameter.

### Skill Setup with Unconfigured Environment Variables

`cclaw skills setup` normally skips already-active skills. However, if a skill is active but has unconfigured environment variables (empty values), setup re-enters the environment variable prompt. This handles the case where `cclaw skills install` auto-activates an MCP skill (no `required_commands` failure) before environment variables are set.

### Session CLAUDE.md Propagation

`ensure_session()` maintains existing behavior (copies bot CLAUDE.md only when session CLAUDE.md doesn't exist).
On skill attach/detach, `update_session_claude_md()` explicitly overwrites CLAUDE.md in all existing sessions.

### Telegram /skills Handler

The `/skills` command queries installed skill list via `list_skills()`,
and displays link status for each skill via `bots_using_skill()`.
Each skill shows its origin type (`builtin` or `custom`) instead of tool type.
Skills not linked to any bot are also included.
Additionally, `list_builtin_skills()` shows uninstalled built-in skills at the bottom.

## Cron Schedule Automation

### cron.yaml Schema

```yaml
jobs:
  - name: morning-email       # Job identifier
    schedule: "0 9 * * *"     # Standard cron expression
    timezone: "Asia/Seoul"    # Optional (defaults to UTC)
    message: "Summarize today's morning emails"
    skills: [gmail]           # Optional (uses bot's default skills if omitted)
    model: haiku              # Optional (uses bot's default model if omitted)
    enabled: true
  - name: call-reminder       # One-shot job
    at: "2026-02-20T15:00:00" # ISO datetime or "30m"/"2h"/"1d"
    message: "Time for client callback"
    delete_after_run: true    # Auto-delete after execution
```

### Per-Job Timezone

- Optional `timezone` field per job (e.g., `Asia/Seoul`, `America/New_York`)
- Defaults to UTC when omitted
- `resolve_job_timezone()` resolves timezone name via `zoneinfo.ZoneInfo`, falls back to UTC on invalid name
- Cron expressions are evaluated in the job's timezone: `datetime.now(job_timezone)` is used instead of UTC
- `next_run_time()` also returns time in the job's timezone for display
- Last run times are tracked in UTC internally to avoid DST issues

### Scheduler Behavior

- `bot_manager.py` launches `asyncio.create_task(run_cron_scheduler())` on bot start
- Checks current time against job schedules every 30 seconds
- Calculates fire time for current minute via `croniter`'s `get_next()` in the job's timezone
- Records last run time in UTC (`last_run_times` dict) to prevent duplicate execution within same minute
- `stop_event` for graceful shutdown (cron shuts down with bot)

### Result Delivery

- Sends to all `allowed_users` via `application.bot.send_message()`
- In DMs, user_id == chat_id, so no separate chat ID management needed
- **Session chat ID fallback**: When `allowed_users` is empty, `collect_session_chat_ids()` scans `sessions/chat_<id>/` directories to find users who have previously chatted with the bot. Skips sending only when both `allowed_users` and session chat IDs are empty
- Prepends `[cron: job_name]` header to messages

### Working Directory Isolation

- Each job runs in `~/.cclaw/bots/{name}/cron_sessions/{job_name}/`
- Bot's CLAUDE.md is copied so Claude Code recognizes bot context
- Completely isolated from regular sessions, no interference between cron jobs

### One-Shot Jobs

- `at` field triggers one-shot execution instead of schedule
- Supports ISO 8601 datetime (`2026-02-20T15:00:00`) or duration shorthand (`30m`, `2h`, `1d`)
- **Relative-to-absolute conversion**: `add_cron_job()` converts relative durations (e.g., `10m`) to absolute ISO datetime at creation time. Without this, the scheduler would re-evaluate `parse_one_shot_time("10m")` every 30-second cycle, always computing `now + 10m`, causing the job to never fire
- **Post-execution cleanup**: `delete_after_run: true` auto-deletes from `cron.yaml`. `delete_after_run: false` sets `enabled: false` to prevent re-execution on restart (since `last_run_times` is in-memory only and lost on restart)

### Telegram /skills Handler (Unified)

The `/skills` handler manages skill listing, attach, and detach (previous `/skill` handler merged into `/skills`).
The `attached_skills` variable in the handler closure tracks currently linked skills.
After attach/detach, the local `bot_config["skills"]` is directly updated to sync memory and disk state.
(`attach_skill_to_bot()` only modifies the on-disk config, so the in-memory `bot_config` must be updated separately.)
`run_claude()` receives `skill_names=attached_skills`.
Uninstalled built-in skills are also listed at the bottom via `list_builtin_skills()`.

### Built-in Skills

The `src/cclaw/builtin_skills/` package contains skill templates.
`install_builtin_skill()` copies template files to `~/.cclaw/skills/<name>/` via `shutil.copy2`.
The `install_hints` field (dict) in `skill.yaml` provides installation guidance for missing tools.
`check_skill_requirements()` reads `install_hints` and includes `Install: <hint>` format in error messages.

## Session Continuity (Conversation Bootstrap + --resume)

### Problem

`claude -p` runs as a new process each time and doesn't remember previous conversations.
Context breaks occur when multi-turn flows are needed, like the iMessage skill.
(e.g., "Show messages from John" -> "What would you like to do with this number?")

### Solution

Two mechanisms are combined:

1. **Conversation bootstrap**: On first message, composes bootstrap prompt in order: global memory -> bot memory -> last 20 turns (`MAX_CONVERSATION_HISTORY_TURNS`) from conversation files -> new message
2. **`--resume <session_id>`**: Claude Code's session continuation flag maintains context for subsequent messages

### Session ID Management

- UUID stored in `.claude_session_id` file (`sessions/chat_<id>/.claude_session_id`)
- `get_claude_session_id()`: Reads session ID from file (None if absent)
- `save_claude_session_id()`: Saves session ID to file
- `clear_claude_session_id()`: Deletes session ID file (`missing_ok=True`)

### Daily Conversation Rotation

Conversation history is stored in daily rotating files (`conversation-YYMMDD.md`) instead of a single `conversation.md`.

- **File naming**: `conversation-YYMMDD.md` (UTC date, e.g., `conversation-260225.md`)
- **Writing**: `log_conversation()` always appends to today's dated file
- **Reading**: `load_conversation_history()` searches dated files newest-first, collecting turns until `max_turns` is reached
- **Legacy fallback**: Reads existing `conversation.md` when no dated files exist (no migration needed)
- **Reset**: `/reset` deletes all dated files + legacy file. `/resetall` removes the entire session directory
- **Glob pattern**: Strict `conversation-[0-9][0-9][0-9][0-9][0-9][0-9].md` pattern prevents matching non-conversation files
- **Status display**: `conversation_status_summary()` reports total size and file count for `/status` command

### Conversation History Parsing

`load_conversation_history()` parses conversation files.

- Searches `conversation-YYMMDD.md` files in reverse chronological order (newest first)
- Falls back to legacy `conversation.md` when no dated files exist
- Splits sections via regex `re.split(r"(?=\n## (?:user|assistant) \()", content)`
- Recognizes sections in `## user (timestamp)` or `## assistant (timestamp)` format
- Collects turns across multiple files until `max_turns` is reached
- Returns only the most recent `max_turns` sections
- Returns None if no conversation files exist or all are empty

### Handler Flow

`_prepare_session_context(session_directory, user_message)`:
1. Calls `get_claude_session_id()`
2. If session ID exists: `resume_session=True`, uses original message as-is
3. If no session ID: Generates new UUID -> Composes bootstrap prompt (global memory -> bot memory -> conversation history -> message) -> `save_claude_session_id()`

`_call_with_resume_fallback(send_function, ...)`:
1. First call with configured settings (resume or new session)
2. If `resume_session=True` and `RuntimeError` occurs:
   - Calls `clear_claude_session_id()`
   - Generates new UUID -> Recomposes with bootstrap prompt (same order: global memory -> bot memory -> conversation history -> message)
   - Retries with `resume_session=False`

### Claude Runner Flags

Parameters added to `run_claude()` and `run_claude_streaming()`:
- `claude_session_id: str | None = None`
- `resume_session: bool = False`

Command build:
- `resume_session=True` + `claude_session_id` -> `--resume <id>`
- `resume_session=False` + `claude_session_id` -> `--session-id <id>`

### Reset

`reset_session()` and `reset_all_session()` include `clear_claude_session_id()` calls
so `/reset` and `/resetall` also delete the session ID.

## Bot-Level Long-Term Memory

### Storage Location

`~/.cclaw/bots/<name>/MEMORY.md` — Bot-level file shared across all chat sessions.

### Save Mechanism

Claude Code directly writes to MEMORY.md via its file write tool.
The CLAUDE.md generated by `compose_claude_md()` includes memory instructions and the absolute path to MEMORY.md,
so when Claude Code receives "remember this" requests, it organizes by category and appends to the file.

### Load Mechanism

`_prepare_session_context()` reads GLOBAL_MEMORY.md via `load_global_memory()` and MEMORY.md via `load_bot_memory()` when composing the bootstrap prompt.
Injection order: **global memory -> bot memory -> conversation history -> new message**. Each section is separated by `---`.
`--resume` sessions don't inject memory separately since the Claude Code session maintains its own context.

### Memory Instructions in CLAUDE.md

When `bot_path` parameter is passed to `compose_claude_md()`, a Memory section is added after the Rules section.
`save_bot_config()` and `regenerate_bot_claude_md()` automatically pass `bot_path`.

## Global Memory

### Storage Location

`~/.cclaw/GLOBAL_MEMORY.md` — Root-level file shared across all bots (read-only for bots).

### CRUD Functions

In `session.py`: `global_memory_file_path()`, `load_global_memory()`, `save_global_memory()`, `clear_global_memory()`.
Same pattern as bot memory CRUD. `load_global_memory()` returns `None` when file is missing or empty/whitespace-only.

### Injection Points

Global memory is injected at four points:

1. **CLAUDE.md composition** (`compose_claude_md()` in `skill.py`): "Global Memory (Read-Only)" section placed before bot Memory section. No file path exposed to prevent Claude from modifying it.
2. **Session bootstrap** (`_prepare_session_context()` in `handlers.py`): Injected as first context part in bootstrap prompt.
3. **Resume fallback** (`_call_with_resume_fallback()` in `handlers.py`): Same injection on `--resume` failure fallback.
4. **Cron/Heartbeat execution** (`execute_cron_job()` in `cron.py`, `execute_heartbeat()` in `heartbeat.py`): Injected before bot memory in the prompt.

### CLI Management

`cclaw global-memory show|edit|clear`. After `edit` or `clear`, `_regenerate_all_bots_claude_md()` iterates all bots and regenerates CLAUDE.md + propagates to all sessions via `update_session_claude_md()`.

## macOS Contacts Lookup (osascript)

The iMessage skill uses `osascript` for name-based contact lookups.

```bash
osascript -e 'tell application "Contacts" to get {name, value of phones} of every person whose name contains "search term"'
```

- Partial matching supported: Searching "John" matches "John Smith"
- Prompts user for confirmation when there are duplicate names
- Requires `Bash(osascript:*)` in skill.yaml's `allowed_tools`

## macOS Reminders Permission (reminders-cli)

`reminders-cli` (`brew install keith/formulae/reminders-cli`) requires TCC (Transparency, Consent, and Control) permission to access the macOS Reminders app.

### Permission Popup May Not Appear Automatically

Unlike regular apps, `reminders-cli` may not automatically trigger the macOS permission request popup on first run. Terminal may not appear in the Reminders permission list in System Settings, and the "+" button may not exist for manual addition.

### Solution: Trigger Permission via osascript

AppleScript calls via `osascript` properly trigger the macOS permission popup.

```bash
osascript -e 'tell application "Reminders" to get name of every list'
```

Selecting "Allow" in the popup adds Terminal to the Reminders permission list, after which `reminders-cli` works normally.

### TCC Reset

If `osascript` also fails to show the popup, reset the TCC database and retry.

```bash
tccutil reset Reminders
osascript -e 'tell application "Reminders" to get name of every list'
```

### Fallback: Full Disk Access

If all above methods fail, adding Terminal.app to **System Settings > Privacy & Security > Full Disk Access** serves as a workaround. Full Disk Access includes Reminders access.

### Daemon Mode Note

When running via `cclaw start --daemon`, the shell used by `launchd` also needs the same permissions.

## Heartbeat (Periodic Situation Awareness)

### Configuration Location

Unlike cron which uses a separate `cron.yaml`, heartbeat is stored in the `heartbeat` section of `bot.yaml` (one per bot).

```yaml
heartbeat:
  enabled: false
  interval_minutes: 30
  active_hours:
    start: "07:00"
    end: "23:00"
```

### HEARTBEAT_OK Marker

When `HEARTBEAT_OK_MARKER = "HEARTBEAT_OK"` string is present in Claude's response, no notification is sent.
Exact case match (`HEARTBEAT_OK in response`).
The HEARTBEAT.md template includes the rule "HEARTBEAT_OK must be included at the end of every response".

### Active Hours

Compares local time (`datetime.now()`) in HH:MM format.
Midnight-crossing supported: When `start > end`, treated as overnight range (e.g., 22:00-06:00).

### Dynamic Config in Scheduler

`run_heartbeat_scheduler()` re-reads bot.yaml via `load_bot_config()` every cycle.
Runtime enable/disable via Telegram `/heartbeat on`/`off` takes effect from the next cycle.

### HEARTBEAT.md Creation Timing

On bot creation (`onboarding.py`), only the `heartbeat` config is added to bot.yaml; HEARTBEAT.md is not created.
HEARTBEAT.md is auto-generated from default template when `cclaw heartbeat enable` or Telegram `/heartbeat on` is executed and the file doesn't exist.

### Working Directory

Claude Code runs in `~/.cclaw/bots/{name}/heartbeat_sessions/`.
Bot's CLAUDE.md is copied and a workspace/ subdirectory is created.
Same isolation pattern as cron_sessions/.

### Result Delivery

Sends to all `allowed_users` in bot.yaml. Falls back to session chat IDs via `collect_session_chat_ids()` when `allowed_users` is empty (same fallback as cron).
Prepends `[heartbeat: bot_name]` header to messages.

## Supabase MCP Skill (No-Deletion Guardrails)

### Dual-Layer Permission Defense

The Supabase skill uses two complementary defense layers to prevent data deletion:

**Layer 1 — Hard block via `allowed_tools`**: Destructive MCP tools (`delete_branch`, `reset_branch`, `pause_project`, `restore_project`) are excluded from `skill.yaml`'s `allowed_tools` list. In Claude Code's `-p` mode, tools not in `allowed_tools` cannot receive auto-approval, so they are effectively blocked from execution. The `_write_session_settings()` function in `claude_runner.py` writes only the safe tools to `.claude/settings.json`.

**Layer 2 — Soft block via SKILL.md instructions**: For tools that are allowed but can perform destructive operations (notably `execute_sql` which can run any SQL), SKILL.md contains explicit guardrails forbidding `DELETE FROM`, `DROP TABLE`, `TRUNCATE`, and related statements. Claude is instructed to suggest soft delete patterns instead.

### MCP Server Environment Variable Injection

The Supabase MCP server requires `SUPABASE_ACCESS_TOKEN`. This flows through the skill system:

1. `skill.yaml` declares `environment_variables: [SUPABASE_ACCESS_TOKEN]`
2. `cclaw skills setup supabase` prompts the user and stores the value in `environment_variable_values`
3. `collect_skill_environment_variables()` reads the stored value during `run_claude()`
4. The value is injected into the subprocess `env` parameter
5. The MCP server (started by Claude Code) inherits the environment variable

### MCP Config Merging

The `mcp.json` in the skill directory defines the Supabase MCP server configuration. During `run_claude()`, `merge_mcp_configs()` combines all attached MCP skill configs into a single `.mcp.json` file in the session working directory. Claude Code auto-detects this file and starts the configured MCP servers.

## Per-Skill Emoji Display

Each builtin skill has an `emoji` field in its `skill.yaml` (e.g., `"\U0001F4AC"` for iMessage). Emojis are used in README documentation and skill guides but are not displayed in the CLI or Telegram skills table to avoid terminal width calculation issues (see "Emoji Width Consistency" section below).

### Builtin Fallback

Already-installed skills (copied to `~/.cclaw/skills/`) may lack the `emoji` field if installed before it was added. `list_skills()` in `skill.py` falls back to the builtin template's emoji via `get_builtin_skill_path()` when the installed config has no emoji.

## Twitter/X MCP Skill

### MCP Server Environment Variable Mapping

The `@enescinar/twitter-mcp` package expects generic env var names (`API_KEY`, `API_SECRET_KEY`, `ACCESS_TOKEN`, `ACCESS_TOKEN_SECRET`). To avoid namespace collision with other skills, cclaw uses `TWITTER_`-prefixed names in `skill.yaml`:

- `TWITTER_API_KEY`
- `TWITTER_API_SECRET_KEY`
- `TWITTER_ACCESS_TOKEN`
- `TWITTER_ACCESS_TOKEN_SECRET`

The `mcp.json` uses a `/bin/sh -c` wrapper to map prefixed env vars to the generic names the package expects:

```json
{
  "mcpServers": {
    "twitter": {
      "command": "/bin/sh",
      "args": ["-c", "API_KEY=\"$TWITTER_API_KEY\" ... npx -y @enescinar/twitter-mcp"]
    }
  }
}
```

This shell wrapper approach is necessary because:
1. Static `mcp.json` cannot reference dynamic env var values
2. Claude Code's MCP config `env` block requires literal values
3. The `/bin/sh` command renames the env vars at MCP server launch time

### Safety Guardrails

SKILL.md enforces confirmation before posting. The bot must show the full tweet text and receive user approval before calling `post_tweet`. Character limit (280) is checked before posting.

### Rate Limits

Free tier: 500 posts/month (~16 per day). The skill instructs Claude to inform users when rate limits are exceeded.

## Jira MCP Skill

### MCP Server

The Jira skill uses `sooperset/mcp-atlassian` (Python package) via `uvx`. Unlike the Twitter skill, no `/bin/sh -c` wrapper is needed because the package natively reads `JIRA_`-prefixed environment variables (`JIRA_URL`, `JIRA_USERNAME`, `JIRA_API_TOKEN`), which matches the cclaw skill convention.

### Environment Variable Flow

1. `skill.yaml` declares `environment_variables: [JIRA_URL, JIRA_USERNAME, JIRA_API_TOKEN]`
2. `cclaw skills setup jira` prompts the user and stores values in `environment_variable_values`
3. `collect_skill_environment_variables()` reads stored values during `run_claude()`
4. Values are injected into the subprocess `env` parameter
5. The MCP server (started by Claude Code via `uvx mcp-atlassian`) inherits the environment variables

### Safety Guardrails

SKILL.md enforces confirmation before creating issues and before transitioning workflow status. Issue deletion is forbidden — closing or moving is suggested instead. Bulk modifications require explicit approval.

### Allowed Tools

Only 5 tools are auto-approved: `jira_search`, `jira_get_issue`, `jira_create_issue`, `jira_update_issue`, `jira_transition_issue`. The `mcp-atlassian` package also provides Confluence tools, but they are not listed in `allowed_tools` and therefore blocked in `-p` mode.

## Token Compact

### Target Selection

`collect_compact_targets()` collects three types of files:

1. **MEMORY.md** (`~/.cclaw/bots/<name>/MEMORY.md`): Bot long-term memory that grows over time
2. **User-created SKILL.md**: Skills attached to the bot, excluding builtins (`is_builtin_skill()` check). Builtin skills are already compressed at build time
3. **HEARTBEAT.md** (`~/.cclaw/bots/<name>/heartbeat_sessions/HEARTBEAT.md`): Periodic check checklist

Empty files (whitespace-only) are skipped.

### Compression Approach

Each target is compressed via a separate one-shot `claude -p` call with a structured prompt (`COMPACT_PROMPT`). The `document_type` parameter provides context-specific guidance (e.g., "Bot long-term memory" vs "AI assistant skill instructions").

Each call runs in a fresh `tempfile.TemporaryDirectory()` — no session state, no MCP config, no skill injection needed.

### Token Estimation

`estimate_token_count()` uses `len(text) // 4` (minimum 1). This is a rough heuristic sufficient for relative before/after comparison in the report. Not intended for billing accuracy.

### Error Isolation

`run_compact()` processes targets sequentially. If one target's compression fails (Claude timeout, runtime error, etc.), the error is captured in `CompactResult.error` and remaining targets continue processing. `save_compact_results()` only writes back results with no error.

### Post-Save Propagation

After saving compacted files, both CLI and Telegram handlers call `regenerate_bot_claude_md()` + `update_session_claude_md()` to propagate SKILL.md changes into bot and session CLAUDE.md files.

## Encrypted Backup

### Why pyzipper

Python's built-in `zipfile` module supports reading encrypted zips but cannot create them. The system `zip -P` command exposes the password in the process list (`ps aux`). `pyzipper` provides AES-256 encryption with a `zipfile`-compatible API, pure Python, no system dependency.

### Password Handling

Password is read via `getpass.getpass()` which masks terminal input. Confirmed twice to prevent typos. The password string is encoded to bytes (`password.encode()`, UTF-8) before passing to pyzipper's `setpassword()`. The password is never logged or stored.

### File Collection

`collect_backup_files()` walks `~/.cclaw/` via `Path.rglob("*")`. Two exclusion rules:
- `cclaw.pid`: Runtime artifact, meaningless after process ends
- `__pycache__/`: Python bytecode cache, regenerated automatically

### Output

Backup file is written to the current working directory as `YYMMDD-cclaw.zip`. Same-day re-runs prompt for overwrite via `typer.confirm()`.

## Emoji Width Consistency (Variation Selector-16)

### Problem

Some emojis in skill.yaml have Unicode `east_asian_width=N` (Narrow), rendering as 1 terminal column instead of 2. This breaks column alignment in Rich tables (e.g., `cclaw skills` list).

Affected emojis: `\U0001F5BC` (image), `\U0001F5FA` (naver-map), `\U0001F5C4` (supabase).

### Solution

Append Variation Selector-16 (`\uFE0F`) to force emoji presentation (Wide, 2 columns):

- `\U0001F5BC\uFE0F` (🖼️), `\U0001F5FA\uFE0F` (🗺️), `\U0001F5C4\uFE0F` (🗄️)

### Note

Installed skills (`~/.cclaw/skills/`) may lack the `emoji` field. The `list_skills()` fallback in `skill.py` reads the emoji from the builtin template via `get_builtin_skill_path()`, so only the builtin template needs the fix.

## QMD Auto-Injection (System-Wide)

### Auto-Detect Mechanism

QMD is auto-injected into all bots when `shutil.which("qmd")` returns a path. No skill installation or attachment needed — `npm install -g @tobilu/qmd` is the only prerequisite.

Two injection points:
1. **`_prepare_skill_config()`** in `claude_runner.py`: Injects `QMD_MCP_SERVER` (`localhost:8181/mcp`, HTTP type) and `QMD_ALLOWED_TOOLS` (6 tools) into every session's `.mcp.json` and `.claude/settings.json`
2. **`compose_claude_md()`** in `skill.py`: Appends QMD SKILL.md instructions from `builtin_skills/qmd/SKILL.md`. Deduplicates if qmd is also attached as a regular skill

### HTTP Daemon Lifecycle

- `bot_manager.py` checks `shutil.which("qmd")` before starting bots
- Calls `_start_qmd_daemon()`: runs `qmd mcp --http --daemon` (synchronous subprocess, QMD self-daemonizes)
- Health check: TCP connect to `localhost:8181` with 2s timeout, retried up to 30 times with 1s sleep
- On shutdown: `_stop_qmd_daemon()` runs `qmd mcp stop`
- Also called from `stop_bots()` for the `cclaw stop` command

### Conversation Collection

`_ensure_qmd_conversations_collection()` runs on startup after daemon is ready:
```
qmd collection add ~/.cclaw/bots/ --name cclaw-conversations --mask "**/conversation-*.md"
```
This makes all bot conversation logs searchable via QMD.

### Test Isolation

`tests/conftest.py` has an autouse fixture that patches `shutil.which` to return `None` for `"qmd"`:

```python
@pytest.fixture(autouse=True)
def disable_qmd_auto_inject(monkeypatch):
    monkeypatch.setattr(shutil, "which", _which_without_qmd)
```

Patches at the `shutil` module level (not per-module reference) to ensure all code paths see the mock. QMD-specific tests in `test_qmd.py` override with explicit `patch()` calls.

Note: `test_claude_runner.py`'s `mock_claude_path` fixture uses `side_effect` (not `return_value`) to return `/usr/local/bin/claude` only for `"claude"` and `None` for other commands. Using `return_value` would return the claude path for all `shutil.which()` calls including `"qmd"`, triggering QMD auto-injection.

## Group Collaboration

### Orchestrator Pattern

Each group has one orchestrator and zero or more members. The orchestrator receives user messages and bot reports; members only respond to @mentions from bots.

### Message Routing (`_should_handle_group_message`)

Role-based filtering in `handlers.py`:

- **Orchestrator**: Handles user messages (`not is_bot`) and member bot @mentions (bot message mentioning orchestrator's username)
- **Member**: Only handles messages from bots that @mention the member's username
- **Self-message**: All bots ignore their own messages (sender user_id == bot.id)

### Authorization Bypass for Bots

When `allowed_users` is configured, bot-to-bot @mention delegation would fail because bot user IDs aren't in the allowlist. Solution: in `message_handler`, group binding is checked **before** authorization. If the sender is a bot (`is_bot == True`) in a bound group, authorization is skipped entirely. Human users are still checked against `allowed_users`.

### Shared Conversation Log

All group messages are logged to `groups/<name>/conversation/YYMMDD.md` (UTC date):

- **User input**: Logged in `message_handler` before `_should_handle_group_message`
- **Claude response**: Logged in `_process_message` after `log_conversation`, via `find_group_by_chat_id` check
- **Deduplication**: Each bot process that receives the same group update writes the incoming message. Since each bot only writes its own Claude response (not other bots'), response logs are not duplicated.
- **Format**: `[HH:MM:SS] sender: content` where sender is "user" or "@bot_name"

### Shared Workspace

`groups/<name>/workspace/` is a flat directory shared by all group members. Bots write outputs here for inter-bot collaboration. The workspace is **preserved** on `/reset` (only conversation and sessions are cleared).

### CLAUDE.md Group Context Injection

`compose_group_claude_md()` in `skill.py` generates role-specific CLAUDE.md:

- **Orchestrator**: Team roster (member names, usernames, roles), delegation rules (use @mention), synthesis instructions
- **Member**: Own role context, shared conversation history (recent messages for context continuity)

The group CLAUDE.md is written to each bot's session directory via `ensure_session()` when `find_group_by_chat_id()` returns a group config.

### Session Reset in Groups

`/reset` from orchestrator:
1. Clears all bots' sessions (orchestrator + members) for this chat
2. Clears shared conversation log
3. Preserves shared workspace
4. Members' `/reset` is ignored (only orchestrator can reset)

### Session CLAUDE.md After Unbind

When `/unbind` removes a group binding, existing session CLAUDE.md files retain stale group context. This is resolved on next message: `ensure_session()` regenerates CLAUDE.md from the current bot's `CLAUDE.md` (which no longer contains group context after the binding is removed).

## IME-Compatible CLI Input

### Problem

`Rich.Console.input()` and `typer.prompt()` (which uses `click.prompt`) interfere with CJK IME composition in certain terminals (e.g., Warp). Korean characters break during composition, producing garbled or incomplete input.

### Solution

All CLI input prompts use Python's builtin `input()` wrapped in two utility functions in `utils.py`:

- `prompt_input(label, default=None)`: Single-line input. Uses `Rich.Console.print()` for label display, then `input()` for actual input capture. Optional `default` parameter returns the default value when input is empty.
- `prompt_multiline(label)`: Multi-line input. Reads lines until an empty line is entered. Used for bot personality, description, cron messages, etc.

### Applied Locations

- `onboarding.py`: Bot Token, Bot name, personality, description
- `cli.py` skill commands: skill name, description, type, required commands, environment variables, environment variable values
- `cli.py` cron commands: job name, schedule, timezone, at value, message, skills, model

### Not Changed

- `typer.confirm()` (y/n prompts): These work correctly with IME since they only accept single ASCII characters.
- `typer.Argument` / `typer.Option`: These are parsed from command-line arguments, not interactive prompts.
