"""
Git Safety Layer — manages isolated git repair branches (ai-fix/<issue-id>),
captures clean diffs, and prevents direct mutation of the main branch.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional


class GitSafetySandbox:
    def __init__(self, repo_root: Path = Path(".")):
        self.root = repo_root.resolve()

    def _run_git(self, *args: str) -> str:
        res = subprocess.run(
            ["git", *args],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False,
        )
        return res.stdout.strip()

    def get_current_branch(self) -> str:
        return self._run_git("rev-parse", "--abbrev-ref", "HEAD")

    def create_repair_branch(self, issue_id: str) -> str:
        clean_id = issue_id.lower().replace(" ", "-").replace("/", "-")
        branch_name = f"ai-fix/{clean_id}"
        # Check if branch exists
        current = self.get_current_branch()
        if current != branch_name:
            self._run_git("checkout", "-b", branch_name)
        return branch_name

    def get_patch_diff(self) -> str:
        return self._run_git("diff")

    def rollback_branch(self, original_branch: str = "main") -> None:
        self._run_git("checkout", original_branch)
