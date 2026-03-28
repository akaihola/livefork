"""Fork README generation using Jinja2."""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass, field
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, Template

from livefork.config import LiveforkConfig


@dataclass
class BranchReadmeInfo:
    name: str
    description: str
    branch_link: str  # Markdown link text for branch column
    status_text: str  # Markdown text for status column
    ref_lines: list[str] = field(
        default_factory=list
    )  # reference-style link definitions


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
    if not upstream_url:
        raise ValueError(
            "upstream_url is empty – cannot generate README without a valid"
            " upstream remote URL"
        )
    if not fork_url:
        raise ValueError(
            "fork_url is empty – cannot generate README without a valid"
            " fork remote URL"
        )
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

        # Description: link to PULL-REQUEST-DRAFT.md when available
        if b.name in draft_branches and has_remote:
            draft_url = f"{fork_url}/blob/{b.name}/PULL-REQUEST-DRAFT.md"
            draft_slug = f"{slug}-draft"
            description = f"[{b.description}][{draft_slug}]"
            ref_lines.append(f"[{draft_slug}]: {draft_url}")
        else:
            description = b.description

        if b.pr:
            pr_num = _pr_number(b.pr)
            pr_slug = f"pr{pr_num}"
            status_text = f"[PR #{pr_num}][{pr_slug}]"
            ref_lines.append(f"[{pr_slug}]: {b.pr}")
        elif b.name in draft_branches and has_remote:
            status_text = "draft PR"
        elif not has_remote:
            status_text = "local only"
        else:
            status_text = "—"

        branch_infos.append(
            BranchReadmeInfo(
                name=b.name,
                description=description,
                branch_link=branch_link,
                status_text=status_text,
                ref_lines=ref_lines,
            )
        )

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
        env = Environment(
            loader=FileSystemLoader(str(p.parent)), keep_trailing_newline=True
        )
        return env.get_template(p.name)
    # built-in template
    tmpl_dir = Path(__file__).parent / "templates"
    env = Environment(
        loader=FileSystemLoader(str(tmpl_dir)), keep_trailing_newline=True
    )
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
