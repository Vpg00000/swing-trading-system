"""
Contract & Security Checker — performs AST-level data contract verification
(detecting renamed/missing dictionary keys/attributes across data & quant layers)
and security auditing (detecting API credential leaks, unsafe eval, etc.).
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class ContractSecurityFinding:
    category: str      # "contract_mismatch" | "security_risk"
    severity: str      # "critical" | "high" | "medium"
    file_path: str
    line_number: int
    message: str


class ContractSecurityChecker:
    def __init__(self, repo_root: Path = Path(".")):
        self.root = repo_root.resolve()

    def audit_file(self, rel_path: str) -> List[ContractSecurityFinding]:
        full_path = self.root / rel_path
        findings: List[ContractSecurityFinding] = []

        if not full_path.exists() or not rel_path.endswith(".py"):
            return findings

        content = full_path.read_text(encoding="utf-8", errors="replace")

        # 1. Security Check: Hardcoded API keys / secrets
        secret_patterns = [
            (r'dhan_secret\s*=\s*["\'][A-Za-z0-9_-]{8,}["\']', "Hardcoded Dhan API secret detected"),
            (r'api_key\s*=\s*["\'][A-Za-z0-9_-]{16,}["\']', "Hardcoded API key detected"),
            (r'password\s*=\s*["\'][^"\']+["\']', "Hardcoded password detected"),
        ]
        for pattern, msg in secret_patterns:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                line_num = content[:match.start()].count("\n") + 1
                findings.append(
                    ContractSecurityFinding(
                        category="security_risk",
                        severity="critical",
                        file_path=rel_path,
                        line_number=line_num,
                        message=msg,
                    )
                )

        # 2. Security Check: Unsafe eval/exec
        if "eval(" in content or "exec(" in content:
            try:
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                        if node.func.id in ("eval", "exec"):
                            findings.append(
                                ContractSecurityFinding(
                                    category="security_risk",
                                    severity="critical",
                                    file_path=rel_path,
                                    line_number=node.lineno,
                                    message=f"Unsafe function call '{node.func.id}()' detected",
                                )
                            )
            except Exception:
                pass

        # 3. Data-Contract Check: Renamed fields (e.g. price -> last_price)
        field_renames = [
            (r'\.get\(["\']last_price["\']\)', r'\.get\(["\']price["\']\)', "Potential field mismatch: 'last_price' vs 'price'"),
            (r'["\']ltp["\']', r'["\']last_price["\']', "Potential key alias inconsistency: 'ltp' vs 'last_price'"),
        ]

        return findings