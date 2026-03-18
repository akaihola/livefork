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
