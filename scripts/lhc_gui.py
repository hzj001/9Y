#!/usr/bin/env python3
"""六合彩分析工具 — 跨平台图形界面（Windows / macOS / Linux）。"""

from __future__ import annotations

import sys
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

from lhc_analyzer import (
    DEFAULT_WEIGHTS,
    LOTTERY_TYPES,
    WEIGHT_LABELS,
    format_result_text,
    normalize_weights,
    resolve_lottery_code,
    run_analysis_for_code,
)

IS_MACOS = sys.platform == "darwin"
IS_WINDOWS = sys.platform == "win32"

LOTTERY_OPTIONS = [
    ("xg6", "香港六合彩"),
    ("am6", "老澳门六合彩"),
    ("nam6", "新澳门六合彩"),
    ("all", "全部分析"),
]


class LhcAnalyzerApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("六合彩分析工具")
        self.geometry("1120x760")
        self.minsize(960, 640)

        self._busy = False
        self._weight_vars: dict[str, tk.DoubleVar] = {}
        self._weight_value_labels: dict[str, ttk.Label] = {}

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
        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)

        self._build_controls(root)
        self._build_results(root)
        self._build_status_bar(root)

    def _build_controls(self, parent: ttk.Frame) -> None:
        panel = ttk.LabelFrame(parent, text="分析设置", padding=12)
        panel.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        panel.columnconfigure(1, weight=1)

        ttk.Label(panel, text="彩种").grid(row=0, column=0, sticky="w", pady=4)
        self.lottery_var = tk.StringVar(value="nam6")
        lottery_box = ttk.Combobox(
            panel,
            textvariable=self.lottery_var,
            state="readonly",
            values=[label for _, label in LOTTERY_OPTIONS],
            width=22,
        )
        lottery_box.grid(row=0, column=1, sticky="ew", pady=4)
        lottery_box.current(2)

        ttk.Label(panel, text="分析期数").grid(row=1, column=0, sticky="w", pady=4)
        self.limit_var = tk.StringVar(value="200")
        ttk.Entry(panel, textvariable=self.limit_var, width=24).grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Label(panel, text="0 = 全部", foreground="#666666").grid(row=2, column=1, sticky="w")

        ttk.Label(panel, text="近期窗口").grid(row=3, column=0, sticky="w", pady=4)
        self.recent_var = tk.StringVar(value="30")
        ttk.Entry(panel, textvariable=self.recent_var, width=24).grid(row=3, column=1, sticky="ew", pady=4)

        options = ttk.Frame(panel)
        options.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 4))
        self.cache_var = tk.BooleanVar(value=True)
        self.refresh_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(options, text="写入本地缓存", variable=self.cache_var).pack(anchor="w")
        ttk.Checkbutton(options, text="强制刷新数据", variable=self.refresh_var).pack(anchor="w")

        ttk.Separator(panel).grid(row=5, column=0, columnspan=2, sticky="ew", pady=12)

        weight_box = ttk.LabelFrame(panel, text="策略权重（拖动滑块，分析时自动归一化）", padding=8)
        weight_box.grid(row=6, column=0, columnspan=2, sticky="ew")
        weight_box.columnconfigure(1, weight=1)

        for row, (key, default) in enumerate(DEFAULT_WEIGHTS.items()):
            label = WEIGHT_LABELS.get(key, key)
            ttk.Label(weight_box, text=label, width=10).grid(row=row, column=0, sticky="w", pady=4)

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
            scale.grid(row=row, column=1, sticky="ew", padx=(8, 8), pady=4)

            value_label = ttk.Label(weight_box, text="0.00", width=6)
            value_label.grid(row=row, column=2, sticky="e")
            self._weight_value_labels[key] = value_label

        self.normalized_label = ttk.Label(
            panel,
            text="",
            foreground="#0066aa",
            wraplength=260,
            justify=tk.LEFT,
        )
        self.normalized_label.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(8, 4))

        buttons = ttk.Frame(panel)
        buttons.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        buttons.columnconfigure(0, weight=1)
        buttons.columnconfigure(1, weight=1)

        ttk.Button(buttons, text="恢复默认权重", command=self._reset_weights).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.analyze_btn = ttk.Button(buttons, text="开始分析", command=self._on_analyze)
        self.analyze_btn.grid(row=0, column=1, sticky="ew", padx=(4, 0))

        ttk.Label(
            panel,
            text="说明：结果为历史统计模型输出，不代表真实开奖概率，请理性参考。",
            foreground="#888888",
            wraplength=260,
            justify=tk.LEFT,
        ).grid(row=9, column=0, columnspan=2, sticky="ew", pady=(12, 0))

    def _build_results(self, parent: ttk.Frame) -> None:
        panel = ttk.LabelFrame(parent, text="分析结果", padding=8)
        panel.grid(row=0, column=1, sticky="nsew")
        panel.rowconfigure(0, weight=1)
        panel.columnconfigure(0, weight=1)

        self.result_text = scrolledtext.ScrolledText(
            panel,
            wrap=tk.WORD,
            font=self._mono_font,
            state=tk.DISABLED,
        )
        self.result_text.grid(row=0, column=0, sticky="nsew")

    def _build_status_bar(self, parent: ttk.Frame) -> None:
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(parent, textvariable=self.status_var, anchor="w").grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(8, 0),
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

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = tk.DISABLED if busy else tk.NORMAL
        self.analyze_btn.configure(state=state)

    def _set_result_text(self, text: str) -> None:
        self.result_text.configure(state=tk.NORMAL)
        self.result_text.delete("1.0", tk.END)
        self.result_text.insert(tk.END, text)
        self.result_text.configure(state=tk.DISABLED)

    def _on_analyze(self) -> None:
        if self._busy:
            return
        try:
            limit_raw = self.limit_var.get().strip()
            limit = None if limit_raw in ("", "0") else self._parse_positive_int(limit_raw, "分析期数")
            recent = self._parse_positive_int(self.recent_var.get(), "近期窗口")
            weights = self._collect_weights()
            lottery_type = self._selected_lottery_code()
        except ValueError as exc:
            messagebox.showerror("参数错误", str(exc))
            return

        self._set_busy(True)
        self.status_var.set("正在分析，请稍候...")
        self._set_result_text("正在拉取数据并计算，请稍候...\n")

        thread = threading.Thread(
            target=self._analyze_worker,
            args=(lottery_type, weights, limit, recent, self.refresh_var.get(), self.cache_var.get()),
            daemon=True,
        )
        thread.start()

    def _analyze_worker(
        self,
        lottery_type: str,
        weights: dict[str, float],
        limit: int | None,
        recent: int,
        refresh: bool,
        use_cache: bool,
    ) -> None:
        try:
            codes = resolve_lottery_code(lottery_type)
            if isinstance(codes, str):
                codes = [codes]

            chunks: list[str] = []
            if len(codes) > 1:
                summary = " | ".join(f"{WEIGHT_LABELS[k]} {weights[k]:.0%}" for k in DEFAULT_WEIGHTS)
                chunks.append("六合彩综合分析结果（香港 / 老澳门 / 新澳门）")
                chunks.append(f"策略权重: {summary}\n")

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
                    )
                    chunks.append(format_result_text(result))
                except Exception as exc:  # noqa: BLE001 - show any failure in UI
                    errors.append(f"[{name}] {exc}")

            if not chunks and errors:
                raise RuntimeError("\n".join(errors))

            text = "\n".join(chunks).strip()
            if errors:
                text += "\n\n部分彩种分析失败：\n" + "\n".join(errors)

            self.after(0, lambda: self._finish_success(text))
        except Exception as exc:  # noqa: BLE001
            self.after(0, lambda: self._finish_error(str(exc)))

    def _finish_success(self, text: str) -> None:
        self._set_result_text(text)
        self.status_var.set("分析完成")
        self._set_busy(False)

    def _finish_error(self, message: str) -> None:
        self._set_result_text(f"分析失败：\n{message}")
        self.status_var.set("分析失败")
        self._set_busy(False)
        messagebox.showerror("分析失败", message)


def main() -> None:
    app = LhcAnalyzerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
