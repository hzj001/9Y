#!/usr/bin/env python3
"""六合彩分析工具 — 跨平台图形界面（集成全部功能）。"""

from __future__ import annotations

import json
import sys
import threading
import tkinter as tk
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from lhc_analyzer import (
    DEFAULT_WEIGHTS,
    LOTTERY_TYPES,
    WEIGHT_LABELS,
    format_number_report,
    format_result_text,
    format_summary_report,
    normalize_weights,
    resolve_lottery_code,
    result_to_json,
    run_analysis_for_code,
)
from lhc_zodiac import format_zodiac_report

IS_MACOS = sys.platform == "darwin"
IS_WINDOWS = sys.platform == "win32"

LOTTERY_OPTIONS = [
    ("xg6", "香港六合彩"),
    ("am6", "老澳门六合彩"),
    ("nam6", "新澳门六合彩"),
    ("all", "全部分析"),
]


@dataclass
class GuiAnalysisBundle:
    summary: str = ""
    number_report: str = ""
    zodiac_report: str = ""
    full_report: str = ""
    json_payload: dict | list = field(default_factory=dict)


class ScrollableFrame(ttk.Frame):
    def __init__(self, parent: tk.Widget) -> None:
        super().__init__(parent)
        canvas = tk.Canvas(self, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=canvas.yview)
        self.inner = ttk.Frame(canvas)
        self.inner.bind(
            "<Configure>",
            lambda _e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=self.inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)


class LhcAnalyzerApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("六合彩分析工具")
        self.geometry("1280x820")
        self.minsize(1080, 700)

        self._busy = False
        self._weight_vars: dict[str, tk.DoubleVar] = {}
        self._weight_value_labels: dict[str, ttk.Label] = {}
        self._last_bundle: GuiAnalysisBundle | None = None
        self._result_widgets: dict[str, scrolledtext.ScrolledText] = {}

        self._setup_style()
        self._setup_platform()
        self._build_ui()
        self._reset_weights()

    def _setup_platform(self) -> None:
        if IS_MACOS:
            self.lift()
            self.focus_force()

    def _setup_style(self) -> None:
        ui_font, mono_font = self._pick_fonts()
        self._ui_font = ui_font
        self._mono_font = mono_font

        style = ttk.Style(self)
        if IS_MACOS and "aqua" in style.theme_names():
            style.theme_use("aqua")
        elif IS_WINDOWS and "vista" in style.theme_names():
            style.theme_use("vista")
        elif "clam" in style.theme_names():
            style.theme_use("clam")

        self.option_add("*Font", ui_font)

    @staticmethod
    def _pick_fonts() -> tuple[tuple[str, int], tuple[str, int]]:
        if IS_MACOS:
            return ("PingFang SC", 12), ("Menlo", 11)
        if IS_WINDOWS:
            return ("Microsoft YaHei UI", 10), ("Consolas", 10)
        return ("TkDefaultFont", 10), ("Monospace", 10)

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=12)
        root.pack(fill=tk.BOTH, expand=True)
        root.rowconfigure(0, weight=1)
        root.columnconfigure(0, weight=1)

        paned = ttk.Panedwindow(root, orient=tk.HORIZONTAL)
        paned.grid(row=0, column=0, sticky="nsew")

        left_wrap = ttk.Frame(paned, width=340)
        right_wrap = ttk.Frame(paned)
        paned.add(left_wrap, weight=0)
        paned.add(right_wrap, weight=1)

        self._build_controls(left_wrap)
        self._build_results(right_wrap)
        self._build_status_bar(root)

    def _build_controls(self, parent: ttk.Frame) -> None:
        scroll = ScrollableFrame(parent)
        scroll.pack(fill=tk.BOTH, expand=True)
        panel = ttk.LabelFrame(scroll.inner, text="分析设置", padding=12)
        panel.pack(fill=tk.BOTH, expand=True)
        panel.columnconfigure(1, weight=1)

        row = 0
        ttk.Label(panel, text="彩种").grid(row=row, column=0, sticky="w", pady=4)
        self.lottery_var = tk.StringVar(value="nam6")
        lottery_box = ttk.Combobox(
            panel,
            textvariable=self.lottery_var,
            state="readonly",
            values=[label for _, label in LOTTERY_OPTIONS],
            width=22,
        )
        lottery_box.grid(row=row, column=1, sticky="ew", pady=4)
        lottery_box.current(2)
        row += 1

        ttk.Label(panel, text="分析期数").grid(row=row, column=0, sticky="w", pady=4)
        self.limit_var = tk.StringVar(value="200")
        ttk.Entry(panel, textvariable=self.limit_var).grid(row=row, column=1, sticky="ew", pady=4)
        row += 1
        ttk.Label(panel, text="0 = 全部历史", foreground="#666666").grid(row=row, column=1, sticky="w")
        row += 1

        ttk.Label(panel, text="近期窗口").grid(row=row, column=0, sticky="w", pady=4)
        self.recent_var = tk.StringVar(value="30")
        ttk.Entry(panel, textvariable=self.recent_var).grid(row=row, column=1, sticky="ew", pady=4)
        row += 1

        ttk.Label(panel, text="推荐正码数").grid(row=row, column=0, sticky="w", pady=4)
        self.top_regular_var = tk.StringVar(value="6")
        ttk.Spinbox(panel, from_=1, to=12, textvariable=self.top_regular_var, width=10).grid(
            row=row, column=1, sticky="w", pady=4
        )
        row += 1

        ttk.Label(panel, text="特码 Top N").grid(row=row, column=0, sticky="w", pady=4)
        self.top_special_var = tk.StringVar(value="3")
        ttk.Spinbox(panel, from_=1, to=12, textvariable=self.top_special_var, width=10).grid(
            row=row, column=1, sticky="w", pady=4
        )
        row += 1

        options = ttk.Frame(panel)
        options.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(8, 4))
        self.cache_var = tk.BooleanVar(value=True)
        self.refresh_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(options, text="写入本地缓存", variable=self.cache_var).pack(anchor="w")
        ttk.Checkbutton(options, text="强制刷新数据（忽略缓存）", variable=self.refresh_var).pack(anchor="w")
        row += 1

        ttk.Separator(panel).grid(row=row, column=0, columnspan=2, sticky="ew", pady=12)
        row += 1

        weight_box = ttk.LabelFrame(
            panel,
            text="策略权重（号码 + 生肖共用，自动归一化）",
            padding=8,
        )
        weight_box.grid(row=row, column=0, columnspan=2, sticky="ew")
        weight_box.columnconfigure(1, weight=1)
        row += 1

        for wrow, (key, default) in enumerate(DEFAULT_WEIGHTS.items()):
            label = WEIGHT_LABELS.get(key, key)
            ttk.Label(weight_box, text=label, width=10).grid(row=wrow, column=0, sticky="w", pady=4)
            var = tk.DoubleVar(value=default * 100)
            self._weight_vars[key] = var
            scale = ttk.Scale(
                weight_box,
                from_=0,
                to=100,
                variable=var,
                orient=tk.HORIZONTAL,
                command=lambda _v, k=key: self._update_weight_label(k),
            )
            scale.grid(row=wrow, column=1, sticky="ew", padx=(8, 8), pady=4)
            value_label = ttk.Label(weight_box, text="0.00", width=6)
            value_label.grid(row=wrow, column=2, sticky="e")
            self._weight_value_labels[key] = value_label

        self.normalized_label = ttk.Label(
            panel,
            text="",
            foreground="#0066aa",
            wraplength=300,
            justify=tk.LEFT,
        )
        self.normalized_label.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(8, 4))
        row += 1

        btn_row1 = ttk.Frame(panel)
        btn_row1.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(8, 4))
        btn_row1.columnconfigure(0, weight=1)
        btn_row1.columnconfigure(1, weight=1)
        ttk.Button(btn_row1, text="恢复默认权重", command=self._reset_weights).grid(
            row=0, column=0, sticky="ew", padx=(0, 4)
        )
        self.analyze_btn = ttk.Button(btn_row1, text="开始分析", command=self._on_analyze)
        self.analyze_btn.grid(row=0, column=1, sticky="ew", padx=(4, 0))
        row += 1

        btn_row2 = ttk.Frame(panel)
        btn_row2.grid(row=row, column=0, columnspan=2, sticky="ew")
        btn_row2.columnconfigure(0, weight=1)
        btn_row2.columnconfigure(1, weight=1)
        ttk.Button(btn_row2, text="导出 JSON", command=self._export_json).grid(
            row=0, column=0, sticky="ew", padx=(0, 4), pady=(4, 0)
        )
        ttk.Button(btn_row2, text="复制完整报告", command=self._copy_full_report).grid(
            row=0, column=1, sticky="ew", padx=(4, 0), pady=(4, 0)
        )
        row += 1

        ttk.Label(
            panel,
            text="功能：香港/老澳门/新澳门 · 号码推荐 · 生肖比例 · 下一期生肖 · 权重可调",
            foreground="#666666",
            wraplength=300,
            justify=tk.LEFT,
        ).grid(row=row, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        row += 1
        ttk.Label(
            panel,
            text="说明：结果为历史统计模型输出，不代表真实开奖概率，请理性参考。",
            foreground="#888888",
            wraplength=300,
            justify=tk.LEFT,
        ).grid(row=row, column=0, columnspan=2, sticky="ew", pady=(6, 0))

    def _build_results(self, parent: ttk.Frame) -> None:
        panel = ttk.Frame(parent)
        panel.pack(fill=tk.BOTH, expand=True)
        panel.rowconfigure(1, weight=1)
        panel.columnconfigure(0, weight=1)

        ttk.Label(
            panel,
            text="分析结果（综合摘要 / 号码 / 生肖 / 完整报告）",
            font=(self._ui_font[0], self._ui_font[1], "bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))

        notebook = ttk.Notebook(panel)
        notebook.grid(row=1, column=0, sticky="nsew")

        tabs = [
            ("summary", "综合摘要"),
            ("number", "号码分析"),
            ("zodiac", "生肖分析"),
            ("full", "完整报告"),
        ]
        for key, title in tabs:
            frame = ttk.Frame(notebook, padding=4)
            notebook.add(frame, text=title)
            frame.rowconfigure(0, weight=1)
            frame.columnconfigure(0, weight=1)
            text = scrolledtext.ScrolledText(
                frame,
                wrap=tk.WORD,
                font=self._mono_font,
                state=tk.DISABLED,
            )
            text.grid(row=0, column=0, sticky="nsew")
            self._result_widgets[key] = text

    def _build_status_bar(self, parent: ttk.Frame) -> None:
        self.status_var = tk.StringVar(value="就绪 — 请选择彩种并点击「开始分析」")
        ttk.Label(parent, textvariable=self.status_var, anchor="w").grid(
            row=1, column=0, sticky="ew", pady=(8, 0)
        )

    def _reset_weights(self) -> None:
        for key, value in DEFAULT_WEIGHTS.items():
            self._weight_vars[key].set(value * 100)
            self._update_weight_label(key)

    def _update_weight_label(self, key: str) -> None:
        raw = {k: v.get() for k, v in self._weight_vars.items()}
        try:
            normalized = normalize_weights(raw)
        except ValueError:
            normalized = {k: 0.0 for k in raw}
        self._weight_value_labels[key].configure(text=f"{normalized[key]:.2f}")
        summary = " | ".join(f"{WEIGHT_LABELS[k]} {normalized[k]:.0%}" for k in DEFAULT_WEIGHTS)
        self.normalized_label.configure(text=f"归一化后：{summary}")

    def _collect_weights(self) -> dict[str, float]:
        raw = {key: var.get() for key, var in self._weight_vars.items()}
        return normalize_weights(raw)

    def _selected_lottery_code(self) -> str:
        label = self.lottery_var.get()
        for code, name in LOTTERY_OPTIONS:
            if name == label:
                return code
        return "xg6"

    def _parse_positive_int(self, raw: str, field_name: str, allow_zero: bool = False) -> int:
        value = int(raw.strip())
        if allow_zero:
            if value < 0:
                raise ValueError(f"{field_name} 不能小于 0")
        elif value <= 0:
            raise ValueError(f"{field_name} 必须大于 0")
        return value

    def _collect_params(self) -> tuple[str, dict[str, float], int | None, int, int, int, bool, bool]:
        limit_raw = self.limit_var.get().strip()
        limit = None if limit_raw in ("", "0") else self._parse_positive_int(limit_raw, "分析期数")
        recent = self._parse_positive_int(self.recent_var.get(), "近期窗口")
        top_regular = self._parse_positive_int(self.top_regular_var.get(), "推荐正码数")
        top_special = self._parse_positive_int(self.top_special_var.get(), "特码 Top N")
        weights = self._collect_weights()
        lottery_type = self._selected_lottery_code()
        return (
            lottery_type,
            weights,
            limit,
            recent,
            top_regular,
            top_special,
            self.refresh_var.get(),
            self.cache_var.get(),
        )

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = tk.DISABLED if busy else tk.NORMAL
        self.analyze_btn.configure(state=state)

    def _set_text_widget(self, widget: scrolledtext.ScrolledText, text: str) -> None:
        widget.configure(state=tk.NORMAL)
        widget.delete("1.0", tk.END)
        widget.insert(tk.END, text)
        widget.configure(state=tk.DISABLED)

    def _show_bundle(self, bundle: GuiAnalysisBundle) -> None:
        self._set_text_widget(self._result_widgets["summary"], bundle.summary)
        self._set_text_widget(self._result_widgets["number"], bundle.number_report)
        self._set_text_widget(self._result_widgets["zodiac"], bundle.zodiac_report)
        self._set_text_widget(self._result_widgets["full"], bundle.full_report)

    def _clear_results(self, message: str) -> None:
        empty = GuiAnalysisBundle(summary=message, number_report=message, zodiac_report=message, full_report=message)
        self._show_bundle(empty)

    def _on_analyze(self) -> None:
        if self._busy:
            return
        try:
            params = self._collect_params()
        except ValueError as exc:
            messagebox.showerror("参数错误", str(exc))
            return

        self._set_busy(True)
        self.status_var.set("正在分析，请稍候...")
        self._clear_results("正在拉取数据并计算，请稍候...\n")

        thread = threading.Thread(target=self._analyze_worker, args=(params,), daemon=True)
        thread.start()

    def _analyze_worker(self, params: tuple) -> None:
        (
            lottery_type,
            weights,
            limit,
            recent,
            top_regular,
            top_special,
            refresh,
            use_cache,
        ) = params
        try:
            codes = resolve_lottery_code(lottery_type)
            if isinstance(codes, str):
                codes = [codes]

            summaries: list[str] = []
            numbers: list[str] = []
            zodiacs: list[str] = []
            fulls: list[str] = []
            json_items: list[dict] = []
            errors: list[str] = []

            for code in codes:
                name = LOTTERY_TYPES[code]["name"]
                self.after(0, lambda n=name: self.status_var.set(f"正在分析：{n}..."))
                try:
                    result = run_analysis_for_code(
                        code,
                        weights,
                        limit=limit,
                        recent=recent,
                        refresh=refresh,
                        use_cache=use_cache,
                        top_regular=top_regular,
                        top_special=top_special,
                    )
                    summaries.append(format_summary_report(result))
                    numbers.append(format_number_report(result))
                    zodiacs.append(format_zodiac_report(result.draws, recent, weights))
                    fulls.append(format_result_text(result))
                    json_items.append(result_to_json(result))
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"[{name}] {exc}")

            if not summaries and errors:
                raise RuntimeError("\n".join(errors))

            divider = "\n\n" + ("=" * 72) + "\n\n"
            bundle = GuiAnalysisBundle(
                summary=divider.join(summaries),
                number_report=divider.join(numbers),
                zodiac_report=divider.join(zodiacs),
                full_report=divider.join(fulls),
                json_payload=json_items[0] if len(json_items) == 1 else {item["lottery_code"]: item for item in json_items},
            )
            if errors:
                err_text = "\n部分彩种分析失败：\n" + "\n".join(errors)
                bundle.full_report += err_text
                bundle.summary += err_text

            self.after(0, lambda b=bundle: self._finish_success(b))
        except Exception as exc:  # noqa: BLE001
            self.after(0, lambda: self._finish_error(str(exc)))

    def _finish_success(self, bundle: GuiAnalysisBundle) -> None:
        self._last_bundle = bundle
        self._show_bundle(bundle)
        self.status_var.set("分析完成 — 可切换标签页查看号码/生肖，或导出 JSON")
        self._set_busy(False)

    def _finish_error(self, message: str) -> None:
        self._last_bundle = None
        err = f"分析失败：\n{message}"
        self._clear_results(err)
        self.status_var.set("分析失败")
        self._set_busy(False)
        messagebox.showerror("分析失败", message)

    def _export_json(self) -> None:
        if not self._last_bundle or not self._last_bundle.json_payload:
            messagebox.showinfo("提示", "请先完成一次分析，再导出 JSON。")
            return
        path = filedialog.asksaveasfilename(
            title="导出 JSON",
            defaultextension=".json",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")],
            initialfile="lhc_analysis.json",
        )
        if not path:
            return
        Path(path).write_text(
            json.dumps(self._last_bundle.json_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        messagebox.showinfo("导出成功", f"已保存到：\n{path}")

    def _copy_full_report(self) -> None:
        if not self._last_bundle or not self._last_bundle.full_report.strip():
            messagebox.showinfo("提示", "请先完成一次分析，再复制报告。")
            return
        self.clipboard_clear()
        self.clipboard_append(self._last_bundle.full_report)
        self.status_var.set("完整报告已复制到剪贴板")


def main() -> None:
    app = LhcAnalyzerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
