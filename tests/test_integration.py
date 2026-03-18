"""
End-to-end integration tests for the sync workflow.
These use real git repos in tmp_path – no GitHub, no remote network.
"""

import subprocess
from pathlib import Path
import pytest
from livefork.config import (
    BranchConfig,
    ForkConfig,
    ForkReadmeConfig,
    KnitSectionConfig,
    LiveforkConfig,
    UpstreamConfig,
)
from livefork.git import GitRepo
from livefork.knit import KnitBridge
from livefork.state import load_state
from livefork.sync import SyncOptions, SyncOrchestrator


def _git(cwd, *args):
    subprocess.run(["git"] + list(args), cwd=cwd, check=True, capture_output=True)


def _commit(repo, msg, fname, content=None):
    (repo / fname).write_text(content or msg)
    _git(repo, "add", fname)
    _git(repo, "commit", "-m", msg)
    return subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _setup_fork(tmp_path) -> tuple[Path, Path, LiveforkConfig]:
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

    # create feature branches
    _git(fork, "checkout", "-b", "feature/alpha")
    _commit(fork, "alpha work", "alpha.txt")
    _git(fork, "checkout", "main")

    _git(fork, "checkout", "-b", "feature/beta")
    _commit(fork, "beta work", "beta.txt")
    _git(fork, "checkout", "main")

    cfg = LiveforkConfig(
        upstream=UpstreamConfig(remote="upstream", branch="main"),
        fork=ForkConfig(remote="origin", branch="main"),
        knit=KnitSectionConfig(branch="johndoe", base="main"),
        fork_readme=ForkReadmeConfig(enabled=False),
        branches=[
            BranchConfig(name="feature/alpha", description="Alpha"),
            BranchConfig(name="feature/beta", description="Beta"),
        ],
    )
    # init knit
    KnitBridge(fork).init_knit("johndoe", "main", ["feature/alpha", "feature/beta"])
    return upstream, fork, cfg


def test_full_sync_no_conflict(tmp_path):
    upstream, fork, cfg = _setup_fork(tmp_path)

    # upstream makes a new commit (non-conflicting)
    _commit(upstream, "upstream new feature", "upstream_new.txt")

    g = GitRepo(fork)
    knit = KnitBridge(fork)
    orch = SyncOrchestrator(cfg, g, knit, fork)
    rc = orch.run(SyncOptions(no_readme=True))

    assert rc == 0
    assert load_state(fork / ".git") is None

    # fork/main should now be at upstream/main
    g.checkout("main")
    fork_sha = g.get_commit_sha("main")
    upstream_sha = g.get_commit_sha("upstream/main")
    assert fork_sha == upstream_sha

    # feature branches rebased
    for branch_name in ["feature/alpha", "feature/beta"]:
        g.checkout(branch_name)
        r = g.run(["log", "--oneline", branch_name], check=True)
        assert "upstream new feature" in r.stdout

    # merge branch exists
    r = g.run(["rev-parse", "--verify", "johndoe"], check=False)
    assert r.returncode == 0


def test_sync_conflict_pauses_and_abort_restores(tmp_path):
    upstream, fork, cfg = _setup_fork(tmp_path)

    # upstream changes alpha.txt (same file as feature/alpha)
    _commit(upstream, "upstream changes alpha", "alpha.txt", "upstream version\n")

    g = GitRepo(fork)
    knit = KnitBridge(fork)
    pre_alpha_sha = g.get_commit_sha("feature/alpha")

    orch = SyncOrchestrator(cfg, g, knit, fork)
    rc = orch.run(SyncOptions(no_readme=True))
    # Should pause on conflict
    assert rc == 1

    state = load_state(fork / ".git")
    assert state is not None
    assert state.paused_branch == "feature/alpha"

    # Abort
    orch.abort_sync()
    assert load_state(fork / ".git") is None
    # feature/alpha back to pre-sync sha
    assert g.get_commit_sha("feature/alpha") == pre_alpha_sha


def test_sync_idempotent_after_no_upstream_change(tmp_path):
    upstream, fork, cfg = _setup_fork(tmp_path)

    g = GitRepo(fork)
    knit = KnitBridge(fork)
    orch = SyncOrchestrator(cfg, g, knit, fork)

    rc1 = orch.run(SyncOptions(no_readme=True))
    sha_after_first = g.get_commit_sha("main")

    rc2 = orch.run(SyncOptions(no_readme=True))
    sha_after_second = g.get_commit_sha("main")

    assert rc1 == 0
    assert rc2 == 0
    assert sha_after_first == sha_after_second
