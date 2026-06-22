# TikTok 视频下载器

基于 [yt-dlp](https://github.com/yt-dlp/yt-dlp) 的 TikTok 视频抓取/下载脚本，支持单个视频、批量链接、整个用户主页下载，并自动去重、保存元数据和缩略图。

包含两个脚本：

- `downloader.py` —— **下载**视频到本地
- `fetch_recent.py` —— **只获取不下载**，返回近 N 天/年的视频地址、id、时间

## 快速开始（如何运行）

```bash
# 1) 安装依赖
pip install -r requirements.txt

# 2) 下载某用户主页最近 20 个视频
python downloader.py "https://www.tiktok.com/@用户名" --max 20

# 3) 获取某用户近两天的视频信息（不下载）
python fetch_recent.py "https://www.tiktok.com/@用户名" --days 2

# 4) 获取近两年的视频信息并存为 JSON
python fetch_recent.py "https://www.tiktok.com/@用户名" --years 2 -o recent_2y.json
```

> 在 Windows 上请先 `cd scripts/tiktok_download` 再执行，或把上面的脚本名换成完整路径 `scripts/tiktok_download/downloader.py`。

## 安装

```bash
pip install -r requirements.txt
```

> 提示：如需「仅提取音频 (`--audio-only`)」或合并音视频，请额外安装 [ffmpeg](https://ffmpeg.org/) 并加入系统 PATH。

## 使用

下载单个视频：

```bash
python downloader.py "https://www.tiktok.com/@user/video/7300000000000000000"
```

下载某个用户主页的全部视频（或最近 N 个）：

```bash
python downloader.py "https://www.tiktok.com/@user"
python downloader.py "https://www.tiktok.com/@user" --max 20
```

从文件批量下载（每行一个链接，参考 `links.txt.example`）：

```bash
python downloader.py -f links.txt
```

其他参数：

| 参数 | 说明 |
| --- | --- |
| `-o, --output` | 保存目录，默认 `./downloads` |
| `--max N` | 下载主页时最多下载 N 个视频 |
| `--from-browser chrome` | 直接读取本地浏览器登录态（你在浏览器登录 TikTok 即可，免导出） |
| `--cookies cookies.txt` | 下载私密/受限内容时使用导出的 cookies |
| `--audio-only` | 仅提取音频并转为 mp3（需 ffmpeg） |
| `-q, --quiet` | 安静模式 |

## 只获取不下载：`fetch_recent.py`

获取某用户主页近 N 天（默认 2 天）的视频信息，返回 `视频地址 / id / 时间` 的结构化数据（JSON），不下载文件。

```bash
# 近 2 天
python fetch_recent.py "https://www.tiktok.com/@win.william_official"

# 近 7 天，并保存为 JSON 文件
python fetch_recent.py "https://www.tiktok.com/@user" --days 7 -o recent.json

# 近两年（--years 会覆盖 --days）
python fetch_recent.py "https://www.tiktok.com/@user" --years 2 -o recent_2y.json
```

输出示例：

```json
[
  {
    "id": "7300000000000000000",
    "url": "https://www.tiktok.com/@win.william_official/video/7300000000000000000",
    "timestamp": 1718900000,
    "datetime": "2026-06-20 10:13:20"
  }
]
```

> 提示：从主页最新视频往旧扫描，连续遇到超出时间窗口的旧视频即停止，因此速度较快。`datetime` 为本地时区时间。

## HTTP 服务：`server.py`

提供一个 HTTP 接口，POST 主页链接 + 天数 + 类型（下载 / 获取地址），返回结果。基于标准库，无需额外依赖。

启动服务：

```bash
python server.py                       # 默认 127.0.0.1:8000
python server.py --host 0.0.0.0 --port 9000
```

调用接口 `POST /api/tiktok`（JSON 请求体）：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `url` | 是 | TikTok 用户主页链接 |
| `days` | 否 | 时间窗口天数，默认 2 |
| `years` | 否 | 时间窗口年数，设置后覆盖 `days` |
| `type` | 否 | `fetch`（默认，只返回地址）/ `download`（下载到本地） |
| `max` | 否 | 处理数量上限 |
| `from_browser` | 否 | 复用浏览器登录态：firefox/chrome/edge... |
| `cookies` | 否 | cookies.txt 路径 |

示例（获取近两天视频地址）：

```bash
curl -X POST http://127.0.0.1:8000/api/tiktok \
     -H "Content-Type: application/json" \
     -d "{\"url\":\"https://www.tiktok.com/@win.william_official\",\"days\":2,\"type\":\"fetch\"}"
```

示例（下载近两天视频）：

```bash
curl -X POST http://127.0.0.1:8000/api/tiktok \
     -H "Content-Type: application/json" \
     -d "{\"url\":\"https://www.tiktok.com/@win.william_official\",\"days\":2,\"type\":\"download\"}"
```

返回示例（fetch）：

```json
{
  "type": "fetch",
  "count": 1,
  "videos": [
    { "id": "7300000000000000000", "url": "https://www.tiktok.com/@.../video/7300000000000000000", "timestamp": 1718900000, "datetime": "2026-06-20 10:13:20" }
  ]
}
```

> 注意：`type=download` 是同步下载，时间窗口大时请求会阻塞较久；建议先用 `fetch` 看清单，再决定是否下载。

## Docker 部署

镜像已包含 Python、yt-dlp、curl_cffi、ffmpeg，开箱即用。

> ⚠️ 容器所在服务器必须能访问 TikTok（国内节点不行，需海外服务器或代理）。

使用 docker compose（推荐）：

```bash
cd scripts/tiktok_download
docker compose up -d --build      # 构建并后台启动
docker compose logs -f            # 查看日志
docker compose down               # 停止
```

或直接用 docker：

```bash
cd scripts/tiktok_download
docker build -t tiktok-fetcher .
docker run -d --name tiktok-fetcher \
  -p 8000:8000 \
  -v "$(pwd)/downloads:/app/downloads" \
  tiktok-fetcher
```

启动后即可调用接口：

```bash
curl -X POST http://localhost:8000/api/tiktok \
     -H "Content-Type: application/json" \
     -d "{\"url\":\"https://www.tiktok.com/@win.william_official\",\"days\":2,\"type\":\"fetch\"}"
```

说明：

- 下载产物持久化在宿主机 `./downloads` 目录。
- 监听地址/端口可用环境变量 `HOST`、`PORT` 调整（compose 里已设置）。
- 需要登录时：把 `cookies.txt` 放到 `scripts/tiktok_download/`，取消 `docker-compose.yml` 中 cookies 挂载那行注释，请求时传 `"cookies": "/app/cookies.txt"`。
- 容器内无浏览器，`from_browser` 不可用，登录请用 cookies。

## 说明

- 文件按 `下载者/创建时间_视频ID.mp4`（如 `20240115_103045_7300000000000000000.mp4`）组织，避免重名覆盖。
- 已下载的链接会记录在 `downloads/.download_archive.txt`，重复运行会自动跳过。
- 同时会保存 `.info.json` 元数据和缩略图，方便后续处理。
- 遇到地区限制或需要登录时，推荐用 `--from-browser`：在自己电脑的浏览器里登录好 TikTok，脚本会自动读取该浏览器的登录 Cookie，无需手动导出。

```bash
# 你已在 Chrome 登录 TikTok，直接复用登录态
python downloader.py "https://www.tiktok.com/@user" --max 20 --from-browser chrome
```

> 注意：用 `--from-browser` 时，请先**完全关闭该浏览器**（尤其 Chrome/Edge 在 Windows 上会锁定 Cookie 数据库），否则可能读取失败。
- 也可以用浏览器扩展导出 `cookies.txt` 后通过 `--cookies` 传入。

## 合规提醒

请仅下载你有权使用的内容，遵守 TikTok 的服务条款及相关版权法律法规。
