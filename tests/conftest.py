"""Shared pytest fixtures."""

import subprocess
from pathlib import Path

import pytest


def _git(cwd: Path, *args: str) -> str:
    """Run a git command in cwd and return stdout."""
    result = subprocess.run(
        ["git"] + list(args),
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _make_commit(repo: Path, message: str, filename: str = "file.txt") -> str:
    """Create a file and commit it; return short SHA."""
    (repo / filename).write_text(f"{message}\n")
    _git(repo, "add", filename)
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "--short", "HEAD")


@pytest.fixture()
def git_repo(tmp_path: Path) -> Path:
    """Create a minimal git repository with one commit on `main`."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    _make_commit(repo, "initial commit")
    return repo


@pytest.fixture()
def two_repo_setup(tmp_path: Path) -> tuple[Path, Path]:
    """Return (upstream, fork) where fork clones upstream with remote 'upstream'."""
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    _git(upstream, "init", "-b", "main")
    _git(upstream, "config", "user.email", "upstream@example.com")
    _git(upstream, "config", "user.name", "Upstream User")
    _make_commit(upstream, "upstream initial")

    fork = tmp_path / "fork"
    subprocess.run(
        ["git", "clone", str(upstream), str(fork)], check=True, capture_output=True
    )
    _git(fork, "config", "user.email", "me@example.com")
    _git(fork, "config", "user.name", "Me")
    # rename origin → upstream (simulating fork setup)
    _git(fork, "remote", "rename", "origin", "upstream")
    # add a fake origin for push tests (bare repo)
    origin = tmp_path / "origin.git"
    origin.mkdir()
    _git(origin, "init", "--bare", "-b", "main")
    _git(fork, "remote", "add", "origin", str(origin))
    _git(fork, "push", "upstream", "main")  # push upstream ref
    return upstream, fork
