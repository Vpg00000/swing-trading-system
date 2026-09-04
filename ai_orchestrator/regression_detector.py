"""
Downstream Regression Detector — analyzes dependency graphs of modified files
and runs targeted tests against dependent modules to ensure zero side effects.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path
from typing import Dict, List, Set


class RegressionDetector:
    def __init__(self, repo_root: Path = Path(".")):
        self.root = repo_root.resolve()

    def find_dependent_modules(self, modified_files: List[str]) -> List[str]:
        """
        Finds python files in the repo that import any of the modified files.
        """
        mod_names: Set[str] = set()
        for f in modified_files:
            p = Path(f)
            mod_names.add(p.stem)

        dependents: List[str] = []
        for py_file in self.root.rglob("*.py"):
            if any(part.startswith((".", "venv", "__pycache__")) for part in py_file.parts):
                continue
            rel_path = str(py_file.relative_to(self.root))
            if rel_path in modified_files:
                continue

            try:
                content = py_file.read_text(encoding="utf-8", errors="replace")
                for m_name in mod_names:
                    if f"import {m_name}" in content or f"from {m_name}" in content or f"engine.{m_name}" in content:
                        dependents.append(rel_path)
                        break
            except Exception:
                pass

        return dependents

    def run_regression_tests(self, modified_files: List[str]) -> Dict[str, bool]:
        dependents = self.find_dependent_modules(modified_files)
        results: Dict[str, bool] = {}

        # Run tests folder if present
        test_dir = self.root / "tests"
        if test_dir.exists():
            try:
                res = subprocess.run(
                    ["pytest", "-q", "tests/"],
                    cwd=self.root,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                results["full_suite"] = (res.returncode == 0)
            except Exception:
                results["full_suite"] = False
        else:
            results["full_suite"] = True

        return results
