# OpenRouter Backend — Setup Guide

abyss bots default to the **Claude Code** backend (full agent: tools, MCP, skills, `--resume`). The **OpenRouter** backend is an opt-in alternative for **simple, fast, cheap text-only chat** against any of OpenRouter's 200+ models.

## When to choose OpenRouter

| Use case | Backend |
|---|---|
| Coding assistant, file editing, shell commands, MCP tools | **Claude Code** (default) |
| Q&A bot, summarizer, translator, simple persona chat | OpenRouter |
| Bot that should run cheaply at scale (haiku-class models, GPT-5-mini, DeepSeek, Qwen) | OpenRouter |
| Bot whose answer must include tool calls, file writes, or codebase navigation | **Claude Code** |

OpenRouter bots **cannot**:
- Invoke MCP tools (skills with `mcp.json` are silent on this backend)
- Use Claude Code's built-in tools (Read, Write, Edit, Bash, Grep, Glob, Agent)
- Resume sessions via `--resume` — they replay the last `max_history` turns from `conversation-YYMMDD.md` instead

## Step 1 — get an API key

1. Sign up at <https://openrouter.ai>.
2. Open your account → Keys → **Create Key**.
3. Copy the `sk-or-v1-…` key.

## Step 2 — configure `bot.yaml`

Edit `~/.abyss/bots/<your-bot>/bot.yaml` and add a `backend` block with `api_key` directly:

```yaml
backend:
  type: openai_compat
  provider: openrouter
  model: anthropic/claude-haiku-4.5
  api_key: sk-or-v1-...
  max_history: 20
  max_tokens: 4096
```

> **Legacy alias:** `type: openrouter` also works and is kept for backward compatibility.
> New bots should use `type: openai_compat` with `provider: openrouter`.

### Notes on `max_history` and dedup

- `max_history` from `bot.yaml` is the source of truth for the per-bot context window. Raising or lowering it takes effect on the next message — no restart required.
- abyss logs the user's incoming message to `conversation-YYMMDD.md` *before* calling the backend. The OpenRouter adapter drops a trailing duplicate so the model never sees the current user message twice.
- A caller (cron / heartbeat) can pass an explicit `request.max_history` larger than 20 to widen the window for a single run; this overrides the bot-level cap. Setting it to 0 disables history replay entirely.

## Step 3 — send a message

No restart needed. The next message to the bot picks up the new config automatically.

If the key is wrong or expired, abyss replies with a clear error and logs the detail at
`~/.abyss/logs/`.

## Available options

| Key | Default | Description |
|---|---|---|
| `provider` | (none) | `openrouter` — sets the endpoint |
| `api_key` | (required) | OpenRouter API key, set directly in bot.yaml |
| `base_url` | from provider preset | Override the API endpoint URL |
| `model` | `anthropic/claude-haiku-4.5` | Model identifier |
| `max_history` | `20` | Number of past turns to replay from disk |
| `max_tokens` | `4096` | Maximum output tokens per response |

## Recommended models (2026-04)

| Model id | Use case | Cost |
|---|---|---|
| `anthropic/claude-haiku-4.5` | General fast chat in Korean / English | ~$0.25/M in, $1.25/M out |
| `openai/gpt-5-mini` | Cheap reasoning, code completions | ~$0.15/M in, $0.60/M out |
| `anthropic/claude-sonnet-4.6` | Stronger reasoning, longer outputs | ~$3/M in, $15/M out |
| `deepseek/deepseek-v3` | Very cheap, decent code | ~$0.27/M in, $1.10/M out |
| `qwen/qwen-3-72b` | Multilingual, low cost | ~$0.20/M in, $0.40/M out |

Verify current pricing at <https://openrouter.ai/models> before relying on these numbers.

## Behavior differences vs Claude Code

| Capability | Claude Code | OpenRouter |
|---|---|---|
| Built-in tools (Bash / Read / Write / Edit / Grep / Glob / Agent) | ✅ | ❌ |
| MCP server tool calling | ✅ | ❌ |
| Skills with `mcp.json` | Run | Markdown only — model sees instructions but cannot invoke |
| `--resume` session continuity | ✅ | ❌ — replay-based history |
| `/cancel` mid-stream | SDK interrupt + subprocess kill | Cancels HTTPX task |
| Subagent spawning | ✅ | ❌ |
| `conversation_search` (FTS5) | ✅ (auto-injected) | ❌ |
| Cost per response | Anthropic-only | 200+ models, often cheaper |
| Streaming | Per-token via SDK | Per-chunk via SSE |

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `api_key` error | Key missing in bot.yaml | Add `api_key: sk-or-v1-...` to the `backend` block |
| HTTP 401 / 403 | Wrong or expired key | Re-generate key at openrouter.ai/account/keys, update bot.yaml |
| HTTP 429 | Rate limit | Free tier has aggressive limits; switch to paid plan or different model |
| HTTP 502 | Provider behind OpenRouter is down | Retry after a few seconds or switch models |
| Bot ignores tool requests | Expected | Tools unavailable on OpenRouter; use Claude Code backend instead |

## Cost monitoring

OpenRouter bills per-request. Check spend at <https://openrouter.ai/account/usage>. abyss does **not** track costs — set an OpenRouter spend cap in their dashboard if needed.
