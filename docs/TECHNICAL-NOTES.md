# Technical Notes

## ABYSS_HOME Environment Variable

The runtime data path defaults to `~/.abyss/` and can be changed via the `ABYSS_HOME` environment variable.
In tests, isolation is achieved via `monkeypatch.setenv("ABYSS_HOME", str(tmp_path))`.

## Path Management Principles

All paths use absolute paths. The `bot_directory(name)` function in `config.py` returns the absolute path `abyss_home() / "bots" / name`, and other modules access bot directories through this function. Absolute paths are also stored in bot entries in `config.yaml`. Avoid relative paths and use `pathlib.Path` for path composition.

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
- Always merges Claude Code feature env vars (see below) on top of `os.environ`
- Collects environment variables from all attached skills (skills override Claude Code env on key collision)
- **QMD auto-injection**: When `shutil.which("qmd")` returns non-None, auto-appends QMD HTTP MCP server config and allowed tools regardless of skill attachment
- Returns `(allowed_tools, environment_variables)` tuple
- Used by `run_claude()`, `run_claude_streaming()`, `run_claude_with_sdk()`, `run_claude_streaming_with_sdk()`

### Claude Code Feature Env Vars

`config.get_claude_code_env()` returns env vars injected into every `claude -p` subprocess and Python Agent SDK call. The `claude_code` section of `~/.abyss/config.yaml` toggles each one (default: all on):

| `config.yaml` key       | Env var                       | Value  | Effect |
|-------------------------|-------------------------------|--------|--------|
| `prompt_caching_1h`     | `ENABLE_PROMPT_CACHING_1H`    | `1`    | Switches Claude Code prompt cache TTL from 5m to 1h. Reduces re-prompt cost for idle bots and multi-call heartbeat/cron flows |
| `fork_subagent`         | `CLAUDE_CODE_FORK_SUBAGENT`   | `1`    | Enables forked subagents in non-interactive (`-p`) mode. Lets bots run parallel sub-tasks |
| `mcp_nonblocking`       | `MCP_CONNECTION_NONBLOCKING`  | `true` | `claude -p` no longer blocks startup waiting on slow MCP servers (auto-retry handles transient failures) |
| `hide_cwd`              | `CLAUDE_CODE_HIDE_CWD`        | `1`    | Masks the working-directory path from system prompts. Hides `~/.abyss/bots/<name>/sessions/...` from the model |
| (always-on, not toggle) | `AI_AGENT`                    | `abyss`| Marks subprocesses as launched by abyss. Used by hook scripts (Phase 3+) to short-circuit when fired outside abyss |

### MCP `alwaysLoad` (Phase 2 — Claude Code 2.1.121)

`config.is_mcp_always_load_enabled()` reads `claude_code.mcp_always_load` (default `True`). When on, abyss-injected MCP entries (qmd, conversation_search) are written to `.mcp.json` with `"alwaysLoad": true` so Claude Code preconnects them at host startup instead of lazily on first call. Combined with `MCP_CONNECTION_NONBLOCKING=true`, this avoids both startup latency *and* first-call latency for these two heavy MCPs.

`_qmd_mcp_server(always_load: bool)` and `_conversation_search_mcp_server(working_directory)` are the helpers that emit the flag conditionally. User skills' own `mcp.json` entries pass through untouched.

### MCP Tool Result Size Ceiling (Phase 2 — Claude Code 2.1.91)

The `conversation_search` MCP server (`abyss/mcp_servers/conversation_search.py`) sets `_meta["anthropic/maxResultSizeChars"] = 500_000` on every `tools/call` result (success and error). Claude Code uses this hint when persisting tool output to the transcript so large hit lists are not silently truncated. The constant `MAX_RESULT_SIZE_CHARS` lives next to `RESULT_META` in the server module.

Example `config.yaml`:

```yaml
claude_code:
  prompt_caching_1h: true
  fork_subagent: true
  mcp_nonblocking: true
  hide_cwd: true
```

A missing or invalid `claude_code` section falls back to all-on defaults. `bot_manager._run_bots` logs the active env at startup.

`config.apply_claude_code_env(base)` is the canonical way to apply these toggles to a base env dict. It overwrites enabled keys with abyss values **and explicitly removes disabled keys** so a stray `export ENABLE_PROMPT_CACHING_1H=1` in `~/.zshrc` cannot resurrect a feature the user turned off in `config.yaml`. `_prepare_skill_config` calls it on top of `os.environ` before merging skill env.

### Effort Level & ultrareview Wrapper (Phase 6 — Claude Code 2.1.111 / 2.1.120)

`bot.yaml.effort` (one of `low|medium|high|xhigh|max`) is read by `claude_runner._effort_flag_args(working_directory)` and added to the `claude -p` command line as `--effort <level>` for both batch (`run_claude`) and streaming (`run_claude_streaming`) paths. Invalid or missing values fall back to Claude Code's own default (`high` for Pro / Max subscribers on Opus 4.6 / Sonnet 4.6). Whitespace and case are normalised. The flag is session-scoped per CC docs — the SDK pool path doesn't expose effort yet, so explicit per-bot effort is delivered via the subprocess fallback.

`run_ultrareview(target, working_directory, *, json_output=True, timeout=1800, extra_arguments=None)` wraps `claude ultrareview <target>` (CC 2.1.120). It applies the same `apply_claude_code_env` baseline so the review subprocess gets the abyss-controlled env (1h cache, AI_AGENT, hide_cwd, etc.). Default timeout matches CC's own 30-minute cap. The result is the raw stdout — JSON when `json_output=True`, prose when `False`.

The new builtin skill `code_review` is the user-facing entry point: it documents how a bot should detect a review request, invoke `claude ultrareview <target> --json`, summarise the findings to the chat, and adapt the verbosity to the session's `${CLAUDE_EFFORT}` template variable. `skill.yaml` whitelists only `Bash(claude ultrareview:*)` so the skill cannot expand into arbitrary shell access.

### Sandbox & Skill Shell-Execution (Phase 5 — Claude Code 2.1.91 / 2.1.113)

`_apply_security_settings(working_directory, settings)` writes two security keys into every session settings.json:

1. `disableSkillShellExecution` (boolean) — enabled when any attached skill is flagged `untrusted: true`. `import_skill_from_github` flips this on for every GitHub-sourced skill, alongside a `source: {type: github, url}` provenance block. `is_untrusted_skill(name)` and `has_untrusted_skill(skill_names)` are the helpers.
2. `sandbox.network.deniedDomains` (array of strings) — `config.compose_bot_sandbox(bot_config)` returns the merged blocklist: `DEFAULT_SANDBOX_DENIED_DOMAINS` (cloud-metadata endpoints for GCP / AWS / Azure / Tencent / Aliyun) plus any extras declared under `bot.yaml.sandbox.denied_domains` (snake_case) or `sandbox.deniedDomains` (camelCase alias). Duplicates and non-string entries are dropped; defaults are preserved first so per-bot extras can extend but never replace them.

Both keys are recomputed every time `_write_session_settings` runs, so flipping a skill's `untrusted` flag or editing `bot.yaml.sandbox` takes effect on the next message without a daemon restart.

### PostToolUse Telemetry & Skill-Conditional Hooks (Phase 4 — Claude Code 2.1.85 / 2.1.119)

`abyss/hooks/log_tool_metrics.py` is a stdin-driven Python script registered as a Claude Code PostToolUse hook **and** PostToolUseFailure hook (matcher `*` for both). PostToolUse fires only on tool success — failed tool executions land on the separate `PostToolUseFailure` channel — so abyss registers the same script on both events and disambiguates via `ABYSS_HOOK_OUTCOME=success|failure` set in the hook command line. The recorded event carries an `outcome` field; aggregation counts a call as an error when `outcome == "failure"` **or** `exit_code != 0`. For each tool call, Claude Code 2.1.119 surfaces `duration_ms` on the payload; the hook resolves the bot from `cwd`, then calls `abyss.tool_metrics.append_event(bot_name, tool, duration_ms, …)` to append one JSONL row per call.

Storage layout: `~/.abyss/bots/<name>/tool_metrics/YYMMDD.jsonl`. One file per UTC day, rotated on every append (files older than `RETENTION_DAYS = 7` days are deleted). Each row is `{"ts", "tool", "duration_ms", "exit_code"?, "session_id"?}`. Markdown is *not* the source of truth — these JSONL files are.

Aggregation: `abyss.tool_metrics.aggregate(bot_name)` returns per-tool rows with `count`, `p50_ms`, `p95_ms`, `p99_ms`, `error_count`. The mirror function on the abysscope side, `getToolMetrics(name)`, reads the same files via `lib/abyss.ts` and feeds the new "Metrics" tab on the bot detail page (`components/tool-latency-panel.tsx`).

Same safety contract as the PreCompact hook (Phase 3):

- `AI_AGENT == "abyss"` guard — hook is a no-op for non-abyss subprocesses.
- Never blocks: empty stdin, malformed JSON, missing `cwd` / `tool_name` / `duration_ms`, unresolvable bot dir, and exceptions all return exit 0.
- Per-bot opt-out via `bot.yaml.hooks_enabled: false` skips both PostToolUse and PreCompact.

#### Skill-Conditional Hooks

Each skill may declare extra hook entries in its `skill.yaml`:

```yaml
hooks:
  PostToolUse:
    - matcher: "Bash"
      if: "tool_input.command =~ /rm -rf/"
      hooks:
        - type: command
          command: /usr/local/bin/safety-check.sh
```

`abyss.skill.collect_skill_hooks(skill_names, event_name)` returns these entries unchanged — abyss writes the optional `if` field through verbatim so Claude Code 2.1.85 can evaluate it. Supported events are `PreToolUse`, `PostToolUse`, `UserPromptSubmit`, `Stop`, `SubagentStop`, `SessionStart`, `PreCompact`, `PermissionDenied`. Malformed entries (missing inner `hooks` list, non-dict items, unsupported events) are dropped silently — a broken hook must never block tool execution.

`_write_session_settings` calls `_merge_skill_hooks(working_directory, "PostToolUse", existing=[abyss baseline])` so abyss's `log_tool_metrics` always runs first, followed by skill-supplied entries.

### PreCompact Hook (Phase 3 — Claude Code 2.1.105)

`abyss/hooks/precompact_hook.py` is a stdin-driven Python script registered as a Claude Code PreCompact hook in every bot session's `.claude/settings.json`. When the host decides to compact the in-flight conversation, it invokes the hook with a JSON payload (`{cwd, session_id, transcript_path, …}`); abyss reuses that signal to also compact the bot's persistent files (MEMORY.md / HEARTBEAT.md / user SKILL.md) via `token_compact.run_compact(bot_name)`.

Safety properties:

- **`AI_AGENT` guard.** The script first checks `os.environ.get("AI_AGENT") == "abyss"` and silently exits 0 otherwise. Combined with Phase 1's env injection (only abyss subprocesses get `AI_AGENT=abyss`), this means the hook is a no-op even if the command somehow ends up referenced from `~/.claude/settings.json`.
- **Never blocks.** Empty stdin, malformed JSON, missing `cwd`, unresolvable bot directory, and exceptions from `run_compact` all return exit 0. The host's transcript compact proceeds either way.
- **Bot resolution.** Mirrors `claude_runner._resolve_bot_dir_from_working_directory` — walks parents of `cwd` until one whose parent is named `bots`. Works for DM (`bots/<name>/sessions/chat_*`), cron (`bots/<name>/cron_sessions/<job>`) and heartbeat (`bots/<name>/heartbeat_sessions`) sessions alike.

Where it lives in settings: `_write_session_settings` always writes `<session>/.claude/settings.json` (no longer conditional on `allowed_tools`) and injects `hooks.PreCompact = [{matcher: "", hooks: [{type: "command", command: "python -m abyss.hooks.precompact_hook"}]}]`. Existing non-PreCompact hook entries (e.g. user-supplied `PreToolUse`) are preserved; `enabledPlugins: {}` still disables user plugins. Per-bot opt-out via `bot.yaml.hooks_enabled: false` skips the PreCompact injection while leaving permissions/plugins behavior untouched. Cron and heartbeat continue to call `run_compact` on their own schedule as a fallback for environments where the hook never fires (older Claude Code, hooks disabled).

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

- **FileHandler**: Writes to `~/.abyss/logs/abyss-YYMMDD.log` with full format (`%(asctime)s [%(name)s] %(levelname)s: %(message)s`)
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
- Also changeable via CLI `abyss bot model <name> [model]`.

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

`abyss start --daemon` creates `~/Library/LaunchAgents/com.abyss.daemon.plist` and runs `launchctl load`.
`KeepAlive` is enabled so the process auto-restarts on termination.
`abyss stop` runs `launchctl unload` then deletes the plist.

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

When a new bot is created via `abyss init` or `abyss bot add` while the daemon is already running, the daemon is automatically restarted to pick up the new bot. This ensures the new bot's Telegram polling and command menu are registered immediately.

- `_is_daemon_running()` in `onboarding.py` checks if the launchd plist file exists
- `_restart_daemon()` calls `stop_bots()` then `start_bots(daemon=True)`
- If the daemon is not running, a message is shown: "Start the bot: abyss start"
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
- Also changeable via CLI `abyss bot streaming <name> [on|off]`.
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

- **Built-in** (`builtin`): Pre-packaged with abyss in `src/abyss/builtin_skills/`. Installable via `abyss skills install <name>`.
- **Custom** (`custom`): User-created via `abyss skills add`. Can be markdown-only or tool-based.

Internally, `skill.yaml` has a `type` field (cli/mcp/browser/None) for tool configuration, but the display (CLI `abyss skills` and Telegram `/skills`) shows origin-based classification (builtin/custom).

### CLAUDE.md Composition

`compose_claude_md()` merges bot profile + skill SKILL.md content into a single CLAUDE.md.
Without skills, output is identical to the existing `generate_claude_md()`.
CLAUDE.md is auto-regenerated when `save_bot_config()` is called.
On bot start, `regenerate_bot_claude_md()` reflects the latest skill state.

### Circular Reference Resolution

Bidirectional dependency exists between `config.py` and `skill.py`.
Resolved via lazy import: `from abyss.skill import compose_claude_md` inside `save_bot_config()` in `config.py`.

### MCP Skills

MCP skills define `mcpServers` configuration in `mcp.json` files.
During `run_claude()`, `merge_mcp_configs()` merges all linked MCP skill configs
and creates `.mcp.json` in the session directory. Claude Code auto-detects this file.

### Default Allowed Tools

When any skill defines `allowed_tools`, the `--allowedTools` flag activates a whitelist — only listed tools are auto-approved. This blocks basic tools (WebFetch, WebSearch, Bash) that aren't skill-specific but are essential for general operation.

`DEFAULT_ALLOWED_TOOLS` in `claude_runner.py` solves this by always merging `WebFetch`, `WebSearch`, and `Bash` into the whitelist when it's active. Without this, attaching any tool-based skill would disable web access and shell execution.

### CLI Skill Environment Variables

CLI skills store values in `skill.yaml`'s `environment_variable_values`.
Environment variable values are collected during `abyss skills setup`.
During `run_claude()`, `collect_skill_environment_variables()` gathers them
and injects into the subprocess `env` parameter.

### Skill Setup with Unconfigured Environment Variables

`abyss skills setup` normally skips already-active skills. However, if a skill is active but has unconfigured environment variables (empty values), setup re-enters the environment variable prompt. This handles the case where `abyss skills install` auto-activates an MCP skill (no `required_commands` failure) before environment variables are set.

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

- Each job runs in `~/.abyss/bots/{name}/cron_sessions/{job_name}/`
- Bot's CLAUDE.md is copied so Claude Code recognizes bot context
- Completely isolated from regular sessions, no interference between cron jobs

### One-Shot Jobs

- `at` field triggers one-shot execution instead of schedule
- Supports ISO 8601 datetime (`2026-02-20T15:00:00`) or duration shorthand (`30m`, `2h`, `1d`)
- **Relative-to-absolute conversion**: `add_cron_job()` converts relative durations (e.g., `10m`) to absolute ISO datetime at creation time. Without this, the scheduler would re-evaluate `parse_one_shot_time("10m")` every 30-second cycle, always computing `now + 10m`, causing the job to never fire
- **Post-execution cleanup**: `delete_after_run: true` auto-deletes from `cron.yaml`. `delete_after_run: false` sets `enabled: false` to prevent re-execution on restart (since `last_run_times` is in-memory only and lost on restart)

### Cron Job Message Editing

- Only the `message` field is editable. Name and schedule require remove + add.
- **CLI**: `abyss cron edit <bot> <job>` opens `$EDITOR` (via `click.edit()`) pre-filled with current message. Save and close to apply; empty or unchanged content cancels.
- **Telegram**: `/cron edit <name>` sends current message with `ForceReply` markup. User's next message becomes the new content.
- **ForceReply state**: `pending_cron_edits: dict[int, str]` (chat_id -> job_name) in handler closure. `message_handler` checks this dict before normal message processing — if a pending edit exists for the chat, it processes the reply as a cron edit and returns early.
- `edit_cron_job_message()` in `cron.py` follows the same pattern as `enable_cron_job`/`disable_cron_job`: load config, find job by name, update field, save.

### Telegram /skills Handler (Unified)

The `/skills` handler manages skill listing, attach, and detach (previous `/skill` handler merged into `/skills`).
The `attached_skills` variable in the handler closure tracks currently linked skills.
After attach/detach, the local `bot_config["skills"]` is directly updated to sync memory and disk state.
(`attach_skill_to_bot()` only modifies the on-disk config, so the in-memory `bot_config` must be updated separately.)
`run_claude()` receives `skill_names=attached_skills`.
Uninstalled built-in skills are also listed at the bottom via `list_builtin_skills()`.

### Built-in Skills

The `src/abyss/builtin_skills/` package contains skill templates.
`install_builtin_skill()` copies template files to `~/.abyss/skills/<name>/` via `shutil.copy2`.
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

`~/.abyss/bots/<name>/MEMORY.md` — Bot-level file shared across all chat sessions.

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

`~/.abyss/GLOBAL_MEMORY.md` — Root-level file shared across all bots (read-only for bots).

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

`abyss global-memory show|edit|clear`. After `edit` or `clear`, `_regenerate_all_bots_claude_md()` iterates all bots and regenerates CLAUDE.md + propagates to all sessions via `update_session_claude_md()`.

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

When running via `abyss start --daemon`, the shell used by `launchd` also needs the same permissions.

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
HEARTBEAT.md is auto-generated from default template when `abyss heartbeat enable` or Telegram `/heartbeat on` is executed and the file doesn't exist.

### Working Directory

Claude Code runs in `~/.abyss/bots/{name}/heartbeat_sessions/`.
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
2. `abyss skills setup supabase` prompts the user and stores the value in `environment_variable_values`
3. `collect_skill_environment_variables()` reads the stored value during `run_claude()`
4. The value is injected into the subprocess `env` parameter
5. The MCP server (started by Claude Code) inherits the environment variable

### MCP Config Merging

The `mcp.json` in the skill directory defines the Supabase MCP server configuration. During `run_claude()`, `merge_mcp_configs()` combines all attached MCP skill configs into a single `.mcp.json` file in the session working directory. Claude Code auto-detects this file and starts the configured MCP servers.

## Per-Skill Emoji Display

Each builtin skill has an `emoji` field in its `skill.yaml` (e.g., `"\U0001F4AC"` for iMessage). Emojis are used in README documentation and skill guides but are not displayed in the CLI or Telegram skills table to avoid terminal width calculation issues (see "Emoji Width Consistency" section below).

### Builtin Fallback

Already-installed skills (copied to `~/.abyss/skills/`) may lack the `emoji` field if installed before it was added. `list_skills()` in `skill.py` falls back to the builtin template's emoji via `get_builtin_skill_path()` when the installed config has no emoji.

## Twitter/X MCP Skill

### MCP Server Environment Variable Mapping

The `@enescinar/twitter-mcp` package expects generic env var names (`API_KEY`, `API_SECRET_KEY`, `ACCESS_TOKEN`, `ACCESS_TOKEN_SECRET`). To avoid namespace collision with other skills, abyss uses `TWITTER_`-prefixed names in `skill.yaml`:

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

The Jira skill uses `sooperset/mcp-atlassian` (Python package) via `uvx`. Unlike the Twitter skill, no `/bin/sh -c` wrapper is needed because the package natively reads `JIRA_`-prefixed environment variables (`JIRA_URL`, `JIRA_USERNAME`, `JIRA_API_TOKEN`), which matches the abyss skill convention.

### Environment Variable Flow

1. `skill.yaml` declares `environment_variables: [JIRA_URL, JIRA_USERNAME, JIRA_API_TOKEN]`
2. `abyss skills setup jira` prompts the user and stores values in `environment_variable_values`
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

1. **MEMORY.md** (`~/.abyss/bots/<name>/MEMORY.md`): Bot long-term memory that grows over time
2. **User-created SKILL.md**: Skills attached to the bot, excluding builtins (`is_builtin_skill()` check). Builtin skills are already compressed at build time
3. **HEARTBEAT.md** (`~/.abyss/bots/<name>/heartbeat_sessions/HEARTBEAT.md`): Periodic check checklist

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

`collect_backup_files()` walks `~/.abyss/` via `Path.rglob("*")`. Two exclusion rules:
- `abyss.pid`: Runtime artifact, meaningless after process ends
- `__pycache__/`: Python bytecode cache, regenerated automatically

### Output

Backup file is written to the current working directory as `YYMMDD-abyss.zip`. Same-day re-runs prompt for overwrite via `typer.confirm()`.

## Emoji Width Consistency (Variation Selector-16)

### Problem

Some emojis in skill.yaml have Unicode `east_asian_width=N` (Narrow), rendering as 1 terminal column instead of 2. This breaks column alignment in Rich tables (e.g., `abyss skills` list).

Affected emojis: `\U0001F5BC` (image), `\U0001F5FA` (naver-map), `\U0001F5C4` (supabase).

### Solution

Append Variation Selector-16 (`\uFE0F`) to force emoji presentation (Wide, 2 columns):

- `\U0001F5BC\uFE0F` (🖼️), `\U0001F5FA\uFE0F` (🗺️), `\U0001F5C4\uFE0F` (🗄️)

### Note

Installed skills (`~/.abyss/skills/`) may lack the `emoji` field. The `list_skills()` fallback in `skill.py` reads the emoji from the builtin template via `get_builtin_skill_path()`, so only the builtin template needs the fix.

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
- Also called from `stop_bots()` for the `abyss stop` command

### Conversation Collection

`_ensure_qmd_conversations_collection()` runs on startup after daemon is ready:
```
qmd collection add ~/.abyss/bots/ --name abyss-conversations --mask "**/conversation-*.md"
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


## Conversation Search (SQLite FTS5)

Cross-session keyword recall, exposed to Claude as the
`search_conversations` MCP tool. Markdown logs remain the source of
truth — the FTS5 index is a parallel, rebuildable cache.

### Storage layout

| Scope | Markdown source | FTS5 DB |
|---|---|---|
| Bot DM | `~/.abyss/bots/<name>/sessions/chat_*/conversation-YYMMDD.md` | `~/.abyss/bots/<name>/conversation.db` |
| Group | `~/.abyss/groups/<name>/conversation/YYMMDD.md` | `~/.abyss/groups/<name>/conversation.db` |

### Schema

```sql
CREATE VIRTUAL TABLE messages USING fts5(
    content,
    chat_id UNINDEXED,
    role UNINDEXED,
    ts UNINDEXED,
    date_key UNINDEXED,        -- 'YYYY-MM-DD' for cheap range filter
    tokenize='unicode61 remove_diacritics 2'
);
```

`schema_version` is a small companion table (`v1`). Tokenizer is
`unicode61` with `remove_diacritics 2` — handles Korean / English /
emoji at word-segment level (no morpheme analysis).

### Indexing trigger

- `session.log_conversation(...)` — appends each user / assistant message.
- `group.log_to_shared_conversation(...)` — appends each group sender's
  line.

Both call `conversation_index.append(...)` after the markdown write.
Failures here log a warning and never raise — markdown is canonical, so
an index miss is recoverable via `abyss reindex`.

`bot_manager._ensure_conversation_index(...)` runs `ensure_schema` for
the bot DB and every group the bot belongs to at startup.

### MCP server

`abyss.mcp_servers.conversation_search` is a stdio JSON-RPC server. One
tool: `search_conversations(query, since=, until=, chat_id=, role=,
limit=)`. Reads its DB path from the `ABYSS_CONVERSATION_DB` environment
variable.

`claude_runner._prepare_skill_config` writes per-session `.mcp.json`
that auto-injects this server with the bot's DB path. The bot
directory is resolved by `_resolve_bot_dir_from_working_directory()`,
which walks up the working directory's parents until it finds an entry
whose parent is named `bots` — so DM (`bots/<name>/sessions/chat_*`),
cron (`bots/<name>/cron_sessions/<job>`), and heartbeat
(`bots/<name>/heartbeat_sessions/`) flows all hit the same per-bot DB.
Tool name in Claude's view:
`mcp__conversation_search__search_conversations`.

`reindex_session_dir` and `reindex_group_dir` always wipe the index —
even when the source markdown directory is missing — so deleting
source content actually purges the DB instead of leaving stale rows
searchable.

### Auto-injection

Two layers:

1. **SKILL.md** — `compose_claude_md()` checks `is_fts5_available()`
   and appends `conversation_search/SKILL.md` from the built-in skills
   package, mirroring the QMD pattern.
2. **MCP server** — `_prepare_skill_config()` adds the server entry
   with substituted DB path.

Tests gate the auto-injection behind a pytest marker
(`@pytest.mark.enable_conversation_search`); the autouse fixture in
`tests/conftest.py` stubs `is_fts5_available` to `False` so legacy
tests do not need updates.

### Reindexing

```
abyss reindex --bot <name>
abyss reindex --group <name>
abyss reindex --all
```

Wipes the affected `conversation.db` and re-parses every markdown file
in the scope. Header formats:

- Session: `## user (YYYY-MM-DD HH:MM:SS UTC)\n\n{body}\n` then blank
  line before the next header.
- Group: `[HH:MM:SS] sender: content` (single line; date inferred from
  `YYMMDD.md` filename).

### Limits

- Keyword (BM25) only — no semantic / embedding search yet.
- No Korean morpheme analysis. Prefix queries hit, but suffix matches
  do not (e.g. `짬뽕집` does not match a search for `짬뽕`; `짬뽕`
  matches `짬뽕집`).
- Group conversations are indexed but the auto-injected MCP server
  currently exposes only the bot's own DB. Group-scope search via MCP
  is future work.


## LLM Backends

Per-bot LLM selection lives behind ``abyss.llm.LLMBackend``. Two
backends ship — Claude Code (full agent, default) and OpenRouter
(text-only chat against 200+ models). New backends drop in by
registering a class via ``abyss.llm.register``.

### Resolution

``abyss.llm.get_or_create(bot_name, bot_config)`` is the only public
entry point. It reads ``bot_config["backend"]["type"]`` (defaulting
to ``claude_code``), instantiates the registered backend class, and
caches it per bot. ``bot_config`` is refreshed in-place on cached
returns so model / skill / option changes take effect without restart;
a backend-type change recreates the instance.

### Claude Code backend

``ClaudeCodeBackend.run`` and ``.run_streaming`` are thin late-binding
wrappers around ``claude_runner.run_claude_with_sdk`` /
``run_claude_streaming_with_sdk``. All Claude Code features preserved:
built-in tools (Bash / Read / Write / Edit / Grep / Glob / Agent),
auto-injected MCP servers (QMD, conversation_search), skills, `--resume`
session continuity, SDK pool persistence.

``cancel(session_key)`` calls ``cancel_sdk_session`` then
``cancel_process``. ``close()`` is a no-op (process-wide lifecycle
managed by ``bot_manager.close_all`` / ``cancel_all_processes``).

### OpenRouter backend

``OpenRouterBackend`` POSTs to ``{base_url}/chat/completions``
(default ``https://openrouter.ai/api/v1``). The request body follows
OpenAI's chat completions schema:

* ``messages[0]`` is the bot's ``CLAUDE.md`` as a ``system`` message
  (falls back from the per-session copy to the bot-level copy).
* The next ``max_history`` entries are user / assistant turns parsed
  from the most recent ``conversation-YYMMDD.md`` files (newest first,
  reversed before sending).
* The current user prompt closes the list.

**User-message dedup.** abyss handlers call ``log_conversation``
*before* ``backend.run``, so the markdown log already contains the
current user message. ``_build_messages`` drops a trailing user turn
whose stripped content matches ``request.user_prompt`` so the model
never sees the same input twice (which would inflate token usage and
bias responses toward the repeated text). Older turns with different
content are preserved.

**``max_history`` precedence.** ``_resolve_max_history(request)``
returns:

1. ``request.max_history`` when the caller explicitly raised it above
   the dataclass default of 20 (lets cron / heartbeat widen the
   window for a one-off run).
2. Otherwise the bot-configured ``backend.max_history``.
3. Otherwise 0 (history disabled).

``_load_history`` loads ``cap + 1`` entries so dedup never trims
below the configured window; the final cap is enforced after dedup.

Streaming uses SSE (``stream=True`` with
``stream_options={"include_usage": true}``) and forwards each
``delta.content`` chunk to the caller's ``on_chunk`` callback.

API key is read from ``backend.api_key`` (set directly in bot.yaml). The
``Authorization`` header is sent alongside ``HTTP-Referer`` and
``X-Title`` headers (per OpenRouter's attribution guidelines).

Failure modes are mapped to ``RuntimeError`` with actionable text:

* 401 / 403 → "OpenRouter rejected the API key".
* 429 → "OpenRouter rate limit hit".
* 5xx → "OpenRouter upstream error" + first 300 chars of body.

``cancel(session_key)`` cancels the in-flight ``asyncio.Task``
registered for that key. ``close()`` calls ``httpx.AsyncClient.aclose``.

### Limits intentionally accepted

* OpenRouter has no tool-calling support in this backend. Bots with
  MCP / Bash / file tools should stay on Claude Code.
* No ``--resume``-style continuity. Long conversations rely on
  history replay; trim ``max_history`` for cost-sensitive bots.
* Subagent spawning is unavailable.
* Token compaction (``token_compact.py``) still uses the direct
  ``run_claude`` subprocess path because it's a system utility, not a
  bot turn.

## Voice Mode (Dashboard Chat STT/TTS)

### Overview

Mic button in the dashboard chat header triggers a full-duplex voice loop managed by `use-voice-mode.ts`:

```
recording → (ElevenLabs Scribe WebSocket) → transcript
  → handleSubmit(voice_mode=true)
  → SSE stream (bot reply)
  → TTS playback (ElevenLabs /speak)
  → back to recording
```

### State Machine

`VoiceState` = `idle | recording | processing | speaking`

`useVoiceMode` transitions:
- `idle` → `recording`: `start()` opens WebSocket, begins VAD capture
- `recording` → `processing`: final transcript received, sends to chat
- `processing` → `speaking`: SSE stream done, TTS begins
- `speaking` → `idle`: audio playback complete
- `idle` (after speaking) → `recording`: auto-restart via `useEffect` watching `voiceState` transition from `speaking` to `idle`

### STT — ElevenLabs Scribe v2 WebSocket

1. Frontend calls `GET /api/chat/scribe-token` → Next.js proxy → `chat_server.py` `/scribe-token` → ElevenLabs signed token API
2. `WebSocket` connects directly to `wss://api.elevenlabs.io/v1/speech-to-text/stream-input?model_id=scribe_v2&language_code=ko`
3. MediaRecorder captures audio in 250 ms slices; each slice sent as binary WebSocket frame
4. Server emits `{ type: "partial_transcript", text }` and `{ type: "final_transcript", text }` events
5. On final transcript: `onTranscript(text)` callback fires → `handleSubmit`

### voice_mode Flag Threading

```
VoiceMode.onTranscript
  → handleSubmit({ text, voiceMode: true })
  → useChatStream.send(bot, sessionId, text, [], voiceMode=true)
  → fetch /api/chat  body: { ..., voice_mode: true }
  → Next.js /api/chat proxy (pass-through)
  → chat_server.py _handle_chat
  → voice_mode = bool(body.get("voice_mode", False))
  → effective_message += "[응답 지침: 음성으로 전달됩니다. ...]"
  → chat_core.process_chat_message(effective_message)
```

Korean spoken-style instruction appended:
```python
"[응답 지침: 음성으로 전달됩니다. 자연스러운 구어체 한국어로 답변하세요. "
'"없음" → "없어요", 마크다운/불릿/이모지 없이 말하듯 짧고 자연스럽게.]'
```

### TTS — ElevenLabs Streaming

After SSE stream completes, `voice.speak(text)` is called:
1. `POST /api/chat/speak` with `{ text, bot, session_id }`
2. Next.js proxy → `chat_server.py` `/speak`
3. Server calls `ElevenLabs /v1/text-to-speech/{voice_id}/stream` with MP3 output
4. MP3 bytes piped back to browser
5. Frontend decodes with `AudioContext.decodeAudioData`, plays via `AudioBufferSourceNode`

Default voice: `ELEVENLABS_DEFAULT_VOICE_ID = "8jHHF8rMqMlg8if2mOUe"`. Override via `config.yaml` `elevenlabs_voice_id`.

### Shared aiohttp.ClientSession

`chat_server.py` creates one `aiohttp.ClientSession` in `start()`:
```python
self._http_session = aiohttp.ClientSession()
```
All three voice routes (`/transcribe`, `/speak`, `/scribe-token`) share this session. Closed in `stop()`.

**Test pattern**: `TestServer` does not call `start()`, so `_http_session` is `None`. Tests inject directly:
```python
server_instance._http_session = MagicMock()
server_instance._http_session.post = MagicMock(return_value=fake_cm)
```

### Orb Component

`VoiceScreen` uses `<Orb>` from `@11labs/react`:
- `agentState` maps: `recording→"listening"`, `processing→"thinking"`, `speaking→"talking"`, `idle→null`
- `colors: [string, string]` — primary and secondary shader colors
- Theme-aware via `useTheme` from `next-themes`:
  ```typescript
  const orbColors: [string, string] = resolvedTheme === "dark"
    ? ["#cccccc", "#ffffff"]
    : ["#111111", "#2a2a2a"];
  ```
- `resolvedTheme` used (not `theme`) to avoid SSR hydration mismatch

### UI Layout

Voice mode opens as a right sidebar (`w-72 shrink-0 border-l`) alongside the chat, not as a full-screen overlay. Chat messages remain visible during voice interaction. Header shows "Voice" label (not bot avatar). Messages show messenger-style timestamps (`toLocaleTimeString("ko-KR", { hour: "numeric", minute: "2-digit", hour12: true })`), hidden while streaming.
