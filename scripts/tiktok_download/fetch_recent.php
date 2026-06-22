<?php

declare(strict_types=1);

/**
 * 获取 TikTok 用户主页近 N 天的视频信息（不下载）。
 *
 * 这是 fetch_recent.py 的 PHP 等价实现：通过调用本地 yt-dlp 命令行，
 * 解析其输出的 JSON。主页视频默认按最新在前，从新往旧扫描，
 * 一旦连续超过时间窗口即停止，避免拉取整个主页。
 *
 * 依赖：系统已安装 yt-dlp（命令行可用），PHP 需启用 proc_open。
 *
 * 作为库使用：
 *   require __DIR__ . '/fetch_recent.php';
 *   $fetcher = new \TikTokDownload\TikTokRecentFetcher();
 *   $videos = $fetcher->getRecentVideos('https://www.tiktok.com/@user', 2);
 *
 * 作为命令行使用：
 *   php fetch_recent.php "https://www.tiktok.com/@win.william_official"
 *   php fetch_recent.php "https://www.tiktok.com/@user" --days 2
 *   php fetch_recent.php "https://www.tiktok.com/@user" --days 7 -o recent.json
 *   php fetch_recent.php "https://www.tiktok.com/@user" --from-browser firefox
 */

namespace TikTokDownload;

class TikTokRecentFetcher
{
    /** yt-dlp 可执行文件名或完整路径（Windows 下可能是 yt-dlp.exe）。 */
    private string $ytDlpBin;

    /** 从本地浏览器读取登录态：chrome/edge/firefox/brave/... 为 null 则不使用。 */
    private ?string $fromBrowser;

    /** cookies.txt 文件路径，为 null 则不使用。 */
    private ?string $cookies;

    public function __construct(
        string $ytDlpBin = 'yt-dlp',
        ?string $fromBrowser = null,
        ?string $cookies = null
    ) {
        $this->ytDlpBin = $ytDlpBin;
        $this->fromBrowser = $fromBrowser;
        $this->cookies = $cookies;
    }

    /**
     * 返回近 N 天的视频信息列表。
     * 每个元素为 ['id' => ?string, 'url' => string, 'timestamp' => int, 'datetime' => string]。
     *
     * @return list<array{id: ?string, url: string, timestamp: int, datetime: string}>
     */
    public function getRecentVideos(string $userUrl, int $days = 2): array
    {
        $cutoffTs = time() - $days * 86400;

        $entries = $this->listEntries($userUrl);
        $results = [];
        $consecutiveOld = 0;

        foreach ($entries as $entry) {
            if (!is_array($entry)) {
                continue;
            }

            $vid = $entry['id'] ?? null;
            $url = $entry['url'] ?? ($entry['webpage_url'] ?? null);

            // 扁平条目有时只给 id，需要补全标准视频地址
            if (!$url && $vid) {
                $uploader = $entry['uploader'] ?? self::extractUsername($userUrl);
                if ($uploader) {
                    $url = "https://www.tiktok.com/@{$uploader}/video/{$vid}";
                }
            }
            if (!$url) {
                continue;
            }

            // 部分扁平条目自带 timestamp，能省一次请求
            $ts = $entry['timestamp'] ?? null;
            if ($ts === null) {
                $ts = $this->videoTimestamp($url);
            }
            if ($ts === null) {
                // 拿不到时间就跳过（保守处理，不计入结果）
                continue;
            }
            $ts = (int) $ts;

            if ($ts >= $cutoffTs) {
                $results[] = [
                    'id' => $vid !== null ? (string) $vid : null,
                    'url' => $url,
                    'timestamp' => $ts,
                    'datetime' => date('Y-m-d H:i:s', $ts),
                ];
                $consecutiveOld = 0;
            } else {
                // 主页按最新在前，连续遇到超窗的旧视频则停止扫描
                $consecutiveOld++;
                if ($consecutiveOld >= 3) {
                    break;
                }
            }
        }

        usort($results, static fn(array $a, array $b): int => $b['timestamp'] <=> $a['timestamp']);

        return $results;
    }

    /**
     * 快速列出主页视频条目（扁平模式，不解析每个视频细节）。
     *
     * @return list<array<string, mixed>>
     */
    public function listEntries(string $userUrl): array
    {
        $args = array_merge($this->baseArgs(), ['-J', '--flat-playlist', $userUrl]);
        $info = $this->runJson($args);
        if (!$info || empty($info['entries'])) {
            return [];
        }
        return array_values($info['entries']);
    }

    /** 获取单个视频的发布时间戳（Unix 秒）。 */
    public function videoTimestamp(string $url): ?int
    {
        $args = array_merge($this->baseArgs(), ['-J', $url]);
        $info = $this->runJson($args);
        if (!$info || !isset($info['timestamp'])) {
            return null;
        }
        return (int) $info['timestamp'];
    }

    /** @return list<string> */
    private function baseArgs(): array
    {
        // 对应 Python 版的 quiet / no_warnings / ignoreerrors
        $args = ['--no-warnings', '--ignore-errors'];
        if ($this->fromBrowser !== null) {
            $args[] = '--cookies-from-browser';
            $args[] = strtolower($this->fromBrowser);
        }
        if ($this->cookies !== null) {
            $args[] = '--cookies';
            $args[] = $this->cookies;
        }
        return $args;
    }

    /**
     * 执行 yt-dlp 并把它的 stdout 解析为关联数组。
     *
     * @param list<string> $args
     * @return array<string, mixed>|null
     */
    private function runJson(array $args): ?array
    {
        $full = array_merge([$this->ytDlpBin], $args);
        $cmd = implode(' ', array_map('escapeshellarg', $full));

        $descriptors = [
            1 => ['pipe', 'w'],
            2 => ['pipe', 'w'],
        ];
        $pipes = [];
        $proc = proc_open($cmd, $descriptors, $pipes);
        if (!is_resource($proc)) {
            throw new \RuntimeException('无法启动 yt-dlp 进程，请确认已安装并在 PATH 中。');
        }

        $stdout = stream_get_contents($pipes[1]) ?: '';
        fclose($pipes[1]);
        // 丢弃 stderr，对齐 Python 版的 quiet 行为；如需调试可改为写到 STDERR
        stream_get_contents($pipes[2]);
        fclose($pipes[2]);
        proc_close($proc);

        $stdout = trim($stdout);
        if ($stdout === '') {
            return null;
        }

        $decoded = json_decode($stdout, true);
        return is_array($decoded) ? $decoded : null;
    }

    /** 从主页 URL 中提取 @用户名。 */
    public static function extractUsername(string $userUrl): ?string
    {
        if (preg_match('/@([\w.\-]+)/', $userUrl, $m)) {
            return $m[1];
        }
        return null;
    }
}

/* ----------------------------- 命令行入口 ----------------------------- */

/**
 * 解析命令行参数。
 *
 * @param list<string> $argv
 * @return array{user_url: ?string, days: int, years: ?float, output: ?string, from_browser: ?string, cookies: ?string}
 */
function parse_args(array $argv): array
{
    $opts = [
        'user_url' => null,
        'days' => 2,
        'years' => null,
        'output' => null,
        'from_browser' => null,
        'cookies' => null,
    ];

    // 跳过脚本名
    $args = array_slice($argv, 1);
    $n = count($args);

    for ($i = 0; $i < $n; $i++) {
        $arg = $args[$i];
        switch ($arg) {
            case '--days':
                $opts['days'] = (int) ($args[++$i] ?? 2);
                break;
            case '--years':
                $opts['years'] = (float) ($args[++$i] ?? 0);
                break;
            case '-o':
            case '--output':
                $opts['output'] = $args[++$i] ?? null;
                break;
            case '--from-browser':
                $opts['from_browser'] = $args[++$i] ?? null;
                break;
            case '--cookies':
                $opts['cookies'] = $args[++$i] ?? null;
                break;
            case '-h':
            case '--help':
                fwrite(STDERR, "用法: php fetch_recent.php <user_url> [--days N] [--years F] [-o file] [--from-browser BROWSER] [--cookies file]\n");
                exit(0);
            default:
                if ($opts['user_url'] === null && $arg[0] !== '-') {
                    $opts['user_url'] = $arg;
                }
                break;
        }
    }

    return $opts;
}

/**
 * @param list<string> $argv
 */
function main(array $argv): int
{
    $args = parse_args($argv);

    if ($args['user_url'] === null) {
        fwrite(STDERR, "错误: 缺少 TikTok 用户主页链接。\n");
        fwrite(STDERR, "用法: php fetch_recent.php <user_url> [--days N] [--years F] [-o file] [--from-browser BROWSER] [--cookies file]\n");
        return 2;
    }

    $days = $args['years'] !== null ? (int) round($args['years'] * 365) : $args['days'];
    $span = $args['years'] !== null ? "{$args['years']} 年" : "{$days} 天";
    fwrite(STDERR, "正在获取 {$args['user_url']} 近 {$span}（≈{$days} 天）的视频...\n");

    $fetcher = new TikTokRecentFetcher(
        'yt-dlp',
        $args['from_browser'],
        $args['cookies']
    );
    $videos = $fetcher->getRecentVideos($args['user_url'], $days);

    $outputJson = json_encode(
        $videos,
        JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT
    );
    echo $outputJson, PHP_EOL;

    if ($args['output'] !== null) {
        $dir = dirname($args['output']);
        if ($dir !== '' && !is_dir($dir)) {
            mkdir($dir, 0777, true);
        }
        file_put_contents($args['output'], $outputJson);
        fwrite(STDERR, '已写入 ' . count($videos) . " 条到: {$args['output']}\n");
    } else {
        fwrite(STDERR, '共 ' . count($videos) . " 条。\n");
    }

    return 0;
}

// 仅在直接通过命令行执行本文件时运行 main；被 require/include 时不执行。
if (PHP_SAPI === 'cli' && isset($argv) && realpath($argv[0] ?? '') === realpath(__FILE__)) {
    exit(main($argv));
}
