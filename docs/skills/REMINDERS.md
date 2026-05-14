# Apple Reminders Skill Guide

A guide to installing and using the built-in Apple Reminders skill for abyss.

## Overview

The Reminders skill is a CLI-based skill that lets you manage macOS Reminders through your Telegram bot.
It uses the [keith/reminders-cli](https://github.com/keith/reminders-cli) CLI tool.

### Key Features

- View reminder lists
- Create reminders with due dates and priorities
- Complete or delete reminders
- View today's tasks and overdue items

## Prerequisites

### 1. Install reminders-cli

Install via Homebrew:

```bash
brew install keith/formulae/reminders-cli
```

Verify the installation:

```bash
reminders --help
```

The binary is installed at `/opt/homebrew/bin/reminders` (Apple Silicon) or `/usr/local/bin/reminders` (Intel).

### 2. macOS Reminders Permission (Important)

`reminders-cli` needs access to the macOS Reminders app. This is the most common setup issue.

#### The Problem

When you first run `reminders show-lists`, you may see:

```
error: you need to grant reminders access
```

Unlike most apps, `reminders-cli` may **not** trigger the macOS permission popup automatically. The Terminal app won't appear in **System Settings > Privacy & Security > Reminders** and there is no "+" button to add it manually.

#### The Solution

Use `osascript` to trigger the permission popup first:

```bash
osascript -e 'tell application "Reminders" to get name of every list'
```

This command will:
1. Trigger a macOS permission popup asking to allow Terminal access to Reminders
2. Click **Allow** in the popup
3. Terminal (or your terminal app) will now appear in the Reminders permission list

After allowing, verify that `reminders-cli` works:

```bash
reminders show-lists
```

#### If osascript Also Doesn't Trigger a Popup

Try resetting the TCC (Transparency, Consent, and Control) database:

```bash
tccutil reset Reminders
```

Then run the `osascript` command again:

```bash
osascript -e 'tell application "Reminders" to get name of every list'
```

#### Alternative: Full Disk Access

If the above methods fail, granting **Full Disk Access** to your terminal app is a fallback:

1. Open **System Settings** > **Privacy & Security** > **Full Disk Access**
2. Add your terminal app (Terminal.app, iTerm2, etc.) and enable it

Full Disk Access includes Reminders access.

> **Note**: When abyss runs as a daemon (default for `abyss start`), the shell used by `launchd` also needs permission.

## Installation & Setup

### 1. Install the Built-in Skill

```bash
abyss skills install reminders
```

This creates `SKILL.md` and `skill.yaml` in `~/.abyss/skills/reminders/`.

### 2. Setup (Activate)

```bash
abyss skills setup reminders
```

This checks if `reminders` is available in your PATH. If requirements are met, the skill status changes to `active`.

### 3. Attach the Skill to a Bot

Via Telegram:
```
/skills attach reminders
```

### 4. Verify

```bash
abyss skills
```

Expected output:
```
reminders (cli) <- my-bot
```

## Usage

After attaching the skill to a bot, send natural language requests via Telegram.

### View Reminder Lists

```
Show me my reminder lists
```

### View Today's Tasks

```
What do I need to do today?
```

### Create a Reminder

```
Add "Buy groceries" to my Shopping list for tomorrow
```

The bot will confirm the details before creating:

```
I'll create the following reminder:
- List: Shopping
- Title: Buy groceries
- Due: 2026-02-22

Shall I proceed?
```

Reply "Yes" to create.

### Complete a Reminder

```
Show me my tasks, then mark the first one as done
```

The bot will show the list first, ask for confirmation, then complete the item.

### View Overdue Items

```
Do I have any overdue reminders?
```

## How It Works

### allowed_tools

The `allowed_tools` configuration in skill.yaml:

```yaml
allowed_tools:
  - "Bash(reminders:*)"
```

This is passed to Claude Code via the `--allowedTools` flag, allowing `reminders` commands to run without permission prompts.

### SKILL.md Instructions

SKILL.md contains guidelines for Claude to follow:

- Check available lists with `show-lists` before operating
- Confirm with the user before creating, completing, or deleting reminders
- Use index numbers from `show` output for complete/delete operations

### Session Continuity

Session continuity enables multi-turn flows:

1. "Show me my tasks" -> Bot lists reminders with indices
2. "Complete number 3" -> Bot uses the context to complete the right item

## Troubleshooting

### "error: you need to grant reminders access"

The most common issue. See [macOS Reminders Permission](#2-macos-reminders-permission-important) above.

**Quick fix:**
```bash
osascript -e 'tell application "Reminders" to get name of every list'
# Allow in the popup -> then retry
reminders show-lists
```

### reminders command not found

```
abyss skills setup reminders
# Error: required command 'reminders' not found
```

**Solution**: Install via Homebrew:

```bash
brew install keith/formulae/reminders-cli
which reminders
# Should output: /opt/homebrew/bin/reminders
```

### Permission popup doesn't appear

**Solution**: Reset TCC and retry:

```bash
tccutil reset Reminders
osascript -e 'tell application "Reminders" to get name of every list'
```

If still no popup, use [Full Disk Access](#alternative-full-disk-access) as a fallback.

### Bot responds with "permission denied" or hangs

**Cause**: Claude Code requires user approval before running `reminders`, but the bot runs in a non-interactive environment.

**Solution**: Verify that `Bash(reminders:*)` is included in `allowed_tools` in skill.yaml.

```bash
cat ~/.abyss/skills/reminders/skill.yaml
```

If `allowed_tools` is present, re-activate with `abyss skills setup reminders`.

### Context lost (multi-turn failure)

"Show my tasks" -> "Complete number 2" flow fails because the bot loses context:

**Solution**: Run `/reset` and try again. Session continuity will activate automatically.
