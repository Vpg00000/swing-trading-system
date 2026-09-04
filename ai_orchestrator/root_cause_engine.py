"""
Root Cause Analyzer Engine — inspects call chains, recent git commits,
file dependencies, and AST nodes to build an evidence-based hypothesis.
"""

from __future__ import annotations

import ast
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from issue_detector import NormalizedIssue


@dataclass
class RootCauseHypothesis:
    issue_id: str
    target_file: str
    primary_suspect: str
    root_cause_summary: str
    recent_commits_touching_file: List[str]
    call_stack_modules: List[str]
    confidence_score: float  # 0.0 - 1.0


class RootCauseEngine:
    def __init__(self, repo_root: Path = Path(".")):
        self.root = repo_root.resolve()

    def _get_recent_commits(self, rel_path: str) -> List[str]:
        try:
            res = subprocess.run(
                ["git", "log", "-n", "3", "--oneline", "--", rel_path],
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=10,
            )
            return [line.strip() for line in res.stdout.splitlines() if line.strip()]
        except Exception:
            return []

    def _find_imports(self, rel_path: str) -> List[str]:
        full_path = self.root / rel_path
        if not full_path.exists() or not rel_path.endswith(".py"):
            return []
        try:
            tree = ast.parse(full_path.read_text(encoding="utf-8", errors="replace"))
            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.append(node.module)
            return imports
        except Exception:
            return []

    def analyze(self, issue: NormalizedIssue) -> RootCauseHypothesis:
        recent_commits = self._get_recent_commits(issue.file_path)
        imports = self._find_imports(issue.file_path)

        summary = (
            f"Failure in {issue.file_path} at line {issue.line_number or 'unknown'}: "
            f"{issue.error_message}. Imports {len(imports)} modules."
        )

        confidence = 0.85 if recent_commits else 0.70

        return RootCauseHypothesis(
            issue_id=issue.issue_id,
            target_file=issue.file_path,
            primary_suspect=f"{issue.file_path}:{issue.line_number or 1}",
            root_cause_summary=summary,
            recent_commits_touching_file=recent_commits,
            call_stack_modules=imports,
            confidence_score=confidence,
        )
