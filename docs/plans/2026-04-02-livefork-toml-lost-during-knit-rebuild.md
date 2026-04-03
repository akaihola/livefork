# Fix: `.livefork.toml` lost during `knit rebuild`

**Date:** 2026-04-02  
**Status:** Implementation complete, tests pass – ready for final verification and commit

---

## Problem

When `livefork knit rebuild` (or `livefork sync`) ran, the untracked `.livefork.toml`
config file would silently disappear from the working tree.

**Root-cause analysis** (confirmed in `~/repos/ai/claude-code-mux/`):

1. `.livefork.toml` was not listed in `.gitignore`, so `git status --porcelain`
   showed it as `??` (untracked, non-ignored).
2. `git_knit`'s `GitExecutor.stash_push` used `git stash push --include-untracked`,
   which stashed – and physically removed from disk – every untracked non-ignored
   file, including `.livefork.toml`.
3. `KnitRebuilder.rebuild` had no `finally` block around `stash_pop`. Any exception
   during rebuild (merge conflict, cherry-pick conflict, missing branch, …) would
   leave the stash un-popped, stranding `.livefork.toml` in the stash.

The leftover `knit/backup/akaihola-fd9a58b` branch in that repo confirmed a previous
rebuild failure – the exact path where `stash_pop` was never called.

---

## Changes

### Repo: `~/prg/git-knit`

#### `src/git_knit/operations/executor.py`

Remove `--include-untracked` from `stash_push`.

```diff
-        args = ["stash", "push", "--include-untracked"]
+        args = ["stash", "push"]
```

**Why:** Untracked files do not need to be stashed before branch switches.
`git checkout` never removes untracked files unless they conflict with a tracked
file in the target branch, which would be a loud error rather than silent data
loss. Stashing untracked files was unnecessary and created a window for data loss.

#### `src/git_knit/operations/rebuilder.py`

Add a `finally` block that always pops the stash when one was created.

```python
            if stash_created:
                self.executor.stash_pop()
                stash_created = False  # prevent double-pop in finally

        except GitConflictError:
            raise
        except Exception:
            raise
        finally:
            if stash_created:
                try:
                    self.executor.stash_pop()
                except Exception:
                    pass  # best-effort; original exception propagates
```

**Why:** Covers all non-success exit paths (missing branch, checkout failure, …).
For cherry-pick conflicts, `git stash pop` itself fails (the index has unresolved
entries) so the `except Exception: pass` is intentional – the stash is retained
for the user to pop manually after resolving the conflict.

#### `tests/test_operations.py`

Four new / updated tests:

| Test                                                                  | What it proves                                                                                                                                 |
| --------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `test_stash_operations` (updated)                                     | Uses tracked modifications; untracked files are no longer stashed                                                                              |
| `test_rebuild_preserves_untracked_files`                              | `.livefork.toml`-style untracked file survives a full rebuild unchanged and is never stashed                                                   |
| `test_rebuild_stash_popped_on_missing_branch`                         | `finally` block pops stash after a non-conflict error (`BranchNotFoundError`); WIP tracked change is restored                                  |
| `test_rebuild_pops_stash_on_success_with_tracked_wip`                 | Success path (lines 97-98) is exercised when tracked WIP exists                                                                                |
| `test_rebuild_stash_remains_on_cherry_pick_conflict_with_tracked_wip` | `finally` block's `except Exception: pass` (lines 108-109) fires during cherry-pick conflict; `GitConflictError` propagates; stash is retained |

---

### Repo: `~/prg/livefork`

#### `src/livefork/config.py`

Add `resolve_config_path(repo_root)` and update `find_config` to prefer
`.git/livefork.toml` over `.livefork.toml`.

**`resolve_config_path(repo_root: Path) -> Path`** – resolution order:

1. `.git/livefork.toml` – preferred; inside the git dir, completely unaffected by
   branch switches, stashing, or `.gitignore`.
2. `.livefork.toml` – legacy working-tree location.
3. Default for new configs: `.git/livefork.toml` if a `.git/` directory exists,
   otherwise `.livefork.toml`.

**`find_config(start: Path) -> Path`** – now checks `.git/livefork.toml` before
`.livefork.toml` at every level of the directory walk.

#### `src/livefork/cli.py`

Three changes:

1. **`_config_path`** delegates to `resolve_config_path` so that every write
   (init, add, remove, pr) uses the same preferred location.

2. **`_require_config`** uses `find_config` instead of `_config_path` (no-walk),
   so it correctly discovers configs in either location.

3. **`_ensure_gitignore_entry(repo_root, config_path)`** – new helper. When
   `config_path` is inside the working tree (i.e. not inside `.git/`), it adds
   the file's name to `.gitignore`, creating `.gitignore` if absent. Called at
   the end of `init`.

4. **`init`** updated to call `_ensure_gitignore_entry` and to log the actual
   config path rather than hardcoding `.livefork.toml`.

5. **`test_status_no_config`** fix (test suite): added `"PWD": str(tmp_path)` to
   the env dict so `_repo_root()` returns the isolated temp dir rather than the
   project directory; updated assertion to match the new error wording.

#### `tests/test_config.py`

New tests for `resolve_config_path` and the updated `find_config`:

- `test_resolve_config_path_git_dir_config_exists`
- `test_resolve_config_path_prefers_git_dir_over_workdir`
- `test_resolve_config_path_falls_back_to_workdir`
- `test_resolve_config_path_new_git_repo_defaults_to_git_dir`
- `test_resolve_config_path_non_git_dir_defaults_to_workdir`
- `test_find_config_prefers_git_dir_over_workdir`
- `test_find_config_git_dir_found_when_walking_up`

#### `tests/test_cli.py`

New `TestEnsureGitignoreEntry` class:

- `test_adds_entry_to_existing_gitignore`
- `test_creates_gitignore_when_absent`
- `test_does_not_duplicate_existing_entry`
- `test_no_gitignore_entry_for_git_dir_config`
- `test_init_writes_to_git_dir_for_new_repo`
- `test_init_workdir_config_added_to_gitignore`

---

## Test results

| Repo     | Before                               | After                  |
| -------- | ------------------------------------ | ---------------------- |
| git-knit | 99 pass, coverage 94% (pre-existing) | 103 pass, coverage 96% |
| livefork | 129 pass                             | 130 pass               |

The `fail-under=100` gate in git-knit was already failing before these changes
(pre-existing gaps in `executor.py`, `rebuilder.py`, and `commands/commit.py`
unrelated to this work). Our changes improved overall coverage from 94% to 96%.

---

## Known edge case: cherry-pick conflict + tracked WIP

When a rebuild fails with a cherry-pick conflict **and** the user had tracked WIP
changes before the rebuild started:

- The WIP changes are stashed at the start of rebuild.
- The conflict leaves the index in an unresolvable state.
- `git stash pop` refuses to operate while there are unresolved index entries.
- The `except Exception: pass` in the `finally` block catches the failure and
  propagates the original `GitConflictError`.
- The user must resolve the cherry-pick conflict (`git cherry-pick --abort` or
  manually), then run `git stash pop` to recover their WIP.

This is acceptable: data is not lost (it's in the stash), just deferred.

---

## Final state

| Repo     | Tests    | Coverage                            |
| -------- | -------- | ----------------------------------- |
| git-knit | 112 pass | **100%** (was 94% before this work) |
| livefork | 130 pass | n/a (no coverage gate)              |

## Remaining work

- [ ] Commit changes in `git-knit`  
       `fix: don't stash untracked files; always pop stash in finally block`
- [ ] Commit changes in `livefork`  
       `fix: prefer .git/livefork.toml; ensure .livefork.toml is git-ignored`
- [ ] Migrate `~/repos/ai/claude-code-mux/.livefork.toml` →  
       `~/repos/ai/claude-code-mux/.git/livefork.toml`  
       (or simply run `livefork init` inside that repo – it will pick up the existing  
       working-tree config, re-save it, and add it to `.gitignore`)
