# Changelog Analysis 2026-05-01

- date: 2026-05-01
- previous: first run
- abyss version: 2026.04.30

## Summary

- New items: 38 / Adopt: 14 / Review: 9 / Reference: 8 / Out of scope: 7
- First-run baseline. Subsequent runs only diff against new releases.

## Per-Source

### openclaw 2026.4.27 (2026-04-29) — [release](https://github.com/openclaw/openclaw/releases/tag/v2026.4.27)

- **Cron `--thread-id` for Telegram forum topics**: scheduled jobs deliver to a specific forum thread. ([release notes](https://github.com/openclaw/openclaw/releases/tag/v2026.4.27))
  - Bucket: 🟢 Adopt
  - abyss application: `src/abyss/cron.py` already stores per-job target chat; extend `cron.yaml` schema with optional `message_thread_id` and forward in `bot.send_message(...)` calls under `cron.py` + `handlers.py`. Tests in `tests/test_cron.py`.
  - Effort: S

- **Preserve session-derived Telegram topic thread IDs across cron deliveries**: keeps replies in the originating forum topic.
  - Bucket: 🟢 Adopt
  - abyss application: when cron job lacks explicit `message_thread_id`, fall back to thread captured during session bind (`group.py` already tracks chat binding — extend to capture `message_thread_id`).
  - Effort: S

- **Outbound proxy routing (`proxy.enabled` + `OPENCLAW_PROXY_URL`) with strict http:// validation, loopback bypass**.
  - Bucket: 🔵 Reference only
  - abyss application: abyss runs locally on user's Mac; proxy routing rarely needed. Note pattern if future enterprise deploy.
  - Effort: —

- **Sandbox Docker `--gpus` passthrough**.
  - Bucket: ⚪ Out of scope
  - abyss application: abyss has no Docker sandbox layer.

- **Auto-reply: stop bare `/reset` and `/new` after reset hooks acknowledge**: avoids empty provider call.
  - Bucket: 🟡 Review
  - abyss application: `handlers.py` `/reset` already short-circuits, but `/reset <message>` path replays user message — verify no empty model turn fires when user types only `/reset`. Audit `handlers.py:reset_command`.
  - Effort: S

- **Memory/compaction: keep pre-compaction memory-flush prompts runtime-only** (do not persist into transcript).
  - Bucket: 🟡 Review
  - abyss application: `src/abyss/token_compact.py` runs `claude -p` to compress MEMORY.md/SKILL.md/HEARTBEAT.md. Verify the compaction prompt itself is not appended to `conversation-YYMMDD.md`.
  - Effort: S

- **Cron tool: infer creating session's `agentId` for `cron.add` when omitted**.
  - Bucket: 🟢 Adopt
  - abyss application: when a bot creates a cron job mid-conversation via Claude tool call, default the owning bot/session. `cron.py` currently requires explicit bot context — relax for in-session adds.
  - Effort: M

- **DeepInfra bundled provider with discovery, media gen, embeddings**.
  - Bucket: ⚪ Out of scope (covered indirectly: `llm/openai_compat.py` already supports any OpenAI-compatible endpoint).

### hermes v0.11.0 (2026-04-23) — [release](https://github.com/NousResearch/hermes-agent/releases/tag/v2026.4.23)

- **`/steer <prompt>` mid-run agent nudges**: inject note that running agent sees after next tool call, no interrupt, no cache break. ([PR #12116](https://github.com/NousResearch/hermes-agent/pull/12116))
  - Bucket: 🟢 Adopt — high user value
  - abyss application: new `/steer` slash command in `src/abyss/handlers.py`. Append nudge to a queue file under `sessions/chat_<id>/.steer`. `claude_runner.py` / `sdk_client.py` watches for steer messages between tool calls and injects as user-role message via SDK `client.query()`. Requires SDK pool path (`sdk_client.SDKClientPool`).
  - Effort: M

- **Webhook direct-delivery mode**: webhook subscriptions forward to platform chat without going through agent (zero-LLM push).
  - Bucket: 🟢 Adopt
  - abyss application: new `src/abyss/webhook.py` HTTP endpoint (FastAPI/aiohttp) that accepts signed payloads and posts to a configured Telegram chat without spawning Claude. Useful for monitoring/uptime alerts piped into a bot. New CLI `abyss webhook add/list/remove`.
  - Effort: M

- **Auto-prune old sessions + VACUUM `state.db` at startup**.
  - Bucket: 🟢 Adopt
  - abyss application: `bot_manager.py` startup hook to enforce session retention. Already does logs cleanup — extend to `sessions/chat_*/` older than N days. Add `cleanup_period_days` to `config.yaml`. Run SQLite `VACUUM` on each `conversation.db`.
  - Effort: S

- **Per-provider + per-model `request_timeout_seconds`** + **configurable API retry count**.
  - Bucket: 🟢 Adopt
  - abyss application: `bot.yaml` `backend.timeout_seconds` and `backend.max_retries`. Wire through `llm/openai_compat.py` httpx client (`timeout=`) and `llm/claude_code.py` subprocess timeout. Add `backend.retry.max_retries`.
  - Effort: S

- **Auxiliary models — per-task overrides (compression, vision, search, title)**: route side-tasks to cheaper model.
  - Bucket: 🟢 Adopt
  - abyss application: `bot.yaml` `auxiliary_models: { compression: claude-haiku-4-5, title: claude-haiku-4-5 }`. `token_compact.py` and `cron.py` (parse natural-language schedule via haiku — already does this) read auxiliary mapping. Cost win for heavy users.
  - Effort: M

- **Compression summaries respect conversation language**.
  - Bucket: 🟡 Review
  - abyss application: `token_compact.py` should include `get_language()` from `config.py` in its compaction prompt. Verify current behavior — likely already inherits via CLAUDE.md but explicit check needed.
  - Effort: S

- **Orchestrator role + configurable `max_spawn_depth` + cross-agent file coordination for concurrent subagents**.
  - Bucket: 🟡 Review
  - abyss application: abyss has group orchestrator pattern (`group.py`). Adopting `max_spawn_depth` (depth-limit on orchestrator → orchestrator chains) is cheap and prevents runaway delegation. File coordination layer is heavier — defer.
  - Effort: S (depth limit only)

- **Compression smart collapse, dedup, anti-thrashing + auto-reset on exhaustion**.
  - Bucket: 🟡 Review
  - abyss application: abyss `token_compact.py` is one-shot. Add anti-thrashing guard: if compaction triggered N times within M minutes, force `/reset` instead of compacting again.
  - Effort: M

- **`ignored_threads` config for Telegram groups**.
  - Bucket: 🟢 Adopt
  - abyss application: `bot.yaml` `telegram.ignored_thread_ids: [...]` checked in `handlers.py` message handler. Useful for forum topics where bot should be silent.
  - Effort: S

- **Disable link previews config**.
  - Bucket: 🟢 Adopt
  - abyss application: `bot.yaml` `telegram.disable_link_preview: true`. Pass `disable_web_page_preview=True` in `bot.send_message` calls (already a python-telegram-bot kwarg).
  - Effort: S

- **Auto-continue interrupted agent work after gateway restart**.
  - Bucket: 🟡 Review
  - abyss application: abyss already saves session_id + uses `--resume`. Hermes adds explicit "this session was interrupted, please continue" injection. Could lift into `bot_manager.py` startup: detect sessions with active heartbeats but no recent assistant turn → seed continuation message.
  - Effort: M

- **Activity heartbeats prevent false gateway inactivity timeouts**.
  - Bucket: 🔵 Reference only
  - abyss application: abyss already has heartbeat module — different purpose (situation awareness). Hermes pattern is keepalive. Note for any future long-running streaming.

- **Transport ABC abstraction (Anthropic/ChatCompletions/Responses/Bedrock)**.
  - Bucket: 🔵 Reference only
  - abyss application: `llm/base.py` LLMBackend Protocol already plays this role. Hermes structure is more granular per-API-shape; reference for future Responses-API or Bedrock backend if needed.

- **Native AWS Bedrock / NVIDIA NIM / Arcee / Vercel ai-gateway providers**.
  - Bucket: ⚪ Out of scope (abyss targets Claude Code + OpenAI-compat; Bedrock could go through claude-code's Bedrock support).

- **Ink-based React TUI with sticky composer, OSC-52 clipboard, virtualized history**.
  - Bucket: ⚪ Out of scope (abyss is Telegram-driven; abysscope is Next.js dashboard, separate concern).

- **Honcho memory provider overhaul**.
  - Bucket: ⚪ Out of scope (abyss has its own MEMORY.md model).

- **Per-turn elapsed stopwatch + subagent spawn observability overlay**.
  - Bucket: 🔵 Reference only
  - abyss application: abysscope dashboard could show per-turn elapsed time on the conversation view.

### pi (Unreleased + 0.70.4–0.70.6, 2026-04-24 → 2026-04-28) — [CHANGELOG](https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/CHANGELOG.md)

- **Fix project context discovery to load `AGENTS.MD` files in addition to `AGENTS.md`** (case-insensitive).
  - Bucket: 🟢 Adopt (defensive)
  - abyss application: `compose_claude_md()` in `skill.py` reads various filenames. Verify case-insensitive match for any optional include files. Low priority but trivial.
  - Effort: S

- **Fix `/handoff` to use compacted session context instead of pre-compaction raw messages** ([#3945](https://github.com/badlogic/pi-mono/issues/3945)).
  - Bucket: 🟡 Review
  - abyss application: when abyss `/reset` is invoked, current behavior wipes session. If we ever add `/handoff` (carry context to new session), use post-compaction transcript.
  - Effort: M (only if /handoff added)

- **HTML export to sanitize markdown link URLs (block `javascript:` payloads)** ([#3532](https://github.com/badlogic/pi-mono/issues/3532)).
  - Bucket: 🟢 Adopt
  - abyss application: `utils.py` `markdown_to_telegram_html()` converts model output to Telegram HTML. Audit: does it allow `<a href="javascript:...">`? Telegram strips most schemes, but defense-in-depth — explicitly whitelist `http/https/tg/mailto`. Add test in `tests/test_utils.py`.
  - Effort: S — security sensitive, do this.

- **`pi update --self`, `pi.dev` update channel, `pi/<version>` user agent**.
  - Bucket: 🔵 Reference only
  - abyss application: abyss publishes via PyPI/wheel; no built-in self-update. Pattern for future.

- **Cloudflare Workers AI / Azure Cognitive Services / DeepSeek providers**.
  - Bucket: ⚪ Out of scope (covered by `llm/openai_compat.py`).

- **`ctx.ui.setWorkingVisible()` / `ctx.ui.getEditorComponent()` extension hooks**.
  - Bucket: ⚪ Out of scope (abyss has no in-process extension UI).

- **Searchable auth provider login (fuzzy)** + **OSC 9;4 terminal progress (opt-in)**.
  - Bucket: ⚪ Out of scope.

- **Anti-XSS HTML export sanitization on session metadata** ([#3819](https://github.com/badlogic/pi-mono/pull/3819)).
  - Bucket: 🟢 Adopt
  - abyss application: see above HTML sanitization audit. Same pass should cover any place abyss escapes session names/titles into HTML (abysscope dashboard markdown rendering — verify React `dangerouslySetInnerHTML` is not used or is sanitized).
  - Effort: S

### claude code 2.1.117 → 2.1.123 (2026-04 latest cuts) — [CHANGELOG](https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md)

- **Skills can reference `${CLAUDE_EFFORT}` env in content** (2.1.120).
  - Bucket: 🟢 Adopt
  - abyss application: abyss Phase 6 already wires `--effort` flag into `claude_runner.py`. Skills under `~/.abyss/skills/` can now branch on effort level. Update `docs/SKILLS.md` if it exists; otherwise add note to `skill.py` docstring.
  - Effort: S (documentation only — Claude Code does substitution itself)

- **`AI_AGENT` env var set for subprocesses so `gh` attributes traffic** (2.1.120).
  - Bucket: 🟢 Adopt
  - abyss application: `claude_runner.py` `_subprocess_env()` should set `AI_AGENT=abyss/<version>`. Helps `gh` and other tools that read this env. Wire in `claude_runner.py` env construction.
  - Effort: S

- **Hooks `PostToolUse` / `PostToolUseFailure` include `duration_ms`** (2.1.119).
  - Bucket: 🟢 Adopt
  - abyss application: abyss Phase 4 added `log_tool_metrics` hook. Extend `log_tool_metrics` reader (`tool_metrics.aggregate()`) to include duration percentiles. Update abysscope `getToolMetrics()` to surface mean/p95 duration.
  - Effort: S

- **`alwaysLoad` option in MCP server config** (2.1.121): tools skip tool-search deferral.
  - Bucket: 🟢 Adopt
  - abyss application: `skill.py` MCP injection (`compose_claude_md` MCP merge) for `mcp__conversation_search__search_conversations` should add `"alwaysLoad": true` so the bundled FTS5 search is not deferred. Verify schema accepted by current Claude Code version.
  - Effort: S

- **`--print` honors agent frontmatter `tools:` / `disallowedTools:`** (2.1.119).
  - Bucket: 🟡 Review
  - abyss application: abyss runs `claude -p` (print mode). If we ever ship agent definitions under `~/.claude/agents/`, frontmatter is now respected. Currently abyss uses skills + DEFAULT_ALLOWED_TOOLS. No action unless agents adopted.
  - Effort: —

- **Hooks invoke MCP tools directly via `type: "mcp_tool"`** (2.1.118).
  - Bucket: 🟢 Adopt
  - abyss application: abyss could replace shell-based hooks with direct MCP tool invocation in skill `hooks` declarations. Audit `~/.abyss/skills/*/skill.yaml` patterns; document new option.
  - Effort: S (documentation)

- **`cleanupPeriodDays` retention sweep covers `~/.claude/tasks/`, `~/.claude/shell-snapshots/`, `~/.claude/backups/`** (2.1.117).
  - Bucket: 🟢 Adopt
  - abyss application: aligned with hermes auto-prune above. abyss should provide unified retention for `bots/<name>/sessions/chat_*/`, `bots/<name>/cron_sessions/`, `bots/<name>/heartbeat_sessions/`. New CLI `abyss cleanup --age 30d`.
  - Effort: M

- **`/resume` accepts PR URL, finds session that created the PR** (2.1.122).
  - Bucket: 🔵 Reference only
  - abyss application: abyss is conversational, no PR-driven resume. UX inspiration only.

- **`ANTHROPIC_BEDROCK_SERVICE_TIER` env, `ANTHROPIC_DEFAULT_*_MODEL_NAME`/`_DESCRIPTION` overrides for custom gateway** (2.1.118, 2.1.122).
  - Bucket: ⚪ Out of scope.

- **`/usage` native dialog, theme system, `/cost`+`/stats` merged** (2.1.118).
  - Bucket: ⚪ Out of scope.

- **Subagent reconfiguration + SDK MCP server reconfig in parallel** (2.1.119).
  - Bucket: 🔵 Reference only
  - abyss application: abyss MCP injection currently sequential per skill. Parallelize MCP startup in `skill.py` if measured slow.

- **Many bug fixes around session resume, scrollback, MCP OAuth, file descriptors**.
  - Bucket: ⚪ Out of scope (most fixes apply to interactive Claude Code, abyss runs `-p`).

### codex CLI 0.122.0 → 0.125.0 (2026-04-20 → 2026-04-24) — [changelog](https://developers.openai.com/codex/changelog)

- **`/side` conversations** for quick questions inside an active session.
  - Bucket: 🟢 Adopt — UX win
  - abyss application: new `/side <question>` slash command in `handlers.py`. Spawns ephemeral Claude run with current session context but does not pollute conversation transcript or session_id. Returns answer inline. Useful for "quick lookup without breaking flow".
  - Effort: M

- **Plan Mode with fresh context and usage preview**.
  - Bucket: 🟡 Review
  - abyss application: abyss `/reset` already starts fresh. Plan-mode-style "preview tokens before run" could be added but low signal in Telegram UX.
  - Effort: —

- **Deny-read glob policies and isolated exec runs**.
  - Bucket: 🟢 Adopt
  - abyss application: extend `claude_runner.py` `DEFAULT_ALLOWED_TOOLS` rules with `deniedRead` glob list per bot (`bot.yaml` `permissions.denied_read_globs`). Maps to Claude Code permissions config. Already partially via Phase 5 `sandbox.deniedDomains`.
  - Effort: S

- **Hooks stable and configurable inline in `config.toml`**.
  - Bucket: 🔵 Reference only
  - abyss application: abyss uses skill.yaml hooks, equivalent pattern. Codex moves them inline into a single config — abyss prefers per-skill isolation; keep current.

- **Permission profiles persist across TUI sessions and shell escalation**.
  - Bucket: 🟡 Review
  - abyss application: abyss permissions are per-bot via `bot.yaml`. Already persistent. No action.
  - Effort: —

- **`codex exec --json` reports reasoning-token usage**.
  - Bucket: 🔵 Reference only
  - abyss application: abyss tool_metrics could capture reasoning tokens if Claude Code returns them in stream-json mode. Reference for future metrics expansion.

- **Multi-environment management in app-server sessions**, **Unix socket transport**, **Bedrock + AWS SigV4**, **Quick reasoning controls Alt+, / Alt+.**, **remote plugin marketplaces**, **`/mcp verbose`**.
  - Bucket: ⚪ Out of scope.

## Top 3 Adoption Priorities

1. **HTML link sanitization in `markdown_to_telegram_html()`** (`src/abyss/utils.py`) — security-sensitive, low effort. Blocks `javascript:` / `data:` URLs in model output before Telegram renders. Add tests in `tests/test_utils.py`. Source: pi #3532, #3819.
2. **`/steer` mid-run agent nudges** (`src/abyss/handlers.py` + `sdk_client.py`) — high user value for course-correcting long agent turns without `/cancel`. Requires SDK pool path. Source: hermes #12116.
3. **Auto-prune sessions + retention CLI (`abyss cleanup`)** (`src/abyss/bot_manager.py`, new `src/abyss/cleanup.py`) — operational hygiene; abyss accumulates `sessions/chat_*/` indefinitely. Source: hermes auto-prune + claude-code 2.1.117 `cleanupPeriodDays`.

## Next Actions

- [ ] Plan documents to draft:
  - `docs/plan-html-sanitize-2026-0501.md` (Top 1)
  - `docs/plan-steer-command-2026-0501.md` (Top 2)
  - `docs/plan-session-cleanup-2026-0501.md` (Top 3)
- [ ] Quick wins (no plan doc — direct PR each):
  - `AI_AGENT` env in subprocess (`claude_runner.py`)
  - `alwaysLoad: true` for `mcp__conversation_search` in `skill.py` MCP merge
  - `disable_link_preview` in `bot.yaml` + `bot.send_message` calls
  - `ignored_thread_ids` in `bot.yaml` + handler check
  - Telegram cron `--thread-id` support in `cron.py`
- [ ] Further investigation:
  - Auxiliary models (cheap haiku for compaction) — cost/quality tradeoff measurement before adopting
  - Anti-thrashing compaction guard — measure how often token_compact runs in a row in practice
  - Webhook direct-delivery — define use case (uptime monitor? Slack→Telegram bridge?) before building
