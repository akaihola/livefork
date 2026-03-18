import subprocess
from pathlib import Path
import pytest
from livefork.knit import KnitBridge


def _git(cwd, *args):
    subprocess.run(["git"] + list(args), cwd=cwd, check=True, capture_output=True)


def _commit(repo, msg, fname="f.txt"):
    (repo / fname).write_text(msg)
    _git(repo, "add", fname)
    _git(repo, "commit", "-m", msg)


@pytest.fixture()
def knit_repo(tmp_path):
    """Repo with main + feature/a + feature/b branches, no knit yet."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "t@t.com")
    _git(repo, "config", "user.name", "T")
    _commit(repo, "initial", "base.txt")

    _git(repo, "checkout", "-b", "feature/a")
    _commit(repo, "add A", "a.txt")

    _git(repo, "checkout", "main")
    _git(repo, "checkout", "-b", "feature/b")
    _commit(repo, "add B", "b.txt")

    _git(repo, "checkout", "main")
    return repo


def test_init_knit(knit_repo):
    kb = KnitBridge(knit_repo)
    kb.init_knit("johndoe", "main", ["feature/a", "feature/b"])
    cfg = kb.get_config("johndoe")
    assert cfg is not None
    assert cfg.base_branch == "main"
    assert "feature/a" in cfg.feature_branches
    assert "feature/b" in cfg.feature_branches


def test_rebuild_knit(knit_repo):
    kb = KnitBridge(knit_repo)
    kb.init_knit("johndoe", "main", ["feature/a", "feature/b"])
    kb.rebuild("johndoe")
    # johndoe branch should now exist
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "johndoe"],
        cwd=knit_repo,
        capture_output=True,
    )
    assert result.returncode == 0


def test_is_initialized_false(knit_repo):
    kb = KnitBridge(knit_repo)
    assert kb.is_initialized("johndoe") is False


def test_is_initialized_true(knit_repo):
    kb = KnitBridge(knit_repo)
    kb.init_knit("johndoe", "main", ["feature/a"])
    assert kb.is_initialized("johndoe") is True


def test_get_config_missing(knit_repo):
    kb = KnitBridge(knit_repo)
    assert kb.get_config("nobody") is None
