#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""临时登录脚本：弹出浏览器供手动登录，轮询检测登录成功后自动保存 state。"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from utils import load_config, writer_home_url  # noqa: E402

LOGIN_COOKIE_NAMES = {"sessionid", "sid_tt", "sid_guard", "uid_tt", "sessionid_ss"}
MAX_WAIT_SEC = 300


def main() -> None:
    cfg = load_config()
    state_path = ROOT / cfg["state_file"]
    state_path.parent.mkdir(parents=True, exist_ok=True)

    print("LOGIN_BROWSER_OPENING", flush=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(writer_home_url(cfg), timeout=60000)

        start = time.time()
        saved = False
        while time.time() - start < MAX_WAIT_SEC:
            cookies = context.cookies()
            names = {c["name"] for c in cookies}
            if names & LOGIN_COOKIE_NAMES:
                # 多等几秒确保 cookie 全部写入
                time.sleep(3)
                context.storage_state(path=str(state_path))
                saved = True
                print("LOGIN_SUCCESS_SAVED", flush=True)
                break
            time.sleep(2)

        browser.close()

    if not saved:
        print("LOGIN_TIMEOUT", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
