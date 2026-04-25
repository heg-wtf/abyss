# abyss

Personal AI assistant powered by Telegram + Claude Code.
A multi-bot, file-based session system that runs locally on Mac.

## Table of Contents

- [Design Principles](#design-principles)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Skills](#skills)
- [Group Collaboration](#group-collaboration)
- [Telegram Commands](#telegram-commands)
- [File Handling](#file-handling)
- [Tech Stack](#tech-stack)
- [CLI Commands](#cli-commands)
- [Project Structure](#project-structure)
- [Runtime Data](#runtime-data)
- [Abysscope Dashboard](#abysscope-dashboard)
- [Testing](#testing)
- [License](#license)

## Design Principles

- **Local First**: No server required. Long Polling. No SSL or public IP needed.
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
abyss bot add                  # Create a bot (Telegram token required)
abyss bot list
abyss bot remove <name>

# Run bots
abyss start              # Foreground
abyss start --daemon     # Background (launchd)
abyss stop               # Stop daemon
abyss status             # Show running status
```

## Skills

abyss has a **skill system** that extends your bot's capabilities with tools and knowledge. Skills are modular — attach or detach them per bot as needed.

- **Built-in skills**: Pre-packaged skill templates bundled with abyss, installable with `abyss skills install <name>`.
- **Custom skills**: User-created skills added via `abyss skills add`. Can be markdown-only or tool-based (CLI, MCP, browser).

### Built-in Skills

| Skill | Description | Guide |
|-------|-------------|-------|
| 💬 iMessage | Read and send iMessage/SMS via [imsg](https://github.com/steipete/imsg) CLI | [Guide](docs/skills/IMESSAGE.md) |
| ⏰ Apple Reminders | Manage macOS Reminders via [reminders-cli](https://github.com/keith/reminders-cli) | [Guide](docs/skills/REMINDERS.md) |
| 🗺 Naver Map | Generate Naver Map web links for search and navigation | [Guide](docs/skills/NAVER-MAP.md) |
| 🖼 Image Processing | Convert, optimize, resize, crop images via [slimg](https://github.com/clroot/slimg) CLI | [Guide](docs/skills/IMAGE.md) |
| 💰 Best Price | Search lowest prices across Danawa, Coupang, Naver Shopping | [Guide](docs/skills/BEST-PRICE.md) |
| 🗄 Supabase | Database, Storage, Edge Functions via Supabase MCP (no-deletion guardrails) | [Guide](docs/skills/SUPABASE.md) |
| 📧 Gmail | Search, read, send emails via [gogcli](https://github.com/steipete/gogcli) | [Guide](docs/skills/GMAIL.md) |
| 📅 Google Calendar | Events, scheduling, free/busy via [gogcli](https://github.com/steipete/gogcli) | [Guide](docs/skills/GCALENDAR.md) |
| 🐦 Twitter | Post tweets, search tweets via Twitter/X API MCP | [Guide](docs/skills/TWITTER.md) |
| 📋 Jira | Search, create, update, transition issues via Jira MCP | [Guide](docs/skills/JIRA.md) |
| 🔍 Naver Search | Search Naver (local, book, blog, cafe, news, shopping) via [naver-cli](https://github.com/heg-wtf/naver-cli) | [Guide](docs/skills/NAVER-SEARCH.md) |
| 📍 Kakao Local | Address/coordinate conversion, keyword place search via [kakao-cli](https://github.com/heg-wtf/kakao-cli) | [Guide](docs/skills/KAKAO-LOCAL.md) |
| 📈 DART | Query Korean corporate disclosure (DART OpenAPI) via [dartcli](https://github.com/seapy/dartcli) | [Guide](docs/skills/DART.md) |
| 🌐 Translate | Translate text and transcripts via [translatecli](https://github.com/seapy/translatecli) (Gemini-powered) | [Guide](docs/skills/TRANSLATE.md) |
| 🏪 Daiso | Search Daiso Mall products via [daiso-cli](https://github.com/heg-wtf/daiso-cli) | [Guide](docs/skills/DAISO.md) |
| 📚 QMD | Search markdown knowledge bases (BM25 + vector) via [QMD](https://github.com/tobi/qmd) MCP | [Guide](docs/skills/QMD.md) |
| 🧠 Conversation Search | Recall past bot conversations via SQLite FTS5 (auto-injected when FTS5 is available) | — |

```bash
abyss skills builtins          # List available built-in skills
abyss skills install <name>    # Install a built-in skill
abyss skills setup <name>      # Activate (check requirements)
```

## Group Collaboration

abyss supports **multi-bot collaboration** via Telegram groups. One orchestrator bot manages missions, delegating tasks to member bots via @mention.

### Setup

```bash
# 1. Create a group (orchestrator + members must be registered bots)
abyss group create dev_team --orchestrator dev_lead --members coder,tester

# 2. Add all bots to a Telegram group chat
# 3. Disable Group Privacy in BotFather for each bot
# 4. In the Telegram group, run:
/bind dev_team

# 5. Send a mission message in the group
```

### How It Works

- **Orchestrator**: Receives user messages, breaks missions into tasks, delegates via @mention
- **Members**: Execute delegated tasks, report results back via @mention to orchestrator
- **Shared conversation**: All messages logged to date-based conversation files
- **Shared workspace**: Persistent file workspace across all group members
- `/reset` in group: Orchestrator resets all bots' sessions + clears shared conversation (workspace preserved)
- `/cancel` in group: Orchestrator cancels all running processes

```bash
abyss group list                # List all groups
abyss group show dev_team       # Show group details
abyss group delete dev_team     # Delete a group
```

## Telegram Commands

| Command | Description |
|---------|-------------|
| `/start` | Bot introduction |
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
| `/cancel` | Stop running process (group: cancel all bots) |
| `/bind <group>` | Bind group to this chat |
| `/unbind` | Unbind group from this chat |
| `/version` | Version info |
| `/help` | Show commands |

## File Handling

Send photos or documents to the bot and they are automatically saved to the workspace and forwarded to Claude Code.
If a caption is included, it is used as the prompt.
Use the `/send` command to retrieve workspace files back via Telegram.

---

## Tech Stack

| Component | Choice |
|-----------|--------|
| Package Manager | uv |
| CLI | Typer + Rich |
| Telegram | python-telegram-bot v21+ |
| Configuration | PyYAML |
| Cron Scheduler | croniter |
| Encrypted Backup | pyzipper (AES-256) |
| AI Engine | Claude Code CLI (`claude -p`, streaming) |
| AI SDK | Python Agent SDK (`claude-agent-sdk`, persistent session pool) |
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

# Run
abyss start                    # Foreground
abyss start --daemon           # Background (launchd)
abyss stop                     # Stop daemon
abyss restart                  # Stop then start
abyss status                   # Show status

# Logs
abyss logs                     # Show today's log
abyss logs -f                  # Tail mode
abyss logs clean               # Delete logs older than 7 days
abyss logs clean -d 30         # Keep last 30 days
abyss logs clean --dry-run     # Preview without deleting

# Group management
abyss group create <name> -o <orchestrator> -m <members>  # Create group
abyss group list               # List all groups
abyss group show <name>        # Show group details
abyss group delete <name>      # Delete a group

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
│   ├── onboarding.py       # Setup wizard (init: timezone/language, bot add: Telegram + bot)
│   ├── claude_runner.py    # Claude Code runner (SDK pool + subprocess fallback)
│   ├── sdk_client.py       # Python Agent SDK client pool (persistent sessions)
│   ├── session.py          # Session directory management
│   ├── handlers.py         # Telegram handler factory (group-aware)
│   ├── group.py            # Group CRUD, shared conversation, workspace
│   ├── bot_manager.py      # Multi-bot lifecycle (regenerate CLAUDE.md on start)
│   ├── skill.py            # Skill management (create/attach/install/MCP/CLAUDE.md composition)
│   ├── builtin_skills/     # Built-in skill templates (imessage, reminders, ...)
│   │   ├── __init__.py     # Built-in skill registry
│   │   ├── imessage/       # iMessage skill (imsg CLI)
│   │   ├── reminders/      # Apple Reminders skill (reminders-cli)
│   │   ├── naver-map/      # Naver Map skill (web URL links)
│   │   ├── image/          # Image processing skill (slimg CLI)
│   │   ├── best-price/    # Best price search skill (knowledge)
│   │   ├── supabase/      # Supabase MCP skill (DB, Storage, Edge Functions)
│   │   ├── gmail/         # Gmail skill (gogcli)
│   │   ├── gcalendar/     # Google Calendar skill (gogcli)
│   │   ├── twitter/      # Twitter/X skill (MCP, tweet posting/search)
│   │   ├── jira/         # Jira skill (MCP, issue management)
│   │   ├── naver-search/ # Naver Search skill (naver-cli)
│   │   ├── kakao-local/  # Kakao Local skill (kakao-cli)
│   │   ├── dart/         # DART corporate disclosure skill (dartcli)
│   │   ├── translate/    # Translate skill (translatecli, Gemini)
│   │   ├── daiso/        # Daiso Mall skill (daiso-cli)
│   │   └── qmd/          # QMD knowledge search skill (MCP, HTTP daemon)
│   ├── backup.py            # Encrypted backup (AES-256 zip)
│   ├── token_compact.py    # Token compaction (compress MD files via Claude)
│   ├── cron.py             # Cron schedule automation (natural language parsing)
│   ├── heartbeat.py        # Heartbeat (periodic situation awareness)
│   └── utils.py            # Utilities
└── tests/
```

## Abysscope Dashboard

Abysscope is a web-based dashboard for managing `~/.abyss/` configuration, bots, skills, cron jobs, sessions, and logs. No terminal required.

```bash
abyss dashboard start              # Foreground (port 3847)
abyss dashboard start --daemon     # Background
abyss dashboard start --port 8080  # Custom port
abyss dashboard stop               # Stop
abyss dashboard restart             # Restart
abyss dashboard restart --daemon   # Restart as background
abyss dashboard status             # Show status

# Or directly
cd abysscope && npx next dev --port 3847
```

| Feature | Description |
|---------|-------------|
| Dashboard | Bot cards, quick stats, disk usage, system status |
| Bot Detail | Profile, cron editor (recurring/one-shot), session management (delete), memory editor (markdown view) |
| Bot Editor | Edit bot.yaml fields (model, skills, personality, heartbeat) |
| Skills | Built-in (read-only) / Custom (add, edit, delete), skill cards with usage info |
| Settings | Timezone/language Select dropdowns, Home directory with Finder open, global memory editor |
| Logs | Date picker, text filter, delete (single/bulk/by-age), daemon log truncate |
| Conversations | Per-chat conversation viewer with date navigation, individual file delete |

**Tech Stack**: Next.js 16 + shadcn/ui + Tailwind CSS + js-yaml. Reads `~/.abyss/` directly (no database).

See [docs/PLAN-26-0311-ABYSSCOPE.md](docs/PLAN-26-0311-ABYSSCOPE.md) for full plan.

## Runtime Data

Configuration and session data are stored in `~/.abyss/`. Override the path with the `ABYSS_HOME` environment variable.

```
~/.abyss/
├── config.yaml               # Global config (timezone, language, bot list, settings)
├── GLOBAL_MEMORY.md          # Global memory (shared across all bots, read-only)
├── bots/
│   └── <bot-name>/
│       ├── bot.yaml              # telegram_token, display_name, personality, role, goal, model, streaming, skills, heartbeat
│       ├── CLAUDE.md
│       ├── MEMORY.md             # Bot long-term memory (shared across all sessions)
│       ├── cron.yaml             # Cron job config (schedule, timezone, optional)
│       ├── cron_sessions/        # Cron job working directories
│       ├── heartbeat_sessions/   # Heartbeat working directory
│       │   ├── CLAUDE.md
│       │   ├── HEARTBEAT.md      # Checklist (user-editable)
│       │   └── workspace/
│       └── sessions/
│           └── chat_<id>/
│               ├── CLAUDE.md
│               ├── conversation-YYMMDD.md  # Daily conversation log (UTC date)
│               ├── .claude_session_id      # Claude Code session ID (for --resume)
│               └── workspace/
├── groups/
│   └── <group-name>/
│       ├── group.yaml            # Group config (orchestrator, members, chat_id)
│       ├── conversation/         # Shared conversation logs (YYMMDD.md)
│       └── workspace/            # Shared workspace (persistent across resets)
├── skills/
│   └── <skill-name>/
│       ├── SKILL.md          # Skill instructions (required)
│       ├── skill.yaml        # Skill config (tool-based skills: type, status, required_commands, install_hints)
│       └── mcp.json          # MCP server config (MCP skills only)
└── logs/
```

## Testing

```bash
uv run pytest                # Unit tests (mocked, fast)
uv run pytest -v             # Verbose

# Evaluation tests (real Claude API, excluded from CI)
uv run pytest tests/evaluation/ -v
```

## License

MIT
