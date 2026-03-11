# ClawHouse: cclaw Web Dashboard

> Plan created: 2026-03-11
> Branch: `feature/clawhouse`

## Overview

ClawHouse is a web-based dashboard for managing `~/.cclaw/` configuration, bots, skills, cron jobs, sessions, and logs. Designed for **general users** who shouldn't need to open a terminal or text editor to manage their cclaw setup.

## Problem

Currently managing cclaw requires:
- Manually editing YAML files (`bot.yaml`, `config.yaml`, `cron.yaml`, `skill.yaml`)
- Terminal commands (`cclaw bot add`, `cclaw start`, `cclaw stop`)
- No visual overview of bot status, session activity, or cron schedules
- No way to browse conversation history or logs without CLI tools

## Solution

A local web dashboard served at `0.0.0.0:<port>` that provides:
- Visual overview of all bots and their status
- CRUD operations for bots, skills, and cron jobs
- Conversation history viewer
- Log viewer with search
- Memory editor (GLOBAL_MEMORY.md + per-bot MEMORY.md)

## Tech Stack

| Layer | Choice | Reason |
|-------|--------|--------|
| Runtime | Node.js (npx) | No Python dependency for dashboard |
| Framework | Next.js | SSR + API routes in one package |
| UI | shadcn/ui + Tailwind CSS | Modern, accessible, consistent |
| State | Server-side file reads | No database needed, reads ~/.cclaw directly |
| Package | npx-runnable | `npx clawhouse` or bundled with cclaw |

## ~/.cclaw Data Model

```
~/.cclaw/
├── config.yaml                    # Global: timezone, language, bot list, settings
├── GLOBAL_MEMORY.md               # Shared read-only memory for all bots
├── cclaw.pid                      # Process ID (running state)
│
├── bots/{name}/
│   ├── bot.yaml                   # Bot config (token, personality, skills, model, etc.)
│   ├── CLAUDE.md                  # Generated system prompt (read-only in dashboard)
│   ├── MEMORY.md                  # Bot long-term memory (editable)
│   ├── cron.yaml                  # Scheduled jobs (optional)
│   ├── sessions/chat_{id}/        # Per-chat session directories
│   │   ├── conversation-YYMMDD.md # Daily conversation logs
│   │   ├── workspace/             # User files (images, docs)
│   │   └── .claude_session_id     # Session continuity UUID
│   ├── cron_sessions/{job}/       # Cron job working directories
│   └── heartbeat_sessions/        # Heartbeat working directory
│
├── skills/{name}/
│   ├── SKILL.md                   # Skill instructions (editable)
│   ├── skill.yaml                 # Metadata, allowed_tools, env vars
│   └── mcp.json                   # MCP server config (optional)
│
├── bridge/                        # Node.js bridge (read-only)
└── logs/
    └── cclaw-YYMMDD.log           # Daily rotating logs
```

### Key Schemas

**config.yaml:**
- `bots[]`: `{ name, path }` — registered bot list
- `timezone`: string (e.g., `Asia/Seoul`)
- `language`: string (e.g., `Korean`)
- `settings.command_timeout`: int (seconds)
- `settings.log_level`: `DEBUG | INFO | WARNING | ERROR`

**bot.yaml:**
- `telegram_token`, `telegram_username`, `telegram_botname` — Telegram credentials
- `display_name` — Human-friendly name
- `personality`, `role`, `goal` — Character definition (multi-line strings)
- `model` — `opus | sonnet` (default: sonnet)
- `streaming` — `true | false` (default: false)
- `skills[]` — Linked skill names
- `allowed_users[]` — Telegram user ID whitelist
- `command_timeout` — Per-bot override (seconds)
- `heartbeat` — `{ enabled, interval_minutes, active_hours: { start, end } }`

**cron.yaml:**
- `jobs[]`: `{ name, enabled, schedule, message, timezone, model, skills[] }`

**skill.yaml:**
- `name`, `type` (`mcp | cli`), `status` (`active | inactive`)
- `description`, `emoji`
- `allowed_tools[]` — Tool patterns
- `environment_variables[]`, `environment_variable_values{}`
- `required_commands[]`, `install_hints{}`

## Current Bots (5)

| Bot | Display | Model | Skills | Cron | Heartbeat |
|-----|---------|-------|--------|------|-----------|
| cclaw0 | (none) | opus | imessage, reminders, naver-map, image | - | - |
| cclawlifebot | 앤 | sonnet | imessage, reminders, best-price, gmail, gcalendar, naver-search, kakao-local, daiso | 2 jobs | off |
| heg-staff | 킴 | opus | supabase, reminders, naver-search, mustgo-operation | - | off |
| cclawnotifybot | (none) | sonnet | clien | 2 jobs | off |
| cclawfinancebot | (none) | sonnet | dart | - | off |

## Current Skills (14)

| Skill | Type | Description |
|-------|------|-------------|
| supabase | mcp | Database, Storage, Edge Functions |
| mustgo-operation | mcp | Browser automation (OpenChrome) |
| naver-search | cli | Web search (local, book, blog, cafe, news, shopping) |
| dart | cli | Stock/financial disclosure search |
| naver-map | cli | Location mapping |
| imessage | cli | macOS iMessage/SMS |
| reminders | cli | Apple Reminders |
| gmail | cli | Email management |
| gcalendar | cli | Google Calendar |
| image | cli | Image processing |
| kakao-local | cli | Kakao local search |
| daiso | cli | Daiso product search |
| best-price | cli | Price comparison |
| clien | cli | Clien forum scraping |

## Pages & Features

### 1. Dashboard (Home) — `/`

Overview page showing:
- **Bot Cards**: Each bot as a card with display name, personality snippet, model badge, skill count, status indicator (running via cclaw.pid check)
- **Quick Stats**: Total bots, active skills, cron jobs today, last activity timestamp
- **System Status**: cclaw process running/stopped, bridge status, timezone/language

### 2. Bot Detail — `/bots/{name}`

**View Tab:**
- Full bot profile (personality, role, goal)
- Telegram info (username, bot name)
- Linked skills (clickable to skill detail)
- Model + streaming config
- Heartbeat config
- Recent conversations (last 5 days)

**Edit Tab:**
- Form for all bot.yaml fields
- Personality/role/goal as textarea
- Skills as multi-select (from available skills)
- Model as dropdown (opus/sonnet)
- Toggle switches for streaming, heartbeat enabled

**Memory Tab:**
- Markdown editor for MEMORY.md
- Preview panel

**Sessions Tab:**
- List of active sessions (chat IDs)
- Click to view conversation history
- Conversation viewer: rendered markdown with date navigation

### 3. Cron Jobs — `/bots/{name}/cron`

- Table of all cron jobs with: name, schedule (human-readable), message preview, timezone, enabled toggle
- Add/edit/delete jobs
- Cron expression builder (visual)
- Next execution time preview

### 4. Skills — `/skills`

**List View:**
- Card grid of all skills
- Type badge (MCP/CLI), status indicator, emoji
- Which bots use each skill

**Skill Detail — `/skills/{name}`:**
- Full description
- Allowed tools list
- Environment variables (values masked)
- Required commands + install status
- SKILL.md content viewer
- MCP config viewer (if applicable)

### 5. Settings — `/settings`

- Global config (timezone, language, log level, command timeout)
- Global memory editor (GLOBAL_MEMORY.md)
- Bot registration list management

### 6. Logs — `/logs`

- Date picker for log file selection
- Log viewer with:
  - Search/filter by bot name
  - Log level filter (INFO/WARNING/ERROR)
  - Auto-scroll to latest
  - Line highlighting

### 7. Conversations — `/conversations`

- Timeline view across all bots
- Filter by bot, date range
- Full conversation renderer (markdown → HTML)
- Workspace file browser (images, documents)

## API Routes

All API routes read/write directly to `~/.cclaw/` filesystem.

```
GET    /api/config                    # Read config.yaml
PUT    /api/config                    # Update config.yaml

GET    /api/bots                      # List all bots
GET    /api/bots/:name                # Read bot.yaml
PUT    /api/bots/:name                # Update bot.yaml
POST   /api/bots                      # Create new bot
DELETE /api/bots/:name                # Remove bot

GET    /api/bots/:name/memory         # Read MEMORY.md
PUT    /api/bots/:name/memory         # Write MEMORY.md

GET    /api/bots/:name/cron           # Read cron.yaml
PUT    /api/bots/:name/cron           # Update cron.yaml

GET    /api/bots/:name/sessions       # List sessions
GET    /api/bots/:name/sessions/:id/conversations  # List conversation files
GET    /api/bots/:name/sessions/:id/conversations/:date  # Read conversation

GET    /api/skills                    # List all skills
GET    /api/skills/:name              # Read skill detail

GET    /api/logs                      # List log files
GET    /api/logs/:date                # Read log file (with pagination)
GET    /api/logs/:date/search?q=      # Search within log

GET    /api/status                    # System status (pid, bridge, uptime)
GET    /api/global-memory             # Read GLOBAL_MEMORY.md
PUT    /api/global-memory             # Write GLOBAL_MEMORY.md
```

## Project Structure

```
clawhouse/
├── package.json
├── next.config.ts
├── tsconfig.json
├── postcss.config.mjs
│
├── src/
│   ├── app/
│   │   ├── layout.tsx              # Root layout (sidebar + theme)
│   │   ├── page.tsx                # Dashboard home (stats, disk usage, bot cards)
│   │   ├── globals.css             # Tailwind CSS
│   │   ├── favicon.ico             # cclaw logo favicon
│   │   ├── bots/
│   │   │   └── [name]/
│   │   │       ├── page.tsx        # Bot detail (tabs: profile, cron, sessions, memory)
│   │   │       ├── edit/
│   │   │       │   └── page.tsx    # Bot config editor
│   │   │       └── conversations/
│   │   │           └── [chatId]/
│   │   │               └── page.tsx  # Conversation viewer
│   │   ├── skills/
│   │   │   ├── page.tsx            # Redirect to /skills/builtin
│   │   │   ├── builtin/
│   │   │   │   └── page.tsx        # Built-in skills
│   │   │   └── custom/
│   │   │       └── page.tsx        # Custom skills
│   │   ├── settings/
│   │   │   └── page.tsx            # Global settings + memory editor
│   │   ├── logs/
│   │   │   └── page.tsx            # Log viewer with filter
│   │   └── api/                    # API routes (10 endpoints)
│   │       ├── bots/route.ts
│   │       ├── bots/[name]/route.ts
│   │       ├── bots/[name]/memory/route.ts
│   │       ├── bots/[name]/cron/route.ts
│   │       ├── bots/[name]/conversations/[chatId]/[date]/route.ts
│   │       ├── config/route.ts
│   │       ├── global-memory/route.ts
│   │       ├── logs/route.ts
│   │       ├── skills/route.ts
│   │       └── status/route.ts
│   │
│   ├── components/
│   │   ├── ui/                     # shadcn/ui (14 components)
│   │   ├── sidebar.tsx             # Collapsible nav (dynamic bot list)
│   │   ├── cron-editor.tsx         # Cron CRUD
│   │   ├── memory-editor.tsx       # Markdown editor
│   │   ├── settings-editor.tsx     # Config editor
│   │   ├── skill-card.tsx          # Skill display card
│   │   ├── live-status.tsx         # Polling status badge
│   │   ├── status-badge.tsx        # Static badges (model, type)
│   │   ├── theme-provider.tsx      # next-themes wrapper
│   │   └── theme-toggle.tsx        # Dark/light toggle
│   │
│   └── lib/
│       ├── cclaw.ts                # ~/.cclaw filesystem reader/writer
│       └── utils.ts                # Tailwind merge utility
│
└── public/
    └── logo.png                    # cclaw logo
```

## Implementation Phases

### Phase 1: Foundation (MVP)
- [x] Next.js project setup with shadcn/ui
- [x] ~/.cclaw filesystem reader library (`lib/cclaw.ts`)
- [x] Dashboard home with bot cards
- [x] Bot detail page (view only)
- [x] Settings page (view only)
- [x] System status indicator

### Phase 2: Read & Browse
- [x] Skill list and detail pages (Built-in / Custom split)
- [x] Cron job viewer (in bot detail tab)
- [x] Conversation history viewer (date picker, markdown render)
- [x] Log viewer with date picker and filter
- [x] Global memory viewer (in settings page)

### Phase 3: Edit & Manage
- [x] Bot config editor (bot.yaml)
- [x] Memory editor (MEMORY.md, GLOBAL_MEMORY.md)
- [x] Cron job CRUD (add/edit/remove/toggle)
- [x] Settings editor (config.yaml)
- [ ] Skill environment variable management

### Phase 4: Polish
- [x] Real-time status updates (10s polling)
- [ ] Responsive mobile layout
- [x] Dark/light theme (next-themes, system default)
- [x] Collapsible sidebar menus (Bots, Skills)
- [x] Dynamic bot list in sidebar
- [x] Disk usage display on dashboard
- [x] Custom favicon (cclaw logo)
- [ ] Search across conversations and logs
- [ ] Export/backup functionality

## Design Principles

1. **Read-first**: Dashboard is primarily for viewing. Edits are secondary and require confirmation
2. **No data loss**: All edits create backups before writing. YAML formatting preserved
3. **Transparent**: Show raw YAML/Markdown alongside the UI forms. Users can see exactly what changes
4. **Local-only**: Runs on localhost. No authentication needed (trusted local environment)
5. **Non-destructive**: Never delete bot data. "Remove" only unlinks from config.yaml

## Running

```bash
# Via cclaw CLI (recommended)
cclaw dashboard
cclaw dashboard --port 8080

# Or directly
cd clawhouse && npx next dev --port 3847
```

Port `3847` chosen as default (CLAW on phone keypad: C=2, L=5, A=2, W=9 → too long, just use 3847).

## Decisions

1. **Embedded in cclaw repo** — `clawhouse/` directory at project root. Easier context management
2. **`cclaw dashboard` command** — Added to CLI, spawns Next.js dev server
3. **Hot-reload** — Config edits take effect immediately (file watch or re-read on request)
4. **No authentication** — Local-only, trusted environment
5. **Bridge integration** — Deferred. Revisit later
