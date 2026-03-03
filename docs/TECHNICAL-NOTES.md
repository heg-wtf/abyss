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

Two execution modes are supported:

- **Batch mode**: `claude -p "<message>" --output-format text` (cron, heartbeat, etc.)
- **Streaming mode**: `claude -p "<message>" --output-format stream-json --verbose --include-partial-messages` (Telegram conversations)

The working directory is set to the session directory via the subprocess `cwd` parameter.

- `shutil.which("claude")` resolves the full path to the Claude CLI. Works regardless of installation method (`uv run`, `pip install`, `pipx install`, etc.) by searching PATH. Raises `RuntimeError` with installation guidance if not found.
- `--output-format text`: Text output (not JSON)
- `--model <model>`: Model selection (sonnet/opus/haiku). Flag is omitted when `model` parameter is None.
- Additional arguments can be passed via the `claude_args` field in `bot.yaml`
- Default timeout: 300 seconds (`command_timeout` in `config.yaml`)

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

- Module-level `_running_processes` dictionary maps `{bot_name}:{chat_id}` to subprocess
- When `session_key` is passed to `run_claude()`, the process is automatically registered/deregistered
- `/cancel` command calls `cancel_process()` which invokes `process.kill()` (SIGKILL)
- When process is killed: `returncode == -9` -> raises `asyncio.CancelledError`
- Handler catches `CancelledError` and sends "Execution was cancelled" message

## Graceful Shutdown (cancel_all_processes)

`cancel_all_processes()` iterates `_running_processes` and kills all running subprocesses (`returncode is None`), then clears the registry.

Called first in `bot_manager.py`'s shutdown sequence (before `application.stop()`). Without this, `application.stop()` waits for running handler coroutines to complete, which blocks until the Claude subprocess finishes (up to `command_timeout`, default 300 seconds). By killing subprocesses first, the handlers complete immediately and shutdown proceeds without delay.

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
