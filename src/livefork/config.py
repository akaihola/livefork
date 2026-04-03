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


def resolve_config_path(repo_root: Path) -> Path:
    """Return the config file path to use for *repo_root*.

    Resolution order (first match wins):

    1. ``.git/livefork.toml`` – preferred; lives inside the git directory so it
       is completely unaffected by branch switches and will never be stashed.
    2. ``.livefork.toml`` – legacy working-tree location.

    When neither file exists yet (initial ``livefork init``):

    * Defaults to ``.git/livefork.toml`` when a ``.git`` *directory* exists.
    * Falls back to ``.livefork.toml`` otherwise (bare / non-git directories).
    """
    git_dir_config = repo_root / ".git" / "livefork.toml"
    workdir_config = repo_root / ".livefork.toml"
    if git_dir_config.exists():
        return git_dir_config
    if workdir_config.exists():
        return workdir_config
    # Neither exists – choose preferred location for a new config
    if (repo_root / ".git").is_dir():
        return git_dir_config
    return workdir_config


def find_config(start: Path) -> Path:
    """Walk up directory tree from *start* looking for a livefork config.

    At each directory level, ``.git/livefork.toml`` is checked before
    ``.livefork.toml`` so that the git-directory location is always preferred.
    """
    for parent in [start, *start.parents]:
        git_dir = parent / ".git"
        if git_dir.is_dir():
            git_config = git_dir / "livefork.toml"
            if git_config.exists():
                return git_config
        candidate = parent / ".livefork.toml"
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"No livefork config found searching up from {start}")


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
