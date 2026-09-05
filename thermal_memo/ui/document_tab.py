"""ファイル取り込みタブ（PDF / Word / テキスト）。

サムネイル印刷とテキスト抽出印刷を切り替えられる。
"""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image

from .. import documents, render
from .common import LabeledScale, debounce, section


class DocumentTab(ttk.Frame):
    title = "ファイル"

    def __init__(self, master, app):
        super().__init__(master, padding=10)
        self.app = app
        self.info: documents.DocumentInfo | None = None
        self.rendered: list[Image.Image] = []
        self.extracted = ""

        self.output = tk.StringVar(value="text")     # text / thumbnail
        self.pages = tk.StringVar(value="all")
        self.ocr = tk.BooleanVar(value=False)
        self.font_size = tk.IntVar(value=max(18, app.cfg["text"]["font_size"] - 4))
        self.thumb_threshold = tk.IntVar(value=140)
        self.thumb_mode = tk.StringVar(value="threshold")
        self.show_filename = tk.BooleanVar(value=True)

        refresh = debounce(self, 200)(self.app.refresh_preview)
        self.refresh = refresh

        # --- ファイル選択
        pick = section(self, "ファイル")
        row = ttk.Frame(pick)
        row.pack(fill="x")
        ttk.Button(row, text="ファイルを選ぶ…", command=self.choose).pack(side="left")
        ttk.Button(row, text="クリア", command=self.clear).pack(side="left", padx=6)
        self.drop_hint = ttk.Label(row, text="", foreground="#777")
        self.drop_hint.pack(side="left", padx=10)
        self.file_label = ttk.Label(pick, text="未選択", foreground="#777", wraplength=520,
                                    justify="left")
        self.file_label.pack(anchor="w", pady=(6, 0))

        # --- 出力方法
        out = section(self, "出力方法")
        mode_row = ttk.Frame(out)
        mode_row.pack(fill="x")
        self.radio_text = ttk.Radiobutton(mode_row, text="テキスト抽出して印刷", value="text",
                                          variable=self.output, command=self._on_mode)
        self.radio_text.pack(side="left")
        self.radio_thumb = ttk.Radiobutton(mode_row, text="サムネイル（見た目のまま）", value="thumbnail",
                                           variable=self.output, command=self._on_mode)
        self.radio_thumb.pack(side="left", padx=12)

        page_row = ttk.Frame(out)
        page_row.pack(fill="x", pady=(6, 0))
        ttk.Label(page_row, text="ページ").pack(side="left")
        entry = ttk.Entry(page_row, textvariable=self.pages, width=14)
        entry.pack(side="left", padx=(4, 8))
        entry.bind("<KeyRelease>", lambda _e: self._reload())
        ttk.Label(page_row, text="例: all / 1 / 1,3-5", foreground="#999").pack(side="left")
        ttk.Checkbutton(page_row, text="OCR（文字が取れない PDF 用）", variable=self.ocr,
                        command=self._reload).pack(side="right")

        # --- 体裁
        self.style_frame = section(self, "体裁")
        LabeledScale(self.style_frame, "文字サイズ", 14, 48, self.font_size,
                     command=refresh).pack(fill="x")
        LabeledScale(self.style_frame, "しきい値", 0, 255, self.thumb_threshold,
                     command=refresh).pack(fill="x")
        thumb_row = ttk.Frame(self.style_frame)
        thumb_row.pack(fill="x", pady=(6, 0))
        ttk.Label(thumb_row, text="サムネ二値化").pack(side="left")
        for value, label in (("threshold", "しきい値"), ("dither", "ディザ"), ("adaptive", "適応的")):
            ttk.Radiobutton(thumb_row, text=label, value=value, variable=self.thumb_mode,
                            command=refresh).pack(side="left", padx=3)
        ttk.Checkbutton(thumb_row, text="ファイル名を印字", variable=self.show_filename,
                        command=refresh).pack(side="right")

        # --- 抽出テキストの編集
        edit = section(self, "抽出テキスト（印刷前に編集できます）")
        wrapper = ttk.Frame(edit, relief="sunken", borderwidth=1)
        wrapper.pack(fill="both", expand=True)
        self.text = tk.Text(wrapper, wrap="word", height=8, undo=True, font=("", 11),
                            borderwidth=0, highlightthickness=0)
        scroll = ttk.Scrollbar(wrapper, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)
        self.text.bind("<KeyRelease>", lambda _e: refresh())

    # ------------------------------------------------------------------ 読み込み
    def enable_dnd(self, widget) -> None:
        """tkinterdnd2 が使える場合にファイル D&D を有効化。"""
        try:
            from tkinterdnd2 import DND_FILES
        except ImportError:
            self.drop_hint.configure(text="（D&D は tkinterdnd2 導入で有効）")
            return
        widget.drop_target_register(DND_FILES)
        widget.dnd_bind("<<Drop>>", self._on_drop)
        self.drop_hint.configure(text="ウィンドウにファイルをドロップできます")

    def _on_drop(self, event) -> None:
        raw = event.data
        paths = self.tk.splitlist(raw) if hasattr(self, "tk") else [raw]
        if not paths:
            return
        path = Path(str(paths[0]).strip("{}"))
        if path.suffix.lower() in documents.IMAGE_SUFFIXES:
            self.app.open_in_image_tab(str(path))
            return
        self.app.select_tab(self)
        self.load(str(path))

    def choose(self) -> None:
        path = filedialog.askopenfilename(
            title="ファイルを選択",
            filetypes=[
                ("対応ファイル", "*.pdf *.docx *.txt *.md *.csv *.png *.jpg *.jpeg"),
                ("PDF", "*.pdf"), ("Word", "*.docx"), ("テキスト", "*.txt *.md *.csv"),
                ("すべて", "*.*"),
            ],
        )
        if path:
            self.load(path)

    def load(self, path: str) -> None:
        try:
            info = documents.inspect(path)
        except documents.DocumentError as exc:
            messagebox.showerror("読み込み失敗", str(exc))
            return
        self.info = info
        note = f"  ※{info.note}" if info.note else ""
        self.file_label.configure(
            text=f"{info.path.name}   [{info.kind}] {info.pages} ページ{note}", foreground="#333"
        )
        self.radio_thumb.configure(state="normal" if info.can_thumbnail else "disabled")
        self.radio_text.configure(state="normal" if info.can_text else "disabled")
        if not info.can_thumbnail and self.output.get() == "thumbnail":
            self.output.set("text")
        if not info.can_text and self.output.get() == "text":
            self.output.set("thumbnail")
        self._reload()

    def clear(self) -> None:
        self.info = None
        self.rendered = []
        self.extracted = ""
        self.text.delete("1.0", "end")
        self.file_label.configure(text="未選択", foreground="#777")
        self.app.refresh_preview()

    def _on_mode(self) -> None:
        self._reload()

    def _reload(self) -> None:
        if not self.info:
            return
        self.app.status("読み込み中…", "busy")
        info = self.info
        mode = self.output.get()
        pages = self.pages.get()
        use_ocr = self.ocr.get()

        def worker() -> None:
            try:
                if mode == "thumbnail":
                    images = documents.render_pages(
                        info.path, pages=pages, width_dots=self.app.width_dots
                    )
                    self.app.post(lambda: self._apply_thumbnails(images))
                else:
                    text = documents.extract_text(info.path, pages=pages, ocr=use_ocr)
                    self.app.post(lambda: self._apply_text(text))
            except Exception as exc:  # noqa: BLE001
                self.app.post(lambda e=exc: self._fail(e))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_thumbnails(self, images: list[Image.Image]) -> None:
        self.rendered = images
        self.app.status(f"{len(images)} ページを描画しました", "ok")
        self.app.refresh_preview()

    def _apply_text(self, text: str) -> None:
        self.extracted = text
        self.text.delete("1.0", "end")
        self.text.insert("1.0", text or "（テキストを抽出できませんでした。OCR かサムネイルをお試しください）")
        self.app.status(f"{len(text)} 文字を抽出しました", "ok")
        self.app.refresh_preview()

    def _fail(self, exc: Exception) -> None:
        self.app.status(f"読み込み失敗: {exc}", "error")
        messagebox.showerror("読み込み失敗", str(exc))

    # ------------------------------------------------------------------ 公開 API
    def build_image(self) -> Image.Image | None:
        if not self.info:
            return None
        cfg = self.app.cfg["text"]
        header = self.info.path.name if self.show_filename.get() else ""

        if self.output.get() == "thumbnail":
            if not self.rendered:
                return None
            processed = [
                render.process_image(
                    page, width_dots=self.app.width_dots, mode=self.thumb_mode.get(),
                    threshold=self.thumb_threshold.get(), autocrop=False,
                )
                for page in self.rendered
            ]
            if header:
                head = render.text_to_image(
                    header, width_dots=self.app.width_dots, font_path=cfg["font_path"],
                    font_size=max(18, int(cfg["font_size"] * 0.7)), line_spacing=2,
                    margin=cfg["margin"], timestamp=cfg["timestamp"],
                    timestamp_format=cfg["timestamp_format"], rule_line=True,
                )
                processed.insert(0, head)
            return render.stack(processed, gap=10, width_dots=self.app.width_dots)

        body = self.text.get("1.0", "end").rstrip()
        if not body.strip():
            return None
        return render.text_to_image(
            body,
            width_dots=self.app.width_dots,
            font_path=cfg["font_path"],
            font_size=self.font_size.get(),
            line_spacing=max(2, cfg["line_spacing"] - 2),
            margin=cfg["margin"],
            align="left",
            header=header,
            timestamp=cfg["timestamp"],
            timestamp_format=cfg["timestamp_format"],
            rule_line=True,
        )

    def describe(self) -> dict:
        body = (self.text.get("1.0", "end").rstrip()
                if self.output.get() == "text" else f"[サムネイル] {self.pages.get()} ページ")
        return {
            "kind": "document",
            "title": self.info.path.name if self.info else "",
            "body": body,
            "source": str(self.info.path) if self.info else "",
            "params": {"output": self.output.get(), "pages": self.pages.get()},
        }

    def empty_message(self) -> str:
        return "ファイルを読み込んでください"

    def persist(self) -> None:
        pass
