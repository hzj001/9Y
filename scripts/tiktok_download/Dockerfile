FROM python:3.12-slim

# ffmpeg 用于音视频合并 / --audio-only；ca-certificates 保证 https 正常
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先装依赖，利用镜像层缓存
COPY requirements.txt ./
RUN pip install --no-cache-dir -U pip \
    && pip install --no-cache-dir -r requirements.txt

# 复制脚本
COPY downloader.py fetch_recent.py server.py ./

# 下载产物目录（建议挂载为数据卷）
RUN mkdir -p /app/downloads
VOLUME ["/app/downloads"]

ENV PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8000

EXPOSE 8000

# 用 shell 形式以便读取 HOST/PORT 环境变量
CMD python server.py --host "$HOST" --port "$PORT"
