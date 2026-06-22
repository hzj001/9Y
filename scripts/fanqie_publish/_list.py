#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""列出当前作品的全部章节（名称+审核状态）。"""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from utils import load_config  # noqa: E402

BOOK_NAME = "雨夜来电情欲张力版"


def main() -> None:
    cfg = load_config()
    state_path = ROOT / cfg["state_file"]
    url = (
        f"https://fanqienovel.com/main/writer/chapter-manage/"
        f"{cfg['writer_id']}&{quote(BOOK_NAME)}?type=1"
    )
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(storage_state=str(state_path))
        page = context.new_page()
        page.goto(url, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(5000)
        # 滚动到底加载所有行
        for _ in range(8):
            page.mouse.wheel(0, 4000)
            page.wait_for_timeout(600)
        rows = page.evaluate(
            r"""() => {
                const out = [];
                // 抓所有包含“第N章”的行文本
                const els = document.querySelectorAll('*');
                const seen = new Set();
                document.querySelectorAll('div,tr,li').forEach(el => {
                    const t = (el.innerText||'').replace(/\s+/g,' ').trim();
                    if (/第\d+章/.test(t) && t.length < 60 && (t.includes('已发布')||t.includes('审核')||t.includes('未发布')||t.includes('草稿')||/\d{4}-\d{2}-\d{2}/.test(t))) {
                        if (!seen.has(t)) { seen.add(t); out.push(t); }
                    }
                });
                return out;
            }"""
        )
        print("COUNT=", len(rows), flush=True)
        for r in rows:
            print("ROW:", r, flush=True)
        page.screenshot(path=str(ROOT/"scripts"/"fanqie_publish"/"_list.png"), full_page=True)
        page.wait_for_timeout(800)
        browser.close()


if __name__ == "__main__":
    main()
