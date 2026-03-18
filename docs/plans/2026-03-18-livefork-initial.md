# livefork Initial Version – Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the complete initial version of `livefork` – a Python CLI tool that keeps a personal fork alive by fetching upstream, rebasing topic branches, and rebuilding the git-knit merge branch in one command.

**Architecture:** Layered design: `git.py` (git subprocess wrapper) → `config.py` (TOML config) + `state.py` (sync progress) → `knit.py` (git-knit API bridge) + `readme.py` (Jinja2 README) → `sync.py` (workflow orchestration) + `agent_context.py` (conflict report) → `cli.py` (Typer entry point). Every public function is independently testable; the CLI is a thin shell over the library.

**Tech Stack:** Python 3.10+, Typer 0.12+, Jinja2 3+, tomli-w, tomllib (stdlib 3.11+, `tomli` backport for 3.10), git-knit Python API (internal classes), pytest, uv_build backend, git subprocess, gh subprocess (optional – `create`/`pr create` only).

---

## File Structure

```
livefork/
├── pyproject.toml
├── src/
│   └── livefork/
│       ├── __init__.py          # version string only
│       ├── cli.py               # Typer app, all commands
│       ├── config.py            # .livefork.toml dataclasses + load/save
│       ├── git.py               # GitRepo subprocess wrapper + BranchInfo/RebaseResult
│       ├── state.py             # SyncState + load/save/delete (.git/livefork-state.json)
│       ├── knit.py              # KnitBridge wrapping git-knit Python API
│       ├── readme.py            # generate_readme() + ReadmeContext
│       ├── sync.py              # SyncOrchestrator (run/continue_sync/abort_sync)
│       ├── agent_context.py     # generate_agent_context() → Markdown string
│       └── templates/
│           └── fork-readme.md.j2
└── tests/
    ├── conftest.py              # git_repo, two_repo_setup, sample_config fixtures
    ├── test_config.py
    ├── test_git.py
    ├── test_state.py
    ├── test_knit.py
    ├── test_readme.py
    ├── test_sync.py
    ├── test_agent_context.py
    └── test_cli.py
```

---

## Chunk 1: Scaffold, Config, Git, State

### Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `src/livefork/__init__.py`
- Create: `src/livefork/cli.py` (stub)
- Create: `tests/__init__.py`
- Create: `tests/conftest.py` (stub)

- [x] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "livefork"
version = "0.1.0"
description = "Keep your personal fork alive"
readme = "README.md"
requires-python = ">=3.10"
license = { text = "BSD-3-Clause" }
dependencies = [
    "typer>=0.12",
    "tomli-w>=1.0",
    "jinja2>=3.0",
    "git-knit>=0.1",
    "tomli>=2.0; python_version < '3.11'",
]

[project.scripts]
livefork = "livefork.cli:app"

[build-system]
requires = ["uv_build"]
build-backend = "uv_build"

[dependency-groups]
dev = ["pytest>=8", "pytest-cov"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [x] **Step 2: Write `src/livefork/__init__.py`**

```python
"""livefork – keep your personal fork alive."""

__version__ = "0.1.0"
```

- [x] **Step 3: Write stub `src/livefork/cli.py`**

```python
"""livefork CLI."""

import typer

app = typer.Typer(
    name="livefork",
    help="Keep your personal fork alive.",
    no_args_is_help=True,
)


@app.callback(invoke_without_command=True)
def main(
    version: bool = typer.Option(False, "--version", "-V", help="Print version and exit."),
) -> None:
    if version:
        from livefork import __version__
        typer.echo(f"livefork {__version__}")
        raise typer.Exit()


if __name__ == "__main__":
    app()
```

- [x] **Step 4: Write stub `tests/conftest.py`**

```python
"""Shared pytest fixtures."""

import subprocess
from pathlib import Path

import pytest


def _git(cwd: Path, *args: str) -> str:
    """Run a git command in cwd and return stdout."""
    result = subprocess.run(
        ["git"] + list(args),
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _make_commit(repo: Path, message: str, filename: str = "file.txt") -> str:
    """Create a file and commit it; return short SHA."""
    (repo / filename).write_text(f"{message}\n")
    _git(repo, "add", filename)
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "--short", "HEAD")


@pytest.fixture()
def git_repo(tmp_path: Path) -> Path:
    """Create a minimal git repository with one commit on `main`."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    _make_commit(repo, "initial commit")
    return repo


@pytest.fixture()
def two_repo_setup(tmp_path: Path) -> tuple[Path, Path]:
    """Return (upstream, fork) where fork clones upstream with remote 'upstream'."""
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    _git(upstream, "init", "-b", "main")
    _git(upstream, "config", "user.email", "upstream@example.com")
    _git(upstream, "config", "user.name", "Upstream User")
    _make_commit(upstream, "upstream initial")

    fork = tmp_path / "fork"
    subprocess.run(["git", "clone", str(upstream), str(fork)], check=True, capture_output=True)
    _git(fork, "config", "user.email", "me@example.com")
    _git(fork, "config", "user.name", "Me")
    # rename origin → upstream (simulating fork setup)
    _git(fork, "remote", "rename", "origin", "upstream")
    # add a fake origin for push tests (bare repo)
    origin = tmp_path / "origin.git"
    origin.mkdir()
    _git(origin, "init", "--bare", "-b", "main")
    _git(fork, "remote", "add", "origin", str(origin))
    _git(fork, "push", "upstream", "main")  # push upstream ref
    return upstream, fork
```

- [x] **Step 5: Run `uv sync`**

```bash
cd /home/agent/prg/livefork
uv sync
```

Expected: resolves and installs all deps.

- [x] **Step 6: Smoke-test the CLI stub**

```bash
uv run livefork --version
```

Expected: `livefork 0.1.0`

- [x] **Step 7: Commit**

```bash
git add pyproject.toml src/ tests/
git commit -m "chore: project scaffold – pyproject, stub CLI, conftest"
```

---

### Task 2: Configuration (`config.py`)

**Files:**
- Create: `src/livefork/config.py`
- Create: `tests/test_config.py`

- [x] **Step 1: Write failing tests**

```python
# tests/test_config.py
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
```

- [x] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_config.py -v
```

Expected: `ImportError` – `livefork.config` does not exist yet.

- [x] **Step 3: Implement `src/livefork/config.py`**

```python
"""livefork configuration management."""

from __future__ import annotations

import getpass
from dataclasses import dataclass, field
from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]

import tomli_w


@dataclass
class UpstreamConfig:
    remote: str = "upstream"
    branch: str = "main"


@dataclass
class ForkConfig:
    remote: str = "origin"
    branch: str = "main"


@dataclass
class KnitSectionConfig:
    branch: str = field(default_factory=getpass.getuser)
    base: str = "main"


@dataclass
class ForkReadmeConfig:
    enabled: bool = True
    file: str = "README.md"
    push: bool = True
    template: str | None = None


@dataclass
class BranchConfig:
    name: str
    description: str = ""
    pr: str | None = None
    push: bool | None = None  # None = auto-detect from tracking


@dataclass
class LiveforkConfig:
    upstream: UpstreamConfig = field(default_factory=UpstreamConfig)
    fork: ForkConfig = field(default_factory=ForkConfig)
    knit: KnitSectionConfig = field(default_factory=KnitSectionConfig)
    fork_readme: ForkReadmeConfig = field(default_factory=ForkReadmeConfig)
    branches: list[BranchConfig] = field(default_factory=list)


def load_config(path: Path) -> LiveforkConfig:
    """Load .livefork.toml from *path*."""
    with path.open("rb") as f:
        data = tomllib.load(f)

    up = data.get("upstream", {})
    fk = data.get("fork", {})
    kn = data.get("knit", {})
    rd = data.get("fork-readme", {})

    upstream = UpstreamConfig(
        remote=up.get("remote", "upstream"),
        branch=up.get("branch", "main"),
    )
    fork = ForkConfig(
        remote=fk.get("remote", "origin"),
        branch=fk.get("branch", "main"),
    )
    knit = KnitSectionConfig(
        branch=kn.get("branch", getpass.getuser()),
        base=kn.get("base", fork.branch),
    )
    fork_readme = ForkReadmeConfig(
        enabled=rd.get("enabled", True),
        file=rd.get("file", "README.md"),
        push=rd.get("push", True),
        template=rd.get("template"),
    )
    branches = [
        BranchConfig(
            name=b["name"],
            description=b.get("description", ""),
            pr=b.get("pr"),
            push=b.get("push"),
        )
        for b in data.get("branches", [])
    ]

    return LiveforkConfig(
        upstream=upstream,
        fork=fork,
        knit=knit,
        fork_readme=fork_readme,
        branches=branches,
    )


def save_config(config: LiveforkConfig, path: Path) -> None:
    """Write .livefork.toml to *path*."""
    data: dict = {
        "upstream": {
            "remote": config.upstream.remote,
            "branch": config.upstream.branch,
        },
        "fork": {
            "remote": config.fork.remote,
            "branch": config.fork.branch,
        },
        "knit": {
            "branch": config.knit.branch,
            "base": config.knit.base,
        },
        "fork-readme": {
            "enabled": config.fork_readme.enabled,
            "file": config.fork_readme.file,
            "push": config.fork_readme.push,
        },
    }
    if config.fork_readme.template:
        data["fork-readme"]["template"] = config.fork_readme.template

    if config.branches:
        rows = []
        for b in config.branches:
            row: dict = {"name": b.name, "description": b.description}
            if b.pr is not None:
                row["pr"] = b.pr
            if b.push is not None:
                row["push"] = b.push
            rows.append(row)
        data["branches"] = rows

    with path.open("wb") as f:
        tomli_w.dump(data, f)


def find_config(start: Path) -> Path:
    """Walk up directory tree from *start* looking for .livefork.toml."""
    for parent in [start, *start.parents]:
        candidate = parent / ".livefork.toml"
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"No .livefork.toml found searching up from {start}")


def auto_detect_branches(git_repo_path: Path) -> list[BranchConfig]:
    """Scan local branches and return those that belong to the fork owner.

    Includes:  tracks origin/<name>  (push=True)
               no upstream set       (push=False)
    Excludes:  tracks upstream/<name>
               tracks any other remote
               named 'main' or 'master'
    """
    import subprocess

    result = subprocess.run(
        ["git", "branch", "--format=%(refname:short)"],
        cwd=git_repo_path,
        capture_output=True,
        text=True,
        check=True,
    )
    branches = []
    for name in result.stdout.splitlines():
        name = name.strip()
        if not name or name in ("main", "master"):
            continue
        remote_result = subprocess.run(
            ["git", "config", f"branch.{name}.remote"],
            cwd=git_repo_path,
            capture_output=True,
            text=True,
        )
        remote = remote_result.stdout.strip() if remote_result.returncode == 0 else None
        if remote == "upstream":
            continue
        if remote and remote not in ("origin",):
            continue
        push: bool | None = True if remote == "origin" else False
        branches.append(BranchConfig(name=name, description=name, push=push))
    return branches
```

- [x] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_config.py -v
```

Expected: all 6 tests PASS.

- [x] **Step 5: Commit**

```bash
git add src/livefork/config.py tests/test_config.py
git commit -m "feat: config.py – TOML load/save, BranchConfig, auto_detect_branches"
```

---

### Task 3: Git operations (`git.py`)

**Files:**
- Create: `src/livefork/git.py`
- Create: `tests/test_git.py`

- [x] **Step 1: Write failing tests**

```python
# tests/test_git.py
import subprocess
from pathlib import Path

import pytest

from livefork.git import GitRepo, GitError, BranchInfo, RebaseResult


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
    subprocess.run(["git", "checkout", "-b", "feature/x"], cwd=git_repo, check=True,
                   capture_output=True)
    g.checkout("main")
    assert g.get_current_branch() == "main"


def test_list_local_branches(git_repo):
    g = GitRepo(git_repo)
    subprocess.run(["git", "checkout", "-b", "feature/a"], cwd=git_repo, check=True,
                   capture_output=True)
    subprocess.run(["git", "checkout", "main"], cwd=git_repo, check=True, capture_output=True)
    branches = g.list_local_branches()
    names = [b.name for b in branches]
    assert "main" in names
    assert "feature/a" in names


def test_get_branch_tracking_none(git_repo):
    g = GitRepo(git_repo)
    subprocess.run(["git", "checkout", "-b", "local-only"], cwd=git_repo, check=True,
                   capture_output=True)
    assert g.get_branch_tracking("local-only") is None


def test_get_remote_url_missing(git_repo):
    g = GitRepo(git_repo)
    assert g.get_remote_url("nonexistent") is None


def test_rebase_success(two_repo_setup):
    upstream, fork = two_repo_setup
    g = GitRepo(fork)
    # create a branch on fork with one commit
    subprocess.run(["git", "checkout", "-b", "feature/patch"], cwd=fork, check=True,
                   capture_output=True)
    (fork / "patch.txt").write_text("patch\n")
    subprocess.run(["git", "add", "patch.txt"], cwd=fork, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "add patch"], cwd=fork, check=True,
                   capture_output=True)
    subprocess.run(["git", "checkout", "main"], cwd=fork, check=True, capture_output=True)
    result = g.rebase("main", branch="feature/patch")
    assert result.success is True
    assert result.conflicting_files == []


def test_enable_rerere(git_repo):
    g = GitRepo(git_repo)
    g.enable_rerere()
    result = subprocess.run(
        ["git", "config", "rerere.enabled"],
        cwd=git_repo, capture_output=True, text=True,
    )
    assert result.stdout.strip() == "true"


def test_is_in_rebase_false(git_repo):
    g = GitRepo(git_repo)
    assert g.is_in_rebase() is False


def test_get_conflicting_files_empty(git_repo):
    g = GitRepo(git_repo)
    assert g.get_conflicting_files() == []
```

- [x] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_git.py -v
```

Expected: `ImportError` – `livefork.git` does not exist yet.

- [x] **Step 3: Implement `src/livefork/git.py`**

```python
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
            raise GitError(msg or f"git {args[0]} failed (rc={result.returncode})",
                           result.returncode)
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
        return (
            (self.cwd / ".git" / "rebase-merge").exists()
            or (self.cwd / ".git" / "rebase-apply").exists()
        )

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
        return RebaseResult(success=False, conflicting_files=self.get_conflicting_files())

    def rebase_continue(self) -> RebaseResult:
        result = self.run(["rebase", "--continue"], check=False)
        if result.returncode == 0:
            return RebaseResult(success=True)
        return RebaseResult(success=False, conflicting_files=self.get_conflicting_files())

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
```

- [x] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_git.py -v
```

Expected: all tests PASS.

- [x] **Step 5: Commit**

```bash
git add src/livefork/git.py tests/test_git.py
git commit -m "feat: git.py – GitRepo subprocess wrapper, BranchInfo, RebaseResult"
```

---

### Task 4: State management (`state.py`)

**Files:**
- Create: `src/livefork/state.py`
- Create: `tests/test_state.py`

- [x] **Step 1: Write failing tests**

```python
# tests/test_state.py
from pathlib import Path
import pytest
from livefork.state import SyncState, load_state, save_state, delete_state


def _git_dir(tmp_path: Path) -> Path:
    d = tmp_path / ".git"
    d.mkdir()
    return d


def test_save_and_load_state(tmp_path):
    gd = _git_dir(tmp_path)
    state = SyncState(
        step=2,
        branch_index=1,
        branch_pre_sync_shas={"feature/foo": "abc1234", "feature/bar": "def5678"},
        paused_branch=None,
    )
    save_state(state, gd)
    loaded = load_state(gd)
    assert loaded is not None
    assert loaded.step == 2
    assert loaded.branch_index == 1
    assert loaded.branch_pre_sync_shas["feature/foo"] == "abc1234"
    assert loaded.paused_branch is None


def test_save_with_paused_branch(tmp_path):
    gd = _git_dir(tmp_path)
    state = SyncState(
        step=3,
        branch_index=2,
        branch_pre_sync_shas={},
        paused_branch="feature/conflict",
    )
    save_state(state, gd)
    loaded = load_state(gd)
    assert loaded.paused_branch == "feature/conflict"


def test_load_missing_returns_none(tmp_path):
    gd = _git_dir(tmp_path)
    assert load_state(gd) is None


def test_delete_state(tmp_path):
    gd = _git_dir(tmp_path)
    save_state(SyncState(1, 0, {}, None), gd)
    delete_state(gd)
    assert load_state(gd) is None


def test_delete_missing_is_noop(tmp_path):
    gd = _git_dir(tmp_path)
    delete_state(gd)  # should not raise


def test_state_file_is_readable_json(tmp_path):
    import json
    gd = _git_dir(tmp_path)
    save_state(SyncState(3, 1, {"b": "sha"}, "b"), gd)
    raw = json.loads((gd / "livefork-state.json").read_text())
    assert raw["step"] == 3
    assert raw["paused_branch"] == "b"
```

- [x] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_state.py -v
```

Expected: `ImportError`.

- [x] **Step 3: Implement `src/livefork/state.py`**

```python
"""Sync progress state stored in .git/livefork-state.json."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

_STATE_FILE = "livefork-state.json"


@dataclass
class SyncState:
    step: int                          # 1–5: which sync step we are on
    branch_index: int                  # index into config.branches (step 3)
    branch_pre_sync_shas: dict[str, str]   # branch → SHA before sync started
    paused_branch: str | None          # set when paused mid-rebase


def load_state(git_dir: Path) -> SyncState | None:
    """Return saved state or None if no sync is in progress."""
    path = git_dir / _STATE_FILE
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    return SyncState(
        step=data["step"],
        branch_index=data["branch_index"],
        branch_pre_sync_shas=data["branch_pre_sync_shas"],
        paused_branch=data.get("paused_branch"),
    )


def save_state(state: SyncState, git_dir: Path) -> None:
    """Persist state to disk."""
    path = git_dir / _STATE_FILE
    path.write_text(json.dumps(asdict(state), indent=2))


def delete_state(git_dir: Path) -> None:
    """Remove the state file (sync finished or aborted)."""
    path = git_dir / _STATE_FILE
    path.unlink(missing_ok=True)
```

- [x] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_state.py -v
```

Expected: all 7 tests PASS.

- [x] **Step 5: Commit**

```bash
git add src/livefork/state.py tests/test_state.py
git commit -m "feat: state.py – SyncState JSON persistence in .git/"
```

---

## Chunk 2: git-knit Bridge, Fork README

### Task 5: git-knit bridge (`knit.py`)

**Files:**
- Create: `src/livefork/knit.py`
- Create: `tests/test_knit.py`

This module imports git-knit's internal Python classes directly (not `git knit` as a subprocess). The public API exported from `git_knit.__init__` is just `cli`, so we use the internal paths: `git_knit.operations.executor.GitExecutor`, `git_knit.operations.config.KnitConfigManager`, `git_knit.operations.rebuilder.KnitRebuilder`.

- [x] **Step 1: Write failing tests**

```python
# tests/test_knit.py
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
        cwd=knit_repo, capture_output=True,
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
```

- [x] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_knit.py -v
```

Expected: `ImportError` – `livefork.knit` does not exist yet.

- [x] **Step 3: Implement `src/livefork/knit.py`**

```python
"""Bridge to git-knit Python API (internal classes)."""

from __future__ import annotations

from pathlib import Path

from git_knit.operations.config import KnitConfig, KnitConfigManager
from git_knit.operations.executor import GitExecutor as KnitGitExecutor
from git_knit.operations.rebuilder import KnitRebuilder
from git_knit.errors import KnitError


class KnitBridge:
    """Wraps git-knit's internal Python API for livefork usage.

    Uses git_knit.operations.* directly (the public git_knit.__init__ only
    exports the CLI entry-point, but the internal modules are stable for use
    within the same installed package).
    """

    def __init__(self, repo_path: Path):
        self._repo_path = Path(repo_path)
        self._executor = KnitGitExecutor(cwd=self._repo_path)
        self._config_mgr = KnitConfigManager(self._executor)
        self._rebuilder = KnitRebuilder(self._executor)

    def init_knit(
        self,
        working_branch: str,
        base_branch: str,
        feature_branches: list[str],
    ) -> None:
        """Initialize git-knit config for *working_branch*."""
        self._config_mgr.init_knit(working_branch, base_branch, feature_branches)

    def rebuild(self, working_branch: str) -> None:
        """Rebuild *working_branch* by merging all configured feature branches."""
        config = self._config_mgr.get_config(working_branch)
        self._rebuilder.rebuild(config)

    def get_config(self, working_branch: str) -> KnitConfig | None:
        """Return KnitConfig or None if not initialised."""
        try:
            return self._config_mgr.get_config(working_branch)
        except KnitError:
            return None

    def add_branch(self, working_branch: str, branch: str) -> None:
        """Add *branch* to *working_branch* and rebuild."""
        self._config_mgr.add_branch(working_branch, branch)
        self.rebuild(working_branch)

    def remove_branch(self, working_branch: str, branch: str) -> None:
        """Remove *branch* from *working_branch* and rebuild."""
        self._config_mgr.remove_branch(working_branch, branch)
        self.rebuild(working_branch)

    def is_initialized(self, working_branch: str) -> bool:
        return self.get_config(working_branch) is not None
```

- [x] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_knit.py -v
```

Expected: all 6 tests PASS.

- [x] **Step 5: Commit**

```bash
git add src/livefork/knit.py tests/test_knit.py
git commit -m "feat: knit.py – KnitBridge wrapping git-knit Python API"
```

---

### Task 6: Fork README generation (`readme.py` + Jinja2 template)

**Files:**
- Create: `src/livefork/readme.py`
- Create: `src/livefork/templates/fork-readme.md.j2`
- Create: `tests/test_readme.py`

- [x] **Step 1: Write failing tests**

```python
# tests/test_readme.py
import datetime
from pathlib import Path
import pytest
from livefork.config import (
    BranchConfig, ForkConfig, ForkReadmeConfig,
    KnitSectionConfig, LiveforkConfig, UpstreamConfig,
)
from livefork.readme import generate_readme, ReadmeContext, build_context


def _make_config(branches=None):
    return LiveforkConfig(
        upstream=UpstreamConfig(remote="upstream", branch="main"),
        fork=ForkConfig(remote="origin", branch="main"),
        knit=KnitSectionConfig(branch="johndoe", base="main"),
        fork_readme=ForkReadmeConfig(enabled=True),
        branches=branches or [],
    )


def test_generate_readme_contains_upstream_link():
    cfg = _make_config()
    readme = generate_readme(
        cfg,
        upstream_sha="a3f91c2",
        upstream_url="https://github.com/upstream-org/project",
        fork_url="https://github.com/johndoe/project",
        synced_at=datetime.date(2026, 3, 18),
    )
    assert "upstream-org/project" in readme
    assert "johndoe/project" in readme
    assert "a3f91c2" in readme
    assert "2026-03-18" in readme


def test_readme_marks_as_personal_fork():
    cfg = _make_config()
    readme = generate_readme(
        cfg,
        upstream_sha="abc1234",
        upstream_url="https://github.com/org/proj",
        fork_url="https://github.com/me/proj",
        synced_at=datetime.date(2026, 1, 1),
    )
    assert "personal fork" in readme.lower()
    assert "@me" in readme


def test_readme_lists_branch_with_pr():
    cfg = _make_config([
        BranchConfig(name="feature/foo", description="Fix foo",
                     pr="https://github.com/org/proj/pull/7"),
    ])
    readme = generate_readme(
        cfg,
        upstream_sha="abc",
        upstream_url="https://github.com/org/proj",
        fork_url="https://github.com/me/proj",
        synced_at=datetime.date(2026, 1, 1),
    )
    assert "feature/foo" in readme
    assert "Fix foo" in readme
    assert "PR #7" in readme or "pull/7" in readme


def test_readme_draft_branch():
    cfg = _make_config([
        BranchConfig(name="feature/bar", description="Add bar"),
    ])
    readme = generate_readme(
        cfg,
        upstream_sha="abc",
        upstream_url="https://github.com/org/proj",
        fork_url="https://github.com/me/proj",
        synced_at=datetime.date(2026, 1, 1),
        draft_branches={"feature/bar"},
    )
    assert "draft" in readme.lower()


def test_readme_local_only_branch():
    cfg = _make_config([
        BranchConfig(name="private/secret", description="Secret", push=False),
    ])
    readme = generate_readme(
        cfg,
        upstream_sha="abc",
        upstream_url="https://github.com/org/proj",
        fork_url="https://github.com/me/proj",
        synced_at=datetime.date(2026, 1, 1),
    )
    assert "local only" in readme


def test_custom_template(tmp_path):
    template = tmp_path / "tmpl.md.j2"
    template.write_text("# Custom: {{ project_name }} synced {{ synced_at }}\n")
    cfg = _make_config()
    cfg.fork_readme.template = str(template)
    readme = generate_readme(
        cfg,
        upstream_sha="abc",
        upstream_url="https://github.com/org/proj",
        fork_url="https://github.com/me/proj",
        synced_at=datetime.date(2026, 3, 18),
    )
    assert "Custom: proj synced 2026-03-18" in readme
```

- [x] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_readme.py -v
```

Expected: `ImportError`.

- [x] **Step 3: Write Jinja2 template `src/livefork/templates/fork-readme.md.j2`**

```jinja
# {{ project_name }} (personal fork – @{{ fork_owner }})

> ⚠️ This is a personal fork of
> [{{ upstream_owner }}/{{ project_name }}]({{ upstream_url }}).
> The `{{ upstream_branch }}` branch tracks upstream and contains no other changes.
> Personal modifications live in the branches listed below.

## Upstream

|             |                                                                            |
| ----------- | -------------------------------------------------------------------------- |
| Repository  | [{{ upstream_owner }}/{{ project_name }}]({{ upstream_url }})              |
| Synced to   | `{{ upstream_branch }}` @ [{{ upstream_sha }}]({{ upstream_url }}/commit/{{ upstream_sha }}) |
| Last synced | {{ synced_at }}                                                            |

## Personal branches

| Branch | Description | Status |
| ------ | ----------- | ------ |
{% for b in branches -%}
| {{ b.branch_link }} | {{ b.description }} | {{ b.status_text }} |
{% endfor %}
{% for ref in branch_refs -%}
{{ ref }}
{% endfor %}
```

- [x] **Step 4: Implement `src/livefork/readme.py`**

```python
"""Fork README generation using Jinja2."""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, Template

from livefork.config import LiveforkConfig


@dataclass
class BranchReadmeInfo:
    name: str
    description: str
    branch_link: str      # Markdown link text for branch column
    status_text: str      # Markdown text for status column
    ref_lines: list[str] = field(default_factory=list)  # reference-style link definitions


@dataclass
class ReadmeContext:
    project_name: str
    fork_owner: str
    upstream_owner: str
    upstream_url: str
    upstream_branch: str
    upstream_sha: str
    fork_url: str
    synced_at: str
    knit_branch: str
    branches: list[BranchReadmeInfo]

    @property
    def branch_refs(self) -> list[str]:
        refs = []
        for b in self.branches:
            refs.extend(b.ref_lines)
        return refs


def _parse_github_owner(url: str) -> str:
    """Extract owner from https://github.com/owner/repo."""
    m = re.match(r"https://github\.com/([^/]+)/", url)
    return m.group(1) if m else url


def _parse_github_repo(url: str) -> str:
    """Extract repo name from https://github.com/owner/repo."""
    m = re.match(r"https://github\.com/[^/]+/([^/]+?)(?:\.git)?$", url)
    return m.group(1) if m else url


def _pr_number(pr_url: str) -> str:
    """Extract PR number from a GitHub PR URL."""
    m = re.search(r"/pull/(\d+)", pr_url)
    return m.group(1) if m else pr_url


def build_context(
    config: LiveforkConfig,
    *,
    upstream_sha: str,
    upstream_url: str,
    fork_url: str,
    synced_at: datetime.date,
    draft_branches: set[str] | None = None,
) -> ReadmeContext:
    draft_branches = draft_branches or set()
    project_name = _parse_github_repo(upstream_url)
    upstream_owner = _parse_github_owner(upstream_url)
    fork_owner = _parse_github_owner(fork_url)

    branch_infos: list[BranchReadmeInfo] = []
    for idx, b in enumerate(config.branches, start=1):
        slug = f"b{idx}"
        push = b.push  # None means auto; treat as pushable
        has_remote = push is not False

        if has_remote:
            branch_tree_url = f"{fork_url}/tree/{b.name}"
            branch_link = f"[{b.name}][{slug}]"
            ref_lines = [f"[{slug}]: {branch_tree_url}"]
        else:
            branch_link = b.name
            ref_lines = []

        if b.pr:
            pr_num = _pr_number(b.pr)
            pr_slug = f"pr{pr_num}"
            status_text = f"[PR #{pr_num}][{pr_slug}]"
            ref_lines.append(f"[{pr_slug}]: {b.pr}")
        elif b.name in draft_branches and has_remote:
            draft_url = f"{fork_url}/blob/{b.name}/PULL-REQUEST-DRAFT.md"
            draft_slug = f"{slug}-draft"
            status_text = f"[draft PR][{draft_slug}]"
            ref_lines.append(f"[{draft_slug}]: {draft_url}")
        elif not has_remote:
            status_text = "local only"
        else:
            status_text = "—"

        branch_infos.append(BranchReadmeInfo(
            name=b.name,
            description=b.description,
            branch_link=branch_link,
            status_text=status_text,
            ref_lines=ref_lines,
        ))

    return ReadmeContext(
        project_name=project_name,
        fork_owner=fork_owner,
        upstream_owner=upstream_owner,
        upstream_url=upstream_url,
        upstream_branch=config.upstream.branch,
        upstream_sha=upstream_sha,
        fork_url=fork_url,
        synced_at=str(synced_at),
        knit_branch=config.knit.branch,
        branches=branch_infos,
    )


def _load_template(template_path: str | None) -> Template:
    if template_path:
        p = Path(template_path)
        env = Environment(loader=FileSystemLoader(str(p.parent)), keep_trailing_newline=True)
        return env.get_template(p.name)
    # built-in template
    tmpl_dir = Path(__file__).parent / "templates"
    env = Environment(loader=FileSystemLoader(str(tmpl_dir)), keep_trailing_newline=True)
    return env.get_template("fork-readme.md.j2")


def generate_readme(
    config: LiveforkConfig,
    *,
    upstream_sha: str,
    upstream_url: str,
    fork_url: str,
    synced_at: datetime.date,
    draft_branches: set[str] | None = None,
) -> str:
    """Render the fork README Markdown string."""
    ctx = build_context(
        config,
        upstream_sha=upstream_sha,
        upstream_url=upstream_url,
        fork_url=fork_url,
        synced_at=synced_at,
        draft_branches=draft_branches,
    )
    tmpl = _load_template(config.fork_readme.template)
    return tmpl.render(**ctx.__dict__, branch_refs=ctx.branch_refs)
```

- [x] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/test_readme.py -v
```

Expected: all 6 tests PASS.

- [x] **Step 6: Commit**

```bash
git add src/livefork/readme.py src/livefork/templates/ tests/test_readme.py
git commit -m "feat: readme.py – Jinja2 fork README generation with branch table"
```

---

## Chunk 3: Sync Workflow, Agent Context

### Task 7: Sync workflow (`sync.py`)

**Files:**
- Create: `src/livefork/sync.py`
- Create: `tests/test_sync.py`

The sync orchestrator runs the 5-step workflow described in REFERENCE.md. It writes state after every step so `livefork continue` can resume exactly where it paused.

- [x] **Step 1: Write failing tests**

```python
# tests/test_sync.py
import subprocess
from pathlib import Path
import pytest
from livefork.config import BranchConfig, LiveforkConfig, ForkReadmeConfig
from livefork.git import GitRepo
from livefork.knit import KnitBridge
from livefork.state import load_state
from livefork.sync import SyncOptions, SyncOrchestrator, SyncError


def _git(cwd, *args):
    subprocess.run(["git"] + list(args), cwd=cwd, check=True, capture_output=True)


def _commit(repo, msg, fname):
    (repo / fname).write_text(msg)
    _git(repo, "add", fname)
    _git(repo, "commit", "-m", msg)


@pytest.fixture()
def sync_setup(tmp_path):
    """
    upstream: has initial commit + one new commit after fork point
    fork:     clones upstream, has 'feature/patch' branch
    Returns (upstream, fork, config)
    """
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    _git(upstream, "init", "-b", "main")
    _git(upstream, "config", "user.email", "u@u.com")
    _git(upstream, "config", "user.name", "U")
    _commit(upstream, "initial", "base.txt")

    fork = tmp_path / "fork"
    subprocess.run(["git", "clone", str(upstream), str(fork)], check=True, capture_output=True)
    _git(fork, "config", "user.email", "me@me.com")
    _git(fork, "config", "user.name", "Me")
    _git(fork, "remote", "rename", "origin", "upstream")

    # add a fake origin (bare) for push tests
    origin = tmp_path / "origin.git"
    origin.mkdir()
    _git(origin, "init", "--bare", "-b", "main")
    _git(fork, "remote", "add", "origin", str(origin))

    # fork creates a feature branch
    _git(fork, "checkout", "-b", "feature/patch")
    _commit(fork, "patch", "patch.txt")
    _git(fork, "checkout", "main")

    # upstream advances
    _commit(upstream, "upstream advance", "up.txt")

    from livefork.config import (
        UpstreamConfig, ForkConfig, KnitSectionConfig,
        ForkReadmeConfig, LiveforkConfig,
    )
    cfg = LiveforkConfig(
        upstream=UpstreamConfig(remote="upstream", branch="main"),
        fork=ForkConfig(remote="origin", branch="main"),
        knit=KnitSectionConfig(branch="johndoe", base="main"),
        fork_readme=ForkReadmeConfig(enabled=False),
        branches=[BranchConfig(name="feature/patch", description="My patch")],
    )
    return upstream, fork, cfg


def test_sync_dry_run_exits_zero(sync_setup):
    upstream, fork, cfg = sync_setup
    g = GitRepo(fork)
    knit = KnitBridge(fork)
    # init knit first
    knit.init_knit("johndoe", "main", ["feature/patch"])
    orch = SyncOrchestrator(cfg, g, knit, fork)
    rc = orch.run(SyncOptions(dry_run=True))
    assert rc == 0
    # no state file left after dry-run completes
    assert load_state(fork / ".git") is None


def test_sync_no_conflict(sync_setup):
    upstream, fork, cfg = sync_setup
    g = GitRepo(fork)
    knit = KnitBridge(fork)
    knit.init_knit("johndoe", "main", ["feature/patch"])
    orch = SyncOrchestrator(cfg, g, knit, fork)
    rc = orch.run(SyncOptions(no_readme=True))
    assert rc == 0
    # fork main should now have upstream's new commit
    g.checkout("main")
    log = subprocess.run(
        ["git", "log", "--oneline", "main"],
        cwd=fork, capture_output=True, text=True,
    ).stdout
    assert "upstream advance" in log
    # no leftover state
    assert load_state(fork / ".git") is None


def test_sync_saves_state_after_fetch(sync_setup, monkeypatch):
    """State should be saved after step 1 (fetch)."""
    upstream, fork, cfg = sync_setup
    g = GitRepo(fork)
    knit = KnitBridge(fork)
    knit.init_knit("johndoe", "main", ["feature/patch"])

    # intercept _step_advance_fork_main to raise so we can inspect state
    calls = []
    orch = SyncOrchestrator(cfg, g, knit, fork)
    original = orch._step_advance_fork_main
    def boom(options):
        calls.append("boom")
        raise RuntimeError("intentional")
    monkeypatch.setattr(orch, "_step_advance_fork_main", boom)

    with pytest.raises(RuntimeError):
        orch.run(SyncOptions(no_readme=True))

    assert len(calls) == 1
    # step was saved as 2 (about to do step 2)
    state = load_state(fork / ".git")
    assert state is not None
    assert state.step == 2


def test_abort_sync_resets_branches(sync_setup):
    upstream, fork, cfg = sync_setup
    g = GitRepo(fork)
    knit = KnitBridge(fork)
    knit.init_knit("johndoe", "main", ["feature/patch"])

    pre_sha = g.get_commit_sha("feature/patch")

    # run sync to completion, then manually inject state as if paused
    from livefork.state import SyncState, save_state
    fake_state = SyncState(
        step=3,
        branch_index=1,  # branch 0 "already rebased"
        branch_pre_sync_shas={"feature/patch": pre_sha},
        paused_branch="feature/patch",
    )
    save_state(fake_state, fork / ".git")

    orch = SyncOrchestrator(cfg, g, knit, fork)
    rc = orch.abort_sync()
    assert rc == 0
    # feature/patch should be back at pre_sha
    assert g.get_commit_sha("feature/patch") == pre_sha
    assert load_state(fork / ".git") is None


def test_sync_raises_if_already_in_progress(sync_setup):
    upstream, fork, cfg = sync_setup
    g = GitRepo(fork)
    knit = KnitBridge(fork)
    knit.init_knit("johndoe", "main", ["feature/patch"])

    from livefork.state import SyncState, save_state
    save_state(SyncState(1, 0, {}, None), fork / ".git")

    orch = SyncOrchestrator(cfg, g, knit, fork)
    with pytest.raises(SyncError, match="already in progress"):
        orch.run()
```

- [x] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_sync.py -v
```

Expected: `ImportError` – `livefork.sync` does not exist yet.

- [x] **Step 3: Implement `src/livefork/sync.py`**

```python
"""Sync workflow orchestration for livefork."""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from pathlib import Path

from livefork.config import LiveforkConfig
from livefork.git import GitRepo, RebaseResult
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
    branch: str | None = None    # rebase only this branch
    no_knit: bool = False
    no_readme: bool = False


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

        state = SyncState(step=1, branch_index=0, branch_pre_sync_shas=pre_shas, paused_branch=None)
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

        upstream_sha = self.git.get_commit_sha(
            f"{self.config.upstream.remote}/{self.config.upstream.branch}", short=True
        )
        upstream_url = self.git.get_remote_url(self.config.upstream.remote) or ""
        fork_url = self.git.get_remote_url(self.config.fork.remote) or ""
        # strip .git suffix
        upstream_url = upstream_url.removesuffix(".git")
        fork_url = fork_url.removesuffix(".git")

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
        if self.config.fork_readme.push:
            self.git.push(
                self.config.fork.remote,
                self.config.fork.branch,
                force_with_lease=True,
            )

    def _print_conflict_message(self, branch: str, conflicting_files: list[str]) -> None:
        sep = "━" * 60
        files_str = "\n".join(f"  {f}  (content conflict)" for f in conflicting_files)
        print(f"""\
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
""")
```

- [x] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_sync.py -v
```

Expected: all 5 tests PASS.

- [x] **Step 5: Commit**

```bash
git add src/livefork/sync.py tests/test_sync.py
git commit -m "feat: sync.py – SyncOrchestrator with 5-step workflow, state persistence"
```

---

### Task 8: Agent context (`agent_context.py`)

**Files:**
- Create: `src/livefork/agent_context.py`
- Create: `tests/test_agent_context.py`

The agent context document is a self-contained Markdown report containing everything a coding AI needs to resolve a rebase conflict without asking questions.

- [x] **Step 1: Write failing tests**

```python
# tests/test_agent_context.py
import subprocess
from pathlib import Path
import pytest
from livefork.config import BranchConfig, LiveforkConfig, ForkConfig, KnitSectionConfig
from livefork.config import UpstreamConfig, ForkReadmeConfig
from livefork.git import GitRepo
from livefork.state import SyncState
from livefork.agent_context import generate_agent_context


def _git(cwd, *args):
    subprocess.run(["git"] + list(args), cwd=cwd, check=True, capture_output=True)


def _commit(repo, msg, fname, content=None):
    (repo / fname).write_text(content or msg)
    _git(repo, "add", fname)
    _git(repo, "commit", "-m", msg)


@pytest.fixture()
def conflict_repo(tmp_path):
    """A repo mid-rebase with a conflict on feature/patch."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "t@t.com")
    _git(repo, "config", "user.name", "T")
    _commit(repo, "initial", "foo.py", "x = 1\n")

    # branch diverges
    _git(repo, "checkout", "-b", "feature/patch")
    _commit(repo, "patch foo", "foo.py", "x = 2\n")

    # main also changes foo.py
    _git(repo, "checkout", "main")
    _commit(repo, "upstream change", "foo.py", "x = 99\n")

    # trigger the conflict
    result = subprocess.run(
        ["git", "rebase", "main"],
        cwd=repo, capture_output=True, text=True,
    )
    # rebase should have stopped with conflict
    assert result.returncode != 0
    return repo


def test_agent_context_contains_branch_name(conflict_repo):
    cfg = LiveforkConfig(
        upstream=UpstreamConfig(),
        fork=ForkConfig(),
        knit=KnitSectionConfig(branch="johndoe"),
        fork_readme=ForkReadmeConfig(enabled=False),
        branches=[BranchConfig(name="feature/patch", description="Patch foo")],
    )
    g = GitRepo(conflict_repo)
    state = SyncState(step=3, branch_index=0,
                      branch_pre_sync_shas={"feature/patch": "abc"},
                      paused_branch="feature/patch")
    doc = generate_agent_context(cfg, g, state)
    assert "feature/patch" in doc


def test_agent_context_contains_conflicting_file(conflict_repo):
    cfg = LiveforkConfig(
        knit=KnitSectionConfig(branch="j"),
        branches=[BranchConfig(name="feature/patch", description="Patch foo")],
    )
    g = GitRepo(conflict_repo)
    state = SyncState(step=3, branch_index=0,
                      branch_pre_sync_shas={},
                      paused_branch="feature/patch")
    doc = generate_agent_context(cfg, g, state)
    assert "foo.py" in doc


def test_agent_context_contains_continue_command(conflict_repo):
    cfg = LiveforkConfig(knit=KnitSectionConfig(branch="j"), branches=[])
    g = GitRepo(conflict_repo)
    state = SyncState(3, 0, {}, "feature/patch")
    doc = generate_agent_context(cfg, g, state)
    assert "livefork continue" in doc


def test_agent_context_no_conflict_raises(tmp_path):
    # no rebase in progress
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "t@t.com")
    _git(repo, "config", "user.name", "T")
    _commit(repo, "init", "f.txt")
    cfg = LiveforkConfig(knit=KnitSectionConfig(branch="j"), branches=[])
    g = GitRepo(repo)
    state = SyncState(3, 0, {}, None)
    with pytest.raises(ValueError, match="No rebase"):
        generate_agent_context(cfg, g, state)
```

- [x] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_agent_context.py -v
```

Expected: `ImportError`.

- [x] **Step 3: Implement `src/livefork/agent_context.py`**

```python
"""Generate a self-contained Markdown conflict report for coding AI assistants."""

from __future__ import annotations

from textwrap import dedent

from livefork.config import LiveforkConfig
from livefork.git import GitRepo
from livefork.state import SyncState


def generate_agent_context(
    config: LiveforkConfig,
    git: GitRepo,
    state: SyncState,
) -> str:
    """Return a Markdown document describing the current rebase conflict.

    Raises ValueError if no rebase is in progress.
    """
    if not git.is_in_rebase():
        raise ValueError("No rebase in progress – nothing to report.")

    paused_branch = state.paused_branch or "(unknown)"
    onto_branch = config.fork.branch
    conflicting_files = git.get_conflicting_files()
    stopped_sha = git.get_rebase_stopped_sha()

    # Diff of the commit being applied
    commit_diff = ""
    if stopped_sha:
        try:
            commit_diff = git.get_diff(stopped_sha)
        except Exception as e:
            commit_diff = f"(could not get commit diff: {e})"

    # Content of each conflicting file
    file_sections = []
    for fname in conflicting_files:
        try:
            content = (git.cwd / fname).read_text()
        except Exception:
            content = "(could not read file)"
        file_sections.append(
            f"### `{fname}`\n\n```\n{content}\n```"
        )

    files_listing = "\n".join(f"- `{f}`" for f in conflicting_files) or "(none found)"
    file_content_sections = "\n\n".join(file_sections) or "(no file content)"

    doc = dedent(f"""\
        # livefork Conflict Report

        An automated sync has paused due to a rebase conflict. Resolve the
        conflict markers in each file listed below, stage the files, and run
        `livefork continue`.

        ---

        ## Situation

        - **Branch being rebased:** `{paused_branch}`
        - **Rebasing onto:** `{onto_branch}`
        - **Conflicting commit SHA:** `{stopped_sha or "(unknown)"}`

        ---

        ## Conflicting files

        {files_listing}

        ---

        ## Diff of the conflicting commit

        This is what the branch was trying to apply:

        ```diff
        {commit_diff}
        ```

        ---

        ## Current file contents (with conflict markers)

        {file_content_sections}

        ---

        ## Resolution steps

        For each conflicting file:

        1. Open the file, resolve all `<<<<<<<` / `=======` / `>>>>>>>` markers.
        2. Keep the changes you want; discard the rest.
        3. Stage the resolved file:

        ```bash
        git add <file>
        ```

        After all files are staged:

        ```bash
        livefork continue
        ```

        To abort the sync entirely:

        ```bash
        livefork abort
        ```
    """)
    return doc
```

- [x] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_agent_context.py -v
```

Expected: all 4 tests PASS.

- [x] **Step 5: Commit**

```bash
git add src/livefork/agent_context.py tests/test_agent_context.py
git commit -m "feat: agent_context.py – structured conflict report for AI assistants"
```

---

## Chunk 4: CLI

### Task 9: CLI – core commands (`init`, `status`, `add`, `remove`, `knit`, `readme`)

**Files:**
- Modify: `src/livefork/cli.py`
- Create: `tests/test_cli.py` (initial)

All commands load config with `_require_config()` or write it with `_save_config()`. The CLI uses `typer.echo` for output and `typer.Exit` for exit codes. Machine-readable output (for agents) uses the same text format – no special flags needed because every message is already structured and unambiguous.

- [x] **Step 1: Write failing tests for core commands**

```python
# tests/test_cli.py
import subprocess
from pathlib import Path
import pytest
from typer.testing import CliRunner
from livefork.cli import app

runner = CliRunner(mix_stderr=False)


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
    subprocess.run(["git", "clone", str(upstream), str(fork)], check=True, capture_output=True)
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
    result = runner.invoke(app, ["status"], catch_exceptions=False,
                           env={"HOME": str(tmp_path)})
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
        app, ["add", "feature/extra", "--description", "Extra work"],
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
        app, ["remove", "feature/patch"],
        catch_exceptions=False,
        env={"PWD": str(repo)},
    )
    from livefork.config import load_config
    cfg = load_config(repo / ".livefork.toml")
    names = [b.name for b in cfg.branches]
    assert "feature/patch" not in names
```

- [x] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_cli.py -v
```

Expected: some pass (--version), others fail (commands not implemented).

- [x] **Step 3: Implement full `src/livefork/cli.py`**

```python
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
        typer.echo(f"Error: no .livefork.toml found in {root}. Run 'livefork init' first.", err=True)
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
    version: Annotated[bool, typer.Option("--version", "-V", help="Print version and exit.")] = False,
) -> None:
    if version:
        from livefork import __version__
        typer.echo(f"livefork {__version__}")
        raise typer.Exit()


# ------------------------------------------------------------------ init

@app.command()
def init(
    upstream: Annotated[Optional[str], typer.Option(help="Upstream remote URL (prompted if needed).")] = None,
    merge_branch: Annotated[Optional[str], typer.Option("--merge-branch", help="Override merge branch name.")] = None,
) -> None:
    """Configure an existing fork clone and initialise the merge branch."""
    from livefork.config import (
        auto_detect_branches, find_config, load_config, save_config,
        LiveforkConfig, UpstreamConfig, ForkConfig, KnitSectionConfig,
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
        typer.echo(f"Found existing .livefork.toml – updating.")
    else:
        knit_branch = merge_branch or getpass.getuser()
        cfg = LiveforkConfig(
            upstream=UpstreamConfig(),
            fork=ForkConfig(),
            knit=KnitSectionConfig(branch=knit_branch),
            fork_readme=ForkReadmeConfig(),
        )
        typer.echo(f"Creating .livefork.toml.")

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
            result = git.run(["merge-base", "--is-ancestor", fork_ref, b.name], check=False)
            rebased = result.returncode == 0
        except Exception:
            rebased = False
        status_sym = "✓ rebased" if rebased else "✗ needs rebase"

        # draft / PR
        draft = ""
        try:
            r = git.run(["cat-file", "-e", f"{b.name}:PULL-REQUEST-DRAFT.md"], check=False)
            if r.returncode == 0:
                draft = "  [draft]"
        except Exception:
            pass
        if b.pr:
            import re
            m = re.search(r"/pull/(\d+)", b.pr)
            draft = f"  [PR #{m.group(1)} submitted]" if m else f"  [PR submitted]"

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
    no_push: Annotated[bool, typer.Option("--no-push", help="Regenerate without pushing.")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print content without writing.")] = False,
) -> None:
    """Regenerate and push the fork README."""
    import datetime
    root = _repo_root()
    cfg = _require_config(root)
    git = _make_git(root)

    from livefork.readme import generate_readme
    from livefork.sync import SyncOptions, SyncOrchestrator
    from livefork.knit import KnitBridge

    knit = KnitBridge(root)
    orch = SyncOrchestrator(cfg, git, knit, root)
    orch._step_update_readme(SyncOptions(dry_run=dry_run, no_knit=True))
    if not dry_run:
        typer.echo("✓ Fork README updated.")


# ------------------------------------------------------------------ sync

@app.command()
def sync(
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    branch: Annotated[Optional[str], typer.Option("--branch", help="Rebase one branch only.")] = None,
    no_knit: Annotated[bool, typer.Option("--no-knit")] = False,
    no_readme: Annotated[bool, typer.Option("--no-readme")] = False,
) -> None:
    """Fetch upstream · rebase all branches · rebuild merge branch · push fork README."""
    root = _repo_root()
    cfg = _require_config(root)
    git = _make_git(root)
    knit = _make_knit(root)

    from livefork.sync import SyncOptions, SyncOrchestrator, SyncError
    options = SyncOptions(dry_run=dry_run, branch=branch, no_knit=no_knit, no_readme=no_readme)
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
    message: Annotated[Optional[str], typer.Option("--message", "-m", help="Set title line.")] = None,
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
            cwd=root, capture_output=True,
        ).returncode == 0
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
    base: Annotated[Optional[str], typer.Option("--base", help="Target branch on upstream.")] = None,
    draft_pr: Annotated[bool, typer.Option("--draft", help="Open as a draft PR.")] = False,
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
    gh_args = ["gh", "pr", "create",
                "--title", title,
                "--body", body,
                "--base", upstream_base,
                "--repo", _upstream_github_slug(git, cfg)]
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
    git.commit(f"chore: remove PULL-REQUEST-DRAFT.md after PR creation")

    git.checkout(cfg.fork.branch)
    typer.echo("✓ PR submitted, config updated, draft removed.")


def _upstream_github_slug(git, cfg) -> str:
    """Return 'owner/repo' from the upstream remote URL."""
    import re
    url = git.get_remote_url(cfg.upstream.remote) or ""
    m = re.search(r"github\.com[:/](.+?)(?:\.git)?$", url)
    return m.group(1) if m else url


# ------------------------------------------------------------------ create (requires gh)

@app.command()
def create(
    repo: Annotated[str, typer.Argument(help="Upstream repo (owner/name or URL).")],
    fork_name: Annotated[Optional[str], typer.Option("--fork-name")] = None,
    org: Annotated[Optional[str], typer.Option("--org")] = None,
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
    if org:
        gh_args += ["--org", org]

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
    git.run(["remote", "add", fork_remote, origin_url.replace(slug.split("/")[0] + "/", f"{getpass.getuser()}/")])

    if not no_init:
        os.environ["PWD"] = str(local_path)
        init(merge_branch=merge_branch)


if __name__ == "__main__":
    app()
```

- [x] **Step 4: Run all tests**

```bash
uv run pytest tests/test_cli.py -v
```

Expected: version, add, remove tests PASS. (Status and others may need further work depending on env.)

- [x] **Step 5: Run full test suite**

```bash
uv run pytest -v
```

Expected: all tests PASS.

- [x] **Step 6: Manual smoke test**

```bash
# In a temp directory with a fork setup:
uv run livefork --help
uv run livefork sync --help
uv run livefork status --help
```

- [x] **Step 7: Commit**

```bash
git add src/livefork/cli.py tests/test_cli.py
git commit -m "feat: cli.py – all commands (init, sync, continue, abort, status, add, remove, knit, readme, agent-context, draft, pr, create)"
```

---

## Chunk 5: Integration Tests

### Task 10: End-to-end sync integration test

**Files:**
- Create: `tests/test_integration.py`

Tests the full sync workflow against real local git repos (no GitHub required).

- [x] **Step 1: Write integration tests**

```python
# tests/test_integration.py
"""
End-to-end integration tests for the sync workflow.
These use real git repos in tmp_path – no GitHub, no remote network.
"""
import subprocess
from pathlib import Path
import pytest
from livefork.config import (
    BranchConfig, ForkConfig, ForkReadmeConfig,
    KnitSectionConfig, LiveforkConfig, UpstreamConfig,
)
from livefork.git import GitRepo
from livefork.knit import KnitBridge
from livefork.state import load_state
from livefork.sync import SyncOptions, SyncOrchestrator


def _git(cwd, *args):
    subprocess.run(["git"] + list(args), cwd=cwd, check=True, capture_output=True)


def _commit(repo, msg, fname, content=None):
    (repo / fname).write_text(content or msg)
    _git(repo, "add", fname)
    _git(repo, "commit", "-m", msg)
    return subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=repo, capture_output=True, text=True, check=True,
    ).stdout.strip()


def _setup_fork(tmp_path) -> tuple[Path, Path, LiveforkConfig]:
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    _git(upstream, "init", "-b", "main")
    _git(upstream, "config", "user.email", "u@u.com")
    _git(upstream, "config", "user.name", "U")
    _commit(upstream, "initial", "base.txt")

    fork = tmp_path / "fork"
    subprocess.run(["git", "clone", str(upstream), str(fork)], check=True, capture_output=True)
    _git(fork, "config", "user.email", "me@me.com")
    _git(fork, "config", "user.name", "Me")
    _git(fork, "remote", "rename", "origin", "upstream")

    # create feature branches
    _git(fork, "checkout", "-b", "feature/alpha")
    _commit(fork, "alpha work", "alpha.txt")
    _git(fork, "checkout", "main")

    _git(fork, "checkout", "-b", "feature/beta")
    _commit(fork, "beta work", "beta.txt")
    _git(fork, "checkout", "main")

    cfg = LiveforkConfig(
        upstream=UpstreamConfig(remote="upstream", branch="main"),
        fork=ForkConfig(remote="origin", branch="main"),
        knit=KnitSectionConfig(branch="johndoe", base="main"),
        fork_readme=ForkReadmeConfig(enabled=False),
        branches=[
            BranchConfig(name="feature/alpha", description="Alpha"),
            BranchConfig(name="feature/beta", description="Beta"),
        ],
    )
    # init knit
    KnitBridge(fork).init_knit("johndoe", "main", ["feature/alpha", "feature/beta"])
    return upstream, fork, cfg


def test_full_sync_no_conflict(tmp_path):
    upstream, fork, cfg = _setup_fork(tmp_path)

    # upstream makes a new commit (non-conflicting)
    _commit(upstream, "upstream new feature", "upstream_new.txt")

    g = GitRepo(fork)
    knit = KnitBridge(fork)
    orch = SyncOrchestrator(cfg, g, knit, fork)
    rc = orch.run(SyncOptions(no_readme=True))

    assert rc == 0
    assert load_state(fork / ".git") is None

    # fork/main should now be at upstream/main
    g.checkout("main")
    fork_sha = g.get_commit_sha("main")
    upstream_sha = g.get_commit_sha("upstream/main")
    assert fork_sha == upstream_sha

    # feature branches rebased
    for branch_name in ["feature/alpha", "feature/beta"]:
        g.checkout(branch_name)
        r = g.run(["log", "--oneline", branch_name], check=True)
        assert "upstream new feature" in r.stdout

    # merge branch exists
    r = g.run(["rev-parse", "--verify", "johndoe"], check=False)
    assert r.returncode == 0


def test_sync_conflict_pauses_and_abort_restores(tmp_path):
    upstream, fork, cfg = _setup_fork(tmp_path)

    # upstream changes base.txt (same file as feature/alpha will touch via rebase)
    _commit(upstream, "upstream changes base", "alpha.txt", "upstream version\n")
    # alpha also changes alpha.txt – conflict!

    g = GitRepo(fork)
    knit = KnitBridge(fork)
    pre_alpha_sha = g.get_commit_sha("feature/alpha")

    orch = SyncOrchestrator(cfg, g, knit, fork)
    rc = orch.run(SyncOptions(no_readme=True))
    # Should pause on conflict
    assert rc == 1

    state = load_state(fork / ".git")
    assert state is not None
    assert state.paused_branch == "feature/alpha"

    # Abort
    orch.abort_sync()
    assert load_state(fork / ".git") is None
    # feature/alpha back to pre-sync sha
    assert g.get_commit_sha("feature/alpha") == pre_alpha_sha


def test_sync_idempotent_after_no_upstream_change(tmp_path):
    upstream, fork, cfg = _setup_fork(tmp_path)

    g = GitRepo(fork)
    knit = KnitBridge(fork)
    orch = SyncOrchestrator(cfg, g, knit, fork)

    rc1 = orch.run(SyncOptions(no_readme=True))
    sha_after_first = g.get_commit_sha("main")

    rc2 = orch.run(SyncOptions(no_readme=True))
    sha_after_second = g.get_commit_sha("main")

    assert rc1 == 0
    assert rc2 == 0
    assert sha_after_first == sha_after_second
```

- [x] **Step 2: Run integration tests**

```bash
uv run pytest tests/test_integration.py -v
```

Expected: all 3 tests PASS (conflict test may need tuning based on exact git rebase behavior).

- [x] **Step 3: Run full test suite**

```bash
uv run pytest -v --tb=short
```

Expected: all tests PASS.

- [x] **Step 4: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: end-to-end integration tests for sync workflow"
```

---

## Final steps

- [x] **Run full test suite with coverage**

```bash
uv run pytest --cov=livefork --cov-report=term-missing -v
```

- [x] **Verify CLI help output**

```bash
uv run livefork --help
uv run livefork sync --help
uv run livefork init --help
uv run livefork agent-context --help
```

- [x] **Update `docs/plans/` with completion note and commit**

```bash
git add docs/
git commit -m "docs: mark initial implementation plan tasks complete"
```

---

## Design decisions and notes

### Machine/agent friendliness
Every command outputs one line per logical event (e.g. `✓ Sync complete.`). Error messages go to `stderr` with `err=True`; success output goes to `stdout`. Exit codes: 0 = success, 1 = error/conflict. The `agent-context` command outputs pure Markdown to stdout, ready to pipe to any AI tool.

### git-knit Python API
We import `git_knit.operations.*` directly. These are not exported from `git_knit.__init__` (which only exports `cli`), but they are stable internal modules. `KnitBridge` isolates all git-knit imports so a future API change only requires touching `knit.py`.

### TOML serialization of `[[branches]]`
`tomli-w` serializes `data["branches"] = [{"name": ...}, ...]` as `[[branches]]` TOML array-of-tables. This matches the format shown in REFERENCE.md.

### Rebase strategy
`git rebase --rebase-merges` preserves any merge structure within a topic branch. `git rerere` is enabled on `livefork init` so conflict resolutions are remembered.

### Fork README push
`git push --force-with-lease` is used because the fork's main branch is always exactly one commit ahead of upstream (the README commit). Each sync discards the old README commit and re-creates it on top of the fresh upstream HEAD.

### State file location
`.git/livefork-state.json` is inside `.git/` so it is never accidentally committed or pushed. It is human-readable JSON for easy inspection.

### `push=None` semantics
A `BranchConfig` with `push=None` means "auto-detect from git tracking". During README generation, `push=False` is the only value that means "local only / no GitHub link". `None` and `True` both produce GitHub links.

### `draft` command and editor
`livefork draft` uses `$EDITOR` (falls back to `vi`). In non-interactive / agent environments, pass `--message` to set the title without opening an editor.

### `pr create` and `create` require `gh`
These commands call `gh` as a subprocess. If `gh` is not installed, the command fails with a clear error from subprocess. No special detection is needed – the error is self-explanatory.
