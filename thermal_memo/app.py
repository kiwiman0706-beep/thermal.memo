"""thermal.memo メインウィンドウ。"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from PIL import Image

from . import APP_NAME, __version__, config, printer
from .history import History
from .ui.common import PreviewPane
from .ui.document_tab import DocumentTab
from .ui.history_tab import HistoryTab
from .ui.image_tab import ImageTab
from .ui.settings_tab import SettingsTab
from .ui.text_tab import TextTab

STATUS_COLORS = {
    "info": "#333333",
    "ok": "#12703a",
    "warn": "#8a6d00",
    "error": "#b3261e",
    "busy": "#1c5fa8",
}


def make_root() -> tk.Tk:
    """tkinterdnd2 があれば D&D 対応の Tk を返す。"""
    try:
        from tkinterdnd2 import TkinterDnD

        return TkinterDnD.Tk()
    except ImportError:
        return tk.Tk()


class App(ttk.Frame):
    def __init__(self, root: tk.Tk):
        super().__init__(root, padding=8)
        self.root = root
        self.cfg = config.load()
        self.history = History()
        self._results: queue.Queue = queue.Queue()
        self._callbacks: queue.Queue = queue.Queue()
        self._printing = False

        root.title(f"{APP_NAME} {__version__}")
        root.geometry(self.cfg["ui"].get("window", "980x720"))
        root.minsize(860, 600)
        self.pack(fill="both", expand=True)
        self._setup_style()

        # 左: タブ / 右: プレビューと印刷操作
        panes = ttk.PanedWindow(self, orient="horizontal")
        panes.pack(fill="both", expand=True)

        left = ttk.Frame(panes)
        right = ttk.Frame(panes, padding=(8, 0, 0, 0))
        panes.add(left, weight=3)
        panes.add(right, weight=2)

        self.notebook = ttk.Notebook(left)
        self.notebook.pack(fill="both", expand=True)
        self.text_tab = TextTab(self.notebook, self)
        self.image_tab = ImageTab(self.notebook, self)
        self.document_tab = DocumentTab(self.notebook, self)
        self.history_tab = HistoryTab(self.notebook, self)
        self.settings_tab = SettingsTab(self.notebook, self)
        self.tabs = [self.text_tab, self.image_tab, self.document_tab,
                     self.history_tab, self.settings_tab]
        for tab in self.tabs:
            self.notebook.add(tab, text=tab.title)
        self.notebook.bind("<<NotebookTabChanged>>", lambda _e: self.refresh_preview())

        self.preview = PreviewPane(right, width=320)
        self.preview.pack(fill="both", expand=True)
        self._build_print_bar(right)

        # ステータスバー
        self.status_var = tk.StringVar(value="準備完了")
        self.status_label = ttk.Label(self, textvariable=self.status_var, anchor="w")
        self.status_label.pack(fill="x", pady=(6, 0))

        # D&D（対応時のみ）
        self.document_tab.enable_dnd(root)

        # キーバインド
        root.bind("<Control-p>", lambda _e: self.print_current())
        root.bind("<Control-Key-1>", lambda _e: self.notebook.select(0))
        root.bind("<Control-Key-2>", lambda _e: self.notebook.select(1))
        root.bind("<Control-Key-3>", lambda _e: self.notebook.select(2))
        root.bind("<Control-Key-4>", lambda _e: self.notebook.select(3))
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        last = int(self.cfg["ui"].get("last_tab", 0))
        if 0 <= last < len(self.tabs):
            self.notebook.select(last)
        self._purge_old()
        self.refresh_preview()
        self.after(80, self._drain_results)

    # ------------------------------------------------------------------ 画面
    def _setup_style(self) -> None:
        style = ttk.Style()
        if "vista" in style.theme_names():
            style.theme_use("vista")
        elif "aqua" in style.theme_names():
            style.theme_use("aqua")
        elif "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Print.TButton", font=("", 11, "bold"))

    def _build_print_bar(self, parent) -> None:
        bar = ttk.Frame(parent, padding=(0, 8, 0, 0))
        bar.pack(fill="x")

        self.copies = tk.IntVar(value=self.cfg["printer"].get("copies", 1))
        row = ttk.Frame(bar)
        row.pack(fill="x")
        ttk.Label(row, text="部数").pack(side="left")
        ttk.Spinbox(row, from_=1, to=20, textvariable=self.copies, width=4).pack(side="left", padx=(4, 12))
        self.printer_label = ttk.Label(row, text="", foreground="#666")
        self.printer_label.pack(side="left")
        ttk.Button(row, text="プレビュー更新", command=self.refresh_preview).pack(side="right")

        self.print_button = ttk.Button(bar, text="印 刷  (Ctrl+P)", style="Print.TButton",
                                       command=self.print_current)
        self.print_button.pack(fill="x", pady=(8, 0), ipady=6)
        self._update_printer_label()

    def _update_printer_label(self) -> None:
        p = self.cfg["printer"]
        self.printer_label.configure(text=f"{p['host']}:{p['port']}  {p['width_dots']}dot")

    # ------------------------------------------------------------------ 状態
    @property
    def width_dots(self) -> int:
        return int(self.cfg["printer"]["width_dots"])

    def printer_config(self) -> printer.PrinterConfig:
        return printer.PrinterConfig.from_dict(self.cfg["printer"])

    def post(self, callback) -> None:
        """ワーカースレッドからメインスレッドへ処理を渡す。

        Tk のウィジェット操作はメインスレッド専用（after() も厳密には
        スレッドセーフではない）ため、キュー経由で必ずメインスレッドに戻す。
        """
        self._callbacks.put(callback)

    def _copies(self) -> int:
        try:
            return max(1, min(50, int(self.copies.get())))
        except (tk.TclError, ValueError):
            self.copies.set(1)
            return 1

    def current_tab(self):
        try:
            index = self.notebook.index(self.notebook.select())
        except tk.TclError:
            return self.text_tab
        return self.tabs[index]

    def select_tab(self, tab) -> None:
        self.notebook.select(self.tabs.index(tab))

    def status(self, message: str, level: str = "info") -> None:
        self.status_var.set(message)
        self.status_label.configure(foreground=STATUS_COLORS.get(level, "#333"))

    def save_config(self) -> None:
        config.save(self.cfg)
        self._update_printer_label()

    # ------------------------------------------------------------------ プレビュー
    def refresh_preview(self) -> None:
        tab = self.current_tab()
        if tab is self.history_tab:
            return
        try:
            image = tab.build_image()
        except Exception as exc:  # noqa: BLE001
            self.status(f"プレビュー生成に失敗: {exc}", "error")
            return
        self.preview.show(image)

    # ------------------------------------------------------------------ 印刷
    def print_current(self) -> None:
        tab = self.current_tab()
        if tab is self.history_tab:
            self.history_tab.reprint()
            return
        try:
            image = tab.build_image()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("印刷", f"印刷データの生成に失敗しました:\n{exc}")
            return
        if image is None:
            self.status(tab.empty_message(), "warn")
            return
        meta = tab.describe()
        self.send_image(image, **meta)

    def send_image(
        self,
        image: Image.Image,
        *,
        kind: str = "text",
        title: str = "",
        body: str = "",
        source: str = "",
        params: dict | None = None,
        printer_cfg: printer.PrinterConfig | None = None,
    ) -> None:
        if self._printing:
            self.status("前の印刷を送信中です…", "warn")
            return
        cfg = printer_cfg or self.printer_config()
        if not cfg.host:
            messagebox.showwarning("印刷", "プリンタの IP アドレスを設定タブで指定してください。")
            self.select_tab(self.settings_tab)
            return
        copies = self._copies()
        if self.cfg["ui"].get("confirm_before_print"):
            mm = image.height / 8
            if not messagebox.askyesno("印刷の確認", f"{copies} 部 / 約 {mm:.0f} mm 印刷します。よろしいですか？"):
                return

        self._printing = True
        self.print_button.configure(state="disabled")
        self.status("送信中…", "busy")
        payload = {
            "kind": kind, "title": title, "body": body, "source": source,
            "params": params or {}, "copies": copies,
        }

        def worker() -> None:
            try:
                printer.print_image(cfg, image, copies=copies)
                self._results.put(("ok", image, cfg, payload, ""))
            except printer.PrinterError as exc:
                self._results.put(("error", image, cfg, payload, str(exc)))
            except Exception as exc:  # noqa: BLE001
                self._results.put(("error", image, cfg, payload, f"予期しないエラー: {exc}"))

        threading.Thread(target=worker, daemon=True).start()

    def _drain_results(self) -> None:
        while True:
            try:
                callback = self._callbacks.get_nowait()
            except queue.Empty:
                break
            try:
                callback()
            except Exception as exc:  # noqa: BLE001
                self.status(f"エラー: {exc}", "error")
        while True:
            try:
                status, image, cfg, payload, error = self._results.get_nowait()
            except queue.Empty:
                break
            self._finish_print(status, image, cfg, payload, error)
        self.after(80, self._drain_results)

    def _finish_print(self, status, image, cfg, payload, error) -> None:
        self._printing = False
        self.print_button.configure(state="normal")
        if status == "ok":
            self.status(f"印刷しました（{payload['copies']} 部 / 約 {image.height / 8:.0f} mm）", "ok")
        else:
            self.status(error, "error")
            messagebox.showerror("印刷失敗", error)

        if self.cfg["history"]["enabled"]:
            sync = (self.cfg["history"]["sync_dir"]
                    if self.cfg["history"]["sync_enabled"] else None)
            try:
                self.history.add(
                    kind=payload["kind"], image=image, title=payload["title"],
                    body=payload["body"], source=payload["source"], copies=payload["copies"],
                    printer=f"{cfg.host}:{cfg.port}", status=status, error=error,
                    params=payload["params"], sync_dir=sync,
                )
                self.history_tab.reload()
            except Exception as exc:  # noqa: BLE001
                self.status(f"履歴の保存に失敗: {exc}", "warn")

    # ------------------------------------------------------------------ 連携
    def load_text(self, body: str) -> None:
        self.select_tab(self.text_tab)
        self.text_tab.load(body)

    def open_in_image_tab(self, path: str) -> None:
        self.select_tab(self.image_tab)
        self.image_tab.load_path(path)

    def hide_window(self) -> None:
        self.root.withdraw()
        self.root.update()

    def show_window(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    # ------------------------------------------------------------------ 終了処理
    def _purge_old(self) -> None:
        days = int(self.cfg["history"].get("keep_days", 0))
        if days > 0:
            removed = self.history.purge_older_than(days)
            if removed:
                self.status(f"{removed} 件の古い履歴を削除しました", "info")

    def on_close(self) -> None:
        for tab in self.tabs:
            try:
                tab.persist()
            except Exception:  # noqa: BLE001
                pass
        try:
            self.cfg["ui"]["last_tab"] = self.notebook.index(self.notebook.select())
            self.cfg["ui"]["window"] = self.root.geometry()
            self.cfg["printer"]["copies"] = self._copies()
            config.save(self.cfg)
        except Exception:  # noqa: BLE001
            pass
        self.history.close()
        self.root.destroy()


def main() -> int:
    root = make_root()
    App(root)
    root.mainloop()
    return 0
