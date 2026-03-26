"""LLM-based pull request draft generation for livefork."""

from __future__ import annotations

from textwrap import dedent

from livefork.draft_format import DraftContent


SYSTEM_PROMPT = dedent("""\
    You are a developer writing a pull request description.  Based on the Git
    commit log and diff provided, write a clear, concise pull request draft.

    Output exactly two sections separated by a single blank line:

    1. First line: a short descriptive PR title (plain text – no Markdown
       heading syntax, no prefix like "PR:" or "Title:").
    2. A blank line.
    3. Body: describe what this PR does, why, and any notable implementation
       details.  Use Markdown formatting as appropriate.

    Do NOT wrap the output in a code fence.  Output only the content described
    above – nothing else.
""")


def build_prompt(log: str, diff: str) -> str:
    """Assemble the user prompt from a git log and a diff."""
    return dedent(f"""\
        ## Git commit log

        {log}

        ## Diff against branch point

        {diff}
    """)


def _parse_llm_output(text: str, branch: str) -> DraftContent:
    """Split raw LLM output into *title* and *body*, attach *branch*."""
    lines = text.strip().splitlines()
    title = lines[0].strip() if lines else branch
    # Skip the blank separator line (index 1) if present.
    body_lines = lines[2:] if len(lines) > 2 else []
    body = "\n".join(body_lines).strip()
    return DraftContent(branch=branch, title=title, body=body)


def generate_draft(
    log: str,
    diff: str,
    *,
    branch: str,
    model_id: str | None = None,
) -> DraftContent:
    """Generate a PR draft using Simon Willison's *llm* library.

    Parameters
    ----------
    log:
        Output of ``git log`` for the branch range.
    diff:
        Output of ``git diff`` between the branch point and the branch tip.
    branch:
        Branch name – embedded in the returned :class:`DraftContent`.
    model_id:
        Optional LLM model identifier (e.g. ``"claude-sonnet-4-20250514"``).
        When *None*, the user's configured default model is used.

    Returns
    -------
    DraftContent
        Parsed draft ready to be written with
        :func:`livefork.draft_format.format_draft`.

    Raises
    ------
    ImportError
        If the ``llm`` package is not installed.
    """
    import llm  # noqa: WPS433 – intentional lazy import

    model = llm.get_model(model_id) if model_id else llm.get_model()
    prompt_text = build_prompt(log, diff)
    response = model.prompt(prompt_text, system=SYSTEM_PROMPT)
    return _parse_llm_output(response.text(), branch)
