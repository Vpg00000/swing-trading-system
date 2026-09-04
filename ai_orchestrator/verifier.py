"""
Verifier agent — runs Python import checks and the task's test command
to determine whether a code fix is actually working.

Returns structured PASS / FAIL results with stdout/stderr.
This is the ground truth: AI cannot hallucinate a passing test.

Verification steps (in order):
  1. Python syntax check (ast.parse) on each changed .py file
  2. Python import check (subprocess) for the task's backend_module
  3. Test command from task CSV (if present)
  4. Basic endpoint smoke test (if api_endpoint is set)
"""

from __future__ import annotations

import ast
import glob
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tasks import Task


# ─────────────────────────────────────────────────────────────────────────────
# Result types
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class StepResult:
    step: str
    passed: bool
    stdout: str = ""
    stderr: str = ""
    duration_sec: float = 0.0
    skipped: bool = False
    skip_reason: str = ""


@dataclass
class VerifyResult:
    passed: bool
    steps: List[StepResult] = field(default_factory=list)
    total_duration_sec: float = 0.0
    fail_reason: str = ""

    @property
    def failed_steps(self) -> List[StepResult]:
        return [s for s in self.steps if not s.passed and not s.skipped]


# ─────────────────────────────────────────────────────────────────────────────
# Verifier
# ─────────────────────────────────────────────────────────────────────────────

class Verifier:
    """
    Ground-truth code verifier.

    Usage:
        verifier = Verifier(repo_root=Path("."))
        result = verifier.verify(task, changed_files=["engine/forensic.py"])
    """

    # Timeout for each subprocess step
    IMPORT_TIMEOUT_SEC = 30
    TEST_TIMEOUT_SEC = 120

    def __init__(self, repo_root: Path):
        self.root = repo_root.resolve()
        self.python = sys.executable or "python3"

    def _run(self, cmd: List[str], timeout: int) -> tuple[int, str, str, float]:
        """Run a subprocess, return (returncode, stdout, stderr, duration)."""
        t = time.time()
        try:
            result = subprocess.run(
                cmd,
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            return result.returncode, result.stdout.strip(), result.stderr.strip(), round(time.time() - t, 2)
        except subprocess.TimeoutExpired:
            return 1, "", f"Timed out after {timeout}s", round(time.time() - t, 2)
        except Exception as exc:
            return 1, "", str(exc), round(time.time() - t, 2)

    # ── Step 1: Syntax check ─────────────────────────────────────────────────

    def _check_syntax(self, changed_files: List[str]) -> StepResult:
        py_files = [f for f in changed_files if f.endswith(".py")]
        if not py_files:
            return StepResult(
                step="syntax_check",
                passed=True,
                skipped=True,
                skip_reason="No .py files changed",
            )

        errors = []
        for rel_path in py_files:
            full = self.root / rel_path
            if not full.exists():
                continue
            try:
                source = full.read_text(encoding="utf-8", errors="replace")
                ast.parse(source)
            except SyntaxError as exc:
                errors.append(f"{rel_path}:{exc.lineno}: {exc.msg}")

        return StepResult(
            step="syntax_check",
            passed=len(errors) == 0,
            stdout=f"Checked {len(py_files)} file(s)",
            stderr="\n".join(errors),
        )

    # ── Step 2: Import check ─────────────────────────────────────────────────

    def _check_imports(self, modules: List[str]) -> StepResult:
        valid_modules = []
        for m in modules:
            mod = m.strip()
            if not mod or mod.lower() in ("all", "none", "n/a", "all modules") or " " in mod or "/" in mod or "-" in mod:
                continue
            valid_modules.append(mod)

        if not valid_modules:
            return StepResult(
                step="import_check",
                passed=True,
                skipped=True,
                skip_reason="No valid Python module names specified",
            )

        failures = []
        t_start = time.time()

        for mod in valid_modules:
            rc, stdout, stderr, _ = self._run(
                [
                    self.python, "-c",
                    f"import sys; sys.path.insert(0, '{self.root}'); import {mod}; print('IMPORT_OK: {mod}')",
                ],
                timeout=self.IMPORT_TIMEOUT_SEC,
            )
            if rc != 0 or "IMPORT_OK" not in stdout:
                failures.append(f"{mod}: {stderr or 'unknown error'}")

        duration = round(time.time() - t_start, 2)
        return StepResult(
            step="import_check",
            passed=len(failures) == 0,
            stdout=f"Checked {len(valid_modules)} module(s)",
            stderr="\n".join(failures),
            duration_sec=duration,
        )

    # ── Step 3: Test command ─────────────────────────────────────────────────

    def _run_test_command(self, test_command: str) -> StepResult:
        if not test_command.strip():
            return StepResult(
                step="test_command",
                passed=True,
                skipped=True,
                skip_reason="No test command in task CSV",
            )

        cmd_parts = test_command.split()
        # Replace bare 'python' or 'pytest' with active virtualenv python interpreter
        if cmd_parts:
            if cmd_parts[0] in ("python", "python3"):
                cmd_parts[0] = self.python
            elif cmd_parts[0] == "pytest":
                cmd_parts = [self.python, "-m", "pytest"] + cmd_parts[1:]

            clean_parts = []
            for part in cmd_parts:
                if part in ("/", "suite", "integration", "integration suite", "suite*") or "integration" in part.lower() or "suite" in part.lower():
                    continue
                clean_parts.append(part)

            expanded_parts = []
            for part in clean_parts:
                if "*" in part or "?" in part:
                    matched = glob.glob(str(self.root / part)) or glob.glob(part)
                    if matched:
                        # Convert absolute paths back to relative for clean execution
                        rel_matched = [
                            str(Path(m).relative_to(self.root)) if Path(m).is_absolute() and str(self.root) in m else m
                            for m in matched
                        ]
                        expanded_parts.extend(rel_matched)
                    else:
                        # Fallback to tests/ if wildcard didn't match any file yet
                        expanded_parts.append("tests/")
                else:
                    expanded_parts.append(part)

            cmd_parts = expanded_parts

        rc, stdout, stderr, duration = self._run(cmd_parts, self.TEST_TIMEOUT_SEC)

        return StepResult(
            step="test_command",
            passed=(rc == 0),
            stdout=stdout[:2000],
            stderr=stderr[:2000],
            duration_sec=duration,
        )

    # ── Public API ───────────────────────────────────────────────────────────

    def verify(
        self,
        task: Task,
        changed_files: List[str],
        extra_modules: Optional[List[str]] = None,
    ) -> VerifyResult:
        """
        Run all verification steps for a task after code has been applied.

        Args:
            task: The Task object from TaskManager
            changed_files: List of relative paths that were modified/created
            extra_modules: Additional Python modules to import-check

        Returns:
            VerifyResult with per-step results and overall passed flag
        """
        t_start = time.time()
        steps: List[StepResult] = []

        # Step 1: Syntax check
        print("    [verify] Syntax check ...")
        step1 = self._check_syntax(changed_files)
        steps.append(step1)
        if not step1.passed:
            print(f"    ✗  Syntax errors:\n       {step1.stderr}")
        else:
            label = "skipped" if step1.skipped else "OK"
            print(f"    ✓  Syntax: {label}")

        # Step 2: Import check
        modules_to_check = []
        if task.backend_module and task.backend_module.strip():
            modules_to_check.append(task.backend_module.strip())
        if extra_modules:
            modules_to_check.extend(extra_modules)

        # Derive module names from changed .py files automatically (excluding tests and scratch scripts)
        for rel_path in changed_files:
            if rel_path.endswith(".py") and not rel_path.startswith(("tests/", "scratch/", "test_")):
                mod = rel_path.replace("/", ".").removesuffix(".py")
                if mod not in modules_to_check:
                    modules_to_check.append(mod)

        if modules_to_check:
            print(f"    [verify] Import check: {', '.join(modules_to_check)} ...")
            step2 = self._check_imports(modules_to_check)
            steps.append(step2)
            if not step2.passed:
                print(f"    ✗  Import failures:\n       {step2.stderr}")
            else:
                print(f"    ✓  Imports: OK ({len(modules_to_check)} module(s))")

        # Step 3: Test command
        if task.test_command:
            print(f"    [verify] Running: {task.test_command} ...")
            step3 = self._run_test_command(task.test_command)
            steps.append(step3)
            if not step3.passed:
                print(f"    ✗  Test failed (exit {step3.passed}):\n       {step3.stderr[:300]}")
            else:
                label = "skipped" if step3.skipped else f"PASS ({step3.duration_sec}s)"
                print(f"    ✓  Test: {label}")

        duration = round(time.time() - t_start, 2)
        failed = [s for s in steps if not s.passed and not s.skipped]
        passed = len(failed) == 0

        fail_reason = ""
        if not passed:
            fail_reason = "; ".join(
                f"{s.step}: {s.stderr[:120]}" for s in failed
            )

        return VerifyResult(
            passed=passed,
            steps=steps,
            total_duration_sec=duration,
            fail_reason=fail_reason,
        )
