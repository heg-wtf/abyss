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

## Step 2 — export the key

```bash
export OPENROUTER_API_KEY=sk-or-v1-...
```

Add this to your shell profile (`~/.zshrc`, `~/.bashrc`) so abyss can read it on every start.

If you prefer a different env var name (e.g. one bot per workspace), just set both:

```bash
export OPENROUTER_PERSONAL_KEY=sk-or-v1-...   # for one bot
export OPENROUTER_WORK_KEY=sk-or-v1-...        # for another
```

You'll point each bot at the right name in step 3.

## Step 3 — create a bot with OpenRouter

```
abyss bot add
```

Fill in the Telegram token + profile, then:

```
Choose LLM backend.

  1. Claude Code (default — full agent: tools, MCP, skills, /resume)
  2. OpenRouter (text-only — cheap/fast chat across 200+ models)

Backend [1]: 2
```

The wizard asks for:

- **API key environment variable** (default `OPENROUTER_API_KEY`).
- **Model id** (default `anthropic/claude-haiku-4.5`). See <https://openrouter.ai/models> for the full list.
- **Max history turns** (default 20). Lower = cheaper / faster, less context. Higher = more cost / latency, better recall.

The bot's `bot.yaml` ends up with:

```yaml
backend:
  type: openrouter
  api_key_env: OPENROUTER_API_KEY
  model: anthropic/claude-haiku-4.5
  max_history: 20
```

You can edit `bot.yaml` directly to tune `max_tokens` (default 4096) or `base_url` (default OpenRouter endpoint; only override for self-hosted gateways).

> **Note:** `type: openrouter` is a legacy alias. New bots can use `type: openai_compat` with
> `provider: openrouter` — the behaviour is identical. The legacy type will continue to work
> indefinitely. See `docs/MINIMAX_SETUP.md` for the `openai_compat` approach with other providers.

### Notes on `max_history` and dedup

- `max_history` from `bot.yaml` is the source of truth for the per-bot context window. Raising or lowering it takes effect on the next message — no daemon restart required (the LLM backend cache refreshes config in place).
- abyss logs the user's incoming message to `conversation-YYMMDD.md` *before* calling the backend. The OpenRouter adapter knows this and drops a trailing duplicate so the model never sees the current user message twice. Older turns with different content stay in history untouched.
- A caller (cron / heartbeat / future plugin) can pass an explicit `request.max_history` larger than 20 to widen the window for a single run; this overrides the bot-level cap. Setting it to 0 disables history replay entirely.

## Step 4 — start the bot

```
abyss start --bot or-bot
```

abyss verifies the env var is set on startup and warns if it's missing.

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
| MCP server tool calling | ✅ | ❌ (1차 릴리즈) |
| Skills with `mcp.json` | Run | Markdown only — model sees instructions but cannot invoke |
| `--resume` session continuity | ✅ | ❌ — replay-based history |
| `/cancel` mid-stream | SDK interrupt + subprocess kill | Cancels HTTPX task |
| Subagent spawning | ✅ | ❌ |
| `conversation_search` (FTS5) | ✅ (auto-injected) | ❌ |
| Cost per response | Anthropic-only | 200+ models, often cheaper |
| Streaming | Per-token via SDK | Per-chunk via SSE |

## Troubleshooting

- **`OpenRouter backend requires environment variable 'OPENROUTER_API_KEY' to be set.`** — Export the key in the shell that starts abyss. Verify with `echo $OPENROUTER_API_KEY` before `abyss start`.
- **`OpenRouter rejected the API key`** — Key is invalid, expired, or revoked. Regenerate at <https://openrouter.ai/account/keys>.
- **`OpenRouter rate limit hit`** — Free tier has aggressive limits. Switch to a paid plan or pick a different model.
- **`OpenRouter upstream error (HTTP 502)`** — Provider behind OpenRouter is down. Retry after a few seconds or switch models temporarily.
- **Bot ignores tool requests** — Expected. Tools are unavailable on OpenRouter; route those bots through Claude Code instead.

## Cost monitoring

OpenRouter bills per-request. Check spend at <https://openrouter.ai/account/usage>. abyss does **not** track costs — set an OpenRouter spend cap in their dashboard if you're nervous.
