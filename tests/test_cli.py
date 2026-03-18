import subprocess
from pathlib import Path
import pytest
from typer.testing import CliRunner
from livefork.cli import app

runner = CliRunner()


def _git(cwd, *args):
    subprocess.run(["git"] + list(args), cwd=cwd, check=True, capture_output=True)


def _commit(repo, msg, fname="f.txt"):
    (repo / fname).write_text(msg)
    _git(repo, "add", fname)
    _git(repo, "commit", "-m", msg)


@pytest.fixture()
def fork_with_config(tmp_path):
    """Fork repo with .livefork.toml already written."""
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
    _git(fork, "remote", "rename", "origin", "upstream")

    # feature branch
    _git(fork, "checkout", "-b", "feature/patch")
    _commit(fork, "patch", "patch.txt")
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
name = "feature/patch"
description = "My patch"
"""
    (fork / ".livefork.toml").write_text(config_toml)
    return fork


def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "livefork" in result.output
    assert "0.1.0" in result.output


def test_status_no_config(tmp_path):
    result = runner.invoke(
        app, ["status"], catch_exceptions=False, env={"HOME": str(tmp_path)}
    )
    # Should fail gracefully when no config
    assert result.exit_code != 0 or "no .livefork.toml" in result.output.lower()


def test_add_branch(fork_with_config):
    """livefork add creates a new feature branch entry in config."""
    repo = fork_with_config
    # create a new local branch
    _git(repo, "checkout", "-b", "feature/extra")
    _commit(repo, "extra", "extra.txt")
    _git(repo, "checkout", "main")

    # init knit first
    from livefork.knit import KnitBridge

    KnitBridge(repo).init_knit("johndoe", "main", ["feature/patch"])

    result = runner.invoke(
        app,
        ["add", "feature/extra", "--description", "Extra work"],
        catch_exceptions=False,
        env={"PWD": str(repo)},
    )
    # We test by reading updated config
    from livefork.config import load_config

    cfg = load_config(repo / ".livefork.toml")
    names = [b.name for b in cfg.branches]
    assert "feature/extra" in names


def test_remove_branch(fork_with_config):
    repo = fork_with_config
    from livefork.knit import KnitBridge

    KnitBridge(repo).init_knit("johndoe", "main", ["feature/patch"])

    result = runner.invoke(
        app,
        ["remove", "feature/patch"],
        catch_exceptions=False,
        env={"PWD": str(repo)},
    )
    from livefork.config import load_config

    cfg = load_config(repo / ".livefork.toml")
    names = [b.name for b in cfg.branches]
    assert "feature/patch" not in names
