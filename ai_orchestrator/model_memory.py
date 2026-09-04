"""
Model Performance Memory — empirical performance tracker.

Records empirical telemetry for every model invocation:
  - Latency (ms)
  - Success vs Failure rate
  - JSON validity rate (valid JSON vs raw/malformed)
  - Syntax validity rate (AST parse pass rate for code)
  - Test pass rate of generated fixes
  - Human approval / correction rate

Persists to `ai_orchestrator/model_performance.json` across runs.
Used by `router.py` to dynamically adjust model routing scores.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

_MEMORY_FILE = Path(__file__).resolve().parent / "model_performance.json"


class ModelPerformanceMemory:
    """
    File-backed telemetry tracker for empirical AI model performance.
    """

    def __init__(self, memory_file: Path = _MEMORY_FILE):
        self._path = memory_file
        self._data: Dict[str, Dict[str, Any]] = self._load()

    def _load(self) -> Dict[str, Dict[str, Any]]:
        if self._path.exists():
            try:
                return json.loads(self._path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _save(self) -> None:
        self._path.write_text(
            json.dumps(self._data, indent=2), encoding="utf-8"
        )

    def _entry(self, model_id: str, task_type: str) -> Dict[str, Any]:
        key = f"{model_id}::{task_type}"
        if key not in self._data:
            self._data[key] = {
                "model_id": model_id,
                "task_type": task_type,
                "total_calls": 0,
                "successful_calls": 0,
                "failed_calls": 0,
                "json_valid_calls": 0,
                "syntax_valid_calls": 0,
                "test_pass_calls": 0,
                "human_approvals": 0,
                "total_latency_ms": 0.0,
                "last_updated": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        return self._data[key]

    def record_call(
        self,
        model_id: str,
        task_type: str,
        latency_ms: float,
        success: bool,
        json_valid: Optional[bool] = None,
        syntax_valid: Optional[bool] = None,
        test_passed: Optional[bool] = None,
        human_approved: Optional[bool] = None,
    ) -> None:
        """
        Record a model invocation result.
        """
        entry = self._entry(model_id, task_type)
        entry["total_calls"] += 1
        if success:
            entry["successful_calls"] += 1
        else:
            entry["failed_calls"] += 1

        entry["total_latency_ms"] += latency_ms

        if json_valid is True:
            entry["json_valid_calls"] += 1
        if syntax_valid is True:
            entry["syntax_valid_calls"] += 1
        if test_passed is True:
            entry["test_pass_calls"] += 1
        if human_approved is True:
            entry["human_approvals"] += 1

        entry["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self._save()

    def get_empirical_score(self, model_id: str, task_type: str) -> float:
        """
        Returns an empirical quality score (0.0 to 1.0) based on historical telemetry.
        If fewer than 3 calls recorded, returns default baseline 0.75.
        """
        key = f"{model_id}::{task_type}"
        if key not in self._data:
            return 0.75

        entry = self._data[key]
        total = entry["total_calls"]
        if total < 3:
            return 0.75

        success_rate = entry["successful_calls"] / total
        avg_latency_sec = (entry["total_latency_ms"] / total) / 1000.0
        latency_penalty = max(0.0, min(0.2, avg_latency_sec / 60.0))

        json_rate = (
            entry["json_valid_calls"] / total
            if entry["json_valid_calls"] > 0
            else 0.8
        )
        syntax_rate = (
            entry["syntax_valid_calls"] / total
            if entry["syntax_valid_calls"] > 0
            else 0.8
        )

        score = (
            0.40 * success_rate
            + 0.30 * json_rate
            + 0.30 * syntax_rate
            - latency_penalty
        )
        return max(0.1, min(1.0, score))

    def summary(self) -> List[Dict[str, Any]]:
        """Return formatted summary table of all recorded telemetry."""
        rows = []
        for key, entry in self._data.items():
            total = entry["total_calls"]
            avg_lat = (
                entry["total_latency_ms"] / total
                if total > 0
                else 0
            )
            rows.append({
                "model_id": entry["model_id"],
                "task_type": entry["task_type"],
                "calls": total,
                "success_pct": round(
                    (entry["successful_calls"] / total) * 100, 1
                )
                if total > 0
                else 0.0,
                "avg_latency_s": round(avg_lat / 1000.0, 2),
                "empirical_score": round(
                    self.get_empirical_score(
                        entry["model_id"], entry["task_type"]
                    ),
                    2,
                ),
            })
        return sorted(rows, key=lambda r: r["calls"], reverse=True)
