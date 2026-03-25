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


class TestStatusAfterSync:
    """Status should report 'rebased' for all topic branches after a successful sync."""

    @pytest.fixture()
    def synced_fork(self, tmp_path):
        """Run a full sync (with README enabled) and return the fork path."""
        upstream = tmp_path / "upstream"
        upstream.mkdir()
        _git(upstream, "init", "-b", "main")
        _git(upstream, "config", "user.email", "u@u.com")
        _git(upstream, "config", "user.name", "U")
        _commit(upstream, "initial", "base.txt")

        fork = tmp_path / "fork"
        subprocess.run(
            ["git", "clone", str(upstream), str(fork)],
            check=True,
            capture_output=True,
        )
        _git(fork, "config", "user.email", "me@me.com")
        _git(fork, "config", "user.name", "Me")
        _git(fork, "remote", "rename", "origin", "upstream")

        # bare origin for push
        origin = tmp_path / "origin.git"
        origin.mkdir()
        _git(origin, "init", "--bare", "-b", "main")
        _git(fork, "remote", "add", "origin", str(origin))

        # two topic branches
        _git(fork, "checkout", "-b", "feature/alpha")
        _commit(fork, "alpha work", "alpha.txt")
        _git(fork, "checkout", "main")
        _git(fork, "checkout", "-b", "feature/beta")
        _commit(fork, "beta work", "beta.txt")
        _git(fork, "checkout", "main")

        # upstream advances
        _commit(upstream, "upstream advance", "up.txt")

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
enabled = true
push = false

[[branches]]
name = "feature/alpha"
description = "Alpha"

[[branches]]
name = "feature/beta"
description = "Beta"
"""
        (fork / ".livefork.toml").write_text(config_toml)

        from livefork.git import GitRepo
        from livefork.knit import KnitBridge
        from livefork.sync import SyncOptions, SyncOrchestrator
        from livefork.config import load_config

        cfg = load_config(fork / ".livefork.toml")
        git = GitRepo(fork)
        knit = KnitBridge(fork)
        knit.init_knit("johndoe", "main", ["feature/alpha", "feature/beta"])
        orch = SyncOrchestrator(cfg, git, knit, fork)
        rc = orch.run(SyncOptions(no_push=True))
        assert rc == 0
        return fork

    def test_status_shows_rebased_after_sync_with_readme(self, synced_fork):
        """After sync (which adds a README commit to fork/main), status must
        report '✓ rebased' for every topic branch – not '✗ needs rebase'."""
        result = runner.invoke(
            app,
            ["status"],
            catch_exceptions=False,
            env={"PWD": str(synced_fork)},
        )
        assert result.exit_code == 0
        assert "✗ needs rebase" not in result.output
        assert "✓ rebased" in result.output

    def test_status_shows_needs_rebase_when_behind(self, synced_fork):
        """A topic branch that is genuinely behind upstream shows '✗ needs rebase'."""
        # Create a new commit on upstream, fetch it, advance fork/main,
        # but do NOT rebase the topic branches.
        upstream_url = subprocess.run(
            ["git", "remote", "get-url", "upstream"],
            cwd=synced_fork,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        _commit(Path(upstream_url), "another upstream advance", "up2.txt")
        _git(synced_fork, "fetch", "upstream")
        _git(synced_fork, "checkout", "main")
        _git(synced_fork, "reset", "--hard", "upstream/main")

        result = runner.invoke(
            app,
            ["status"],
            catch_exceptions=False,
            env={"PWD": str(synced_fork)},
        )
        assert result.exit_code == 0
        assert "✗ needs rebase" in result.output

    def test_status_rebased_after_sync_without_readme(self, tmp_path):
        """Status reports '✓ rebased' after sync with README disabled too."""
        upstream = tmp_path / "upstream"
        upstream.mkdir()
        _git(upstream, "init", "-b", "main")
        _git(upstream, "config", "user.email", "u@u.com")
        _git(upstream, "config", "user.name", "U")
        _commit(upstream, "initial", "base.txt")

        fork = tmp_path / "fork"
        subprocess.run(
            ["git", "clone", str(upstream), str(fork)],
            check=True,
            capture_output=True,
        )
        _git(fork, "config", "user.email", "me@me.com")
        _git(fork, "config", "user.name", "Me")
        _git(fork, "remote", "rename", "origin", "upstream")

        origin = tmp_path / "origin.git"
        origin.mkdir()
        _git(origin, "init", "--bare", "-b", "main")
        _git(fork, "remote", "add", "origin", str(origin))

        _git(fork, "checkout", "-b", "feature/solo")
        _commit(fork, "solo work", "solo.txt")
        _git(fork, "checkout", "main")

        _commit(upstream, "upstream advance", "up.txt")

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
name = "feature/solo"
description = "Solo"
"""
        (fork / ".livefork.toml").write_text(config_toml)

        from livefork.git import GitRepo
        from livefork.knit import KnitBridge
        from livefork.sync import SyncOptions, SyncOrchestrator
        from livefork.config import load_config

        cfg = load_config(fork / ".livefork.toml")
        git = GitRepo(fork)
        knit = KnitBridge(fork)
        knit.init_knit("johndoe", "main", ["feature/solo"])
        orch = SyncOrchestrator(cfg, git, knit, fork)
        rc = orch.run(SyncOptions(no_readme=True))
        assert rc == 0

        result = runner.invoke(
            app,
            ["status"],
            catch_exceptions=False,
            env={"PWD": str(fork)},
        )
        assert result.exit_code == 0
        assert "✗ needs rebase" not in result.output
        assert "✓ rebased" in result.output

    def test_status_per_branch_after_partial_rebase(self, tmp_path):
        """When only one branch is rebased via --branch, status correctly shows
        mixed state: rebased for the synced branch, needs-rebase for the other."""
        upstream = tmp_path / "upstream"
        upstream.mkdir()
        _git(upstream, "init", "-b", "main")
        _git(upstream, "config", "user.email", "u@u.com")
        _git(upstream, "config", "user.name", "U")
        _commit(upstream, "initial", "base.txt")

        fork = tmp_path / "fork"
        subprocess.run(
            ["git", "clone", str(upstream), str(fork)],
            check=True,
            capture_output=True,
        )
        _git(fork, "config", "user.email", "me@me.com")
        _git(fork, "config", "user.name", "Me")
        _git(fork, "remote", "rename", "origin", "upstream")

        origin = tmp_path / "origin.git"
        origin.mkdir()
        _git(origin, "init", "--bare", "-b", "main")
        _git(fork, "remote", "add", "origin", str(origin))

        _git(fork, "checkout", "-b", "feature/one")
        _commit(fork, "one work", "one.txt")
        _git(fork, "checkout", "main")
        _git(fork, "checkout", "-b", "feature/two")
        _commit(fork, "two work", "two.txt")
        _git(fork, "checkout", "main")

        _commit(upstream, "upstream advance", "up.txt")

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
name = "feature/one"
description = "One"

[[branches]]
name = "feature/two"
description = "Two"
"""
        (fork / ".livefork.toml").write_text(config_toml)

        from livefork.git import GitRepo
        from livefork.knit import KnitBridge
        from livefork.sync import SyncOptions, SyncOrchestrator
        from livefork.config import load_config

        cfg = load_config(fork / ".livefork.toml")
        git = GitRepo(fork)
        knit = KnitBridge(fork)
        knit.init_knit("johndoe", "main", ["feature/one", "feature/two"])
        orch = SyncOrchestrator(cfg, git, knit, fork)
        # Only rebase feature/one
        rc = orch.run(SyncOptions(no_readme=True, branch="feature/one"))
        assert rc == 0

        result = runner.invoke(
            app,
            ["status"],
            catch_exceptions=False,
            env={"PWD": str(fork)},
        )
        assert result.exit_code == 0
        # feature/one should be rebased, feature/two should need rebase
        for line in result.output.splitlines():
            if "feature/one" in line:
                assert "✓ rebased" in line
            if "feature/two" in line:
                assert "✗ needs rebase" in line


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
