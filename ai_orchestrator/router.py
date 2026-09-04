"""
Multi-Provider AI Router — dynamic scoring + quota-aware model selection.

Backward-compatible upgrade of the original router.py.
The existing interface complete(role, messages) works unchanged.
New interface: complete(role, messages, task_type="coding") routes
to the best model for the specific task.

Dynamic score per candidate:
    effective_score =
        base_priority          (from models.yaml, 0–100)
      × quality_for_task       (task-specific quality, 0.0–1.0)
      × quota_score            (0.0 if exhausted, 1.0 if unlimited/fresh)
      × availability_score     (0.0 if in cooldown, 1.0 if healthy)

Privacy rule: task_type="private" ONLY routes to models where private=true.
This ensures portfolio/account data never leaves the local machine.

Task types (for routing to the right model tier):
    coding       →  Ollama first, then Qwen/Mistral, then Gemini
    planning     →  Gemini first, then DeepSeek, then Ollama
    reviewing    →  Gemini/Groq first, then Ollama
    research     →  Gemini/DeepSeek, huge context needed
    classification → Groq first (ultra-fast), then Ollama
    triage       →  Groq/Ollama (fast, cheap, bulk)
    private      →  LOCAL ONLY (never cloud) — portfolio data
    escalation   →  Any available, highest-quality first
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import litellm
import yaml

# Load .env file automatically
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    with open(_env_path, "r", encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

# Suppress litellm's verbose output that's not actionable
litellm.suppress_debug_info = True

try:
    from quota import QuotaTracker
    _quota_tracker = QuotaTracker()
except Exception:
    _quota_tracker = None  # graceful degradation if quota.py missing


try:
    from model_memory import ModelPerformanceMemory
    _model_memory = ModelPerformanceMemory()
except Exception:
    _model_memory = None


# ─────────────────────────────────────────────────────────────────────────────
# Model state
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ModelState:
    model_id: str
    failures: int = 0
    successes: int = 0
    cooldown_until: float = 0.0
    last_error: str | None = None
    last_error_type: str | None = None

    @property
    def healthy(self) -> bool:
        return time.time() >= self.cooldown_until

    @property
    def availability_score(self) -> float:
        """1.0 if healthy, 0.0 if in cooldown."""
        return 1.0 if self.healthy else 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Router
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ModelRouter:
    config_path: str = "ai_orchestrator/models.yaml"
    states: dict[str, ModelState] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._load_config()

    # ── Config ────────────────────────────────────────────────────────────

    def _load_config(self) -> None:
        with open(self.config_path, "r", encoding="utf-8") as fh:
            config = yaml.safe_load(fh) or {}

        self.models = [
            m for m in config.get("models", [])
            if m.get("enabled", False)
        ]

        # Validate API keys — disable models whose provider key is absent
        self.models = [m for m in self.models if self._has_api_key(m)]

        for model in self.models:
            mid = model["id"]
            if mid not in self.states:
                self.states[mid] = ModelState(model_id=mid)

    def _has_api_key(self, model: dict) -> bool:
        """
        Returns True if the provider's required API key is set in env.
        Local models (Ollama) are always True.
        Unknown providers pass through (litellm handles them).
        """
        if model.get("local", False):
            return True
        env_var = model.get("api_key_env")
        if env_var:
            return bool(os.environ.get(env_var))
        # If no env_var specified, let litellm try (uses provider defaults)
        return True

    # ── Dynamic scoring ───────────────────────────────────────────────────

    def _quality_score(self, model: dict, task_type: Optional[str]) -> float:
        """
        Returns 0.0–1.0 quality score combining declared profile + empirical memory.
        """
        t_type = task_type or "general"
        quality_map: dict = model.get("quality", {})
        if t_type in quality_map:
            declared = float(quality_map[t_type])
        else:
            declared = float(model.get("base_quality", model.get("priority", 50) / 100.0))

        if _model_memory is not None:
            emp = _model_memory.get_empirical_score(model["id"], t_type)
            return round(0.50 * declared + 0.50 * emp, 2)

        return declared

    def _quota_score(self, model: dict) -> float:
        """Returns 0.0–1.0 quota availability for this model's provider."""
        if _quota_tracker is None:
            return 1.0
        provider = model.get("provider", model["id"])
        daily_limit = model.get("daily_limit", "unlimited")
        return _quota_tracker.score(provider, daily_limit)

    def _effective_score(
        self, model: dict, task_type: Optional[str]
    ) -> float:
        """
        Combined score: priority × quality × quota × availability
        Range: 0.0 (unusable) to 100.0 (perfect).
        """
        state = self.states[model["id"]]
        return (
            model.get("priority", 50)
            * self._quality_score(model, task_type)
            * self._quota_score(model)
            * state.availability_score
        )

    # ── Selection ─────────────────────────────────────────────────────────

    def select_all(
        self,
        role: str,
        task_type: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """
        Return all healthy, quota-available models for a role,
        sorted by effective score (best first).

        Privacy rule: if task_type == "private", only private=true models.
        """
        candidates = []

        for model in self.models:
            # Role match
            if role not in model.get("role", []):
                continue

            # Privacy enforcement: private tasks → local only
            if task_type == "private" and not model.get("private", False):
                continue

            # Quota check: skip completely exhausted models
            if self._quota_score(model) == 0.0:
                continue

            # Availability (cooldown) check
            state = self.states[model["id"]]
            if not state.healthy:
                continue

            candidates.append(model)

        # Sort by effective score descending
        candidates.sort(
            key=lambda m: self._effective_score(m, task_type),
            reverse=True,
        )
        return candidates

    def select(
        self,
        role: str,
        task_type: Optional[str] = None,
    ) -> dict[str, Any]:
        candidates = self.select_all(role, task_type)
        if not candidates:
            raise RuntimeError(
                f"No healthy model available for role={role}"
                + (f", task_type={task_type}" if task_type else "")
            )
        return candidates[0]

    # ── Error classification ──────────────────────────────────────────────

    @staticmethod
    def _classify_error(exc: Exception) -> str:
        text = str(exc).lower()
        if any(k in text for k in ("429", "rate limit", "ratelimit", "quota", "resource_exhausted")):
            return "QUOTA_OR_RATE_LIMIT"
        if any(k in text for k in ("timeout", "timed out", "readtimeout")):
            return "TIMEOUT"
        if any(k in text for k in ("connection refused", "connection error", "connecterror")):
            return "CONNECTION_ERROR"
        if any(k in text for k in ("503", "502", "500", "service unavailable", "high demand")):
            return "PROVIDER_ERROR"
        if any(k in text for k in ("401", "403", "authentication", "api key")):
            return "AUTHENTICATION_ERROR"
        if "404" in text:
            return "MODEL_NOT_FOUND"
        return "UNKNOWN_ERROR"

    @staticmethod
    def _cooldown_for(error_type: str, failures: int) -> int:
        if error_type in ("QUOTA_OR_RATE_LIMIT", "AUTHENTICATION_ERROR"):
            return 3600
        if error_type == "MODEL_NOT_FOUND":
            return 86400  # disable for 24h — model doesn't exist
        if error_type == "CONNECTION_ERROR":
            return min(300, 15 * (2 ** min(failures - 1, 4)))
        if error_type in ("TIMEOUT", "PROVIDER_ERROR"):
            return min(300, 30 * (2 ** min(failures - 1, 3)))
        return min(600, 30 * (2 ** min(failures - 1, 4)))

    def _mark_failure(self, model_id: str, exc: Exception) -> str:
        state = self.states[model_id]
        state.failures += 1
        state.last_error = str(exc)
        error_type = self._classify_error(exc)
        state.last_error_type = error_type
        state.cooldown_until = time.time() + self._cooldown_for(
            error_type, state.failures
        )
        return error_type

    def _mark_success(self, model_id: str, provider: str) -> None:
        state = self.states[model_id]
        state.successes += 1
        state.last_error = None
        state.last_error_type = None
        state.cooldown_until = 0.0
        # Increment quota counter
        if _quota_tracker and provider:
            _quota_tracker.increment(provider)

    # ── Completion ────────────────────────────────────────────────────────

    def complete(
        self,
        role: str,
        messages: list[dict[str, str]],
        task_type: Optional[str] = None,
    ) -> str:
        """
        Try each candidate model in effective-score order.
        Returns the first successful response.

        Args:
            role:      Model role key (e.g. "coder", "planner")
            messages:  OpenAI-format message list
            task_type: Optional task type for smarter routing
                       ("coding", "planning", "research", "private", ...)
        """
        candidates = self.select_all(role, task_type)

        if not candidates:
            raise RuntimeError(
                f"No healthy model available for role={role}"
                + (f", task_type={task_type}" if task_type else "")
            )

        failures: list[str] = []

        for model in candidates:
            model_id = model["id"]
            model_name = model["model"]
            provider = model.get("provider", model_id)
            timeout = model.get("max_timeout_seconds", 120)

            score = self._effective_score(model, task_type)
            print(
                f"[ROUTER] → {model_id}"
                f"  score={score:.1f}"
                f"  role={role}"
                + (f"  task={task_type}" if task_type else "")
            )

            try:
                response = litellm.completion(
                    model=model_name,
                    messages=messages,
                    timeout=timeout,
                )

                content = (response.choices[0].message.content or "").strip()
                if not content:
                    raise RuntimeError("Model returned empty response")

                self._mark_success(model_id, provider)
                print(f"[ROUTER] ✓ {model_id}")
                return content

            except Exception as exc:
                error_type = self._mark_failure(model_id, exc)
                failures.append(
                    f"{model_id}: {error_type}: {str(exc)[:200]}"
                )
                print(f"[ROUTER] ✗ {model_id} ({error_type}) → trying next")
                continue

        raise RuntimeError(
            f"All models failed for role={role}.\n" + "\n".join(failures)
        )

    # ── Status reporting ──────────────────────────────────────────────────

    def status(self) -> list[dict[str, Any]]:
        now = time.time()
        result = []
        for model in self.models:
            state = self.states[model["id"]]
            remaining_cooldown = max(0, int(state.cooldown_until - now))
            quota_score = self._quota_score(model)
            provider = model.get("provider", model["id"])
            used_today = (
                _quota_tracker.requests_today(provider)
                if _quota_tracker else 0
            )
            result.append({
                "id": model["id"],
                "model": model["model"],
                "roles": model.get("role", []),
                "task_types": model.get("task_types", []),
                "priority": model.get("priority", 0),
                "enabled": True,  # already filtered
                "free": model.get("free", False),
                "local": model.get("local", False),
                "private": model.get("private", False),
                "healthy": state.healthy,
                "failures": state.failures,
                "successes": state.successes,
                "cooldown_seconds": remaining_cooldown,
                "last_error_type": state.last_error_type,
                "quota_score": round(quota_score, 2),
                "requests_today": used_today,
                "daily_limit": model.get("daily_limit", "unlimited"),
            })
        return result