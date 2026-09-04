"""
Reviewer agent — post-coding quality gate.

Re-uses the existing RepositoryAuditor to scan only the changed files
for placeholder/mock/TODO/fake patterns before a task is marked VERIFIED.

A task passes review only when:
  - 0 HIGH severity findings in PRODUCTION files
  - No new TODO/FIXME/mock/dummy patterns added by the coder

LOW and INFO severity findings are reported but do not block verification.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parent))
from auditor import RepositoryAuditor, PlaceholderFinding


# ─────────────────────────────────────────────────────────────────────────────
# Result types
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ReviewResult:
    approved: bool
    high_severity: List[PlaceholderFinding] = field(default_factory=list)
    medium_severity: List[PlaceholderFinding] = field(default_factory=list)
    low_severity: List[PlaceholderFinding] = field(default_factory=list)
    files_scanned: int = 0

    @property
    def total_issues(self) -> int:
        return len(self.high_severity) + len(self.medium_severity) + len(self.low_severity)

    def summary(self) -> str:
        if self.approved:
            return f"✓  Review PASSED — {self.files_scanned} file(s) scanned, 0 HIGH issues"
        return (
            f"✗  Review FAILED — {len(self.high_severity)} HIGH, "
            f"{len(self.medium_severity)} MEDIUM severity findings in {self.files_scanned} file(s)"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Reviewer
# ─────────────────────────────────────────────────────────────────────────────

class Reviewer:
    """
    Quality gate that runs after the Coder has applied file edits.

    Only scans the files that were actually changed — not the whole repo.
    Uses the existing RepositoryAuditor (read-only, no AI calls).

    Usage:
        reviewer = Reviewer(repo_root=Path("."))
        result = reviewer.review(changed_files=["engine/forensic.py"])
        if result.approved:
            # mark task VERIFIED
    """

    def __init__(self, repo_root: Path):
        self.root = repo_root.resolve()
        self.auditor = RepositoryAuditor(repository_root=str(self.root))

    def review(self, changed_files: List[str]) -> ReviewResult:
        """
        Scan the changed files for placeholder/mock/TODO patterns.

        Args:
            changed_files: List of relative file paths that were modified or created.

        Returns:
            ReviewResult(approved=True) if no HIGH severity findings.
            ReviewResult(approved=False) if any HIGH severity findings exist.
        """
        if not changed_files:
            return ReviewResult(
                approved=True,
                files_scanned=0,
            )

        # Scan all findings across the repository
        all_findings: List[PlaceholderFinding] = self.auditor.scan_placeholders(
            focus_production_only=True
        )

        # Filter to only the files that were changed in this task
        changed_set = set(
            p.replace("\\", "/") for p in changed_files
        )
        relevant: List[PlaceholderFinding] = [
            f for f in all_findings
            if f.file.replace("\\", "/") in changed_set
        ]

        high = [f for f in relevant if f.severity == "HIGH"]
        medium = [f for f in relevant if f.severity == "MEDIUM"]
        low = [f for f in relevant if f.severity in ("LOW", "INFO")]

        # Print a concise report
        if relevant:
            print(f"    [review] {len(relevant)} finding(s) in changed files:")
            for finding in high:
                print(f"    ✗  HIGH [{finding.category}] {finding.file}:{finding.line_number}")
                print(f"         {finding.matched_text[:100]}")
            for finding in medium:
                print(f"    ⚠  MEDIUM [{finding.category}] {finding.file}:{finding.line_number}")
            for finding in low:
                print(f"    ℹ  LOW [{finding.category}] {finding.file}:{finding.line_number}")
        else:
            print(f"    [review] Clean — no placeholder/mock findings in {len(changed_files)} file(s)")

        return ReviewResult(
            approved=len(high) == 0,
            high_severity=high,
            medium_severity=medium,
            low_severity=low,
            files_scanned=len(changed_files),
        )
