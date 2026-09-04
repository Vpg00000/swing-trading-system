"""
Ollama provider — local model health check and availability probe.

This module does NOT wrap litellm.completion() directly.
The ModelRouter already handles that via litellm.
This module only provides:
  - health_check()   — is Ollama reachable at localhost:11434?
  - list_models()    — what models are installed?
  - is_model_ready() — is a specific model name available?

The router calls litellm.completion(model="ollama/<name>", ...)
which routes to the Ollama REST API automatically via litellm's
Ollama integration. No additional wrapping needed here.
"""

from __future__ import annotations

import json
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import List

OLLAMA_BASE_URL = "http://localhost:11434"


@dataclass
class OllamaModel:
    name: str
    size_gb: float
    modified: str


class OllamaProvider:
    """
    Utility class for probing Ollama availability before routing calls to it.
    Used by run.py's startup check and the health endpoint.
    """

    def __init__(self, base_url: str = OLLAMA_BASE_URL):
        self.base_url = base_url.rstrip("/")

    def health_check(self) -> tuple[bool, str]:
        """
        Returns (is_healthy: bool, message: str).
        Pings GET /  — Ollama returns 'Ollama is running' on success.
        """
        try:
            req = urllib.request.Request(
                f"{self.base_url}/",
                headers={"Accept": "text/plain"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                if "ollama" in body.lower() or resp.status == 200:
                    return True, f"Ollama reachable at {self.base_url}"
                return False, f"Unexpected response: {body[:80]}"
        except urllib.error.URLError as exc:
            return False, f"Connection failed: {exc.reason}"
        except Exception as exc:
            return False, f"Health check error: {exc}"

    def list_models(self) -> List[OllamaModel]:
        """
        Calls GET /api/tags to list installed models.
        Returns empty list if Ollama is not reachable.
        """
        try:
            req = urllib.request.Request(
                f"{self.base_url}/api/tags",
                headers={"Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                models = []
                for m in data.get("models", []):
                    size_bytes = m.get("size", 0)
                    models.append(OllamaModel(
                        name=m.get("name", ""),
                        size_gb=round(size_bytes / (1024 ** 3), 1),
                        modified=m.get("modified_at", "")[:10],
                    ))
                return models
        except Exception:
            return []

    def is_model_ready(self, model_name: str) -> bool:
        """
        Returns True if a model with the given name is installed.
        model_name can be bare ('qwen2.5-coder:7b') or prefixed ('ollama/qwen2.5-coder:7b').
        """
        bare = model_name.removeprefix("ollama/")
        installed = self.list_models()
        return any(m.name == bare or m.name.startswith(bare.split(":")[0]) for m in installed)
