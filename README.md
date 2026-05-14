<p align="center"><img src="docs/landing/logo-square.png" width="80" alt="abyss logo" /></p>

# abyss

Personal AI assistant powered by a PWA + Claude Code.
A multi-bot, file-based session system that runs locally on Mac and is
reached from the phone via a Tailscale-hosted dashboard.

> **v2026.05.14** — Telegram was retired. The mobile PWA + dashboard
> chat (built into `abysscope`) are now the only user-facing surfaces.
> Group collaboration (orchestrator + member) is gone with it and will
> return on top of the PWA in a later release.

## Table of Contents

- [Design Principles](#design-principles)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Skills](#skills)
- [LLM Backend](#llm-backend)
- [Memory & Recall](#memory--recall)
- [Slash Commands](#slash-commands)
- [File Handling](#file-handling)
- [Tech Stack](#tech-stack)
- [CLI Commands](#cli-commands)
- [Project Structure](#project-structure)
- [Runtime Data](#runtime-data)
- [Abysscope Dashboard](#abysscope-dashboard)
- [Testing](#testing)
- [License](#license)

## Design Principles

- **Local First**: No server required. Runs locally on Mac, reached over Tailscale. No SSL or public IP needed.
- **File Based**: No database. Session = directory. Conversation = markdown.
- **Claude Code Delegation**: No direct LLM API calls. Runs `claude -p` as a subprocess.
- **CLI First**: Everything from onboarding to bot management is done in the terminal.

## Requirements

- Python >= 3.11
- [Claude Code CLI](https://www.npmjs.com/package/@anthropic-ai/claude-code)
- [uv](https://docs.astral.sh/uv/)

## Installation

### Quick Install (Recommended)

```bash
curl -sSL https://raw.githubusercontent.com/heg-wtf/abyss/main/install.sh | bash
```

Auto-detects `uv` / `pipx` / `pip` and installs from GitHub.

### Manual Install

```bash
# uv
uv sync

# pip / pipx
pip install .
pipx install .
```

## Quick Start

```bash
# Check environment
abyss doctor                    # pip/pipx install
uv run abyss doctor             # uv

# Initial setup (environment check + timezone + language)
abyss init

# Bot management
abyss bot add                  # Create a bot
abyss bot list
abyss bot remove <name>

# Run abyss (API + dashboard + schedulers)
abyss start              # Foreground (default) — BuildProgress checklist visible
abyss start --daemon     # Background (launchd)
abyss start --port 8080  # Custom dashboard port (default 3847)
abyss stop               # Stop daemon + dashboard
abyss status             # Show running status
```

## Skills

abyss has a **skill system** that extends your bot's capabilities with tools and knowledge. Skills are modular — attach or detach them per bot as needed.

**Philosophy**: Built-in skills cover **universal tooling only** (email, calendar, OS integrations, generic utilities). Domain-specific and region-specific skills (local search APIs, country-specific data sources, etc.) are intentionally **not bundled** — author your own or import via [`abyss skills import <github-url>`](docs/SKILL_AUTHORING.md).

- **Built-in skills**: Pre-packaged universal skill templates bundled with abyss, installable with `abyss skills install <name>`.
- **Custom skills**: User-created skills added via `abyss skills add` or imported from GitHub via `abyss skills import <url>`. Can be markdown-only or tool-based (CLI, MCP, browser). See [Skill Authoring Guide](docs/SKILL_AUTHORING.md).

### Built-in Skills

| Skill | Description | Guide |
|-------|-------------|-------|
| 💬 iMessage | Read and send iMessage/SMS via [imsg](https://github.com/steipete/imsg) CLI | [Guide](docs/skills/IMESSAGE.md) |
| ⏰ Apple Reminders | Manage macOS Reminders via [reminders-cli](https://github.com/keith/reminders-cli) | [Guide](docs/skills/REMINDERS.md) |
| 🖼 Image Processing | Convert, optimize, resize, crop images via [slimg](https://github.com/clroot/slimg) CLI | [Guide](docs/skills/IMAGE.md) |
| 🗄 Supabase | Database, Storage, Edge Functions via Supabase MCP (no-deletion guardrails) | [Guide](docs/skills/SUPABASE.md) |
| 📧 Gmail | Search, read, send emails via [gogcli](https://github.com/steipete/gogcli) | [Guide](docs/skills/GMAIL.md) |
| 📅 Google Calendar | Events, scheduling, free/busy via [gogcli](https://github.com/steipete/gogcli) | [Guide](docs/skills/GCALENDAR.md) |
| 🐦 Twitter | Post tweets, search tweets via Twitter/X API MCP | [Guide](docs/skills/TWITTER.md) |
| 📋 Jira | Search, create, update, transition issues via Jira MCP | [Guide](docs/skills/JIRA.md) |
| 🌐 Translate | Translate text and transcripts via [translatecli](https://github.com/seapy/translatecli) (Gemini-powered) | [Guide](docs/skills/TRANSLATE.md) |
| 📚 QMD | Search markdown knowledge bases (BM25 + vector) via [QMD](https://github.com/tobi/qmd) MCP | [Guide](docs/skills/QMD.md) |
| 🧠 Conversation Search | Recall past bot conversations via SQLite FTS5 (auto-injected when FTS5 is available) | — |
| 🔎 Code Review | Run `claude ultrareview` on a PR or path and summarize findings | — |

```bash
abyss skills builtins          # List available built-in skills
abyss skills install <name>    # Install a built-in skill
abyss skills setup <name>      # Activate (check requirements)
abyss skills import <url>      # Import a custom skill from a GitHub repo
```

## LLM Backend

Every bot runs on **Claude Code** — the full agent surface: tools (Bash / Read / Write / Edit / Grep), MCP-backed skills, and `--resume`-based session continuity via the Python Agent SDK pool.

> v2026.05.15 dropped the OpenAI-compatible backends (`openai_compat` / `openrouter` / `minimax`). abyss is a Claude Code persona agent toolkit — the simpler surface is the point. The `LLMBackend` Protocol + registry stay in place so a future full-agent backend can be slotted in.

If your `bot.yaml` still has a `backend.type` set to one of the removed values, abyss will refuse to start that bot with a migration hint. Remove the `backend:` block (or set `backend.type: claude_code`) and the bot boots normally.

## Memory & Recall

abyss layers three memory surfaces on top of the per-session markdown logs:

- **`MEMORY.md`** — per-bot long-term notes the bot reads and writes. Injected into the system prompt.
- **`GLOBAL_MEMORY.md`** — read-only shared memory injected into every bot's system prompt. CLI-managed.
- **Conversation Search (SQLite FTS5)** — an auto-injected MCP tool (`search_conversations`) lets the bot recall specific past messages by keyword, even when they've rolled out of the context window. The index is built incrementally per message; markdown stays the source of truth, and `abyss reindex --bot|--group|--all` rebuilds it from scratch.

Conversation search is on by default whenever the bundled SQLite supports FTS5 (effectively always on macOS / Linux). Each bot has its own `~/.abyss/bots/<name>/conversation.db`; each group has `~/.abyss/groups/<name>/conversation.db`. `abyss doctor` reports FTS5 availability.

## Slash Commands

Slash commands are typed directly in the mobile PWA or dashboard chat.

| Command | Description |
|---------|-------------|
| `/reset` | Clear conversation (keep workspace) |
| `/resetall` | Delete entire session |
| `/files` | List workspace files |
| `/send <filename>` | Send workspace file |
| `/status` | Session status |
| `/model` | Show current model (with version) |
| `/model <name>` | Change model (sonnet/opus/haiku) |
| `/streaming` | Show streaming status |
| `/streaming on/off` | Toggle streaming mode |
| `/memory` | Show bot memory |
| `/memory clear` | Clear bot memory |
| `/skills` | Show bot's used, available, and not-installed skills |
| `/skills attach <name>` | Attach a skill |
| `/skills detach <name>` | Detach a skill |
| `/cron list` | List cron jobs |
| `/cron add <description>` | Add cron job via natural language (any language) |
| `/cron run <name>` | Run a cron job now |
| `/cron remove <name>` | Remove a cron job |
| `/cron enable <name>` | Enable a cron job |
| `/cron disable <name>` | Disable a cron job |
| `/heartbeat` | Heartbeat status |
| `/heartbeat on` | Enable heartbeat |
| `/heartbeat off` | Disable heartbeat |
| `/heartbeat run` | Run heartbeat now |
| `/compact` | Compact MD files to save tokens |
| `/cancel` | Stop running process |
| `/version` | Version info |
| `/help` | Show commands |

## File Handling

Send photos or documents via the mobile PWA or dashboard chat and they are automatically saved to the workspace and forwarded to Claude Code.
If a caption is included, it is used as the prompt.
Use the `/send` command to retrieve workspace files.

---

## Tech Stack

| Component | Choice |
|-----------|--------|
| Package Manager | uv |
| CLI | Typer + Rich |
| Chat / PWA | aiohttp HTTP+SSE (`abyss.chat_server`) reached over Tailscale |
| Configuration | PyYAML |
| Cron Scheduler | croniter |
| Encrypted Backup | pyzipper (AES-256) |
| LLM Backend | Claude Code CLI (`claude -p`, streaming) + Python Agent SDK persistent session pool — only registered backend |
| Conversation Index | SQLite FTS5 (stdlib, no extra dependency) |
| Logging | Rich (RichHandler, colorized console) |
| Process Manager | launchd (macOS) |

## CLI Commands

```bash
# Banner
abyss                          # Show ASCII art banner

# Onboarding
abyss init                     # Initial setup (environment check + timezone)
abyss doctor                   # Environment check (shows timezone)

# Bot management
abyss bot list                 # List bots (with model info)
abyss bot add                  # Add a bot
abyss bot remove <name>        # Remove a bot
abyss bot edit <name>          # Edit bot.yaml
abyss bot model <name>         # Show current model
abyss bot model <name> opus    # Change model
abyss bot streaming <name>     # Show streaming status
abyss bot streaming <name> off # Toggle streaming on/off
abyss bot compact <name>       # Compact MD files to save tokens
abyss bot compact <name> -y    # Compact without confirmation

# Skill management
abyss skills                   # List all skills (installed + available builtins)
abyss skills add               # Create a skill interactively
abyss skills remove <name>     # Remove a skill
abyss skills setup <name>      # Setup skill (check requirements, activate)
abyss skills test <name>       # Test skill requirements
abyss skills edit <name>       # Edit SKILL.md ($EDITOR)
abyss skills builtins          # List available built-in skills
abyss skills install           # List available built-in skills
abyss skills install <name>    # Install a built-in skill
abyss skills import <url>      # Import a skill from a GitHub repo

# Cron job management
abyss cron list <bot>          # List cron jobs
abyss cron add <bot>           # Add a cron job interactively
abyss cron remove <bot> <job>  # Remove a cron job
abyss cron enable <bot> <job>  # Enable a cron job
abyss cron disable <bot> <job> # Disable a cron job
abyss cron run <bot> <job>     # Run a cron job immediately (test)

# Memory management
abyss memory show <bot>        # Show memory contents
abyss memory edit <bot>        # Edit MEMORY.md ($EDITOR)
abyss memory clear <bot>       # Clear memory

# Global memory (shared across all bots, read-only for bots)
abyss global-memory show       # Show global memory contents
abyss global-memory edit       # Edit GLOBAL_MEMORY.md ($EDITOR)
abyss global-memory clear      # Clear global memory

# Heartbeat management
abyss heartbeat status         # Show heartbeat status for all bots
abyss heartbeat enable <bot>   # Enable heartbeat
abyss heartbeat disable <bot>  # Disable heartbeat
abyss heartbeat run <bot>      # Run heartbeat immediately (test)
abyss heartbeat edit <bot>     # Edit HEARTBEAT.md ($EDITOR)

# Run abyss
abyss start                    # Foreground (default) — boot checklist visible, Ctrl+C to stop
abyss start --daemon           # Background (launchd)
abyss start --port 8080        # Custom dashboard port (default 3847)
abyss stop                     # Stop daemon + dashboard
abyss restart                  # Stop then start
abyss status                   # Show status

# Logs
abyss logs                     # Show today's log
abyss logs -f                  # Tail mode
abyss logs clean               # Delete logs older than 7 days
abyss logs clean -d 30         # Keep last 30 days
abyss logs clean --dry-run     # Preview without deleting

# Backup
abyss backup                   # Backup ~/.abyss/ to AES-256 encrypted zip
```

## Project Structure

```
abyss/
├── pyproject.toml
├── abysscope/              # Abysscope web dashboard (Next.js)
├── src/abyss/
│   ├── cli.py              # Typer CLI entry point (ASCII art banner)
│   ├── config.py           # Configuration load/save, timezone/language management
│   ├── onboarding.py       # Setup wizard (init: timezone/language, bot add)
│   ├── claude_runner.py    # Claude Code runner (SDK pool + subprocess fallback)
│   ├── sdk_client.py       # Python Agent SDK client pool (persistent sessions)
│   ├── session.py          # Session directory management
│   ├── handlers.py         # Chat handler factory (slash commands, streaming, session continuity)
│   ├── group.py            # Group CRUD, shared conversation, workspace
│   ├── bot_manager.py      # Multi-bot lifecycle (regenerate CLAUDE.md on start)
│   ├── chat_core.py        # Backend-agnostic chat orchestration (PWA + dashboard)
│   ├── chat_server.py      # Internal aiohttp HTTP/SSE server for dashboard chat
│   ├── dashboard.py        # abysscope subprocess management (build / spawn / stop)
│   ├── dashboard_ui.py     # Rich checklist UI for `abyss start` boot sequence
│   ├── tool_metrics.py     # Per-bot tool call metrics (jsonl + p50/p95/p99)
│   ├── conversation_index.py # SQLite FTS5 index over conversation markdown
│   ├── llm/                # LLM backend layer (claude_code only post-v2026.05.15)
│   ├── mcp_servers/        # Bundled stdio MCP servers (conversation_search)
│   ├── hooks/              # Claude Code hooks (log_tool_metrics, precompact_hook)
│   ├── skill.py            # Skill management (create/attach/install/MCP/CLAUDE.md composition)
│   ├── builtin_skills/     # Built-in skill templates (universal only)
│   │   ├── __init__.py     # Built-in skill registry
│   │   ├── imessage/       # iMessage skill (imsg CLI)
│   │   ├── reminders/      # Apple Reminders skill (reminders-cli)
│   │   ├── image/          # Image processing skill (slimg CLI)
│   │   ├── supabase/       # Supabase MCP skill (DB, Storage, Edge Functions)
│   │   ├── gmail/          # Gmail skill (gogcli)
│   │   ├── gcalendar/      # Google Calendar skill (gogcli)
│   │   ├── twitter/        # Twitter/X skill (MCP, tweet posting/search)
│   │   ├── jira/           # Jira skill (MCP, issue management)
│   │   ├── translate/      # Translate skill (translatecli, Gemini)
│   │   ├── qmd/            # QMD knowledge search skill (MCP, HTTP daemon)
│   │   ├── conversation_search/ # Past conversation recall (FTS5 MCP, auto-injected)
│   │   └── code_review/    # `claude ultrareview` PR/path review
│   ├── backup.py            # Encrypted backup (AES-256 zip)
│   ├── token_compact.py    # Token compaction (compress MD files via Claude)
│   ├── cron.py             # Cron schedule automation (natural language parsing)
│   ├── heartbeat.py        # Heartbeat (periodic situation awareness)
│   └── utils.py            # Utilities
└── tests/
```

## Abysscope Dashboard

Abysscope is a web-based dashboard for managing `~/.abyss/` configuration, bots, skills, cron jobs, sessions, and logs. No terminal required. As of v2026.05.15 the dashboard boots automatically as part of `abyss start` — there is no separate `abyss dashboard` subcommand.

```bash
abyss start                        # Foreground (default) — boot checklist visible
abyss start --daemon               # Background (launchd)
abyss start --port 8080            # Custom dashboard port (default 3847)
abyss stop                         # Stop daemon + dashboard
abyss status                       # Show running state (API + dashboard URLs)

# Or directly
cd abysscope && npx next build && npx next start --port 3847
```

| Feature | Description |
|---------|-------------|
| Dashboard | Frequency heatmap (GitHub-style, all bots merged), disk usage breakdown, bot cards with profile photos, system status, abyss version |
| Bot Detail | Profile, cron editor (recurring/one-shot), session management (delete), memory editor (markdown view) |
| Bot Editor | Edit bot.yaml fields (model, skills, personality, heartbeat) |
| Skills | Built-in (read-only) / Custom (add, edit, delete), skill cards with usage info |
| Settings | Timezone/language Select dropdowns, Home directory with Finder open, global memory editor |
| Logs | Date picker, text filter, delete (single/bulk/by-age), daemon log truncate |
| Conversations | Per-chat conversation viewer with date navigation, individual file delete |
| Chat | In-browser chat with any bot — SDK session pool, SSE token streaming, image + PDF uploads |
| Voice Chat | Mic button opens voice sidebar with animated Orb — ElevenLabs Scribe v2 STT → bot reply → ElevenLabs TTS playback, auto-restart loop, theme-aware Orb colors |
| Tool Metrics | Per-bot tool call latency (p50/p95/p99) and counts from Claude Code `PostToolUse` hooks |

**Tech Stack**: Next.js 16 + shadcn/ui + Tailwind CSS + js-yaml. Reads `~/.abyss/` directly (no database). Chat / upload uses the internal aiohttp `ChatServer` started by `abyss start`.

### Mobile (`/mobile`)

A mobile-friendly route ships alongside the desktop UI at `http://<host>:3847/mobile`. It exposes the same chat backend with a phone-first layout: session list with custom names + long-press actions, single-chat screen with attachments, slash commands, and a workspace-files sheet. See [`docs/MOBILE_ACCESS.md`](docs/MOBILE_ACCESS.md) for the Tailscale + LAN access guide.

## Runtime Data

Configuration and session data are stored in `~/.abyss/`. Override the path with the `ABYSS_HOME` environment variable.

```
~/.abyss/
├── config.yaml               # Global config (timezone, language, bot list, settings)
├── GLOBAL_MEMORY.md          # Global memory (shared across all bots, read-only)
├── vapid-keys.json           # Web Push VAPID keypair (auto-generated on first PWA push)
├── abyss.pid                 # Bot manager PID (daemon mode)
├── abysscope.pid             # Dashboard PID + port (daemon mode)
├── bots/
│   └── <bot-name>/
│       ├── bot.yaml              # display_name, personality, role, goal, model, streaming, skills, heartbeat, backend
│       ├── CLAUDE.md             # Generated system prompt (do not edit manually)
│       ├── MEMORY.md             # Bot long-term memory (read/written by Claude)
│       ├── avatar.jpg            # Optional bot avatar (PWA + dashboard)
│       ├── conversation.db       # SQLite FTS5 index (auto-built from markdown)
│       ├── cron.yaml             # Cron job config (optional)
│       ├── cron_sessions/        # Per-job working directories
│       ├── heartbeat_sessions/   # Heartbeat working directory (HEARTBEAT.md + workspace/)
│       ├── tool_metrics/         # Daily jsonl of tool calls (PostToolUse hook)
│       └── sessions/
│           └── chat_<id>/
│               ├── CLAUDE.md
│               ├── conversation-YYMMDD.md  # Daily conversation log (UTC date)
│               ├── .claude_session_id      # Claude Code session ID (for --resume)
│               └── workspace/
├── skills/
│   └── <skill-name>/
│       ├── SKILL.md          # Skill instructions (required)
│       ├── skill.yaml        # Skill config (tool-based skills: type, status, required_commands, install_hints)
│       └── mcp.json          # MCP server config (MCP skills only)
└── logs/                     # Daily rotating logs
```

> Group surface (`groups/<name>/`) was removed in v2026.05.14 and is pending a redesign — see [ROADMAP.md](docs/ROADMAP.md). Existing directories under `~/.abyss/groups/` are inert.

## Testing

```bash
uv run pytest                # Unit tests (mocked, fast)
uv run pytest -v             # Verbose

# Evaluation tests (real Claude API, excluded from CI)
uv run pytest tests/evaluation/ -v
```

## License

MIT
