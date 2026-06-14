"""六合彩生肖映射与统计分析。"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Iterable

from lhc_analyzer import MAX_NUMBER, MIN_NUMBER, DrawRecord, normalize

# 十二生肖顺序（逆推序号用：01=本命生肖，02=前一个生肖……）
ZODIAC_NAMES: tuple[str, ...] = ("鼠", "牛", "虎", "兔", "龙", "蛇", "马", "羊", "猴", "鸡", "狗", "猪")

# 农历新年起始日 -> 该农历年本命生肖索引
LUNAR_YEAR_STARTS: tuple[tuple[date, int], ...] = (
    (date(2020, 1, 25), 0),   # 鼠
    (date(2021, 2, 12), 1),   # 牛
    (date(2022, 2, 1), 2),    # 虎
    (date(2023, 1, 22), 3),   # 兔
    (date(2024, 2, 10), 4),   # 龙
    (date(2025, 1, 29), 5),   # 蛇
    (date(2026, 2, 17), 6),   # 马
    (date(2027, 2, 6), 7),    # 羊
    (date(2028, 1, 26), 8),   # 猴
    (date(2029, 2, 13), 9),   # 鸡
    (date(2030, 2, 3), 10),   # 狗
    (date(2031, 1, 23), 11),  # 猪
)


@dataclass
class ZodiacStats:
    zodiac: str
    number_count: int = 0
    numbers: tuple[int, ...] = ()
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
            return 12.0
        return sum(self.gaps) / len(self.gaps)

    @property
    def current_gap(self) -> int:
        if self.last_seen_index is None:
            return 10**9
        return self.last_seen_index

    @property
    def theoretical_ratio(self) -> float:
        return self.number_count / MAX_NUMBER

    def actual_ratio(self, total_slots: int) -> float:
        if total_slots <= 0:
            return 0.0
        return self.total_hits / total_slots


def parse_lottery_date(raw: str) -> date:
    text = raw.strip()
    if " " in text:
        text = text.split(" ", 1)[0]
    return datetime.strptime(text, "%Y-%m-%d").date()


def year_zodiac_index_for_date(d: date) -> int:
    index = LUNAR_YEAR_STARTS[0][1]
    for start, zodiac_index in LUNAR_YEAR_STARTS:
        if d >= start:
            index = zodiac_index
    return index


def year_zodiac_name_for_date(d: date) -> str:
    return ZODIAC_NAMES[year_zodiac_index_for_date(d)]


def number_to_zodiac(number: int, year_zodiac_index: int) -> str:
    if not MIN_NUMBER <= number <= MAX_NUMBER:
        raise ValueError(f"号码超出范围: {number}")
    offset = (number - 1) % len(ZODIAC_NAMES)
    zodiac_index = (year_zodiac_index - offset) % len(ZODIAC_NAMES)
    return ZODIAC_NAMES[zodiac_index]


def zodiac_to_numbers(zodiac: str, year_zodiac_index: int) -> tuple[int, ...]:
    zodiac_index = ZODIAC_NAMES.index(zodiac)
    offset = (year_zodiac_index - zodiac_index) % len(ZODIAC_NAMES)
    start = offset + 1
    numbers = [n for n in range(start, MAX_NUMBER + 1, len(ZODIAC_NAMES))]
    return tuple(numbers)


def build_zodiac_table(year_zodiac_index: int) -> dict[str, tuple[int, ...]]:
    return {name: zodiac_to_numbers(name, year_zodiac_index) for name in ZODIAC_NAMES}


def build_zodiac_stats(draws: list[DrawRecord], recent_window: int) -> dict[str, ZodiacStats]:
    if not draws:
        return {}

    next_year_index = year_zodiac_index_for_date(parse_lottery_date(draws[-1].lottery_date))
    stats = {
        name: ZodiacStats(
            zodiac=name,
            number_count=len(zodiac_to_numbers(name, next_year_index)),
            numbers=zodiac_to_numbers(name, next_year_index),
        )
        for name in ZODIAC_NAMES
    }

    total = len(draws)
    recent_start = max(0, total - recent_window)
    last_seen: dict[str, int | None] = {name: None for name in ZODIAC_NAMES}

    for idx, draw in enumerate(draws):
        year_index = year_zodiac_index_for_date(parse_lottery_date(draw.lottery_date))
        is_recent = idx >= recent_start
        seen_in_draw: set[str] = set()

        for num in draw.regular:
            zodiac = number_to_zodiac(num, year_index)
            seen_in_draw.add(zodiac)
            s = stats[zodiac]
            s.total_hits += 1
            s.regular_hits += 1
            if is_recent:
                s.recent_hits += 1
                s.recent_regular_hits += 1

        zodiac = number_to_zodiac(draw.special, year_index)
        seen_in_draw.add(zodiac)
        s = stats[zodiac]
        s.total_hits += 1
        s.special_hits += 1
        if is_recent:
            s.recent_hits += 1
            s.recent_special_hits += 1

        for zodiac in seen_in_draw:
            s = stats[zodiac]
            if last_seen[zodiac] is not None:
                s.gaps.append(idx - last_seen[zodiac])
            last_seen[zodiac] = idx
            s.last_seen_index = total - 1 - idx

    return stats


def score_zodiacs(
    stats: dict[str, ZodiacStats],
    total_draws: int,
    recent_window: int,
    weights: dict[str, float],
) -> None:
    total_slots = total_draws * 7
    freq_all = {z: s.total_hits / max(total_slots, 1) for z, s in stats.items()}
    freq_recent = {
        z: s.recent_hits / max(min(recent_window, total_draws) * 7, 1) for z, s in stats.items()
    }
    freq_regular = {z: s.regular_hits / max(total_draws * 6, 1) for z, s in stats.items()}
    freq_special = {z: s.special_hits / max(total_draws, 1) for z, s in stats.items()}
    overdue = {z: float(s.current_gap) for z, s in stats.items()}
    avg_gap = {z: s.avg_gap for z, s in stats.items()}

    norm = {
        "frequency": normalize(freq_all),
        "recent_hot": normalize(freq_recent),
        "regular_strength": normalize(freq_regular),
        "special_strength": normalize(freq_special),
        "overdue": normalize(overdue),
        "gap_cycle": normalize(avg_gap, reverse=True),
    }

    for zodiac, s in stats.items():
        s.scores = {k: norm[k][zodiac] for k in norm}
        s.scores["composite"] = sum(weights[k] * norm[k][zodiac] for k in norm)


def rank_zodiacs(stats: dict[str, ZodiacStats], key: str = "composite") -> list[ZodiacStats]:
    return sorted(stats.values(), key=lambda s: s.scores.get(key, 0.0), reverse=True)


def format_numbers(numbers: Iterable[int]) -> str:
    return ", ".join(f"{n:02d}" for n in numbers)


def print_zodiac_section(title: str) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def print_zodiac_table(year_zodiac_index: int) -> None:
    year_name = ZODIAC_NAMES[year_zodiac_index]
    print_zodiac_section(f"生肖号码对照表（下一期基准：{year_name}年）")
    print(f"{'生肖':<4} {'号码数':<6} {'对应号码'}")
    print("-" * 72)
    for name in ZODIAC_NAMES:
        numbers = zodiac_to_numbers(name, year_zodiac_index)
        mark = " ★本命" if name == year_name else ""
        print(f"{name:<4} {len(numbers):<6} {format_numbers(numbers)}{mark}")


def print_zodiac_ratio(stats: dict[str, ZodiacStats], total_draws: int) -> None:
    total_slots = total_draws * 7
    print_zodiac_section("生肖历史出现比例")
    print(
        f"{'生肖':<4} {'次数':<6} {'实际比例':<10} {'理论比例':<10} "
        f"{'正码':<6} {'特码':<6} {'近窗':<6}"
    )
    print("-" * 72)
    ranked = sorted(stats.values(), key=lambda s: s.total_hits, reverse=True)
    for s in ranked:
        print(
            f"{s.zodiac:<4} {s.total_hits:<6} "
            f"{s.actual_ratio(total_slots):<10.2%} {s.theoretical_ratio:<10.2%} "
            f"{s.regular_hits:<6} {s.special_hits:<6} {s.recent_hits:<6}"
        )
    print()
    print("说明：实际比例 = 该生肖出现次数 / (期数×7)；理论比例 = 该生肖号码数/49。")


def print_latest_zodiac(latest: DrawRecord, year_zodiac_index: int) -> None:
    year_name = ZODIAC_NAMES[year_zodiac_index]
    regular_zodiacs = [number_to_zodiac(n, year_zodiac_index) for n in latest.regular]
    special_zodiac = number_to_zodiac(latest.special, year_zodiac_index)
    unique = sorted(set(regular_zodiacs + [special_zodiac]), key=ZODIAC_NAMES.index)

    print_zodiac_section(f"最新一期生肖分布（第 {latest.period} 期）")
    print(f"农历生肖年：{year_name}年")
    print("正码生肖：" + "、".join(regular_zodiacs))
    print(f"特码生肖：{special_zodiac}")
    print("本期涉及生肖：" + "、".join(unique))


def print_zodiac_prediction(
    stats: dict[str, ZodiacStats],
    latest: DrawRecord,
    year_zodiac_index: int,
    total_draws: int,
    top_n: int = 5,
) -> None:
    ranked = rank_zodiacs(stats, "composite")
    year_name = ZODIAC_NAMES[year_zodiac_index]
    latest_zodiacs = {number_to_zodiac(n, year_zodiac_index) for n in latest.all_numbers}
    total_slots = total_draws * 7

    print_zodiac_section("下一期生肖参考（统计模型输出，非真实概率）")
    print(f"基于最新一期（第 {latest.period} 期）及历史统计，{year_name}年号码映射下：")
    print()
    print(f"推荐关注 Top {top_n}：" + "、".join(s.zodiac for s in ranked[:top_n]))
    cold = [s for s in ranked if s.zodiac not in latest_zodiacs]
    if cold:
        print(f"上期未出生肖 Top 3：" + "、".join(s.zodiac for s in cold[:3]))
    print()
    print(
        f"{'排名':<4} {'生肖':<4} {'综合分':<8} {'实际比例':<10} {'遗漏':<6} "
        f"{'近窗':<6} {'对应号码'}"
    )
    print("-" * 72)
    for i, s in enumerate(ranked, start=1):
        gap = s.current_gap if s.current_gap < 10**6 else "-"
        in_latest = "✓" if s.zodiac in latest_zodiacs else ""
        print(
            f"{i:<4} {s.zodiac:<4} {s.scores.get('composite', 0.0):<8.3f} "
            f"{s.actual_ratio(total_slots):<10.2%} {gap!s:<6} "
            f"{s.recent_hits:<6} {format_numbers(s.numbers)} {in_latest}"
        )
    print()
    print("✓ = 最新一期已出现该生肖")


def print_zodiac_analysis(
    draws: list[DrawRecord],
    recent_window: int,
    weights: dict[str, float],
) -> None:
    if not draws:
        return

    latest = draws[-1]
    next_year_index = year_zodiac_index_for_date(parse_lottery_date(latest.lottery_date))
    stats = build_zodiac_stats(draws, recent_window)
    score_zodiacs(stats, total_draws=len(draws), recent_window=recent_window, weights=weights)

    print_zodiac_table(next_year_index)
    print_zodiac_ratio(stats, len(draws))
    print_latest_zodiac(latest, next_year_index)
    print_zodiac_prediction(stats, latest, next_year_index, len(draws))


def format_zodiac_report(
    draws: list[DrawRecord],
    recent_window: int,
    weights: dict[str, float],
) -> str:
    import io
    from contextlib import redirect_stdout

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        print_zodiac_analysis(draws, recent_window, weights)
    return buffer.getvalue()


def zodiac_analysis_to_dict(
    draws: list[DrawRecord],
    recent_window: int,
    weights: dict[str, float],
) -> dict:
    latest = draws[-1]
    next_year_index = year_zodiac_index_for_date(parse_lottery_date(latest.lottery_date))
    stats = build_zodiac_stats(draws, recent_window)
    score_zodiacs(stats, total_draws=len(draws), recent_window=recent_window, weights=weights)
    ranked = rank_zodiacs(stats, "composite")
    total_slots = len(draws) * 7

    return {
        "lunar_year_zodiac": ZODIAC_NAMES[next_year_index],
        "zodiac_table": {
            name: list(zodiac_to_numbers(name, next_year_index)) for name in ZODIAC_NAMES
        },
        "ratios": [
            {
                "zodiac": s.zodiac,
                "hits": s.total_hits,
                "actual_ratio": round(s.actual_ratio(total_slots), 4),
                "theoretical_ratio": round(s.theoretical_ratio, 4),
                "regular_hits": s.regular_hits,
                "special_hits": s.special_hits,
            }
            for s in sorted(stats.values(), key=lambda x: x.total_hits, reverse=True)
        ],
        "latest_zodiacs": {
            "regular": [number_to_zodiac(n, next_year_index) for n in latest.regular],
            "special": number_to_zodiac(latest.special, next_year_index),
        },
        "recommended_next": [s.zodiac for s in ranked[:5]],
        "ranking": [
            {
                "zodiac": s.zodiac,
                "score": round(s.scores.get("composite", 0.0), 4),
                "numbers": list(s.numbers),
                "current_gap": s.current_gap if s.current_gap < 10**6 else None,
            }
            for s in ranked
        ],
    }
