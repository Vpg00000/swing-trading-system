"""
Fix Memory — persistent knowledge base storing bug signatures, root causes,
applied patches, and validation outcomes.

Persists to `ai_orchestrator/fix_memory.json`. Prevents repeating past mistakes.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

_FIX_MEMORY_FILE = Path(__file__).resolve().parent / "fix_memory.json"


class FixMemory:
    def __init__(self, memory_file: Path = _FIX_MEMORY_FILE):
        self._path = memory_file
        self._data: List[Dict[str, Any]] = self._load()

    def _load(self) -> List[Dict[str, Any]]:
        if self._path.exists():
            try:
                return json.loads(self._path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return []

    def _save(self) -> None:
        self._path.write_text(
            json.dumps(self._data, indent=2), encoding="utf-8"
        )

    def record_fix(
        self,
        issue_id: str,
        file_path: str,
        error_signature: str,
        root_cause: str,
        patch_summary: str,
        test_outcome: str,  # "PASS" | "FAIL"
        confidence_score: float,
    ) -> None:
        entry = {
            "issue_id": issue_id,
            "file_path": file_path,
            "error_signature": error_signature[:200],
            "root_cause": root_cause,
            "patch_summary": patch_summary,
            "test_outcome": test_outcome,
            "confidence_score": confidence_score,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        self._data.append(entry)
        self._save()

    def find_similar_fix(self, file_path: str, error_signature: str) -> Optional[Dict[str, Any]]:
        """
        Finds previous successful fixes matching the target file or error signature.
        """
        for entry in reversed(self._data):
            if entry.get("test_outcome") == "PASS":
                if entry.get("file_path") == file_path or entry.get("error_signature") in error_signature:
                    return entry
        return None

    def list_history(self) -> List[Dict[str, Any]]:
        return self._data
