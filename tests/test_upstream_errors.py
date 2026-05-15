"""Tests for ``abyss.upstream_errors`` — classifier + sanitizer."""

from __future__ import annotations

from abyss.upstream_errors import UpstreamErrorMatch, classify, sanitize

# ---------------------------------------------------------------------------
# Fixtures — realistic samples taken from production logs.
# ---------------------------------------------------------------------------

_REAL_529 = (
    'API Error: 529 {"error":{"message":"{\\"type\\":\\"error\\",'
    '\\"error\\":{\\"type\\":\\"overloaded_error\\",'
    '\\"message\\":\\"Overloaded\\"},'
    '\\"request_id\\":\\"req_011Cb3RtVZBrZgTH4FQB7tct\\"}. '
    "Received Model Group=claude-sonnet-4-6\\n"
    'Available Model Group Fallbacks=None","type":"None","param":"None",'
    '"code":"529"}}'
)

_REAL_503 = (
    'API Error: 503 {"error":{"type":"service_unavailable_error",'
    '"message":"Service temporarily unavailable"},'
    '"request_id":"req_011Cabcdef"}'
)

_REAL_429 = (
    'API Error: 429 {"error":{"type":"rate_limit_error",'
    '"message":"Rate limit exceeded"},'
    '"request_id":"req_011Cratelimit"}'
)

_REAL_400 = (
    'API Error: 400 {"error":{"type":"invalid_request_error",'
    '"message":"Bad parameter"},'
    '"request_id":"req_011Cbadrequest"}'
)


# ---------------------------------------------------------------------------
# classify
# ---------------------------------------------------------------------------


def test_classify_529_overloaded() -> None:
    match = classify(_REAL_529)
    assert match is not None
    assert match.status == 529
    assert match.error_type == "overloaded_error"
    assert match.request_id == "req_011Cb3RtVZBrZgTH4FQB7tct"
    assert match.retryable is True
    assert match.kind == "overloaded"


def test_classify_503_service_unavailable() -> None:
    match = classify(_REAL_503)
    assert match is not None
    assert match.status == 503
    assert match.error_type == "service_unavailable_error"
    assert match.retryable is True
    assert match.kind == "gateway"


def test_classify_429_rate_limit_is_retryable() -> None:
    match = classify(_REAL_429)
    assert match is not None
    assert match.status == 429
    assert match.error_type == "rate_limit_error"
    assert match.retryable is True
    assert match.kind == "rate_limit"


def test_classify_400_not_retryable() -> None:
    match = classify(_REAL_400)
    assert match is not None
    assert match.status == 400
    assert match.error_type == "invalid_request_error"
    assert match.retryable is False
    assert match.kind == "generic_4xx"


def test_classify_returns_none_for_normal_response() -> None:
    assert classify("안녕하세요, 도와드릴게요.") is None
    assert classify("") is None
    assert classify("This is not an API Error response.") is None


def test_classify_api_error_without_json_payload() -> None:
    """Some Claude Code wrappers omit the trailing JSON entirely."""
    match = classify("API Error: 529 Overloaded")
    assert match is not None
    assert match.status == 529
    assert match.retryable is True
    # No JSON → no embedded request_id, falls back to generic label.
    assert match.request_id is None
    assert match.error_type == "unknown_error"


def test_classify_only_matches_leading_prefix() -> None:
    """A success reply quoting 'API Error: 500' in body should not match."""
    text = "참고로 어제 API Error: 500 발생 사례가 있었어요."
    assert classify(text) is None


def test_classify_is_case_insensitive_on_prefix() -> None:
    assert classify("api error: 503 ...") is not None


# ---------------------------------------------------------------------------
# sanitize
# ---------------------------------------------------------------------------


def test_sanitize_529_returns_overload_message_with_request_id() -> None:
    match = classify(_REAL_529)
    assert match is not None
    out = sanitize(match)
    assert "혼잡" in out
    trailer = "<!-- upstream error: HTTP 529 overloaded_error req=req_011Cb3RtVZBrZgTH4FQB7tct -->"
    assert trailer in out
    # Raw JSON must not leak through the user-visible portion.
    assert "overloaded_error" not in out.split("<!--")[0]


def test_sanitize_429_uses_rate_limit_specific_copy() -> None:
    match = classify(_REAL_429)
    assert match is not None
    out = sanitize(match)
    assert "한도" in out  # Korean rate-limit message mentions "한도"


def test_sanitize_falls_back_when_request_id_missing() -> None:
    match = UpstreamErrorMatch(
        status=529,
        error_type="overloaded_error",
        request_id=None,
        retryable=True,
    )
    out = sanitize(match)
    assert "req=unknown" in out


def test_sanitize_generic_5xx_when_status_only() -> None:
    match = UpstreamErrorMatch(
        status=500,
        error_type="unknown_error",
        request_id=None,
        retryable=True,
    )
    out = sanitize(match)
    assert "일시적인 문제" in out
    assert "HTTP 500" in out
