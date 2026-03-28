import subprocess
from pathlib import Path

import pytest

from livefork.git import GitRepo, GitError, BranchInfo, RebaseResult, normalize_github_url


# conftest git_repo fixture creates: tmp_path/repo on branch 'main' with 1 commit


def test_get_current_branch(git_repo):
    g = GitRepo(git_repo)
    assert g.get_current_branch() == "main"


def test_get_commit_sha_full(git_repo):
    g = GitRepo(git_repo)
    sha = g.get_commit_sha("HEAD")
    assert len(sha) == 40
    assert sha.isalnum()


def test_get_commit_sha_short(git_repo):
    g = GitRepo(git_repo)
    sha = g.get_commit_sha("HEAD", short=True)
    assert len(sha) == 7


def test_checkout_branch(git_repo):
    g = GitRepo(git_repo)
    subprocess.run(
        ["git", "checkout", "-b", "feature/x"],
        cwd=git_repo,
        check=True,
        capture_output=True,
    )
    g.checkout("main")
    assert g.get_current_branch() == "main"


def test_list_local_branches(git_repo):
    g = GitRepo(git_repo)
    subprocess.run(
        ["git", "checkout", "-b", "feature/a"],
        cwd=git_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "checkout", "main"], cwd=git_repo, check=True, capture_output=True
    )
    branches = g.list_local_branches()
    names = [b.name for b in branches]
    assert "main" in names
    assert "feature/a" in names


def test_get_branch_tracking_none(git_repo):
    g = GitRepo(git_repo)
    subprocess.run(
        ["git", "checkout", "-b", "local-only"],
        cwd=git_repo,
        check=True,
        capture_output=True,
    )
    assert g.get_branch_tracking("local-only") is None


def test_get_remote_url_missing(git_repo):
    g = GitRepo(git_repo)
    assert g.get_remote_url("nonexistent") is None


def test_rebase_success(two_repo_setup):
    upstream, fork = two_repo_setup
    g = GitRepo(fork)
    # create a branch on fork with one commit
    subprocess.run(
        ["git", "checkout", "-b", "feature/patch"],
        cwd=fork,
        check=True,
        capture_output=True,
    )
    (fork / "patch.txt").write_text("patch\n")
    subprocess.run(
        ["git", "add", "patch.txt"], cwd=fork, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "add patch"], cwd=fork, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "checkout", "main"], cwd=fork, check=True, capture_output=True
    )
    result = g.rebase("main", branch="feature/patch")
    assert result.success is True
    assert result.conflicting_files == []


def test_enable_rerere(git_repo):
    g = GitRepo(git_repo)
    g.enable_rerere()
    result = subprocess.run(
        ["git", "config", "rerere.enabled"],
        cwd=git_repo,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == "true"


def test_is_in_rebase_false(git_repo):
    g = GitRepo(git_repo)
    assert g.is_in_rebase() is False


def test_get_conflicting_files_empty(git_repo):
    g = GitRepo(git_repo)
    assert g.get_conflicting_files() == []


class TestNormalizeGithubUrl:
    def test_ssh_url(self):
        assert (
            normalize_github_url("git@github.com:akaihola/dotfiles")
            == "https://github.com/akaihola/dotfiles"
        )

    def test_ssh_url_with_git_suffix(self):
        assert (
            normalize_github_url("git@github.com:akaihola/dotfiles.git")
            == "https://github.com/akaihola/dotfiles"
        )

    def test_https_url_unchanged(self):
        assert (
            normalize_github_url("https://github.com/akaihola/dotfiles")
            == "https://github.com/akaihola/dotfiles"
        )

    def test_https_url_strips_git_suffix(self):
        assert (
            normalize_github_url("https://github.com/akaihola/dotfiles.git")
            == "https://github.com/akaihola/dotfiles"
        )
