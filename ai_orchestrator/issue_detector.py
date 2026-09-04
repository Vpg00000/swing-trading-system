"""
Issue Intelligence — normalizes runtime errors, failed tests, tracebacks,
and static lint issues into a unified `NormalizedIssue` schema.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class NormalizedIssue:
    issue_id: str
    issue_type: str  # "runtime_error" | "test_failure" | "syntax_error" | "contract_mismatch" | "security_risk"
    severity: str    # "critical" | "high" | "medium" | "low"
    file_path: str
    line_number: Optional[int] = None
    error_message: str = ""
    traceback_text: str = ""
    frequency: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "issue_type": self.issue_type,
            "severity": self.severity,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "error_message": self.error_message,
            "traceback_text": self.traceback_text[:500],
            "frequency": self.frequency,
            "metadata": self.metadata,
        }


class IssueDetector:
    """
    Parses unhandled exceptions, pytest outputs, and tracebacks into NormalizedIssue.
    """

    @staticmethod
    def parse_python_traceback(tb_text: str, default_issue_id: str = "ISSUE-001") -> NormalizedIssue:
        file_path = "unknown"
        line_num = None
        error_msg = tb_text.strip().splitlines()[-1] if tb_text else "Unknown error"

        # Regex search for last File "path.py", line XX
        matches = re.findall(r'File "([^"]+)", line (\d+)', tb_text)
        if matches:
            file_path, line_str = matches[-1]
            line_num = int(line_str)

        return NormalizedIssue(
            issue_id=default_issue_id,
            issue_type="runtime_error",
            severity="high",
            file_path=file_path,
            line_number=line_num,
            error_message=error_msg,
            traceback_text=tb_text,
        )

    @staticmethod
    def parse_pytest_output(pytest_output: str, default_issue_id: str = "TEST-FAIL") -> List[NormalizedIssue]:
        issues = []
        # Find FAILED test_xxx.py::test_func - Error
        failed_lines = re.findall(r'FAILED ([^\s:]+)::([^\s]+)\s*-\s*(.*)', pytest_output)
        for i, (file_path, test_func, msg) in enumerate(failed_lines, 1):
            issues.append(
                NormalizedIssue(
                    issue_id=f"{default_issue_id}-{i:03d}",
                    issue_type="test_failure",
                    severity="high",
                    file_path=file_path,
                    error_message=f"Test '{test_func}' failed: {msg}",
                    traceback_text=pytest_output,
                    metadata={"test_function": test_func},
                )
            )
        return issues
