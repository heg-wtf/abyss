"""Tests for abyss.utils module."""

from __future__ import annotations

from unittest.mock import patch

from abyss.utils import (
    markdown_to_telegram_html,
    prompt_input,
    prompt_multiline,
    split_message,
)


class TestPromptInput:
    """Tests for prompt_input function."""

    @patch("builtins.input", return_value="hello world")
    def test_prompt_input_basic(self, mock_input: object) -> None:
        result = prompt_input("Enter value:")
        assert result == "hello world"

    @patch("builtins.input", return_value="  spaced  ")
    def test_prompt_input_strips_whitespace(self, mock_input: object) -> None:
        result = prompt_input("Enter value:")
        assert result == "spaced"

    @patch("builtins.input", return_value="custom value")
    def test_prompt_input_with_default_uses_input(self, mock_input: object) -> None:
        result = prompt_input("Enter value:", default="fallback")
        assert result == "custom value"

    @patch("builtins.input", return_value="")
    def test_prompt_input_with_default_uses_default_on_empty(self, mock_input: object) -> None:
        result = prompt_input("Enter value:", default="fallback")
        assert result == "fallback"

    @patch("builtins.input", return_value="   ")
    def test_prompt_input_with_default_uses_default_on_whitespace(self, mock_input: object) -> None:
        result = prompt_input("Enter value:", default="fallback")
        assert result == "fallback"


class TestPromptMultiline:
    """Tests for prompt_multiline function."""

    @patch("builtins.input", side_effect=["line one", "line two", ""])
    def test_prompt_multiline_basic(self, mock_input: object) -> None:
        result = prompt_multiline("Enter text:")
        assert result == "line one\nline two"

    @patch("builtins.input", side_effect=[""])
    def test_prompt_multiline_empty(self, mock_input: object) -> None:
        result = prompt_multiline("Enter text:")
        assert result == ""

    @patch("builtins.input", side_effect=["single line", ""])
    def test_prompt_multiline_single_line(self, mock_input: object) -> None:
        result = prompt_multiline("Enter text:")
        assert result == "single line"


class TestSplitMessage:
    """Tests for split_message function."""

    def test_short_message(self) -> None:
        result = split_message("hello")
        assert result == ["hello"]

    def test_split_at_newline(self) -> None:
        text = "a" * 4000 + "\n" + "b" * 1000
        result = split_message(text, limit=4096)
        assert len(result) == 2


class TestMarkdownToTelegramHtml:
    """Tests for markdown_to_telegram_html function."""

    def test_bold(self) -> None:
        result = markdown_to_telegram_html("**bold text**")
        assert "<b>bold text</b>" in result

    def test_italic(self) -> None:
        result = markdown_to_telegram_html("*italic text*")
        assert "<i>italic text</i>" in result

    def test_inline_code(self) -> None:
        result = markdown_to_telegram_html("`code`")
        assert "<code>code</code>" in result

    def test_heading(self) -> None:
        result = markdown_to_telegram_html("## Heading")
        assert "<b>Heading</b>" in result


class TestMarkdownToTelegramHtmlLinks:
    """Tests for link-URL sanitization in markdown_to_telegram_html."""

    def test_https_link_rendered(self) -> None:
        result = markdown_to_telegram_html("[ok](https://example.com)")
        assert '<a href="https://example.com">ok</a>' in result

    def test_http_link_rendered(self) -> None:
        result = markdown_to_telegram_html("[ok](http://example.com)")
        assert '<a href="http://example.com">ok</a>' in result

    def test_mailto_link_rendered(self) -> None:
        result = markdown_to_telegram_html("[mail](mailto:a@b.com)")
        assert '<a href="mailto:a@b.com">mail</a>' in result

    def test_tg_link_rendered(self) -> None:
        result = markdown_to_telegram_html("[chat](tg://resolve?domain=foo)")
        assert '<a href="tg://resolve?domain=foo">chat</a>' in result

    def test_javascript_url_dropped(self) -> None:
        result = markdown_to_telegram_html("[click](javascript:alert(1))")
        assert "<a" not in result
        assert "javascript:" not in result.lower()
        assert "click" in result

    def test_data_url_dropped(self) -> None:
        result = markdown_to_telegram_html("[x](data:text/html,<script>alert(1)</script>)")
        assert "<a" not in result
        assert "data:" not in result

    def test_vbscript_url_dropped(self) -> None:
        result = markdown_to_telegram_html("[x](vbscript:msgbox)")
        assert "<a" not in result
        assert "vbscript:" not in result.lower()

    def test_file_url_dropped(self) -> None:
        result = markdown_to_telegram_html("[x](file:///etc/passwd)")
        assert "<a" not in result
        assert "file:" not in result

    def test_relative_url_dropped(self) -> None:
        result = markdown_to_telegram_html("[x](/relative/path)")
        assert "<a" not in result

    def test_quote_injection_escaped(self) -> None:
        # Markdown link regex stops at the first ')', so the closing ')' bounds
        # the URL and the trailing junk falls outside; what does flow into the
        # href is the part with the quote, which must be HTML-escaped.
        result = markdown_to_telegram_html('[x](https://a.com" onerror="evil)')
        assert 'onerror="evil"' not in result
        # The injected quote is HTML-encoded inside the href value.
        assert "&quot;" in result

    def test_uppercase_scheme_allowed(self) -> None:
        result = markdown_to_telegram_html("[x](HTTPS://example.com)")
        assert '<a href="HTTPS://example.com">x</a>' in result

    def test_whitespace_in_url_stripped(self) -> None:
        result = markdown_to_telegram_html("[x](  https://example.com  )")
        assert '<a href="https://example.com">x</a>' in result
