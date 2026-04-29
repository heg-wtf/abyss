# Security Audit

Last audited: 2026-02-25

## Summary

Total issues found: 35 (Critical: 5, High: 4, Medium: 5, Low/Info: 21)

## Critical

### 1. Path Traversal in /send Command

- **File**: `src/abyss/handlers.py` (lines 217-226)
- **Status**: Open
- **Description**: The `/send` command constructs file paths using unsanitized user input. Sending `../../../etc/passwd` can access files outside the workspace directory.
- **Fix**: Validate with `file_path.resolve().relative_to(workspace.resolve())` and reject on `ValueError`.

### 2. Path Traversal in File Download

- **File**: `src/abyss/handlers.py` (lines 675-676)
- **Status**: Open
- **Description**: Files downloaded from Telegram are saved with the original filename from the sender. A filename like `../../exploit.sh` can write files outside the workspace.
- **Fix**: Sanitize filenames — strip path separators and `..`, or use a deterministic naming scheme like `file_{hash}{extension}`.

### 3. Telegram Token Stored in Plaintext

- **File**: `src/abyss/onboarding.py` (line 185), `src/abyss/config.py`
- **Status**: Open
- **Description**: Telegram bot tokens are saved directly to `bot.yaml` without encryption. If the home directory is compromised, tokens are immediately accessible.
- **Fix**: Use macOS Keychain via `keyring` library, or encrypt tokens at rest.

### 4. Cron Job Name Not Validated

- **File**: `src/abyss/cron.py` (line 95), `src/abyss/cli.py`
- **Status**: Open
- **Description**: Job name from user input is used directly in `cron_sessions/{job_name}/` directory creation. Path traversal sequences like `../` can escape the intended directory.
- **Fix**: Validate job name with `^[a-z0-9][a-z0-9_-]{0,63}$`.

### 5. Environment Variable Injection via Skills

- **File**: `src/abyss/claude_runner.py` (lines 168, 232-234)
- **Status**: Open
- **Description**: Skill environment variables are merged into `os.environ` without validation. Malicious skill configs could override critical system variables (e.g., `PATH`, `HOME`).
- **Fix**: Whitelist allowed environment variable prefixes per skill. Reject variables that override system-critical names.

## High

### 6. No Rate Limiting on Messages

- **File**: `src/abyss/handlers.py` (message_handler, file_handler)
- **Status**: Open
- **Description**: Users can send unlimited messages, each spawning a Claude subprocess. This can exhaust CPU, memory, and file handles.
- **Fix**: Implement per-user rate limiting (e.g., sliding window, max 1 message per 10 seconds).

### 7. Bot Name Validation Insufficient

- **File**: `src/abyss/onboarding.py` (lines 161-170)
- **Status**: Open
- **Description**: Bot name allows names starting with `.` (hidden directories) and has no length limit. Used directly in directory creation.
- **Fix**: Enforce `^[a-z0-9][a-z0-9-]{0,62}$`.

### 8. Absolute Path Exposed in CLAUDE.md

- **File**: `src/abyss/skill.py` (line 324)
- **Status**: Open
- **Description**: The absolute filesystem path to `MEMORY.md` is embedded in the generated CLAUDE.md system prompt. Reveals system directory structure.
- **Fix**: Use relative path or abstract description.

### 9. Message Content Logged

- **File**: `src/abyss/claude_runner.py` (line 176)
- **Status**: Open
- **Description**: User messages are logged (truncated to 100 chars). Could contain passwords, tokens, or PII.
- **Fix**: Log only metadata (message length, timestamp) instead of content.

## Medium

### 10. Conversation History Unlimited Growth

- **File**: `src/abyss/session.py`
- **Status**: Mitigated
- **Description**: `conversation.md` was appended indefinitely with no size limit. A user sending thousands of messages could exhaust disk space.
- **Mitigation**: Daily rotation to `conversation-YYMMDD.md` files limits per-file growth. Old files are not auto-deleted yet.
- **Remaining**: Auto-cleanup of old dated files (similar to `abyss logs clean`) is not yet implemented.

### 11. No Workspace Size Limit

- **File**: `src/abyss/session.py` (workspace directory)
- **Status**: Open
- **Description**: Workspace directories have no quota. Large file uploads can fill the disk.
- **Fix**: Check workspace size before download, enforce per-session quota (e.g., 100MB).

### 12. HEARTBEAT_OK Marker Spoofable

- **File**: `src/abyss/heartbeat.py` (line 228)
- **Status**: Open
- **Description**: Heartbeat response is checked with `HEARTBEAT_OK_MARKER in response`. If the LLM echoes user input containing "HEARTBEAT_OK", notifications are suppressed.
- **Fix**: Use structured response format or stricter pattern matching.

### 13. Error Messages Expose Internal Paths

- **File**: `src/abyss/handlers.py` (lines 221, 225, 628, 716)
- **Status**: Open
- **Description**: Error responses sent to Telegram users include internal paths and exception details.
- **Fix**: Send generic error messages to users, log full details internally.

### 14. No Timeout on File Download

- **File**: `src/abyss/handlers.py` (line 676)
- **Status**: Open
- **Description**: `file.download_to_drive()` has no explicit timeout. Slow or large downloads can hang the handler indefinitely.
- **Fix**: Wrap with `asyncio.wait_for(..., timeout=60)`.

## Low / Informational

### 15. Session ID Entropy

- **File**: `src/abyss/handlers.py` (line 508)
- **Description**: Uses `uuid.uuid4()` for session IDs. `secrets.token_urlsafe(32)` provides higher entropy.

### 16. No CSRF Protection for Destructive Commands

- **File**: `src/abyss/handlers.py`
- **Description**: `/resetall` deletes session without confirmation. Consider requiring `/resetall confirm`.

### 17. MCP Config Written in Plaintext

- **File**: `src/abyss/claude_runner.py` (lines 162-164)
- **Description**: `.mcp.json` with potential credentials is stored in plaintext in session directories.

### 18. Launchd Plist Embeds Current PATH

- **File**: `src/abyss/bot_manager.py` (lines 238, 254)
- **Description**: Full current `PATH` is copied into the launchd plist file.

### 19. No Audit Logging

- **File**: Various handlers
- **Description**: No structured audit log of user actions (who, what, when).

### 20. Exception Details Sent to Users

- **File**: `src/abyss/handlers.py` (lines 628, 716)
- **Description**: Full `str(error)` is sent in Telegram responses. Could leak internal details.

### 21. Subprocess Timeout Cleanup

- **File**: `src/abyss/claude_runner.py` (lines 191-193)
- **Description**: Timeout sends SIGKILL directly. Consider SIGTERM first with a grace period.

### 22. No Config Schema Validation

- **File**: Various YAML loaders
- **Description**: YAML files have no schema validation. Corrupted configs can cause crashes.

### 23. Skill Installation Integrity

- **File**: `src/abyss/skill.py` (lines 439-441)
- **Description**: Builtin skills are copied without checksum verification.

### 24-33. Additional Minor Items

- Chat ID not validated as positive integer (`session.py:17`)
- No HTTPS validation for MCP server URLs (`skill.py`)
- No file size check before Telegram download
- Hardcoded language strings (Korean only)
- `.gitignore` should cover `bot.yaml` and `.mcp.json`
- No workspace file type restrictions
- `collect_session_chat_ids` could return stale sessions
- Race condition between `lock.locked()` check and `async with lock` (`handlers.py:591`)
- Regex in `parse_one_shot_time` not anchored for multiline (`cron.py:161`)
- No max retry limit on `_call_with_resume_fallback` (`handlers.py`)

### 34. Group Mode Authorization Bypass for Bots

- **File**: `src/abyss/handlers.py` (message_handler)
- **Status**: By design
- **Description**: In group mode, bot senders (`is_bot == True`) skip `allowed_users` authorization. This enables orchestrator-to-member @mention delegation. A malicious bot added to the Telegram group (but not in the group config) could send messages that bypass authorization, though `_should_handle_group_message()` filters by role and only processes messages from known group members.
- **Mitigation**: Validate that the sending bot's username matches a known group member before skipping authorization.

### 35. Shared Conversation Log Accessible to All Group Members

- **File**: `src/abyss/group.py` (log_to_shared_conversation)
- **Status**: By design
- **Description**: All bots in a group read the full shared conversation log. A compromised member bot could exfiltrate conversation history from other members' delegated tasks.
- **Mitigation**: Accept as inherent to shared context model. Limit sensitive data to bot-specific memory (MEMORY.md) rather than group conversation.

### 36. Conversation Search Index Stores Plaintext

- **File**: `src/abyss/conversation_index.py`
- **Status**: Equivalent risk to existing markdown logs
- **Description**: `conversation.db` (SQLite FTS5) stores every user / assistant message in plaintext. Same exposure surface as `conversation-YYMMDD.md` files. Disk read by any process running as the user is sufficient to recover history.
- **Mitigation**: `backup.py` packages everything under `~/.abyss/` into an AES-256 zip — DB included. No additional protections at rest beyond that. Use OS-level full-disk encryption for stronger guarantees.

### 37. SQL Injection Surface in conversation_search

- **File**: `src/abyss/conversation_index.py` (`search`)
- **Status**: Mitigated
- **Description**: The `search_conversations` MCP tool accepts a free-form `query` string from Claude. The underlying `MATCH ?` query is fully parameterized; FTS5 rejects malformed expressions cleanly without leaking schema. Date / chat_id / role filters are bound parameters as well.
- **Verification**: `tests/test_conversation_index.py::test_search_query_with_sql_metacharacters_safe` confirms `' OR 1=1 --` and `'; DROP TABLE messages; --` are rejected without side effects.

### 38. OpenRouter API Key in Environment Variable

- **File**: `src/abyss/llm/openrouter.py` (`_auth_headers`)
- **Status**: Acceptable for personal use; document for users
- **Description**: The OpenRouter backend reads the API key from a process-level environment variable (default name `OPENROUTER_API_KEY`, overridable per-bot via `backend.api_key_env`). The key never lands in `bot.yaml`. Any process running as the same OS user can read the key via `/proc/<pid>/environ` or by attaching a debugger.
- **Mitigation**: documentation calls this out; users who need stronger protection should run abyss under a dedicated OS user, scope OpenRouter keys to specific models, or move to a secret manager (macOS Keychain integration is a follow-up). The key is never logged: errors mention only the env var name, not the value.

### 39. OpenRouter Sends Conversations to a Third Party

- **File**: `src/abyss/llm/openrouter.py`
- **Status**: By design; user-visible
- **Description**: When a bot's backend is `openrouter`, every user message — plus the system prompt (`CLAUDE.md`) and the last `max_history` turns from disk — is transmitted to OpenRouter and the underlying model provider. This is the same trust posture as Claude Code calling Anthropic, but the *set* of providers is broader (200+ third parties).
- **Mitigation**: opt-in per bot. Default backend (Claude Code) routes only to Anthropic. Onboarding flow surfaces the trade-off. Users handling sensitive data (PCI, PII, internal-only) should keep those bots on the default backend.

### 40. OpenRouter Output Echo (Markdown Injection)

- **File**: `src/abyss/handlers.py` (Telegram HTML conversion)
- **Status**: Equivalent risk to existing Claude responses
- **Description**: Model-generated text is rendered to Telegram via `markdown_to_telegram_html`, which escapes raw HTML before applying conversion. OpenRouter responses can contain adversarial markdown but the existing escape pipeline applies.
- **Mitigation**: re-using the same conversion path means no new code path to audit. Slack adapter (separate plan) will need its own escape policy when it lands.

## Phase 5 Hardening (2026-04-30)

abyss now plumbs two recent Claude Code settings into every bot session:

### `disableSkillShellExecution` (CC 2.1.91)

- **What**: top-level boolean in `<session>/.claude/settings.json` that blocks inline `!command` shell execution embedded in skill markdown / custom commands.
- **When abyss enables it**: any attached skill whose `skill.yaml` carries `untrusted: true`. `import_skill_from_github` automatically marks every imported skill untrusted (see `src/abyss/skill.py::is_untrusted_skill`).
- **Threat addressed**: a malicious or compromised third-party skill cannot leverage `!`-blocks to execute arbitrary shell commands as the bot host. Falls back to `false` for trusted (built-in / user-authored) skills so power-user workflows are unaffected.
- **Per-bot override**: explicit `bot.yaml.skills` curation. Removing the imported skill clears the flag.

### `sandbox.network.deniedDomains` (CC 2.1.113)

- **What**: an array of outbound-traffic blocklist entries (wildcards supported, e.g. `*.internal.example.com`) under `settings.json::sandbox.network.deniedDomains`.
- **abyss baseline** (`config.DEFAULT_SANDBOX_DENIED_DOMAINS`): cloud-metadata endpoints across the major providers — `metadata.google.internal`, `metadata.goog`, `169.254.169.254`, `instance-data`, `metadata.azure.com`, `metadata.tencentyun.com`, `metadata.ali`. These are the canonical SSRF targets for cloud-runner deployments.
- **Per-bot extras**: `bot.yaml.sandbox.denied_domains: ["sensitive.cloud.example.com"]`. Merged on top of the defaults; duplicates dropped.
- **Threat addressed**: SSRF via the model's `WebFetch` tool, opportunistic exfiltration of secrets via internal/private endpoints. The list takes precedence over `allowedDomains` in CC's evaluation order.

### Untrusted-skill provenance

- `import_skill_from_github` now writes both `untrusted: true` and a `source: {type: github, url: ...}` provenance block into the imported `skill.yaml`. The provenance is informational; the security gate is the boolean.

## Positive Findings

- All YAML loading uses `yaml.safe_load()` (no arbitrary code execution)
- Subprocess execution uses `create_subprocess_exec` (no `shell=True`)
- `allowed_users` permission check on all handlers (group mode: human users only, bots bypass by design)
- Process tracking with proper cleanup on shutdown (`cancel_all_processes`)
- Skill `allowed_tools` provides hard permission boundary in Claude Code `-p` mode
- GitHub-imported skills automatically run with `disableSkillShellExecution: true` (Phase 5)
- Cloud-metadata endpoints blocked by default via `sandbox.network.deniedDomains` (Phase 5)

## Remediation Priority

1. **Immediate**: Path traversal (#1, #2), name validation (#4, #7)
2. **Short-term**: Rate limiting (#6), environment variable validation (#5), error message sanitization (#13, #20)
3. **Medium-term**: Token encryption (#3), disk quota (#10, #11), download timeout (#14)
4. **Long-term**: Audit logging (#19), config validation (#22), i18n
