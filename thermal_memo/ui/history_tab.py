"""履歴タブ（検索・再印刷・同期）。"""

from __future__ import annotations

import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image

from ..history import KIND_LABEL, Entry

KIND_CHOICES = {"すべて": "", "テキスト": "text", "スクショ": "screenshot",
                "ファイル": "document", "QR": "qr"}
from .common import section


class HistoryTab(ttk.Frame):
    title = "履歴"

    def __init__(self, master, app):
        super().__init__(master, padding=10)
        self.app = app
        self.entries: list[Entry] = []
        self.selected: Entry | None = None

        self.query = tk.StringVar()
        self.kind_filter = tk.StringVar(value="")

        bar = ttk.Frame(self)
        bar.pack(fill="x")
        ttk.Label(bar, text="検索").pack(side="left")
        entry = ttk.Entry(bar, textvariable=self.query)
        entry.pack(side="left", fill="x", expand=True, padx=(4, 8))
        entry.bind("<KeyRelease>", lambda _e: self.reload())
        self.kind_choice = tk.StringVar(value="すべて")
        combo = ttk.Combobox(bar, textvariable=self.kind_choice, width=10, state="readonly",
                             values=list(KIND_CHOICES))
        combo.pack(side="left")
        combo.bind("<<ComboboxSelected>>", lambda _e: self._on_kind())
        ttk.Button(bar, text="更新", width=6, command=self.reload).pack(side="left", padx=4)

        table = ttk.Frame(self)
        table.pack(fill="both", expand=True, pady=(8, 0))
        columns = ("when", "kind", "summary")
        self.tree = ttk.Treeview(table, columns=columns, show="headings", height=14)
        self.tree.heading("when", text="日時")
        self.tree.heading("kind", text="種別")
        self.tree.heading("summary", text="内容")
        self.tree.column("when", width=140, stretch=False)
        self.tree.column("kind", width=80, stretch=False)
        self.tree.column("summary", width=380)
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", lambda _e: self.reprint())

        actions = ttk.Frame(self)
        actions.pack(fill="x", pady=8)
        ttk.Button(actions, text="もう一度印刷", command=self.reprint).pack(side="left")
        ttk.Button(actions, text="テキストとして編集", command=self.edit_as_text).pack(side="left", padx=6)
        ttk.Button(actions, text="PNG 書き出し", command=self.export_png).pack(side="left", padx=6)
        ttk.Button(actions, text="削除", command=self.delete).pack(side="left", padx=6)

        sync = section(self, "クラウド同期（同期フォルダ方式）")
        self.sync_label = ttk.Label(sync, text="", wraplength=520, justify="left", foreground="#555")
        self.sync_label.pack(anchor="w")
        sync_row = ttk.Frame(sync)
        sync_row.pack(fill="x", pady=(6, 0))
        ttk.Button(sync_row, text="同期フォルダを選ぶ…", command=self.choose_sync_dir).pack(side="left")
        ttk.Button(sync_row, text="全件を書き出し", command=self.export_all).pack(side="left", padx=6)
        ttk.Button(sync_row, text="フォルダを開く", command=self.open_sync_dir).pack(side="left")
        ttk.Button(sync_row, text="データ保存先を開く", command=self.open_data_dir).pack(side="right")

        self.reload()
        self.update_sync_label()

    # ------------------------------------------------------------------ 一覧
    def _on_kind(self) -> None:
        self.kind_filter.set(KIND_CHOICES.get(self.kind_choice.get(), ""))
        self.reload()

    def reload(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self.entries = self.app.history.list(self.query.get().strip(), self.kind_filter.get())
        for entry in self.entries:
            mark = "" if entry.status == "ok" else "⚠ "
            self.tree.insert(
                "", "end", iid=str(entry.id),
                values=(f"{entry.when:%m/%d %H:%M}", KIND_LABEL.get(entry.kind, entry.kind),
                        mark + entry.summary(70)),
            )

    def _on_select(self, _event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            self.selected = None
            return
        entry_id = int(selection[0])
        self.selected = next((e for e in self.entries if e.id == entry_id), None)
        if self.selected:
            image = self.app.history.image_of(self.selected)
            self.app.preview.show(image)

    def _require(self) -> Entry | None:
        if not self.selected:
            self.app.status("履歴を選択してください", "warn")
        return self.selected

    # ------------------------------------------------------------------ 操作
    def reprint(self) -> None:
        entry = self._require()
        if not entry:
            return
        image = self.app.history.image_of(entry)
        if image is None:
            messagebox.showinfo("再印刷", "この履歴には画像が保存されていません")
            return
        self.app.send_image(
            image,
            kind=entry.kind, title=entry.title, body=entry.body,
            source=entry.source or "（履歴からの再印刷）", params=entry.params,
        )

    def edit_as_text(self) -> None:
        entry = self._require()
        if not entry:
            return
        if not entry.body.strip():
            messagebox.showinfo("編集", "テキストが保存されていない履歴です")
            return
        self.app.load_text(entry.body)

    def export_png(self) -> None:
        entry = self._require()
        if not entry:
            return
        image: Image.Image | None = self.app.history.image_of(entry)
        if image is None:
            messagebox.showinfo("書き出し", "画像がありません")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".png", filetypes=[("PNG", "*.png")],
            initialfile=f"{entry.when:%Y%m%d-%H%M%S}.png",
        )
        if path:
            image.save(path)
            self.app.status(f"保存しました: {path}", "ok")

    def delete(self) -> None:
        entry = self._require()
        if not entry:
            return
        if not messagebox.askyesno("削除", "この履歴を削除しますか？"):
            return
        self.app.history.delete(entry.id)
        self.selected = None
        self.reload()
        self.app.status("削除しました", "ok")

    # ------------------------------------------------------------------ 同期
    def update_sync_label(self) -> None:
        cfg = self.app.cfg["history"]
        target = cfg.get("sync_dir")
        if target and cfg.get("sync_enabled"):
            text = (f"同期先: {target}\n"
                    "印刷のたびに Markdown + PNG が書き出されます。"
                    "Google ドライブ／iCloud／Dropbox の同期フォルダを指定すればスマホからも読めます。")
        else:
            text = ("未設定。Google Keep には個人アカウント向けの公開 API が無いため、"
                    "「クラウドの同期フォルダへ書き出す」方式にしています。"
                    "Google ドライブ等のローカル同期フォルダを指定してください。")
        self.sync_label.configure(text=text)

    def choose_sync_dir(self) -> None:
        path = filedialog.askdirectory(title="同期フォルダを選択")
        if not path:
            return
        self.app.cfg["history"]["sync_dir"] = path
        self.app.cfg["history"]["sync_enabled"] = True
        self.app.save_config()
        self.update_sync_label()
        self.app.status("同期フォルダを設定しました", "ok")

    def export_all(self) -> None:
        cfg = self.app.cfg["history"]
        if not cfg.get("sync_dir"):
            self.choose_sync_dir()
            if not cfg.get("sync_dir"):
                return
        count = self.app.history.export_all(cfg["sync_dir"])
        self.app.status(f"{count} 件を書き出しました", "ok")

    def open_sync_dir(self) -> None:
        target = self.app.cfg["history"].get("sync_dir")
        if not target:
            self.app.status("同期フォルダが未設定です", "warn")
            return
        _open_path(Path(target))

    def open_data_dir(self) -> None:
        _open_path(self.app.history.base)


def _open_path(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        subprocess.Popen(["explorer", str(path)])
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])
