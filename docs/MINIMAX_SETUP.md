# MiniMax Backend — Setup Guide

abyss supports MiniMax's chat completions API directly via the **OpenAI-compatible backend**
(`openai_compat`). This lets you use models like `minimax-text-01` without routing through
a third-party gateway.

Two endpoints are available:

| Provider key | Endpoint | Audience |
|---|---|---|
| `minimax` | `https://api.minimaxi.chat/v1` | International (outside China) |
| `minimax_china` | `https://api.minimax.chat/v1` | Users in China |

---

## When to choose MiniMax

| Use case | Recommendation |
|---|---|
| Already have a MiniMax subscription and want direct billing | **MiniMax direct** |
| Need access to MiniMax + 200 other models from one key | OpenRouter (see `OPENROUTER_SETUP.md`) |
| Agentic bot: tools, MCP, file editing, `--resume` | **Claude Code** (default) |
| Simple text chat, summarizer, persona bot | MiniMax or OpenRouter |

MiniMax bots via `openai_compat` **cannot**:
- Invoke MCP tools (skills with `mcp.json` are silent on this backend)
- Use Claude Code's built-in tools (Read, Write, Edit, Bash, Grep, Glob, Agent)
- Resume sessions via `--resume` — they replay `max_history` turns from conversation logs

---

## Step 1 — get an API key

1. Log in to the [MiniMax platform](https://platform.minimaxi.com) (international)
   or [minimax.chat](https://platform.minimax.chat) (China).
2. Go to **Account → API Keys → Create Key**.
3. Copy the key.

---

## Step 2 — configure `bot.yaml`

Edit `~/.abyss/bots/<your-bot>/bot.yaml` and add a `backend` block with `api_key` directly:

**International endpoint:**

```yaml
display_name: MiniMax Bot
personality: "You are a helpful assistant."
backend:
  type: openai_compat
  provider: minimax
  model: minimax-text-01
  api_key: your-minimax-api-key
  max_history: 20
  max_tokens: 4096
```

**China endpoint:**

```yaml
backend:
  type: openai_compat
  provider: minimax_china
  model: minimax-text-01
  api_key: your-minimax-api-key
```

**Custom endpoint override** (if MiniMax changes URLs):

```yaml
backend:
  type: openai_compat
  provider: minimax
  base_url: https://api.minimaxi.chat/v1
  model: minimax-text-01
  api_key: your-minimax-api-key
```

---

## Step 3 — send a message

No restart needed. The next message to the bot picks up the new config automatically.

If the key is wrong or expired, abyss replies with a clear error and logs the detail at
`~/.abyss/logs/`.

---

## Available options

| Key | Default | Description |
|---|---|---|
| `provider` | (none) | `minimax` or `minimax_china` — sets the endpoint |
| `api_key` | (required) | MiniMax API key, set directly in bot.yaml |
| `base_url` | from provider preset | Override the API endpoint URL |
| `model` | `anthropic/claude-haiku-4.5` | Model identifier |
| `max_history` | `20` | Number of past turns to replay from disk |
| `max_tokens` | `4096` | Maximum output tokens per response |

---

## Checking available models

MiniMax's model identifiers (e.g. `minimax-text-01`, `abab6.5s-chat`) can be found in the
[MiniMax platform documentation](https://platform.minimaxi.com/document/ChatCompletion%20v2).

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `api_key` error | Key missing in bot.yaml | Add `api_key: your-key` to the `backend` block |
| HTTP 401 / 403 | Wrong or expired key | Re-generate key on platform, update bot.yaml |
| HTTP 429 | Rate limit | Lower request frequency or upgrade plan |
| HTTP 500–503 | MiniMax upstream issue | Retry shortly |
| Empty response | Model returned no content | Check model name is valid |

---

## Relationship to OpenRouter

If you prefer a single API key that covers MiniMax *and* other providers, you can use
OpenRouter instead:

```yaml
backend:
  type: openai_compat
  provider: openrouter
  model: minimax/minimax-text-01
  api_key: your-openrouter-api-key
```

See `docs/OPENROUTER_SETUP.md` for OpenRouter setup instructions.
