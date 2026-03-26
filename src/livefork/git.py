"""Git subprocess wrapper for livefork operations."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path


class GitError(Exception):
    """Raised when a git command fails unexpectedly."""

    def __init__(self, message: str, returncode: int = 1):
        super().__init__(message)
        self.returncode = returncode


@dataclass
class BranchInfo:
    name: str
    tracking_remote: str | None = None
    tracking_branch: str | None = None


@dataclass
class RebaseResult:
    success: bool
    conflicting_files: list[str] = field(default_factory=list)


class GitRepo:
    """Thin subprocess wrapper for git operations needed by livefork."""

    def __init__(self, cwd: Path):
        self.cwd = Path(cwd)

    # ------------------------------------------------------------------ low-level

    def run(
        self,
        args: list[str],
        *,
        check: bool = True,
        capture: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        """Run `git <args>` in self.cwd. Raises GitError on non-zero exit when check=True."""
        result = subprocess.run(
            ["git"] + args,
            cwd=self.cwd,
            capture_output=capture,
            text=True,
        )
        if check and result.returncode != 0:
            msg = (result.stderr or result.stdout or "").strip()
            raise GitError(
                msg or f"git {args[0]} failed (rc={result.returncode})",
                result.returncode,
            )
        return result

    # ------------------------------------------------------------------ queries

    def get_current_branch(self) -> str:
        return self.run(["rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()

    def get_commit_sha(self, ref: str, *, short: bool = False) -> str:
        args = ["rev-parse"] + (["--short"] if short else []) + [ref]
        return self.run(args).stdout.strip()

    def get_remote_url(self, remote: str) -> str | None:
        result = self.run(["remote", "get-url", remote], check=False)
        return result.stdout.strip() if result.returncode == 0 else None

    def get_branch_tracking(self, branch: str) -> tuple[str, str] | None:
        """Return (remote, remote_branch) or None."""
        r1 = self.run(["config", f"branch.{branch}.remote"], check=False)
        if r1.returncode != 0:
            return None
        remote = r1.stdout.strip()
        r2 = self.run(["config", f"branch.{branch}.merge"], check=False)
        if r2.returncode != 0:
            return None
        merge_ref = r2.stdout.strip()  # e.g. refs/heads/main
        remote_branch = merge_ref.removeprefix("refs/heads/")
        return (remote, remote_branch)

    def list_local_branches(self) -> list[BranchInfo]:
        result = self.run(["branch", "--format=%(refname:short)"])
        infos = []
        for name in result.stdout.splitlines():
            name = name.strip()
            if not name:
                continue
            tracking = self.get_branch_tracking(name)
            if tracking:
                infos.append(BranchInfo(name, tracking[0], tracking[1]))
            else:
                infos.append(BranchInfo(name))
        return infos

    def get_conflicting_files(self) -> list[str]:
        result = self.run(["diff", "--name-only", "--diff-filter=U"], check=False)
        return [f for f in result.stdout.splitlines() if f.strip()]

    def is_in_rebase(self) -> bool:
        return (self.cwd / ".git" / "rebase-merge").exists() or (
            self.cwd / ".git" / "rebase-apply"
        ).exists()

    def get_rebase_stopped_sha(self) -> str | None:
        """Return SHA of the commit that caused the current rebase conflict."""
        stopped = self.cwd / ".git" / "rebase-merge" / "stopped-sha"
        if stopped.exists():
            return stopped.read_text().strip()
        return None

    def get_diff(self, ref: str) -> str:
        """Return `git show` output for a commit."""
        return self.run(["show", "--stat", "-p", ref]).stdout

    def get_range_diff(self, base: str, tip: str) -> str:
        """Return diff of commits between base and tip."""
        return self.run(["log", "-p", f"{base}..{tip}"]).stdout

    def get_merge_base(self, ref1: str, ref2: str) -> str:
        """Return the merge-base SHA between two refs."""
        return self.run(["merge-base", ref1, ref2]).stdout.strip()

    def get_log_messages(self, range_spec: str) -> str:
        """Return ``git log`` with full commit messages for *range_spec*."""
        return self.run(["log", "--format=medium", range_spec]).stdout

    def get_diff_range(self, base: str, tip: str) -> str:
        """Return the combined diff between *base* and *tip*."""
        return self.run(["diff", base, tip]).stdout

    # ------------------------------------------------------------------ mutations

    def checkout(self, branch: str) -> None:
        self.run(["checkout", branch])

    def fetch(self, remote: str) -> None:
        self.run(["fetch", remote])

    def reset_hard(self, ref: str) -> None:
        self.run(["reset", "--hard", ref])

    def rebase(self, onto: str, *, branch: str | None = None) -> RebaseResult:
        """Rebase current branch (or *branch*) onto *onto* with --rebase-merges."""
        if branch is not None:
            self.checkout(branch)
        result = self.run(["rebase", "--rebase-merges", onto], check=False)
        if result.returncode == 0:
            return RebaseResult(success=True)
        return RebaseResult(
            success=False, conflicting_files=self.get_conflicting_files()
        )

    def rebase_continue(self) -> RebaseResult:
        result = self.run(["rebase", "--continue"], check=False)
        if result.returncode == 0:
            return RebaseResult(success=True)
        return RebaseResult(
            success=False, conflicting_files=self.get_conflicting_files()
        )

    def rebase_abort(self) -> None:
        self.run(["rebase", "--abort"])

    def push(self, remote: str, branch: str, *, force_with_lease: bool = False) -> None:
        args = ["push"]
        if force_with_lease:
            args.append("--force-with-lease")
        args += [remote, branch]
        self.run(args)

    def add(self, files: list[str]) -> None:
        self.run(["add"] + files)

    def commit(self, message: str) -> None:
        self.run(["commit", "-m", message])

    def enable_rerere(self) -> None:
        self.run(["config", "rerere.enabled", "true"])

    def set_config(self, key: str, value: str) -> None:
        self.run(["config", key, value])
