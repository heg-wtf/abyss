"""Classify and sanitize upstream Anthropic API errors.

When the Claude API returns a 5xx (commonly 529 ``overloaded_error``)
the Claude Code CLI surfaces the error as a regular assistant text
result, not as a non-zero exit. We detect that pattern here so
``chat_core`` can (a) retry on retryable statuses and (b) replace the
raw JSON with a friendly Korean message before the user ever sees it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

# Matches the very specific Claude Code CLI prefix
# ``API Error: <status> ...``. We only care about the leading status
# code; the rest may or may not be valid JSON (Claude's wrapper varies
# across versions / proxies).
_API_ERROR_PREFIX = re.compile(r"^\s*API Error:\s*(\d{3})\b", re.IGNORECASE)

# ``request_id`` field embedded anywhere in the payload. The Anthropic
# proxy sometimes nests a stringified JSON inside the outer message,
# so the quotes around the key/value may be backslash-escaped. Accept
# both forms with an optional ``\\?`` before each quote.
_REQUEST_ID = re.compile(r'\\?"request_id\\?"\s*:\s*\\?"(req_[a-zA-Z0-9]+)\\?"')

# ``"type":"<error_type>"`` — Anthropic sticks the semantic error type
# (``overloaded_error``, ``rate_limit_error``, ``invalid_request_error``,
# …) inside the nested error object. Match the *last* occurrence so the
# outer envelope ``"type":"error"`` doesn't win. Quotes may be escaped
# when the payload is wrapped in another JSON layer.
_ERROR_TYPE = re.compile(r'\\?"type\\?"\s*:\s*\\?"([a-z_]+_error)\\?"')

_RETRYABLE_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504, 522, 524, 529})

_MESSAGE_BY_KIND: dict[str, str] = {
    "overloaded": ("지금 모델 서버가 혼잡해서 응답을 받지 못했어요. 잠시 후 다시 보내주세요."),
    "rate_limit": ("요청이 너무 빨라 한도에 걸렸어요. 잠시 후 다시 시도해 주세요."),
    "gateway": ("서버와의 연결이 잠시 끊겼어요. 다시 시도해 주세요."),
    "generic_5xx": ("모델 서버에 일시적인 문제가 있어요. 잠시 후 다시 시도해 주세요."),
    "generic_4xx": ("요청 처리에 실패했어요. 잠시 후 다시 시도하거나 운영자에게 문의해 주세요."),
}


@dataclass(frozen=True)
class UpstreamErrorMatch:
    """Structured view of a detected upstream API error."""

    status: int
    error_type: str
    request_id: str | None
    retryable: bool

    @property
    def kind(self) -> str:
        """Short slug used to pick a user-facing message."""
        if self.error_type == "overloaded_error":
            return "overloaded"
        if self.error_type == "rate_limit_error":
            return "rate_limit"
        if self.status in {502, 503, 504, 522, 524}:
            return "gateway"
        if 500 <= self.status < 600:
            return "generic_5xx"
        return "generic_4xx"


def classify(text: str) -> UpstreamErrorMatch | None:
    """Detect an upstream API error in an assistant reply text.

    Returns ``None`` for any reply that doesn't start with the
    ``API Error: <status>`` prefix — so legitimate assistant prose
    that happens to mention "API Error" elsewhere is unaffected.
    """
    if not text:
        return None
    head = _API_ERROR_PREFIX.match(text)
    if not head:
        return None

    status = int(head.group(1))
    error_type = _extract_error_type(text)
    request_id = _extract_request_id(text)
    retryable = status in _RETRYABLE_STATUSES
    return UpstreamErrorMatch(
        status=status,
        error_type=error_type,
        request_id=request_id,
        retryable=retryable,
    )


def sanitize(match: UpstreamErrorMatch) -> str:
    """Render the user-facing message for a detected upstream error.

    The HTML comment trailer is invisible in rendered markdown but
    stays in the conversation log file so operators can grep for the
    Anthropic ``request_id``.
    """
    body = _MESSAGE_BY_KIND.get(match.kind, _MESSAGE_BY_KIND["generic_5xx"])
    request_part = match.request_id or "unknown"
    comment = f"<!-- upstream error: HTTP {match.status} {match.error_type} req={request_part} -->"
    return f"{body}\n\n{comment}"


def _extract_error_type(text: str) -> str:
    """Pull the most specific Anthropic error type from the payload."""
    matches = _ERROR_TYPE.findall(text)
    if matches:
        # Last match is the innermost (most specific) error type.
        return matches[-1]
    # The wrapper sometimes uses ``"type":"error"`` only; fall back to
    # a generic label so downstream code can still pick a message.
    return "unknown_error"


def _extract_request_id(text: str) -> str | None:
    match = _REQUEST_ID.search(text)
    if match:
        return match.group(1)
    # Some payloads embed the request id inside a stringified JSON
    # blob. Try once more after unescaping.
    try:
        unescaped = json.loads(f'"{text}"') if text.startswith('"') else None
    except json.JSONDecodeError, ValueError:
        unescaped = None
    if unescaped:
        match = _REQUEST_ID.search(unescaped)
        if match:
            return match.group(1)
    return None
