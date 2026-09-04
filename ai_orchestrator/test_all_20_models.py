"""
Diagnostic utility to test all 20+ model targets in `ai_orchestrator/models.yaml`.

Checks API key environment variables, queries Ollama endpoints, calls litellm completion,
and outputs a formatted summary table of all 20 models.

Usage:
    python ai_orchestrator/test_all_20_models.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# Add ai_orchestrator to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml
import litellm

litellm.suppress_debug_info = True


def load_env_file():
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())


def audit_20_models():
    load_env_file()
    yaml_path = Path(__file__).resolve().parent / "models.yaml"
    if not yaml_path.exists():
        print(f"Error: {yaml_path} not found.")
        return

    with open(yaml_path, "r", encoding="utf-8") as fh:
        config = yaml.safe_load(fh) or {}

    models = config.get("models", [])
    print(f"\n================================================================")
    print(f"  AI CONTROL PLANE — 20 MODEL TARGET AUDIT")
    print(f"================================================================")
    print(f"  Total models configured in YAML: {len(models)}")
    print(f"================================================================\n")

    print(f"{'#':<3} {'MODEL ID':<24} {'PROVIDER':<12} {'ENABLED':<8} {'KEY STATUS':<18} {'TEST RESULT':<18} {'LATENCY'}")
    print("-" * 95)

    for i, m in enumerate(models, 1):
        mid = m["id"]
        provider = m.get("provider", "unknown")
        enabled = m.get("enabled", False)
        is_local = m.get("local", False)
        env_var = m.get("api_key_env")

        # Key Status
        if is_local:
            key_status = "LOCAL (No Key)"
        elif env_var:
            val = os.environ.get(env_var)
            key_status = f"SET ({val[:3]}...{val[-2:]})" if val else f"MISSING ({env_var})"
        else:
            key_status = "DEFAULT"

        enabled_str = "YES" if enabled else "NO (Disabled)"

        # Run Live Test Call if Enabled
        test_res = "SKIPPED"
        latency_str = "-"

        if enabled:
            t0 = time.time()
            try:
                model_name = m["model"]
                resp = litellm.completion(
                    model=model_name,
                    messages=[{"role": "user", "content": "Reply READY"}],
                    timeout=m.get("max_timeout_seconds", 30),
                )
                dt = round((time.time() - t0) * 1000)
                txt = (resp.choices[0].message.content or "").strip().replace("\n", " ")
                test_res = f"PASSED ({txt[:10]})"
                latency_str = f"{dt}ms"
            except Exception as exc:
                err = str(exc)
                if "401" in err or "key" in err.lower():
                    test_res = "AUTH_FAIL"
                elif "503" in err or "demand" in err.lower():
                    test_res = "OVERLOAD_503"
                elif "429" in err or "quota" in err.lower():
                    test_res = "RATE_LIMIT_429"
                elif "connection" in err.lower():
                    test_res = "CONN_FAIL"
                else:
                    test_res = f"FAIL ({err[:12]})"

        print(f"{i:<3} {mid:<24} {provider:<12} {enabled_str:<8} {key_status:<18} {test_res:<18} {latency_str}")

    print("\n================================================================")
    print("  SUMMARY: To activate any missing provider, set its API key in ~/.zshrc")
    print("  and flip `enabled: true` in ai_orchestrator/models.yaml.")
    print("================================================================\n")


if __name__ == "__main__":
    audit_20_models()
