"""更新の確認・ダウンロード・適用を担当する UI。

ネットワーク処理はすべてワーカースレッドで行い、画面操作は
:meth:`App.post` 経由でメインスレッドに戻す。
"""

from __future__ import annotations

import datetime as _dt
import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

from .. import __version__, updater


class UpdateFlow:
    """更新確認から適用までの一連の流れ。"""

    def __init__(self, app):
        self.app = app
        self._busy = False

    # ------------------------------------------------------------------ 確認
    def check(self, *, silent: bool = False) -> None:
        """更新を確認する。

        :param silent: 起動時の自動確認。更新が無いときや失敗したときは黙る。
        """
        if self._busy:
            return
        cfg = self.app.cfg["update"]
        repo = cfg.get("repo") or updater.DEFAULT_REPO
        self._busy = True
        if not silent:
            self.app.status("更新を確認しています…", "busy")

        def worker() -> None:
            try:
                release = updater.fetch_latest(repo)
            except updater.UpdateError as exc:
                self.app.post(lambda e=exc: self._check_failed(e, silent))
                return
            self.app.post(lambda: self._check_done(release, silent))

        threading.Thread(target=worker, daemon=True).start()

    def _check_failed(self, exc: Exception, silent: bool) -> None:
        self._busy = False
        if silent:
            return
        self.app.status(f"更新の確認に失敗: {exc}", "warn")

    def _check_done(self, release: updater.Release, silent: bool) -> None:
        self._busy = False
        cfg = self.app.cfg["update"]
        cfg["last_checked"] = _dt.datetime.now().isoformat(timespec="seconds")

        if release.prerelease and not cfg.get("include_prerelease"):
            if not silent:
                self.app.status(f"最新は事前リリース {release.tag} のみです", "info")
            return

        if not updater.is_newer(release.version, __version__):
            if not silent:
                self.app.status(f"最新版です（{__version__}）", "ok")
            return

        if silent and cfg.get("skip_version") == release.version:
            return

        self.app.status(f"新しい版があります: {release.tag}", "ok")
        UpdateDialog(self.app, release, self).show()

    # ------------------------------------------------------------------ 適用
    def apply(self, release: updater.Release) -> None:
        """配布物を落として更新を実行する。"""
        asset = updater.pick_asset(release)
        if asset is None:
            messagebox.showinfo(
                "自動更新",
                "この環境に合う配布物が見つかりませんでした。\n\n"
                + updater.manual_instructions(),
            )
            webbrowser.open(release.html_url)
            return
        ProgressDialog(self.app, release, asset).run()


class UpdateDialog:
    """新しい版が見つかったときに出す案内。"""

    def __init__(self, app, release: updater.Release, flow: UpdateFlow):
        self.app = app
        self.release = release
        self.flow = flow

    def show(self) -> None:
        top = tk.Toplevel(self.app.winfo_toplevel())
        top.title("更新があります")
        top.transient(self.app.winfo_toplevel())
        top.geometry("580x430")

        frame = ttk.Frame(top, padding=14)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text=f"新しい版 {self.release.tag} が公開されています",
                  font=("", 12, "bold")).pack(anchor="w")
        ttk.Label(frame, text=f"お使いの版: {__version__}", foreground="#666").pack(anchor="w")

        ttk.Label(frame, text="変更点", font=("", 10, "bold")).pack(anchor="w", pady=(12, 4))
        box = ttk.Frame(frame, relief="sunken", borderwidth=1)
        box.pack(fill="both", expand=True)
        notes = tk.Text(box, wrap="word", height=10, borderwidth=0, highlightthickness=0,
                        font=("", 10))
        scroll = ttk.Scrollbar(box, orient="vertical", command=notes.yview)
        notes.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        notes.pack(side="left", fill="both", expand=True)
        notes.insert("1.0", self.release.notes.strip() or "（変更点の記載がありません）")
        notes.configure(state="disabled")

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(12, 0))

        def close() -> None:
            top.destroy()

        def update_now() -> None:
            top.destroy()
            self.flow.apply(self.release)

        def open_page() -> None:
            webbrowser.open(self.release.html_url)

        def skip() -> None:
            self.app.cfg["update"]["skip_version"] = self.release.version
            self.app.save_config()
            self.app.status(f"{self.release.tag} をスキップします", "info")
            top.destroy()

        ttk.Button(buttons, text="後で", command=close).pack(side="right")
        ttk.Button(buttons, text="スキップ", command=skip).pack(side="right", padx=6)
        ttk.Button(buttons, text="リリースページ", command=open_page).pack(side="left")
        ttk.Button(buttons, text="更新する", command=update_now).pack(side="left", padx=6)

        top.grab_set()


class ProgressDialog:
    """ダウンロードの進捗と、インストーラ起動までの確認。"""

    def __init__(self, app, release: updater.Release, asset: updater.Asset):
        self.app = app
        self.release = release
        self.asset = asset
        self.top: tk.Toplevel | None = None
        self.bar: ttk.Progressbar | None = None
        self.label: ttk.Label | None = None
        self.cancelled = False

    def run(self) -> None:
        top = tk.Toplevel(self.app.winfo_toplevel())
        self.top = top
        top.title("更新をダウンロード中")
        top.transient(self.app.winfo_toplevel())
        top.resizable(False, False)

        frame = ttk.Frame(top, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=self.asset.name).pack(anchor="w")
        self.bar = ttk.Progressbar(frame, length=380, mode="determinate", maximum=100)
        self.bar.pack(pady=8)
        self.label = ttk.Label(frame, text="接続しています…", foreground="#666")
        self.label.pack(anchor="w")
        ttk.Button(frame, text="中止", command=self._cancel).pack(anchor="e", pady=(10, 0))
        top.protocol("WM_DELETE_WINDOW", self._cancel)
        top.grab_set()

        threading.Thread(target=self._worker, daemon=True).start()

    def _cancel(self) -> None:
        self.cancelled = True
        if self.top:
            self.top.destroy()
            self.top = None

    def _worker(self) -> None:
        try:
            checksums = updater.fetch_checksums(self.release)
            path = updater.download(self.asset, progress=self._progress)
            if self.cancelled:
                return
            updater.verify(path, checksums)
        except updater.UpdateError as exc:
            self.app.post(lambda e=exc: self._failed(e))
            return
        except Exception as exc:  # noqa: BLE001
            self.app.post(lambda e=exc: self._failed(e))
            return
        self.app.post(lambda: self._finished(path))

    def _progress(self, received: int, total: int) -> None:
        if self.cancelled:
            raise updater.UpdateError("中止しました")
        percent = int(received * 100 / total) if total else 0
        megabytes = received / 1024 / 1024
        self.app.post(lambda: self._render(percent, megabytes, total))

    def _render(self, percent: int, megabytes: float, total: int) -> None:
        if not self.top or not self.bar or not self.label:
            return
        self.bar["value"] = percent
        if total:
            self.label.configure(text=f"{percent}%  ({megabytes:.1f} / {total/1024/1024:.1f} MB)")
        else:
            self.label.configure(text=f"{megabytes:.1f} MB")

    def _failed(self, exc: Exception) -> None:
        if self.top:
            self.top.destroy()
            self.top = None
        if self.cancelled:
            self.app.status("更新を中止しました", "info")
            return
        self.app.status(f"更新に失敗: {exc}", "error")
        messagebox.showerror("更新に失敗しました", str(exc))

    def _finished(self, path) -> None:
        if self.top:
            self.top.destroy()
            self.top = None
        proceed = messagebox.askyesno(
            "更新の適用",
            f"ダウンロードが完了しました。\n\n{path}\n\n"
            "インストーラを起動して thermal.memo を終了します。\n"
            "未保存の入力があれば先に印刷してください。\n\n続けますか？",
        )
        if not proceed:
            self.app.status(f"ダウンロード済み: {path}", "info")
            return
        try:
            updater.launch_installer(path)
        except updater.UpdateError as exc:
            messagebox.showerror("更新に失敗しました", str(exc))
            return
        self.app.on_close()
