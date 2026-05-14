"""Tests for abyss.utils module."""

from __future__ import annotations

from unittest.mock import patch

from abyss.utils import (
    prompt_input,
    prompt_multiline,
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


class TestSetupLogging:
    def test_setup_logging_creates_log_directory_and_handlers(self, tmp_path, monkeypatch) -> None:
        import logging

        from abyss.utils import setup_logging

        monkeypatch.setenv("ABYSS_HOME", str(tmp_path))
        for handler in list(logging.root.handlers):
            logging.root.removeHandler(handler)

        setup_logging("DEBUG")

        log_dir = tmp_path / "logs"
        assert log_dir.is_dir()
        file_handler = logging.root.handlers[0]
        assert isinstance(file_handler, logging.FileHandler)
        assert file_handler.baseFilename.startswith(str(log_dir))
        assert file_handler.formatter is not None
        assert logging.root.level == logging.DEBUG

    def test_setup_logging_falls_back_to_info_for_unknown_level(
        self, tmp_path, monkeypatch
    ) -> None:
        import logging

        from abyss.utils import setup_logging

        monkeypatch.setenv("ABYSS_HOME", str(tmp_path))
        for handler in list(logging.root.handlers):
            logging.root.removeHandler(handler)

        setup_logging("not-a-real-level")
        assert logging.root.level == logging.INFO
