"""Tests for the LLM-based PR draft generation module."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from livefork.draft_format import DraftContent
from livefork.draft_llm import SYSTEM_PROMPT, build_prompt, generate_draft, _parse_llm_output


def _make_mock_llm(response_text: str = "Generated title\n\nGenerated body\n"):
    """Create a mock ``llm`` module with ``get_model`` returning a mock model."""
    mock_llm = MagicMock()
    fake_response = MagicMock()
    fake_response.text.return_value = response_text
    mock_model = MagicMock()
    mock_model.prompt.return_value = fake_response
    mock_llm.get_model.return_value = mock_model
    return mock_llm, mock_model, fake_response


# ------------------------------------------------------------------ build_prompt


class TestBuildPrompt:
    """Unit tests for ``build_prompt``."""

    def test_includes_log(self):
        prompt = build_prompt("commit abc\n", "diff --git a/f b/f\n")
        assert "commit abc" in prompt

    def test_includes_diff(self):
        prompt = build_prompt("commit abc\n", "diff --git a/f b/f\n")
        assert "diff --git a/f b/f" in prompt

    def test_has_section_headers(self):
        prompt = build_prompt("log", "diff")
        assert "## Git commit log" in prompt
        assert "## Diff against branch point" in prompt


# ------------------------------------------------------------------ _parse_llm_output


class TestParseLlmOutput:
    """Unit tests for ``_parse_llm_output``."""

    def test_splits_title_and_body(self):
        dc = _parse_llm_output("My title\n\nBody paragraph.", "feature/x")
        assert dc.title == "My title"
        assert dc.body == "Body paragraph."
        assert dc.branch == "feature/x"

    def test_title_only(self):
        dc = _parse_llm_output("Just a title", "feature/x")
        assert dc.title == "Just a title"
        assert dc.body == ""

    def test_empty_string_uses_branch_as_title(self):
        dc = _parse_llm_output("", "feature/x")
        assert dc.title == "feature/x"
        assert dc.body == ""

    def test_multiline_body(self):
        dc = _parse_llm_output("Title\n\nLine 1\nLine 2\nLine 3", "b")
        assert dc.title == "Title"
        assert dc.body == "Line 1\nLine 2\nLine 3"


# ------------------------------------------------------------------ generate_draft


class TestGenerateDraft:
    """Unit tests for ``generate_draft`` (LLM call mocked)."""

    def test_uses_specified_model(self):
        mock_llm, mock_model, _ = _make_mock_llm()
        with patch.dict(sys.modules, {"llm": mock_llm}):
            result = generate_draft(
                "log text", "diff text",
                branch="feature/x", model_id="test-model",
            )

        mock_llm.get_model.assert_called_once_with("test-model")
        assert isinstance(result, DraftContent)
        assert result.branch == "feature/x"
        assert result.title == "Generated title"

    def test_uses_default_model_when_none(self):
        mock_llm, mock_model, _ = _make_mock_llm()
        with patch.dict(sys.modules, {"llm": mock_llm}):
            generate_draft("log", "diff", branch="b")

        mock_llm.get_model.assert_called_once_with()

    def test_passes_system_prompt(self):
        mock_llm, mock_model, _ = _make_mock_llm()
        with patch.dict(sys.modules, {"llm": mock_llm}):
            generate_draft("log", "diff", branch="b")

        call_kwargs = mock_model.prompt.call_args
        assert call_kwargs.kwargs["system"] == SYSTEM_PROMPT

    def test_prompt_contains_log_and_diff(self):
        mock_llm, mock_model, _ = _make_mock_llm()
        with patch.dict(sys.modules, {"llm": mock_llm}):
            generate_draft("my-log-text", "my-diff-text", branch="b")

        prompt_arg = mock_model.prompt.call_args.args[0]
        assert "my-log-text" in prompt_arg
        assert "my-diff-text" in prompt_arg

    def test_returns_draft_content(self):
        mock_llm, _, _ = _make_mock_llm("Cool title\n\nCool body stuff.")
        with patch.dict(sys.modules, {"llm": mock_llm}):
            dc = generate_draft("log", "diff", branch="feature/cool")

        assert dc.branch == "feature/cool"
        assert dc.title == "Cool title"
        assert dc.body == "Cool body stuff."
