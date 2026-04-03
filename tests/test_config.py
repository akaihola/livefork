import pytest
from pathlib import Path
from livefork.config import (
    BranchConfig,
    ForkConfig,
    ForkReadmeConfig,
    KnitSectionConfig,
    LiveforkConfig,
    UpstreamConfig,
    find_config,
    load_config,
    resolve_config_path,
    save_config,
)


MINIMAL_TOML = """\
[knit]
branch = "johndoe"
"""

FULL_TOML = """\
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
enabled = true
file = "README.md"
push = true

[[branches]]
name = "feature/foo"
description = "Fix foo"

[[branches]]
name = "feature/bar"
description = "Add bar"
pr = "https://github.com/org/repo/pull/42"
push = false
"""


def test_load_minimal_config(tmp_path):
    p = tmp_path / ".livefork.toml"
    p.write_text(MINIMAL_TOML)
    cfg = load_config(p)
    assert cfg.upstream.remote == "upstream"
    assert cfg.fork.remote == "origin"
    assert cfg.knit.branch == "johndoe"
    assert cfg.fork_readme.enabled is True
    assert cfg.branches == []


def test_load_full_config(tmp_path):
    p = tmp_path / ".livefork.toml"
    p.write_text(FULL_TOML)
    cfg = load_config(p)
    assert len(cfg.branches) == 2
    assert cfg.branches[0].name == "feature/foo"
    assert cfg.branches[1].pr == "https://github.com/org/repo/pull/42"
    assert cfg.branches[1].push is False


def test_save_config_roundtrip(tmp_path):
    cfg = LiveforkConfig(
        upstream=UpstreamConfig(remote="upstream", branch="main"),
        fork=ForkConfig(remote="origin", branch="main"),
        knit=KnitSectionConfig(branch="alice", base="main"),
        fork_readme=ForkReadmeConfig(enabled=True, file="README.md", push=True),
        branches=[
            BranchConfig(name="feature/foo", description="Fix foo"),
            BranchConfig(name="feature/bar", description="Add bar", push=False),
        ],
    )
    p = tmp_path / ".livefork.toml"
    save_config(cfg, p)
    loaded = load_config(p)
    assert loaded.knit.branch == "alice"
    assert len(loaded.branches) == 2
    assert loaded.branches[1].push is False


def test_branch_push_none_is_preserved(tmp_path):
    """push=None means 'auto' – not serialized to TOML."""
    cfg = LiveforkConfig(
        knit=KnitSectionConfig(branch="me"),
        branches=[BranchConfig(name="feature/x", description="x")],
    )
    p = tmp_path / ".livefork.toml"
    save_config(cfg, p)
    loaded = load_config(p)
    assert loaded.branches[0].push is None


def test_find_config_walks_up(tmp_path):
    (tmp_path / ".livefork.toml").write_text(MINIMAL_TOML)
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    found = find_config(nested)
    assert found == tmp_path / ".livefork.toml"


def test_find_config_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        find_config(tmp_path / "nowhere")


# ------------------------------------------------------------------ resolve_config_path


def test_resolve_config_path_git_dir_config_exists(tmp_path):
    """.git/livefork.toml is returned when it already exists."""
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    git_config = git_dir / "livefork.toml"
    git_config.write_text(MINIMAL_TOML)
    assert resolve_config_path(tmp_path) == git_config


def test_resolve_config_path_prefers_git_dir_over_workdir(tmp_path):
    """When both locations exist, .git/livefork.toml wins."""
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "livefork.toml").write_text(MINIMAL_TOML)
    (tmp_path / ".livefork.toml").write_text(MINIMAL_TOML)
    assert resolve_config_path(tmp_path) == git_dir / "livefork.toml"


def test_resolve_config_path_falls_back_to_workdir(tmp_path):
    """When only .livefork.toml exists it is returned (legacy repos)."""
    workdir_config = tmp_path / ".livefork.toml"
    workdir_config.write_text(MINIMAL_TOML)
    assert resolve_config_path(tmp_path) == workdir_config


def test_resolve_config_path_new_git_repo_defaults_to_git_dir(tmp_path):
    """New config in a git repo defaults to .git/livefork.toml."""
    (tmp_path / ".git").mkdir()
    assert resolve_config_path(tmp_path) == tmp_path / ".git" / "livefork.toml"


def test_resolve_config_path_non_git_dir_defaults_to_workdir(tmp_path):
    """When there is no .git directory, .livefork.toml is the default."""
    assert resolve_config_path(tmp_path) == tmp_path / ".livefork.toml"


# ------------------------------------------------------------------ find_config (git-dir preference)


def test_find_config_prefers_git_dir_over_workdir(tmp_path):
    """find_config picks .git/livefork.toml before .livefork.toml at same level."""
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    git_config = git_dir / "livefork.toml"
    git_config.write_text(MINIMAL_TOML)
    (tmp_path / ".livefork.toml").write_text(MINIMAL_TOML)
    assert find_config(tmp_path) == git_config


def test_find_config_git_dir_found_when_walking_up(tmp_path):
    """.git/livefork.toml in a parent is found when searching from a nested dir."""
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    git_config = git_dir / "livefork.toml"
    git_config.write_text(MINIMAL_TOML)
    nested = tmp_path / "src" / "sub"
    nested.mkdir(parents=True)
    assert find_config(nested) == git_config
