from __future__ import annotations

import os
import re
import sys
import subprocess
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional

TARGET_ARCHITECTURE_PATHS = [
    "data/database.py",
    "data/sync_engine.py",
    "data/microstructure.py",
    "data/institutional_flow.py",
    "data/corporate_calendar.py",
    "data/dhan_auth.py",
    "data/fii_dii.py",
    "data/nse_filings.py",
    "engine/indicators.py",
    "engine/portfolio_optimizer.py",
    "engine/tax_lots.py",
    "engine/forensic.py",
    "engine/macro_regime.py",
    "engine/macro_shocks.py",
    "engine/dhan_routing.py",
    "engine/backtest.py",
    "engine/security.py",
    "engine/resiliency.py",
    "engine/tax_indexation.py",
    "engine/candlesticks_advanced.py",
    "engine/trade_journal.py",
    "engine/ai_engine.py",
    "web_server.py",
    "web/index.html",
    "web/style.css",
    "web/app.js",
]

DEFAULT_BACKEND_MODULES = [
    "engine.indicators",
    "engine.portfolio_optimizer",
    "engine.tax_lots",
    "engine.forensic",
    "engine.macro_regime",
    "engine.macro_shocks",
    "engine.dhan_routing",
    "engine.backtest",
    "engine.security",
    "engine.resiliency",
    "data.database",
    "data.sync_engine",
    "data.microstructure",
    "data.institutional_flow",
    "data.corporate_calendar",
]

SUSPICIOUS_PATTERNS = [
    ("mock", re.compile(r'\bmock(?:ing|ed|s)?\b', re.IGNORECASE)),
    ("dummy", re.compile(r'\bdummy\b', re.IGNORECASE)),
    ("fake", re.compile(r'\bfake\b', re.IGNORECASE)),
    ("placeholder", re.compile(r'\bplaceholder\b', re.IGNORECASE)),
    ("hardcoded", re.compile(r'\bhardcoded?\b', re.IGNORECASE)),
    ("TODO", re.compile(r'\bTODO\b')),
    ("FIXME", re.compile(r'\bFIXME\b')),
    ("XXX", re.compile(r'\bXXX\b')),
    ("sample_data", re.compile(r'\bsample\s+data\b|\bsample_data\b', re.IGNORECASE)),
    ("demo_data", re.compile(r'\bdemo\s+data\b|\bdemo_data\b', re.IGNORECASE)),
    ("static_response", re.compile(r'\bstatic\s+response\b|\bstatic_response\b', re.IGNORECASE)),
    ("fake_response", re.compile(r'\breturn\s*\{\s*["\']status["\']\s*:\s*["\'](?:STUB|FAKE|DUMMY|MOCK|PLACEHOLDER)["\']|\breturn\s*\{\s*["\']stub["\']|\breturn\s*\{\s*["\']fake["\']|\breturn\s*\{\s*["\']mock["\']', re.IGNORECASE)),
]


@dataclass
class AuditResult:
    command: str
    return_code: int
    stdout: str
    stderr: str


@dataclass
class PlaceholderFinding:
    file: str
    line_number: int
    category: str
    matched_text: str
    classification: str
    severity: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RepositoryAuditor:
    """
    Read-only repository inspection and evidence collection layer.

    This component MUST NOT modify project files or execute trading operations.
    """

    def __init__(self, repository_root: str = "."):
        self.root = Path(repository_root).resolve()

    def classify_path(self, path: str | Path) -> str:
        """
        Classifies a file path into an explicit category:
        PRODUCTION, TEST, CONFIG, DOCUMENTATION, CACHE, AI_ORCHESTRATOR, GENERATED, IGNORED.
        """
        path_str = str(path).replace("\\", "/")
        if Path(path_str).is_absolute():
            try:
                path_str = str(Path(path_str).relative_to(self.root)).replace("\\", "/")
            except ValueError:
                pass

        parts = path_str.split("/")
        filename = parts[-1]

        # Explicit exclusions / ignored files and directories
        ignored_names = {
            ".aider.chat.history.md",
            ".aider.input.history",
            "AI_Investment_Command_Center_Task_Tracker.csv",
            "AI_Investment_Command_Center_Master_Repair_Prompt.txt",
            ".DS_Store",
        }
        if filename in ignored_names:
            return "IGNORED"

        ignored_dirs = {".git", "venv", ".venv", "__pycache__", "logs", "scratch"}
        for part in parts:
            if part in ignored_dirs:
                return "IGNORED"

        # Cache classification
        if path_str.startswith("data/cache/") or "data/cache" in path_str or ".aider.tags.cache" in path_str or ".pytest_cache" in path_str:
            return "CACHE"

        # Generated outputs
        if path_str.startswith("reports/") or path_str.endswith(".db") or (path_str.endswith(".csv") and not path_str.startswith("config/")):
            return "GENERATED"

        # AI Orchestrator framework
        if path_str.startswith("ai_orchestrator/") or path_str == "ai_orchestrator":
            if filename.startswith("test_") or filename.endswith("_test.py"):
                return "TEST"
            return "AI_ORCHESTRATOR"

        # Test suites
        if path_str.startswith("tests/") or filename.startswith("test_") or filename.endswith("_test.py"):
            return "TEST"

        # Configuration files
        if path_str.startswith("config/") or filename in ["requirements.txt", ".gitignore"]:
            return "CONFIG"

        # Documentation
        if path_str.endswith(".md") or path_str.endswith(".txt") or filename in ["DESIGN.md", "PROGRESS.md", "ROADMAP.md", "HANDOFF.md"]:
            return "DOCUMENTATION"

        # Production source code
        if (
            path_str.startswith("engine/") or
            (path_str.startswith("data/") and not path_str.startswith("data/cache/")) or
            path_str.startswith("web/") or
            filename == "web_server.py" or
            path_str.endswith(".py") or
            path_str.endswith(".js") or
            path_str.endswith(".html") or
            path_str.endswith(".css")
        ):
            return "PRODUCTION"

        return "IGNORED"

    def _determine_severity(self, classification: str, category: str) -> str:
        if classification == "PRODUCTION":
            if category in ["mock", "dummy", "fake", "fake_response", "placeholder", "demo_data", "sample_data", "static_response"]:
                return "HIGH"
            elif category in ["TODO", "FIXME", "XXX", "hardcoded"]:
                return "MEDIUM"
            return "LOW"
        elif classification == "TEST":
            return "LOW"
        elif classification == "DOCUMENTATION":
            return "INFO"
        return "LOW"

    def run_command(
        self,
        command: List[str],
        timeout: int = 60,
    ) -> AuditResult:
        result = subprocess.run(
            command,
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

        return AuditResult(
            command=" ".join(command),
            return_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    def git_status(self) -> AuditResult:
        return self.run_command(["git", "status", "--short"])

    def repository_tree(self) -> AuditResult:
        return self.run_command(["find", ".", "-maxdepth", "3", "-type", "f"])

    def scan_placeholders(
        self,
        focus_production_only: bool = False,
    ) -> List[PlaceholderFinding]:
        """
        Scans source files for suspicious placeholder patterns with path classification and exclusion filters.
        """
        findings: List[PlaceholderFinding] = []

        for root_dir, dirs, files in os.walk(self.root):
            # Prune ignored directory trees
            dirs[:] = [
                d for d in dirs
                if d not in [".git", "venv", ".venv", "__pycache__", "logs", "scratch", ".aider.tags.cache.v4", ".pytest_cache"]
                and not str(Path(root_dir, d).relative_to(self.root)).replace("\\", "/").startswith("data/cache")
            ]

            for file in files:
                file_path = Path(root_dir) / file
                try:
                    rel_path = str(file_path.relative_to(self.root)).replace("\\", "/")
                except ValueError:
                    rel_path = str(file_path).replace("\\", "/")

                classification = self.classify_path(rel_path)

                if classification in ["IGNORED", "CACHE", "GENERATED"]:
                    continue

                if focus_production_only and classification != "PRODUCTION":
                    continue

                ext = file_path.suffix.lower()
                if ext not in [".py", ".js", ".html", ".css", ".md", ".txt"]:
                    continue

                try:
                    content = file_path.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue

                for line_idx, line in enumerate(content.splitlines(), start=1):
                    for cat, pattern in SUSPICIOUS_PATTERNS:
                        match = pattern.search(line)
                        if match:
                            severity = self._determine_severity(classification, cat)
                            findings.append(
                                PlaceholderFinding(
                                    file=rel_path,
                                    line_number=line_idx,
                                    category=cat,
                                    matched_text=line.strip()[:120],
                                    classification=classification,
                                    severity=severity,
                                )
                            )
                            break

        return findings

    def search_placeholders(self) -> AuditResult:
        findings = self.scan_placeholders()
        lines = [
            f"{f.file}:{f.line_number}: [{f.classification}] [{f.severity}] [{f.category}] {f.matched_text}"
            for f in findings
        ]
        return AuditResult(
            command="scan_placeholders",
            return_code=0,
            stdout="\n".join(lines),
            stderr="",
        )

    def verify_architecture(
        self,
        paths: Optional[List[str]] = None,
    ) -> Dict[str, str]:
        """
        Verifies target architecture paths and reports: EXISTS, MISSING, DIRECTORY, EMPTY.
        """
        target_paths = paths if paths is not None else TARGET_ARCHITECTURE_PATHS
        report: Dict[str, str] = {}

        for rel_path in target_paths:
            target = self.root / rel_path
            if not target.exists():
                report[rel_path] = "MISSING"
            elif target.is_dir():
                report[rel_path] = "DIRECTORY"
            elif target.is_file():
                if target.stat().st_size == 0:
                    report[rel_path] = "EMPTY"
                else:
                    report[rel_path] = "EXISTS"
            else:
                report[rel_path] = "MISSING"

        return report

    def architecture_files(
        self,
        paths: List[str],
    ) -> Dict[str, bool]:
        result = {}
        for path in paths:
            result[path] = (self.root / path).exists()
        return result

    def verify_python_imports(
        self,
        modules: Optional[List[str]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Executes safe read-only Python import verification in isolated subprocesses.
        """
        target_modules = modules if modules is not None else DEFAULT_BACKEND_MODULES
        results: Dict[str, Dict[str, Any]] = {}
        python_bin = sys.executable or "python3"

        for mod in target_modules:
            cmd = [
                python_bin,
                "-c",
                f"import sys; sys.path.insert(0, '{self.root}'); import {mod}; print('IMPORT_OK')"
            ]
            res = self.run_command(cmd, timeout=10)
            is_ok = (res.return_code == 0) and ("IMPORT_OK" in res.stdout)
            results[mod] = {
                "status": "IMPORT_OK" if is_ok else "IMPORT_FAILED",
                "return_code": res.return_code,
                "error": res.stderr.strip() if not is_ok else "",
            }

        return results

    def python_import(
        self,
        module: str,
    ) -> AuditResult:
        return self.run_command(
            [
                sys.executable or "python",
                "-c",
                f"import sys; sys.path.insert(0, '{self.root}'); import {module}; print('IMPORT_OK: {module}')",
            ],
            timeout=60,
        )

    def inspect_file(
        self,
        path: str,
    ) -> str:
        target = self.root / path
        if not target.exists():
            return f"FILE_NOT_FOUND: {path}"
        if not target.is_file():
            return f"NOT_A_FILE: {path}"
        return target.read_text(encoding="utf-8", errors="replace")

    def generate_structured_audit_report(self) -> Dict[str, Any]:
        """
        Generates a complete structured JSON-compatible audit report.
        """
        git_res = self.git_status()
        arch_status = self.verify_architecture()
        import_status = self.verify_python_imports()
        findings = self.scan_placeholders()

        findings_by_classification: Dict[str, int] = {}
        findings_by_severity: Dict[str, int] = {}

        for f in findings:
            findings_by_classification[f.classification] = findings_by_classification.get(f.classification, 0) + 1
            findings_by_severity[f.severity] = findings_by_severity.get(f.severity, 0) + 1

        return {
            "repository_root": str(self.root),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "git_status": {
                "is_clean": len(git_res.stdout.strip()) == 0 if git_res.return_code == 0 else False,
                "stdout": git_res.stdout,
                "stderr": git_res.stderr,
            },
            "architecture_verification": arch_status,
            "import_verification": import_status,
            "placeholder_findings": [f.to_dict() for f in findings],
            "summary": {
                "total_findings": len(findings),
                "findings_by_classification": findings_by_classification,
                "findings_by_severity": findings_by_severity,
                "architecture_missing_count": sum(1 for status in arch_status.values() if status == "MISSING"),
                "architecture_empty_count": sum(1 for status in arch_status.values() if status == "EMPTY"),
                "import_failure_count": sum(1 for info in import_status.values() if info["status"] != "IMPORT_OK"),
            },
        }

    def run_basic_audit(self) -> List[AuditResult]:
        return [
            self.git_status(),
            self.repository_tree(),
            self.search_placeholders(),
        ]
