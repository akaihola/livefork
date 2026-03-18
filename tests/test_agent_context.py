import subprocess
from pathlib import Path
import pytest
from livefork.config import BranchConfig, LiveforkConfig, ForkConfig, KnitSectionConfig
from livefork.config import UpstreamConfig, ForkReadmeConfig
from livefork.git import GitRepo
from livefork.state import SyncState
from livefork.agent_context import generate_agent_context


def _git(cwd, *args):
    subprocess.run(["git"] + list(args), cwd=cwd, check=True, capture_output=True)


def _commit(repo, msg, fname, content=None):
    (repo / fname).write_text(content or msg)
    _git(repo, "add", fname)
    _git(repo, "commit", "-m", msg)


@pytest.fixture()
def conflict_repo(tmp_path):
    """A repo mid-rebase with a conflict on feature/patch."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "t@t.com")
    _git(repo, "config", "user.name", "T")
    _commit(repo, "initial", "foo.py", "x = 1\n")

    # branch diverges
    _git(repo, "checkout", "-b", "feature/patch")
    _commit(repo, "patch foo", "foo.py", "x = 2\n")

    # main also changes foo.py
    _git(repo, "checkout", "main")
    _commit(repo, "upstream change", "foo.py", "x = 99\n")

    # trigger the conflict: rebase feature/patch onto updated main
    _git(repo, "checkout", "feature/patch")
    result = subprocess.run(
        ["git", "rebase", "main"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    # rebase should have stopped with conflict
    assert result.returncode != 0
    return repo


def test_agent_context_contains_branch_name(conflict_repo):
    cfg = LiveforkConfig(
        upstream=UpstreamConfig(),
        fork=ForkConfig(),
        knit=KnitSectionConfig(branch="johndoe"),
        fork_readme=ForkReadmeConfig(enabled=False),
        branches=[BranchConfig(name="feature/patch", description="Patch foo")],
    )
    g = GitRepo(conflict_repo)
    state = SyncState(
        step=3,
        branch_index=0,
        branch_pre_sync_shas={"feature/patch": "abc"},
        paused_branch="feature/patch",
    )
    doc = generate_agent_context(cfg, g, state)
    assert "feature/patch" in doc


def test_agent_context_contains_conflicting_file(conflict_repo):
    cfg = LiveforkConfig(
        knit=KnitSectionConfig(branch="j"),
        branches=[BranchConfig(name="feature/patch", description="Patch foo")],
    )
    g = GitRepo(conflict_repo)
    state = SyncState(
        step=3, branch_index=0, branch_pre_sync_shas={}, paused_branch="feature/patch"
    )
    doc = generate_agent_context(cfg, g, state)
    assert "foo.py" in doc


def test_agent_context_contains_continue_command(conflict_repo):
    cfg = LiveforkConfig(knit=KnitSectionConfig(branch="j"), branches=[])
    g = GitRepo(conflict_repo)
    state = SyncState(3, 0, {}, "feature/patch")
    doc = generate_agent_context(cfg, g, state)
    assert "livefork continue" in doc


def test_agent_context_no_conflict_raises(tmp_path):
    # no rebase in progress
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "t@t.com")
    _git(repo, "config", "user.name", "T")
    _commit(repo, "init", "f.txt")
    cfg = LiveforkConfig(knit=KnitSectionConfig(branch="j"), branches=[])
    g = GitRepo(repo)
    state = SyncState(3, 0, {}, None)
    with pytest.raises(ValueError, match="No rebase"):
        generate_agent_context(cfg, g, state)
