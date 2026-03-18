import datetime
from pathlib import Path
import pytest
from livefork.config import (
    BranchConfig,
    ForkConfig,
    ForkReadmeConfig,
    KnitSectionConfig,
    LiveforkConfig,
    UpstreamConfig,
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
    cfg = _make_config(
        [
            BranchConfig(
                name="feature/foo",
                description="Fix foo",
                pr="https://github.com/org/proj/pull/7",
            ),
        ]
    )
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
    cfg = _make_config(
        [
            BranchConfig(name="feature/bar", description="Add bar"),
        ]
    )
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
    cfg = _make_config(
        [
            BranchConfig(name="private/secret", description="Secret", push=False),
        ]
    )
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
