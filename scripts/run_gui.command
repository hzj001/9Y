#!/bin/bash
# 双击启动（macOS Finder）：在 Terminal 中运行 GUI
cd "$(dirname "$0")"
chmod +x run_gui.sh 2>/dev/null || true
./run_gui.sh
