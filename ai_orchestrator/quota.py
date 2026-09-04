"""
Quota Tracker — per-provider daily request counting.

Tracks how many API calls have been made to each provider today.
Resets at midnight local time. Persists to quota.json between runs.

Usage:
    from quota import QuotaTracker
    qt = QuotaTracker()
    score = qt.score("gemini", daily_limit=1500)   # 0.0 – 1.0
    qt.increment("gemini")                          # call after success

Score meaning:
    1.0  →  >80% quota remaining (use freely)
    0.8  →  50–80% remaining
    0.5  →  20–50% remaining (start conserving)
    0.2  →  5–20% remaining  (high-value tasks only)
    0.0  →  <5% remaining    (treat as exhausted)
    1.0  →  unlimited daily_limit (local Ollama etc.)
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Union

_QUOTA_FILE = Path(__file__).resolve().parent / "quota.json"
_UNLIMITED = "unlimited"


class QuotaTracker:
    """
    File-backed daily request counter per provider.
    Thread-safe enough for single-process use (no async concern here).
    """

    def __init__(self, quota_file: Path = _QUOTA_FILE):
        self._path = quota_file
        self._data = self._load()

    # ── Persistence ───────────────────────────────────────────────────────

    def _load(self) -> dict:
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

    # ── Per-provider state ────────────────────────────────────────────────

    def _today(self) -> str:
        return date.today().isoformat()

    def _provider_data(self, provider_id: str) -> dict:
        today = self._today()
        entry = self._data.get(provider_id, {})
        # Reset if new day
        if entry.get("date") != today:
            entry = {"date": today, "requests": 0}
            self._data[provider_id] = entry
        return entry

    # ── Public API ────────────────────────────────────────────────────────

    def increment(self, provider_id: str) -> None:
        """Call this after every successful API call to this provider."""
        entry = self._provider_data(provider_id)
        entry["requests"] = entry.get("requests", 0) + 1
        self._data[provider_id] = entry
        self._save()

    def requests_today(self, provider_id: str) -> int:
        """How many requests have been made today to this provider."""
        return self._provider_data(provider_id).get("requests", 0)

    def score(
        self,
        provider_id: str,
        daily_limit: Union[int, str],
    ) -> float:
        """
        Returns a 0.0–1.0 availability score based on quota remaining.

        - unlimited  → always 1.0
        - >80% left  → 1.0 (use freely)
        - 50–80%     → 0.8
        - 20–50%     → 0.5
        - 5–20%      → 0.2 (conserve — only high-value tasks)
        - <5%        → 0.0 (treat as exhausted)
        """
        if daily_limit == _UNLIMITED or daily_limit == 0:
            return 1.0

        used = self.requests_today(provider_id)
        if daily_limit <= 0:
            return 1.0

        remaining_pct = max(0.0, 1.0 - (used / daily_limit))

        if remaining_pct > 0.80:
            return 1.0
        elif remaining_pct > 0.50:
            return 0.8
        elif remaining_pct > 0.20:
            return 0.5
        elif remaining_pct > 0.05:
            return 0.2
        else:
            return 0.0

    def summary(self) -> list[dict]:
        """Return usage summary for all tracked providers today."""
        today = self._today()
        rows = []
        for pid, entry in self._data.items():
            if entry.get("date") == today:
                rows.append({
                    "provider": pid,
                    "requests_today": entry.get("requests", 0),
                    "date": today,
                })
        return sorted(rows, key=lambda r: r["requests_today"], reverse=True)
