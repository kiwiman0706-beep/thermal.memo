"""設定タブ（プリンタ・フォント・履歴）。"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .. import fonts, printer, render
from ..config import PAPER_PRESETS, config_path
from .common import section


def _int(variable, fallback: int) -> int:
    """入力欄が空/不正でも落ちないように読む。"""
    try:
        return int(variable.get())
    except (tk.TclError, ValueError):
        variable.set(fallback)
        return fallback


def _float(variable, fallback: float) -> float:
    try:
        return float(variable.get())
    except (tk.TclError, ValueError):
        variable.set(fallback)
        return fallback


class SettingsTab(ttk.Frame):
    title = "設定"

    def __init__(self, master, app):
        super().__init__(master, padding=10)
        self.app = app
        p = app.cfg["printer"]
        t = app.cfg["text"]
        h = app.cfg["history"]

        self.host = tk.StringVar(value=p["host"])
        self.port = tk.IntVar(value=p["port"])
        self.paper = tk.StringVar(value=p.get("paper", "80mm"))
        self.width_dots = tk.IntVar(value=p["width_dots"])
        self.timeout = tk.DoubleVar(value=p["timeout"])
        self.cut = tk.BooleanVar(value=p["cut"])
        self.feed_lines = tk.IntVar(value=p["feed_lines"])
        self.chunk_rows = tk.IntVar(value=p["chunk_rows"])
        self.font_path = tk.StringVar(value=t["font_path"] or "")
        self.timestamp_format = tk.StringVar(value=t["timestamp_format"])
        self.history_enabled = tk.BooleanVar(value=h["enabled"])
        self.keep_days = tk.IntVar(value=h["keep_days"])
        self.sync_enabled = tk.BooleanVar(value=h["sync_enabled"])
        self.sync_dir = tk.StringVar(value=h["sync_dir"] or "")
        self.confirm = tk.BooleanVar(value=app.cfg["ui"]["confirm_before_print"])

        # --- プリンタ
        pr = section(self, "プリンタ（ESC/POS · RAW 9100）")
        row = ttk.Frame(pr)
        row.pack(fill="x")
        ttk.Label(row, text="IP アドレス").pack(side="left")
        ttk.Entry(row, textvariable=self.host, width=18).pack(side="left", padx=(4, 12))
        ttk.Label(row, text="ポート").pack(side="left")
        ttk.Entry(row, textvariable=self.port, width=7).pack(side="left", padx=4)
        ttk.Button(row, text="接続テスト", command=self.test_connection).pack(side="left", padx=8)
        ttk.Button(row, text="LAN を探す", command=self.scan).pack(side="left")

        row2 = ttk.Frame(pr)
        row2.pack(fill="x", pady=(8, 0))
        ttk.Label(row2, text="用紙幅").pack(side="left")
        combo = ttk.Combobox(row2, textvariable=self.paper, width=14, state="readonly",
                             values=list(PAPER_PRESETS.keys()) + ["カスタム"])
        combo.pack(side="left", padx=(4, 8))
        combo.bind("<<ComboboxSelected>>", self._on_paper)
        ttk.Label(row2, text="印字ドット数").pack(side="left")
        ttk.Entry(row2, textvariable=self.width_dots, width=7).pack(side="left", padx=4)
        ttk.Label(row2, text="（203dpi: 58mm=384 / 80mm=576）", foreground="#999").pack(side="left", padx=6)

        row3 = ttk.Frame(pr)
        row3.pack(fill="x", pady=(8, 0))
        ttk.Checkbutton(row3, text="印刷後にカット", variable=self.cut).pack(side="left")
        ttk.Label(row3, text="カット前フィード").pack(side="left", padx=(12, 4))
        ttk.Spinbox(row3, from_=0, to=10, textvariable=self.feed_lines, width=4).pack(side="left")
        ttk.Label(row3, text="タイムアウト秒").pack(side="left", padx=(12, 4))
        ttk.Spinbox(row3, from_=1, to=60, textvariable=self.timeout, width=5).pack(side="left")
        ttk.Label(row3, text="分割行数").pack(side="left", padx=(12, 4))
        ttk.Spinbox(row3, from_=16, to=1024, increment=16, textvariable=self.chunk_rows,
                    width=6).pack(side="left")

        row4 = ttk.Frame(pr)
        row4.pack(fill="x", pady=(8, 0))
        ttk.Button(row4, text="テストページを印刷", command=self.print_test_page).pack(side="left")
        ttk.Button(row4, text="紙送り＋カット", command=self.feed_cut).pack(side="left", padx=6)
        self.scan_status = ttk.Label(row4, text="", foreground="#666")
        self.scan_status.pack(side="left", padx=10)

        # --- フォント
        ft = section(self, "フォント")
        row = ttk.Frame(ft)
        row.pack(fill="x")
        ttk.Entry(row, textvariable=self.font_path).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="選ぶ…", command=self.choose_font).pack(side="left", padx=4)
        ttk.Button(row, text="自動", command=lambda: self.font_path.set("")).pack(side="left")
        detected = fonts.detect(None)
        ttk.Label(ft, text=f"自動検出: {fonts.display_name(detected)}", foreground="#777").pack(anchor="w", pady=(4, 0))

        row = ttk.Frame(ft)
        row.pack(fill="x", pady=(6, 0))
        ttk.Label(row, text="日時の書式").pack(side="left")
        ttk.Entry(row, textvariable=self.timestamp_format, width=22).pack(side="left", padx=4)
        ttk.Label(row, text="（strftime 書式）", foreground="#999").pack(side="left")

        # --- 履歴
        hs = section(self, "履歴・同期")
        row = ttk.Frame(hs)
        row.pack(fill="x")
        ttk.Checkbutton(row, text="印刷履歴を残す", variable=self.history_enabled).pack(side="left")
        ttk.Label(row, text="保存日数（0=無期限）").pack(side="left", padx=(12, 4))
        ttk.Spinbox(row, from_=0, to=3650, textvariable=self.keep_days, width=6).pack(side="left")
        row = ttk.Frame(hs)
        row.pack(fill="x", pady=(6, 0))
        ttk.Checkbutton(row, text="同期フォルダへ自動書き出し", variable=self.sync_enabled).pack(side="left")
        ttk.Entry(row, textvariable=self.sync_dir).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(row, text="選ぶ…", command=self.choose_sync).pack(side="left")

        # --- その他
        misc = section(self, "動作")
        ttk.Checkbutton(misc, text="印刷前に確認ダイアログを出す", variable=self.confirm).pack(anchor="w")
        ttk.Label(misc, text=f"設定ファイル: {config_path()}", foreground="#777").pack(anchor="w", pady=(6, 0))
        ttk.Label(misc, text=f"データ保存先: {app.history.base}", foreground="#777").pack(anchor="w")

        ttk.Button(self, text="設定を保存", command=self.save).pack(anchor="e", pady=8)

    # ------------------------------------------------------------------ 動作
    def _on_paper(self, _event=None) -> None:
        preset = PAPER_PRESETS.get(self.paper.get())
        if preset:
            self.width_dots.set(preset)

    def _printer_cfg(self) -> printer.PrinterConfig:
        return printer.PrinterConfig(
            host=self.host.get().strip(),
            port=_int(self.port, 9100),
            timeout=_float(self.timeout, 8.0),
            width_dots=_int(self.width_dots, 576),
            cut=self.cut.get(),
            feed_lines=_int(self.feed_lines, 3),
            chunk_rows=_int(self.chunk_rows, 128),
        )

    def test_connection(self) -> None:
        cfg = self._printer_cfg()
        self.app.status("接続テスト中…", "busy")

        def worker() -> None:
            ok, message = printer.test_connection(cfg)
            self.app.post(lambda: self.app.status(message, "ok" if ok else "error"))

        threading.Thread(target=worker, daemon=True).start()

    def scan(self) -> None:
        base = self.host.get().strip() or "192.168.1.1"
        if not messagebox.askyesno(
            "LAN を探す",
            f"{base} と同じサブネット（/24）の 9100 番ポートを順に調べます。\n"
            "自分の管理下のネットワークでのみ実行してください。よろしいですか？",
        ):
            return
        self.app.status("スキャン中…", "busy")
        port = _int(self.port, 9100)

        def worker() -> None:
            try:
                found = printer.scan_subnet(
                    base, port,
                    progress=lambda i, n: self.app.post(
                        lambda: self.scan_status.configure(text=f"{i}/{n}")),
                )
            except ValueError as exc:
                self.app.post(lambda e=exc: self.app.status(str(e), "error"))
                return
            self.app.post(lambda: self._scan_done(found))

        threading.Thread(target=worker, daemon=True).start()

    def _scan_done(self, found: list[str]) -> None:
        self.scan_status.configure(text="")
        if not found:
            self.app.status("見つかりませんでした", "warn")
            return
        self.host.set(found[0])
        self.app.status(f"候補: {', '.join(found)} → 先頭を設定しました", "ok")

    def print_test_page(self) -> None:
        cfg = self._printer_cfg()
        sample = (
            "thermal.memo テストページ\n"
            "─────────────\n"
            "あいうえお 漢字 ｶﾀｶﾅ ABCabc 0123\n"
            "髙﨑 塚﨑 ①②③ ㎎ ㎖ ℃ №\n"
            f"用紙幅 {cfg.width_dots} dot / カット {'ON' if cfg.cut else 'OFF'}\n"
            "この行が切れずに印字されていれば設定は正しいです。"
        )
        image = render.text_to_image(
            sample, width_dots=cfg.width_dots,
            font_path=self.font_path.get() or None,
            font_size=self.app.cfg["text"]["font_size"],
            timestamp=True, timestamp_format=self.timestamp_format.get(),
        )
        self.app.send_image(image, kind="text", title="テストページ", body=sample,
                            source="設定タブ", printer_cfg=cfg)

    def feed_cut(self) -> None:
        cfg = self._printer_cfg()

        def worker() -> None:
            try:
                printer.feed_and_cut(cfg)
                self.app.post(lambda: self.app.status("紙送りしました", "ok"))
            except printer.PrinterError as exc:
                self.app.post(lambda e=exc: self.app.status(str(e), "error"))

        threading.Thread(target=worker, daemon=True).start()

    def choose_font(self) -> None:
        path = filedialog.askopenfilename(
            title="フォントを選択",
            filetypes=[("フォント", "*.ttf *.ttc *.otf"), ("すべて", "*.*")],
        )
        if path:
            self.font_path.set(path)

    def choose_sync(self) -> None:
        path = filedialog.askdirectory(title="同期フォルダを選択")
        if path:
            self.sync_dir.set(path)
            self.sync_enabled.set(True)

    def save(self) -> None:
        cfg = self.app.cfg
        cfg["printer"].update({
            "host": self.host.get().strip(),
            "port": _int(self.port, 9100),
            "paper": self.paper.get(),
            "width_dots": max(64, _int(self.width_dots, 576)),
            "timeout": _float(self.timeout, 8.0),
            "cut": self.cut.get(),
            "feed_lines": _int(self.feed_lines, 3),
            "chunk_rows": max(16, _int(self.chunk_rows, 128)),
        })
        cfg["text"].update({
            "font_path": self.font_path.get().strip() or None,
            "timestamp_format": self.timestamp_format.get(),
        })
        cfg["history"].update({
            "enabled": self.history_enabled.get(),
            "keep_days": _int(self.keep_days, 0),
            "sync_enabled": self.sync_enabled.get(),
            "sync_dir": self.sync_dir.get().strip() or None,
        })
        cfg["ui"]["confirm_before_print"] = self.confirm.get()
        self.app.save_config()
        self.app.refresh_preview()
        self.app.history_tab.update_sync_label()
        self.app.status("設定を保存しました", "ok")

    # 共通インタフェース（このタブは印刷対象を持たない）
    def build_image(self):
        return None

    def describe(self) -> dict:
        return {"kind": "text", "title": "", "body": "", "source": "", "params": {}}

    def empty_message(self) -> str:
        return "設定タブでは印刷できません（テストページをお使いください）"

    def persist(self) -> None:
        pass
