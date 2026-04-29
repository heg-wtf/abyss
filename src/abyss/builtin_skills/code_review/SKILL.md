# code_review

Run a Claude Code `ultrareview` on a pull request or local target and summarize
findings back to the user. Use this when the user asks for a code review, asks
you to "ultrareview", drops a PR link, or otherwise wants a multi-aspect review
of code rather than a free-form chat about a diff.

## When to use

Trigger this skill when the message is clearly a review request:

- A GitHub / GitLab / Bitbucket PR URL.
- A bare PR number (e.g. `#123`).
- A local path (`src/auth/`) plus the word "review".
- An explicit `/review` or "review this" instruction.

Skip it for casual code questions ("what does this function do?"), small
code edits, or pure search tasks.

## How to invoke

Call the Claude Code `ultrareview` subcommand via Bash. It runs the same
parallel review pipeline used by the human-side `/ultrareview` slash
command and prints a structured JSON payload to stdout:

```bash
claude ultrareview <target> --json
```

`<target>` is whatever the user provided (PR URL, PR number, or local
path). The default review timeout is 30 minutes; ultrareview manages its
own progress, so do not wrap it in a shorter timeout.

If the review is exploratory, prefer `--json` so you can extract
findings programmatically. Drop `--json` only when the user explicitly
asks for prose.

## Effort

Match the review depth to the bot's session effort level: `${CLAUDE_EFFORT}`.
At `low` keep the summary tight (top 3 issues only). At `high` / `xhigh` /
`max`, walk through every finding with file path and one-line rationale.
At `medium`, group findings by category and surface the top 5.

## How to summarize

After ultrareview returns, write the user a short report:

1. Lead with the **headline severity** — block / fix-required / nitpick / lgtm.
2. List findings as bullet points: `path:line — one-line summary`.
3. End with a one-sentence recommendation (merge, request changes, needs
   discussion).

Keep the message under ~30 lines. If there are more findings than that,
say "+N more — paste again with `verbose:` for the full report" and
truncate.

## Failure modes

- `ultrareview` exits 1 → relay the stderr message to the user and stop.
  Do not retry without their say-so.
- Timeout (30 min) → tell the user the review didn't complete, suggest
  they re-run with a smaller scope.
- Target ambiguous (e.g. multiple PRs match a branch name) → ask the
  user to disambiguate before running.
