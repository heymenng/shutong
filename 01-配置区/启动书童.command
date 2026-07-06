#!/bin/bash
# 伴读书童AI 一键启动器（Mac）
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/.."
"$SCRIPT_DIR/../.venv/bin/python" "$SCRIPT_DIR/start.py"
