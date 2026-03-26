"""Canonical format for ``PULL-REQUEST-DRAFT.md``.

File layout::

    branch: feature/my-thing
    title: Add the my-thing feature

    Longer description in Markdown.  This section becomes
    the PR body when ``livefork pr`` submits the pull request.

Lines before the first blank line are ``key: value`` metadata.
Everything after the first blank line is the description body.
"""

from __future__ import annotations

from dataclasses import dataclass
from textwrap import dedent


@dataclass
class DraftContent:
    """Parsed representation of a ``PULL-REQUEST-DRAFT.md`` file."""

    branch: str
    title: str
    body: str


def format_draft(draft: DraftContent) -> str:
    """Serialize *draft* to the canonical file format.

    >>> format_draft(DraftContent("b", "t", "body"))
    'branch: b\\ntitle: t\\n\\nbody\\n'
    """
    lines = [
        f"branch: {draft.branch}",
        f"title: {draft.title}",
        "",
        draft.body,
    ]
    text = "\n".join(lines)
    if not text.endswith("\n"):
        text += "\n"
    return text


def parse_draft(text: str) -> DraftContent:
    """Parse *text* into a :class:`DraftContent`.

    Raises :exc:`ValueError` when required metadata is missing.
    """
    lines = text.splitlines()

    meta: dict[str, str] = {}
    body_start = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            body_start = i + 1
            break
        if ":" in stripped:
            key, _, value = stripped.partition(":")
            meta[key.strip().lower()] = value.strip()
        else:
            # Non-metadata line before first blank – treat rest as body.
            body_start = i
            break
    else:
        # No blank line found – everything is metadata, body is empty.
        body_start = len(lines)

    branch = meta.get("branch", "")
    title = meta.get("title", "")
    body = "\n".join(lines[body_start:]).strip()

    if not branch:
        raise ValueError("PULL-REQUEST-DRAFT.md is missing 'branch:' metadata")
    if not title:
        raise ValueError("PULL-REQUEST-DRAFT.md is missing 'title:' metadata")

    return DraftContent(branch=branch, title=title, body=body)
