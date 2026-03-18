"""Bridge to git-knit Python API (internal classes)."""

from __future__ import annotations

from pathlib import Path

from git_knit.errors import KnitError
from git_knit.operations.config import KnitConfig, KnitConfigManager
from git_knit.operations.executor import GitExecutor as KnitGitExecutor
from git_knit.operations.rebuilder import KnitRebuilder


class KnitBridge:
    """Wraps git-knit's internal Python API for livefork usage.

    Uses git_knit.operations.* directly (the public git_knit.__init__ only
    exports the CLI entry-point, but the internal modules are stable for use
    within the same installed package).
    """

    def __init__(self, repo_path: Path):
        self._repo_path = Path(repo_path)
        self._executor = KnitGitExecutor(cwd=self._repo_path)
        self._config_mgr = KnitConfigManager(self._executor)
        self._rebuilder = KnitRebuilder(self._executor)

    def init_knit(
        self,
        working_branch: str,
        base_branch: str,
        feature_branches: list[str],
    ) -> None:
        """Initialize git-knit config for *working_branch*."""
        self._config_mgr.init_knit(working_branch, base_branch, feature_branches)

    def rebuild(self, working_branch: str) -> None:
        """Rebuild *working_branch* by merging all configured feature branches."""
        config = self._config_mgr.get_config(working_branch)
        self._rebuilder.rebuild(config)

    def get_config(self, working_branch: str) -> KnitConfig | None:
        """Return KnitConfig or None if not initialised."""
        try:
            return self._config_mgr.get_config(working_branch)
        except KnitError:
            return None

    def add_branch(self, working_branch: str, branch: str) -> None:
        """Add *branch* to *working_branch* and rebuild."""
        self._config_mgr.add_branch(working_branch, branch)
        self.rebuild(working_branch)

    def remove_branch(self, working_branch: str, branch: str) -> None:
        """Remove *branch* from *working_branch* and rebuild."""
        self._config_mgr.remove_branch(working_branch, branch)
        self.rebuild(working_branch)

    def is_initialized(self, working_branch: str) -> bool:
        return self.get_config(working_branch) is not None
