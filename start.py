#!/usr/bin/env python3
"""
start.py - Swing Trading System Master Launcher Script
One-command startup script: builds static assets, launches FastAPI server, and opens Web UI in browser.

Usage:
    python start.py
"""

import sys
import os
import subprocess
import time
import webbrowser
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
VENV_PYTHON = PROJECT_ROOT / "venv" / "bin" / "python"

def main():
    print("=" * 70)
    print("🚀 LAUNCHING SWING TRADING SYSTEM AI COMMAND CENTER")
    print("=" * 70)

    # 1. Select Python Interpreter
    python_cmd = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable
    print(f"[1/4] Using Python interpreter: {python_cmd}")

    # 2. Build / Minify Static Assets
    print("[2/4] Building static web assets...")
    build_script = PROJECT_ROOT / "web" / "build_assets.py"
    if build_script.exists():
        try:
            res = subprocess.run([python_cmd, str(build_script)], capture_output=True, text=True)
            if res.returncode == 0:
                print("      ✅ Static assets built and minified successfully.")
            else:
                print(f"      ⚠️ Asset minifier notice: {res.stderr.strip()[:100]}")
        except Exception as err:
            print(f"      ⚠️ Asset build warning: {err}")

    # 3. Schedule Browser Auto-Open
    def open_browser():
        time.sleep(1.5)
        url = "http://localhost:8000"
        print(f"\n🌐 Opening Swing Trading Command Center in Browser: {url}")
        try:
            webbrowser.open(url)
        except Exception:
            pass

    import threading
    threading.Thread(target=open_browser, daemon=True).start()

    # 4. Start Uvicorn Web Server
    print("[3/4] Starting Uvicorn FastAPI Server on http://0.0.0.0:8000...")
    print("[4/4] Click 'RUN MAIN PIPELINE' button in UI to execute python main.py dynamically!")
    print("-" * 70)

    server_cmd = [
        python_cmd, "-m", "uvicorn", "web_server:app",
        "--host", "0.0.0.0",
        "--port", "8000",
        "--reload"
    ]

    try:
        subprocess.run(server_cmd, cwd=str(PROJECT_ROOT))
    except KeyboardInterrupt:
        print("\n\n🛑 Swing Trading System server stopped cleanly.")

if __name__ == "__main__":
    main()
