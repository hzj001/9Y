#!/usr/bin/env python3
"""
香港六合彩（Mark Six）历史数据分析脚本。

基于历史开奖记录，使用多种统计策略对 1-49 号码打分，
并输出本期正码 / 特码的推荐排序。

重要说明：六合彩开奖在理论上各号码概率相等，历史数据不能预测未来结果。
本脚本仅供数据统计与娱乐参考，请理性购彩。
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable

import requests

MIN_NUMBER = 1
MAX_NUMBER = 49
REGULAR_COUNT = 6
SPECIAL_INDEX = 6
DEFAULT_API = "https://www.kj1868.cc/openapi/drawLottery/xg6/last.kj"
DEFAULT_CACHE = Path(__file__).resolve().parent / "data" / "xg6_history.json"


@dataclass(frozen=True)
class DrawRecord:
    period: str
    lottery_date: str
    regular: tuple[int, ...]
    special: int

    @property
    def all_numbers(self) -> tuple[int, ...]:
        return self.regular + (self.special,)


@dataclass
class NumberStats:
    number: int
    total_hits: int = 0
    regular_hits: int = 0
    special_hits: int = 0
    recent_hits: int = 0
    recent_regular_hits: int = 0
    recent_special_hits: int = 0
    last_seen_index: int | None = None
    gaps: list[int] = field(default_factory=list)
    scores: dict[str, float] = field(default_factory=dict)

    @property
    def avg_gap(self) -> float:
        if not self.gaps:
            return float(len(self.gaps) or MAX_NUMBER)
        return sum(self.gaps) / len(self.gaps)

    @property
    def current_gap(self) -> int:
        if self.last_seen_index is None:
            return 10**9
        return self.last_seen_index


def parse_numbers(raw: str) -> tuple[int, ...]:
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    numbers = tuple(int(p) for p in parts)
    if len(numbers) != REGULAR_COUNT + 1:
        raise ValueError(f"期望 7 个号码，实际得到 {len(numbers)} 个: {raw}")
    for n in numbers:
        if not MIN_NUMBER <= n <= MAX_NUMBER:
            raise ValueError(f"号码超出范围 1-49: {n}")
    return numbers


def parse_draw(item: dict) -> DrawRecord:
    numbers = parse_numbers(item["numbers"])
    return DrawRecord(
        period=str(item["period"]),
        lottery_date=str(item["lottery_date"]),
        regular=numbers[:REGULAR_COUNT],
        special=numbers[SPECIAL_INDEX],
    )


def fetch_history(
    api_url: str = DEFAULT_API,
    page_size: int = 100,
    max_pages: int | None = None,
    timeout: int = 30,
    retries: int = 3,
) -> list[DrawRecord]:
    session = requests.Session()
    session.headers.update({"User-Agent": "lhc-analyzer/1.0"})
    draws: list[DrawRecord] = []
    page = 1
    last_page = 1

    while page <= last_page:
        if max_pages is not None and page > max_pages:
            break
        last_error: Exception | None = None
        resp = None
        for attempt in range(1, retries + 1):
            try:
                resp = session.get(
                    api_url,
                    params={"page": page, "pageSize": page_size},
                    timeout=timeout,
                )
                resp.raise_for_status()
                break
            except requests.RequestException as exc:
                last_error = exc
                if attempt == retries:
                    raise exc
        if resp is None:
            raise RuntimeError(f"第 {page} 页请求失败: {last_error}")
        payload = resp.json()
        if payload.get("status") != "10":
            raise RuntimeError(f"API 返回异常: {payload.get('message', payload)}")

        data = payload["data"]
        last_page = int(data["last_page"])
        for item in data["data"]:
            draws.append(parse_draw(item))
        page += 1

    draws.sort(key=lambda d: d.period)
    return draws


def load_cache(path: Path) -> list[DrawRecord] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [
        DrawRecord(
            period=item["period"],
            lottery_date=item["lottery_date"],
            regular=tuple(item["regular"]),
            special=item["special"],
        )
        for item in payload
    ]


def save_cache(path: Path, draws: list[DrawRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        {
            "period": d.period,
            "lottery_date": d.lottery_date,
            "regular": list(d.regular),
            "special": d.special,
        }
        for d in draws
    ]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_stats(draws: list[DrawRecord], recent_window: int) -> dict[int, NumberStats]:
    stats = {n: NumberStats(number=n) for n in range(MIN_NUMBER, MAX_NUMBER + 1)}
    total = len(draws)
    recent_start = max(0, total - recent_window)

    last_seen: dict[int, int | None] = {n: None for n in stats}

    for idx, draw in enumerate(draws):
        is_recent = idx >= recent_start
        for num in draw.regular:
            s = stats[num]
            s.total_hits += 1
            s.regular_hits += 1
            if is_recent:
                s.recent_hits += 1
                s.recent_regular_hits += 1
            if last_seen[num] is not None:
                s.gaps.append(idx - last_seen[num])
            last_seen[num] = idx
            s.last_seen_index = total - 1 - idx

        num = draw.special
        s = stats[num]
        s.total_hits += 1
        s.special_hits += 1
        if is_recent:
            s.recent_hits += 1
            s.recent_special_hits += 1
        if last_seen[num] is not None:
            s.gaps.append(idx - last_seen[num])
        last_seen[num] = idx
        s.last_seen_index = total - 1 - idx

    return stats


def normalize(values: dict[int, float], reverse: bool = False) -> dict[int, float]:
    nums = list(values.values())
    lo, hi = min(nums), max(nums)
    if math.isclose(lo, hi):
        return {k: 1.0 for k in values}
    result = {}
    for k, v in values.items():
        score = (v - lo) / (hi - lo)
        if reverse:
            score = 1.0 - score
        result[k] = score
    return result


def score_numbers(
    stats: dict[int, NumberStats],
    total_draws: int,
    recent_window: int,
    weights: dict[str, float],
) -> None:
    freq_all = {n: s.total_hits / max(total_draws, 1) for n, s in stats.items()}
    freq_recent = {
        n: s.recent_hits / max(min(recent_window, total_draws), 1) for n, s in stats.items()
    }
    freq_regular = {n: s.regular_hits / max(total_draws, 1) for n, s in stats.items()}
    freq_special = {n: s.special_hits / max(total_draws, 1) for n, s in stats.items()}
    overdue = {n: float(s.current_gap) for n, s in stats.items()}
    avg_gap = {n: s.avg_gap for n, s in stats.items()}

    norm = {
        "frequency": normalize(freq_all),
        "recent_hot": normalize(freq_recent),
        "regular_strength": normalize(freq_regular),
        "special_strength": normalize(freq_special),
        "overdue": normalize(overdue),
        "gap_cycle": normalize(avg_gap, reverse=True),
    }

    for n, s in stats.items():
        s.scores = {k: norm[k][n] for k in norm}
        s.scores["composite"] = sum(weights[k] * norm[k][n] for k in norm)


def rank_numbers(
    stats: dict[int, NumberStats],
    key: str,
    top_n: int,
) -> list[NumberStats]:
    ordered = sorted(stats.values(), key=lambda s: s.scores[key], reverse=True)
    return ordered[:top_n]


def format_number(n: int) -> str:
    return f"{n:02d}"


def print_section(title: str) -> None:
    print()
    print("=" * 60)
    print(title)
    print("=" * 60)


def print_ranking(title: str, ranked: Iterable[NumberStats], score_key: str) -> None:
    print_section(title)
    print(f"{'排名':<4} {'号码':<6} {'综合分':<8} {'总出现':<8} {'正码':<6} {'特码':<6} {'近窗':<6} {'遗漏':<6}")
    print("-" * 60)
    for i, s in enumerate(ranked, start=1):
        print(
            f"{i:<4} {format_number(s.number):<6} "
            f"{s.scores[score_key]:<8.3f} {s.total_hits:<8} "
            f"{s.regular_hits:<6} {s.special_hits:<6} "
            f"{s.recent_hits:<6} {s.current_gap if s.current_gap < 10**6 else '-':<6}"
        )


def print_recommendation(
    regular: list[NumberStats],
    special: list[NumberStats],
    latest: DrawRecord | None,
) -> None:
    print_section("本期推荐（统计模型输出，非真实概率）")
    if latest:
        print(f"最新一期: 第 {latest.period} 期 ({latest.lottery_date})")
        print(
            "开奖号码: "
            + ", ".join(format_number(n) for n in latest.regular)
            + f" + 特码 {format_number(latest.special)}"
        )

    regular_nums = sorted(s.number for s in regular)
    special_num = special[0].number
    print()
    print(f"推荐正码 Top {len(regular_nums)}: " + ", ".join(format_number(n) for n in regular_nums))
    print(f"推荐特码 Top 1: {format_number(special_num)}")
    print()
    print("组合示例（正码 + 特码）:")
    print("  " + ", ".join(format_number(n) for n in regular_nums) + f" | 特码 {format_number(special_num)}")


def print_strategy_breakdown(stats: dict[int, NumberStats], numbers: Iterable[int]) -> None:
    print_section("推荐号码各策略得分")
    headers = ["号码", "综合", "全频", "近热", "正码", "特码", "遗漏", "周期"]
    print("{:<6}{:<8}{:<8}{:<8}{:<8}{:<8}{:<8}{:<8}".format(*headers))
    print("-" * 60)
    for n in numbers:
        s = stats[n]
        print(
            f"{format_number(n):<6}"
            f"{s.scores['composite']:<8.3f}"
            f"{s.scores['frequency']:<8.3f}"
            f"{s.scores['recent_hot']:<8.3f}"
            f"{s.scores['regular_strength']:<8.3f}"
            f"{s.scores['special_strength']:<8.3f}"
            f"{s.scores['overdue']:<8.3f}"
            f"{s.scores['gap_cycle']:<8.3f}"
        )


def resolve_draws(args: argparse.Namespace) -> list[DrawRecord]:
    cache_path = Path(args.cache_file)
    if cache_path.exists() and not args.refresh:
        draws = load_cache(cache_path)
        if draws:
            return draws[-args.limit :] if args.limit else draws

    draws = fetch_history(
        api_url=args.api,
        page_size=args.page_size,
        max_pages=args.max_pages,
    )
    if args.cache or cache_path.exists():
        save_cache(cache_path, draws)
    if args.limit:
        draws = draws[-args.limit :]
    return draws


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="香港六合彩历史数据分析 — 基于多策略统计给出推荐号码",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--api", default=DEFAULT_API, help="历史开奖 API 地址")
    parser.add_argument("--page-size", type=int, default=100, help="每页抓取条数")
    parser.add_argument("--max-pages", type=int, default=None, help="最多抓取页数")
    parser.add_argument("--limit", type=int, default=None, help="只使用最近 N 期数据")
    parser.add_argument("--recent", type=int, default=30, help="“近期热度”统计窗口（期数）")
    parser.add_argument("--top-regular", type=int, default=6, help="推荐正码数量")
    parser.add_argument("--top-special", type=int, default=3, help="展示特码 Top N")
    parser.add_argument("--refresh", action="store_true", help="忽略缓存，重新拉取 API")
    parser.add_argument("--cache", action="store_true", help="拉取后将历史数据写入本地缓存")
    parser.add_argument(
        "--cache-file",
        default=str(DEFAULT_CACHE),
        help="本地缓存文件路径（存在时优先读取）",
    )
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出结果")
    parser.add_argument(
        "--weights",
        default="frequency:0.20,recent_hot:0.25,regular_strength:0.20,special_strength:0.10,overdue:0.15,gap_cycle:0.10",
        help="各策略权重，格式 key:weight,key:weight",
    )
    return parser


def parse_weights(raw: str) -> dict[str, float]:
    weights: dict[str, float] = {}
    for part in raw.split(","):
        key, value = part.split(":")
        weights[key.strip()] = float(value.strip())
    total = sum(weights.values())
    if not math.isclose(total, 1.0, rel_tol=1e-6):
        weights = {k: v / total for k, v in weights.items()}
    return weights


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    weights = parse_weights(args.weights)

    try:
        draws = resolve_draws(args)
    except requests.RequestException as exc:
        print(f"网络请求失败: {exc}", file=sys.stderr)
        return 1
    except (RuntimeError, ValueError, KeyError) as exc:
        print(f"数据解析失败: {exc}", file=sys.stderr)
        return 1

    if len(draws) < 10:
        print("历史数据不足，至少需要 10 期。", file=sys.stderr)
        return 1

    stats = build_stats(draws, recent_window=args.recent)
    score_numbers(stats, total_draws=len(draws), recent_window=args.recent, weights=weights)

    regular_ranked = rank_numbers(stats, "regular_strength", MAX_NUMBER)
    special_ranked = rank_numbers(stats, "special_strength", MAX_NUMBER)
    composite_ranked = rank_numbers(stats, "composite", MAX_NUMBER)

    recommended_regular = rank_numbers(stats, "regular_strength", args.top_regular)
    recommended_special = rank_numbers(stats, "special_strength", 1)
    latest = draws[-1] if draws else None

    if args.json:
        output = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "total_draws": len(draws),
            "latest_period": latest.period if latest else None,
            "weights": weights,
            "recommended_regular": [s.number for s in recommended_regular],
            "recommended_special": recommended_special[0].number,
            "top_composite": [
                {
                    "number": s.number,
                    "score": round(s.scores["composite"], 4),
                    "total_hits": s.total_hits,
                    "current_gap": s.current_gap if s.current_gap < 10**6 else None,
                }
                for s in composite_ranked[:15]
            ],
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0

    print("香港六合彩分析结果")
    print(f"分析期数: {len(draws)} 期 | 近期窗口: {args.recent} 期")
    print(f"策略权重: {', '.join(f'{k}={v:.2f}' for k, v in weights.items())}")
    print("说明: 以下为历史统计模型输出，不代表真实开奖概率。")

    print_recommendation(recommended_regular, recommended_special, latest)
    print_strategy_breakdown(
        stats,
        [s.number for s in recommended_regular] + [recommended_special[0].number],
    )
    print_ranking("正码强度 Top 15", regular_ranked[:15], "regular_strength")
    print_ranking("特码强度 Top 15", special_ranked[:15], "special_strength")
    print_ranking("综合得分 Top 15", composite_ranked[:15], "composite")
    if args.top_special > 1:
        print_ranking(f"特码推荐 Top {args.top_special}", special_ranked[: args.top_special], "special_strength")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
