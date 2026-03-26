"""CLI tests for the ``livefork draft`` command with LLM support."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from livefork.cli import app
from livefork.draft_format import DraftContent, format_draft, parse_draft

runner = CliRunner()


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True
    )


def _commit(repo: Path, msg: str, fname: str = "f.txt") -> None:
    (repo / fname).write_text(msg)
    _git(repo, "add", fname)
    _git(repo, "commit", "-m", msg)


@pytest.fixture()
def draft_repo(tmp_path: Path) -> Path:
    """Repository with an upstream, a feature branch, and a .livefork.toml."""
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    _git(upstream, "init", "-b", "main")
    _git(upstream, "config", "user.email", "u@u.com")
    _git(upstream, "config", "user.name", "U")
    _commit(upstream, "initial", "base.txt")

    fork = tmp_path / "fork"
    subprocess.run(
        ["git", "clone", str(upstream), str(fork)], check=True, capture_output=True
    )
    _git(fork, "config", "user.email", "me@me.com")
    _git(fork, "config", "user.name", "Me")
    _git(fork, "remote", "rename", "origin", "upstream")

    # Feature branch with a commit
    _git(fork, "checkout", "-b", "feature/cool")
    _commit(fork, "Add cool feature", "cool.txt")
    _git(fork, "checkout", "main")

    config_toml = """\
[upstream]
remote = "upstream"
branch = "main"

[fork]
remote = "origin"
branch = "main"

[knit]
branch = "johndoe"
base = "main"

[fork-readme]
enabled = false

[[branches]]
name = "feature/cool"
description = "Cool feature"
"""
    (fork / ".livefork.toml").write_text(config_toml)
    return fork


def _read_draft_on_branch(repo: Path, branch: str) -> DraftContent:
    """Check out *branch*, parse ``PULL-REQUEST-DRAFT.md``, return to main."""
    _git(repo, "checkout", branch)
    dc = parse_draft((repo / "PULL-REQUEST-DRAFT.md").read_text())
    _git(repo, "checkout", "main")
    return dc


class TestDraftLLMGeneration:
    """Tests that ``draft`` calls the LLM to generate a draft."""

    def test_draft_generates_with_llm(self, draft_repo: Path) -> None:
        """When llm is available, the draft is generated via the LLM."""
        fake_dc = DraftContent(
            branch="feature/cool",
            title="Cool feature title",
            body="This PR does stuff.",
        )
        fake_generate = MagicMock(return_value=fake_dc)

        with patch("livefork.draft_llm.generate_draft", fake_generate):
            result = runner.invoke(
                app,
                ["draft", "feature/cool", "--no-edit"],
                catch_exceptions=False,
                env={"PWD": str(draft_repo)},
            )

        assert result.exit_code == 0
        fake_generate.assert_called_once()
        # Log and diff should be non-empty strings
        call_kw = fake_generate.call_args
        log_arg = call_kw.args[0]
        diff_arg = call_kw.args[1]
        assert "Add cool feature" in log_arg
        assert "cool.txt" in diff_arg

    def test_draft_file_has_canonical_format(self, draft_repo: Path) -> None:
        """The written file uses the canonical branch/title/body format."""
        fake_dc = DraftContent(
            branch="feature/cool",
            title="My PR title",
            body="Detailed description.",
        )
        fake_generate = MagicMock(return_value=fake_dc)

        with patch("livefork.draft_llm.generate_draft", fake_generate):
            runner.invoke(
                app,
                ["draft", "feature/cool", "--no-edit"],
                catch_exceptions=False,
                env={"PWD": str(draft_repo)},
            )

        dc = _read_draft_on_branch(draft_repo, "feature/cool")
        assert dc.branch == "feature/cool"
        assert dc.title == "My PR title"
        assert dc.body == "Detailed description."

    def test_draft_passes_model_and_branch(self, draft_repo: Path) -> None:
        """--model and branch name are forwarded to generate_draft."""
        fake_dc = DraftContent("feature/cool", "Title", "Body")
        fake_generate = MagicMock(return_value=fake_dc)

        with patch("livefork.draft_llm.generate_draft", fake_generate):
            result = runner.invoke(
                app,
                ["draft", "feature/cool", "--no-edit", "--model", "test-model"],
                catch_exceptions=False,
                env={"PWD": str(draft_repo)},
            )

        assert result.exit_code == 0
        assert fake_generate.call_args.kwargs["model_id"] == "test-model"
        assert fake_generate.call_args.kwargs["branch"] == "feature/cool"

    def test_draft_falls_back_on_import_error(self, draft_repo: Path) -> None:
        """When llm is not installed, a template draft is created instead."""
        import livefork.draft_llm as draft_mod

        def _raise_import(*a, **kw):
            raise ImportError("No module named 'llm'")

        with patch.object(draft_mod, "generate_draft", side_effect=_raise_import):
            result = runner.invoke(
                app,
                ["draft", "feature/cool", "--no-edit"],
                catch_exceptions=False,
                env={"PWD": str(draft_repo)},
            )

        assert result.exit_code == 0
        dc = _read_draft_on_branch(draft_repo, "feature/cool")
        assert dc.branch == "feature/cool"
        assert "Describe the purpose" in dc.body

    def test_draft_falls_back_on_llm_error(self, draft_repo: Path) -> None:
        """When the LLM call fails, a template draft is created instead."""
        import livefork.draft_llm as draft_mod

        def _raise_runtime(*a, **kw):
            raise RuntimeError("API key not set")

        with patch.object(draft_mod, "generate_draft", side_effect=_raise_runtime):
            result = runner.invoke(
                app,
                ["draft", "feature/cool", "--no-edit"],
                catch_exceptions=False,
                env={"PWD": str(draft_repo)},
            )

        assert result.exit_code == 0
        dc = _read_draft_on_branch(draft_repo, "feature/cool")
        assert dc.branch == "feature/cool"
        assert "Describe the purpose" in dc.body

    def test_draft_skips_llm_if_file_exists(self, draft_repo: Path) -> None:
        """If PULL-REQUEST-DRAFT.md already exists, the LLM is not called."""
        _git(draft_repo, "checkout", "feature/cool")
        existing = DraftContent("feature/cool", "Existing title", "Existing body.")
        (draft_repo / "PULL-REQUEST-DRAFT.md").write_text(format_draft(existing))
        _git(draft_repo, "add", "PULL-REQUEST-DRAFT.md")
        _git(draft_repo, "commit", "-m", "docs: existing draft")
        _git(draft_repo, "checkout", "main")

        fake_generate = MagicMock(
            return_value=DraftContent("feature/cool", "New", "New body"),
        )
        import livefork.draft_llm as draft_mod

        with patch.object(draft_mod, "generate_draft", fake_generate):
            result = runner.invoke(
                app,
                ["draft", "feature/cool", "--no-edit"],
                catch_exceptions=False,
                env={"PWD": str(draft_repo)},
            )

        assert result.exit_code == 0
        fake_generate.assert_not_called()

    def test_draft_message_overrides_title(self, draft_repo: Path) -> None:
        """--message replaces the title in an LLM-generated draft."""
        fake_dc = DraftContent("feature/cool", "LLM title", "LLM body.")
        fake_generate = MagicMock(return_value=fake_dc)
        import livefork.draft_llm as draft_mod

        with patch.object(draft_mod, "generate_draft", fake_generate):
            result = runner.invoke(
                app,
                [
                    "draft", "feature/cool",
                    "--no-edit",
                    "--message", "My custom title",
                ],
                catch_exceptions=False,
                env={"PWD": str(draft_repo)},
            )

        assert result.exit_code == 0
        dc = _read_draft_on_branch(draft_repo, "feature/cool")
        assert dc.title == "My custom title"
        assert dc.body == "LLM body."
        assert dc.branch == "feature/cool"

    def test_template_fallback_uses_message_as_title(self, draft_repo: Path) -> None:
        """--message sets the title in the template fallback path too."""
        import livefork.draft_llm as draft_mod

        with patch.object(
            draft_mod, "generate_draft", side_effect=ImportError("nope"),
        ):
            result = runner.invoke(
                app,
                [
                    "draft", "feature/cool",
                    "--no-edit",
                    "--message", "Custom fallback title",
                ],
                catch_exceptions=False,
                env={"PWD": str(draft_repo)},
            )

        assert result.exit_code == 0
        dc = _read_draft_on_branch(draft_repo, "feature/cool")
        assert dc.title == "Custom fallback title"


class TestDraftNoEdit:
    """Tests for the --no-edit flag."""

    def test_no_edit_commits_without_editor(self, draft_repo: Path) -> None:
        """--no-edit creates and commits the draft without opening an editor."""
        fake_dc = DraftContent("feature/cool", "Title", "Body.")
        fake_generate = MagicMock(return_value=fake_dc)
        import livefork.draft_llm as draft_mod

        with patch.object(draft_mod, "generate_draft", fake_generate):
            result = runner.invoke(
                app,
                ["draft", "feature/cool", "--no-edit"],
                catch_exceptions=False,
                env={"PWD": str(draft_repo)},
            )

        assert result.exit_code == 0
        dc = _read_draft_on_branch(draft_repo, "feature/cool")
        assert dc.branch == "feature/cool"
        assert dc.title == "Title"
        assert dc.body == "Body."
