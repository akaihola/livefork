import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from typer.testing import CliRunner
from livefork.cli import app, _gh_owner_type, _gh_authenticated_user

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


# ------------------------------------------------------------------ helpers for create


def _make_sp_result(returncode=0, stdout="", stderr=""):
    """Build a fake subprocess.CompletedProcess."""
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


# ------------------------------------------------------------------ _gh_owner_type


class TestGhOwnerType:
    """Unit tests for the ``_gh_owner_type`` helper."""

    def test_returns_organization(self):
        with patch("subprocess.run", return_value=_make_sp_result(stdout="Organization\n")):
            assert _gh_owner_type("my-org") == "Organization"

    def test_returns_user(self):
        with patch("subprocess.run", return_value=_make_sp_result(stdout="User\n")):
            assert _gh_owner_type("akaihola") == "User"

    def test_returns_unknown_on_failure(self):
        with patch("subprocess.run", return_value=_make_sp_result(returncode=1)):
            assert _gh_owner_type("nonexistent") == "unknown"

    def test_calls_gh_api_with_correct_args(self):
        with patch("subprocess.run", return_value=_make_sp_result(stdout="User\n")) as mock_run:
            _gh_owner_type("testuser")
            mock_run.assert_called_once_with(
                ["gh", "api", "users/testuser", "--jq", ".type"],
                capture_output=True,
                text=True,
            )


# ------------------------------------------------------------------ _gh_authenticated_user


class TestGhAuthenticatedUser:
    """Unit tests for the ``_gh_authenticated_user`` helper."""

    def test_returns_login(self):
        with patch("subprocess.run", return_value=_make_sp_result(stdout="octocat\n")):
            assert _gh_authenticated_user() == "octocat"

    def test_falls_back_to_getuser_on_failure(self):
        with patch("subprocess.run", return_value=_make_sp_result(returncode=1)):
            with patch("livefork.cli.getpass.getuser", return_value="localuser"):
                assert _gh_authenticated_user() == "localuser"

    def test_falls_back_to_getuser_on_empty_output(self):
        with patch("subprocess.run", return_value=_make_sp_result(stdout="")):
            with patch("livefork.cli.getpass.getuser", return_value="localuser"):
                assert _gh_authenticated_user() == "localuser"


# ------------------------------------------------------------------ create command


def _gh_passthrough_side_effect(gh_result):
    """Return a side_effect for ``subprocess.run`` that intercepts ``gh`` calls
    and lets real ``git`` calls through to the filesystem."""
    _real_run = subprocess.run

    def _side_effect(args, **kwargs):
        if args and args[0] == "gh":
            return gh_result
        return _real_run(args, **kwargs)

    return _side_effect


class TestCreate:
    """Tests for ``livefork create``."""

    @pytest.fixture()
    def clone_target(self, tmp_path):
        """Set up a git repo that looks like a freshly cloned fork.

        The ``origin`` remote points to the upstream URL so that
        ``create`` can rename it and construct the fork remote.
        """
        clone_dir = tmp_path / "project"
        clone_dir.mkdir()
        _git(clone_dir, "init", "-b", "main")
        _git(clone_dir, "config", "user.email", "t@t.com")
        _git(clone_dir, "config", "user.name", "T")
        (clone_dir / "README.md").write_text("hello\n")
        _git(clone_dir, "add", ".")
        _git(clone_dir, "commit", "-m", "init")
        _git(
            clone_dir,
            "remote",
            "add",
            "origin",
            "https://github.com/upstream-org/project.git",
        )
        return clone_dir

    def test_slug_normalisation_from_url(self, clone_target):
        """GitHub URLs are normalised to owner/repo slugs."""
        gh_ok = _make_sp_result()
        with (
            patch("livefork.cli._gh_authenticated_user", return_value="testuser"),
            patch(
                "subprocess.run",
                side_effect=_gh_passthrough_side_effect(gh_ok),
            ),
        ):
            result = runner.invoke(
                app,
                [
                    "create",
                    "https://github.com/upstream-org/project.git",
                    "--clone-path",
                    str(clone_target),
                    "--no-init",
                ],
                catch_exceptions=False,
            )
        assert result.exit_code == 0
        assert "Forking upstream-org/project" in result.output

    def test_owner_org_passes_org_flag(self, clone_target):
        """--owner with an organisation passes --org to gh."""
        gh_ok = _make_sp_result()
        with (
            patch("livefork.cli._gh_owner_type", return_value="Organization"),
            patch(
                "subprocess.run",
                side_effect=_gh_passthrough_side_effect(gh_ok),
            ) as mock_run,
        ):
            result = runner.invoke(
                app,
                [
                    "create",
                    "upstream-org/project",
                    "--owner",
                    "my-org",
                    "--clone-path",
                    str(clone_target),
                    "--no-init",
                ],
                catch_exceptions=False,
            )
        assert result.exit_code == 0
        # Find the gh repo fork call among all subprocess.run calls
        gh_calls = [
            c for c in mock_run.call_args_list if c[0][0][0] == "gh"
        ]
        assert len(gh_calls) == 1
        gh_args = gh_calls[0][0][0]
        assert "--org" in gh_args
        assert "my-org" in gh_args

    def test_owner_self_skips_org_flag(self, clone_target):
        """--owner with authenticated user's own name skips --org."""
        gh_ok = _make_sp_result()
        with (
            patch("livefork.cli._gh_owner_type", return_value="User"),
            patch("livefork.cli._gh_authenticated_user", return_value="akaihola"),
            patch(
                "subprocess.run",
                side_effect=_gh_passthrough_side_effect(gh_ok),
            ) as mock_run,
        ):
            result = runner.invoke(
                app,
                [
                    "create",
                    "upstream-org/project",
                    "--owner",
                    "akaihola",
                    "--clone-path",
                    str(clone_target),
                    "--no-init",
                ],
                catch_exceptions=False,
            )
        assert result.exit_code == 0
        gh_calls = [
            c for c in mock_run.call_args_list if c[0][0][0] == "gh"
        ]
        assert len(gh_calls) == 1
        gh_args = gh_calls[0][0][0]
        assert "--org" not in gh_args

    def test_owner_different_user_errors(self):
        """--owner with a different user's name gives a clear error."""
        with (
            patch("livefork.cli._gh_owner_type", return_value="User"),
            patch("livefork.cli._gh_authenticated_user", return_value="akaihola"),
        ):
            result = runner.invoke(
                app,
                [
                    "create",
                    "upstream-org/project",
                    "--owner",
                    "someone-else",
                    "--no-init",
                ],
            )
        assert result.exit_code != 0
        assert "Cannot fork to another user's account" in result.output

    def test_owner_case_insensitive(self, clone_target):
        """--owner matching is case-insensitive."""
        gh_ok = _make_sp_result()
        with (
            patch("livefork.cli._gh_owner_type", return_value="User"),
            patch("livefork.cli._gh_authenticated_user", return_value="AkaiHola"),
            patch(
                "subprocess.run",
                side_effect=_gh_passthrough_side_effect(gh_ok),
            ),
        ):
            result = runner.invoke(
                app,
                [
                    "create",
                    "upstream-org/project",
                    "--owner",
                    "akaihola",
                    "--clone-path",
                    str(clone_target),
                    "--no-init",
                ],
                catch_exceptions=False,
            )
        assert result.exit_code == 0

    def test_owner_unknown_passes_through(self, clone_target):
        """When API lookup fails, --owner value is passed as --org to gh."""
        gh_ok = _make_sp_result()
        with (
            patch("livefork.cli._gh_owner_type", return_value="unknown"),
            patch(
                "subprocess.run",
                side_effect=_gh_passthrough_side_effect(gh_ok),
            ) as mock_run,
        ):
            result = runner.invoke(
                app,
                [
                    "create",
                    "upstream-org/project",
                    "--owner",
                    "mystery",
                    "--clone-path",
                    str(clone_target),
                    "--no-init",
                ],
                catch_exceptions=False,
            )
        assert result.exit_code == 0
        gh_calls = [
            c for c in mock_run.call_args_list if c[0][0][0] == "gh"
        ]
        gh_args = gh_calls[0][0][0]
        assert "--org" in gh_args
        assert "mystery" in gh_args

    def test_no_owner_skips_org_flag(self, clone_target):
        """Without --owner, no --org flag is passed to gh."""
        gh_ok = _make_sp_result()
        with (
            patch("livefork.cli._gh_authenticated_user", return_value="octocat"),
            patch(
                "subprocess.run",
                side_effect=_gh_passthrough_side_effect(gh_ok),
            ) as mock_run,
        ):
            result = runner.invoke(
                app,
                [
                    "create",
                    "upstream-org/project",
                    "--clone-path",
                    str(clone_target),
                    "--no-init",
                ],
                catch_exceptions=False,
            )
        assert result.exit_code == 0
        gh_calls = [
            c for c in mock_run.call_args_list if c[0][0][0] == "gh"
        ]
        gh_args = gh_calls[0][0][0]
        assert "--org" not in gh_args

    def test_fork_name_passed_through(self, clone_target):
        """--fork-name is forwarded to gh repo fork."""
        gh_ok = _make_sp_result()
        with (
            patch("livefork.cli._gh_authenticated_user", return_value="octocat"),
            patch(
                "subprocess.run",
                side_effect=_gh_passthrough_side_effect(gh_ok),
            ) as mock_run,
        ):
            result = runner.invoke(
                app,
                [
                    "create",
                    "upstream-org/project",
                    "--fork-name",
                    "my-fork",
                    "--clone-path",
                    str(clone_target),
                    "--no-init",
                ],
                catch_exceptions=False,
            )
        assert result.exit_code == 0
        gh_calls = [
            c for c in mock_run.call_args_list if c[0][0][0] == "gh"
        ]
        gh_args = gh_calls[0][0][0]
        assert "--fork-name" in gh_args
        assert "my-fork" in gh_args

    def test_clone_path_dot_reuses_current_repo_and_runs_init(self, clone_target):
        """--clone-path . reuses the current repo instead of requiring --no-init."""
        gh_ok = _make_sp_result()
        with (
            patch("livefork.cli._gh_authenticated_user", return_value="octocat"),
            patch(
                "subprocess.run",
                side_effect=_gh_passthrough_side_effect(gh_ok),
            ) as mock_run,
            patch("livefork.cli.init") as mock_init,
        ):
            result = runner.invoke(
                app,
                [
                    "create",
                    "upstream-org/project",
                    "--clone-path",
                    ".",
                ],
                catch_exceptions=False,
                env={"PWD": str(clone_target)},
            )
        assert result.exit_code == 0
        mock_init.assert_called_once_with(merge_branch=None)
        gh_calls = [
            c for c in mock_run.call_args_list if c[0][0][0] == "gh"
        ]
        gh_args = gh_calls[0][0][0]
        assert "--clone" not in gh_args
        assert result.output.splitlines()[1] == f"Using existing clone at {clone_target}"
        git_result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=clone_target,
            capture_output=True,
            text=True,
            check=True,
        )
        assert "octocat" in git_result.stdout

    def test_existing_matching_repo_reuses_clone_without_clone_path(self, clone_target):
        """Current repo is reused automatically when it already matches the upstream slug."""
        gh_ok = _make_sp_result()
        with (
            patch("livefork.cli._gh_authenticated_user", return_value="octocat"),
            patch(
                "subprocess.run",
                side_effect=_gh_passthrough_side_effect(gh_ok),
            ) as mock_run,
            patch("livefork.cli.init") as mock_init,
        ):
            result = runner.invoke(
                app,
                ["create", "upstream-org/project"],
                catch_exceptions=False,
                env={"PWD": str(clone_target)},
            )
        assert result.exit_code == 0
        mock_init.assert_called_once_with(merge_branch=None)
        gh_calls = [
            c for c in mock_run.call_args_list if c[0][0][0] == "gh"
        ]
        gh_args = gh_calls[0][0][0]
        assert "--clone" not in gh_args
        assert result.output.splitlines()[1] == f"Using existing clone at {clone_target}"

    def test_gh_fork_failure_reports_error(self):
        """When gh repo fork fails, stderr is reported."""
        gh_fail = _make_sp_result(returncode=1, stderr="HTTP 404: Not Found")
        with (
            patch("livefork.cli._gh_authenticated_user", return_value="testuser"),
            patch(
                "subprocess.run",
                side_effect=_gh_passthrough_side_effect(gh_fail),
            ),
        ):
            result = runner.invoke(
                app,
                [
                    "create",
                    "nonexistent/repo",
                    "--no-init",
                ],
            )
        assert result.exit_code != 0
        assert "gh error" in result.output
        assert "404" in result.output

    def test_remote_url_uses_fork_owner(self, clone_target):
        """The fork remote URL is constructed using fork_owner, not getpass.getuser()."""
        gh_ok = _make_sp_result()
        with (
            patch("livefork.cli._gh_authenticated_user", return_value="ghuser"),
            patch(
                "subprocess.run",
                side_effect=_gh_passthrough_side_effect(gh_ok),
            ),
        ):
            result = runner.invoke(
                app,
                [
                    "create",
                    "upstream-org/project",
                    "--clone-path",
                    str(clone_target),
                    "--no-init",
                ],
                catch_exceptions=False,
            )
        assert result.exit_code == 0
        # The origin remote was renamed to upstream; the new origin uses fork_owner
        git_result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=clone_target,
            capture_output=True,
            text=True,
        )
        assert "ghuser" in git_result.stdout
