#!/usr/bin/env bash
# start.sh - One-command shell launcher for Swing Trading System
set -e
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
if [ -d "$DIR/venv" ]; then
    PYTHON="$DIR/venv/bin/python"
else
    PYTHON="python3"
fi

echo "🚀 Starting Swing Trading System AI Command Center..."
"$PYTHON" "$DIR/start.py"
