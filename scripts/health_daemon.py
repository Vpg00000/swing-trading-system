"""
scripts/health_daemon.py - System Health Auto-Recovery Daemon.

Task T-313: Build System Health Auto-Recovery daemon that monitors memory leaks,
thread deadlocks, and server unresponsiveness, and automatically restarts the server when needed.
"""

import os
import sys
import time
import json
import logging
import argparse
import subprocess
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, Any, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [HealthDaemon] %(message)s"
)
logger = logging.getLogger("HealthDaemon")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SERVER_URL = os.getenv("HEALTH_CHECK_URL", "http://localhost:8000/health")
MEMORY_LIMIT_MB = int(os.getenv("HEALTH_MAX_MEMORY_MB", "1024"))
CHECK_INTERVAL_SEC = int(os.getenv("HEALTH_CHECK_INTERVAL", "15"))
MAX_FAILURES = 3

_CONSECUTIVE_FAILURES = 0


def get_server_memory_mb() -> float:
    """Gets memory usage (RSS MB) of the running web_server process."""
    try:
        import psutil
        for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'memory_info']):
            cmdline = " ".join(proc.info['cmdline'] or [])
            if "web_server" in cmdline or "uvicorn" in cmdline:
                mem_bytes = proc.info['memory_info'].rss
                return mem_bytes / (1024 * 1024)
    except Exception:
        # Fallback using ps command on Linux/macOS
        try:
            out = subprocess.check_output(["ps", "aux"]).decode("utf-8")
            for line in out.splitlines():
                if "web_server" in line or "uvicorn" in line:
                    parts = line.split()
                    if len(parts) >= 6:
                        rss_kb = float(parts[5])
                        return rss_kb / 1024
        except Exception:
            pass
    return 0.0


def check_server_health() -> Dict[str, Any]:
    """Pings server health check endpoint and returns status."""
    try:
        req = urllib.request.Request(SERVER_URL, headers={"User-Agent": "SystemHealthDaemon/1.0"})
        start_time = time.time()
        with urllib.request.urlopen(req, timeout=5) as response:
            latency_ms = (time.time() - start_time) * 1000
            status_code = response.getcode()
            body = response.read().decode("utf-8")
            return {
                "healthy": (status_code == 200),
                "status_code": status_code,
                "latency_ms": round(latency_ms, 2),
                "response": body[:200]
            }
    except Exception as exc:
        return {
            "healthy": False,
            "error": str(exc),
            "status_code": 503,
            "latency_ms": 0.0
        }


def restart_server() -> bool:
    """Executes server auto-restart on memory leak, deadlock, or crash."""
    logger.warning("🚨 INITIATING SERVER AUTO-RECOVERY RESTART...")

    # Check if running in Docker container
    if os.path.exists("/.dockerenv"):
        try:
            subprocess.run(["pkill", "-f", "uvicorn"], check=False)
            subprocess.run(["python3", "web_server.py"], cwd=str(PROJECT_ROOT))
            logger.info("Restarted process in Docker container.")
            return True
        except Exception as exc:
            logger.error(f"Failed to restart container process: {exc}")
            return False

    # Standard process restart
    try:
        subprocess.run(["pkill", "-f", "web_server.py"], check=False)
        time.sleep(2)
        subprocess.Popen([sys.executable, "web_server.py"], cwd=str(PROJECT_ROOT))
        logger.info("Server process restarted successfully.")
        return True
    except Exception as exc:
        logger.error(f"Auto-recovery restart failed: {exc}")
        return False


def run_health_cycle() -> Dict[str, Any]:
    """Single health monitoring & auto-recovery iteration."""
    global _CONSECUTIVE_FAILURES

    health = check_server_health()
    mem_mb = get_server_memory_mb()

    is_healthy = health["healthy"]
    is_memory_ok = (mem_mb <= MEMORY_LIMIT_MB) if mem_mb > 0 else True

    status_report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "server_healthy": is_healthy,
        "memory_mb": round(mem_mb, 2),
        "memory_limit_mb": MEMORY_LIMIT_MB,
        "latency_ms": health.get("latency_ms", 0),
        "consecutive_failures": _CONSECUTIVE_FAILURES,
        "auto_recovery_triggered": False
    }

    if not is_healthy:
        _CONSECUTIVE_FAILURES += 1
        logger.warning(f"Health check failed ({_CONSECUTIVE_FAILURES}/{MAX_FAILURES}): {health.get('error', 'Status ' + str(health.get('status_code')))}")
    elif not is_memory_ok:
        logger.warning(f"Memory leak detected! Server using {mem_mb:.2f} MB (Threshold: {MEMORY_LIMIT_MB} MB)")
        _CONSECUTIVE_FAILURES = MAX_FAILURES  # Trigger immediate restart
    else:
        _CONSECUTIVE_FAILURES = 0
        logger.info(f"System Healthy 🟢 | Memory: {mem_mb:.1f}MB | Response Time: {health.get('latency_ms')}ms")

    if _CONSECUTIVE_FAILURES >= MAX_FAILURES:
        logger.error(f"Unhealthy threshold reached ({_CONSECUTIVE_FAILURES} failures). Triggering recovery.")
        restarted = restart_server()
        _CONSECUTIVE_FAILURES = 0
        status_report["auto_recovery_triggered"] = True
        status_report["restart_success"] = restarted

    return status_report


def main():
    parser = argparse.ArgumentParser(description="System Health Auto-Recovery Daemon")
    parser.add_argument("--check-once", action="store_true", help="Run a single health check cycle and exit")
    args = parser.parse_args()

    if args.check_once:
        report = run_health_cycle()
        print(json.dumps(report, indent=2))
        sys.exit(0 if report["server_healthy"] else 1)

    logger.info(f"Starting System Health Auto-Recovery Daemon (Target: {SERVER_URL}, Max Memory: {MEMORY_LIMIT_MB}MB)")
    while True:
        try:
            run_health_cycle()
        except Exception as exc:
            logger.error(f"Daemon cycle error: {exc}")
        time.sleep(CHECK_INTERVAL_SEC)


if __name__ == "__main__":
    main()
