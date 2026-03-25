"""livefork CLI – all commands."""

from __future__ import annotations

import getpass
import os
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer

app = typer.Typer(
    name="livefork",
    help="Keep your personal fork alive.",
    no_args_is_help=True,
)


# ------------------------------------------------------------------ helpers


def _repo_root() -> Path:
    """Return cwd (Typer tests set PWD; real use sets cwd)."""
    return Path(os.environ.get("PWD", ".")).resolve()


def _config_path(root: Path) -> Path:
    return root / ".livefork.toml"


def _require_config(root: Path):
    from livefork.config import load_config

    p = _config_path(root)
    if not p.exists():
        typer.echo(
            f"Error: no .livefork.toml found in {root}. Run 'livefork init' first.",
            err=True,
        )
        raise typer.Exit(1)
    return load_config(p)


def _make_git(root: Path):
    from livefork.git import GitRepo

    return GitRepo(root)


def _make_knit(root: Path):
    from livefork.knit import KnitBridge

    return KnitBridge(root)


# ------------------------------------------------------------------ --version


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: Annotated[
        bool, typer.Option("--version", "-V", help="Print version and exit.")
    ] = False,
) -> None:
    if version:
        from livefork import __version__

        typer.echo(f"livefork {__version__}")
        raise typer.Exit()


# ------------------------------------------------------------------ init


@app.command()
def init(
    upstream: Annotated[
        Optional[str],
        typer.Option(help="Upstream remote URL (prompted if needed)."),
    ] = None,
    merge_branch: Annotated[
        Optional[str],
        typer.Option("--merge-branch", help="Override merge branch name."),
    ] = None,
) -> None:
    """Configure an existing fork clone and initialise the merge branch."""
    from livefork.config import (
        auto_detect_branches,
        find_config,
        load_config,
        save_config,
        LiveforkConfig,
        UpstreamConfig,
        ForkConfig,
        KnitSectionConfig,
        ForkReadmeConfig,
    )

    root = _repo_root()
    config_file = _config_path(root)
    git = _make_git(root)
    knit = _make_knit(root)

    git.enable_rerere()

    # If config exists, load it; otherwise build defaults
    if config_file.exists():
        cfg = load_config(config_file)
        typer.echo("Found existing .livefork.toml – updating.")
    else:
        knit_branch = merge_branch or getpass.getuser()
        cfg = LiveforkConfig(
            upstream=UpstreamConfig(),
            fork=ForkConfig(),
            knit=KnitSectionConfig(branch=knit_branch),
            fork_readme=ForkReadmeConfig(),
        )
        typer.echo("Creating .livefork.toml.")

    # Auto-detect branches if none configured
    if not cfg.branches:
        detected = auto_detect_branches(root)
        cfg.branches = detected
        typer.echo(f"Auto-detected {len(detected)} branch(es).")

    save_config(cfg, config_file)
    typer.echo(f"Wrote {config_file}")

    # Initialise git-knit if not already done
    branch_names = [b.name for b in cfg.branches]
    if not knit.is_initialized(cfg.knit.branch):
        typer.echo(f"Initialising git-knit merge branch '{cfg.knit.branch}'...")
        knit.init_knit(cfg.knit.branch, cfg.knit.base, branch_names)
        knit.rebuild(cfg.knit.branch)
    else:
        typer.echo(f"git-knit already initialised for '{cfg.knit.branch}'.")

    typer.echo("✓ livefork initialised.")


# ------------------------------------------------------------------ status


@app.command()
def status() -> None:
    """Show branch sync state and PR status."""
    import subprocess

    root = _repo_root()
    cfg = _require_config(root)
    git = _make_git(root)
    knit = _make_knit(root)

    def sha_short(ref: str) -> str:
        try:
            return git.get_commit_sha(ref, short=True)
        except Exception:
            return "???????"

    upstream_ref = f"{cfg.upstream.remote}/{cfg.upstream.branch}"
    fork_ref = cfg.fork.branch

    typer.echo(f"upstream/{cfg.upstream.branch}  {sha_short(upstream_ref)}")
    typer.echo(f"fork/{cfg.fork.branch}     {sha_short(fork_ref)}")
    typer.echo("")
    typer.echo("TOPIC BRANCHES")

    for b in cfg.branches:
        bsha = sha_short(b.name)
        # Check if rebased (branch is on top of fork main)
        try:
            result = git.run(
                ["merge-base", "--is-ancestor", fork_ref, b.name], check=False
            )
            rebased = result.returncode == 0
        except Exception:
            rebased = False
        status_sym = "✓ rebased" if rebased else "✗ needs rebase"

        # draft / PR
        draft = ""
        try:
            r = git.run(
                ["cat-file", "-e", f"{b.name}:PULL-REQUEST-DRAFT.md"], check=False
            )
            if r.returncode == 0:
                draft = "  [draft]"
        except Exception:
            pass
        if b.pr:
            import re

            m = re.search(r"/pull/(\d+)", b.pr)
            draft = f"  [PR #{m.group(1)} submitted]" if m else "  [PR submitted]"

        typer.echo(f"  {b.name:<30} {bsha}  {status_sym}{draft}")

    # knit branch
    typer.echo("")
    typer.echo("MERGE BRANCH")
    knit_cfg = knit.get_config(cfg.knit.branch)
    if knit_cfg:
        ksha = sha_short(cfg.knit.branch)
        typer.echo(f"  {cfg.knit.branch:<30} {ksha}  (configured)")
    else:
        typer.echo(f"  {cfg.knit.branch}  (not initialised – run 'livefork init')")


# ------------------------------------------------------------------ add


@app.command()
def add(
    branch: Annotated[str, typer.Argument(help="Topic branch to add.")],
    description: Annotated[Optional[str], typer.Option("--description", "-d")] = None,
) -> None:
    """Add a topic branch to the configuration and merge branch."""
    root = _repo_root()
    cfg = _require_config(root)
    git = _make_git(root)
    knit = _make_knit(root)

    from livefork.config import BranchConfig, save_config

    # Guard: branch must exist
    try:
        git.get_commit_sha(branch)
    except Exception:
        typer.echo(f"Error: branch '{branch}' does not exist.", err=True)
        raise typer.Exit(1)

    if any(b.name == branch for b in cfg.branches):
        typer.echo(f"Branch '{branch}' is already in the config.")
        raise typer.Exit(0)

    cfg.branches.append(BranchConfig(name=branch, description=description or branch))
    save_config(cfg, _config_path(root))
    typer.echo(f"Added '{branch}' to .livefork.toml")

    knit.add_branch(cfg.knit.branch, branch)
    typer.echo(f"✓ '{branch}' added to merge branch '{cfg.knit.branch}'")


# ------------------------------------------------------------------ remove


@app.command()
def remove(
    branch: Annotated[str, typer.Argument(help="Topic branch to remove.")],
) -> None:
    """Remove a topic branch from configuration and merge branch."""
    root = _repo_root()
    cfg = _require_config(root)

    from livefork.config import save_config

    knit = _make_knit(root)

    if not any(b.name == branch for b in cfg.branches):
        typer.echo(f"Branch '{branch}' is not in the config.", err=True)
        raise typer.Exit(1)

    cfg.branches = [b for b in cfg.branches if b.name != branch]
    save_config(cfg, _config_path(root))
    typer.echo(f"Removed '{branch}' from .livefork.toml")

    knit.remove_branch(cfg.knit.branch, branch)
    typer.echo(f"✓ '{branch}' removed from merge branch '{cfg.knit.branch}'")


# ------------------------------------------------------------------ knit


@app.command()
def knit() -> None:
    """Rebuild the merge branch without touching topic branches."""
    root = _repo_root()
    cfg = _require_config(root)
    kb = _make_knit(root)
    typer.echo(f"Rebuilding merge branch '{cfg.knit.branch}'...")
    kb.rebuild(cfg.knit.branch)
    typer.echo("✓ Done.")


# ------------------------------------------------------------------ readme


@app.command()
def readme(
    no_push: Annotated[
        bool, typer.Option("--no-push", help="Regenerate without pushing.")
    ] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Print content without writing.")
    ] = False,
) -> None:
    """Regenerate and push the fork README."""
    root = _repo_root()
    cfg = _require_config(root)
    git = _make_git(root)
    knit = _make_knit(root)

    from livefork.sync import SyncOptions, SyncOrchestrator

    orch = SyncOrchestrator(cfg, git, knit, root)
    orch._step_update_readme(
        SyncOptions(dry_run=dry_run, no_knit=True, no_push=no_push)
    )
    if not dry_run:
        typer.echo("✓ Fork README updated.")


# ------------------------------------------------------------------ sync


@app.command()
def sync(
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    branch: Annotated[
        Optional[str], typer.Option("--branch", help="Rebase one branch only.")
    ] = None,
    no_knit: Annotated[bool, typer.Option("--no-knit")] = False,
    no_readme: Annotated[bool, typer.Option("--no-readme")] = False,
) -> None:
    """Fetch upstream · rebase all branches · rebuild merge branch · push fork README."""
    root = _repo_root()
    cfg = _require_config(root)
    git = _make_git(root)
    knit = _make_knit(root)

    from livefork.sync import SyncOptions, SyncOrchestrator, SyncError

    options = SyncOptions(
        dry_run=dry_run, branch=branch, no_knit=no_knit, no_readme=no_readme
    )
    orch = SyncOrchestrator(cfg, git, knit, root)
    try:
        rc = orch.run(options)
    except SyncError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    if rc != 0:
        raise typer.Exit(rc)
    typer.echo("✓ Sync complete.")


# ------------------------------------------------------------------ continue


@app.command(name="continue")
def continue_sync() -> None:
    """Resume a paused sync after resolving a conflict."""
    root = _repo_root()
    cfg = _require_config(root)
    git = _make_git(root)
    knit = _make_knit(root)

    from livefork.sync import SyncOrchestrator, SyncError, ConflictPause

    orch = SyncOrchestrator(cfg, git, knit, root)
    try:
        rc = orch.continue_sync()
    except SyncError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except ConflictPause as e:
        orch._print_conflict_message(e.branch, e.conflicting_files)
        raise typer.Exit(1)
    if rc != 0:
        raise typer.Exit(rc)
    typer.echo("✓ Sync complete.")


# ------------------------------------------------------------------ abort


@app.command()
def abort() -> None:
    """Abort a paused sync and restore all branches to pre-sync state."""
    root = _repo_root()
    cfg = _require_config(root)
    git = _make_git(root)
    knit = _make_knit(root)

    from livefork.sync import SyncOrchestrator, SyncError

    orch = SyncOrchestrator(cfg, git, knit, root)
    try:
        orch.abort_sync()
    except SyncError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    typer.echo("✓ Sync aborted. All branches restored.")


# ------------------------------------------------------------------ agent-context


@app.command(name="agent-context")
def agent_context() -> None:
    """Print a structured Markdown conflict report for a coding AI assistant."""
    root = _repo_root()
    cfg = _require_config(root)
    git = _make_git(root)

    from livefork.state import load_state
    from livefork.agent_context import generate_agent_context

    state = load_state(root / ".git")
    if state is None:
        typer.echo("Error: no sync in progress.", err=True)
        raise typer.Exit(1)

    try:
        doc = generate_agent_context(cfg, git, state)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    typer.echo(doc)


# ------------------------------------------------------------------ draft


@app.command()
def draft(
    branch: Annotated[str, typer.Argument(help="Branch to create/edit draft for.")],
    message: Annotated[
        Optional[str], typer.Option("--message", "-m", help="Set title line.")
    ] = None,
) -> None:
    """Create or edit PULL-REQUEST-DRAFT.md on a branch."""
    import subprocess

    root = _repo_root()
    cfg = _require_config(root)
    git = _make_git(root)

    git.checkout(branch)
    draft_file = root / "PULL-REQUEST-DRAFT.md"
    if not draft_file.exists():
        draft_file.write_text(
            f"{message or branch}\n\nDescribe the purpose of this PR.\n"
        )

    if message and draft_file.exists():
        lines = draft_file.read_text().splitlines()
        if lines:
            lines[0] = message
            draft_file.write_text("\n".join(lines) + "\n")

    editor = os.environ.get("EDITOR", "vi")
    subprocess.run([editor, str(draft_file)])

    # Commit only if changed
    result = git.run(["diff", "--quiet", "PULL-REQUEST-DRAFT.md"], check=False)
    if result.returncode != 0 or not (
        subprocess.run(
            ["git", "ls-files", "--error-unmatch", "PULL-REQUEST-DRAFT.md"],
            cwd=root,
            capture_output=True,
        ).returncode
        == 0
    ):
        git.add(["PULL-REQUEST-DRAFT.md"])
        git.commit("docs: update PULL-REQUEST-DRAFT.md")
        typer.echo("✓ Draft committed.")
    else:
        typer.echo("No changes to draft.")

    git.checkout(cfg.fork.branch)


# ------------------------------------------------------------------ pr create (requires gh)


@app.command(name="pr")
def pr_create(
    branch: Annotated[str, typer.Argument(help="Branch to submit PR for.")],
    base: Annotated[
        Optional[str], typer.Option("--base", help="Target branch on upstream.")
    ] = None,
    draft_pr: Annotated[
        bool, typer.Option("--draft", help="Open as a draft PR.")
    ] = False,
) -> None:
    """Submit a PR from PULL-REQUEST-DRAFT.md (requires gh CLI)."""
    import re
    import subprocess as sp

    root = _repo_root()
    cfg = _require_config(root)
    git = _make_git(root)

    from livefork.config import save_config

    git.checkout(branch)
    draft_file = root / "PULL-REQUEST-DRAFT.md"
    if not draft_file.exists():
        typer.echo(f"Error: PULL-REQUEST-DRAFT.md not found on {branch}.", err=True)
        raise typer.Exit(1)

    text = draft_file.read_text()
    lines = text.splitlines()
    title = lines[0].strip()
    body = "\n".join(lines[2:]).strip() if len(lines) > 2 else ""

    upstream_base = base or cfg.upstream.branch
    gh_args = [
        "gh",
        "pr",
        "create",
        "--title",
        title,
        "--body",
        body,
        "--base",
        upstream_base,
        "--repo",
        _upstream_github_slug(git, cfg),
    ]
    if draft_pr:
        gh_args.append("--draft")

    result = sp.run(gh_args, capture_output=True, text=True)
    if result.returncode != 0:
        typer.echo(f"gh error: {result.stderr}", err=True)
        raise typer.Exit(1)

    pr_url = result.stdout.strip()
    typer.echo(f"PR created: {pr_url}")

    # Record URL in config
    for b in cfg.branches:
        if b.name == branch:
            b.pr = pr_url
    save_config(cfg, _config_path(root))

    # Remove draft file and commit
    draft_file.unlink()
    git.add(["."])
    git.commit("chore: remove PULL-REQUEST-DRAFT.md after PR creation")

    git.checkout(cfg.fork.branch)
    typer.echo("✓ PR submitted, config updated, draft removed.")


def _upstream_github_slug(git, cfg) -> str:
    """Return 'owner/repo' from the upstream remote URL."""
    import re

    url = git.get_remote_url(cfg.upstream.remote) or ""
    m = re.search(r"github\.com[:/](.+?)(?:\.git)?$", url)
    return m.group(1) if m else url


# ------------------------------------------------------------------ create (requires gh)


def _gh_owner_type(owner: str) -> str:
    """Return ``"Organization"`` or ``"User"`` for a GitHub account name.

    Falls back to ``"unknown"`` if the API call fails.
    """
    import subprocess as sp

    result = sp.run(
        ["gh", "api", f"users/{owner}", "--jq", ".type"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return result.stdout.strip()
    return "unknown"


def _gh_authenticated_user() -> str:
    """Return the login name of the currently authenticated ``gh`` user."""
    import subprocess as sp

    result = sp.run(
        ["gh", "api", "user", "--jq", ".login"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    # Last resort – OS username (may differ from GitHub login)
    return getpass.getuser()


@app.command()
def create(
    repo: Annotated[str, typer.Argument(help="Upstream repo (owner/name or URL).")],
    fork_name: Annotated[Optional[str], typer.Option("--fork-name")] = None,
    owner: Annotated[
        Optional[str],
        typer.Option(
            "--owner",
            help=(
                "GitHub user or organisation to own the fork. "
                "Defaults to the authenticated user."
            ),
        ),
    ] = None,
    clone_path: Annotated[Optional[str], typer.Option("--clone-path")] = None,
    upstream_remote: Annotated[str, typer.Option("--upstream-remote")] = "upstream",
    fork_remote: Annotated[str, typer.Option("--fork-remote")] = "origin",
    merge_branch: Annotated[Optional[str], typer.Option("--merge-branch")] = None,
    no_init: Annotated[bool, typer.Option("--no-init")] = False,
) -> None:
    """Fork a GitHub repository, clone, configure, and initialise in one step (requires gh)."""
    import subprocess as sp

    # Normalise repo slug
    if repo.startswith("https://github.com/"):
        slug = repo.removeprefix("https://github.com/").removesuffix(".git")
    else:
        slug = repo

    repo_name = slug.split("/")[-1]
    local_path = Path(clone_path or f"./{repo_name}").resolve()

    gh_args = ["gh", "repo", "fork", slug, "--clone"]
    if fork_name:
        gh_args += ["--fork-name", fork_name]

    # Determine the actual fork owner for remote URL construction
    if owner:
        owner_type = _gh_owner_type(owner)
        if owner_type == "Organization":
            gh_args += ["--org", owner]
        elif owner_type == "User":
            # gh fork to your own account is the default – only need --org for
            # orgs.  Verify the target is the authenticated user; forking to a
            # *different* user's account is not supported by GitHub.
            authed = _gh_authenticated_user()
            if owner.lower() != authed.lower():
                typer.echo(
                    f"Cannot fork to another user's account ({owner!r}). "
                    f"You are authenticated as {authed!r}. "
                    "Use --owner with an organisation name, or omit it to fork "
                    "to your own account.",
                    err=True,
                )
                raise typer.Exit(1)
            # target is the authenticated user – no extra flag needed
        else:
            # API lookup failed; pass through to gh and let it report errors
            gh_args += ["--org", owner]
        fork_owner = owner
    else:
        fork_owner = _gh_authenticated_user()

    typer.echo(f"Forking {slug} with gh...")
    result = sp.run(gh_args, capture_output=True, text=True)
    if result.returncode != 0:
        typer.echo(f"gh error: {result.stderr}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Cloned to {local_path}")

    # Rename origin → upstream, set upstream-remote
    git = _make_git(local_path)
    origin_url = git.get_remote_url("origin") or ""
    git.run(["remote", "rename", "origin", upstream_remote])
    git.run(
        [
            "remote",
            "add",
            fork_remote,
            origin_url.replace(slug.split("/")[0] + "/", f"{fork_owner}/"),
        ]
    )

    if not no_init:
        os.environ["PWD"] = str(local_path)
        init(merge_branch=merge_branch)


if __name__ == "__main__":
    app()
