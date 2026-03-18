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
        file_sections.append(f"### `{fname}`\n\n```\n{content}\n```")

    files_listing = "\n".join(f"- `{f}`" for f in conflicting_files) or "(none found)"
    file_content_sections = "\n\n".join(file_sections) or "(no file content)"

    doc = dedent(
        f"""\
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
    """
    )
    return doc
