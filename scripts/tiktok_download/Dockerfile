# 用高版本 Python 跑 TikTok 下载脚本，宿主机（如 CentOS 7 自带 Python 3.6）无需改动。
# 镜像内置新版 yt-dlp + ffmpeg。
FROM python:3.12-slim

# PYTHONUNBUFFERED: 日志实时输出，便于 docker logs 观察
# TZ: 让 fetch_recent.py 的 datetime 字段按本地时区显示
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Shanghai

# ffmpeg: --audio-only / 音视频合并所需；tzdata: 提供时区数据
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先装依赖，利用 Docker 层缓存（requirements 不变时不会重复安装）
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY downloader.py fetch_recent.py api.py ./

# 下载产物目录，建议运行时挂载宿主机卷以持久化
VOLUME ["/app/downloads"]

# HTTP 接口默认端口（仅文档作用，实际以 -p 映射为准）
EXPOSE 8000

# 以 python 为入口，运行时再指定要跑哪个脚本及参数，例如：
#   下载：  docker run --rm -v "$PWD/downloads:/app/downloads" tiktok-crawler \
#             downloader.py "https://www.tiktok.com/@user" --max 20
#   起接口：docker run --rm -p 8000:8000 tiktok-crawler api.py
ENTRYPOINT ["python"]
CMD ["downloader.py", "--help"]
