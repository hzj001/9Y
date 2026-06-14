#!/usr/bin/env bash
# macOS / Linux 启动六合彩分析图形界面

set -euo pipefail
cd "$(dirname "$0")"

pick_python() {
  if command -v python3 >/dev/null 2>&1; then
    echo python3
  elif command -v python >/dev/null 2>&1; then
    echo python
  else
    echo ""
  fi
}

PYTHON="$(pick_python)"
if [[ -z "$PYTHON" ]]; then
  echo "未找到 Python，请先安装 Python 3.10+"
  exit 1
fi

if ! "$PYTHON" -c "import tkinter" 2>/dev/null; then
  echo "缺少 tkinter 模块，图形界面无法启动。"
  echo ""
  if [[ "$(uname -s)" == "Darwin" ]]; then
    echo "macOS 可尝试："
    echo "  brew install python-tk@3.12"
    echo "或使用 python.org 官方安装包（自带 tkinter）"
  else
    echo "Linux 可尝试："
    echo "  sudo apt install python3-tk     # Debian/Ubuntu"
    echo "  sudo dnf install python3-tkinter # Fedora"
  fi
  exit 1
fi

echo "正在启动六合彩分析工具..."
exec "$PYTHON" lhc_gui.py
