# Plan: Sanitize link URLs in markdown_to_telegram_html()

- date: 2026-05-01
- status: done
- author: claude
- approved-by: ash84

## 1. Purpose & Background

`src/abyss/utils.py:markdown_to_telegram_html()` converts model output Markdown to Telegram HTML and renders `[text](url)` as `<a href="{url}">{text}</a>`. The URL is interpolated **without** scheme validation and **without** HTML-escaping. Two XSS-style vectors exist:

1. **Dangerous scheme** — model output (potentially poisoned by prompt injection) emits `[click](javascript:alert(1))` or `[click](data:text/html,<script>...)`. Telegram clients usually strip these schemes, but defense-in-depth is required because:
   - Telegram client behavior is not contractually guaranteed.
   - Future channel adapters may render the same HTML differently.
   - `abysscope` Next.js dashboard renders conversation markdown; while `react-markdown` v10 defaults to a safe `urlTransform`, the abyss-side string is the canonical source and must not contain attack payloads.
2. **Attribute injection** — URL containing `"` breaks out of the `href` attribute: `[x](https://a.com" onerror="alert(1))` → `<a href="https://a.com" onerror="alert(1)">`. Currently mitigated only because the regex `\[([^\]]+)\]\(([^)]+)\)` stops at `)` — but `"` and other control chars pass through.

Reference: pi-mono PR [#3532](https://github.com/badlogic/pi-mono/issues/3532) and [#3819](https://github.com/badlogic/pi-mono/pull/3819) shipped the same fix in their HTML export path.

## 2. Expected Impact

- **Affected modules**: `src/abyss/utils.py` (single function).
- **User-visible change**: malicious or malformed URLs no longer render as clickable links — they fall back to plain text. Legitimate `http(s)://`, `tg://`, `mailto:` links continue to work.
- **Performance**: negligible. One additional regex match per link.
- **Backward compatibility**: any existing model output that depended on `javascript:` or `data:` URLs (none expected) loses the link rendering.

## 3. Implementation Approaches

### Option A — Scheme whitelist + URL escape (chosen)

- Allowed schemes (case-insensitive): `http`, `https`, `tg`, `mailto`.
- Reject everything else (`javascript`, `data`, `vbscript`, `file`, schemeless, etc.) → render as plain escaped text without `<a>`.
- HTML-escape the URL before interpolating into `href="..."` to neutralize quote-injection.
- Plus: Strip leading/trailing whitespace from URL.

**Pros**: Deterministic, easy to audit, covers both XSS vectors. Aligns with pi-mono fix.
**Cons**: Any non-listed scheme is dropped, even arguably-safe ones (`ftp`, `irc`).

### Option B — Use a third-party HTML sanitizer (e.g. `bleach`, `nh3`)

**Pros**: Battle-tested.
**Cons**: New dependency, runtime overhead, overkill for a regex-built HTML string. Function output is whitelisted Telegram HTML subset (`<b>`, `<i>`, `<code>`, `<pre>`, `<a>`) — nothing that needs full DOM sanitization.

### Decision: Option A

Single-file change, no new dependency, transparent behavior. If we later need broader sanitization (e.g. for arbitrary HTML), revisit.

## 4. Implementation Steps

- [x] Step 1: Add `_SAFE_URL_SCHEMES` constant + helper `_sanitize_link_url(url: str) -> str | None` in `utils.py`.
- [x] Step 2: Update `_replace_link` and the link restoration loop in `markdown_to_telegram_html()`:
  - Run `_sanitize_link_url()` on URL.
  - If `None` → emit plain escaped text (drop `<a>`).
  - If valid → `html.escape(url, quote=True)` and emit `<a href="...">`.
- [x] Step 3: Add `TestMarkdownToTelegramHtmlLinks` test class to `tests/test_utils.py`:
  - `test_https_link_rendered`
  - `test_http_link_rendered`
  - `test_mailto_link_rendered`
  - `test_tg_link_rendered`
  - `test_javascript_url_dropped` → no `<a` in output
  - `test_data_url_dropped`
  - `test_vbscript_url_dropped`
  - `test_relative_url_dropped` (no scheme)
  - `test_quote_injection_escaped` → `https://a.com" onerror="x` URL appears HTML-escaped, not as raw attribute
  - `test_uppercase_scheme_allowed` → `HTTPS://...` works
  - `test_whitespace_in_url_stripped`

## 5. Test Plan

**Unit tests** (in `tests/test_utils.py`):

- [x] Allowed schemes (http, https, mailto, tg) render as `<a href="...">`
- [x] Blocked schemes (javascript, data, vbscript, file, schemeless) render as plain text
- [x] HTML quote injection in URL is escaped
- [x] Case-insensitive scheme matching
- [x] Existing tests (bold/italic/code/heading) continue to pass

**Result**: 927 passed (whole suite) / 12 new link tests / lint + format clean.

**Integration tests**: not needed — function is pure string transform.

**Manual verification**: run `make test` and `make lint`.

## 6. Side Effects

- Any existing model output with non-whitelisted scheme links degrades to plain text. **No known production usage** of such links.
- `abysscope` dashboard (`memory-editor.tsx` uses `react-markdown` v10 with default `urlTransform`) is **already safe** — confirmed in audit. No change needed.
- No backward-compat shim required.
- No migration.

## 7. Security Review

- **OWASP A03 (Injection)**: this *is* the fix. Resolves stored XSS-style injection through LLM output.
- **A05 (Security Misconfig)**: defense-in-depth — does not rely on Telegram client behavior.
- **Auth/AuthZ**: no change.
- **Sensitive data**: no change.
- **PCI-DSS**: not applicable.

## 8. Plan Deviation Guard

If implementation reveals additional XSS surface in `markdown_to_telegram_html()` (e.g. unescaped attributes elsewhere), pause and update this plan.

## 9. Completion Criteria

- All 11 new tests pass
- Existing tests still pass
- `make lint && make test` green
- Side effects section confirmed "no impact"
- Plan status set to `done`
