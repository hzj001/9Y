#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
番茄小说 - 浏览器自动填章/发布脚本

使用前请先运行 login.py 完成手动登录。

示例:
  # 查看将发布哪些章（不打开浏览器填表）
  python scripts/fanqie_publish/publish.py --dry-run

  # 只发第1章草稿（推荐先试）
  python scripts/fanqie_publish/publish.py --start 1 --end 1 --mode draft

  # 正式发布第1-5章（会点「下一步」「确认发布」）
  python scripts/fanqie_publish/publish.py --start 1 --end 5 --mode publish

  # 从断点续发（跳过 published_log.json 里已记录的章节）
  python scripts/fanqie_publish/publish.py --resume --mode draft
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from utils import (  # noqa: E402
    chapter_manage_url,
    chapters_path,
    extract_word_count,
    list_chapter_files,
    load_config,
    load_published_log,
    parse_chapter_file,
    save_published_log,
)

# 番茄章节编辑器选择器（若页面改版，可在此调整）
SEL_NUM = '.serial-editor-title-left .left-input input'  # “第 □ 章”里的序号框
SEL_TITLE = 'input.serial-editor-input-hint-area[placeholder="请输入标题"]'  # 标题（副标题）框
SEL_EDITOR = '.serial-editor-container .ProseMirror[contenteditable="true"]'
SEL_SAVE_DRAFT = 'button.auto-editor-save-btn'
SEL_PUBLISH_NEXT = 'button.auto-editor-next'  # 右上角真正的“下一步/发布”按钮
SEL_GUIDE_BTN = 'button.guide-card-footer-btn'  # 新手引导弹窗按钮
SEL_NEW_CHAPTER_BTN = 'button:has-text("新建章节")'  # 章节管理页“新建章节”按钮
SEL_HEADER = '.publish-header'
SEL_STATUS = '.publish-maintain-info-status'

# 标题里的“第N章”前缀，用于拆分出纯副标题
TITLE_PREFIX_RE = re.compile(r"^第[\d一二三四五六七八九十百零两]+章\s*")


def split_title(title: str) -> str:
    """从 '第十四章 加班夜' 拆出副标题 '加班夜'。无副标题时返回空串。"""
    return TITLE_PREFIX_RE.sub("", title).strip()


def dismiss_guides(page: Page) -> None:
    # 关闭新手引导（1/3 -> 2/3 -> 3/3 -> 完成），按钮固定 class
    for _ in range(8):
        guide = page.locator(SEL_GUIDE_BTN)
        if guide.count() == 0 or not guide.first.is_visible():
            break
        try:
            guide.first.click()
            page.wait_for_timeout(400)
        except Exception:
            break

    for _ in range(2):
        page.keyboard.press("Escape")
        page.wait_for_timeout(150)

    # 兜底：其它可能的关闭按钮
    for text in ("我知道了", "跳过", "完成"):
        try:
            loc = page.get_by_text(text, exact=True)
            for btn in loc.element_handles():
                box = btn.bounding_box()
                if box and box["y"] > 100:
                    btn.click()
                    page.wait_for_timeout(300)
        except Exception:
            pass


def _fill_input(page: Page, selector: str, value: str) -> str:
    loc = page.locator(selector).first
    loc.wait_for(state="visible", timeout=15000)
    loc.click()
    loc.fill("")
    loc.fill(value)
    page.wait_for_timeout(200)
    # 触发 React 表单更新
    loc.press("End")
    loc.press(" ")
    loc.press("Backspace")
    page.wait_for_timeout(100)
    return loc.input_value()


def fill_title(page: Page, chapter_num: int, title: str) -> None:
    """番茄标题区：序号框填阿拉伯数字（必填，需键盘输入），标题框填副标题。"""
    subtitle = split_title(title)
    if not subtitle:
        raise RuntimeError(f"无法从标题中解析出副标题: {title!r}")

    actual_sub = _fill_input(page, SEL_TITLE, subtitle)
    if actual_sub.strip() != subtitle:
        raise RuntimeError(f"标题写入失败，当前值: {actual_sub!r} (期望 {subtitle!r})")


def fill_number(page: Page, chapter_num: int) -> None:
    """序号框是字节 byte-input，fill() 无效，必须用键盘逐字输入。"""
    num = str(chapter_num)
    loc = page.locator(SEL_NUM).first
    loc.wait_for(state="visible", timeout=15000)
    for _ in range(3):
        loc.click()
        page.keyboard.press("Control+A")
        page.keyboard.press("Delete")
        page.wait_for_timeout(150)
        page.keyboard.type(num, delay=40)
        page.wait_for_timeout(250)
        if loc.input_value().strip() == num:
            return
    raise RuntimeError(f"章节序号写入失败，当前值: {loc.input_value()!r}")


def clear_editor(page: Page, editor) -> None:
    """彻底清空正文编辑器（页面可能自动恢复上次草稿，必须清干净再写）。"""
    for _ in range(5):
        editor.click()
        page.wait_for_timeout(150)
        page.keyboard.press("Control+A")
        page.keyboard.press("Delete")
        page.wait_for_timeout(200)
        remaining = editor.evaluate("el => (el.innerText || '').trim()")
        if len(remaining) == 0:
            return
    # 兜底：直接清空 DOM
    try:
        editor.evaluate("el => { el.innerHTML = '<p><br></p>'; }")
    except Exception:
        pass


def fill_body(page: Page, text: str) -> None:
    editor = page.locator(SEL_EDITOR).first
    editor.wait_for(state="visible", timeout=15000)

    clear_editor(page, editor)

    # 优先剪贴板粘贴（快）
    try:
        editor.click()
        page.evaluate("async (v) => await navigator.clipboard.writeText(v)", text)
        page.keyboard.press("Control+V")
        page.wait_for_timeout(1500)
    except Exception:
        pass

    body = editor.evaluate("el => (el.innerText || '').trim()")
    if len(body) < 20:
        # 退回逐行输入
        editor.click()
        for line in text.replace("\r\n", "\n").split("\n"):
            if line == "":
                page.keyboard.press("Enter")
            else:
                page.keyboard.type(line, delay=5)
                page.keyboard.press("Enter")
        page.wait_for_timeout(1000)

    body = editor.evaluate("el => (el.innerText || '').trim()")
    if len(body) < 20:
        raise RuntimeError("正文写入过短，可能失败")


def wait_word_count(page: Page, min_words: int, timeout_sec: int) -> int:
    """以编辑器实际正文长度为准（顶栏“正文字数”偶发不渲染，不能依赖它）。"""
    editor = page.locator(SEL_EDITOR).first
    start = time.time()
    last = 0
    while time.time() - start < timeout_sec:
        try:
            last = len(editor.evaluate("el => (el.innerText || '').trim()"))
        except Exception:
            last = 0
        if last >= min_words:
            return last
        page.wait_for_timeout(500)
    raise RuntimeError(f"等待正文同步超时（当前编辑器字数 {last}）")


def click_save_draft(page: Page) -> None:
    btn = page.locator(SEL_SAVE_DRAFT).first
    btn.wait_for(state="visible", timeout=10000)
    if btn.is_disabled():
        raise RuntimeError("「存草稿」按钮不可用")
    btn.click()
    wait_saved(page, 20)


def wait_saved(page: Page, timeout_sec: int) -> None:
    start = time.time()
    while time.time() - start < timeout_sec:
        header_text = page.locator(SEL_HEADER).inner_text(timeout=1000) if page.locator(SEL_HEADER).count() else ""
        status_text = page.locator(SEL_STATUS).inner_text(timeout=1000) if page.locator(SEL_STATUS).count() else ""
        combined = header_text + status_text
        if re.search(r"已保存|保存成功|草稿已保存", combined):
            return
        page.wait_for_timeout(500)
    raise RuntimeError("等待保存成功超时")


def check_validation_errors(page: Page) -> None:
    """点击下一步后若出现红色校验横幅，抛出明确错误。"""
    try:
        banner = page.locator("text=/章节序号只支持|正文至少输入|请输入标题|标题不能/").first
        if banner.count() and banner.is_visible(timeout=500):
            raise RuntimeError(f"发布校验未通过: {banner.inner_text().strip()}")
    except PlaywrightTimeout:
        pass


def try_publish(page: Page, debug_shot: Path | None = None) -> None:
    """点击发布流程：右上角「下一步」-> 处理弹窗 -> 确认发布，并校验成功。"""

    entry = page.locator(SEL_PUBLISH_NEXT).first
    entry.wait_for(state="visible", timeout=10000)
    if entry.is_disabled():
        raise RuntimeError("发布按钮（下一步）当前不可用，可能标题/正文未通过校验")

    entry.click()
    page.wait_for_timeout(2000)

    check_validation_errors(page)

    if debug_shot is not None:
        try:
            page.screenshot(path=str(debug_shot))
        except Exception:
            pass

    # 发布依次弹出：错别字提示(提交) -> 内容检测方式(仅基础检测) -> 发布设置(选否+确认发布)。
    # 「仅基础检测」优先以免消耗「全面检测」次数。
    confirm_patterns = [
        re.compile(r"^仅基础检测$"),
        re.compile(r"^提交$"),
        re.compile(r"确认发布|立即发布|^确认$|^确定$|^发布$"),
    ]
    for _ in range(6):
        # 「发布设置」里「是否使用AI」必选，选「否」
        try:
            if page.get_by_text("是否使用AI", exact=False).first.is_visible(timeout=500):
                page.get_by_text("否", exact=True).first.click()
                page.wait_for_timeout(300)
        except Exception:
            pass

        clicked = False
        for pat in confirm_patterns:
            btn = page.get_by_role("button", name=pat).first
            try:
                if not (btn.count() and btn.is_visible(timeout=2000)):
                    continue
            except PlaywrightTimeout:
                continue
            for _ in range(10):
                if not btn.is_disabled():
                    break
                page.wait_for_timeout(500)
            btn.click()
            page.wait_for_timeout(2500)
            clicked = True
            break
        if not clicked:
            break

    if debug_shot is not None:
        try:
            after = debug_shot.with_name(debug_shot.stem + "_after.png")
            page.screenshot(path=str(after))
            print(f"  [debug] after-confirm url={page.url}")
        except Exception:
            pass

    verify_published(page, 15)


def verify_published(page: Page, timeout_sec: int) -> None:
    """校验发布是否真正成功：成功提示 toast / 跳转 / 已提交状态。"""
    start = time.time()
    while time.time() - start < timeout_sec:
        # 成功提示（arco message / toast）
        try:
            body_text = page.locator("body").inner_text(timeout=1000)
        except Exception:
            body_text = ""
        if re.search(r"发布成功|提交成功|审核中|已发布", body_text):
            return
        # 已离开编辑页（跳回章节管理）也视为成功
        if "enter_from=newchapter" not in page.url and "/publish/" not in page.url:
            return
        page.wait_for_timeout(500)
    raise RuntimeError("未检测到发布成功提示，可能发布未完成")


def open_new_chapter_editor(context, manage_page: Page, cfg: dict) -> Page:
    """通过“章节管理页 -> 新建章节”按钮创建一个全新章节，返回编辑器页面。

    关键：每次都点“新建章节”生成新的章节ID，避免反复覆盖同一章。
    """
    manage_page.goto(chapter_manage_url(cfg), wait_until="domcontentloaded", timeout=60000)
    manage_page.wait_for_timeout(2500)
    dismiss_guides(manage_page)

    btn = manage_page.locator(SEL_NEW_CHAPTER_BTN).first
    btn.wait_for(state="visible", timeout=20000)

    before = list(context.pages)
    btn.click()
    manage_page.wait_for_timeout(3000)

    new_pages = [p for p in context.pages if p not in before]
    editor = new_pages[-1] if new_pages else manage_page
    try:
        editor.wait_for_load_state("domcontentloaded", timeout=20000)
    except Exception:
        pass
    editor.wait_for_timeout(2000)
    dismiss_guides(editor)

    if "enter_from=newchapter" not in editor.url:
        raise RuntimeError(f"未进入新建章节编辑器，当前URL: {editor.url}")
    return editor


def publish_one_chapter(
    context,
    manage_page: Page,
    cfg: dict,
    chapter_num: int,
    title: str,
    body: str,
    mode: str,
) -> None:
    editor = open_new_chapter_editor(context, manage_page, cfg)
    print(f"  -> 新建章节编辑器: {editor.url}")
    try:
        editor.locator(SEL_TITLE).first.wait_for(state="visible", timeout=15000)
        editor.locator(SEL_EDITOR).first.wait_for(state="visible", timeout=15000)

        print(f"  -> 填写标题: 第{chapter_num}章 {split_title(title)}")
        fill_title(editor, chapter_num, title)

        print(f"  -> 填写正文 ({len(body)} 字)...")
        fill_body(editor, body)

        print(f"  -> 填写章节序号: {chapter_num}")
        fill_number(editor, chapter_num)

        min_words = max(20, min(100, len(body) // 2))
        count = wait_word_count(editor, min_words, cfg.get("word_count_timeout", 20))
        print(f"  -> 编辑器字数: {count}")

        if mode == "draft":
            print("  -> 存草稿...")
            click_save_draft(editor)
            print("  -> ✅ 草稿已保存")
        elif mode == "publish":
            print("  -> 尝试正式发布...")
            debug_shot = ROOT / "scripts" / "fanqie_publish" / "_last_publish.png"
            try_publish(editor, debug_shot=debug_shot)
            editor.wait_for_timeout(2000)
            print("  -> ✅ 已执行发布流程（请在后台核对章节状态）")
        else:
            raise ValueError(f"未知模式: {mode}")
    finally:
        # 编辑器若是新标签页，发布后关闭，避免标签堆积
        if editor is not manage_page:
            try:
                editor.close()
            except Exception:
                pass


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="番茄小说自动填章/发布")
    p.add_argument("--start", type=int, default=1, help="起始章节序号（含）")
    p.add_argument("--end", type=int, default=0, help="结束章节序号（含），0=到最后一章")
    p.add_argument("--count", type=int, default=0, help="最多发布 N 章（与 start/end 二选一逻辑，优先 count）")
    p.add_argument("--mode", choices=["draft", "publish"], default=None, help="draft=只存草稿; publish=正式发布")
    p.add_argument("--resume", action="store_true", help="跳过 published_log 中已发布章节")
    p.add_argument("--dry-run", action="store_true", help="只打印计划，不启动浏览器")
    p.add_argument("--no-headless", action="store_true", default=True, help="显示浏览器（默认开启）")
    p.add_argument("--delay", type=int, default=None, help="章间间隔秒数")
    p.add_argument(
        "--config",
        default=None,
        help="指定配置文件（用于发布不同小说，如 config.liuxing.yaml）；缺省读取 config.yaml",
    )
    return p


def main() -> None:
    args = build_arg_parser().parse_args()
    cfg = load_config(args.config)
    mode = args.mode or cfg.get("default_mode", "draft")
    delay = args.delay if args.delay is not None else cfg.get("delay_between_chapters", 8)

    state_path = ROOT / cfg["state_file"]
    if not args.dry_run and not state_path.exists():
        print(f"❌ 未找到登录状态: {state_path}")
        print("请先运行: python scripts/fanqie_publish/login.py")
        sys.exit(1)

    files = list_chapter_files(cfg)
    if not files:
        print(f"❌ 未找到章节文件: {chapters_path(cfg)}")
        sys.exit(1)

    chapters: list[tuple[int, str, str, Path]] = []
    for f in files:
        num, title, body = parse_chapter_file(f)
        chapters.append((num, title, body, f))
    chapters.sort(key=lambda x: x[0])

    # 始终加载已发布记录（用于合并保存，避免覆盖丢失）；--resume 时还用于过滤
    published = load_published_log(cfg)

    selected = [c for c in chapters if c[0] >= args.start]
    if args.end and args.end > 0:
        selected = [c for c in selected if c[0] <= args.end]
    if args.count and args.count > 0:
        selected = selected[: args.count]
    if args.resume:
        selected = [c for c in selected if c[0] not in published]

    if not selected:
        print("没有待发布的章节。")
        return

    print("=" * 60)
    print(f"模式: {mode} | 待处理: {len(selected)} 章 | 章间间隔: {delay}s")
    print("=" * 60)
    for num, title, body, path in selected:
        print(f"  [{num:02d}] {title}  ({len(body)} 字)  <- {path.name}")
    print("=" * 60)

    if args.dry_run:
        print("dry-run 结束，未启动浏览器。")
        return

    if mode == "publish":
        ans = input("⚠️  publish 模式将尝试正式发布。确认继续? [y/N] ").strip().lower()
        if ans != "y":
            print("已取消。")
            return

    success: list[int] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.no_headless)
        context = browser.new_context(storage_state=str(state_path))
        manage_page = context.new_page()

        consec_fail = 0
        stop_threshold = int(cfg.get("stop_after_consecutive_failures", 3))
        for i, (num, title, body, path) in enumerate(selected, 1):
            print(f"\n[{i}/{len(selected)}] 第{num}章 {title}")
            try:
                publish_one_chapter(context, manage_page, cfg, num, title, body, mode)
                success.append(num)
                published.add(num)
                save_published_log(cfg, published)
                consec_fail = 0
            except Exception as e:
                print(f"  ❌ 失败: {e}")
                consec_fail += 1
                if consec_fail >= stop_threshold:
                    print(
                        f"\n⚠️ 连续 {consec_fail} 章发布失败，疑似触发番茄发布上限/限流，已自动停止。"
                    )
                    print("   建议隔几小时或次日再运行（加 --resume 续发未完成章节）。")
                    break
                print("  （已跳过本章，继续下一章）")
            if i < len(selected):
                print(f"  ... 等待 {delay} 秒")
                time.sleep(delay)

        browser.close()

    print("\n" + "=" * 60)
    print(f"完成。成功: {len(success)} 章 -> {success}")
    print("请到番茄作家后台核对章节列表。")
    print("=" * 60)


if __name__ == "__main__":
    main()
