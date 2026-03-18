# livefork

> Keep your personal fork alive – one command to sync upstream, rebase your branches, and rebuild the merge stack.

`livefork` is a Python CLI tool for maintaining a long-lived personal fork of an upstream project. You keep additions and modifications in focused topic branches and a [`git-knit`][git-knit] merge branch that combines them all for daily use. `livefork sync` pulls upstream changes, rebases every topic branch, and rebuilds the merge branch in one shot – pausing with clear instructions whenever a conflict needs attention.

---

## How it works

```
upstream/main
      │  git fetch + reset --hard
      ▼
your fork/main  (+ fork README commit, pushed)
      │
      ├─► feature/my-patch-1 ──── git rebase fork/main ─────┐
      ├─► feature/my-patch-2 ──── git rebase fork/main ─────┤
      └─► private/integration ─── git rebase fork/main ─────┘
                                                              │
                              git-knit rebuild ◄──────────────┘
                                     │
                                     ▼
                          merge-branch  (all topic branches merged)
```

---

## Prerequisites

- Python 3.10+, Git 2.38+
- [`git-knit`][git-knit] – builds and maintains the merge branch
- [GitHub CLI (`gh`)][gh-cli] – required only for `livefork create` and `livefork pr create`

---

## Installation

```bash
pip install livefork        # or: uv tool install livefork
livefork --version
```

---

## Quick start

**Fork a new repository:**

```bash
livefork create upstream-org/project
cd project
livefork sync
```

**Configure an existing fork:**

```bash
cd my-fork
livefork init
livefork sync
```

Both commands detect your local branches automatically, write `.livefork.toml`, initialise the merge branch (named after your username by default), and generate an initial fork README on the `main` branch.

---

## Commands

| Command                       | Description                                                                    |
| ----------------------------- | ------------------------------------------------------------------------------ |
| `livefork create <repo>`      | Fork on GitHub, clone, configure, and initialise in one step                   |
| `livefork init`               | Configure an existing fork clone and initialise the merge branch               |
| `livefork sync`               | Fetch upstream · rebase all branches · rebuild merge branch · push fork README |
| `livefork continue`           | Resume a paused sync after resolving a conflict                                |
| `livefork abort`              | Abort a paused sync and restore the previous state                             |
| `livefork status`             | Show sync state and PR status for all branches                                 |
| `livefork draft <branch>`     | Create or edit a `PULL-REQUEST-DRAFT.md` for a branch                          |
| `livefork pr create <branch>` | Submit a PR from the draft, record the URL, update the fork README             |
| `livefork readme`             | Regenerate and push the fork README on demand                                  |
| `livefork add <branch>`       | Add a topic branch to the configuration                                        |
| `livefork remove <branch>`    | Remove a topic branch from the configuration                                   |
| `livefork knit`               | Rebuild the merge branch without touching topic branches                       |
| `livefork agent-context`      | Print a conflict report for a coding AI assistant                              |

See [REFERENCE.md] for full configuration options, all command flags, the sync workflow, conflict resolution, the PR draft convention, and the fork README feature.

---

## Contributing

Contributions are welcome. Please open an issue before starting significant work.

```bash
git clone https://github.com/akaihola/livefork && cd livefork
uv sync && uv run pytest
```

## License

BSD 3-Clause – see [LICENSE](LICENSE).

---

[git-knit]: https://github.com/akaihola/git-knit
[gh-cli]: https://cli.github.com
[REFERENCE.md]: REFERENCE.md
