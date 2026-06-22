#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""获取 TikTok 用户主页近 N 天的视频信息（不下载）

只返回结构化数据：视频地址、id、发布时间。
基于 yt-dlp 提取，主页视频默认按最新在前，从新往旧扫描，
一旦超过时间窗口即停止，避免拉取整个主页。

用法示例：
  python fetch_recent.py "https://www.tiktok.com/@win.william_official"
  python fetch_recent.py "https://www.tiktok.com/@user" --days 2
  python fetch_recent.py "https://www.tiktok.com/@user" --days 7 -o recent.json
  python fetch_recent.py "https://www.tiktok.com/@user" --from-browser firefox
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    import yt_dlp
except ImportError:
    print("缺少依赖 yt-dlp，请先安装：pip install -U yt-dlp", file=sys.stderr)
    sys.exit(1)


def _base_opts(from_browser: str | None, cookies: Path | None) -> dict:
    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
    }
    if from_browser is not None:
        opts["cookiesfrombrowser"] = (from_browser.lower(),)
    if cookies is not None:
        opts["cookiefile"] = str(cookies)
    return opts


def list_entries(user_url: str, opts: dict) -> list[dict[str, Any]]:
    """快速列出主页视频条目（扁平模式，不解析每个视频细节）。"""
    flat_opts = dict(opts)
    flat_opts["extract_flat"] = "in_playlist"
    with yt_dlp.YoutubeDL(flat_opts) as ydl:
        info = ydl.extract_info(user_url, download=False)
    if not info:
        return []
    return list(info.get("entries") or [])


def video_timestamp(url: str, opts: dict) -> int | None:
    """获取单个视频的发布时间戳（Unix 秒）。"""
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info:
        return None
    return info.get("timestamp")


def get_recent_videos(
    user_url: str,
    days: int = 2,
    from_browser: str | None = None,
    cookies: Path | None = None,
    sleep_min: float = 0.0,
    sleep_max: float = 0.0,
) -> list[dict[str, Any]]:
    """返回近 N 天的视频信息列表，元素为 {id, url, timestamp, datetime}。

    sleep_min/sleep_max：每次「逐个视频取时间戳」的网络请求之间随机停顿的秒数区间，
    用于降低被风控的概率（定时批量场景建议开启）。
    """
    opts = _base_opts(from_browser, cookies)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    cutoff_ts = cutoff.timestamp()

    entries = list_entries(user_url, opts)
    results: list[dict[str, Any]] = []
    consecutive_old = 0

    for entry in entries:
        if not entry:
            continue
        vid = entry.get("id")
        url = entry.get("url") or entry.get("webpage_url")
        # 扁平条目有时只给 id，需要补全标准视频地址
        if not url and vid:
            # 从主页 URL 提取 @用户名
            uploader = entry.get("uploader") or _extract_username(user_url)
            if uploader:
                url = f"https://www.tiktok.com/@{uploader}/video/{vid}"
        if not url:
            continue

        # 部分扁平条目自带 timestamp，能省一次请求
        ts = entry.get("timestamp")
        if ts is None:
            ts = video_timestamp(url, opts)
            # 只有真正发起了网络请求才随机停顿
            if sleep_max > 0:
                time.sleep(random.uniform(max(0.0, sleep_min), max(sleep_min, sleep_max)))
        if ts is None:
            # 拿不到时间就跳过（保守处理，不计入结果）
            continue

        if ts >= cutoff_ts:
            results.append(
                {
                    "id": str(vid) if vid else None,
                    "url": url,
                    "timestamp": int(ts),
                    "datetime": datetime.fromtimestamp(ts, timezone.utc)
                    .astimezone()
                    .strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
            consecutive_old = 0
        else:
            # 主页按最新在前，连续遇到超窗的旧视频则停止扫描
            consecutive_old += 1
            if consecutive_old >= 3:
                break

    results.sort(key=lambda x: x["timestamp"], reverse=True)
    return results


def _extract_username(user_url: str) -> str | None:
    import re

    m = re.search(r"@([\w.\-]+)", user_url)
    return m.group(1) if m else None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="获取 TikTok 用户主页近 N 天的视频信息（不下载）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("user_url", help="TikTok 用户主页链接，如 https://www.tiktok.com/@user")
    parser.add_argument("--days", type=int, default=2, help="时间窗口，单位天（默认 2）")
    parser.add_argument(
        "--years",
        type=float,
        default=None,
        help="时间窗口，单位年（设置后覆盖 --days，如 --years 2 表示近两年）",
    )
    parser.add_argument(
        "-o", "--output", type=Path, default=None, help="将结果写入 JSON 文件（默认仅打印到控制台）"
    )
    parser.add_argument(
        "--from-browser",
        type=str,
        default=None,
        metavar="BROWSER",
        help="读取本地浏览器登录态：chrome/edge/firefox/brave/... (Chrome 在 Win 上可能因加密失败，建议 firefox)",
    )
    parser.add_argument("--cookies", type=Path, default=None, help="cookies.txt 文件路径")
    parser.add_argument(
        "--sleep-min",
        type=float,
        default=2.0,
        help="逐个取视频时间戳的请求之间最小随机停顿秒数（默认 2，设 0 关闭）",
    )
    parser.add_argument(
        "--sleep-max",
        type=float,
        default=6.0,
        help="逐个取视频时间戳的请求之间最大随机停顿秒数（默认 6）",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    days = round(args.years * 365) if args.years is not None else args.days
    span = f"{args.years} 年" if args.years is not None else f"{days} 天"
    print(f"正在获取 {args.user_url} 近 {span}（≈{days} 天）的视频...", file=sys.stderr)

    videos = get_recent_videos(
        args.user_url,
        days=days,
        from_browser=args.from_browser,
        cookies=args.cookies,
        sleep_min=args.sleep_min,
        sleep_max=args.sleep_max,
    )

    output_json = json.dumps(videos, ensure_ascii=False, indent=2)
    print(output_json)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output_json, encoding="utf-8")
        print(f"已写入 {len(videos)} 条到: {args.output}", file=sys.stderr)
    else:
        print(f"共 {len(videos)} 条。", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
