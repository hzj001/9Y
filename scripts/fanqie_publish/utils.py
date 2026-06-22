#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""工具函数：配置、章节解析、Markdown 清洗"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent


def load_config(config_path: str | None = None) -> dict[str, Any]:
    """加载配置。

    config_path 为空时默认读取脚本目录下的 config.yaml；
    也可传入相对仓库根目录或绝对路径的其它配置文件（用于多部小说分别配置）。
    """
    if config_path:
        p = Path(config_path)
        if not p.is_absolute():
            # 优先按“相对脚本目录”找，找不到再按“相对仓库根目录”
            cand = SCRIPT_DIR / config_path
            p = cand if cand.exists() else (ROOT / config_path)
    else:
        p = SCRIPT_DIR / "config.yaml"
    with open(p, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg


def writer_home_url(cfg: dict[str, Any]) -> str:
    return f"https://fanqienovel.com/main/writer/{cfg['writer_id']}/book-manage"


def new_chapter_url(cfg: dict[str, Any]) -> str:
    return (
        f"https://fanqienovel.com/main/writer/{cfg['writer_id']}/publish/{cfg['book_id']}"
        f"?enter_from=newchapter"
    )


def chapter_manage_url(cfg: dict[str, Any], type_: int = 1) -> str:
    """章节管理页。type=1 已发布章节列表；type=2 草稿箱。"""
    from urllib.parse import quote

    return (
        f"https://fanqienovel.com/main/writer/chapter-manage/"
        f"{cfg['writer_id']}&{quote(cfg['book_name'])}?type={type_}"
    )


def chapters_path(cfg: dict[str, Any]) -> Path:
    return ROOT / cfg["chapters_dir"]


def load_published_log(cfg: dict[str, Any]) -> set[int]:
    log_path = ROOT / cfg["published_log"]
    if not log_path.exists():
        return set()
    with open(log_path, encoding="utf-8") as f:
        data = json.load(f)
    return set(data.get("published", []))


def save_published_log(cfg: dict[str, Any], published: set[int]) -> None:
    log_path = ROOT / cfg["published_log"]
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump({"published": sorted(published)}, f, ensure_ascii=False, indent=2)


def list_chapter_files(cfg: dict[str, Any]) -> list[Path]:
    d = chapters_path(cfg)
    # chapter_glob 可在 config.yaml 中自定义；默认兼容老的 chapter_XX.md 命名。
    pattern = cfg.get("chapter_glob", "chapter_*.md")
    files = sorted(d.glob(pattern))
    return files


def parse_chapter_file(path: Path) -> tuple[int, str, str]:
    """返回 (章节序号, 标题, 正文)"""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines:
        raise ValueError(f"空文件: {path}")

    # 优先从文件名解析序号：兼容 chapter_64.md 与 第01章_xxx.md 两种命名
    file_m = re.search(r"chapter_(\d+)", path.stem, re.I) or re.search(r"第(\d+)章", path.stem)
    chapter_num = int(file_m.group(1)) if file_m else 0

    title_line = lines[0].strip()
    m = re.match(r"^#\s*第([一二三四五六七八九十百零\d]+)章\s*(.*)$", title_line)
    if not m:
        raise ValueError(f"无法解析标题行: {title_line}")

    num_raw, subtitle = m.group(1), m.group(2).strip()
    if not chapter_num:
        chapter_num = chinese_or_digit_to_int(num_raw)
    title = f"第{num_raw}章" + (f" {subtitle}" if subtitle else "")

    body_lines = lines[1:]
    body = clean_markdown_body(body_lines)
    return chapter_num, title, body


def chinese_or_digit_to_int(s: str) -> int:
    if s.isdigit():
        return int(s)
    mapping = {"零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
    if s == "十":
        return 10
    if s.startswith("十") and len(s) == 2:
        return 10 + mapping.get(s[1], 0)
    if s.endswith("十") and len(s) == 2:
        return mapping.get(s[0], 0) * 10
    if "十" in s:
        a, b = s.split("十", 1)
        tens = mapping.get(a, 0) if a else 1
        ones = mapping.get(b, 0) if b else 0
        return tens * 10 + ones
    return mapping.get(s, 0)


def clean_markdown_body(lines: list[str]) -> str:
    out: list[str] = []
    for line in lines:
        s = line.strip()
        if not s:
            out.append("")
            continue
        if s == "---":
            continue
        if s.startswith("#"):
            continue
        s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
        s = re.sub(r"\*(.+?)\*", r"\1", s)
        out.append(s)

    # 去掉首尾空行
    while out and not out[0].strip():
        out.pop(0)
    while out and not out[-1].strip():
        out.pop()
    return "\n".join(out)


def extract_word_count(header_text: str) -> int | None:
    m = re.search(r"正文字数\s*(\d+)", header_text)
    return int(m.group(1)) if m else None
