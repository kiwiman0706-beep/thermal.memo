"""テキスト入力タブ。"""

from __future__ import annotations

import datetime as _dt
import tkinter as tk
from tkinter import ttk

from PIL import Image

from .. import fonts, render
from .common import LabeledScale, debounce, section

SNIPPETS = [
    ("受付メモ", "受付：\n患者ID：\n用件：\n対応："),
    ("TODO", "□ \n□ \n□ "),
    ("電話メモ", "☎ 着信 \n相手：\n用件：\n折返し： 要 / 不要"),
    ("申し送り", "【申し送り】\n\n担当："),
]


class TextTab(ttk.Frame):
    title = "テキスト"

    def __init__(self, master, app):
        super().__init__(master, padding=10)
        self.app = app
        cfg = app.cfg["text"]

        self.font_size = tk.IntVar(value=cfg["font_size"])
        self.line_spacing = tk.IntVar(value=cfg["line_spacing"])
        self.margin = tk.IntVar(value=cfg["margin"])
        self.align = tk.StringVar(value=cfg["align"])
        self.bold = tk.BooleanVar(value=cfg["bold"])
        self.timestamp = tk.BooleanVar(value=cfg["timestamp"])
        self.rule_line = tk.BooleanVar(value=cfg["rule_line"])
        self.header = tk.StringVar(value=cfg["header"])
        self.footer = tk.StringVar(value=cfg["footer"])

        refresh = debounce(self, 200)(self.app.refresh_preview)

        # --- 入力欄
        editor = ttk.Frame(self)
        editor.pack(fill="both", expand=True)
        ttk.Label(editor, text="メモ本文（Ctrl+Enter で印刷）").pack(anchor="w")
        wrapper = ttk.Frame(editor, relief="sunken", borderwidth=1)
        wrapper.pack(fill="both", expand=True, pady=(4, 8))
        self.text = tk.Text(wrapper, wrap="word", height=12, undo=True,
                            font=("", 12), borderwidth=0, highlightthickness=0)
        scroll = ttk.Scrollbar(wrapper, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)
        self.text.bind("<KeyRelease>", lambda _e: refresh())
        self.text.bind("<Control-Return>", self._print_now)
        self.text.bind("<Control-a>", self._select_all)

        # --- 定型文
        snippet_bar = ttk.Frame(self)
        snippet_bar.pack(fill="x", pady=(0, 8))
        ttk.Label(snippet_bar, text="定型：").pack(side="left")
        for label, body in SNIPPETS:
            ttk.Button(snippet_bar, text=label, width=8,
                       command=lambda b=body: self._insert(b)).pack(side="left", padx=2)
        ttk.Button(snippet_bar, text="日付", width=6,
                   command=lambda: self._insert(_dt.date.today().strftime("%Y/%m/%d "))
                   ).pack(side="left", padx=2)
        ttk.Button(snippet_bar, text="消去", width=6, command=self.clear).pack(side="right")

        # --- 書式
        form = section(self, "書式")
        LabeledScale(form, "文字サイズ", 16, 72, self.font_size, command=refresh).pack(fill="x")
        LabeledScale(form, "行間", 0, 30, self.line_spacing, command=refresh).pack(fill="x")
        LabeledScale(form, "余白", 0, 48, self.margin, command=refresh).pack(fill="x")

        row = ttk.Frame(form)
        row.pack(fill="x", pady=(6, 0))
        ttk.Label(row, text="揃え").pack(side="left")
        for value, label in (("left", "左"), ("center", "中央"), ("right", "右")):
            ttk.Radiobutton(row, text=label, value=value, variable=self.align,
                            command=refresh).pack(side="left", padx=2)
        ttk.Checkbutton(row, text="太字", variable=self.bold, command=refresh).pack(side="left", padx=(12, 2))
        ttk.Checkbutton(row, text="日時を印字", variable=self.timestamp,
                        command=refresh).pack(side="left", padx=2)
        ttk.Checkbutton(row, text="罫線", variable=self.rule_line,
                        command=refresh).pack(side="left", padx=2)

        row2 = ttk.Frame(form)
        row2.pack(fill="x", pady=(6, 0))
        ttk.Label(row2, text="見出し").pack(side="left")
        entry = ttk.Entry(row2, textvariable=self.header)
        entry.pack(side="left", fill="x", expand=True, padx=(4, 10))
        entry.bind("<KeyRelease>", lambda _e: refresh())
        ttk.Label(row2, text="フッタ").pack(side="left")
        entry2 = ttk.Entry(row2, textvariable=self.footer, width=18)
        entry2.pack(side="left", padx=(4, 0))
        entry2.bind("<KeyRelease>", lambda _e: refresh())

        ttk.Label(self, text=f"フォント: {fonts.display_name(fonts.detect(app.cfg['text']['font_path']))}",
                  foreground="#777").pack(anchor="w")

    # ------------------------------------------------------------------ 公開 API
    def build_image(self) -> Image.Image | None:
        body = self.text.get("1.0", "end").rstrip()
        if not body.strip():
            return None
        cfg = self.app.cfg["text"]
        return render.text_to_image(
            body,
            width_dots=self.app.width_dots,
            font_path=cfg["font_path"],
            font_size=self.font_size.get(),
            line_spacing=self.line_spacing.get(),
            margin=self.margin.get(),
            align=self.align.get(),
            bold=self.bold.get(),
            header=self.header.get(),
            footer=self.footer.get(),
            timestamp=self.timestamp.get(),
            timestamp_format=cfg["timestamp_format"],
            rule_line=self.rule_line.get(),
        )

    def describe(self) -> dict:
        body = self.text.get("1.0", "end").rstrip()
        first = next((line for line in body.splitlines() if line.strip()), "")
        return {
            "kind": "text",
            "title": first[:80],
            "body": body,
            "source": "",
            "params": {
                "font_size": self.font_size.get(),
                "align": self.align.get(),
                "bold": self.bold.get(),
                "header": self.header.get(),
            },
        }

    def empty_message(self) -> str:
        return "本文を入力してください"

    def persist(self) -> None:
        cfg = self.app.cfg["text"]
        cfg.update({
            "font_size": self.font_size.get(),
            "line_spacing": self.line_spacing.get(),
            "margin": self.margin.get(),
            "align": self.align.get(),
            "bold": self.bold.get(),
            "timestamp": self.timestamp.get(),
            "rule_line": self.rule_line.get(),
            "header": self.header.get(),
            "footer": self.footer.get(),
        })

    # ------------------------------------------------------------------ 内部
    def clear(self) -> None:
        self.text.delete("1.0", "end")
        self.app.refresh_preview()

    def load(self, body: str) -> None:
        self.text.delete("1.0", "end")
        self.text.insert("1.0", body)
        self.app.refresh_preview()

    def _insert(self, snippet: str) -> None:
        if self.text.get("1.0", "end").strip():
            self.text.insert("end", "\n")
        self.text.insert("end", snippet)
        self.text.focus_set()
        self.app.refresh_preview()

    def _print_now(self, _event=None) -> str:
        self.app.print_current()
        return "break"

    def _select_all(self, _event=None) -> str:
        self.text.tag_add("sel", "1.0", "end")
        return "break"
