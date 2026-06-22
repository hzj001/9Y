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

## 用 Docker 运行（推荐：系统 Python 过低时）

CentOS 7 等老系统自带的 Python 版本太低（如 3.6），新版 `yt-dlp` 装不上。
此时用 Docker 跑最省心：镜像内置高版本 Python + 新版 `yt-dlp` + `ffmpeg`，宿主机环境完全不用动。

```bash
cd scripts/tiktok_download

# 1) 构建镜像（首次或脚本/依赖变更后执行）
docker build -t tiktok-crawler .

# 2) 下载某用户主页最近 20 个视频（产物保存到当前目录 downloads/）
docker run --rm -v "$PWD/downloads:/app/downloads" tiktok-crawler \
  downloader.py "https://www.tiktok.com/@用户名" --max 20

# 3) 获取近 2 天视频信息（不下载，输出 JSON 到终端）
docker run --rm tiktok-crawler \
  fetch_recent.py "https://www.tiktok.com/@用户名" --days 2

# 4) 获取近两年并保存为 JSON（需挂载目录才能拿到文件）
docker run --rm -v "$PWD/downloads:/app/downloads" tiktok-crawler \
  fetch_recent.py "https://www.tiktok.com/@用户名" --years 2 -o downloads/recent_2y.json
```

镜像入口是 `python`，所以 `docker run ... tiktok-crawler` 后面直接跟「脚本名 + 参数」即可，
两个脚本（`downloader.py` / `fetch_recent.py`）都能用。

### 用 docker compose（命令更短）

```bash
docker compose build

docker compose run --rm tiktok downloader.py "https://www.tiktok.com/@用户名" --max 20
docker compose run --rm tiktok fetch_recent.py "https://www.tiktok.com/@用户名" --days 2
```

> CentOS 7 上的 Docker / Compose 通常较老：如果 `docker compose`（带空格，v2）不可用，
> 请改用 `docker-compose`（带横线，v1），子命令完全一样。

### 批量链接 / cookies

需要 `-f links.txt` 或 `--cookies cookies.txt` 时，先在本目录创建文件再挂载进去：

```bash
# docker run 方式：把当前目录挂到容器 /app
docker run --rm -v "$PWD:/app/work" -w /app tiktok-crawler \
  downloader.py -f work/links.txt -o work/downloads
```

用 compose 的话，先 `touch links.txt cookies.txt`，再取消 `docker-compose.yml` 里对应挂载行的注释即可。

> 说明：
> - 容器内**没有浏览器**，所以 `--from-browser` 不可用；需要登录态请改用 `--cookies cookies.txt`。
> - 时区默认 `Asia/Shanghai`（影响 `fetch_recent.py` 的 `datetime` 显示），可在构建/运行时改 `TZ`。
> - 镜像已内置 `ffmpeg`，`--audio-only` 可直接使用。

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
| `--sleep-min / --sleep-max` | 每个视频之间的随机停顿秒数（默认 3~8，防风控；设 `--sleep-min 0 --sleep-max 0` 关闭） |
| `--sleep-requests N` | 每次网络请求之间停顿 N 秒（默认 0，更保守可设 1~2） |
| `--limit-rate 2M` | 限制下载速率（默认不限速） |
| `--concurrency N` | 分片并发数（默认 2，越低越不易被风控） |

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

## HTTP 接口：`api.py`（给前端调用）

把「获取近期视频信息」封装成 HTTP 接口(基于 **FastAPI**),前端直接调用拿 JSON,不下载文件。

### 启动

接口用 **API Key 鉴权**:通过环境变量 `API_KEY` 配置密钥(逗号分隔可配多个),调用方在请求头带 `X-API-Key`(或 `Authorization: Bearer <key>`)。**不设置 `API_KEY` 则不鉴权**(仅建议本地开发,启动时会打印警告)。

```bash
# 本地直接跑（需先 pip install -r requirements.txt）
API_KEY=your-secret-key python api.py        # 监听 0.0.0.0:8000

# 或用 Docker（推荐）
docker build -t tiktok-crawler .
docker run --rm -p 8000:8000 -e API_KEY=your-secret-key tiktok-crawler api.py

# 或用 compose 后台常驻（密钥从宿主机环境变量注入）
export API_KEY=your-secret-key
docker compose up -d api
```

启动后自带交互式文档:`http://<服务器>:8000/docs`(点右上角 **Authorize** 填入 key 即可在线调试)。

### 接口说明

**`GET /api/recent`** —— 获取某用户近 N 天/年的视频信息

| 参数 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `url` | string | 必填 | TikTok 用户主页链接 |
| `days` | int | 2 | 时间窗口(天) |
| `years` | float | - | 时间窗口(年),设置后覆盖 `days` |
| `sleep_min` | float | 2 | 取时间戳请求间最小随机停顿(秒) |
| `sleep_max` | float | 6 | 取时间戳请求间最大随机停顿(秒) |

**`GET /health`** —— 健康检查,返回 `{"status":"ok"}`。

### 鉴权

| 方式 | 请求头 |
| --- | --- |
| API Key(推荐) | `X-API-Key: your-secret-key` |
| Bearer | `Authorization: Bearer your-secret-key` |

未带或密钥错误时返回 `401`。

### 调用示例

```bash
curl -H "X-API-Key: your-secret-key" \
  "http://localhost:8000/api/recent?url=https://www.tiktok.com/@cyndiwang905&days=2"
```

前端(浏览器 fetch):

```js
const res = await fetch(
  `http://你的服务器:8000/api/recent?url=${encodeURIComponent(userUrl)}&days=2`,
  { headers: { "X-API-Key": "your-secret-key" } }
);
if (res.status === 401) throw new Error("API Key 无效");
const data = await res.json();
// data = { user_url, days, count, videos: [{ id, url, timestamp, datetime }, ...] }
```

返回示例:

```json
{
  "user_url": "https://www.tiktok.com/@cyndiwang905",
  "days": 2,
  "count": 1,
  "videos": [
    {
      "id": "7300000000000000000",
      "url": "https://www.tiktok.com/@cyndiwang905/video/7300000000000000000",
      "timestamp": 1718900000,
      "datetime": "2026-06-20 10:13:20"
    }
  ]
}
```

> 说明：
> - 底层是 yt-dlp,单次请求可能耗时数秒到数十秒(视视频数量与限速而定),前端注意加 loading / 超时处理。
> - 跨域:默认允许所有来源(`CORS_ORIGINS=*`),**生产环境请设为前端实际域名**(环境变量 `CORS_ORIGINS=https://your-frontend.com`)。
> - 登录态:接口不暴露 cookie 参数;如需登录态,在服务端用环境变量 `TIKTOK_COOKIES=/app/cookies.txt` 配置(见 `docker-compose.yml` 的 `api` 服务)。
> - 接口只读取信息、不下载,风控风险低;但仍建议保留默认的 `sleep` 随机停顿。

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

## 定时爬虫（每日增量 + 防风控）

每天定时抓取多个账号的新视频时,关键是**增量 + 限速 + 错峰**,避免被 TikTok 风控(限流/封 IP)。
脚本 `daily_crawl.sh` 已经把这些都封装好了。

### 原理

- **增量**:`downloader.py` 用 `download_archive` 记录下过的视频,每天跑只会下当天新增的几个,请求量天然很小(前提:`downloads/` 挂载到宿主机持久化)。
- **限速**:视频之间随机停顿、限制速率、低并发(脚本默认已开)。
- **错峰**:cron 定一个时间,脚本启动时再随机延迟 0~30 分钟,避免每天精确同点。
- **账号间停顿**:每个账号处理完随机歇一会。
- **cookie 预留**:本目录放了 `cookies.txt` 就会自动启用登录态,没有则裸跑。

### 步骤

1）准备账号列表 `links.txt`(每行一个主页链接,`#` 开头为注释):

```bash
cd /opt/9Y/scripts/tiktok_download
cp links.txt.example links.txt
vi links.txt   # 填入要追踪的账号主页，如 https://www.tiktok.com/@用户名
```

2）确保镜像已构建:

```bash
docker build -t tiktok-crawler .
```

3）手动测试一次(关掉随机启动延迟,立即执行):

```bash
chmod +x daily_crawl.sh
MAX_START_DELAY=0 ./daily_crawl.sh
```

跑完看产物:`data/` 下是每个账号的近 N 天信息 JSON,`downloads/` 下是下载的视频,`logs/` 下是当天日志。

4）加到 cron,每天跑一次(示例:每天 03:10,再叠加脚本内 0~30 分钟随机延迟):

```bash
crontab -e
```

加入一行(注意用脚本绝对路径):

```cron
10 3 * * * /opt/9Y/scripts/tiktok_download/daily_crawl.sh >> /opt/9Y/scripts/tiktok_download/logs/cron.log 2>&1
```

### 可调参数（通过环境变量覆盖,无需改脚本）

```bash
# 例：抓近 3 天、每账号最多 50 个、下载限速 1M
DAYS=3 MAX_VIDEOS=50 LIMIT_RATE=1M ./daily_crawl.sh
```

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `DAYS` | 2 | 抓近几天的新视频 |
| `MAX_VIDEOS` | 30 | 每个账号单次最多扫描/下载数 |
| `MAX_START_DELAY` | 1800 | 启动随机延迟上限(秒),0=不延迟 |
| `LIMIT_RATE` | 2M | 下载限速 |
| `DL_SLEEP_MIN/MAX` | 3 / 8 | 下载时视频间随机停顿(秒) |
| `FETCH_SLEEP_MIN/MAX` | 2 / 6 | 取信息时请求间随机停顿(秒) |
| `GAP_MIN/MAX` | 15 / 45 | 账号之间随机停顿(秒) |

> 关于会不会被封:绝大多数情况是**临时限流**(返回 403/验证码/拉取失败),过段时间自动恢复,且只影响该 IP 访问 TikTok,不影响服务器其他业务。云服务器 IP 比家庭宽带更容易触发风控,所以**务必保持限速、控制频率、量大时考虑住宅代理**。

## 合规提醒

请仅下载你有权使用的内容，遵守 TikTok 的服务条款及相关版权法律法规。
