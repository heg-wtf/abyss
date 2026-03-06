# cclaw (claude-claw)

<p align="center">
  <img src="cclaw-logo.png" width="160" alt="cclaw logo" />
</p>

Personal AI assistant powered by Telegram + Claude Code.
A multi-bot, file-based session system that runs locally on Mac.

## Table of Contents

- [Design Principles](#design-principles)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Skills](#skills)
- [Telegram Commands](#telegram-commands)
- [File Handling](#file-handling)
- [Tech Stack](#tech-stack)
- [CLI Commands](#cli-commands)
- [Project Structure](#project-structure)
- [Runtime Data](#runtime-data)
- [Testing](#testing)
- [License](#license)

## Design Principles

- **Local First**: No server required. Long Polling. No SSL or public IP needed.
- **File Based**: No database. Session = directory. Conversation = markdown.
- **Claude Code Delegation**: No direct LLM API calls. Runs `claude -p` as a subprocess.
- **CLI First**: Everything from onboarding to bot management is done in the terminal.

## Requirements

- Python >= 3.11
- Node.js (Claude Code runtime)
- [Claude Code CLI](https://www.npmjs.com/package/@anthropic-ai/claude-code)
- [uv](https://docs.astral.sh/uv/)

## Installation

### Quick Install (Recommended)

```bash
curl -sSL https://raw.githubusercontent.com/heg-wtf/cclaw/main/install.sh | bash
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
cclaw doctor                    # pip/pipx install
uv run cclaw doctor             # uv

# Initial setup (Telegram bot token required)
cclaw init

# Bot management
cclaw bot list
cclaw bot add
cclaw bot remove <name>

# Run bots
cclaw start              # Foreground
cclaw start --daemon     # Background (launchd)
cclaw stop               # Stop daemon
cclaw status             # Show running status
```

## Skills

cclaw has a **skill system** that extends your bot's capabilities with tools and knowledge. Skills are modular — attach or detach them per bot as needed.

- **Built-in skills**: Pre-packaged skill templates bundled with cclaw, installable with `cclaw skills install <name>`.
- **Custom skills**: User-created skills added via `cclaw skills add`. Can be markdown-only or tool-based (CLI, MCP, browser).

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

```bash
cclaw skills builtins          # List available built-in skills
cclaw skills install <name>    # Install a built-in skill
cclaw skills setup <name>      # Activate (check requirements)
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
| `/skills` | List all skills (installed + available builtins) |
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
| AI Bridge | Node.js + Claude Agent SDK (optional, Unix socket) |
| Logging | Rich (RichHandler, colorized console) |
| Process Manager | launchd (macOS) |

## CLI Commands

```bash
# Banner
cclaw                          # Show ASCII art banner

# Onboarding
cclaw init                     # Initial setup
cclaw doctor                   # Environment check

# Bot management
cclaw bot list                 # List bots (with model info)
cclaw bot add                  # Add a bot
cclaw bot remove <name>        # Remove a bot
cclaw bot edit <name>          # Edit bot.yaml
cclaw bot model <name>         # Show current model
cclaw bot model <name> opus    # Change model
cclaw bot streaming <name>     # Show streaming status
cclaw bot streaming <name> off # Toggle streaming on/off
cclaw bot compact <name>       # Compact MD files to save tokens
cclaw bot compact <name> -y    # Compact without confirmation

# Skill management
cclaw skills                   # List all skills (installed + available builtins)
cclaw skills add               # Create a skill interactively
cclaw skills remove <name>     # Remove a skill
cclaw skills setup <name>      # Setup skill (check requirements, activate)
cclaw skills test <name>       # Test skill requirements
cclaw skills edit <name>       # Edit SKILL.md ($EDITOR)
cclaw skills builtins          # List available built-in skills
cclaw skills install           # List available built-in skills
cclaw skills install <name>    # Install a built-in skill

# Cron job management
cclaw cron list <bot>          # List cron jobs
cclaw cron add <bot>           # Add a cron job interactively
cclaw cron remove <bot> <job>  # Remove a cron job
cclaw cron enable <bot> <job>  # Enable a cron job
cclaw cron disable <bot> <job> # Disable a cron job
cclaw cron run <bot> <job>     # Run a cron job immediately (test)

# Memory management
cclaw memory show <bot>        # Show memory contents
cclaw memory edit <bot>        # Edit MEMORY.md ($EDITOR)
cclaw memory clear <bot>       # Clear memory

# Global memory (shared across all bots, read-only for bots)
cclaw global-memory show       # Show global memory contents
cclaw global-memory edit       # Edit GLOBAL_MEMORY.md ($EDITOR)
cclaw global-memory clear      # Clear global memory

# Heartbeat management
cclaw heartbeat status         # Show heartbeat status for all bots
cclaw heartbeat enable <bot>   # Enable heartbeat
cclaw heartbeat disable <bot>  # Disable heartbeat
cclaw heartbeat run <bot>      # Run heartbeat immediately (test)
cclaw heartbeat edit <bot>     # Edit HEARTBEAT.md ($EDITOR)

# Run
cclaw start                    # Foreground
cclaw start --daemon           # Background (launchd)
cclaw stop                     # Stop daemon
cclaw status                   # Show status

# Logs
cclaw logs                     # Show today's log
cclaw logs -f                  # Tail mode
cclaw logs clean               # Delete logs older than 7 days
cclaw logs clean -d 30         # Keep last 30 days
cclaw logs clean --dry-run     # Preview without deleting

# Backup
cclaw backup                   # Backup ~/.cclaw/ to AES-256 encrypted zip
```

## Project Structure

```
cclaw/
├── pyproject.toml
├── bridge/
│   └── server.mjs          # Node.js bridge server (development source)
├── src/cclaw/
│   ├── cli.py              # Typer CLI entry point (ASCII art banner)
│   ├── config.py           # Configuration load/save
│   ├── onboarding.py       # Setup wizard
│   ├── claude_runner.py    # Claude Code runner (subprocess + bridge, batch + streaming)
│   ├── bridge.py           # Node.js bridge client (Unix socket, lifecycle management)
│   ├── bridge_data/        # Bridge server bundled with package (server.mjs, package.json)
│   ├── session.py          # Session directory management
│   ├── handlers.py         # Telegram handler factory
│   ├── bot_manager.py      # Multi-bot lifecycle
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
│   │   └── daiso/        # Daiso Mall skill (daiso-cli)
│   ├── backup.py            # Encrypted backup (AES-256 zip)
│   ├── token_compact.py    # Token compaction (compress MD files via Claude)
│   ├── cron.py             # Cron schedule automation (natural language parsing)
│   ├── heartbeat.py        # Heartbeat (periodic situation awareness)
│   └── utils.py            # Utilities
└── tests/
```

## Runtime Data

Configuration and session data are stored in `~/.cclaw/`. Override the path with the `CCLAW_HOME` environment variable.

```
~/.cclaw/
├── config.yaml
├── GLOBAL_MEMORY.md          # Global memory (shared across all bots, read-only)
├── bots/
│   └── <bot-name>/
│       ├── bot.yaml
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
├── bridge/
│   ├── server.mjs            # Bridge server (auto-copied from package data)
│   ├── package.json          # NPM package (@anthropic-ai/claude-agent-sdk)
│   └── node_modules/         # NPM dependencies (auto-installed)
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
