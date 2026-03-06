# QMD - Markdown Knowledge Search

Search your markdown knowledge bases, notes, documents, and past bot conversations using [QMD](https://github.com/tobi/qmd). All processing runs locally.

## Requirements

- [QMD](https://github.com/tobi/qmd): `npm install -g @tobilu/qmd`

## Installation

```bash
cclaw skills install qmd
cclaw skills setup qmd
```

Setup automatically registers your bot conversation logs as a searchable collection (`cclaw-conversations`).

## Adding Your Own Collections

Add any markdown directory to QMD:

```bash
# Personal notes
qmd collection add ~/Documents/notes --name my-notes --mask "**/*.md"

# Project documentation
qmd collection add ~/projects/myapp/docs --name myapp-docs --mask "**/*.md"

# Index and create embeddings
qmd update
qmd embed
```

List collections:

```bash
qmd collection list
```

## Attaching to a Bot

```
/skills attach qmd
```

Or via CLI:

```bash
cclaw bot edit <bot-name>
# Add "qmd" to the skills list
```

## Usage Examples

Once attached, the bot can search your knowledge:

- "내 노트에서 React hooks 관련 내용 찾아줘"
- "지난주에 날씨에 대해 물어봤던 거 뭐였지?"
- "예전에 얘기했던 서버 배포 관련 내용 찾아줘"

## Search Modes

| Mode | Speed | Best For |
|------|-------|----------|
| `search` | ~30ms | Exact keyword matching |
| `vector_search` | ~2s | Conceptual/semantic similarity |
| `deep_search` | ~10s | Best accuracy (query expansion + reranking) |

## Re-indexing

Conversations grow daily. Re-index periodically:

```bash
# Manual
qmd update && qmd embed

# Or set up a cron job via Telegram
/cron add every day at 4am run qmd update
```

## How It Works

- QMD runs as an HTTP daemon on port 8181 (started automatically with `cclaw start`)
- Claude Code connects to QMD via MCP HTTP transport
- Models are loaded once when the daemon starts, so searches are fast
- The daemon stops automatically with `cclaw stop`

## Troubleshooting

**QMD not found**
```bash
npm install -g @tobilu/qmd
```

**First run is slow**
QMD downloads ML models (~100MB) on first use. This is a one-time operation.

**No search results**
```bash
qmd status          # Check if collections exist and documents are indexed
qmd update          # Re-index
qmd embed           # Create vector embeddings (needed for vector_search/deep_search)
```

**Daemon not starting**
```bash
cclaw doctor        # Check QMD daemon status
qmd mcp --http      # Try starting manually to see errors
```
