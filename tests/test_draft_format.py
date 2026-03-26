"""Tests for ``livefork.draft_format`` – the canonical PULL-REQUEST-DRAFT.md format."""

from __future__ import annotations

import pytest

from livefork.draft_format import DraftContent, format_draft, parse_draft


# ------------------------------------------------------------------ format_draft


class TestFormatDraft:
    """Unit tests for ``format_draft``."""

    def test_basic_round_trip_text(self):
        dc = DraftContent(branch="feature/x", title="My title", body="Body text.")
        text = format_draft(dc)
        assert text == "branch: feature/x\ntitle: My title\n\nBody text.\n"

    def test_empty_body(self):
        text = format_draft(DraftContent("b", "t", ""))
        assert text == "branch: b\ntitle: t\n\n"

    def test_multiline_body(self):
        text = format_draft(DraftContent("b", "t", "line1\nline2"))
        assert "line1\nline2" in text

    def test_ends_with_newline(self):
        text = format_draft(DraftContent("b", "t", "body"))
        assert text.endswith("\n")

    def test_body_already_ends_with_newline(self):
        text = format_draft(DraftContent("b", "t", "body\n"))
        # Should not double-up newlines
        assert text.endswith("body\n\n") or text.endswith("body\n")


# ------------------------------------------------------------------ parse_draft


class TestParseDraft:
    """Unit tests for ``parse_draft``."""

    def test_basic_parse(self):
        text = "branch: feature/x\ntitle: My title\n\nBody text.\n"
        dc = parse_draft(text)
        assert dc.branch == "feature/x"
        assert dc.title == "My title"
        assert dc.body == "Body text."

    def test_multiline_body(self):
        text = "branch: b\ntitle: t\n\nline 1\nline 2\nline 3\n"
        dc = parse_draft(text)
        assert dc.body == "line 1\nline 2\nline 3"

    def test_empty_body(self):
        text = "branch: b\ntitle: t\n\n"
        dc = parse_draft(text)
        assert dc.body == ""

    def test_no_blank_line_empty_body(self):
        text = "branch: b\ntitle: t\n"
        dc = parse_draft(text)
        assert dc.body == ""

    def test_metadata_order_irrelevant(self):
        text = "title: T\nbranch: B\n\nbody\n"
        dc = parse_draft(text)
        assert dc.branch == "B"
        assert dc.title == "T"

    def test_missing_branch_raises(self):
        with pytest.raises(ValueError, match="branch"):
            parse_draft("title: T\n\nbody\n")

    def test_missing_title_raises(self):
        with pytest.raises(ValueError, match="title"):
            parse_draft("branch: B\n\nbody\n")

    def test_colons_in_title_preserved(self):
        text = "branch: b\ntitle: fix: handle edge case\n\nbody\n"
        dc = parse_draft(text)
        assert dc.title == "fix: handle edge case"

    def test_body_with_colon_lines(self):
        text = "branch: b\ntitle: t\n\nkey: value inside body\n"
        dc = parse_draft(text)
        assert dc.body == "key: value inside body"

    def test_extra_whitespace_stripped(self):
        text = "  branch:  b  \n  title:  t  \n\n  body  \n"
        dc = parse_draft(text)
        assert dc.branch == "b"
        assert dc.title == "t"
        assert dc.body == "body"


# ------------------------------------------------------------------ round-trip


class TestRoundTrip:
    """``format_draft`` → ``parse_draft`` should preserve all fields."""

    @pytest.mark.parametrize(
        "branch, title, body",
        [
            ("feature/foo", "Add foo support", "Long description here."),
            ("fix/bar", "fix: handle bar edge case", ""),
            ("topic/baz", "Refactor baz module", "Line 1\n\nLine 3"),
        ],
    )
    def test_round_trip(self, branch: str, title: str, body: str):
        original = DraftContent(branch=branch, title=title, body=body)
        restored = parse_draft(format_draft(original))
        assert restored.branch == original.branch
        assert restored.title == original.title
        assert restored.body == original.body
