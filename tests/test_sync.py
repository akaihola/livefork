import subprocess
from pathlib import Path
import pytest
from livefork.config import BranchConfig, LiveforkConfig, ForkReadmeConfig
from livefork.git import GitRepo
from livefork.knit import KnitBridge
from livefork.state import load_state
from livefork.sync import SyncOptions, SyncOrchestrator, SyncError


def _git(cwd, *args):
    subprocess.run(["git"] + list(args), cwd=cwd, check=True, capture_output=True)


def _commit(repo, msg, fname):
    (repo / fname).write_text(msg)
    _git(repo, "add", fname)
    _git(repo, "commit", "-m", msg)


@pytest.fixture()
def sync_setup(tmp_path):
    """
    upstream: has initial commit + one new commit after fork point
    fork:     clones upstream, has 'feature/patch' branch
    Returns (upstream, fork, config)
    """
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

    # add a fake origin (bare) for push tests
    origin = tmp_path / "origin.git"
    origin.mkdir()
    _git(origin, "init", "--bare", "-b", "main")
    _git(fork, "remote", "add", "origin", str(origin))

    # fork creates a feature branch
    _git(fork, "checkout", "-b", "feature/patch")
    _commit(fork, "patch", "patch.txt")
    _git(fork, "checkout", "main")

    # upstream advances
    _commit(upstream, "upstream advance", "up.txt")

    from livefork.config import (
        UpstreamConfig,
        ForkConfig,
        KnitSectionConfig,
        ForkReadmeConfig,
        LiveforkConfig,
    )

    cfg = LiveforkConfig(
        upstream=UpstreamConfig(remote="upstream", branch="main"),
        fork=ForkConfig(remote="origin", branch="main"),
        knit=KnitSectionConfig(branch="johndoe", base="main"),
        fork_readme=ForkReadmeConfig(enabled=False),
        branches=[BranchConfig(name="feature/patch", description="My patch")],
    )
    return upstream, fork, cfg


def test_sync_dry_run_exits_zero(sync_setup):
    upstream, fork, cfg = sync_setup
    g = GitRepo(fork)
    knit = KnitBridge(fork)
    # init knit first
    knit.init_knit("johndoe", "main", ["feature/patch"])
    orch = SyncOrchestrator(cfg, g, knit, fork)
    rc = orch.run(SyncOptions(dry_run=True))
    assert rc == 0
    # no state file left after dry-run completes
    assert load_state(fork / ".git") is None


def test_sync_no_conflict(sync_setup):
    upstream, fork, cfg = sync_setup
    g = GitRepo(fork)
    knit = KnitBridge(fork)
    knit.init_knit("johndoe", "main", ["feature/patch"])
    orch = SyncOrchestrator(cfg, g, knit, fork)
    rc = orch.run(SyncOptions(no_readme=True))
    assert rc == 0
    # fork main should now have upstream's new commit
    g.checkout("main")
    log = subprocess.run(
        ["git", "log", "--oneline", "main"],
        cwd=fork,
        capture_output=True,
        text=True,
    ).stdout
    assert "upstream advance" in log
    # no leftover state
    assert load_state(fork / ".git") is None


def test_sync_saves_state_after_fetch(sync_setup, monkeypatch):
    """State should be saved after step 1 (fetch)."""
    upstream, fork, cfg = sync_setup
    g = GitRepo(fork)
    knit = KnitBridge(fork)
    knit.init_knit("johndoe", "main", ["feature/patch"])

    # intercept _step_advance_fork_main to raise so we can inspect state
    calls = []
    orch = SyncOrchestrator(cfg, g, knit, fork)
    original = orch._step_advance_fork_main

    def boom(options):
        calls.append("boom")
        raise RuntimeError("intentional")

    monkeypatch.setattr(orch, "_step_advance_fork_main", boom)

    with pytest.raises(RuntimeError):
        orch.run(SyncOptions(no_readme=True))

    assert len(calls) == 1
    # step was saved as 2 (about to do step 2)
    state = load_state(fork / ".git")
    assert state is not None
    assert state.step == 2


def test_abort_sync_resets_branches(sync_setup):
    upstream, fork, cfg = sync_setup
    g = GitRepo(fork)
    knit = KnitBridge(fork)
    knit.init_knit("johndoe", "main", ["feature/patch"])

    pre_sha = g.get_commit_sha("feature/patch")

    # run sync to completion, then manually inject state as if paused
    from livefork.state import SyncState, save_state

    fake_state = SyncState(
        step=3,
        branch_index=1,  # branch 0 "already rebased"
        branch_pre_sync_shas={"feature/patch": pre_sha},
        paused_branch="feature/patch",
    )
    save_state(fake_state, fork / ".git")

    orch = SyncOrchestrator(cfg, g, knit, fork)
    rc = orch.abort_sync()
    assert rc == 0
    # feature/patch should be back at pre_sha
    assert g.get_commit_sha("feature/patch") == pre_sha
    assert load_state(fork / ".git") is None


def test_sync_raises_if_already_in_progress(sync_setup):
    upstream, fork, cfg = sync_setup
    g = GitRepo(fork)
    knit = KnitBridge(fork)
    knit.init_knit("johndoe", "main", ["feature/patch"])

    from livefork.state import SyncState, save_state

    save_state(SyncState(1, 0, {}, None), fork / ".git")

    orch = SyncOrchestrator(cfg, g, knit, fork)
    with pytest.raises(SyncError, match="already in progress"):
        orch.run()
