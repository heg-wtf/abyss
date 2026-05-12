# Skill Authoring Guide

abyss bundles only **universal** skills (email, calendar, OS integrations, generic utilities). Domain-specific and region-specific skills (local search APIs, country-specific data sources, etc.) are intentionally **not bundled** — you are expected to author your own or import from GitHub.

This guide explains how to write a skill, share it via GitHub, and import it back into abyss.

## Skill Directory Structure

Every skill lives under `~/.abyss/skills/<name>/` with this layout:

```
~/.abyss/skills/my-skill/
├── SKILL.md       # Required. Instructions injected into the bot's CLAUDE.md
├── skill.yaml     # Optional. Metadata: type, requirements, allowed tools, env vars
└── mcp.json       # Optional. MCP server configuration (for skills of type "mcp")
```

Only `SKILL.md` is mandatory. Everything else is opt-in.

### `SKILL.md`

Plain markdown. Whatever you write here becomes a section of the bot's system prompt at runtime via `compose_claude_md()`. Keep it focused — agents read every line.

Recommended structure:

```markdown
# my-skill

When to use this skill — describe the trigger conditions (user intent, keywords).

## Commands / Tools

Reference the CLI commands or MCP tools the skill exposes.

## Examples

Show 2-3 input → action examples so the agent can pattern-match.
```

### `skill.yaml`

Metadata read by `abyss skills` commands and `compose_claude_md()`. All fields are optional except `name`.

```yaml
name: my-skill                # Required. Must match the directory name
emoji: "🛠"                   # Optional. Shown in `abyss skills` listings
description: "What it does"   # Optional. Single line
type: cli                     # One of: cli, mcp, browser, knowledge
status: inactive              # inactive | active. Skill activation state

# CLI skills: tools / env vars the skill needs to function
required_commands:
  - my-cli
install_hints:
  my-cli: "Install via: pip install my-cli"
environment_variables:
  - MY_API_KEY

# Allowed tool patterns passed to Claude Code via --allowedTools
allowed_tools:
  - "Bash(my-cli:*)"
```

#### `type` values

| Type | When to use |
|------|------------|
| `cli` | The skill wraps a CLI tool (e.g. `naver-cli`, `dartcli`). Needs `required_commands` and usually `allowed_tools` |
| `mcp` | The skill is an MCP server. Requires a `mcp.json` file describing the server |
| `browser` | The skill uses Claude Code's built-in browser tool |
| `knowledge` | Pure markdown knowledge — no commands, no MCP. Just instructions/URLs |

### `mcp.json`

For `type: mcp` skills. Standard MCP server config; abyss merges this into the bot's MCP setup at runtime.

```json
{
  "mcpServers": {
    "my-server": {
      "command": "npx",
      "args": ["-y", "my-mcp-server"],
      "env": {
        "API_KEY": "${MY_API_KEY}"
      }
    }
  }
}
```

`${VAR}` placeholders are substituted from the skill's `environment_variables` values (entered during `abyss skills setup <name>`).

## Authoring Workflow

### Local-only (private skill)

```bash
abyss skills add               # Interactive prompt for name/type
# Edit ~/.abyss/skills/<name>/SKILL.md and skill.yaml directly
abyss skills setup <name>      # Check requirements, activate
```

Attach the skill to a bot via **Telegram** (`/skills attach <name>`), the **abysscope dashboard**, or by adding the skill name to the bot's `skills:` list in `bot.yaml`. There is no `abyss skills attach` CLI subcommand.

### Share via GitHub

Push your skill to a public repo. Two layouts work:

**Layout A: repo root contains the skill**

```
my-skill-repo/
├── SKILL.md
├── skill.yaml
└── mcp.json
```

Then anyone can import it:

```bash
abyss skills import https://github.com/<owner>/my-skill-repo
```

**Layout B: skill lives in a subdirectory** (handy for monorepos of multiple skills)

```
my-skills-repo/
├── skill-a/
│   ├── SKILL.md
│   └── skill.yaml
└── skill-b/
    ├── SKILL.md
    └── skill.yaml
```

Use a `tree/<branch>/<subdir>` URL:

```bash
abyss skills import https://github.com/<owner>/my-skills-repo/tree/main/skill-a
```

`abyss skills import` downloads `SKILL.md` (required) plus optional `skill.yaml` and `mcp.json`. The skill name defaults to the subdirectory name (or repo name when no subdir). Override with `--skill <name>`.

## Security: Trusted vs Untrusted Skills

Skills imported from GitHub are marked `untrusted: true` in their `skill.yaml`. abyss propagates this to Claude Code as `disableSkillShellExecution: true`, which **blocks inline shell execution from the skill markdown / custom commands** for the duration of any session that attaches an untrusted skill.

Skills authored locally (`abyss skills add` or hand-edited under `~/.abyss/skills/`) are trusted by default. Review imported skills before flipping `untrusted: false` manually.

## Listing & Removing

```bash
abyss skills                   # List installed skills (builtin + custom)
abyss skills builtins          # List bundled builtin templates
abyss skills remove <name>     # Delete from ~/.abyss/skills/
```

## Tips

- Keep `SKILL.md` short. Multi-page skills bloat every bot prompt that attaches them
- Pin required CLI versions in `install_hints` if behavior depends on them
- For MCP skills, test the server locally with `claude mcp` before publishing
- Avoid hardcoding region/locale defaults — let the user override via env vars or memory
