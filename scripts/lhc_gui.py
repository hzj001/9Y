#!/usr/bin/env python3
"""六合彩分析工具 — 美化图形界面，正码/特码/生肖分标签展示。"""

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
    format_regular_report,
    format_result_text,
    format_special_report,
    format_summary_report,
    normalize_weights,
    resolve_lottery_code,
    result_to_json,
    run_analysis_for_code,
)
from lhc_zodiac import format_zodiac_report, zodiac_analysis_to_dict

IS_MACOS = sys.platform == "darwin"
IS_WINDOWS = sys.platform == "win32"

LOTTERY_OPTIONS = [
    ("xg6", "香港六合彩"),
    ("am6", "老澳门六合彩"),
    ("nam6", "新澳门六合彩"),
    ("all", "全部分析"),
]

THEME = {
    "header_bg": "#1e293b",
    "header_fg": "#f8fafc",
    "sidebar_bg": "#f1f5f9",
    "content_bg": "#ffffff",
    "accent": "#2563eb",
    "accent_hover": "#1d4ed8",
    "regular": "#3b82f6",
    "special": "#ec4899",
    "zodiac": "#10b981",
    "summary": "#6366f1",
    "muted": "#64748b",
    "border": "#cbd5e1",
    "card_regular_bg": "#eff6ff",
    "card_special_bg": "#fdf2f8",
    "card_zodiac_bg": "#ecfdf5",
    "card_summary_bg": "#eef2ff",
}


@dataclass
class TabContent:
    highlight: str = ""
    body: str = ""


@dataclass
class GuiAnalysisBundle:
    summary: TabContent = field(default_factory=TabContent)
    regular: TabContent = field(default_factory=TabContent)
    special: TabContent = field(default_factory=TabContent)
    zodiac: TabContent = field(default_factory=TabContent)
    full_report: str = ""
    json_payload: dict | list = field(default_factory=dict)


class ScrollableFrame(ttk.Frame):
    def __init__(self, parent: tk.Widget) -> None:
        super().__init__(parent)
        canvas = tk.Canvas(self, highlightthickness=0, bg=THEME["sidebar_bg"])
        scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=canvas.yview)
        self.inner = ttk.Frame(canvas)
        self.inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)


class ResultTab(ttk.Frame):
    """单个结果标签页：顶部高亮卡片 + 下方详情文本。"""

    def __init__(
        self,
        parent: tk.Widget,
        *,
        accent: str,
        card_bg: str,
        mono_font: tuple[str, int],
    ) -> None:
        super().__init__(parent, padding=0)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        self._card = tk.Frame(self, bg=card_bg, highlightbackground=accent, highlightthickness=2)
        self._card.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self._card.columnconfigure(0, weight=1)

        self.highlight_label = tk.Label(
            self._card,
            text="分析完成后在此显示推荐结果",
            bg=card_bg,
            fg=THEME["header_bg"],
            font=(mono_font[0], mono_font[1] + 1, "bold"),
            justify=tk.LEFT,
            anchor="w",
            padx=16,
            pady=14,
            wraplength=820,
        )
        self.highlight_label.pack(fill=tk.X)

        text_wrap = ttk.Frame(self)
        text_wrap.grid(row=1, column=0, sticky="nsew")
        text_wrap.rowconfigure(0, weight=1)
        text_wrap.columnconfigure(0, weight=1)

        self.body_text = scrolledtext.ScrolledText(
            text_wrap,
            wrap=tk.WORD,
            font=mono_font,
            state=tk.DISABLED,
            bg=THEME["content_bg"],
            fg="#0f172a",
            relief=tk.FLAT,
            padx=8,
            pady=8,
        )
        self.body_text.grid(row=0, column=0, sticky="nsew")

    def set_content(self, content: TabContent, *, placeholder: str = "") -> None:
        highlight = content.highlight or placeholder
        self.highlight_label.configure(text=highlight)
        self.body_text.configure(state=tk.NORMAL)
        self.body_text.delete("1.0", tk.END)
        self.body_text.insert(tk.END, content.body or placeholder)
        self.body_text.configure(state=tk.DISABLED)


class LhcAnalyzerApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("六合彩分析工具")
        self.geometry("1360x860")
        self.minsize(1120, 720)
        self.configure(bg=THEME["content_bg"])

        self._busy = False
        self._weight_vars: dict[str, tk.DoubleVar] = {}
        self._weight_value_labels: dict[str, ttk.Label] = {}
        self._last_bundle: GuiAnalysisBundle | None = None
        self._result_tabs: dict[str, ResultTab] = {}

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
        style.theme_use("clam")

        style.configure(".", background=THEME["content_bg"], foreground="#0f172a")
        style.configure("TFrame", background=THEME["content_bg"])
        style.configure("Sidebar.TFrame", background=THEME["sidebar_bg"])
        style.configure("TLabel", background=THEME["content_bg"], foreground="#0f172a")
        style.configure("Sidebar.TLabel", background=THEME["sidebar_bg"])
        style.configure("Muted.TLabel", foreground=THEME["muted"], background=THEME["sidebar_bg"])
        style.configure("TLabelframe", background=THEME["sidebar_bg"])
        style.configure("TLabelframe.Label", background=THEME["sidebar_bg"], foreground="#0f172a", font=(ui_font[0], ui_font[1], "bold"))
        style.configure("TNotebook", background=THEME["content_bg"], borderwidth=0)
        style.configure("TNotebook.Tab", padding=(16, 8), font=(ui_font[0], ui_font[1], "bold"))
        style.map(
            "TNotebook.Tab",
            background=[("selected", THEME["content_bg"]), ("!selected", "#e2e8f0")],
            foreground=[("selected", THEME["accent"]), ("!selected", THEME["muted"])],
        )
        style.configure("Accent.TButton", font=(ui_font[0], ui_font[1], "bold"))
        style.map("Accent.TButton", background=[("active", THEME["accent_hover"])])
        style.configure("Horizontal.TScale", background=THEME["sidebar_bg"])

        self.option_add("*Font", ui_font)

    @staticmethod
    def _pick_fonts() -> tuple[tuple[str, int], tuple[str, int]]:
        if IS_MACOS:
            return ("PingFang SC", 12), ("Menlo", 11)
        if IS_WINDOWS:
            return ("Microsoft YaHei UI", 10), ("Consolas", 10)
        return ("TkDefaultFont", 10), ("Monospace", 10)

    def _build_ui(self) -> None:
        header = tk.Frame(self, bg=THEME["header_bg"], height=56)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(
            header,
            text="六合彩分析工具",
            bg=THEME["header_bg"],
            fg=THEME["header_fg"],
            font=(self._ui_font[0], 16, "bold"),
        ).pack(side=tk.LEFT, padx=20, pady=12)
        tk.Label(
            header,
            text="正码 · 特码 · 生肖  独立分析  |  权重可调  |  统计模型仅供参考",
            bg=THEME["header_bg"],
            fg="#94a3b8",
            font=(self._ui_font[0], 10),
        ).pack(side=tk.LEFT, pady=16)

        body = ttk.Frame(self, padding=12)
        body.pack(fill=tk.BOTH, expand=True)
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)

        paned = ttk.Panedwindow(body, orient=tk.HORIZONTAL)
        paned.grid(row=0, column=0, sticky="nsew")

        left_wrap = ttk.Frame(paned, style="Sidebar.TFrame", width=360)
        right_wrap = ttk.Frame(paned)
        paned.add(left_wrap, weight=0)
        paned.add(right_wrap, weight=1)

        self._build_controls(left_wrap)
        self._build_results(right_wrap)
        self._build_status_bar(body)

    def _build_controls(self, parent: ttk.Frame) -> None:
        scroll = ScrollableFrame(parent)
        scroll.pack(fill=tk.BOTH, expand=True)
        panel = ttk.LabelFrame(scroll.inner, text="  分析设置  ", padding=14)
        panel.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        panel.columnconfigure(1, weight=1)

        row = 0
        ttk.Label(panel, text="彩种", style="Sidebar.TLabel").grid(row=row, column=0, sticky="w", pady=5)
        self.lottery_var = tk.StringVar(value="nam6")
        lottery_box = ttk.Combobox(
            panel,
            textvariable=self.lottery_var,
            state="readonly",
            values=[label for _, label in LOTTERY_OPTIONS],
            width=22,
        )
        lottery_box.grid(row=row, column=1, sticky="ew", pady=5)
        lottery_box.current(2)
        row += 1

        for label_text, var_name, default, hint in (
            ("分析期数", "limit_var", "200", "0 = 全部历史"),
            ("近期窗口", "recent_var", "30", None),
            ("推荐正码数", "top_regular_var", "6", None),
            ("特码 Top N", "top_special_var", "3", None),
        ):
            ttk.Label(panel, text=label_text, style="Sidebar.TLabel").grid(row=row, column=0, sticky="w", pady=5)
            setattr(self, var_name, tk.StringVar(value=default))
            if var_name in ("top_regular_var", "top_special_var"):
                ttk.Spinbox(panel, from_=1, to=12, textvariable=getattr(self, var_name), width=10).grid(
                    row=row, column=1, sticky="w", pady=5
                )
            else:
                ttk.Entry(panel, textvariable=getattr(self, var_name)).grid(row=row, column=1, sticky="ew", pady=5)
            row += 1
            if hint:
                ttk.Label(panel, text=hint, style="Muted.TLabel").grid(row=row, column=1, sticky="w")
                row += 1

        options = ttk.Frame(panel, style="Sidebar.TFrame")
        options.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(6, 2))
        self.cache_var = tk.BooleanVar(value=True)
        self.refresh_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(options, text="写入本地缓存", variable=self.cache_var).pack(anchor="w")
        ttk.Checkbutton(options, text="强制刷新数据", variable=self.refresh_var).pack(anchor="w")
        row += 1

        ttk.Separator(panel).grid(row=row, column=0, columnspan=2, sticky="ew", pady=12)
        row += 1

        weight_box = ttk.LabelFrame(panel, text="  策略权重  ", padding=10)
        weight_box.grid(row=row, column=0, columnspan=2, sticky="ew")
        weight_box.columnconfigure(1, weight=1)
        row += 1

        for wrow, (key, default) in enumerate(DEFAULT_WEIGHTS.items()):
            label = WEIGHT_LABELS.get(key, key)
            ttk.Label(weight_box, text=label, width=10, style="Sidebar.TLabel").grid(row=wrow, column=0, sticky="w", pady=3)
            var = tk.DoubleVar(value=default * 100)
            self._weight_vars[key] = var
            ttk.Scale(
                weight_box,
                from_=0,
                to=100,
                variable=var,
                orient=tk.HORIZONTAL,
                command=lambda _v, k=key: self._update_weight_label(k),
            ).grid(row=wrow, column=1, sticky="ew", padx=(8, 8), pady=3)
            value_label = ttk.Label(weight_box, text="0.00", width=6, style="Sidebar.TLabel")
            value_label.grid(row=wrow, column=2, sticky="e")
            self._weight_value_labels[key] = value_label

        self.normalized_label = ttk.Label(
            panel,
            text="",
            foreground=THEME["accent"],
            wraplength=310,
            justify=tk.LEFT,
            style="Sidebar.TLabel",
        )
        self.normalized_label.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(8, 4))
        row += 1

        self.analyze_btn = tk.Button(
            panel,
            text="▶  开始分析",
            command=self._on_analyze,
            bg=THEME["accent"],
            fg="white",
            activebackground=THEME["accent_hover"],
            activeforeground="white",
            relief=tk.FLAT,
            padx=12,
            pady=10,
            cursor="hand2",
            font=(self._ui_font[0], self._ui_font[1] + 1, "bold"),
        )
        self.analyze_btn.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(10, 6))
        row += 1

        btn_row = ttk.Frame(panel, style="Sidebar.TFrame")
        btn_row.grid(row=row, column=0, columnspan=2, sticky="ew")
        btn_row.columnconfigure(0, weight=1)
        btn_row.columnconfigure(1, weight=1)
        ttk.Button(btn_row, text="恢复默认权重", command=self._reset_weights).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(btn_row, text="导出 JSON", command=self._export_json).grid(row=0, column=1, sticky="ew", padx=(4, 0))
        row += 1

        ttk.Button(panel, text="复制完整报告", command=self._copy_full_report).grid(
            row=row, column=0, columnspan=2, sticky="ew", pady=(6, 0)
        )
        row += 1

        ttk.Label(
            panel,
            text="说明：历史统计不代表真实开奖概率，请理性参考。",
            style="Muted.TLabel",
            wraplength=310,
        ).grid(row=row, column=0, columnspan=2, sticky="ew", pady=(14, 0))

    def _build_results(self, parent: ttk.Frame) -> None:
        panel = ttk.Frame(parent)
        panel.pack(fill=tk.BOTH, expand=True)
        panel.rowconfigure(0, weight=1)
        panel.columnconfigure(0, weight=1)

        notebook = ttk.Notebook(panel)
        notebook.grid(row=0, column=0, sticky="nsew")

        tab_defs = [
            ("summary", "综合摘要", THEME["summary"], THEME["card_summary_bg"]),
            ("regular", "正码分析", THEME["regular"], THEME["card_regular_bg"]),
            ("special", "特码分析", THEME["special"], THEME["card_special_bg"]),
            ("zodiac", "生肖分析", THEME["zodiac"], THEME["card_zodiac_bg"]),
        ]
        for key, title, accent, card_bg in tab_defs:
            tab = ResultTab(notebook, accent=accent, card_bg=card_bg, mono_font=self._mono_font)
            notebook.add(tab, text=f"  {title}  ")
            self._result_tabs[key] = tab

        full_frame = ttk.Frame(notebook, padding=4)
        notebook.add(full_frame, text="  完整报告  ")
        full_frame.rowconfigure(0, weight=1)
        full_frame.columnconfigure(0, weight=1)
        self.full_text = scrolledtext.ScrolledText(
            full_frame,
            wrap=tk.WORD,
            font=self._mono_font,
            state=tk.DISABLED,
            bg="#fafafa",
        )
        self.full_text.grid(row=0, column=0, sticky="nsew")

    def _build_status_bar(self, parent: ttk.Frame) -> None:
        bar = tk.Frame(parent, bg="#e2e8f0", height=28)
        bar.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        self.status_var = tk.StringVar(value="就绪 — 请选择彩种并点击「开始分析」")
        tk.Label(
            bar,
            textvariable=self.status_var,
            bg="#e2e8f0",
            fg="#334155",
            anchor="w",
            padx=12,
        ).pack(fill=tk.X, ipady=4)

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
        summary = "  ·  ".join(f"{WEIGHT_LABELS[k]} {normalized[k]:.0%}" for k in DEFAULT_WEIGHTS)
        self.normalized_label.configure(text=f"归一化：{summary}")

    def _collect_weights(self) -> dict[str, float]:
        return normalize_weights({key: var.get() for key, var in self._weight_vars.items()})

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

    def _collect_params(self) -> tuple:
        limit_raw = self.limit_var.get().strip()
        limit = None if limit_raw in ("", "0") else self._parse_positive_int(limit_raw, "分析期数")
        return (
            self._selected_lottery_code(),
            self._collect_weights(),
            limit,
            self._parse_positive_int(self.recent_var.get(), "近期窗口"),
            self._parse_positive_int(self.top_regular_var.get(), "推荐正码数"),
            self._parse_positive_int(self.top_special_var.get(), "特码 Top N"),
            self.refresh_var.get(),
            self.cache_var.get(),
        )

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = tk.DISABLED if busy else tk.NORMAL
        self.analyze_btn.configure(state=state, bg=THEME["muted"] if busy else THEME["accent"])

    @staticmethod
    def _build_highlights(result, zodiac_data: dict) -> tuple[TabContent, TabContent, TabContent, TabContent]:
        from lhc_analyzer import format_number, rank_numbers

        stats = result.stats
        recommended_regular = rank_numbers(stats, "regular_strength", result.top_regular)
        recommended_special = rank_numbers(stats, "special_strength", 1)
        latest = result.draws[-1]

        regular_nums = ", ".join(format_number(s.number) for s in recommended_regular)
        special_num = format_number(recommended_special[0].number)
        zodiac_top = "、".join(zodiac_data["recommended_next"][:5])

        summary = TabContent(
            highlight=(
                f"【{result.lottery_name}】  "
                f"正码 → {regular_nums}  |  特码 → {special_num}  |  生肖 → {zodiac_top}"
            ),
            body=format_summary_report(result),
        )
        regular = TabContent(
            highlight=f"★ 推荐正码 Top {result.top_regular}：{regular_nums}",
            body=format_regular_report(result),
        )
        special = TabContent(
            highlight=f"★ 推荐特码 Top 1：{special_num}    （最新特码：{format_number(latest.special)}）",
            body=format_special_report(result),
        )
        zodiac = TabContent(
            highlight=(
                f"★ 下一期推荐生肖：{zodiac_top}    "
                f"（{zodiac_data['lunar_year_zodiac']}年 · 最新特码生肖：{zodiac_data['latest_zodiacs']['special']}）"
            ),
            body=format_zodiac_report(result.draws, result.recent_window, result.weights),
        )
        return summary, regular, special, zodiac

    def _show_bundle(self, bundle: GuiAnalysisBundle) -> None:
        mapping = {
            "summary": bundle.summary,
            "regular": bundle.regular,
            "special": bundle.special,
            "zodiac": bundle.zodiac,
        }
        for key, tab in self._result_tabs.items():
            tab.set_content(mapping[key], placeholder="暂无数据")

        self.full_text.configure(state=tk.NORMAL)
        self.full_text.delete("1.0", tk.END)
        self.full_text.insert(tk.END, bundle.full_report or "暂无数据")
        self.full_text.configure(state=tk.DISABLED)

    def _clear_results(self, message: str) -> None:
        empty = TabContent(highlight=message, body=message)
        self._show_bundle(
            GuiAnalysisBundle(
                summary=empty,
                regular=empty,
                special=empty,
                zodiac=empty,
                full_report=message,
            )
        )

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
        self._clear_results("正在拉取数据并计算，请稍候...")

        threading.Thread(target=self._analyze_worker, args=(params,), daemon=True).start()

    def _analyze_worker(self, params: tuple) -> None:
        lottery_type, weights, limit, recent, top_regular, top_special, refresh, use_cache = params
        try:
            codes = resolve_lottery_code(lottery_type)
            if isinstance(codes, str):
                codes = [codes]

            summaries: list[TabContent] = []
            regulars: list[TabContent] = []
            specials: list[TabContent] = []
            zodiacs: list[TabContent] = []
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
                    zodiac_data = zodiac_analysis_to_dict(result.draws, recent, weights)
                    s, r, sp, z = self._build_highlights(result, zodiac_data)
                    summaries.append(s)
                    regulars.append(r)
                    specials.append(sp)
                    zodiacs.append(z)
                    fulls.append(format_result_text(result))
                    json_items.append(result_to_json(result))
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"[{name}] {exc}")

            if not summaries and errors:
                raise RuntimeError("\n".join(errors))

            def join_tabs(items: list[TabContent]) -> TabContent:
                if len(items) == 1:
                    return items[0]
                divider = "\n\n" + ("═" * 72) + "\n\n"
                return TabContent(
                    highlight=divider.join(i.highlight for i in items),
                    body=divider.join(i.body for i in items),
                )

            bundle = GuiAnalysisBundle(
                summary=join_tabs(summaries),
                regular=join_tabs(regulars),
                special=join_tabs(specials),
                zodiac=join_tabs(zodiacs),
                full_report=("\n\n" + ("=" * 72) + "\n\n").join(fulls),
                json_payload=json_items[0] if len(json_items) == 1 else {i["lottery_code"]: i for i in json_items},
            )
            if errors:
                err = "\n部分彩种失败：\n" + "\n".join(errors)
                bundle.full_report += err
                bundle.summary.body += err

            self.after(0, lambda b=bundle: self._finish_success(b))
        except Exception as exc:  # noqa: BLE001
            self.after(0, lambda: self._finish_error(str(exc)))

    def _finish_success(self, bundle: GuiAnalysisBundle) -> None:
        self._last_bundle = bundle
        self._show_bundle(bundle)
        self.status_var.set("分析完成 — 请切换「正码 / 特码 / 生肖」标签页查看")
        self._set_busy(False)

    def _finish_error(self, message: str) -> None:
        self._last_bundle = None
        self._clear_results(f"分析失败：\n{message}")
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
