#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TikTok 抓取/下载 HTTP 小服务

提供一个接口：发送主页链接 + 天数 + 类型（下载 / 获取地址），返回结果。
基于标准库 http.server，无需额外依赖（仅依赖已安装的 yt-dlp）。

运行：
  python server.py                 # 默认监听 127.0.0.1:8000
  python server.py --host 0.0.0.0 --port 9000

接口：
  POST /api/tiktok
  Content-Type: application/json
  请求体字段：
    url          (必填) TikTok 用户主页链接
    days         (可选) 时间窗口天数，默认 2
    years        (可选) 时间窗口年数，设置后覆盖 days
    type         (可选) "fetch"=只返回视频地址(默认) | "download"=下载到本地
    max          (可选) 限制处理的视频数量上限
    from_browser (可选) 读取本地浏览器登录态：firefox/chrome/edge...
    cookies      (可选) cookies.txt 路径

  返回(JSON)：
    fetch:    { "type":"fetch", "count":N, "videos":[{id,url,timestamp,datetime}, ...] }
    download: { "type":"download", "count":N, "failed":X, "output_dir":"...", "videos":[...] }

示例(curl)：
  curl -X POST http://127.0.0.1:8000/api/tiktok \
       -H "Content-Type: application/json" \
       -d '{"url":"https://www.tiktok.com/@win.william_official","days":2,"type":"fetch"}'
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from downloader import DEFAULT_OUTPUT, download  # noqa: E402
from fetch_recent import get_recent_videos  # noqa: E402


def handle_request(payload: dict) -> tuple[int, dict]:
    """处理业务逻辑，返回 (http_status, response_dict)。"""
    url = payload.get("url")
    if not url or not isinstance(url, str):
        return 400, {"error": "缺少必填字段 url（TikTok 用户主页链接）"}

    req_type = (payload.get("type") or "fetch").lower()
    if req_type not in ("fetch", "download"):
        return 400, {"error": "type 只能是 'fetch' 或 'download'"}

    years = payload.get("years")
    if years is not None:
        try:
            days = round(float(years) * 365)
        except (TypeError, ValueError):
            return 400, {"error": "years 必须是数字"}
    else:
        try:
            days = int(payload.get("days", 2))
        except (TypeError, ValueError):
            return 400, {"error": "days 必须是整数"}

    max_videos = payload.get("max")
    if max_videos is not None:
        try:
            max_videos = int(max_videos)
        except (TypeError, ValueError):
            return 400, {"error": "max 必须是整数"}

    from_browser = payload.get("from_browser")
    cookies = payload.get("cookies")
    cookies_path = Path(cookies) if cookies else None

    # 1) 先获取时间窗口内的视频清单
    videos = get_recent_videos(
        url,
        days=days,
        from_browser=from_browser,
        cookies=cookies_path,
    )
    if max_videos is not None:
        videos = videos[:max_videos]

    if req_type == "fetch":
        return 200, {"type": "fetch", "count": len(videos), "videos": videos}

    # 2) download：下载上面这些视频
    if not videos:
        return 200, {
            "type": "download",
            "count": 0,
            "failed": 0,
            "output_dir": str(DEFAULT_OUTPUT),
            "videos": [],
            "message": "时间窗口内没有视频",
        }

    target_urls = [v["url"] for v in videos]
    failed = download(
        target_urls,
        output_dir=DEFAULT_OUTPUT,
        cookies=cookies_path,
        from_browser=from_browser,
        quiet=True,
    )
    return 200, {
        "type": "download",
        "count": len(videos),
        "failed": int(failed or 0),
        "output_dir": str(DEFAULT_OUTPUT),
        "videos": videos,
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "TikTokFetcher/1.0"

    def _send_json(self, status: int, data: dict) -> None:
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/", "/health"):
            self._send_json(
                200,
                {
                    "service": "tiktok-fetcher",
                    "status": "ok",
                    "endpoint": "POST /api/tiktok",
                    "fields": {
                        "url": "必填，TikTok 用户主页链接",
                        "days": "可选，时间窗口天数，默认 2",
                        "years": "可选，时间窗口年数，覆盖 days",
                        "type": "可选，fetch(默认)|download",
                        "max": "可选，数量上限",
                        "from_browser": "可选，firefox/chrome/edge...",
                        "cookies": "可选，cookies.txt 路径",
                    },
                },
            )
        else:
            self._send_json(404, {"error": "未知路径，请使用 POST /api/tiktok"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/tiktok":
            self._send_json(404, {"error": "未知路径，请使用 POST /api/tiktok"})
            return

        try:
            length = int(self.headers.get("Content-Length", 0))
        except (TypeError, ValueError):
            length = 0
        raw = self.rfile.read(length) if length > 0 else b""

        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except json.JSONDecodeError:
            self._send_json(400, {"error": "请求体不是合法 JSON"})
            return

        try:
            status, data = handle_request(payload)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self._send_json(500, {"error": f"处理失败: {e}"})
            return

        self._send_json(status, data)

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="TikTok 抓取/下载 HTTP 小服务")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址（默认 127.0.0.1）")
    parser.add_argument("--port", type=int, default=8000, help="监听端口（默认 8000）")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"TikTok 服务已启动: http://{args.host}:{args.port}")
    print("接口: POST /api/tiktok  (Ctrl+C 退出)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n正在关闭服务...")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
