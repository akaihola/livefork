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
