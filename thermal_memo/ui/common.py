"""UI 共通パーツ。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from PIL import Image, ImageTk

PAPER_BG = "#f4f4f2"


class PreviewPane(ttk.Frame):
    """印刷される 1bit 画像をそのまま表示するプレビュー。"""

    def __init__(self, master, width: int = 300, **kwargs):
        super().__init__(master, **kwargs)
        self.preview_width = width
        self._photo: ImageTk.PhotoImage | None = None
        self._image: Image.Image | None = None

        header = ttk.Frame(self)
        header.pack(fill="x")
        ttk.Label(header, text="プレビュー").pack(side="left")
        self.info = ttk.Label(header, text="-", foreground="#666", anchor="e")
        self.info.pack(side="right", fill="x", expand=True, padx=(8, 0))

        body = ttk.Frame(self, relief="sunken", borderwidth=1)
        body.pack(fill="both", expand=True, pady=(4, 0))
        self.canvas = tk.Canvas(body, background=PAPER_BG, highlightthickness=0, width=width)
        scroll = ttk.Scrollbar(body, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _e: self._redraw())
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Button-4>", lambda _e: self.canvas.yview_scroll(-3, "units"))
        self.canvas.bind("<Button-5>", lambda _e: self.canvas.yview_scroll(3, "units"))

    def _on_wheel(self, event) -> None:
        self.canvas.yview_scroll(int(-event.delta / 40) or (-1 if event.delta > 0 else 1), "units")

    def show(self, image: Image.Image | None) -> None:
        self._image = image
        if image is None:
            self.info.configure(text="-")
        else:
            mm = image.height / 8  # 203dpi ≒ 8 dot/mm
            self.info.configure(text=f"{image.width} × {image.height} dot  /  約 {mm:.0f} mm")
        self._redraw()

    def _redraw(self) -> None:
        self.canvas.delete("all")
        if self._image is None:
            self.canvas.create_text(
                self.canvas.winfo_width() // 2 or 150, 60,
                text="ここにプレビューが出ます", fill="#999",
            )
            self.canvas.configure(scrollregion=(0, 0, 0, 0))
            return
        avail = max(80, self.canvas.winfo_width() - 16)
        scale = min(1.0, avail / self._image.width)
        size = (max(1, int(self._image.width * scale)), max(1, int(self._image.height * scale)))
        shown = self._image.convert("L").resize(size, Image.LANCZOS)
        self._photo = ImageTk.PhotoImage(shown)
        x = (self.canvas.winfo_width() - size[0]) // 2
        self.canvas.create_rectangle(x - 2, 6, x + size[0] + 2, size[1] + 10,
                                     fill="white", outline="#ccc")
        self.canvas.create_image(x, 8, image=self._photo, anchor="nw")
        self.canvas.configure(scrollregion=(0, 0, self.canvas.winfo_width(), size[1] + 20))


class LabeledScale(ttk.Frame):
    """ラベル＋スライダ＋数値表示。"""

    def __init__(
        self,
        master,
        text: str,
        from_: float,
        to: float,
        variable,
        *,
        resolution: float = 1.0,
        fmt: str = "{:.0f}",
        command: Callable[[], None] | None = None,
        width: int = 90,
    ):
        super().__init__(master)
        self.variable = variable
        self.fmt = fmt
        self.resolution = resolution
        self._command = command

        ttk.Label(self, text=text, width=int(width / 8)).pack(side="left")
        self.value_label = ttk.Label(self, width=6, anchor="e", foreground="#555")
        self.value_label.pack(side="right")
        self.scale = ttk.Scale(self, from_=from_, to=to, orient="horizontal",
                               command=self._on_change)
        self.scale.pack(side="left", fill="x", expand=True, padx=6)
        self._syncing = False
        self.scale.set(variable.get())
        self._update_label(variable.get())
        # 外部から variable を書き換えたときもスライダと数値表示を追従させる
        variable.trace_add("write", self._on_variable)

    def _on_variable(self, *_args) -> None:
        if self._syncing:
            return
        try:
            value = self.variable.get()
        except tk.TclError:
            return
        self._syncing = True
        try:
            self.scale.set(value)
            self._update_label(value)
        finally:
            self._syncing = False

    def _on_change(self, raw) -> None:
        if self._syncing:
            return
        value = float(raw)
        if self.resolution >= 1:
            value = round(value / self.resolution) * self.resolution
        self._syncing = True
        try:
            if isinstance(self.variable, tk.IntVar):
                self.variable.set(int(round(value)))
            else:
                self.variable.set(round(value, 3))
        finally:
            self._syncing = False
        self._update_label(self.variable.get())
        if self._command:
            self._command()

    def _update_label(self, value) -> None:
        self.value_label.configure(text=self.fmt.format(value))

    def set(self, value) -> None:
        self.scale.set(value)
        self._update_label(value)


def section(master, title: str) -> ttk.LabelFrame:
    frame = ttk.LabelFrame(master, text=title, padding=8)
    frame.pack(fill="x", pady=(0, 8))
    return frame


def debounce(widget, delay_ms: int = 250):
    """連続イベントをまとめるデコレータ生成器。"""
    state: dict[str, str | None] = {"job": None}

    def wrap(func: Callable[[], None]) -> Callable[..., None]:
        def call(*_args) -> None:
            if state["job"]:
                widget.after_cancel(state["job"])
            state["job"] = widget.after(delay_ms, func)
        return call

    return wrap
