"""Sync workflow orchestration for livefork."""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from pathlib import Path

from livefork.config import LiveforkConfig
from livefork.git import GitError, GitRepo, RebaseResult, normalize_github_url
from livefork.knit import KnitBridge
from livefork.state import SyncState, delete_state, load_state, save_state


class SyncError(Exception):
    """Raised for unrecoverable sync errors (not conflict pauses)."""


class ConflictPause(Exception):
    """Raised when a rebase conflict requires user intervention."""

    def __init__(self, branch: str, conflicting_files: list[str]):
        super().__init__(f"Conflict on {branch}")
        self.branch = branch
        self.conflicting_files = conflicting_files


@dataclass
class SyncOptions:
    dry_run: bool = False
    branch: str | None = None  # rebase only this branch
    no_knit: bool = False
    no_readme: bool = False
    no_push: bool = False


class SyncOrchestrator:
    """Executes the five-step sync workflow with state persistence."""

    def __init__(
        self,
        config: LiveforkConfig,
        git: GitRepo,
        knit: KnitBridge,
        repo_root: Path,
    ):
        self.config = config
        self.git = git
        self.knit = knit
        self.repo_root = Path(repo_root)
        self.git_dir = self.repo_root / ".git"

    # ------------------------------------------------------------------

    def run(self, options: SyncOptions = SyncOptions()) -> int:  # noqa: B008
        """Run a full sync. Returns 0 on success, 1 if paused on conflict."""
        if load_state(self.git_dir) is not None:
            raise SyncError(
                "A sync is already in progress. "
                "Use 'livefork continue' or 'livefork abort'."
            )

        pre_shas: dict[str, str] = {}
        for b in self.config.branches:
            try:
                pre_shas[b.name] = self.git.get_commit_sha(b.name)
            except Exception:
                pre_shas[b.name] = ""

        state = SyncState(
            step=1, branch_index=0, branch_pre_sync_shas=pre_shas, paused_branch=None
        )
        save_state(state, self.git_dir)

        try:
            return self._execute(state, options)
        except ConflictPause as e:
            self._print_conflict_message(e.branch, e.conflicting_files)
            return 1

    def continue_sync(self) -> int:
        """Resume after manual conflict resolution."""
        state = load_state(self.git_dir)
        if state is None:
            raise SyncError("No sync in progress.")

        if not self.git.is_in_rebase():
            raise SyncError("No rebase is in progress – check 'git status'.")

        result = self.git.rebase_continue()
        if not result.success:
            raise ConflictPause(state.paused_branch or "?", result.conflicting_files)

        state.branch_index += 1
        state.paused_branch = None
        save_state(state, self.git_dir)

        try:
            return self._execute(state, SyncOptions())
        except ConflictPause as e:
            self._print_conflict_message(e.branch, e.conflicting_files)
            return 1

    def abort_sync(self) -> int:
        """Abort sync and reset all branches to pre-sync state."""
        state = load_state(self.git_dir)
        if state is None:
            raise SyncError("No sync in progress.")

        if self.git.is_in_rebase():
            self.git.rebase_abort()

        for i, branch in enumerate(self.config.branches):
            if i < state.branch_index:
                sha = state.branch_pre_sync_shas.get(branch.name, "")
                if sha:
                    self.git.run(["branch", "-f", branch.name, sha])

        delete_state(self.git_dir)
        return 0

    # ------------------------------------------------------------------ steps

    def _execute(self, state: SyncState, options: SyncOptions) -> int:
        """Drive remaining steps from the current state."""
        if state.step <= 1:
            self._step_fetch(options)
            state.step = 2
            save_state(state, self.git_dir)

        if state.step <= 2:
            self._step_advance_fork_main(options)
            state.step = 3
            save_state(state, self.git_dir)

        if state.step <= 3:
            branches = self.config.branches
            if options.branch:
                branches = [b for b in branches if b.name == options.branch]

            for i in range(state.branch_index, len(branches)):
                branch = branches[i]
                result = self._step_rebase(branch.name, options)
                if not result.success:
                    state.branch_index = i
                    state.paused_branch = branch.name
                    save_state(state, self.git_dir)
                    raise ConflictPause(branch.name, result.conflicting_files)
                state.branch_index = i + 1
                save_state(state, self.git_dir)

            state.step = 4
            save_state(state, self.git_dir)

        if state.step <= 4 and not options.no_knit:
            self._step_rebuild_knit(options)
            state.step = 5
            save_state(state, self.git_dir)

        if state.step <= 5 and not options.no_readme:
            self._step_update_readme(options)

        delete_state(self.git_dir)
        return 0

    def _step_fetch(self, options: SyncOptions) -> None:
        if options.dry_run:
            print(f"[dry-run] git fetch {self.config.upstream.remote}")
            return
        self.git.fetch(self.config.upstream.remote)

    def _step_advance_fork_main(self, options: SyncOptions) -> None:
        ref = f"{self.config.upstream.remote}/{self.config.upstream.branch}"
        if options.dry_run:
            print(f"[dry-run] Reset {self.config.fork.branch} → {ref}")
            return
        self.git.checkout(self.config.fork.branch)
        self.git.reset_hard(ref)

    def _step_rebase(self, branch_name: str, options: SyncOptions) -> RebaseResult:
        if options.dry_run:
            print(f"[dry-run] Rebase {branch_name} onto {self.config.fork.branch}")
            return RebaseResult(success=True)
        return self.git.rebase(self.config.fork.branch, branch=branch_name)

    def _step_rebuild_knit(self, options: SyncOptions) -> None:
        if options.dry_run:
            print(f"[dry-run] Rebuild knit branch {self.config.knit.branch}")
            return
        self.knit.rebuild(self.config.knit.branch)

    def _step_update_readme(self, options: SyncOptions) -> None:
        if not self.config.fork_readme.enabled:
            return
        from livefork.readme import generate_readme

        upstream_ref = f"{self.config.upstream.remote}/{self.config.upstream.branch}"
        try:
            upstream_sha = self.git.get_commit_sha(upstream_ref, short=True)
        except GitError:
            print(
                f"[warn] Could not resolve {upstream_ref!r} – "
                "upstream not fetched? Using 'unknown' as SHA."
            )
            upstream_sha = "unknown"
        upstream_url = self.git.get_remote_url(self.config.upstream.remote) or ""
        fork_url = self.git.get_remote_url(self.config.fork.remote) or ""
        upstream_url = normalize_github_url(upstream_url) if upstream_url else ""
        fork_url = normalize_github_url(fork_url) if fork_url else ""

        errors = []
        if not upstream_url:
            errors.append(
                f"Cannot resolve upstream remote URL"
                f" (remote {self.config.upstream.remote!r} not found)."
            )
        if not fork_url:
            errors.append(
                f"Cannot resolve fork remote URL"
                f" (remote {self.config.fork.remote!r} not found)."
            )
        if errors:
            import sys

            for e in errors:
                print(f"[error] {e}", file=sys.stderr)
            print(
                "[error] Refusing to generate README with empty URLs.",
                file=sys.stderr,
            )
            raise SystemExit(1)

        # detect draft branches (have PULL-REQUEST-DRAFT.md on their tip)
        draft_branches: set[str] = set()
        for b in self.config.branches:
            result = self.git.run(
                ["cat-file", "-e", f"{b.name}:PULL-REQUEST-DRAFT.md"],
                check=False,
            )
            if result.returncode == 0:
                draft_branches.add(b.name)

        content = generate_readme(
            self.config,
            upstream_sha=upstream_sha,
            upstream_url=upstream_url,
            fork_url=fork_url,
            synced_at=datetime.date.today(),
            draft_branches=draft_branches,
        )

        if options.dry_run:
            print(content)
            return

        readme_file = self.repo_root / self.config.fork_readme.file
        self.git.checkout(self.config.fork.branch)
        readme_file.write_text(content)
        self.git.add([self.config.fork_readme.file])
        self.git.commit("chore: update fork README [skip ci]")
        if self.config.fork_readme.push and not options.no_push:
            self.git.push(
                self.config.fork.remote,
                self.config.fork.branch,
                force_with_lease=True,
            )

    def _print_conflict_message(
        self, branch: str, conflicting_files: list[str]
    ) -> None:
        sep = "━" * 60
        files_str = "\n".join(f"  {f}  (content conflict)" for f in conflicting_files)
        print(
            f"""\
{sep}
⚠  Rebase conflict on {branch}
{sep}

Rebasing: {branch}
     on:  {self.config.fork.branch}

Conflicting files:
{files_str}

To resolve manually:
  1. Open the conflicting file(s) listed above.
  2. Edit, keeping the changes you want.
  3. git add <file> ...
  4. livefork continue

To abort this sync entirely:
  livefork abort

To resolve with a coding agent:
  livefork agent-context > /tmp/conflict.md
  # Hand /tmp/conflict.md to your AI assistant, then run:
  livefork continue
{sep}
"""
        )
