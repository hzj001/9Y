#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TikTok 近期视频信息 HTTP 接口（FastAPI）

把 fetch_recent.get_recent_videos 封装成 HTTP 接口供前端调用：
只返回结构化信息（id / url / timestamp / datetime），不下载视频文件。

启动方式：
  python api.py                                  # 默认监听 0.0.0.0:8000
  uvicorn api:app --host 0.0.0.0 --port 8000     # 等价
  HOST=0.0.0.0 PORT=8080 python api.py           # 用环境变量改地址/端口

交互式文档（自带）：
  http://<服务器>:8000/docs

环境变量：
  HOST / PORT       监听地址与端口（默认 0.0.0.0 / 8000）
  CORS_ORIGINS      允许的前端来源，逗号分隔，默认 *（生产建议收紧为具体域名）
  TIKTOK_COOKIES    服务端 cookies.txt 路径（可选，不暴露给前端）
  API_KEY           接口鉴权密钥，逗号分隔可配多个；为空则不鉴权（仅建议本地开发）
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

from fetch_recent import get_recent_videos

app = FastAPI(
    title="TikTok Recent API",
    version="1.0.0",
    description="获取 TikTok 用户主页近 N 天/年的视频信息（不下载）。",
)

# 允许前端跨域调用；生产环境建议把 CORS_ORIGINS 设为具体域名
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# 服务端可选 cookie（登录态），由运维配置，不通过接口暴露给前端
_cookies_env = os.getenv("TIKTOK_COOKIES")
DEFAULT_COOKIES: Optional[Path] = Path(_cookies_env) if _cookies_env else None

# ---- 鉴权：API Key（请求头 X-API-Key，或 Authorization: Bearer <key>）----
API_KEYS = {k.strip() for k in os.getenv("API_KEY", "").split(",") if k.strip()}
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
_bearer_header = APIKeyHeader(name="Authorization", auto_error=False)

if not API_KEYS:
    print(
        "[警告] 未设置 API_KEY 环境变量，接口当前【未启用鉴权】，"
        "生产环境请通过 API_KEY 配置密钥。",
        file=sys.stderr,
    )


def require_api_key(
    x_api_key: Optional[str] = Security(_api_key_header),
    authorization: Optional[str] = Security(_bearer_header),
) -> None:
    """校验 API Key。未配置 API_KEY 时放行（开发模式）。"""
    if not API_KEYS:
        return
    token = x_api_key
    if not token and authorization:
        # 兼容 Authorization: Bearer <key>
        parts = authorization.split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1].strip()
        else:
            token = authorization.strip()
    if not token or token not in API_KEYS:
        raise HTTPException(
            status_code=401,
            detail="无效或缺失的 API Key（请在请求头 X-API-Key 或 Authorization: Bearer 提供）",
        )


class VideoItem(BaseModel):
    id: Optional[str] = None
    url: str
    timestamp: int
    datetime: str


class RecentResponse(BaseModel):
    user_url: str
    days: int
    count: int
    videos: list[VideoItem]


@app.get("/health", summary="健康检查")
def health() -> dict:
    return {"status": "ok"}


@app.get(
    "/api/recent",
    response_model=RecentResponse,
    summary="获取近期视频信息",
    dependencies=[Depends(require_api_key)],
)
def recent(
    url: str = Query(..., description="TikTok 用户主页链接，如 https://www.tiktok.com/@user"),
    days: int = Query(2, ge=1, le=3650, description="时间窗口（天），默认 2"),
    years: Optional[float] = Query(None, gt=0, description="时间窗口（年），设置后覆盖 days"),
    sleep_min: float = Query(2.0, ge=0, description="逐个取时间戳请求间最小随机停顿（秒）"),
    sleep_max: float = Query(6.0, ge=0, description="逐个取时间戳请求间最大随机停顿（秒）"),
) -> RecentResponse:
    """返回该用户主页近 N 天（或近 N 年）的视频信息列表。

    注意：底层基于 yt-dlp，单次请求可能耗时数秒到数十秒（取决于视频数量与限速）。
    """
    if "tiktok.com" not in url:
        raise HTTPException(status_code=400, detail="url 必须是有效的 TikTok 链接")

    effective_days = round(years * 365) if years is not None else days

    try:
        videos = get_recent_videos(
            url,
            days=effective_days,
            cookies=DEFAULT_COOKIES,
            sleep_min=sleep_min,
            sleep_max=sleep_max,
        )
    except Exception as exc:  # yt-dlp 抓取异常统一转 502
        raise HTTPException(status_code=502, detail=f"抓取失败: {exc}") from exc

    return RecentResponse(
        user_url=url,
        days=effective_days,
        count=len(videos),
        videos=[VideoItem(**v) for v in videos],
    )


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
