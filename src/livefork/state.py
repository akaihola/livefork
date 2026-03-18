"""Sync progress state stored in .git/livefork-state.json."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

_STATE_FILE = "livefork-state.json"


@dataclass
class SyncState:
    step: int  # 1–5: which sync step we are on
    branch_index: int  # index into config.branches (step 3)
    branch_pre_sync_shas: dict[str, str]  # branch → SHA before sync started
    paused_branch: str | None  # set when paused mid-rebase


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
