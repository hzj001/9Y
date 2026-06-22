#!/usr/bin/env bash
#
# TikTok 每日定时增量爬取脚本（配合 Docker 镜像 tiktok-crawler 使用）
#
# 流程：随机延迟启动 -> 读取 links.txt 中的账号 -> 对每个账号：
#   1) fetch_recent.py 取近 N 天的新视频信息，存为 data/<用户>-<日期>.json
#   2) downloader.py 增量下载（基于 download_archive 自动跳过已下过的）
# 全程限速 + 账号间随机停顿，降低被风控/封禁的概率。
#
# 用法：
#   ./daily_crawl.sh            # 正常跑
#   MAX_START_DELAY=0 ./daily_crawl.sh   # 手动测试时关掉随机启动延迟
#
# 配合 cron 定时见 README「定时爬虫」章节。

set -uo pipefail

# ============ 可按需修改的配置 ============
IMAGE="tiktok-crawler"                 # docker 镜像名
DAYS="${DAYS:-2}"                      # 抓近几天的新视频
MAX_VIDEOS="${MAX_VIDEOS:-30}"         # 每个账号单次最多扫描/下载多少个（配合增量去重）
MAX_START_DELAY="${MAX_START_DELAY:-1800}"   # 启动时随机延迟上限（秒），0=不延迟
DL_SLEEP_MIN="${DL_SLEEP_MIN:-3}"      # 下载时视频间最小停顿（秒）
DL_SLEEP_MAX="${DL_SLEEP_MAX:-8}"      # 下载时视频间最大停顿（秒）
LIMIT_RATE="${LIMIT_RATE:-2M}"         # 下载限速
FETCH_SLEEP_MIN="${FETCH_SLEEP_MIN:-2}"  # 取信息时请求间最小停顿（秒）
FETCH_SLEEP_MAX="${FETCH_SLEEP_MAX:-6}"  # 取信息时请求间最大停顿（秒）
GAP_MIN="${GAP_MIN:-15}"               # 账号之间最小停顿（秒）
GAP_MAX="${GAP_MAX:-45}"               # 账号之间最大停顿（秒）
COOKIES_FILE="cookies.txt"             # 存在则自动启用登录态（预留，以后放进来即可）
# =========================================

# 切到脚本所在目录，保证相对路径稳定
cd "$(dirname "$(readlink -f "$0")")" || exit 1

DATE="$(date +%F)"
LOG_DIR="logs"
DATA_DIR="data"
DL_DIR="downloads"
mkdir -p "$LOG_DIR" "$DATA_DIR" "$DL_DIR"
LOG="$LOG_DIR/crawl-$DATE.log"

log() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

# 前置检查
if ! command -v docker >/dev/null 2>&1; then
  log "ERROR: 未找到 docker 命令"; exit 1
fi
if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  log "ERROR: 镜像 $IMAGE 不存在，请先在本目录执行: docker build -t $IMAGE ."; exit 1
fi
if [ ! -f links.txt ]; then
  log "ERROR: 缺少 links.txt（每行一个 TikTok 主页链接）。可参考 links.txt.example"; exit 1
fi

# 随机延迟启动，避免每天精确同一秒发起请求（更像真人）
if [ "$MAX_START_DELAY" -gt 0 ]; then
  D=$(( RANDOM % MAX_START_DELAY ))
  log "随机延迟 ${D}s 后开始（设 MAX_START_DELAY=0 可关闭）"
  sleep "$D"
fi

# cookie 预留：文件存在才挂载并启用登录态
COOKIE_MOUNT=()
COOKIE_ARGS=()
if [ -f "$COOKIES_FILE" ]; then
  COOKIE_MOUNT=(-v "$PWD/$COOKIES_FILE:/app/cookies.txt:ro")
  COOKIE_ARGS=(--cookies cookies.txt)
  log "检测到 $COOKIES_FILE，已启用登录态"
fi

# 读取账号列表（忽略空行与 # 注释）
USERS=()
while IFS= read -r line || [ -n "$line" ]; do
  line="${line%$'\r'}"   # 去掉可能存在的 Windows 换行符 CR
  line="$(echo "$line" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
  [ -z "$line" ] && continue
  [ "${line#\#}" != "$line" ] && continue   # 以 # 开头则视为注释
  USERS+=("$line")
done < links.txt

log "===== 开始：共 ${#USERS[@]} 个账号，窗口近 ${DAYS} 天 ====="

fail=0
for URL in "${USERS[@]}"; do
  log "--- 账号: $URL ---"
  NAME="$(echo "$URL" | grep -oE '@[A-Za-z0-9._-]+' | head -1 | tr -d '@')"
  [ -z "$NAME" ] && NAME="unknown"

  # 1) 取近 N 天的视频信息，存档为 JSON
  log "[1/2] 取近 ${DAYS} 天信息 -> $DATA_DIR/${NAME}-${DATE}.json"
  if ! docker run --rm \
      -v "$PWD/$DATA_DIR:/app/$DATA_DIR" \
      "${COOKIE_MOUNT[@]}" \
      "$IMAGE" fetch_recent.py "$URL" \
      --days "$DAYS" \
      --sleep-min "$FETCH_SLEEP_MIN" --sleep-max "$FETCH_SLEEP_MAX" \
      "${COOKIE_ARGS[@]}" \
      -o "$DATA_DIR/${NAME}-${DATE}.json" >>"$LOG" 2>&1; then
    log "WARN: 取信息失败: $URL"
    fail=$((fail+1))
  fi

  # 2) 增量下载（download_archive 自动跳过已下过的）
  log "[2/2] 增量下载（最多 ${MAX_VIDEOS} 个，限速 ${LIMIT_RATE}）"
  if ! docker run --rm \
      -v "$PWD/$DL_DIR:/app/downloads" \
      "${COOKIE_MOUNT[@]}" \
      "$IMAGE" downloader.py "$URL" \
      --max "$MAX_VIDEOS" \
      --sleep-min "$DL_SLEEP_MIN" --sleep-max "$DL_SLEEP_MAX" \
      --limit-rate "$LIMIT_RATE" \
      "${COOKIE_ARGS[@]}" >>"$LOG" 2>&1; then
    log "WARN: 下载失败: $URL"
    fail=$((fail+1))
  fi

  # 账号之间随机歇一会
  GAP=$(( GAP_MIN + RANDOM % (GAP_MAX - GAP_MIN + 1) ))
  log "歇 ${GAP}s 再处理下一个账号"
  sleep "$GAP"
done

log "===== 结束：完成 ${#USERS[@]} 个账号，告警 ${fail} 次 ====="
exit 0
