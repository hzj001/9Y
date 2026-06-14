#!/usr/bin/env bash
# 推送后自动拉取，保持本地与远程同步
set -euo pipefail
cd "$(dirname "$0")/.."
git push "$@"
git pull
echo "push + pull 完成"
